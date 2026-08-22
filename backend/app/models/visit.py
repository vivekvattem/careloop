import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.appointment import Appointment
from app.models.user import User


def enum_values(enum_type: type[enum.Enum]) -> list[str]:
    return [str(item.value) for item in enum_type]


class GenerationStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FALLBACK = "fallback"
    RETRY_PENDING = "retry_pending"
    FAILED = "failed"


class GenerationSource(str, enum.Enum):
    LLM = "llm"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


class Urgency(str, enum.Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class ReviewStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class CareDocumentType(str, enum.Enum):
    SYMPTOMS = "symptoms"
    CLINICAL_NOTE = "clinical_note"
    PRESCRIPTION = "prescription"
    APPROVED_POST_VISIT = "approved_post_visit"


class ClinicalNote(TimestampMixin, Base):
    __tablename__ = "clinical_notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    doctor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    original_notes: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    treatment_plan: Mapped[str | None] = mapped_column(Text)
    follow_up_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_follow_up_date: Mapped[date | None] = mapped_column(Date)
    private_doctor_notes: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    appointment: Mapped[Appointment] = relationship()
    doctor: Mapped[User] = relationship()


class Prescription(TimestampMixin, Base):
    __tablename__ = "prescriptions"
    __table_args__ = (
        UniqueConstraint("clinical_note_id", name="uq_prescriptions_clinical_note_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    clinical_note_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinical_notes.id", ondelete="CASCADE"), nullable=False
    )
    prescribing_doctor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    general_instructions: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["PrescriptionItem"]] = relationship(
        back_populates="prescription", cascade="all, delete-orphan", order_by="PrescriptionItem.id"
    )


class PrescriptionItem(TimestampMixin, Base):
    __tablename__ = "prescription_items"
    __table_args__ = (
        CheckConstraint("frequency_per_day BETWEEN 1 AND 24", name="frequency_range"),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="valid_date_range"),
        CheckConstraint("length(trim(medication_name)) > 0", name="medication_name_nonblank"),
        CheckConstraint("length(trim(dosage)) > 0", name="dosage_nonblank"),
        Index("ix_prescription_items_prescription", "prescription_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    prescription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False
    )
    medication_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dosage: Mapped[str] = mapped_column(String(120), nullable=False)
    route: Mapped[str | None] = mapped_column(String(80))
    frequency_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    reminder_times: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    food_instructions: Mapped[str | None] = mapped_column(String(255))
    additional_instructions: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    prescription: Mapped[Prescription] = relationship(back_populates="items")


class SummaryMetadataMixin:
    status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus, name="generation_status", values_callable=enum_values),
        default=GenerationStatus.PENDING,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(String(255))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    historical_context_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generation_source: Mapped[GenerationSource | None] = mapped_column(
        Enum(GenerationSource, name="generation_source", values_callable=enum_values)
    )


class PreVisitSummary(SummaryMetadataMixin, TimestampMixin, Base):
    __tablename__ = "pre_visit_summaries"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    urgency: Mapped[Urgency | None] = mapped_column(
        Enum(Urgency, name="summary_urgency", values_callable=enum_values)
    )
    chief_complaint: Mapped[str | None] = mapped_column(String(200))
    suggested_questions: Mapped[list[str] | None] = mapped_column(JSON)
    relevant_history_note: Mapped[str | None] = mapped_column(Text)
    safety_disclaimer: Mapped[str | None] = mapped_column(Text)


class PostVisitSummary(SummaryMetadataMixin, TimestampMixin, Base):
    __tablename__ = "post_visit_summaries"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    patient_friendly_summary: Mapped[str | None] = mapped_column(Text)
    medication_schedule: Mapped[list[dict] | None] = mapped_column(JSON)
    follow_up_steps: Mapped[list[str] | None] = mapped_column(JSON)
    warning_signs: Mapped[list[str] | None] = mapped_column(JSON)
    safety_disclaimer: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status", values_callable=enum_values),
        default=ReviewStatus.PENDING_REVIEW,
        nullable=False,
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_content: Mapped[dict | None] = mapped_column(JSON)


class CareDocument(Base):
    __tablename__ = "care_documents"
    __table_args__ = (
        Index("ix_care_documents_patient_event", "patient_user_id", "event_date"),
        Index("ix_care_documents_appointment", "appointment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    document_type: Mapped[CareDocumentType] = mapped_column(
        Enum(CareDocumentType, name="care_document_type", values_callable=enum_values),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doctor_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PreVisitSummarySource(Base):
    __tablename__ = "pre_visit_summary_sources"
    __table_args__ = (
        UniqueConstraint(
            "pre_visit_summary_id", "care_document_id", name="uq_pre_visit_summary_sources_pair"
        ),
        CheckConstraint("rank_position BETWEEN 1 AND 3", name="rank_position_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pre_visit_summary_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pre_visit_summaries.id", ondelete="CASCADE"), nullable=False
    )
    care_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("care_documents.id", ondelete="CASCADE"), nullable=False
    )
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    ranking_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[CareDocument] = relationship(lazy="joined")
