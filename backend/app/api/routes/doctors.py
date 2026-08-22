from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_roles
from app.db.session import get_db
from app.models.user import UserRole
from app.repositories.doctor import DoctorRepository
from app.schemas.doctor import DoctorPublic, DoctorPublicList, SlotPreview
from app.services.doctor import DoctorNotFoundError, SlotGenerationService, to_doctor_public

router = APIRouter(
    prefix="/doctors",
    tags=["doctor discovery"],
    dependencies=[Depends(require_roles(UserRole.PATIENT))],
)


@router.get("", response_model=DoctorPublicList)
def list_doctors(
    specialisation: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> DoctorPublicList:
    items, total = DoctorRepository(db).list_public(
        page=page,
        page_size=page_size,
        specialisation=specialisation,
    )
    return DoctorPublicList(
        items=[to_doctor_public(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{doctor_id}", response_model=DoctorPublic)
def get_doctor(doctor_id: UUID, db: Session = Depends(get_db)) -> DoctorPublic:
    profile = DoctorRepository(db).get_public_by_id(doctor_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    return to_doctor_public(profile)


@router.get("/{doctor_id}/slots", response_model=SlotPreview)
def preview_slots(
    doctor_id: UUID,
    date_: date = Query(alias="date"),
    db: Session = Depends(get_db),
) -> SlotPreview:
    try:
        return SlotGenerationService(db).generate(doctor_id, date_)
    except DoctorNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found") from None

