from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies.auth import require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories.appointment import AppointmentRepository
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentDetail,
    AppointmentList,
    CancellationRequest,
    HoldCreate,
    HoldResponse,
    RescheduleRequest,
)
from app.services.appointment import (
    AppointmentNotFoundError,
    AppointmentPermissionError,
    AppointmentService,
    DoctorUnavailableError,
    HoldConflictError,
    InvalidSlotError,
    InvalidTransitionError,
    to_detail,
    to_list_item,
)
from app.services.visit import run_pre_visit_generation

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, AppointmentNotFoundError):
        return HTTPException(status_code=404, detail="Appointment not found")
    if isinstance(error, AppointmentPermissionError):
        return HTTPException(status_code=403, detail="You cannot access this appointment or hold")
    if isinstance(error, DoctorUnavailableError):
        return HTTPException(status_code=404, detail="Doctor is unavailable")
    if isinstance(error, InvalidSlotError):
        return HTTPException(status_code=422, detail="The requested time is not a valid schedule slot")
    if isinstance(error, InvalidTransitionError):
        return HTTPException(status_code=409, detail="Appointment state does not allow this operation")
    return HTTPException(status_code=409, detail="The hold or appointment slot is no longer available")


@router.post("/holds", response_model=HoldResponse, status_code=status.HTTP_201_CREATED)
def create_hold(
    data: HoldCreate,
    patient: User = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_db),
) -> HoldResponse:
    try:
        return AppointmentService(db).create_hold(patient, data.doctor_id, data.slot_start)
    except (DoctorUnavailableError, InvalidSlotError, HoldConflictError) as exc:
        raise _translate(exc) from None


@router.post("", response_model=AppointmentDetail, status_code=status.HTTP_201_CREATED)
def confirm_appointment(
    data: AppointmentCreate,
    background_tasks: BackgroundTasks,
    patient: User = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_db),
) -> AppointmentDetail:
    try:
        appointment = AppointmentService(db).confirm(patient, data.hold_token, data.symptoms)
        factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
        background_tasks.add_task(run_pre_visit_generation, appointment.id, factory)
        return to_detail(appointment)
    except (
        AppointmentPermissionError,
        DoctorUnavailableError,
        InvalidSlotError,
        HoldConflictError,
    ) as exc:
        raise _translate(exc) from None


@router.get("/me", response_model=AppointmentList)
def patient_appointments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    patient: User = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_db),
) -> AppointmentList:
    items, total = AppointmentRepository(db).list_for_patient(
        patient.id, page=page, page_size=page_size
    )
    return AppointmentList(
        items=[to_list_item(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{appointment_id}", response_model=AppointmentDetail)
def patient_appointment(
    appointment_id: UUID,
    patient: User = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_db),
) -> AppointmentDetail:
    appointment = AppointmentRepository(db).get_appointment(appointment_id)
    if appointment is None or appointment.patient_user_id != patient.id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return to_detail(appointment)


@router.post("/{appointment_id}/cancel", response_model=AppointmentDetail)
def cancel_appointment(
    appointment_id: UUID,
    data: CancellationRequest,
    actor: User = Depends(require_roles(UserRole.PATIENT, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> AppointmentDetail:
    try:
        return to_detail(AppointmentService(db).cancel(appointment_id, actor, data.reason))
    except (
        AppointmentNotFoundError,
        AppointmentPermissionError,
        InvalidTransitionError,
    ) as exc:
        raise _translate(exc) from None


@router.post("/{appointment_id}/reschedule", response_model=AppointmentDetail)
def reschedule_appointment(
    appointment_id: UUID,
    data: RescheduleRequest,
    background_tasks: BackgroundTasks,
    patient: User = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_db),
) -> AppointmentDetail:
    try:
        appointment = AppointmentService(db).reschedule(
            appointment_id,
            patient,
            data.new_hold_token,
            data.reason,
        )
        factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
        background_tasks.add_task(run_pre_visit_generation, appointment.id, factory)
        return to_detail(appointment)
    except (
        AppointmentNotFoundError,
        AppointmentPermissionError,
        DoctorUnavailableError,
        InvalidSlotError,
        InvalidTransitionError,
        HoldConflictError,
    ) as exc:
        raise _translate(exc) from None
