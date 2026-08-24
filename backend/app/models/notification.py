import enum
import uuid
from datetime import datetime, time

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


def enum_values(enum_type):
    return [item.value for item in enum_type]


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    RETRY_SCHEDULED = "retry_scheduled"
    PERMANENTLY_FAILED = "permanently_failed"
    CANCELLED = "cancelled"


class NotificationEventType(str, enum.Enum):
    APPOINTMENT_CONFIRMED = "appointment_confirmed"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    APPOINTMENT_RESCHEDULED = "appointment_rescheduled"
    POST_VISIT_APPROVED = "post_visit_approved"
    MEDICATION_REMINDER_DUE = "medication_reminder_due"
    PASSWORD_RESET = "password_reset"


class NotificationOutbox(TimestampMixin, Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_notification_outbox_idempotency_key"),
        Index("ix_notification_outbox_due", "status", "next_attempt_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_type: Mapped[NotificationEventType] = mapped_column(Enum(NotificationEventType, name="notification_event_type", values_callable=enum_values), nullable=False)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("appointments.id", ondelete="CASCADE"))
    prescription_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prescription_items.id", ondelete="CASCADE"))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(Enum(NotificationStatus, name="notification_status", values_callable=enum_values), default=NotificationStatus.PENDING, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    maximum_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    failure_category: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(String(255))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MedicationReminderSchedule(TimestampMixin, Base):
    __tablename__ = "medication_reminder_schedules"
    __table_args__ = (UniqueConstraint("prescription_item_id", "reminder_time", name="uq_medication_reminder_item_time"), Index("ix_medication_reminder_due", "is_active", "next_due_at"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    prescription_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prescription_items.id", ondelete="CASCADE"), nullable=False)
    patient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reminder_time: Mapped[time] = mapped_column(nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
