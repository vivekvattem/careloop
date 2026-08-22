from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_roles
from app.db.session import get_db
from app.models.notification import MedicationReminderSchedule, NotificationOutbox, NotificationStatus
from app.models.user import User, UserRole

patient_router = APIRouter(prefix="/notifications", tags=["notifications"])
admin_router = APIRouter(prefix="/admin/notifications", tags=["notifications"])


@patient_router.get("/me")
def my_notifications(patient: User = Depends(require_roles(UserRole.PATIENT)), db: Session = Depends(get_db)) -> dict:
    schedules = db.scalars(select(MedicationReminderSchedule).where(MedicationReminderSchedule.patient_user_id == patient.id).order_by(MedicationReminderSchedule.next_due_at)).all()
    jobs = db.scalars(select(NotificationOutbox).where(NotificationOutbox.recipient_user_id == patient.id).order_by(NotificationOutbox.created_at.desc()).limit(50)).all()
    return {"schedules": [{"id": str(s.id), "prescription_item_id": str(s.prescription_item_id), "reminder_time": s.reminder_time.isoformat(timespec="minutes"), "timezone": s.timezone, "next_due_at": s.next_due_at, "is_active": s.is_active} for s in schedules], "notifications": [{"id": str(j.id), "event_type": j.event_type, "status": j.status, "created_at": j.created_at, "sent_at": j.sent_at} for j in jobs]}


@patient_router.patch("/me/reminders/{schedule_id}")
def set_reminder(schedule_id: UUID, active: bool, patient: User = Depends(require_roles(UserRole.PATIENT)), db: Session = Depends(get_db)) -> dict:
    schedule = db.get(MedicationReminderSchedule, schedule_id)
    if not schedule or schedule.patient_user_id != patient.id: raise HTTPException(404, "Reminder not found")
    schedule.is_active = active; db.commit(); return {"id": str(schedule.id), "is_active": schedule.is_active}


@admin_router.get("/summary")
def summary(_: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(NotificationOutbox.status, func.count()).group_by(NotificationOutbox.status)).all()
    return {status.value: count for status, count in rows}
