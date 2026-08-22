import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.user import User


class DoctorProfile(TimestampMixin, Base):
    __tablename__ = "doctor_profiles"
    __table_args__ = (
        CheckConstraint(
            "slot_duration_minutes BETWEEN 5 AND 180",
            name="slot_duration_range",
        ),
        CheckConstraint("length(trim(specialisation)) > 0", name="specialisation_not_blank"),
        CheckConstraint(
            "consultation_mode IN ('in_person', 'video', 'hybrid')",
            name="valid_consultation_mode",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    specialisation: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    qualifications: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    biography: Mapped[str] = mapped_column(Text, default="", nullable=False)
    consultation_mode: Mapped[str] = mapped_column(String(80), default="in_person", nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    is_available_for_booking: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(lazy="joined")
    working_hours: Mapped[list["DoctorWorkingHour"]] = relationship(
        back_populates="doctor_profile",
        cascade="all, delete-orphan",
        order_by="DoctorWorkingHour.day_of_week, DoctorWorkingHour.start_time",
    )
    leaves: Mapped[list["DoctorLeave"]] = relationship(
        back_populates="doctor_profile",
        cascade="all, delete-orphan",
        order_by="DoctorLeave.leave_date",
    )


class DoctorWorkingHour(TimestampMixin, Base):
    __tablename__ = "doctor_working_hours"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="valid_day_of_week"),
        CheckConstraint("start_time < end_time", name="start_before_end"),
        UniqueConstraint(
            "doctor_profile_id",
            "day_of_week",
            "start_time",
            "end_time",
            name="uq_doctor_working_hours_interval",
        ),
        Index("ix_doctor_working_hours_profile_weekday", "doctor_profile_id", "day_of_week"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    doctor_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="CASCADE"), nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    doctor_profile: Mapped[DoctorProfile] = relationship(back_populates="working_hours")


class DoctorLeave(Base):
    __tablename__ = "doctor_leaves"
    __table_args__ = (
        UniqueConstraint(
            "doctor_profile_id",
            "leave_date",
            name="uq_doctor_leaves_profile_date",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    doctor_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctor_profiles.id", ondelete="CASCADE"), nullable=False
    )
    leave_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    doctor_profile: Mapped[DoctorProfile] = relationship(back_populates="leaves")
