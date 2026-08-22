import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    DDL,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.doctor import DoctorProfile
from app.models.user import User


class HoldStatus(str, enum.Enum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    RELEASED = "released"


class AppointmentStatus(str, enum.Enum):
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    RESCHEDULE_REQUIRED = "reschedule_required"


def enum_values(enum_type: type[enum.Enum]) -> list[str]:
    return [str(item.value) for item in enum_type]


class SlotHold(TimestampMixin, Base):
    __tablename__ = "slot_holds"
    __table_args__ = (
        CheckConstraint("slot_start < slot_end", name="start_before_end"),
        Index("ix_slot_holds_doctor_time", "doctor_profile_id", "slot_start", "slot_end"),
        Index("ix_slot_holds_patient_status", "patient_user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    doctor_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="CASCADE"), nullable=False
    )
    patient_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[HoldStatus] = mapped_column(
        Enum(HoldStatus, name="hold_status", values_callable=enum_values),
        default=HoldStatus.ACTIVE,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    doctor_profile: Mapped[DoctorProfile] = relationship(lazy="joined")
    patient: Mapped[User] = relationship(lazy="joined")


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("slot_start < slot_end", name="start_before_end"),
        UniqueConstraint("rescheduled_from_id", name="uq_appointments_rescheduled_from_id"),
        Index("ix_appointments_patient_start", "patient_user_id", "slot_start"),
        Index("ix_appointments_doctor_start", "doctor_profile_id", "slot_start"),
        Index("ix_appointments_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    doctor_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status", values_callable=enum_values),
        default=AppointmentStatus.CONFIRMED,
        nullable=False,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rescheduled_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL")
    )

    patient: Mapped[User] = relationship(foreign_keys=[patient_user_id], lazy="joined")
    doctor_profile: Mapped[DoctorProfile] = relationship(lazy="joined")
    rescheduled_from: Mapped["Appointment | None"] = relationship(
        remote_side="Appointment.id", foreign_keys=[rescheduled_from_id]
    )
    symptom_submission: Mapped["SymptomSubmission | None"] = relationship(
        back_populates="appointment", cascade="all, delete-orphan", uselist=False
    )
    history: Mapped[list["AppointmentStatusHistory"]] = relationship(
        back_populates="appointment",
        cascade="all, delete-orphan",
        order_by="AppointmentStatusHistory.created_at",
    )


class SymptomSubmission(TimestampMixin, Base):
    __tablename__ = "symptom_submissions"
    __table_args__ = (
        CheckConstraint("severity BETWEEN 1 AND 10", name="severity_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    chief_complaint: Mapped[str] = mapped_column(String(200), nullable=False)
    symptom_description: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    existing_conditions: Mapped[str | None] = mapped_column(Text)
    current_medications: Mapped[str | None] = mapped_column(Text)

    appointment: Mapped[Appointment] = relationship(back_populates="symptom_submission")


class AppointmentStatusHistory(Base):
    __tablename__ = "appointment_status_history"
    __table_args__ = (
        Index("ix_appointment_status_history_appointment_created", "appointment_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    previous_status: Mapped[AppointmentStatus | None] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status", values_callable=enum_values),
    )
    new_status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status", values_callable=enum_values),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    appointment: Mapped[Appointment] = relationship(back_populates="history")
    actor: Mapped[User | None] = relationship(lazy="joined")


event.listen(
    SlotHold.__table__,
    "after_create",
    DDL(
        "ALTER TABLE slot_holds ADD CONSTRAINT ex_slot_holds_active_overlap "
        "EXCLUDE USING gist (doctor_profile_id WITH =, "
        "tstzrange(slot_start, slot_end, '[)') WITH &&) WHERE (status = 'active')"
    ).execute_if(dialect="postgresql"),
)
event.listen(
    Appointment.__table__,
    "after_create",
    DDL(
        "ALTER TABLE appointments ADD CONSTRAINT ex_appointments_active_overlap "
        "EXCLUDE USING gist (doctor_profile_id WITH =, "
        "tstzrange(slot_start, slot_end, '[)') WITH &&) "
        "WHERE (status IN ('confirmed', 'reschedule_required'))"
    ).execute_if(dialect="postgresql"),
)
