from datetime import datetime, timezone
import smtplib

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.models.notification import NotificationEventType, NotificationOutbox, NotificationStatus
from app.models.user import User, UserRole
from app.services.notifications import (
    EmailDeliveryError,
    SMTPEmailProvider,
    SendGridEmailProvider,
    ResendEmailProvider,
    claim_due,
    deliver_job,
    email_provider,
    enqueue,
)
from tests.conftest import TestingSessionLocal


@pytest.fixture(autouse=True)
def smtp_settings(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "localhost")
    monkeypatch.setattr(settings, "smtp_port", 1025)
    monkeypatch.setattr(settings, "smtp_username", "")
    monkeypatch.setattr(settings, "smtp_password", "")
    monkeypatch.setattr(settings, "smtp_use_starttls", False)
    monkeypatch.setattr(settings, "email_from_address", "notifications@careloop.app")
    monkeypatch.setattr(settings, "email_timeout_seconds", 8)


class FakeSMTP:
    instances = []
    failure = None

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.started_tls = False
        self.logged_in = None
        self.messages = []
        self.__class__.instances.append(self)

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def starttls(self): self.started_tls = True
    def login(self, username, password):
        self.logged_in = (username, password)
    def send_message(self, message):
        if self.failure: raise self.failure
        self.messages.append(message)
        return {}


def setup_function():
    FakeSMTP.instances.clear()
    FakeSMTP.failure = None


def test_unauthenticated_mailpit_style_delivery():
    message_id = SMTPEmailProvider(smtp_factory=FakeSMTP).send(to="patient@example.test", subject="Reminder", text="Take medicine", idempotency_key="notification-1")
    client = FakeSMTP.instances[0]
    assert message_id.startswith("smtp-") and client.logged_in is None and not client.started_tls
    assert client.messages[0]["To"] == "patient@example.test"


def test_starttls_is_used_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_use_starttls", True)
    SMTPEmailProvider(smtp_factory=FakeSMTP).send(to="patient@example.test", subject="Test", text="Body")
    assert FakeSMTP.instances[0].started_tls


def test_authenticated_delivery_uses_both_credentials(monkeypatch):
    monkeypatch.setattr(settings, "smtp_username", "smtp-user")
    monkeypatch.setattr(settings, "smtp_password", "smtp-password")
    SMTPEmailProvider(smtp_factory=FakeSMTP).send(to="patient@example.test", subject="Test", text="Body")
    assert FakeSMTP.instances[0].logged_in == ("smtp-user", "smtp-password")


def test_partial_credentials_are_rejected_without_connecting(monkeypatch):
    monkeypatch.setattr(settings, "smtp_username", "smtp-user")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, smtp_username="smtp-user")
    with pytest.raises(EmailDeliveryError) as raised:
        SMTPEmailProvider(smtp_factory=FakeSMTP).send(to="patient@example.test", subject="Test", text="Body")
    assert raised.value.category == "invalid_configuration"
    assert not FakeSMTP.instances


@pytest.mark.parametrize(
    "failure,category,retryable",
    [
        (TimeoutError("timed out"), "connection", True),
        (smtplib.SMTPDataError(450, b"temporary"), "provider_unavailable", True),
        (smtplib.SMTPDataError(550, b"permanent"), "provider_rejected", False),
    ],
)
def test_smtp_error_classification(failure, category, retryable):
    FakeSMTP.failure = failure
    with pytest.raises(EmailDeliveryError) as raised:
        SMTPEmailProvider(smtp_factory=FakeSMTP).send(to="patient@example.test", subject="Test", text="Body")
    assert raised.value.category == category and raised.value.retryable is retryable


def test_authentication_error_redacts_credentials(monkeypatch):
    monkeypatch.setattr(settings, "smtp_username", "smtp-user")
    monkeypatch.setattr(settings, "smtp_password", "smtp-password")
    FakeSMTP.failure = smtplib.SMTPAuthenticationError(535, b"smtp-password leaked by server")
    with pytest.raises(EmailDeliveryError) as raised:
        SMTPEmailProvider(smtp_factory=FakeSMTP).send(to="patient@example.test", subject="Test", text="Body")
    assert raised.value.category == "authentication"
    assert "smtp-password" not in raised.value.message and "smtp-password" not in str(raised.value)


def test_unicode_credential_error_is_permanent_and_does_not_crash_worker(monkeypatch):
    class UnicodeCredentialSMTP(FakeSMTP):
        def login(self, username, password):
            raise UnicodeEncodeError("ascii", password, 0, 1, "invalid")

    monkeypatch.setattr(settings, "smtp_username", "smtp-user")
    monkeypatch.setattr(settings, "smtp_password", "pässword")
    with TestingSessionLocal() as db:
        patient = User(full_name="Unicode SMTP", email="smtp-unicode@example.test", password_hash="x", role=UserRole.PATIENT)
        db.add(patient); db.flush()
        job = enqueue(db, event_type=NotificationEventType.APPOINTMENT_CONFIRMED, recipient=patient, idempotency_key="smtp-unicode", payload={"message": "Appointment confirmed"})
        db.commit()
        claimed = claim_due(db, "worker", now=datetime.now(timezone.utc))
        deliver_job(db, claimed[0].id, SMTPEmailProvider(smtp_factory=UnicodeCredentialSMTP), now=datetime.now(timezone.utc))
        stored = db.get(NotificationOutbox, job.id)
        assert stored.status == NotificationStatus.PERMANENTLY_FAILED and stored.failure_category == "authentication"
        assert "pässword" not in (stored.failure_message or "")


def test_worker_delivery_and_duplicate_prevention():
    with TestingSessionLocal() as db:
        patient = User(full_name="SMTP Patient", email="smtp-worker@example.test", password_hash="x", role=UserRole.PATIENT)
        db.add(patient); db.flush()
        job = enqueue(db, event_type=NotificationEventType.APPOINTMENT_CONFIRMED, recipient=patient, idempotency_key="smtp-worker-key", payload={"message": "Appointment confirmed"})
        db.commit()
        claimed = claim_due(db, "worker", now=datetime.now(timezone.utc))
        provider = SMTPEmailProvider(smtp_factory=FakeSMTP)
        deliver_job(db, claimed[0].id, provider, now=datetime.now(timezone.utc))
        deliver_job(db, claimed[0].id, provider, now=datetime.now(timezone.utc))
        stored = db.get(NotificationOutbox, job.id)
        assert stored.status == NotificationStatus.SENT and stored.provider_message_id.startswith("smtp-")
    assert len(FakeSMTP.instances) == 1 and len(FakeSMTP.instances[0].messages) == 1


def test_provider_selection_preserves_existing_providers(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "smtp")
    assert isinstance(email_provider(), SMTPEmailProvider)
    monkeypatch.setattr(settings, "email_provider", "sendgrid")
    assert isinstance(email_provider(), SendGridEmailProvider)
    monkeypatch.setattr(settings, "email_provider", "resend")
    assert isinstance(email_provider(), ResendEmailProvider)
