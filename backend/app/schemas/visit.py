from datetime import date, datetime, time
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.visit import (
    GenerationSource,
    GenerationStatus,
    ReviewStatus,
    Urgency,
)


class StrictOutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreVisitLLMOutput(StrictOutputModel):
    urgency: Urgency
    chief_complaint: str = Field(min_length=1, max_length=200)
    suggested_questions: list[str] = Field(min_length=3, max_length=3)
    relevant_history_note: str | None
    safety_disclaimer: str = Field(min_length=1, max_length=500)


class MedicationScheduleOutput(StrictOutputModel):
    medication_name: str
    dosage: str
    route: str | None
    frequency_per_day: int
    reminder_times: list[str]
    start_date: date
    end_date: date | None
    food_instructions: str | None
    additional_instructions: str | None


class PostVisitLLMOutput(StrictOutputModel):
    patient_friendly_summary: str = Field(min_length=1, max_length=5000)
    medication_schedule: list[MedicationScheduleOutput]
    follow_up_steps: list[str]
    warning_signs: list[str]
    safety_disclaimer: str = Field(min_length=1, max_length=500)


class PrescriptionItemInput(BaseModel):
    medication_name: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=120)
    route: str | None = Field(default=None, max_length=80)
    frequency_per_day: int = Field(ge=1, le=24)
    reminder_times: list[time] = Field(default_factory=list, max_length=24)
    start_date: date
    end_date: date | None = None
    food_instructions: str | None = Field(default=None, max_length=255)
    additional_instructions: str | None = Field(default=None, max_length=2000)
    is_active: bool = True

    @field_validator("reminder_times", mode="before")
    @classmethod
    def reminder_times_are_hhmm(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        for reminder in value:
            if isinstance(reminder, str) and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", reminder):
                raise ValueError("Reminder times must use HH:MM 24-hour format")
        return value

    @field_validator("medication_name", "dosage")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_schedule(self) -> "PrescriptionItemInput":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        if len(set(self.reminder_times)) != len(self.reminder_times):
            raise ValueError("Reminder times must be unique")
        if len(self.reminder_times) > self.frequency_per_day:
            raise ValueError("Reminder times cannot exceed frequency per day")
        return self


class PrescriptionInput(BaseModel):
    general_instructions: str | None = Field(default=None, max_length=2000)
    items: list[PrescriptionItemInput] = Field(default_factory=list, max_length=30)


class ClinicalNoteInput(BaseModel):
    original_notes: str = Field(min_length=5, max_length=10000)
    diagnosis: str | None = Field(default=None, max_length=2000)
    treatment_plan: str | None = Field(default=None, max_length=5000)
    follow_up_instructions: str = Field(min_length=2, max_length=5000)
    recommended_follow_up_date: date | None = None
    private_doctor_notes: str | None = Field(default=None, max_length=10000)


class CompleteVisitRequest(BaseModel):
    clinical_note: ClinicalNoteInput
    prescription: PrescriptionInput


class UpdateClinicalRecordRequest(CompleteVisitRequest):
    pass


class PrescriptionItemPublic(PrescriptionItemInput):
    id: UUID
    reminder_times: list[str]


class ClinicalRecordPublic(BaseModel):
    appointment_id: UUID
    original_notes: str
    diagnosis: str | None
    treatment_plan: str | None
    follow_up_instructions: str
    recommended_follow_up_date: date | None
    private_doctor_notes: str | None
    general_instructions: str | None
    items: list[PrescriptionItemPublic]
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class SummaryMetadataPublic(BaseModel):
    status: GenerationStatus
    provider: str
    model_identifier: str
    prompt_version: str
    attempt_count: int
    failure_category: str | None
    failure_message: str | None
    generated_at: datetime | None
    historical_context_used: bool
    generation_source: GenerationSource | None


class SummarySourcePublic(BaseModel):
    document_id: UUID
    appointment_id: UUID
    document_type: str
    event_date: datetime
    rank_position: int
    ranking_score: float


class PreVisitSummaryPublic(SummaryMetadataPublic):
    appointment_id: UUID
    urgency: Urgency | None
    chief_complaint: str | None
    suggested_questions: list[str] | None
    relevant_history_note: str | None
    safety_disclaimer: str | None
    sources: list[SummarySourcePublic] = Field(default_factory=list)


class PostVisitSummaryPublic(SummaryMetadataPublic):
    appointment_id: UUID
    patient_friendly_summary: str | None
    medication_schedule: list[dict] | None
    follow_up_steps: list[str] | None
    warning_signs: list[str] | None
    safety_disclaimer: str | None
    review_status: ReviewStatus
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    approved_content: dict | None


class PostVisitApprovalRequest(BaseModel):
    patient_friendly_summary: str | None = Field(default=None, min_length=1, max_length=5000)
    follow_up_steps: list[str] | None = Field(default=None, max_length=30)
    warning_signs: list[str] | None = Field(default=None, max_length=30)


class PatientPostVisitPublic(BaseModel):
    appointment_id: UUID
    availability: Literal["awaiting_doctor_review", "approved"]
    generation_source: GenerationSource | None
    approved_content: dict | None


class PrescriptionItemUpdate(BaseModel):
    medication_name: str | None = Field(default=None, min_length=1, max_length=200)
    dosage: str | None = Field(default=None, min_length=1, max_length=120)
    route: str | None = Field(default=None, max_length=80)
    frequency_per_day: int | None = Field(default=None, ge=1, le=24)
    reminder_times: list[time] | None = Field(default=None, max_length=24)
    start_date: date | None = None
    end_date: date | None = None
    food_instructions: str | None = Field(default=None, max_length=255)
    additional_instructions: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None

    @field_validator("reminder_times", mode="before")
    @classmethod
    def reminder_times_are_hhmm(cls, value: object) -> object:
        return PrescriptionItemInput.reminder_times_are_hhmm(value)

    @model_validator(mode="after")
    def validate_provided_schedule(self) -> "PrescriptionItemUpdate":
        if self.end_date is not None and self.start_date is not None and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        if self.reminder_times is not None:
            if len(set(self.reminder_times)) != len(self.reminder_times):
                raise ValueError("Reminder times must be unique")
            if self.frequency_per_day is not None and len(self.reminder_times) > self.frequency_per_day:
                raise ValueError("Reminder times cannot exceed frequency per day")
        return self


class RegenerationAccepted(BaseModel):
    appointment_id: UUID
    status: Literal["retry_pending"]
    should_start: bool = Field(default=True, exclude=True)
