from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories.doctor import DoctorRepository
from app.schemas.doctor import (
    DoctorLeaveList,
    DoctorSchedule,
    DoctorSelf,
)
from app.services.doctor import to_doctor_self, to_leave_admin, to_working_hour

router = APIRouter(prefix="/doctor/me", tags=["doctor self-service"])


def _own_profile(current_user: User, db: Session):
    profile = DoctorRepository(db).get_by_user_id(current_user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor profile not found")
    return profile


@router.get("/profile", response_model=DoctorSelf)
def own_profile(
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> DoctorSelf:
    return to_doctor_self(_own_profile(current_user, db))


@router.get("/schedule", response_model=DoctorSchedule)
def own_schedule(
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> DoctorSchedule:
    profile = _own_profile(current_user, db)
    return DoctorSchedule(
        timezone=profile.timezone,
        slot_duration_minutes=profile.slot_duration_minutes,
        working_hours=[to_working_hour(item) for item in profile.working_hours],
    )


@router.get("/leave", response_model=DoctorLeaveList)
def own_leave(
    current_user: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> DoctorLeaveList:
    profile = _own_profile(current_user, db)
    today = datetime.now(ZoneInfo(profile.timezone)).date()
    leaves = DoctorRepository(db).list_upcoming_leaves(profile.id, today)
    return DoctorLeaveList(leaves=[to_leave_admin(item) for item in leaves])

