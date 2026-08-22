from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.appointment import (
    Appointment,
    AppointmentStatus,
    AppointmentStatusHistory,
    HoldStatus,
    SlotHold,
    SymptomSubmission,
)
from app.models.doctor import DoctorProfile
from app.models.user import User

ACTIVE_APPOINTMENT_STATUSES = (
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.RESCHEDULE_REQUIRED,
)


class AppointmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def lock_doctor(self, doctor_id: UUID) -> DoctorProfile | None:
        return self.db.scalar(
            select(DoctorProfile)
            .where(DoctorProfile.id == doctor_id)
            .with_for_update(of=DoctorProfile)
        )

    def expire_holds(self, now: datetime, doctor_id: UUID | None = None) -> int:
        statement = (
            update(SlotHold)
            .where(SlotHold.status == HoldStatus.ACTIVE, SlotHold.expires_at <= now)
            .values(status=HoldStatus.EXPIRED)
        )
        if doctor_id:
            statement = statement.where(SlotHold.doctor_profile_id == doctor_id)
        result = self.db.execute(statement)
        self.db.flush()
        return result.rowcount

    def create_hold(self, **fields: object) -> SlotHold:
        hold = SlotHold(**fields)
        self.db.add(hold)
        self.db.flush()
        self.db.refresh(hold)
        return hold

    def get_hold_by_hash(self, token_hash: str, *, lock: bool = False) -> SlotHold | None:
        statement = select(SlotHold).where(SlotHold.token_hash == token_hash)
        if lock:
            statement = statement.with_for_update(of=SlotHold)
        return self.db.scalar(statement)

    def has_active_hold_overlap(
        self, doctor_id: UUID, slot_start: datetime, slot_end: datetime
    ) -> bool:
        return self.db.scalar(
            select(SlotHold.id).where(
                SlotHold.doctor_profile_id == doctor_id,
                SlotHold.status == HoldStatus.ACTIVE,
                SlotHold.slot_start < slot_end,
                SlotHold.slot_end > slot_start,
            ).limit(1)
        ) is not None

    def has_active_appointment_overlap(
        self,
        doctor_id: UUID,
        slot_start: datetime,
        slot_end: datetime,
        *,
        exclude_id: UUID | None = None,
    ) -> bool:
        statement = select(Appointment.id).where(
            Appointment.doctor_profile_id == doctor_id,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            Appointment.slot_start < slot_end,
            Appointment.slot_end > slot_start,
        )
        if exclude_id:
            statement = statement.where(Appointment.id != exclude_id)
        return self.db.scalar(statement.limit(1)) is not None

    def create_appointment(self, **fields: object) -> Appointment:
        appointment = Appointment(**fields)
        self.db.add(appointment)
        self.db.flush()
        self.db.refresh(appointment)
        return appointment

    def create_symptoms(self, appointment: Appointment, **fields: object) -> SymptomSubmission:
        symptoms = SymptomSubmission(appointment=appointment, **fields)
        self.db.add(symptoms)
        self.db.flush()
        return symptoms

    def create_history(
        self,
        appointment: Appointment,
        *,
        previous_status: AppointmentStatus | None,
        new_status: AppointmentStatus,
        actor_user_id: UUID | None,
        reason: str | None,
    ) -> AppointmentStatusHistory:
        history = AppointmentStatusHistory(
            appointment=appointment,
            previous_status=previous_status,
            new_status=new_status,
            actor_user_id=actor_user_id,
            reason=reason,
        )
        self.db.add(history)
        self.db.flush()
        return history

    def get_appointment(self, appointment_id: UUID, *, lock: bool = False) -> Appointment | None:
        statement = (
            select(Appointment)
            .options(
                selectinload(Appointment.symptom_submission),
                selectinload(Appointment.history),
            )
            .where(Appointment.id == appointment_id)
        )
        if lock:
            statement = statement.with_for_update(of=Appointment)
        return self.db.scalar(statement)

    def list_for_patient(
        self, patient_id: UUID, *, page: int, page_size: int
    ) -> tuple[list[Appointment], int]:
        filters = (Appointment.patient_user_id == patient_id,)
        return self._list(filters, page, page_size)

    def list_for_doctor(
        self, doctor_id: UUID, *, page: int, page_size: int
    ) -> tuple[list[Appointment], int]:
        filters = (Appointment.doctor_profile_id == doctor_id,)
        return self._list(filters, page, page_size)

    def list_admin(self, *, page: int, page_size: int) -> tuple[list[Appointment], int]:
        return self._list((), page, page_size)

    def _list(
        self, filters: tuple[object, ...], page: int, page_size: int
    ) -> tuple[list[Appointment], int]:
        total = self.db.scalar(
            select(func.count()).select_from(Appointment).where(*filters)
        ) or 0
        statement = (
            select(Appointment)
            .where(*filters)
            .order_by(Appointment.slot_start.desc(), Appointment.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement).all()), total

    def active_for_period(
        self, doctor_id: UUID, period_start: datetime, period_end: datetime
    ) -> list[Appointment]:
        statement = (
            select(Appointment)
            .where(
                Appointment.doctor_profile_id == doctor_id,
                Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
                Appointment.slot_start < period_end,
                Appointment.slot_end > period_start,
            )
            .order_by(Appointment.slot_start)
        )
        return list(self.db.scalars(statement).all())
