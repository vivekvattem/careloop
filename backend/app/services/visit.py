from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment, AppointmentStatus, SymptomSubmission
from app.models.user import User
from app.models.visit import (
    CareDocument,
    CareDocumentType,
    ClinicalNote,
    GenerationSource,
    GenerationStatus,
    PostVisitSummary,
    Prescription,
    PrescriptionItem,
    PreVisitSummary,
    PreVisitSummarySource,
    ReviewStatus,
    Urgency,
)
from app.repositories.appointment import AppointmentRepository
from app.schemas.visit import (
    ClinicalRecordPublic,
    CompleteVisitRequest,
    MedicationScheduleOutput,
    PostVisitApprovalRequest,
    PostVisitLLMOutput,
    PostVisitSummaryPublic,
    PreVisitLLMOutput,
    PreVisitSummaryPublic,
    PrescriptionItemInput,
    PrescriptionItemUpdate,
    PrescriptionItemPublic,
    RegenerationAccepted,
    SummarySourcePublic,
)
from app.services.llm import LLMGenerationError, LLMProvider, configured_provider
from app.services.prompts import (
    POST_VISIT_PROMPT_VERSION,
    POST_VISIT_SYSTEM_PROMPT,
    PRE_VISIT_PROMPT_VERSION,
    PRE_VISIT_SYSTEM_PROMPT,
    structured_user_prompt,
)

SessionFactory = Callable[[], Session]


class VisitNotFoundError(Exception):
    pass


class VisitPermissionError(Exception):
    pass


class VisitStateError(Exception):
    pass


class SummaryStateError(Exception):
    pass


def create_pending_pre_visit(
    db: Session, appointment: Appointment, symptoms: SymptomSubmission
) -> PreVisitSummary:
    summary = PreVisitSummary(
        appointment_id=appointment.id,
        status=GenerationStatus.PENDING,
        provider=settings.llm_provider,
        model_identifier=settings.llm_model,
        prompt_version=PRE_VISIT_PROMPT_VERSION,
        attempt_count=0,
        historical_context_used=False,
    )
    document = CareDocument(
        patient_user_id=appointment.patient_user_id,
        appointment_id=appointment.id,
        document_type=CareDocumentType.SYMPTOMS,
        content=(
            f"Chief complaint: {symptoms.chief_complaint}. "
            f"Description: {symptoms.symptom_description}. Duration: {symptoms.duration}. "
            f"Severity: {symptoms.severity}/10."
        ),
        event_date=appointment.slot_start,
        doctor_verified=False,
    )
    db.add_all([summary, document])
    return summary


def _urgency_from_severity(severity: int) -> Urgency:
    if severity >= 8:
        return Urgency.HIGH
    if severity >= 5:
        return Urgency.MEDIUM
    return Urgency.LOW


def _pre_fallback(symptoms: dict[str, object]) -> PreVisitLLMOutput:
    return PreVisitLLMOutput(
        urgency=_urgency_from_severity(int(symptoms["severity"])),
        chief_complaint=str(symptoms["chief_complaint"]),
        suggested_questions=[
            "What details about these symptoms are most important for this visit?",
            "What evaluation or next steps do you recommend?",
            "What changes should prompt me to seek help sooner?",
        ],
        relevant_history_note=None,
        safety_disclaimer="This summary supports clinician review and is not a diagnosis.",
    )


def _medication_schedule(prescription: Prescription) -> list[dict]:
    return [
        MedicationScheduleOutput(
            medication_name=item.medication_name,
            dosage=item.dosage,
            route=item.route,
            frequency_per_day=item.frequency_per_day,
            reminder_times=sorted(item.reminder_times),
            start_date=item.start_date,
            end_date=item.end_date,
            food_instructions=item.food_instructions,
            additional_instructions=item.additional_instructions,
        ).model_dump(mode="json")
        for item in prescription.items
        if item.is_active
    ]


def _serialize_reminder_times(values: list) -> list[str]:
    return sorted(value.isoformat(timespec="minutes") for value in values)


def _validate_item_schedule(item: PrescriptionItem) -> None:
    if len(set(item.reminder_times)) != len(item.reminder_times):
        raise VisitStateError
    if len(item.reminder_times) > item.frequency_per_day:
        raise VisitStateError


def _post_fallback(note: ClinicalNote, prescription: Prescription) -> PostVisitLLMOutput:
    follow_up = [note.follow_up_instructions]
    if note.recommended_follow_up_date:
        follow_up.append(f"Recommended follow-up date: {note.recommended_follow_up_date.isoformat()}")
    explanation = note.diagnosis or note.original_notes
    return PostVisitLLMOutput(
        patient_friendly_summary=f"Your doctor recorded: {explanation}",
        medication_schedule=[
            MedicationScheduleOutput.model_validate(item)
            for item in _medication_schedule(prescription)
        ],
        follow_up_steps=follow_up,
        warning_signs=[],
        safety_disclaimer="Follow your clinician's instructions and seek urgent care for emergencies.",
    )


class HistoryRetriever:
    def retrieve(
        self, db: Session, *, patient_id: UUID, appointment_id: UUID, query_text: str
    ) -> list[tuple[CareDocument, float]]:
        base_filters = (
            CareDocument.patient_user_id == patient_id,
            CareDocument.appointment_id != appointment_id,
            or_(
                CareDocument.doctor_verified.is_(True),
                CareDocument.document_type == CareDocumentType.SYMPTOMS,
            ),
        )
        reliability = case(
            (CareDocument.document_type == CareDocumentType.CLINICAL_NOTE, 3.0),
            (CareDocument.document_type == CareDocumentType.PRESCRIPTION, 2.5),
            (CareDocument.document_type == CareDocumentType.APPROVED_POST_VISIT, 2.0),
            else_=1.0,
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            rank = func.ts_rank_cd(
                func.to_tsvector("simple", CareDocument.content),
                func.plainto_tsquery("simple", query_text),
            )
            score = (rank * 10 + reliability).label("ranking_score")
            statement = (
                select(CareDocument, score)
                .where(*base_filters)
                .order_by(score.desc(), CareDocument.event_date.desc())
                .limit(3)
            )
            return [(document, float(value)) for document, value in db.execute(statement)]

        documents = list(
            db.scalars(
                select(CareDocument)
                .where(*base_filters)
                .order_by(CareDocument.doctor_verified.desc(), CareDocument.event_date.desc())
                .limit(20)
            )
        )
        query_terms = {term.lower() for term in query_text.split() if len(term) > 2}
        scored = []
        for document in documents:
            overlap = len(query_terms & set(document.content.lower().split()))
            source_score = {
                CareDocumentType.CLINICAL_NOTE: 3.0,
                CareDocumentType.PRESCRIPTION: 2.5,
                CareDocumentType.APPROVED_POST_VISIT: 2.0,
            }.get(document.document_type, 1.0)
            scored.append((document, overlap * 10.0 + source_score))
        return sorted(scored, key=lambda item: (item[1], item[0].event_date), reverse=True)[:3]


def run_pre_visit_generation(
    appointment_id: UUID,
    session_factory: SessionFactory,
    provider: LLMProvider | None = None,
    retriever: HistoryRetriever | None = None,
) -> None:
    provider = provider or configured_provider()
    retriever = retriever or HistoryRetriever()
    sources: list[tuple[CareDocument, float]] = []
    with session_factory() as db:
        appointment = db.get(Appointment, appointment_id)
        symptoms = db.scalar(
            select(SymptomSubmission).where(SymptomSubmission.appointment_id == appointment_id)
        )
        summary = db.scalar(
            select(PreVisitSummary).where(PreVisitSummary.appointment_id == appointment_id)
        )
        if appointment is None or symptoms is None or summary is None:
            return
        symptom_data = {
            "chief_complaint": symptoms.chief_complaint,
            "symptom_description": symptoms.symptom_description,
            "duration": symptoms.duration,
            "severity": symptoms.severity,
            "existing_conditions": symptoms.existing_conditions,
            "current_medications": symptoms.current_medications,
        }
        try:
            sources = retriever.retrieve(
                db,
                patient_id=appointment.patient_user_id,
                appointment_id=appointment.id,
                query_text=f"{symptoms.chief_complaint} {symptoms.symptom_description}",
            )
        except SQLAlchemyError:
            db.rollback()
            sources = []
        history_data = [
            {
                "document_type": document.document_type.value,
                "event_date": document.event_date,
                "content": document.content[:1500],
            }
            for document, _ in sources
        ]

    prompt = structured_user_prompt(
        sections={"current_symptoms": symptom_data, "retrieved_history": history_data},
        response_schema=PreVisitLLMOutput,
    )
    error: LLMGenerationError | None = None
    try:
        output, attempts = provider.generate_structured(
            system_prompt=PRE_VISIT_SYSTEM_PROMPT,
            user_prompt=prompt,
            response_schema=PreVisitLLMOutput,
        )
        source = GenerationSource.LLM
        status = GenerationStatus.COMPLETED
    except LLMGenerationError as exc:
        error = exc
        attempts = exc.attempts
        output = _pre_fallback(symptom_data)
        source = GenerationSource.DETERMINISTIC_FALLBACK
        status = GenerationStatus.FALLBACK

    with session_factory() as db:
        summary = db.scalar(
            select(PreVisitSummary)
            .where(PreVisitSummary.appointment_id == appointment_id)
            .with_for_update()
        )
        if summary is None:
            return
        db.execute(
            delete(PreVisitSummarySource).where(
                PreVisitSummarySource.pre_visit_summary_id == summary.id
            )
        )
        summary.status = status
        summary.attempt_count += attempts
        summary.failure_category = error.category if error else None
        summary.failure_message = error.safe_message if error else None
        summary.generated_at = datetime.now(timezone.utc)
        summary.historical_context_used = bool(sources) and error is None
        summary.generation_source = source
        summary.urgency = output.urgency
        summary.chief_complaint = output.chief_complaint
        summary.suggested_questions = output.suggested_questions
        summary.relevant_history_note = output.relevant_history_note
        summary.safety_disclaimer = output.safety_disclaimer
        if error is None:
            for position, (document, score) in enumerate(sources, start=1):
                db.add(
                    PreVisitSummarySource(
                        pre_visit_summary_id=summary.id,
                        care_document_id=document.id,
                        rank_position=position,
                        ranking_score=score,
                    )
                )
        db.commit()


def run_post_visit_generation(
    appointment_id: UUID,
    session_factory: SessionFactory,
    provider: LLMProvider | None = None,
) -> None:
    provider = provider or configured_provider()
    with session_factory() as db:
        note = db.scalar(select(ClinicalNote).where(ClinicalNote.appointment_id == appointment_id))
        prescription = db.scalar(
            select(Prescription).where(Prescription.appointment_id == appointment_id)
        )
        summary = db.scalar(
            select(PostVisitSummary).where(PostVisitSummary.appointment_id == appointment_id)
        )
        if note is None or prescription is None or summary is None:
            return
        expected_schedule = _medication_schedule(prescription)
        note_data = {
            "original_notes": note.original_notes,
            "diagnosis": note.diagnosis,
            "treatment_plan": note.treatment_plan,
            "follow_up_instructions": note.follow_up_instructions,
            "recommended_follow_up_date": note.recommended_follow_up_date,
        }
        prescription_data = {
            "general_instructions": prescription.general_instructions,
            "items": expected_schedule,
        }
        fallback = _post_fallback(note, prescription)

    prompt = structured_user_prompt(
        sections={"doctor_authored_note": note_data, "structured_prescription": prescription_data},
        response_schema=PostVisitLLMOutput,
    )
    error: LLMGenerationError | None = None
    try:
        output, attempts = provider.generate_structured(
            system_prompt=POST_VISIT_SYSTEM_PROMPT,
            user_prompt=prompt,
            response_schema=PostVisitLLMOutput,
        )
        if [item.model_dump(mode="json") for item in output.medication_schedule] != expected_schedule:
            raise LLMGenerationError(
                "prescription_fidelity", "LLM medication schedule did not match prescription", attempts
            )
        source_text = " ".join(str(value or "") for value in note_data.values()).lower()
        if any(warning.lower() not in source_text for warning in output.warning_signs):
            raise LLMGenerationError(
                "prescription_fidelity", "LLM warning signs were not present in doctor notes", attempts
            )
        source = GenerationSource.LLM
        status = GenerationStatus.COMPLETED
    except LLMGenerationError as exc:
        error = exc
        attempts = exc.attempts
        output = fallback
        source = GenerationSource.DETERMINISTIC_FALLBACK
        status = GenerationStatus.FALLBACK
    except Exception:
        error = LLMGenerationError("unexpected_error", "LLM summary generation failed", 0)
        attempts = 0
        output = fallback
        source = GenerationSource.DETERMINISTIC_FALLBACK
        status = GenerationStatus.FALLBACK

    with session_factory() as db:
        summary = db.scalar(
            select(PostVisitSummary)
            .where(PostVisitSummary.appointment_id == appointment_id)
            .with_for_update()
        )
        if summary is None:
            return
        summary.status = status
        summary.attempt_count += attempts
        summary.failure_category = error.category if error else None
        summary.failure_message = error.safe_message if error else None
        summary.generated_at = datetime.now(timezone.utc)
        summary.historical_context_used = False
        summary.generation_source = source
        summary.patient_friendly_summary = output.patient_friendly_summary
        summary.medication_schedule = [
            item.model_dump(mode="json") for item in output.medication_schedule
        ]
        summary.follow_up_steps = output.follow_up_steps
        summary.warning_signs = output.warning_signs
        summary.safety_disclaimer = output.safety_disclaimer
        summary.review_status = ReviewStatus.PENDING_REVIEW
        summary.approved_content = None
        db.commit()


class VisitService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.appointments = AppointmentRepository(db)

    def complete(
        self,
        appointment_id: UUID,
        doctor: User,
        data: CompleteVisitRequest,
        *,
        now: datetime | None = None,
    ) -> ClinicalRecordPublic:
        appointment = self.appointments.get_appointment(appointment_id, lock=True)
        if appointment is None:
            raise VisitNotFoundError
        if appointment.doctor_profile.user_id != doctor.id:
            raise VisitPermissionError
        if appointment.status == AppointmentStatus.COMPLETED:
            existing = self._record(appointment_id)
            if existing and self._matches(existing, data):
                return existing
            raise VisitStateError
        current = now or datetime.now(timezone.utc)
        start = appointment.slot_start
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if start > current:
            raise VisitStateError
        if appointment.status not in {
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.RESCHEDULE_REQUIRED,
        }:
            raise VisitStateError

        note = ClinicalNote(
            appointment_id=appointment.id,
            doctor_user_id=doctor.id,
            started_at=current,
            completed_at=current,
            **data.clinical_note.model_dump(),
        )
        self.db.add(note)
        self.db.flush()
        prescription = Prescription(
            appointment_id=appointment.id,
            clinical_note_id=note.id,
            prescribing_doctor_user_id=doctor.id,
            general_instructions=data.prescription.general_instructions,
        )
        self.db.add(prescription)
        self.db.flush()
        for item in data.prescription.items:
            fields = item.model_dump(exclude={"reminder_times"})
            self.db.add(
                PrescriptionItem(
                    prescription_id=prescription.id,
                    reminder_times=_serialize_reminder_times(item.reminder_times),
                    **fields,
                )
            )
        self.db.flush()
        from app.services.notifications import reconcile_medication_schedules
        for item in prescription.items:
            reconcile_medication_schedules(self.db, item, appointment.patient_user_id)
        self.db.expire(prescription, ["items"])
        previous_status = appointment.status
        appointment.status = AppointmentStatus.COMPLETED
        self.appointments.create_history(
            appointment,
            previous_status=previous_status,
            new_status=AppointmentStatus.COMPLETED,
            actor_user_id=doctor.id,
            reason="Visit completed",
        )
        self.db.add(
            PostVisitSummary(
                appointment_id=appointment.id,
                status=GenerationStatus.PENDING,
                provider=settings.llm_provider,
                model_identifier=settings.llm_model,
                prompt_version=POST_VISIT_PROMPT_VERSION,
                attempt_count=0,
                historical_context_used=False,
                review_status=ReviewStatus.PENDING_REVIEW,
            )
        )
        self._replace_clinical_documents(appointment, note, prescription)
        self.db.commit()
        return self._record(appointment_id)  # type: ignore[return-value]

    def update_record(
        self, appointment_id: UUID, doctor: User, data: CompleteVisitRequest
    ) -> ClinicalRecordPublic:
        appointment = self.appointments.get_appointment(appointment_id, lock=True)
        if appointment is None:
            raise VisitNotFoundError
        if appointment.doctor_profile.user_id != doctor.id:
            raise VisitPermissionError
        if appointment.status != AppointmentStatus.COMPLETED:
            raise VisitStateError
        note = self.db.scalar(select(ClinicalNote).where(ClinicalNote.appointment_id == appointment_id))
        prescription = self.db.scalar(
            select(Prescription).where(Prescription.appointment_id == appointment_id)
        )
        if note is None or prescription is None:
            raise VisitNotFoundError
        for key, value in data.clinical_note.model_dump().items():
            setattr(note, key, value)
        prescription.general_instructions = data.prescription.general_instructions
        self.db.execute(delete(PrescriptionItem).where(PrescriptionItem.prescription_id == prescription.id))
        for item in data.prescription.items:
            fields = item.model_dump(exclude={"reminder_times"})
            self.db.add(PrescriptionItem(
                prescription_id=prescription.id,
                reminder_times=_serialize_reminder_times(item.reminder_times),
                **fields,
            ))
        self.db.flush()
        self.db.expire(prescription, ["items"])
        from app.services.notifications import reconcile_medication_schedules
        for item in prescription.items:
            reconcile_medication_schedules(self.db, item, appointment.patient_user_id)
        self._replace_clinical_documents(appointment, note, prescription)
        summary = self.db.scalar(
            select(PostVisitSummary).where(PostVisitSummary.appointment_id == appointment_id)
        )
        if summary:
            summary.status = GenerationStatus.RETRY_PENDING
            summary.review_status = ReviewStatus.PENDING_REVIEW
            summary.approved_content = None
        self.db.commit()
        return self._record(appointment_id)  # type: ignore[return-value]

    def get_record(self, appointment_id: UUID, doctor: User) -> ClinicalRecordPublic:
        appointment = self.appointments.get_appointment(appointment_id)
        if appointment is None or appointment.doctor_profile.user_id != doctor.id:
            raise VisitNotFoundError
        record = self._record(appointment_id)
        if record is None:
            raise VisitNotFoundError
        return record

    def add_prescription_item(
        self, appointment_id: UUID, doctor: User, data: PrescriptionItemInput
    ) -> PrescriptionItemPublic:
        appointment, note, prescription = self._editable_prescription(appointment_id, doctor)
        fields = data.model_dump(exclude={"reminder_times"})
        item = PrescriptionItem(
            prescription_id=prescription.id,
            reminder_times=_serialize_reminder_times(data.reminder_times),
            **fields,
        )
        self.db.add(item)
        self.db.flush()
        from app.services.notifications import reconcile_medication_schedules
        reconcile_medication_schedules(self.db, item, appointment.patient_user_id)
        self._replace_clinical_documents(appointment, note, prescription)
        self._mark_post_summary_for_regeneration(appointment_id)
        self.db.commit()
        return self._item_public(item)

    def update_prescription_item(
        self,
        appointment_id: UUID,
        prescription_item_id: UUID,
        doctor: User,
        data: PrescriptionItemUpdate,
    ) -> PrescriptionItemPublic:
        appointment, note, prescription = self._editable_prescription(appointment_id, doctor)
        item = self.db.get(PrescriptionItem, prescription_item_id)
        if item is None or item.prescription_id != prescription.id:
            raise VisitNotFoundError
        changes = data.model_dump(exclude_unset=True)
        if "reminder_times" in changes and changes["reminder_times"] is not None:
            changes["reminder_times"] = _serialize_reminder_times(changes["reminder_times"])
        for field, value in changes.items():
            setattr(item, field, value)
        if not item.medication_name.strip() or not item.dosage.strip():
            raise VisitStateError
        if item.end_date is not None and item.end_date < item.start_date:
            raise VisitStateError
        _validate_item_schedule(item)
        from app.services.notifications import reconcile_medication_schedules
        reconcile_medication_schedules(self.db, item, appointment.patient_user_id)
        self._replace_clinical_documents(appointment, note, prescription)
        self._mark_post_summary_for_regeneration(appointment_id)
        self.db.commit()
        return self._item_public(item)

    def delete_prescription_item(
        self, appointment_id: UUID, prescription_item_id: UUID, doctor: User
    ) -> None:
        appointment, note, prescription = self._editable_prescription(appointment_id, doctor)
        item = self.db.get(PrescriptionItem, prescription_item_id)
        if item is None or item.prescription_id != prescription.id:
            raise VisitNotFoundError
        self.db.delete(item)
        self.db.flush()
        self._replace_clinical_documents(appointment, note, prescription)
        self._mark_post_summary_for_regeneration(appointment_id)
        self.db.commit()

    def mark_regeneration(
        self, appointment_id: UUID, doctor: User, *, post: bool
    ) -> RegenerationAccepted:
        appointment = self.appointments.get_appointment(appointment_id)
        if appointment is None or appointment.doctor_profile.user_id != doctor.id:
            raise VisitNotFoundError
        model = PostVisitSummary if post else PreVisitSummary
        summary = self.db.scalar(
            select(model)
            .where(model.appointment_id == appointment_id)
            .with_for_update()
        )
        if summary is None:
            raise VisitNotFoundError
        accepted = RegenerationAccepted(
            appointment_id=appointment_id,
            status="retry_pending",
            should_start=summary.status
            not in {GenerationStatus.PENDING, GenerationStatus.RETRY_PENDING},
        )
        if summary.status in {GenerationStatus.PENDING, GenerationStatus.RETRY_PENDING}:
            self.db.commit()
            return accepted
        summary.status = GenerationStatus.RETRY_PENDING
        if post:
            summary.review_status = ReviewStatus.PENDING_REVIEW
            summary.approved_content = None
        self.db.commit()
        return accepted

    def approve(
        self, appointment_id: UUID, doctor: User, data: PostVisitApprovalRequest
    ) -> PostVisitSummaryPublic:
        appointment = self.appointments.get_appointment(appointment_id)
        if appointment is None or appointment.doctor_profile.user_id != doctor.id:
            raise VisitNotFoundError
        summary = self.db.scalar(
            select(PostVisitSummary)
            .where(PostVisitSummary.appointment_id == appointment_id)
            .with_for_update()
        )
        if summary is None or summary.status not in {GenerationStatus.COMPLETED, GenerationStatus.FALLBACK}:
            raise SummaryStateError
        approved = {
            "patient_friendly_summary": data.patient_friendly_summary or summary.patient_friendly_summary,
            "medication_schedule": summary.medication_schedule or [],
            "follow_up_steps": data.follow_up_steps if data.follow_up_steps is not None else summary.follow_up_steps or [],
            "warning_signs": data.warning_signs if data.warning_signs is not None else summary.warning_signs or [],
            "safety_disclaimer": summary.safety_disclaimer,
        }
        summary.review_status = ReviewStatus.APPROVED
        summary.reviewed_by_user_id = doctor.id
        summary.reviewed_at = datetime.now(timezone.utc)
        summary.approved_content = approved
        from app.models.notification import NotificationEventType
        from app.services.notifications import enqueue
        enqueue(self.db, event_type=NotificationEventType.POST_VISIT_APPROVED, recipient=appointment.patient, appointment_id=appointment.id, idempotency_key=f"post-visit-approved:{appointment.id}:{summary.updated_at.isoformat() if summary.updated_at else 'new'}", payload={"message": "Your post-visit summary is available in CareLoop."})
        approved_text = f"Visit summary: {approved['patient_friendly_summary']}. Follow-up: {'; '.join(approved['follow_up_steps'])}"
        document = self.db.scalar(select(CareDocument).where(
            CareDocument.appointment_id == appointment.id,
            CareDocument.document_type == CareDocumentType.APPROVED_POST_VISIT,
        ))
        if document:
            document.content = approved_text
        else:
            self.db.add(CareDocument(
                patient_user_id=appointment.patient_user_id,
                appointment_id=appointment.id,
                document_type=CareDocumentType.APPROVED_POST_VISIT,
                content=approved_text,
                event_date=appointment.slot_start,
                doctor_verified=True,
            ))
        self.db.commit()
        return post_summary_public(summary)

    def reject(self, appointment_id: UUID, doctor: User) -> PostVisitSummaryPublic:
        appointment = self.appointments.get_appointment(appointment_id)
        if appointment is None or appointment.doctor_profile.user_id != doctor.id:
            raise VisitNotFoundError
        summary = self.db.scalar(select(PostVisitSummary).where(PostVisitSummary.appointment_id == appointment_id))
        if summary is None:
            raise VisitNotFoundError
        summary.review_status = ReviewStatus.REJECTED
        summary.reviewed_by_user_id = doctor.id
        summary.reviewed_at = datetime.now(timezone.utc)
        summary.approved_content = None
        self.db.commit()
        return post_summary_public(summary)

    def _replace_clinical_documents(
        self, appointment: Appointment, note: ClinicalNote, prescription: Prescription
    ) -> None:
        note_content = (
            f"Diagnosis: {note.diagnosis or 'not recorded'}. Notes: {note.original_notes}. "
            f"Treatment plan: {note.treatment_plan or 'not recorded'}. "
            f"Follow-up: {note.follow_up_instructions}"
        )
        note_document = self.db.scalar(select(CareDocument).where(
            CareDocument.appointment_id == appointment.id,
            CareDocument.document_type == CareDocumentType.CLINICAL_NOTE,
        ))
        if note_document:
            note_document.content = note_content
        else:
            self.db.add(CareDocument(
                patient_user_id=appointment.patient_user_id,
                appointment_id=appointment.id,
                document_type=CareDocumentType.CLINICAL_NOTE,
                content=note_content,
                event_date=appointment.slot_start,
                doctor_verified=True,
            ))
        item_text = "; ".join(
            f"{item.medication_name} {item.dosage} {item.frequency_per_day} time(s) daily"
            for item in prescription.items
            if item.is_active
        ) or "No medication prescribed"
        prescription_document = self.db.scalar(select(CareDocument).where(
            CareDocument.appointment_id == appointment.id,
            CareDocument.document_type == CareDocumentType.PRESCRIPTION,
        ))
        if prescription_document:
            prescription_document.content = f"Prescription: {item_text}"
        else:
            self.db.add(CareDocument(
                patient_user_id=appointment.patient_user_id,
                appointment_id=appointment.id,
                document_type=CareDocumentType.PRESCRIPTION,
                content=f"Prescription: {item_text}",
                event_date=appointment.slot_start,
                doctor_verified=True,
            ))

    def _editable_prescription(
        self, appointment_id: UUID, doctor: User
    ) -> tuple[Appointment, ClinicalNote, Prescription]:
        appointment = self.appointments.get_appointment(appointment_id, lock=True)
        if appointment is None or appointment.doctor_profile.user_id != doctor.id:
            raise VisitNotFoundError
        if appointment.status != AppointmentStatus.COMPLETED:
            raise VisitStateError
        note = self.db.scalar(select(ClinicalNote).where(ClinicalNote.appointment_id == appointment_id))
        prescription = self.db.scalar(
            select(Prescription).where(Prescription.appointment_id == appointment_id)
        )
        if note is None or prescription is None:
            raise VisitNotFoundError
        return appointment, note, prescription

    def _mark_post_summary_for_regeneration(self, appointment_id: UUID) -> None:
        summary = self.db.scalar(
            select(PostVisitSummary).where(PostVisitSummary.appointment_id == appointment_id)
        )
        if summary is not None:
            summary.status = GenerationStatus.RETRY_PENDING
            summary.review_status = ReviewStatus.PENDING_REVIEW
            summary.approved_content = None

    @staticmethod
    def _item_public(item: PrescriptionItem) -> PrescriptionItemPublic:
        return PrescriptionItemPublic(
            id=item.id,
            medication_name=item.medication_name,
            dosage=item.dosage,
            route=item.route,
            frequency_per_day=item.frequency_per_day,
            reminder_times=sorted(item.reminder_times),
            start_date=item.start_date,
            end_date=item.end_date,
            food_instructions=item.food_instructions,
            additional_instructions=item.additional_instructions,
            is_active=item.is_active,
        )
    def _record(self, appointment_id: UUID) -> ClinicalRecordPublic | None:
        note = self.db.scalar(select(ClinicalNote).where(ClinicalNote.appointment_id == appointment_id))
        prescription = self.db.scalar(select(Prescription).where(Prescription.appointment_id == appointment_id))
        if note is None or prescription is None:
            return None
        return ClinicalRecordPublic(
            appointment_id=appointment_id,
            original_notes=note.original_notes,
            diagnosis=note.diagnosis,
            treatment_plan=note.treatment_plan,
            follow_up_instructions=note.follow_up_instructions,
            recommended_follow_up_date=note.recommended_follow_up_date,
            private_doctor_notes=note.private_doctor_notes,
            general_instructions=prescription.general_instructions,
            items=[PrescriptionItemPublic(
                id=item.id,
                medication_name=item.medication_name,
                dosage=item.dosage,
                route=item.route,
                frequency_per_day=item.frequency_per_day,
                reminder_times=sorted(item.reminder_times),
                start_date=item.start_date,
                end_date=item.end_date,
                food_instructions=item.food_instructions,
                additional_instructions=item.additional_instructions,
                is_active=item.is_active,
            ) for item in prescription.items],
            created_at=note.created_at,
            updated_at=note.updated_at,
            started_at=note.started_at,
            completed_at=note.completed_at,
        )

    @staticmethod
    def _matches(record: ClinicalRecordPublic, data: CompleteVisitRequest) -> bool:
        comparable = record.model_dump(exclude={
            "appointment_id", "created_at", "updated_at", "started_at", "completed_at",
            "private_doctor_notes", "items"
        })
        expected = data.clinical_note.model_dump(exclude={"private_doctor_notes"}) | {
            "general_instructions": data.prescription.general_instructions
        }
        items = [item.model_dump(exclude={"id"}) for item in record.items]
        expected_items = []
        for item in data.prescription.items:
            item_data = item.model_dump()
            item_data["reminder_times"] = _serialize_reminder_times(item.reminder_times)
            expected_items.append(item_data)
        return comparable == expected and items == expected_items


def pre_summary_public(db: Session, summary: PreVisitSummary) -> PreVisitSummaryPublic:
    source_rows = list(db.scalars(
        select(PreVisitSummarySource)
        .where(PreVisitSummarySource.pre_visit_summary_id == summary.id)
        .order_by(PreVisitSummarySource.rank_position)
    ))
    return PreVisitSummaryPublic(
        appointment_id=summary.appointment_id,
        status=summary.status,
        provider=summary.provider,
        model_identifier=summary.model_identifier,
        prompt_version=summary.prompt_version,
        attempt_count=summary.attempt_count,
        failure_category=summary.failure_category,
        failure_message=summary.failure_message,
        generated_at=summary.generated_at,
        historical_context_used=summary.historical_context_used,
        generation_source=summary.generation_source,
        urgency=summary.urgency,
        chief_complaint=summary.chief_complaint,
        suggested_questions=summary.suggested_questions,
        relevant_history_note=summary.relevant_history_note,
        safety_disclaimer=summary.safety_disclaimer,
        sources=[SummarySourcePublic(
            document_id=row.document.id,
            appointment_id=row.document.appointment_id,
            document_type=row.document.document_type.value,
            event_date=row.document.event_date,
            rank_position=row.rank_position,
            ranking_score=row.ranking_score,
        ) for row in source_rows],
    )


def post_summary_public(summary: PostVisitSummary) -> PostVisitSummaryPublic:
    return PostVisitSummaryPublic(
        appointment_id=summary.appointment_id,
        status=summary.status,
        provider=summary.provider,
        model_identifier=summary.model_identifier,
        prompt_version=summary.prompt_version,
        attempt_count=summary.attempt_count,
        failure_category=summary.failure_category,
        failure_message=summary.failure_message,
        generated_at=summary.generated_at,
        historical_context_used=summary.historical_context_used,
        generation_source=summary.generation_source,
        patient_friendly_summary=summary.patient_friendly_summary,
        medication_schedule=summary.medication_schedule,
        follow_up_steps=summary.follow_up_steps,
        warning_signs=summary.warning_signs,
        safety_disclaimer=summary.safety_disclaimer,
        review_status=summary.review_status,
        reviewed_by_user_id=summary.reviewed_by_user_id,
        reviewed_at=summary.reviewed_at,
        approved_content=summary.approved_content,
    )
