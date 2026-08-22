from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.doctor import DoctorLeave, DoctorProfile, DoctorWorkingHour
from app.models.user import UserRole
from app.repositories.doctor import DoctorRepository
from app.repositories.user import UserRepository
from app.schemas.doctor import (
    DoctorAdmin,
    DoctorProvisionRequest,
    DoctorPublic,
    DoctorSelf,
    DoctorUpdateRequest,
    LeaveAdmin,
    LeaveCreate,
    Slot,
    SlotPreview,
    WorkingHourCreate,
    WorkingHourPublic,
    WorkingHourUpdate,
)


class DoctorNotFoundError(Exception):
    pass


class DuplicateDoctorEmailError(Exception):
    pass


class DoctorProvisioningError(Exception):
    pass


class WorkingHourConflictError(Exception):
    pass


class InvalidWorkingHourError(Exception):
    pass


class DuplicateLeaveError(Exception):
    pass


def to_working_hour(interval: DoctorWorkingHour) -> WorkingHourPublic:
    return WorkingHourPublic.model_validate(interval)


def to_leave_admin(leave: DoctorLeave) -> LeaveAdmin:
    return LeaveAdmin.model_validate(leave)


def to_doctor_admin(profile: DoctorProfile) -> DoctorAdmin:
    return DoctorAdmin(
        id=profile.id,
        user_id=profile.user_id,
        full_name=profile.user.full_name,
        email=profile.user.email,
        role=profile.user.role,
        is_active=profile.user.is_active,
        specialisation=profile.specialisation,
        qualifications=profile.qualifications,
        biography=profile.biography,
        consultation_mode=profile.consultation_mode,
        location=profile.location,
        slot_duration_minutes=profile.slot_duration_minutes,
        timezone=profile.timezone,
        is_available_for_booking=profile.is_available_for_booking,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        working_hours=[to_working_hour(item) for item in profile.working_hours],
        leaves=[to_leave_admin(item) for item in profile.leaves],
    )


def to_doctor_public(profile: DoctorProfile) -> DoctorPublic:
    return DoctorPublic(
        id=profile.id,
        full_name=profile.user.full_name,
        specialisation=profile.specialisation,
        qualifications=profile.qualifications,
        biography=profile.biography,
        consultation_mode=profile.consultation_mode,
        location=profile.location,
        slot_duration_minutes=profile.slot_duration_minutes,
        timezone=profile.timezone,
    )


def to_doctor_self(profile: DoctorProfile) -> DoctorSelf:
    return DoctorSelf(
        id=profile.id,
        user_id=profile.user_id,
        full_name=profile.user.full_name,
        email=profile.user.email,
        specialisation=profile.specialisation,
        qualifications=profile.qualifications,
        biography=profile.biography,
        consultation_mode=profile.consultation_mode,
        location=profile.location,
        slot_duration_minutes=profile.slot_duration_minutes,
        timezone=profile.timezone,
        is_available_for_booking=profile.is_available_for_booking,
        is_active=profile.user.is_active,
    )


class DoctorManagementService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.doctors = DoctorRepository(db)

    def provision(self, data: DoctorProvisionRequest) -> DoctorProfile:
        if self.users.get_by_email(str(data.email)):
            raise DuplicateDoctorEmailError

        profile_fields = data.model_dump(
            exclude={"full_name", "email", "initial_password"}
        )
        try:
            user = self.users.create(
                full_name=data.full_name,
                email=str(data.email),
                password_hash=hash_password(data.initial_password),
                role=UserRole.DOCTOR,
            )
            profile = self.doctors.create_profile(user=user, **profile_fields)
        except IntegrityError as exc:
            self.db.rollback()
            if self.users.get_by_email(str(data.email)):
                raise DuplicateDoctorEmailError from exc
            raise DoctorProvisioningError from exc
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise DoctorProvisioningError from exc
        return profile

    def get(self, doctor_id: UUID) -> DoctorProfile:
        profile = self.doctors.get_by_id(doctor_id)
        if profile is None:
            raise DoctorNotFoundError
        return profile

    def update(self, doctor_id: UUID, data: DoctorUpdateRequest) -> DoctorProfile:
        profile = self.get(doctor_id)
        supplied = data.model_fields_set
        if "full_name" in supplied and data.full_name is not None:
            profile.user.full_name = data.full_name
        if "is_active" in supplied and data.is_active is not None:
            profile.user.is_active = data.is_active

        profile_fields = supplied - {"full_name", "is_active"}
        for field_name in profile_fields:
            setattr(profile, field_name, getattr(data, field_name))
        self.db.flush()
        return self.get(doctor_id)

    def add_working_hour(
        self, doctor_id: UUID, data: WorkingHourCreate
    ) -> DoctorWorkingHour:
        profile = self.get(doctor_id)
        if self.doctors.find_overlapping_interval(
            doctor_id=doctor_id,
            day_of_week=data.day_of_week,
            start_time=data.start_time,
            end_time=data.end_time,
        ):
            raise WorkingHourConflictError
        try:
            return self.doctors.add_working_hour(profile=profile, **data.model_dump())
        except IntegrityError as exc:
            self.db.rollback()
            raise WorkingHourConflictError from exc

    def update_working_hour(
        self,
        doctor_id: UUID,
        working_hour_id: UUID,
        data: WorkingHourUpdate,
    ) -> DoctorWorkingHour:
        self.get(doctor_id)
        interval = self.doctors.get_working_hour(doctor_id, working_hour_id)
        if interval is None:
            raise DoctorNotFoundError
        day_of_week = data.day_of_week if data.day_of_week is not None else interval.day_of_week
        start_time = data.start_time if data.start_time is not None else interval.start_time
        end_time = data.end_time if data.end_time is not None else interval.end_time
        if start_time >= end_time:
            raise InvalidWorkingHourError
        if self.doctors.find_overlapping_interval(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            exclude_id=interval.id,
        ):
            raise WorkingHourConflictError
        interval.day_of_week = day_of_week
        interval.start_time = start_time
        interval.end_time = end_time
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise WorkingHourConflictError from exc
        self.db.refresh(interval)
        return interval

    def delete_working_hour(self, doctor_id: UUID, working_hour_id: UUID) -> None:
        self.get(doctor_id)
        interval = self.doctors.get_working_hour(doctor_id, working_hour_id)
        if interval is None:
            raise DoctorNotFoundError
        self.doctors.delete_working_hour(interval)

    def add_leave(self, doctor_id: UUID, data: LeaveCreate) -> DoctorLeave:
        profile = self.get(doctor_id)
        if self.doctors.get_leave_for_date(doctor_id, data.leave_date):
            raise DuplicateLeaveError
        try:
            return self.doctors.add_leave(profile=profile, **data.model_dump())
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateLeaveError from exc

    def delete_leave(self, doctor_id: UUID, leave_id: UUID) -> None:
        self.get(doctor_id)
        leave = self.doctors.get_leave(doctor_id, leave_id)
        if leave is None:
            raise DoctorNotFoundError
        # Phase 2B will notify or block around conflicting appointments here.
        self.doctors.delete_leave(leave)


class SlotGenerationService:
    def __init__(self, db: Session) -> None:
        self.doctors = DoctorRepository(db)

    def generate(
        self,
        doctor_id: UUID,
        requested_date: date,
        *,
        now: datetime | None = None,
    ) -> SlotPreview:
        profile = self.doctors.get_by_id(doctor_id)
        if profile is None:
            raise DoctorNotFoundError
        doctor_timezone = ZoneInfo(profile.timezone)

        if not profile.user.is_active or not profile.is_available_for_booking:
            return self._empty(profile, requested_date, "doctor_inactive")
        if self.doctors.get_leave_for_date(doctor_id, requested_date):
            return self._empty(profile, requested_date, "on_leave")

        intervals = self.doctors.list_working_hours_for_weekday(
            doctor_id, requested_date.weekday()
        )
        if not intervals:
            return self._empty(profile, requested_date, "no_working_hours")

        local_now = (now or datetime.now(doctor_timezone)).astimezone(doctor_timezone)
        duration = timedelta(minutes=profile.slot_duration_minutes)
        generated: dict[tuple[datetime, datetime], Slot] = {}
        for interval in intervals:
            cursor = datetime.combine(requested_date, interval.start_time, doctor_timezone)
            interval_end = datetime.combine(requested_date, interval.end_time, doctor_timezone)
            while cursor + duration <= interval_end:
                slot_end = cursor + duration
                if cursor > local_now:
                    generated[(cursor, slot_end)] = Slot(start=cursor, end=slot_end)
                cursor = slot_end

        from app.repositories.appointment import AppointmentRepository

        appointment_repository = AppointmentRepository(self.doctors.db)
        appointment_repository.expire_holds(local_now.astimezone(timezone.utc), doctor_id)
        slots = [
            generated[key]
            for key in sorted(generated)
            if not appointment_repository.has_active_hold_overlap(
                doctor_id,
                generated[key].start.astimezone(timezone.utc),
                generated[key].end.astimezone(timezone.utc),
            )
            and not appointment_repository.has_active_appointment_overlap(
                doctor_id,
                generated[key].start.astimezone(timezone.utc),
                generated[key].end.astimezone(timezone.utc),
            )
        ]
        return SlotPreview(
            doctor_id=profile.id,
            date=requested_date,
            timezone=profile.timezone,
            availability="available",
            slots=slots,
        )

    @staticmethod
    def _empty(
        profile: DoctorProfile,
        requested_date: date,
        availability: str,
    ) -> SlotPreview:
        return SlotPreview(
            doctor_id=profile.id,
            date=requested_date,
            timezone=profile.timezone,
            availability=availability,
            slots=[],
        )
