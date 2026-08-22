from uuid import UUID

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories.doctor import DoctorRepository
from app.schemas.doctor import (
    DoctorAdmin,
    DoctorAdminList,
    DoctorProvisionRequest,
    DoctorUpdateRequest,
    LeaveAdmin,
    LeaveCreate,
    WorkingHourCreate,
    WorkingHourPublic,
    WorkingHourUpdate,
)
from app.schemas.appointment import LeaveApplyResult, LeaveConflictPreview
from app.services.appointment import (
    DoctorUnavailableError,
    LeaveConflictError,
    LeaveConflictService,
)
from app.services.doctor import (
    DoctorManagementService,
    DoctorNotFoundError,
    DoctorProvisioningError,
    DuplicateDoctorEmailError,
    DuplicateLeaveError,
    InvalidWorkingHourError,
    WorkingHourConflictError,
    to_doctor_admin,
    to_leave_admin,
    to_working_hour,
)

router = APIRouter(
    prefix="/admin/doctors",
    tags=["admin doctors"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor or resource not found")


@router.post("", response_model=DoctorAdmin, status_code=status.HTTP_201_CREATED)
def create_doctor(
    data: DoctorProvisionRequest,
    db: Session = Depends(get_db),
) -> DoctorAdmin:
    try:
        profile = DoctorManagementService(db).provision(data)
    except DuplicateDoctorEmailError:
        raise HTTPException(status_code=409, detail="An account with this email already exists") from None
    except DoctorProvisioningError:
        raise HTTPException(status_code=409, detail="Doctor profile could not be created") from None
    return to_doctor_admin(profile)


@router.get("", response_model=DoctorAdminList)
def list_doctors(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> DoctorAdminList:
    items, total = DoctorRepository(db).list_admin(page=page, page_size=page_size)
    return DoctorAdminList(
        items=[to_doctor_admin(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{doctor_id}", response_model=DoctorAdmin)
def get_doctor(doctor_id: UUID, db: Session = Depends(get_db)) -> DoctorAdmin:
    try:
        return to_doctor_admin(DoctorManagementService(db).get(doctor_id))
    except DoctorNotFoundError:
        raise _not_found() from None


@router.patch("/{doctor_id}", response_model=DoctorAdmin)
def update_doctor(
    doctor_id: UUID,
    data: DoctorUpdateRequest,
    db: Session = Depends(get_db),
) -> DoctorAdmin:
    try:
        return to_doctor_admin(DoctorManagementService(db).update(doctor_id, data))
    except DoctorNotFoundError:
        raise _not_found() from None


@router.post(
    "/{doctor_id}/working-hours",
    response_model=WorkingHourPublic,
    status_code=status.HTTP_201_CREATED,
)
def add_working_hour(
    doctor_id: UUID,
    data: WorkingHourCreate,
    db: Session = Depends(get_db),
) -> WorkingHourPublic:
    try:
        return to_working_hour(DoctorManagementService(db).add_working_hour(doctor_id, data))
    except DoctorNotFoundError:
        raise _not_found() from None
    except WorkingHourConflictError:
        raise HTTPException(status_code=409, detail="Working interval overlaps an existing interval") from None


@router.patch(
    "/{doctor_id}/working-hours/{working_hour_id}", response_model=WorkingHourPublic
)
def update_working_hour(
    doctor_id: UUID,
    working_hour_id: UUID,
    data: WorkingHourUpdate,
    db: Session = Depends(get_db),
) -> WorkingHourPublic:
    try:
        interval = DoctorManagementService(db).update_working_hour(
            doctor_id, working_hour_id, data
        )
        return to_working_hour(interval)
    except DoctorNotFoundError:
        raise _not_found() from None
    except InvalidWorkingHourError:
        raise HTTPException(status_code=422, detail="Start time must be before end time") from None
    except WorkingHourConflictError:
        raise HTTPException(status_code=409, detail="Working interval overlaps an existing interval") from None


@router.delete(
    "/{doctor_id}/working-hours/{working_hour_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_working_hour(
    doctor_id: UUID,
    working_hour_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    try:
        DoctorManagementService(db).delete_working_hour(doctor_id, working_hour_id)
    except DoctorNotFoundError:
        raise _not_found() from None


@router.post(
    "/{doctor_id}/leave",
    response_model=LeaveApplyResult,
    status_code=status.HTTP_201_CREATED,
)
def add_leave(
    doctor_id: UUID,
    data: LeaveCreate,
    confirm_conflicts: bool = Query(default=False),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> LeaveApplyResult:
    try:
        return LeaveConflictService(db).apply(
            doctor_id,
            data,
            confirmed=confirm_conflicts,
            actor_user_id=admin.id,
        )
    except (DoctorNotFoundError, DoctorUnavailableError):
        raise _not_found() from None
    except DuplicateLeaveError:
        raise HTTPException(status_code=409, detail="Leave already exists for this date") from None
    except LeaveConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "leave_conflicts",
                "affected_count": exc.preview.affected_count,
                "appointment_ids": [
                    str(item.appointment_id) for item in exc.preview.appointments
                ],
            },
        ) from None


@router.get("/{doctor_id}/leave-conflicts", response_model=LeaveConflictPreview)
def preview_leave_conflicts(
    doctor_id: UUID,
    date_: date = Query(alias="date"),
    db: Session = Depends(get_db),
) -> LeaveConflictPreview:
    try:
        return LeaveConflictService(db).preview(doctor_id, date_)
    except DoctorUnavailableError:
        raise _not_found() from None


@router.delete(
    "/{doctor_id}/leave/{leave_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_leave(
    doctor_id: UUID,
    leave_id: UUID,
    db: Session = Depends(get_db),
) -> None:
    try:
        DoctorManagementService(db).delete_leave(doctor_id, leave_id)
    except DoctorNotFoundError:
        raise _not_found() from None
