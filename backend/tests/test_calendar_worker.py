from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
import pytest
from cryptography.fernet import Fernet

from app.models.appointment import Appointment, AppointmentStatus
from app.models.user import User, UserRole
from app.models.doctor import DoctorProfile
from app.models.calendar import (
    AppointmentCalendarMapping, CalendarConnectionStatus, CalendarOperation,
    CalendarSyncJob, CalendarSyncStatus, GoogleCalendarConnection,
)
from app.services.calendar import encrypt
from app.services.calendar import GoogleProviderError, decrypt
from app.core.config import settings
from app.services import calendar_worker
from tests.conftest import TestingSessionLocal
from tests.test_postgres_concurrency import pg_sessions


class FakeProvider:
    def __init__(self): self.created = []; self.updated = []; self.deleted = []
    def create_event(self, connection, payload): self.created.append(payload); return {"event_id": "google-event-1", "calendar_id": connection.calendar_id}
    def update_event(self, connection, event_id, payload): self.updated.append((event_id, payload)); return {"event_id": event_id, "calendar_id": connection.calendar_id}
    def delete_event(self, connection, event_id): self.deleted.append(event_id); return {"deleted": True}


class FailingProvider(FakeProvider):
    def __init__(self, error): super().__init__(); self.error = error
    def create_event(self, connection, payload): raise self.error


class RefreshingProvider(FakeProvider):
    def refresh(self, db, connection):
        connection.access_token_encrypted = encrypt("refreshed-access")
        connection.token_expiry = datetime(2030, 1, 1, tzinfo=timezone.utc)
        db.commit()
        return "refreshed-access"


@pytest.fixture(autouse=True)
def temporary_google_key(monkeypatch):
    monkeypatch.setattr(settings, "google_token_encryption_key", Fernet.generate_key().decode())


def setup_job(operation=CalendarOperation.CREATE, mapping=False):
    now = datetime(2026, 8, 24, 8, tzinfo=timezone.utc)
    with TestingSessionLocal() as db:
        user_id, doctor_id, appointment_id = uuid4(), uuid4(), uuid4()
        appointment = Appointment(id=appointment_id, patient_user_id=user_id, doctor_profile_id=doctor_id, slot_start=now, slot_end=now + timedelta(minutes=30), status=AppointmentStatus.CONFIRMED)
        connection = GoogleCalendarConnection(user_id=user_id, access_token_encrypted=encrypt("access"), refresh_token_encrypted=encrypt("refresh"), scopes="calendar.events", calendar_id="primary", status=CalendarConnectionStatus.CONNECTED)
        db.add_all([appointment, connection]); db.flush()
        existing = None
        if mapping:
            existing = AppointmentCalendarMapping(appointment_id=appointment_id, user_id=user_id, connection_id=connection.id, calendar_id="primary", google_event_id="existing-event", sync_status="sent")
            db.add(existing)
        job = CalendarSyncJob(appointment_id=appointment_id, user_id=user_id, operation=operation, idempotency_key=str(uuid4()), status=CalendarSyncStatus.PENDING, attempt_count=0, next_attempt_at=now)
        db.add(job); db.commit(); return job.id, appointment_id, now


def test_create_persists_mapping_and_is_idempotent():
    job_id, appointment_id, now = setup_job(); fake = FakeProvider()
    assert calendar_worker.claim_calendar_jobs(TestingSessionLocal(), "worker", now=now)
    assert calendar_worker.process_calendar_job(job_id, fake, now=now, session_factory=TestingSessionLocal) == "create"
    with TestingSessionLocal() as db:
        job=db.get(CalendarSyncJob,job_id); mapping=db.scalar(select(AppointmentCalendarMapping).where(AppointmentCalendarMapping.appointment_id==appointment_id))
        assert job.status == CalendarSyncStatus.SENT and mapping.google_event_id == "google-event-1"
    assert len(fake.created)==1


def test_update_and_delete_use_mapping():
    job_id, appointment_id, now = setup_job(CalendarOperation.UPDATE, mapping=True); fake=FakeProvider()
    with TestingSessionLocal() as db: calendar_worker.claim_calendar_jobs(db,"worker",now=now)
    assert calendar_worker.process_calendar_job(job_id,fake,now=now,session_factory=TestingSessionLocal)=="update"; assert fake.updated[0][0]=="existing-event"
    with TestingSessionLocal() as db:
        job=db.get(CalendarSyncJob,job_id); job.operation=CalendarOperation.DELETE; job.status=CalendarSyncStatus.PROCESSING; db.commit()
    assert calendar_worker.process_calendar_job(job_id,fake,now=now,session_factory=TestingSessionLocal)=="delete"; assert fake.deleted==["existing-event"]


def test_stale_and_not_due_claims():
    job_id, _, now=setup_job();
    with TestingSessionLocal() as db:
        job=db.get(CalendarSyncJob,job_id); job.status=CalendarSyncStatus.PROCESSING; job.claimed_at=now-timedelta(hours=1); db.commit()
        assert calendar_worker.claim_calendar_jobs(db,"worker",now=now)
        job.status=CalendarSyncStatus.PENDING; job.next_attempt_at=now+timedelta(hours=1); db.commit(); assert not calendar_worker.claim_calendar_jobs(db,"worker",now=now)


def test_retryable_failure_schedules_exponential_retry_and_preserves_appointment():
    job_id, appointment_id, now = setup_job()
    with TestingSessionLocal() as db: calendar_worker.claim_calendar_jobs(db, "worker", now=now)
    result = calendar_worker.process_calendar_job(job_id, FailingProvider(GoogleProviderError("provider_unavailable", True)), now=now, session_factory=TestingSessionLocal)
    assert result == "retried"
    with TestingSessionLocal() as db:
        job=db.get(CalendarSyncJob, job_id); appointment=db.get(Appointment, appointment_id)
        assert job.status == CalendarSyncStatus.RETRY_SCHEDULED and job.attempt_count == 1
        assert job.next_attempt_at.replace(tzinfo=timezone.utc) == now + timedelta(seconds=60)
        assert appointment.status == AppointmentStatus.CONFIRMED


def test_maximum_attempt_is_permanently_failed_and_not_claimed_again(monkeypatch):
    job_id, _, now = setup_job()
    monkeypatch.setattr(calendar_worker.settings, "notification_max_attempts", 1)
    with TestingSessionLocal() as db:
        calendar_worker.claim_calendar_jobs(db, "worker", now=now)
    assert calendar_worker.process_calendar_job(job_id, FailingProvider(GoogleProviderError("provider_unavailable", True)), now=now, session_factory=TestingSessionLocal) == "retried"
    with TestingSessionLocal() as db:
        job=db.get(CalendarSyncJob, job_id); assert job.status == CalendarSyncStatus.PERMANENTLY_FAILED; assert not calendar_worker.claim_calendar_jobs(db, "worker-2", now=now)


def test_revoked_consent_marks_connection_without_secret_failure_data():
    job_id, _, now = setup_job()
    with TestingSessionLocal() as db: calendar_worker.claim_calendar_jobs(db, "worker", now=now)
    calendar_worker.process_calendar_job(job_id, FailingProvider(GoogleProviderError("reauthorization_required")), now=now, session_factory=TestingSessionLocal)
    with TestingSessionLocal() as db:
        job=db.get(CalendarSyncJob, job_id); connection=db.scalar(select(GoogleCalendarConnection).where(GoogleCalendarConnection.user_id==job.user_id))
        assert connection.status == CalendarConnectionStatus.REAUTHORIZATION_REQUIRED and job.status == CalendarSyncStatus.PERMANENTLY_FAILED
        assert "access" not in (job.failure_message or "").lower() and "refresh" not in (job.failure_message or "").lower()


def test_expired_token_refreshes_before_create_and_persists():
    job_id, _, now = setup_job(); fake=RefreshingProvider()
    with TestingSessionLocal() as db:
        job=db.get(CalendarSyncJob, job_id); connection=db.scalar(select(GoogleCalendarConnection).where(GoogleCalendarConnection.user_id==job.user_id)); connection.token_expiry=now-timedelta(minutes=1); db.commit(); calendar_worker.claim_calendar_jobs(db, "worker", now=now)
    assert calendar_worker.process_calendar_job(job_id, fake, now=now, session_factory=TestingSessionLocal) == "create"
    with TestingSessionLocal() as db:
        job=db.get(CalendarSyncJob,job_id); connection=db.scalar(select(GoogleCalendarConnection).where(GoogleCalendarConnection.user_id==job.user_id)); assert job.status == CalendarSyncStatus.SENT and decrypt(connection.access_token_encrypted) == "refreshed-access"


def test_update_without_mapping_falls_back_to_one_create_mapping():
    job_id, appointment_id, now=setup_job(CalendarOperation.UPDATE); fake=FakeProvider()
    with TestingSessionLocal() as db: calendar_worker.claim_calendar_jobs(db,"worker",now=now)
    assert calendar_worker.process_calendar_job(job_id,fake,now=now,session_factory=TestingSessionLocal)=="update"
    with TestingSessionLocal() as db: assert len(db.scalars(select(AppointmentCalendarMapping).where(AppointmentCalendarMapping.appointment_id==appointment_id)).all()) == 1
    assert len(fake.created)==1


def test_delete_without_mapping_is_idempotent():
    job_id, _, now=setup_job(CalendarOperation.DELETE); fake=FakeProvider()
    with TestingSessionLocal() as db: calendar_worker.claim_calendar_jobs(db,"worker",now=now)
    assert calendar_worker.process_calendar_job(job_id,fake,now=now,session_factory=TestingSessionLocal)=="delete"; assert fake.deleted == []


class _WorkerSession:
    def __enter__(self): return self
    def __exit__(self, *args): return False


def test_run_once_empty_batch_keeps_all_counts_zero(monkeypatch):
    monkeypatch.setattr(calendar_worker, "claim_calendar_jobs", lambda db, worker_id: [])
    counts = calendar_worker.run_once(session_factory=_WorkerSession)
    assert counts == {"claimed": 0, "created": 0, "updated": 0, "deleted": 0, "retried": 0, "failed": 0}


def test_run_once_counts_successful_create_update_delete(monkeypatch):
    jobs = [type("Job", (), {"id": "create"})(), type("Job", (), {"id": "update"})(), type("Job", (), {"id": "delete"})()]
    monkeypatch.setattr(calendar_worker, "claim_calendar_jobs", lambda db, worker_id: jobs)
    monkeypatch.setattr(calendar_worker, "process_calendar_job", lambda job_id, **kwargs: job_id)
    assert calendar_worker.run_once(session_factory=_WorkerSession) == {"claimed": 3, "created": 1, "updated": 1, "deleted": 1, "retried": 0, "failed": 0}


def test_run_once_counts_mixed_success_retry_and_failure(monkeypatch):
    results = iter(["create", "delete", "retried", "failed"])
    jobs = [type("Job", (), {"id": str(index)})() for index in range(4)]
    monkeypatch.setattr(calendar_worker, "claim_calendar_jobs", lambda db, worker_id: jobs)
    monkeypatch.setattr(calendar_worker, "process_calendar_job", lambda job_id, **kwargs: next(results))
    assert calendar_worker.run_once(session_factory=_WorkerSession) == {"claimed": 4, "created": 1, "updated": 0, "deleted": 1, "retried": 1, "failed": 1}


@pytest.mark.postgresql
def test_postgresql_competing_claims_process_once(pg_sessions):
    now=datetime(2026,8,24,8,tzinfo=timezone.utc); factory=pg_sessions
    with factory() as db:
        patient=User(full_name="PG Patient",email=f"pg-{uuid4()}@example.com",password_hash="x",role=UserRole.PATIENT); doctor=User(full_name="PG Doctor",email=f"pgd-{uuid4()}@example.com",password_hash="x",role=UserRole.DOCTOR); db.add_all([patient,doctor]); db.flush(); profile=DoctorProfile(user_id=doctor.id,specialisation="General Medicine"); db.add(profile); db.flush(); appointment=Appointment(patient_user_id=patient.id,doctor_profile_id=profile.id,slot_start=now,slot_end=now+timedelta(minutes=30),status=AppointmentStatus.CONFIRMED); db.add(appointment); db.flush(); connection=GoogleCalendarConnection(user_id=patient.id,access_token_encrypted=encrypt("access"),refresh_token_encrypted=encrypt("refresh"),scopes="calendar.events",calendar_id="primary",status=CalendarConnectionStatus.CONNECTED); db.add(connection); db.flush(); job=CalendarSyncJob(appointment_id=appointment.id,user_id=patient.id,operation=CalendarOperation.CREATE,idempotency_key=str(uuid4()),status=CalendarSyncStatus.PENDING,attempt_count=0,next_attempt_at=now); db.add(job);db.commit();job_id=job.id
    with factory() as first, factory() as second:
        claimed_one=calendar_worker.claim_calendar_jobs(first,"one",now=now); claimed_two=calendar_worker.claim_calendar_jobs(second,"two",now=now)
    assert len(claimed_one)==1 and claimed_two==[]
