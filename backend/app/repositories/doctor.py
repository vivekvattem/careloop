from datetime import date, time
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.doctor import DoctorLeave, DoctorProfile, DoctorWorkingHour
from app.models.user import User


class DoctorRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _with_details():
        return (
            select(DoctorProfile)
            .options(
                selectinload(DoctorProfile.working_hours),
                selectinload(DoctorProfile.leaves),
            )
        )

    def create_profile(self, *, user: User, **fields: object) -> DoctorProfile:
        profile = DoctorProfile(user=user, **fields)
        self.db.add(profile)
        self.db.flush()
        self.db.refresh(profile)
        return profile

    def get_by_id(self, doctor_id: UUID) -> DoctorProfile | None:
        statement = self._with_details().where(DoctorProfile.id == doctor_id)
        return self.db.scalar(statement)

    def get_by_user_id(self, user_id: UUID) -> DoctorProfile | None:
        statement = self._with_details().where(DoctorProfile.user_id == user_id)
        return self.db.scalar(statement)

    def list_admin(self, *, page: int, page_size: int) -> tuple[list[DoctorProfile], int]:
        total = self.db.scalar(select(func.count()).select_from(DoctorProfile)) or 0
        statement = (
            self._with_details()
            .join(DoctorProfile.user)
            .order_by(User.full_name, DoctorProfile.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement).all()), total

    def list_public(
        self,
        *,
        page: int,
        page_size: int,
        specialisation: str | None,
    ) -> tuple[list[DoctorProfile], int]:
        filters = [User.is_active.is_(True), DoctorProfile.is_available_for_booking.is_(True)]
        if specialisation:
            filters.append(
                func.lower(DoctorProfile.specialisation).contains(specialisation.strip().lower())
            )
        base = select(DoctorProfile).join(DoctorProfile.user).where(*filters)
        total = self.db.scalar(
            select(func.count()).select_from(base.order_by(None).subquery())
        ) or 0
        statement = (
            base.order_by(User.full_name, DoctorProfile.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(statement).all()), total

    def get_public_by_id(self, doctor_id: UUID) -> DoctorProfile | None:
        statement = (
            select(DoctorProfile)
            .join(DoctorProfile.user)
            .where(
                DoctorProfile.id == doctor_id,
                User.is_active.is_(True),
                DoctorProfile.is_available_for_booking.is_(True),
            )
        )
        return self.db.scalar(statement)

    def add_working_hour(
        self,
        *,
        profile: DoctorProfile,
        day_of_week: int,
        start_time: time,
        end_time: time,
    ) -> DoctorWorkingHour:
        interval = DoctorWorkingHour(
            doctor_profile=profile,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
        )
        self.db.add(interval)
        self.db.flush()
        self.db.refresh(interval)
        return interval

    def get_working_hour(
        self, doctor_id: UUID, working_hour_id: UUID
    ) -> DoctorWorkingHour | None:
        return self.db.scalar(
            select(DoctorWorkingHour).where(
                DoctorWorkingHour.doctor_profile_id == doctor_id,
                DoctorWorkingHour.id == working_hour_id,
            )
        )

    def find_overlapping_interval(
        self,
        *,
        doctor_id: UUID,
        day_of_week: int,
        start_time: time,
        end_time: time,
        exclude_id: UUID | None = None,
    ) -> DoctorWorkingHour | None:
        statement = select(DoctorWorkingHour).where(
            DoctorWorkingHour.doctor_profile_id == doctor_id,
            DoctorWorkingHour.day_of_week == day_of_week,
            DoctorWorkingHour.start_time < end_time,
            DoctorWorkingHour.end_time > start_time,
        )
        if exclude_id:
            statement = statement.where(DoctorWorkingHour.id != exclude_id)
        return self.db.scalar(statement.limit(1))

    def delete_working_hour(self, interval: DoctorWorkingHour) -> None:
        self.db.delete(interval)
        self.db.flush()

    def add_leave(
        self, *, profile: DoctorProfile, leave_date: date, reason: str | None
    ) -> DoctorLeave:
        leave = DoctorLeave(
            doctor_profile=profile,
            leave_date=leave_date,
            reason=reason,
        )
        self.db.add(leave)
        self.db.flush()
        self.db.refresh(leave)
        return leave

    def get_leave(self, doctor_id: UUID, leave_id: UUID) -> DoctorLeave | None:
        return self.db.scalar(
            select(DoctorLeave).where(
                DoctorLeave.doctor_profile_id == doctor_id,
                DoctorLeave.id == leave_id,
            )
        )

    def get_leave_for_date(self, doctor_id: UUID, leave_date: date) -> DoctorLeave | None:
        return self.db.scalar(
            select(DoctorLeave).where(
                DoctorLeave.doctor_profile_id == doctor_id,
                DoctorLeave.leave_date == leave_date,
            )
        )

    def delete_leave(self, leave: DoctorLeave) -> None:
        self.db.delete(leave)
        self.db.flush()

    def list_working_hours_for_weekday(
        self, doctor_id: UUID, day_of_week: int
    ) -> list[DoctorWorkingHour]:
        statement = (
            select(DoctorWorkingHour)
            .where(
                DoctorWorkingHour.doctor_profile_id == doctor_id,
                DoctorWorkingHour.day_of_week == day_of_week,
            )
            .order_by(DoctorWorkingHour.start_time, DoctorWorkingHour.end_time)
        )
        return list(self.db.scalars(statement).all())

    def list_upcoming_leaves(self, doctor_id: UUID, from_date: date) -> list[DoctorLeave]:
        statement = (
            select(DoctorLeave)
            .where(
                DoctorLeave.doctor_profile_id == doctor_id,
                DoctorLeave.leave_date >= from_date,
            )
            .order_by(DoctorLeave.leave_date)
        )
        return list(self.db.scalars(statement).all())

