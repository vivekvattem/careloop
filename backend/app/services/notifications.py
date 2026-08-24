from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib
import smtplib
from email.message import EmailMessage
import httpx

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notification import MedicationReminderSchedule, NotificationEventType, NotificationOutbox, NotificationStatus
from app.models.visit import PrescriptionItem
from app.models.user import User


class EmailDeliveryError(Exception):
    def __init__(self, category: str, message: str, retryable: bool): self.category, self.message, self.retryable = category, message, retryable


class LogEmailProvider:
    name = "log"
    def send(self, *, to: str, subject: str, text: str, idempotency_key: str | None = None) -> str:
        return "log-delivered"


class SendGridEmailProvider:
    name = "sendgrid"
    def send(self, *, to: str, subject: str, text: str, idempotency_key: str | None = None) -> str:
        if not settings.sendgrid_api_key: raise EmailDeliveryError("missing_configuration", "Email provider is not configured", False)
        try:
            response = httpx.post("https://api.sendgrid.com/v3/mail/send", headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"}, json={"personalizations": [{"to": [{"email": to}]}], "from": {"email": settings.email_from_address}, "subject": subject, "content": [{"type": "text/plain", "value": text}]}, timeout=8)
        except (httpx.TimeoutException, httpx.ConnectError) as exc: raise EmailDeliveryError("connection", "Email delivery temporarily unavailable", True) from exc
        if response.status_code in {429} or response.status_code >= 500: raise EmailDeliveryError("provider_unavailable", "Email delivery temporarily unavailable", True)
        if response.status_code >= 400: raise EmailDeliveryError("provider_rejected", "Email provider rejected the message", False)
        return response.headers.get("X-Message-Id", "sendgrid-accepted")


class ResendEmailProvider:
    name = "resend"

    def __init__(self, *, transport: httpx.BaseTransport | None = None, timeout: float | None = None):
        self.transport = transport
        self.timeout = timeout if timeout is not None else settings.email_timeout_seconds

    def send(self, *, to: str, subject: str, text: str, idempotency_key: str | None = None) -> str:
        if not settings.resend_api_key:
            raise EmailDeliveryError("missing_configuration", "Email provider is not configured", False)
        headers = {
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
                response = client.post(
                    f"{settings.resend_base_url.rstrip('/')}/emails",
                    headers=headers,
                    json={"from": settings.email_from_address, "to": to, "subject": subject, "text": text},
                )
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise EmailDeliveryError("connection", "Email delivery temporarily unavailable", True) from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise EmailDeliveryError("provider_unavailable", "Email delivery temporarily unavailable", True)
        if response.status_code in {401, 403}:
            raise EmailDeliveryError("authentication", "Email provider authentication failed", False)
        if response.status_code == 400:
            raise EmailDeliveryError("provider_rejected", "Email provider rejected the message", False)
        if response.status_code >= 400:
            raise EmailDeliveryError("provider_rejected", "Email provider rejected the message", False)
        try:
            return response.json().get("id", "resend-accepted")
        except ValueError:
            return "resend-accepted"


class SMTPEmailProvider:
    name = "smtp"

    def __init__(self, *, smtp_factory=None, timeout: float | None = None):
        self.smtp_factory = smtp_factory or smtplib.SMTP
        self.timeout = timeout if timeout is not None else settings.email_timeout_seconds

    def send(self, *, to: str, subject: str, text: str, idempotency_key: str | None = None) -> str:
        if bool(settings.smtp_username) != bool(settings.smtp_password):
            raise EmailDeliveryError("invalid_configuration", "SMTP credentials are incomplete", False)
        message = EmailMessage()
        message["From"] = settings.email_from_address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        try:
            with self.smtp_factory(settings.smtp_host, settings.smtp_port, timeout=self.timeout) as client:
                if settings.smtp_use_starttls:
                    client.starttls()
                if settings.smtp_username and settings.smtp_password:
                    client.login(settings.smtp_username, settings.smtp_password)
                refused = client.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailDeliveryError("authentication", "SMTP authentication failed", False) from exc
        except UnicodeError as exc:
            # smtplib may raise UnicodeEncodeError before a server response when credentials are malformed.
            raise EmailDeliveryError("authentication", "SMTP credentials are invalid", False) from exc
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
            raise EmailDeliveryError("invalid_address", "SMTP rejected the sender or recipient", False) from exc
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                raise EmailDeliveryError("provider_unavailable", "SMTP delivery temporarily unavailable", True) from exc
            raise EmailDeliveryError("provider_rejected", "SMTP rejected the message", False) from exc
        except (TimeoutError, OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("connection", "SMTP delivery temporarily unavailable", True) from exc
        if refused:
            raise EmailDeliveryError("invalid_address", "SMTP rejected the sender or recipient", False)
        digest = hashlib.sha256((idempotency_key or f"{to}:{subject}:{text}").encode()).hexdigest()[:20]
        return f"smtp-{digest}"


def email_provider():
    if settings.email_provider == "sendgrid": return SendGridEmailProvider()
    if settings.email_provider == "resend": return ResendEmailProvider()
    if settings.email_provider == "smtp": return SMTPEmailProvider()
    return LogEmailProvider()


def enqueue(db: Session, *, event_type: NotificationEventType, recipient, idempotency_key: str, payload: dict, appointment_id=None, prescription_item_id=None, now: datetime | None = None) -> NotificationOutbox:
    current = now or datetime.now(timezone.utc)
    db.flush()
    existing = db.scalar(select(NotificationOutbox).where(NotificationOutbox.idempotency_key == idempotency_key))
    if existing: return existing
    job = NotificationOutbox(event_type=event_type, recipient_user_id=recipient.id, recipient_email=recipient.email, appointment_id=appointment_id, prescription_item_id=prescription_item_id, idempotency_key=idempotency_key, payload=payload, status=NotificationStatus.PENDING, attempt_count=0, maximum_attempts=settings.notification_max_attempts, next_attempt_at=current, provider=settings.email_provider)
    db.add(job); return job


def appointment_payload(appointment, *, message: str) -> dict:
    """Snapshot only patient-safe scheduling data so later delivery never reads clinical records."""
    profile = appointment.doctor_profile
    zone_name = profile.timezone or "Asia/Kolkata"
    def timestamp(value: datetime) -> str:
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).isoformat()
    return {
        "message": message,
        "patient_name": appointment.patient.full_name,
        "doctor_name": profile.user.full_name,
        "doctor_specialisation": profile.specialisation,
        "slot_start": timestamp(appointment.slot_start),
        "slot_end": timestamp(appointment.slot_end),
        "timezone": zone_name,
        "consultation_mode": profile.consultation_mode,
    }


def _next_due(item: PrescriptionItem, reminder: time, tz_name: str, now: datetime) -> datetime | None:
    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    candidate = datetime.combine(max(item.start_date, local_now.date()), reminder, tzinfo=tz)
    if candidate <= local_now: candidate += timedelta(days=1)
    if item.end_date and candidate.date() > item.end_date: return None
    return candidate.astimezone(timezone.utc)


def reconcile_medication_schedules(db: Session, item: PrescriptionItem, patient_id, *, timezone_name: str = "Asia/Kolkata", now: datetime | None = None) -> None:
    current = now or datetime.now(timezone.utc)
    wanted = set(item.reminder_times) if item.is_active else set()
    schedules = db.scalars(select(MedicationReminderSchedule).where(MedicationReminderSchedule.prescription_item_id == item.id)).all()
    for schedule in schedules:
        if schedule.reminder_time.isoformat(timespec="minutes") not in wanted:
            schedule.is_active = False; schedule.cancelled_at = current; schedule.next_due_at = None
    have = {schedule.reminder_time.isoformat(timespec="minutes") for schedule in schedules}
    for value in wanted - have:
        reminder = time.fromisoformat(value)
        due = _next_due(item, reminder, timezone_name, current)
        db.add(MedicationReminderSchedule(prescription_item_id=item.id, patient_user_id=patient_id, reminder_time=reminder, timezone=timezone_name, next_due_at=due, is_active=due is not None))


def claim_due(db: Session, worker_id: str, *, now: datetime | None = None, limit: int = 20) -> list[NotificationOutbox]:
    current = now or datetime.now(timezone.utc)
    stale = current - timedelta(seconds=settings.notification_stale_claim_seconds)
    db.query(NotificationOutbox).filter(NotificationOutbox.status == NotificationStatus.PROCESSING, NotificationOutbox.claimed_at < stale).update({"status": NotificationStatus.RETRY_SCHEDULED, "next_attempt_at": current, "claimed_at": None, "claimed_by": None}, synchronize_session=False)
    stmt = select(NotificationOutbox).where(NotificationOutbox.status.in_([NotificationStatus.PENDING, NotificationStatus.RETRY_SCHEDULED]), NotificationOutbox.next_attempt_at <= current).order_by(NotificationOutbox.next_attempt_at).limit(limit).with_for_update(skip_locked=True)
    jobs = list(db.scalars(stmt))
    for job in jobs: job.status = NotificationStatus.PROCESSING; job.claimed_at = current; job.claimed_by = worker_id
    db.commit(); return jobs


def enqueue_due_reminders(db: Session, *, now: datetime | None = None) -> int:
    current = now or datetime.now(timezone.utc)
    schedules = db.scalars(select(MedicationReminderSchedule).where(MedicationReminderSchedule.is_active.is_(True), MedicationReminderSchedule.next_due_at <= current).with_for_update()).all()
    count = 0
    for schedule in schedules:
        item = db.get(PrescriptionItem, schedule.prescription_item_id); patient = db.get(User, schedule.patient_user_id)
        if not item or not patient or not item.is_active or (item.end_date and current.astimezone(ZoneInfo(schedule.timezone)).date() > item.end_date):
            schedule.is_active = False; schedule.cancelled_at = current; schedule.next_due_at = None; continue
        due_key = schedule.next_due_at.isoformat()
        enqueue(db, event_type=NotificationEventType.MEDICATION_REMINDER_DUE, recipient=patient, appointment_id=None, prescription_item_id=item.id, idempotency_key=f"medication-reminder:{schedule.id}:{due_key}", payload={"medication_name": item.medication_name, "dosage": item.dosage, "route": item.route, "reminder_time": schedule.reminder_time.isoformat(timespec="minutes"), "food_instructions": item.food_instructions, "additional_instructions": item.additional_instructions}, now=current)
        schedule.next_due_at = _next_due(item, schedule.reminder_time, schedule.timezone, current + timedelta(seconds=1)); schedule.is_active = schedule.next_due_at is not None; count += 1
    db.commit(); return count


def deliver_job(db: Session, job_id, provider=None, *, now: datetime | None = None) -> None:
    current = now or datetime.now(timezone.utc); job = db.get(NotificationOutbox, job_id)
    if not job or job.status != NotificationStatus.PROCESSING: return
    try:
        message_id = (provider or email_provider()).send(to=job.recipient_email, subject=_subject(job), text=_template(job), idempotency_key=job.idempotency_key)
        job.status = NotificationStatus.SENT; job.provider_message_id = message_id; job.sent_at = current; job.failure_category = job.failure_message = None
    except EmailDeliveryError as exc:
        job.attempt_count += 1; job.failure_category = exc.category; job.failure_message = exc.message[:255]
        if not exc.retryable or job.attempt_count >= job.maximum_attempts: job.status = NotificationStatus.PERMANENTLY_FAILED
        else: job.status = NotificationStatus.RETRY_SCHEDULED; job.next_attempt_at = current + timedelta(seconds=settings.notification_base_retry_seconds * 2 ** (job.attempt_count - 1))
    finally: db.commit()


def _subject(job: NotificationOutbox) -> str:
    data = job.payload
    if job.event_type == NotificationEventType.PASSWORD_RESET:
        return "Reset your CareLoop password"
    doctor = data.get("doctor_name")
    if not doctor:
        return job.event_type.value.replace("_", " ").title()
    if job.event_type == NotificationEventType.APPOINTMENT_CONFIRMED:
        return f"CareLoop appointment confirmed — Dr. {doctor}"
    if job.event_type == NotificationEventType.APPOINTMENT_CANCELLED:
        return f"CareLoop appointment cancelled — Dr. {doctor}"
    if job.event_type == NotificationEventType.APPOINTMENT_RESCHEDULED:
        return f"CareLoop appointment rescheduled — Dr. {doctor}"
    return job.event_type.value.replace("_", " ").title()


def _template(job: NotificationOutbox) -> str:
    data = job.payload
    if job.event_type == NotificationEventType.PASSWORD_RESET:
        token = data.get("reset_token")
        if not token:
            return "CareLoop password-reset instructions are unavailable. Please request a new link."
        return "\n".join([
            f"Hello {str(data.get('recipient_name') or 'there').split()[0]},", "",
            "We received a request to reset your CareLoop password.", "",
            "Reset your password:",
            f"{settings.frontend_origin.rstrip('/')}/reset-password?token={token}", "",
            f"This link expires in {data.get('expires_minutes', settings.password_reset_minutes)} minutes and can only be used once.", "",
            "If you did not request this reset, you can safely ignore this email. Do not share this link with anyone.", "", "— CareLoop",
        ])
    if job.event_type == NotificationEventType.MEDICATION_REMINDER_DUE:
        return f"Hello, reminder: {data['medication_name']} {data['dosage']}. {data.get('route') or ''} {data.get('food_instructions') or ''} {data.get('additional_instructions') or ''} Follow your clinician's prescription."
    if job.event_type in {
        NotificationEventType.APPOINTMENT_CONFIRMED,
        NotificationEventType.APPOINTMENT_CANCELLED,
        NotificationEventType.APPOINTMENT_RESCHEDULED,
    }:
        rendered = _appointment_template(job.event_type, data)
        if rendered:
            return rendered
    return data.get("message", "You have a CareLoop appointment update.")


def _appointment_template(event_type: NotificationEventType, data: dict) -> str | None:
    required = ("patient_name", "doctor_name", "slot_start", "slot_end", "timezone")
    if any(not data.get(field) for field in required):
        return None
    try:
        zone = ZoneInfo(data["timezone"])
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Kolkata")
    try:
        start = datetime.fromisoformat(data["slot_start"])
        end = datetime.fromisoformat(data["slot_end"])
    except (TypeError, ValueError):
        return None
    if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
    start, end = start.astimezone(zone), end.astimezone(zone)
    date_label = f"{start.day} {start.strftime('%B %Y')}"
    time_label = f"{start.strftime('%I:%M %p').lstrip('0')} – {end.strftime('%I:%M %p').lstrip('0')}"
    if event_type == NotificationEventType.APPOINTMENT_CONFIRMED:
        event_message = "Your CareLoop appointment has been confirmed."
    elif event_type == NotificationEventType.APPOINTMENT_CANCELLED:
        event_message = "Your CareLoop appointment has been cancelled."
    else:
        event_message = "Your CareLoop appointment has been rescheduled. Your new appointment details are below."
    lines = [
        f"Hello, {data['patient_name'].split()[0] or data['patient_name']}", "", event_message, "",
        f"Doctor: Dr. {data['doctor_name']}",
    ]
    if data.get("doctor_specialisation"):
        lines.append(f"Specialisation: {data['doctor_specialisation']}")
    lines.extend([f"Date: {date_label}", f"Time: {time_label}", f"Timezone: {data['timezone']}"])
    if data.get("consultation_mode"):
        mode = {"video": "Online", "in_person": "In person", "hybrid": "Hybrid"}.get(data["consultation_mode"], data["consultation_mode"])
        lines.append(f"Consultation mode: {mode}")
    lines.extend(["", "You can manage this appointment from your CareLoop patient dashboard.", "", "If you did not make this booking, please contact the clinic.", "", "— CareLoop"])
    return "\n".join(lines)
