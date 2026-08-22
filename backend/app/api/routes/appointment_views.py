from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.repositories.appointment import AppointmentRepository
from app.repositories.doctor import DoctorRepository
from app.schemas.appointment import AppointmentDetail, AppointmentList
from app.services.appointment import to_detail, to_list_item

doctor_router = APIRouter(prefix="/doctor/me/appointments", tags=["doctor appointments"])
admin_router = APIRouter(prefix="/admin/appointments", tags=["admin appointments"])


@doctor_router.get("", response_model=AppointmentList)
def doctor_appointments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> AppointmentList:
    profile = DoctorRepository(db).get_by_user_id(doctor.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Doctor profile not found")
    items, total = AppointmentRepository(db).list_for_doctor(
        profile.id, page=page, page_size=page_size
    )
    return AppointmentList(items=[to_list_item(item) for item in items], page=page, page_size=page_size, total=total)


@doctor_router.get("/{appointment_id}", response_model=AppointmentDetail)
def doctor_appointment(
    appointment_id: UUID,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> AppointmentDetail:
    profile = DoctorRepository(db).get_by_user_id(doctor.id)
    appointment = AppointmentRepository(db).get_appointment(appointment_id)
    if profile is None or appointment is None or appointment.doctor_profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return to_detail(appointment)


@admin_router.get("", response_model=AppointmentList)
def admin_appointments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> AppointmentList:
    items, total = AppointmentRepository(db).list_admin(page=page, page_size=page_size)
    return AppointmentList(items=[to_list_item(item) for item in items], page=page, page_size=page_size, total=total)

