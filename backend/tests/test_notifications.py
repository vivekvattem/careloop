from datetime import date, datetime, time, timezone
from uuid import UUID

from sqlalchemy import select

from app.models.notification import MedicationReminderSchedule, NotificationEventType, NotificationOutbox, NotificationStatus
from app.models.user import User, UserRole
from app.models.visit import PrescriptionItem
from app.services.notifications import EmailDeliveryError, claim_due, deliver_job, enqueue, reconcile_medication_schedules
from tests.conftest import TestingSessionLocal


class FakeEmail:
    def __init__(self, error=None): self.error = error
    def send(self, **_):
        if self.error: raise self.error
        return "fake-message"


def test_outbox_is_idempotent_and_successfully_delivered() -> None:
    with TestingSessionLocal() as db:
        user = User(full_name="Notification Patient", email="notify@example.com", password_hash="x", role=UserRole.PATIENT); db.add(user); db.flush()
        first = enqueue(db, event_type=NotificationEventType.APPOINTMENT_CONFIRMED, recipient=user, idempotency_key="same", payload={"message": "confirmed"})
        second = enqueue(db, event_type=NotificationEventType.APPOINTMENT_CONFIRMED, recipient=user, idempotency_key="same", payload={"message": "confirmed"})
        db.commit(); assert first.id == second.id
        jobs = claim_due(db, "worker", now=datetime.now(timezone.utc)); assert len(jobs) == 1
        deliver_job(db, jobs[0].id, FakeEmail(), now=datetime.now(timezone.utc))
        assert db.get(NotificationOutbox, jobs[0].id).status == NotificationStatus.SENT


def test_retry_backoff_and_permanent_failure() -> None:
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    with TestingSessionLocal() as db:
        user = User(full_name="Retry Patient", email="retry@example.com", password_hash="x", role=UserRole.PATIENT); db.add(user); db.flush()
        job = enqueue(db, event_type=NotificationEventType.APPOINTMENT_CONFIRMED, recipient=user, idempotency_key="retry", payload={"message": "x"}, now=now); db.commit()
        claim_due(db, "worker", now=now); deliver_job(db, job.id, FakeEmail(EmailDeliveryError("timeout", "timeout", True)), now=now)
        job = db.get(NotificationOutbox, job.id); assert job.status == NotificationStatus.RETRY_SCHEDULED and job.next_attempt_at > now
        job.status = NotificationStatus.PROCESSING; deliver_job(db, job.id, FakeEmail(EmailDeliveryError("authentication", "denied", False)), now=now)
        assert db.get(NotificationOutbox, job.id).status == NotificationStatus.PERMANENTLY_FAILED


def test_medication_schedule_has_one_row_per_time_and_cancels_inactive() -> None:
    with TestingSessionLocal() as db:
        patient = User(full_name="Schedule Patient", email="schedule@example.com", password_hash="x", role=UserRole.PATIENT); db.add(patient); db.flush()
        item = PrescriptionItem(prescription_id=UUID("00000000-0000-0000-0000-000000000001"), medication_name="Example", dosage="1 mg", frequency_per_day=2, reminder_times=["09:00", "21:00"], start_date=date(2026, 8, 24), is_active=True); db.add(item); db.flush()
        reconcile_medication_schedules(db, item, patient.id, now=datetime(2026, 8, 24, 8, tzinfo=timezone.utc)); db.commit()
        assert len(db.execute(select(MedicationReminderSchedule)).scalars().all()) == 2
        item.is_active = False; reconcile_medication_schedules(db, item, patient.id); db.commit()
        assert not any(s.is_active for s in db.execute(select(MedicationReminderSchedule)).scalars())
