from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_hold_token, hash_hold_token
from app.models.appointment import Appointment, AppointmentStatus, HoldStatus, SlotHold
from app.models.doctor import DoctorProfile
from app.models.user import User, UserRole
from app.repositories.appointment import AppointmentRepository
from app.repositories.doctor import DoctorRepository
from app.schemas.appointment import (
    AppointmentDetail,
    AppointmentListItem,
    HoldResponse,
    LeaveApplyResult,
    LeaveConflictItem,
    LeaveConflictPreview,
    StatusHistoryPublic,
    SymptomInput,
    SymptomPublic,
)
from app.schemas.doctor import LeaveCreate


class AppointmentNotFoundError(Exception):
    pass


class AppointmentPermissionError(Exception):
    pass


class HoldConflictError(Exception):
    pass


class InvalidSlotError(Exception):
    pass


class DoctorUnavailableError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


class LeaveConflictError(Exception):
    def __init__(self, preview: LeaveConflictPreview) -> None:
        self.preview = preview


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_list_item(appointment: Appointment) -> AppointmentListItem:
    return AppointmentListItem(
        id=appointment.id,
        patient_user_id=appointment.patient_user_id,
        doctor_id=appointment.doctor_profile_id,
        doctor_name=appointment.doctor_profile.user.full_name,
        patient_name=appointment.patient.full_name,
        slot_start=utc(appointment.slot_start),
        slot_end=utc(appointment.slot_end),
        status=appointment.status,
        cancellation_reason=appointment.cancellation_reason,
        rescheduled_from_id=appointment.rescheduled_from_id,
        created_at=utc(appointment.created_at),
    )


def to_detail(appointment: Appointment) -> AppointmentDetail:
    item = to_list_item(appointment)
    symptoms = appointment.symptom_submission
    return AppointmentDetail(
        **item.model_dump(),
        symptoms=SymptomPublic.model_validate(symptoms, from_attributes=True) if symptoms else None,
        history=[
            StatusHistoryPublic(
                id=entry.id,
                previous_status=entry.previous_status,
                new_status=entry.new_status,
                actor_user_id=entry.actor_user_id,
                reason=entry.reason,
                created_at=utc(entry.created_at),
            )
            for entry in appointment.history
        ],
    )


class AppointmentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.appointments = AppointmentRepository(db)
        self.doctors = DoctorRepository(db)

    def create_hold(
        self,
        patient: User,
        doctor_id: UUID,
        requested_start: datetime,
        *,
        now: datetime | None = None,
    ) -> HoldResponse:
        current = utc(now or datetime.now(timezone.utc))
        start = utc(requested_start)
        profile = self.appointments.lock_doctor(doctor_id)
        if profile is None or not profile.user.is_active or not profile.is_available_for_booking:
            raise DoctorUnavailableError
        end = self._validate_schedule_slot(profile, start, current)
        self.appointments.expire_holds(current, doctor_id)
        if self.appointments.has_active_hold_overlap(doctor_id, start, end):
            raise HoldConflictError
        if self.appointments.has_active_appointment_overlap(doctor_id, start, end):
            raise HoldConflictError

        raw_token = generate_hold_token()
        expires_at = current + timedelta(minutes=settings.slot_hold_minutes)
        try:
            hold = self.appointments.create_hold(
                doctor_profile_id=doctor_id,
                patient_user_id=patient.id,
                slot_start=start,
                slot_end=end,
                token_hash=hash_hold_token(raw_token),
                status=HoldStatus.ACTIVE,
                expires_at=expires_at,
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HoldConflictError from exc
        return HoldResponse(
            hold_token=raw_token,
            hold_id=hold.id,
            doctor_id=doctor_id,
            slot_start=start,
            slot_end=end,
            expires_at=expires_at,
            remaining_seconds=settings.slot_hold_minutes * 60,
            status=hold.status,
        )

    def confirm(
        self,
        patient: User,
        raw_token: str,
        symptoms: SymptomInput,
        *,
        now: datetime | None = None,
    ) -> Appointment:
        current = utc(now or datetime.now(timezone.utc))
        token_hash = hash_hold_token(raw_token)
        initial = self.appointments.get_hold_by_hash(token_hash)
        if initial is None:
            raise HoldConflictError
        self.appointments.lock_doctor(initial.doctor_profile_id)
        hold = self.appointments.get_hold_by_hash(token_hash, lock=True)
        if hold is None or hold.patient_user_id != patient.id:
            raise AppointmentPermissionError
        if hold.status != HoldStatus.ACTIVE:
            raise HoldConflictError
        if utc(hold.expires_at) <= current:
            hold.status = HoldStatus.EXPIRED
            self.db.commit()
            raise HoldConflictError

        profile = hold.doctor_profile
        end = self._validate_schedule_slot(profile, utc(hold.slot_start), current)
        if end != utc(hold.slot_end):
            raise InvalidSlotError
        if self.appointments.has_active_appointment_overlap(
            profile.id, utc(hold.slot_start), utc(hold.slot_end)
        ):
            raise HoldConflictError
        try:
            appointment = self.appointments.create_appointment(
                patient_user_id=patient.id,
                doctor_profile_id=profile.id,
                slot_start=utc(hold.slot_start),
                slot_end=utc(hold.slot_end),
                status=AppointmentStatus.CONFIRMED,
            )
            symptom_record = self.appointments.create_symptoms(
                appointment, **symptoms.model_dump()
            )
            from app.services.visit import create_pending_pre_visit

            create_pending_pre_visit(self.db, appointment, symptom_record)
            from app.models.notification import NotificationEventType
            from app.services.notifications import appointment_payload, enqueue
            enqueue(self.db, event_type=NotificationEventType.APPOINTMENT_CONFIRMED, recipient=patient, appointment_id=appointment.id, idempotency_key=f"appointment-confirmed:{appointment.id}", payload=appointment_payload(appointment, message="Your CareLoop appointment is confirmed."))
            # Calendar delivery is durable work in this same domain transaction; it never calls Google here.
            from app.services.calendar import enqueue_sync
            enqueue_sync(self.db, appointment, patient.id)
            self.appointments.create_history(
                appointment,
                previous_status=None,
                new_status=AppointmentStatus.CONFIRMED,
                actor_user_id=patient.id,
                reason="Appointment confirmed",
            )
            hold.status = HoldStatus.CONSUMED
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HoldConflictError from exc
        return self.appointments.get_appointment(appointment.id) or appointment

    def cancel(self, appointment_id: UUID, actor: User, reason: str) -> Appointment:
        initial = self.appointments.get_appointment(appointment_id)
        if initial is None:
            raise AppointmentNotFoundError
        self.appointments.lock_doctor(initial.doctor_profile_id)
        appointment = self.appointments.get_appointment(appointment_id, lock=True)
        if appointment is None:
            raise AppointmentNotFoundError
        if actor.role != UserRole.ADMIN and appointment.patient_user_id != actor.id:
            raise AppointmentPermissionError
        if appointment.status not in (
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.RESCHEDULE_REQUIRED,
        ):
            raise InvalidTransitionError
        previous = appointment.status
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancellation_reason = reason
        appointment.cancelled_at = datetime.now(timezone.utc)
        from app.models.notification import NotificationEventType
        from app.services.notifications import appointment_payload, enqueue
        enqueue(self.db, event_type=NotificationEventType.APPOINTMENT_CANCELLED, recipient=appointment.patient, appointment_id=appointment.id, idempotency_key=f"appointment-cancelled:{appointment.id}", payload=appointment_payload(appointment, message="Your CareLoop appointment was cancelled."))
        from app.services.calendar import enqueue_sync
        enqueue_sync(self.db, appointment, appointment.patient_user_id)
        self.appointments.create_history(
            appointment,
            previous_status=previous,
            new_status=AppointmentStatus.CANCELLED,
            actor_user_id=actor.id,
            reason=reason,
        )
        self.db.commit()
        return self.appointments.get_appointment(appointment.id) or appointment

    def reschedule(
        self,
        appointment_id: UUID,
        patient: User,
        raw_token: str,
        reason: str | None,
        *,
        now: datetime | None = None,
    ) -> Appointment:
        current = utc(now or datetime.now(timezone.utc))
        token_hash = hash_hold_token(raw_token)
        initial_appointment = self.appointments.get_appointment(appointment_id)
        initial_hold = self.appointments.get_hold_by_hash(token_hash)
        if initial_appointment is None:
            raise AppointmentNotFoundError
        if initial_hold is None:
            raise HoldConflictError
        for doctor_id in sorted(
            {initial_appointment.doctor_profile_id, initial_hold.doctor_profile_id}, key=str
        ):
            self.appointments.lock_doctor(doctor_id)
        original = self.appointments.get_appointment(appointment_id, lock=True)
        hold = self.appointments.get_hold_by_hash(token_hash, lock=True)
        if original is None or original.patient_user_id != patient.id:
            raise AppointmentPermissionError
        if original.status not in (
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.RESCHEDULE_REQUIRED,
        ):
            raise InvalidTransitionError
        self._validate_hold(hold, patient.id, current)
        assert hold is not None
        self._validate_schedule_slot(hold.doctor_profile, utc(hold.slot_start), current)
        if self.appointments.has_active_appointment_overlap(
            hold.doctor_profile_id,
            utc(hold.slot_start),
            utc(hold.slot_end),
            exclude_id=original.id,
        ):
            raise HoldConflictError

        previous = original.status
        original.status = AppointmentStatus.CANCELLED
        original.cancelled_at = current
        original.cancellation_reason = reason or "Rescheduled by patient"
        try:
            replacement = self.appointments.create_appointment(
                patient_user_id=patient.id,
                doctor_profile_id=hold.doctor_profile_id,
                slot_start=utc(hold.slot_start),
                slot_end=utc(hold.slot_end),
                status=AppointmentStatus.CONFIRMED,
                rescheduled_from_id=original.id,
            )
            if original.symptom_submission:
                source = original.symptom_submission
                replacement_symptoms = self.appointments.create_symptoms(
                    replacement,
                    chief_complaint=source.chief_complaint,
                    symptom_description=source.symptom_description,
                    duration=source.duration,
                    severity=source.severity,
                    existing_conditions=source.existing_conditions,
                    current_medications=source.current_medications,
                )
                from app.services.visit import create_pending_pre_visit

                create_pending_pre_visit(self.db, replacement, replacement_symptoms)
            self.appointments.create_history(
                original,
                previous_status=previous,
                new_status=AppointmentStatus.CANCELLED,
                actor_user_id=patient.id,
                reason=original.cancellation_reason,
            )
            self.appointments.create_history(
                replacement,
                previous_status=None,
                new_status=AppointmentStatus.CONFIRMED,
                actor_user_id=patient.id,
                reason="Created by rescheduling",
            )
            from app.models.notification import NotificationEventType
            from app.services.notifications import appointment_payload, enqueue
            enqueue(self.db, event_type=NotificationEventType.APPOINTMENT_RESCHEDULED, recipient=patient, appointment_id=replacement.id, idempotency_key=f"appointment-rescheduled:{replacement.id}", payload=appointment_payload(replacement, message="Your CareLoop appointment was rescheduled."))
            # Rescheduling creates a replacement row. Delete/create avoids transferring a Google mapping
            # across appointment identities and remains idempotent for adjacent reschedules.
            from app.services.calendar import enqueue_sync
            enqueue_sync(self.db, original, patient.id)
            enqueue_sync(self.db, replacement, patient.id)
            hold.status = HoldStatus.CONSUMED
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HoldConflictError from exc
        return self.appointments.get_appointment(replacement.id) or replacement

    def _validate_hold(
        self, hold: SlotHold | None, patient_id: UUID, current: datetime
    ) -> None:
        if hold is None or hold.patient_user_id != patient_id:
            raise AppointmentPermissionError
        if hold.status == HoldStatus.ACTIVE and utc(hold.expires_at) <= current:
            hold.status = HoldStatus.EXPIRED
            self.db.commit()
            raise HoldConflictError
        if hold.status != HoldStatus.ACTIVE:
            raise HoldConflictError

    def _validate_schedule_slot(
        self, profile: DoctorProfile, start_utc: datetime, current: datetime
    ) -> datetime:
        if not profile.user.is_active or not profile.is_available_for_booking:
            raise DoctorUnavailableError
        if start_utc <= current:
            raise InvalidSlotError
        zone = ZoneInfo(profile.timezone)
        local_start = start_utc.astimezone(zone)
        requested_date = local_start.date()
        if self.doctors.get_leave_for_date(profile.id, requested_date):
            raise InvalidSlotError
        duration = timedelta(minutes=profile.slot_duration_minutes)
        for interval in self.doctors.list_working_hours_for_weekday(
            profile.id, requested_date.weekday()
        ):
            cursor = datetime.combine(requested_date, interval.start_time, zone)
            interval_end = datetime.combine(requested_date, interval.end_time, zone)
            while cursor + duration <= interval_end:
                if cursor == local_start:
                    return utc(cursor + duration)
                cursor += duration
        raise InvalidSlotError


class LeaveConflictService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.appointments = AppointmentRepository(db)
        self.doctors = DoctorRepository(db)

    def preview(self, doctor_id: UUID, leave_date: date) -> LeaveConflictPreview:
        profile = self.doctors.get_by_id(doctor_id)
        if profile is None:
            raise DoctorUnavailableError
        appointments = self._conflicts(profile, leave_date)
        return self._preview(profile.id, leave_date, appointments)

    def apply(
        self,
        doctor_id: UUID,
        data: LeaveCreate,
        *,
        confirmed: bool,
        actor_user_id: UUID,
    ) -> LeaveApplyResult:
        profile = self.appointments.lock_doctor(doctor_id)
        if profile is None:
            raise DoctorUnavailableError
        if self.doctors.get_leave_for_date(doctor_id, data.leave_date):
            from app.services.doctor import DuplicateLeaveError

            raise DuplicateLeaveError
        conflicts = self._conflicts(profile, data.leave_date)
        if conflicts and not confirmed:
            raise LeaveConflictError(self._preview(doctor_id, data.leave_date, conflicts))
        try:
            leave = self.doctors.add_leave(
                profile=profile, leave_date=data.leave_date, reason=data.reason
            )
        except IntegrityError as exc:
            self.db.rollback()
            from app.services.doctor import DuplicateLeaveError

            raise DuplicateLeaveError from exc
        affected: list[UUID] = []
        for appointment in conflicts:
            previous = appointment.status
            appointment.status = AppointmentStatus.RESCHEDULE_REQUIRED
            self.appointments.create_history(
                appointment,
                previous_status=previous,
                new_status=AppointmentStatus.RESCHEDULE_REQUIRED,
                actor_user_id=actor_user_id,
                reason=f"Doctor leave on {data.leave_date.isoformat()}",
            )
            affected.append(appointment.id)
        self.db.commit()
        return LeaveApplyResult(
            id=leave.id,
            leave_date=leave.leave_date,
            reason=leave.reason,
            created_at=utc(leave.created_at),
            affected_count=len(affected),
            affected_appointment_ids=affected,
        )

    def _conflicts(self, profile: DoctorProfile, leave_date: date) -> list[Appointment]:
        zone = ZoneInfo(profile.timezone)
        start = utc(datetime.combine(leave_date, time.min, zone))
        end = utc(datetime.combine(leave_date + timedelta(days=1), time.min, zone))
        return self.appointments.active_for_period(profile.id, start, end)

    @staticmethod
    def _preview(
        doctor_id: UUID, leave_date: date, appointments: list[Appointment]
    ) -> LeaveConflictPreview:
        return LeaveConflictPreview(
            doctor_id=doctor_id,
            date=leave_date,
            affected_count=len(appointments),
            appointments=[
                LeaveConflictItem(
                    appointment_id=item.id,
                    slot_start=utc(item.slot_start),
                    slot_end=utc(item.slot_end),
                    status=item.status,
                )
                for item in appointments
            ],
        )
