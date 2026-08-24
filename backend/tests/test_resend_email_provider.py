from datetime import datetime, timezone
import json

import httpx
import pytest

from app.core.config import settings
from app.models.notification import NotificationEventType, NotificationOutbox, NotificationStatus
from app.models.user import User, UserRole
from app.services.notifications import (
    EmailDeliveryError,
    LogEmailProvider,
    ResendEmailProvider,
    SendGridEmailProvider,
    _template,
    claim_due,
    deliver_job,
    email_provider,
    enqueue,
)
from tests.conftest import TestingSessionLocal


@pytest.fixture(autouse=True)
def resend_settings(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "test-resend-key")
    monkeypatch.setattr(settings, "resend_base_url", "https://api.resend.com")
    monkeypatch.setattr(settings, "email_from_address", "CareLoop <onboarding@resend.dev>")
    monkeypatch.setattr(settings, "email_timeout_seconds", 8)


def mock_transport(handler):
    return httpx.MockTransport(handler)


def test_resend_success_forwards_authorization_and_idempotency_key():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "resend-message-id"})

    result = ResendEmailProvider(transport=mock_transport(handler)).send(
        to="patient@example.test", subject="Reminder", text="Take medication", idempotency_key="careloop-notification-key",
    )
    assert result == "resend-message-id"
    assert seen[0].url.path == "/emails"
    assert seen[0].headers.get("Authorization", "") != ""
    assert seen[0].headers["Idempotency-Key"] == "careloop-notification-key"
    assert set(json.loads(seen[0].content)) == {"from", "to", "subject", "text"}


def test_resend_missing_configuration_is_safe(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "")
    with pytest.raises(EmailDeliveryError) as raised:
        ResendEmailProvider().send(to="patient@example.test", subject="Test", text="Test")
    assert raised.value.category == "missing_configuration"


@pytest.mark.parametrize(
    "failure,category,retryable",
    [
        (httpx.ReadTimeout("timeout"), "connection", True),
        (httpx.ConnectError("connection"), "connection", True),
        (httpx.Response(429), "provider_unavailable", True),
        (httpx.Response(500), "provider_unavailable", True),
        (httpx.Response(400), "provider_rejected", False),
        (httpx.Response(401), "authentication", False),
        (httpx.Response(403), "authentication", False),
    ],
)
def test_resend_classifies_failures_without_raw_provider_data(failure, category, retryable):
    def handler(_request):
        if isinstance(failure, Exception): raise failure
        return failure

    with pytest.raises(EmailDeliveryError) as raised:
        ResendEmailProvider(transport=mock_transport(handler)).send(to="patient@example.test", subject="Test", text="Test")
    assert raised.value.category == category and raised.value.retryable is retryable


def test_resend_safe_error_never_contains_api_key(monkeypatch):
    secret = "resend-secret-that-must-not-leak"
    monkeypatch.setattr(settings, "resend_api_key", secret)
    with pytest.raises(EmailDeliveryError) as raised:
        ResendEmailProvider(transport=mock_transport(lambda _request: httpx.Response(401, text=secret))).send(to="patient@example.test", subject="Test", text="Test")
    assert secret not in raised.value.message
    assert secret not in str(raised.value)


def test_medication_template_excludes_private_clinical_information():
    with TestingSessionLocal() as db:
        patient = User(full_name="Resend Patient", email="resend-template@example.test", password_hash="x", role=UserRole.PATIENT)
        db.add(patient); db.flush()
        job = enqueue(db, event_type=NotificationEventType.MEDICATION_REMINDER_DUE, recipient=patient, idempotency_key="resend-template", payload={
            "medication_name": "Example medicine", "dosage": "10 mg", "route": "oral", "reminder_time": "09:00",
            "food_instructions": "With food", "additional_instructions": "Use water",
            "private_doctor_notes": "private note", "symptoms": "private symptoms", "diagnosis": "private diagnosis",
        })
        text = _template(job)
    assert "Example medicine" in text and "10 mg" in text and "private" not in text


def test_resend_worker_delivery_persists_message_id_and_is_idempotent():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "resend-job-id"})

    provider = ResendEmailProvider(transport=mock_transport(handler))
    with TestingSessionLocal() as db:
        patient = User(full_name="Worker Patient", email="resend-worker@example.test", password_hash="x", role=UserRole.PATIENT)
        db.add(patient); db.flush()
        job = enqueue(db, event_type=NotificationEventType.APPOINTMENT_CONFIRMED, recipient=patient, idempotency_key="resend-worker", payload={"message": "Appointment confirmed"})
        db.commit()
        claimed = claim_due(db, "worker", now=datetime.now(timezone.utc))
        deliver_job(db, claimed[0].id, provider, now=datetime.now(timezone.utc))
        deliver_job(db, claimed[0].id, provider, now=datetime.now(timezone.utc))
        stored = db.get(NotificationOutbox, job.id)
        assert stored.status == NotificationStatus.SENT and stored.provider_message_id == "resend-job-id"
    assert len(calls) == 1


def test_provider_selection_keeps_log_default_available(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "log")
    assert isinstance(email_provider(), LogEmailProvider)
    monkeypatch.setattr(settings, "email_provider", "sendgrid")
    assert isinstance(email_provider(), SendGridEmailProvider)
