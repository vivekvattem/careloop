from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies.auth import require_roles
from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.user import User, UserRole
from app.models.visit import PostVisitSummary, PreVisitSummary, ReviewStatus
from app.schemas.visit import (
    ClinicalRecordPublic,
    CompleteVisitRequest,
    PatientPostVisitPublic,
    PostVisitApprovalRequest,
    PostVisitSummaryPublic,
    PreVisitSummaryPublic,
    PrescriptionItemInput,
    PrescriptionItemPublic,
    PrescriptionItemUpdate,
    RegenerationAccepted,
    UpdateClinicalRecordRequest,
)
from app.services.visit import (
    SummaryStateError,
    VisitNotFoundError,
    VisitPermissionError,
    VisitService,
    VisitStateError,
    post_summary_public,
    pre_summary_public,
    run_post_visit_generation,
    run_pre_visit_generation,
)

patient_router = APIRouter(prefix="/appointments", tags=["visit intelligence"])
doctor_router = APIRouter(prefix="/doctor/me/appointments", tags=["doctor visit intelligence"])


def _factory(db: Session):
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, VisitNotFoundError):
        return HTTPException(404, "Clinical record or summary not found")
    if isinstance(exc, VisitPermissionError):
        return HTTPException(403, "You cannot access this clinical record")
    return HTTPException(409, "Visit state does not allow this operation")


@patient_router.get("/{appointment_id}/pre-visit-summary", response_model=PreVisitSummaryPublic)
def patient_pre_summary(
    appointment_id: UUID,
    patient: User = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_db),
) -> PreVisitSummaryPublic:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None or appointment.patient_user_id != patient.id:
        raise HTTPException(404, "Summary not found")
    summary = db.scalar(select(PreVisitSummary).where(PreVisitSummary.appointment_id == appointment_id))
    if summary is None:
        raise HTTPException(404, "Summary not found")
    return pre_summary_public(db, summary)


@patient_router.get("/{appointment_id}/post-visit-summary", response_model=PatientPostVisitPublic)
def patient_post_summary(
    appointment_id: UUID,
    patient: User = Depends(require_roles(UserRole.PATIENT)),
    db: Session = Depends(get_db),
) -> PatientPostVisitPublic:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None or appointment.patient_user_id != patient.id:
        raise HTTPException(404, "Summary not found")
    summary = db.scalar(select(PostVisitSummary).where(PostVisitSummary.appointment_id == appointment_id))
    if summary is None:
        raise HTTPException(404, "Summary not found")
    approved = summary.review_status == ReviewStatus.APPROVED
    return PatientPostVisitPublic(
        appointment_id=appointment_id,
        availability="approved" if approved else "awaiting_doctor_review",
        generation_source=summary.generation_source if approved else None,
        approved_content=summary.approved_content if approved else None,
    )


@doctor_router.get("/{appointment_id}/pre-visit-summary", response_model=PreVisitSummaryPublic)
def doctor_pre_summary(
    appointment_id: UUID,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> PreVisitSummaryPublic:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None or appointment.doctor_profile.user_id != doctor.id:
        raise HTTPException(404, "Summary not found")
    summary = db.scalar(select(PreVisitSummary).where(PreVisitSummary.appointment_id == appointment_id))
    if summary is None:
        raise HTTPException(404, "Summary not found")
    return pre_summary_public(db, summary)


@doctor_router.post(
    "/{appointment_id}/pre-visit-summary/regenerate",
    response_model=RegenerationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_pre_summary(
    appointment_id: UUID,
    background_tasks: BackgroundTasks,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> RegenerationAccepted:
    try:
        result = VisitService(db).mark_regeneration(appointment_id, doctor, post=False)
    except (VisitNotFoundError, VisitStateError) as exc:
        raise _translate(exc) from None
    if result.should_start:
        background_tasks.add_task(run_pre_visit_generation, appointment_id, _factory(db))
    return result


@doctor_router.post("/{appointment_id}/complete", response_model=ClinicalRecordPublic)
def complete_visit(
    appointment_id: UUID,
    data: CompleteVisitRequest,
    background_tasks: BackgroundTasks,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> ClinicalRecordPublic:
    existing = db.get(Appointment, appointment_id)
    was_completed = existing is not None and existing.status.value == "completed"
    try:
        result = VisitService(db).complete(appointment_id, doctor, data)
    except (VisitNotFoundError, VisitPermissionError, VisitStateError) as exc:
        raise _translate(exc) from None
    if not was_completed:
        background_tasks.add_task(run_post_visit_generation, appointment_id, _factory(db))
    return result


@doctor_router.get("/{appointment_id}/clinical-record", response_model=ClinicalRecordPublic)
def clinical_record(
    appointment_id: UUID,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> ClinicalRecordPublic:
    try:
        return VisitService(db).get_record(appointment_id, doctor)
    except VisitNotFoundError as exc:
        raise _translate(exc) from None


@doctor_router.get("/{appointment_id}/visit", response_model=ClinicalRecordPublic)
def visit_record(
    appointment_id: UUID,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> ClinicalRecordPublic:
    try:
        return VisitService(db).get_record(appointment_id, doctor)
    except VisitNotFoundError as exc:
        raise _translate(exc) from None


@doctor_router.put("/{appointment_id}/clinical-record", response_model=ClinicalRecordPublic)
def update_clinical_record(
    appointment_id: UUID,
    data: UpdateClinicalRecordRequest,
    background_tasks: BackgroundTasks,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> ClinicalRecordPublic:
    try:
        result = VisitService(db).update_record(appointment_id, doctor, data)
    except (VisitNotFoundError, VisitPermissionError, VisitStateError) as exc:
        raise _translate(exc) from None
    background_tasks.add_task(run_post_visit_generation, appointment_id, _factory(db))
    return result


@doctor_router.put("/{appointment_id}/visit", response_model=ClinicalRecordPublic)
def update_visit_record(
    appointment_id: UUID,
    data: UpdateClinicalRecordRequest,
    background_tasks: BackgroundTasks,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> ClinicalRecordPublic:
    try:
        result = VisitService(db).update_record(appointment_id, doctor, data)
    except (VisitNotFoundError, VisitPermissionError, VisitStateError) as exc:
        raise _translate(exc) from None
    background_tasks.add_task(run_post_visit_generation, appointment_id, _factory(db))
    return result


@doctor_router.post(
    "/{appointment_id}/prescriptions", response_model=PrescriptionItemPublic, status_code=status.HTTP_201_CREATED
)
def add_prescription(
    appointment_id: UUID,
    data: PrescriptionItemInput,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> PrescriptionItemPublic:
    try:
        return VisitService(db).add_prescription_item(appointment_id, doctor, data)
    except (VisitNotFoundError, VisitPermissionError, VisitStateError) as exc:
        raise _translate(exc) from None


@doctor_router.patch(
    "/{appointment_id}/prescriptions/{prescription_id}", response_model=PrescriptionItemPublic
)
def update_prescription(
    appointment_id: UUID,
    prescription_id: UUID,
    data: PrescriptionItemUpdate,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> PrescriptionItemPublic:
    try:
        return VisitService(db).update_prescription_item(appointment_id, prescription_id, doctor, data)
    except (VisitNotFoundError, VisitPermissionError, VisitStateError) as exc:
        raise _translate(exc) from None


@doctor_router.delete("/{appointment_id}/prescriptions/{prescription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prescription(
    appointment_id: UUID,
    prescription_id: UUID,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> None:
    try:
        VisitService(db).delete_prescription_item(appointment_id, prescription_id, doctor)
    except (VisitNotFoundError, VisitPermissionError, VisitStateError) as exc:
        raise _translate(exc) from None


@doctor_router.get("/{appointment_id}/post-visit-summary", response_model=PostVisitSummaryPublic)
def doctor_post_summary(
    appointment_id: UUID,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> PostVisitSummaryPublic:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None or appointment.doctor_profile.user_id != doctor.id:
        raise HTTPException(404, "Summary not found")
    summary = db.scalar(select(PostVisitSummary).where(PostVisitSummary.appointment_id == appointment_id))
    if summary is None:
        raise HTTPException(404, "Summary not found")
    return post_summary_public(summary)


@doctor_router.post(
    "/{appointment_id}/post-visit-summary/regenerate",
    response_model=RegenerationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_post_summary(
    appointment_id: UUID,
    background_tasks: BackgroundTasks,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> RegenerationAccepted:
    try:
        result = VisitService(db).mark_regeneration(appointment_id, doctor, post=True)
    except (VisitNotFoundError, VisitStateError) as exc:
        raise _translate(exc) from None
    if result.should_start:
        background_tasks.add_task(run_post_visit_generation, appointment_id, _factory(db))
    return result


@doctor_router.post("/{appointment_id}/post-visit-summary/approve", response_model=PostVisitSummaryPublic)
def approve_post_summary(
    appointment_id: UUID,
    data: PostVisitApprovalRequest,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> PostVisitSummaryPublic:
    try:
        return VisitService(db).approve(appointment_id, doctor, data)
    except (VisitNotFoundError, SummaryStateError) as exc:
        raise _translate(exc) from None


@doctor_router.post("/{appointment_id}/post-visit-summary/reject", response_model=PostVisitSummaryPublic)
def reject_post_summary(
    appointment_id: UUID,
    doctor: User = Depends(require_roles(UserRole.DOCTOR)),
    db: Session = Depends(get_db),
) -> PostVisitSummaryPublic:
    try:
        return VisitService(db).reject(appointment_id, doctor)
    except VisitNotFoundError as exc:
        raise _translate(exc) from None
