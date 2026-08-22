from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.appointment import AppointmentStatus, HoldStatus


class HoldCreate(BaseModel):
    doctor_id: UUID
    slot_start: datetime

    @field_validator("slot_start")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Slot start must include a timezone offset")
        return value


class HoldResponse(BaseModel):
    hold_token: str
    hold_id: UUID
    doctor_id: UUID
    slot_start: datetime
    slot_end: datetime
    expires_at: datetime
    remaining_seconds: int
    status: HoldStatus


class SymptomInput(BaseModel):
    chief_complaint: str = Field(min_length=2, max_length=200)
    symptom_description: str = Field(min_length=5, max_length=5000)
    duration: str = Field(min_length=1, max_length=120)
    severity: int = Field(ge=1, le=10)
    existing_conditions: str | None = Field(default=None, max_length=5000)
    current_medications: str | None = Field(default=None, max_length=5000)


class AppointmentCreate(BaseModel):
    hold_token: str = Field(min_length=20, max_length=200)
    symptoms: SymptomInput


class CancellationRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


class RescheduleRequest(BaseModel):
    new_hold_token: str = Field(min_length=20, max_length=200)
    reason: str | None = Field(default=None, max_length=500)


class SymptomPublic(BaseModel):
    chief_complaint: str
    symptom_description: str
    duration: str
    severity: int
    existing_conditions: str | None
    current_medications: str | None


class StatusHistoryPublic(BaseModel):
    id: UUID
    previous_status: AppointmentStatus | None
    new_status: AppointmentStatus
    actor_user_id: UUID | None
    reason: str | None
    created_at: datetime


class AppointmentListItem(BaseModel):
    id: UUID
    patient_user_id: UUID
    doctor_id: UUID
    doctor_name: str
    patient_name: str
    slot_start: datetime
    slot_end: datetime
    status: AppointmentStatus
    cancellation_reason: str | None
    rescheduled_from_id: UUID | None
    created_at: datetime


class AppointmentDetail(AppointmentListItem):
    symptoms: SymptomPublic | None
    history: list[StatusHistoryPublic]


class AppointmentList(BaseModel):
    items: list[AppointmentListItem]
    page: int
    page_size: int
    total: int


class LeaveConflictItem(BaseModel):
    appointment_id: UUID
    slot_start: datetime
    slot_end: datetime
    status: AppointmentStatus


class LeaveConflictPreview(BaseModel):
    doctor_id: UUID
    date: date
    affected_count: int
    appointments: list[LeaveConflictItem]


class LeaveApplyResult(BaseModel):
    id: UUID
    leave_date: date
    reason: str | None
    created_at: datetime
    affected_count: int
    affected_appointment_ids: list[UUID]
