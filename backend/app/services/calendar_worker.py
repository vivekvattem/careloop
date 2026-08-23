import socket
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.calendar import (
    AppointmentCalendarMapping,
    CalendarConnectionStatus,
    CalendarOperation,
    CalendarSyncJob,
    CalendarSyncStatus,
    GoogleCalendarConnection,
)
from app.services.calendar import GoogleProvider, GoogleProviderError


def claim_calendar_jobs(db, worker_id: str, *, now=None, limit: int = 20):
    now = now or datetime.now(timezone.utc)
    stale = now - timedelta(seconds=settings.notification_stale_claim_seconds)
    db.query(CalendarSyncJob).filter(
        CalendarSyncJob.status == CalendarSyncStatus.PROCESSING,
        CalendarSyncJob.claimed_at < stale,
    ).update({"status": CalendarSyncStatus.RETRY_SCHEDULED, "claimed_at": None, "claimed_by": None, "next_attempt_at": now}, synchronize_session=False)
    jobs = list(db.scalars(select(CalendarSyncJob).where(
        CalendarSyncJob.status.in_([CalendarSyncStatus.PENDING, CalendarSyncStatus.RETRY_SCHEDULED]),
        CalendarSyncJob.next_attempt_at <= now,
    ).order_by(CalendarSyncJob.next_attempt_at).limit(limit).with_for_update(skip_locked=True)))
    for job in jobs:
        job.status = CalendarSyncStatus.PROCESSING; job.claimed_at = now; job.claimed_by = worker_id
    db.commit()
    return jobs


def _payload(appointment):
    return {
        "summary": "CareLoop appointment",
        "start": appointment.slot_start.isoformat(),
        "end": appointment.slot_end.isoformat(),
        "timezone": "Asia/Kolkata",
        "consultation_mode": "appointment",
        "careloop_appointment_reference": str(appointment.id),
    }


def process_calendar_job(job_id, provider=None, *, now=None, session_factory=SessionLocal):
    now = now or datetime.now(timezone.utc)
    with session_factory() as db:
        job = db.get(CalendarSyncJob, job_id)
        if not job or job.status != CalendarSyncStatus.PROCESSING:
            return "ignored"
        appointment = db.get(Appointment, job.appointment_id)
        connection = db.scalar(select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.user_id == job.user_id,
            GoogleCalendarConnection.status == CalendarConnectionStatus.CONNECTED,
        ))
        mapping = db.scalar(select(AppointmentCalendarMapping).where(
            AppointmentCalendarMapping.appointment_id == job.appointment_id,
            AppointmentCalendarMapping.user_id == job.user_id,
            AppointmentCalendarMapping.calendar_id == (connection.calendar_id if connection else "primary"),
        ))
    if not appointment or not connection:
        with session_factory() as db:
            job = db.get(CalendarSyncJob, job_id); job.status = CalendarSyncStatus.CANCELLED; db.commit()
        return "failed"
    try:
        provider = provider or GoogleProvider()
        expiry = connection.token_expiry
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry and expiry <= now:
            with session_factory() as db:
                fresh = db.get(GoogleCalendarConnection, connection.id); provider.refresh(db, fresh)
            with session_factory() as db: connection = db.get(GoogleCalendarConnection, connection.id)
        payload = _payload(appointment)
        if job.operation == CalendarOperation.CREATE and mapping and mapping.google_event_id:
            result = {"event_id": mapping.google_event_id, "calendar_id": mapping.calendar_id}
        elif job.operation == CalendarOperation.CREATE:
            result = provider.create_event(connection, payload)
        elif job.operation == CalendarOperation.UPDATE and mapping and mapping.google_event_id:
            result = provider.update_event(connection, mapping.google_event_id, payload)
        elif job.operation == CalendarOperation.DELETE and mapping is None:
            result = {"deleted": True}
        elif job.operation == CalendarOperation.DELETE:
            result = provider.delete_event(connection, mapping.google_event_id if mapping else None)
        else:
            result = provider.create_event(connection, payload)
        with session_factory() as db:
            job = db.get(CalendarSyncJob, job_id)
            if job.operation != CalendarOperation.DELETE:
                mapping = db.scalar(select(AppointmentCalendarMapping).where(AppointmentCalendarMapping.appointment_id == job.appointment_id, AppointmentCalendarMapping.user_id == job.user_id, AppointmentCalendarMapping.calendar_id == result.get("calendar_id", connection.calendar_id)))
                if not mapping:
                    mapping = AppointmentCalendarMapping(appointment_id=job.appointment_id, user_id=job.user_id, connection_id=connection.id, calendar_id=result.get("calendar_id", connection.calendar_id)); db.add(mapping)
                mapping.google_event_id=result.get("event_id"); mapping.sync_status="sent"; mapping.last_synced_version=appointment.updated_at; mapping.last_synced_at=now
            elif mapping: db.delete(mapping)
            job.status=CalendarSyncStatus.SENT; db.commit()
        return job.operation.value
    except GoogleProviderError as exc:
        with session_factory() as db:
            job=db.get(CalendarSyncJob,job_id); job.attempt_count += 1; job.failure_category=exc.category; job.failure_message="Calendar provider request failed"
            if exc.category == "reauthorization_required":
                connection=db.get(GoogleCalendarConnection,connection.id); connection.status=CalendarConnectionStatus.REAUTHORIZATION_REQUIRED; job.status=CalendarSyncStatus.PERMANENTLY_FAILED
            elif exc.retryable and job.attempt_count < settings.notification_max_attempts:
                job.status=CalendarSyncStatus.RETRY_SCHEDULED; job.next_attempt_at=now+timedelta(seconds=settings.notification_base_retry_seconds * 2 ** (job.attempt_count-1))
            else: job.status=CalendarSyncStatus.PERMANENTLY_FAILED
            db.commit()
        return "retried" if exc.retryable else "failed"


def run_once(worker_id=None, session_factory=SessionLocal, provider=None):
    worker_id = worker_id or f"calendar-{socket.gethostname()}-{id(object())}"
    try:
        with session_factory() as db: jobs=claim_calendar_jobs(db,worker_id)
    except SQLAlchemyError:
        # Development databases may not yet have the opt-in Phase 6 migration.
        return {"claimed":0,"created":0,"updated":0,"deleted":0,"retried":0,"failed":0}
    counts={"claimed":len(jobs),"created":0,"updated":0,"deleted":0,"retried":0,"failed":0}
    for job in jobs:
        result=process_calendar_job(job.id, provider=provider, session_factory=session_factory)
        if result in counts: counts[result]+=1
    return counts
