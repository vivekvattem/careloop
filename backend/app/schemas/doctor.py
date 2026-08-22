from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.user import UserRole


def _clean_required_text(value: str, field_name: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{field_name} cannot be blank")
    return cleaned


class DoctorProfileFields(BaseModel):
    specialisation: str = Field(min_length=1, max_length=120)
    qualifications: str = Field(default="", max_length=500)
    biography: str = Field(default="", max_length=5000)
    consultation_mode: Literal["in_person", "video", "hybrid"] = "in_person"
    location: str | None = Field(default=None, max_length=255)
    slot_duration_minutes: int = Field(default=30, ge=5, le=180)
    timezone: str = "Asia/Kolkata"
    is_available_for_booking: bool = True

    @field_validator("specialisation")
    @classmethod
    def validate_specialisation(cls, value: str) -> str:
        return _clean_required_text(value, "Specialisation")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone must be a valid IANA timezone") from exc
        return value


class DoctorProvisionRequest(DoctorProfileFields):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    initial_password: str = Field(min_length=10, max_length=128)

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, value: str) -> str:
        return _clean_required_text(value, "Full name")

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("initial_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if not any(character.islower() for character in value):
            raise ValueError("Password must include a lowercase letter")
        if not any(character.isupper() for character in value):
            raise ValueError("Password must include an uppercase letter")
        if not any(character.isdigit() for character in value):
            raise ValueError("Password must include a number")
        return value


class DoctorUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    specialisation: str | None = Field(default=None, min_length=1, max_length=120)
    qualifications: str | None = Field(default=None, max_length=500)
    biography: str | None = Field(default=None, max_length=5000)
    consultation_mode: Literal["in_person", "video", "hybrid"] | None = None
    location: str | None = Field(default=None, max_length=255)
    slot_duration_minutes: int | None = Field(default=None, ge=5, le=180)
    timezone: str | None = None
    is_available_for_booking: bool | None = None
    is_active: bool | None = None

    @field_validator("full_name", "specialisation")
    @classmethod
    def clean_nonblank_fields(cls, value: str | None) -> str | None:
        return _clean_required_text(value, "Value") if value is not None else None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Timezone must be a valid IANA timezone") from exc
        return value


class WorkingHourCreate(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def validate_order(self) -> "WorkingHourCreate":
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")
        return self


class WorkingHourUpdate(BaseModel):
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None

    @model_validator(mode="after")
    def validate_order_when_complete(self) -> "WorkingHourUpdate":
        if self.start_time is not None and self.end_time is not None:
            if self.start_time >= self.end_time:
                raise ValueError("Start time must be before end time")
        return self


class WorkingHourPublic(BaseModel):
    id: UUID
    day_of_week: int
    start_time: time
    end_time: time
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeaveCreate(BaseModel):
    leave_date: date
    reason: str | None = Field(default=None, max_length=500)


class LeaveAdmin(BaseModel):
    id: UUID
    leave_date: date
    reason: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DoctorAdmin(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    specialisation: str
    qualifications: str
    biography: str
    consultation_mode: str
    location: str | None
    slot_duration_minutes: int
    timezone: str
    is_available_for_booking: bool
    created_at: datetime
    updated_at: datetime
    working_hours: list[WorkingHourPublic] = []
    leaves: list[LeaveAdmin] = []


class DoctorAdminList(BaseModel):
    items: list[DoctorAdmin]
    page: int
    page_size: int
    total: int


class DoctorPublic(BaseModel):
    id: UUID
    full_name: str
    specialisation: str
    qualifications: str
    biography: str
    consultation_mode: str
    location: str | None
    slot_duration_minutes: int
    timezone: str


class DoctorPublicList(BaseModel):
    items: list[DoctorPublic]
    page: int
    page_size: int
    total: int


class DoctorSelf(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: EmailStr
    specialisation: str
    qualifications: str
    biography: str
    consultation_mode: str
    location: str | None
    slot_duration_minutes: int
    timezone: str
    is_available_for_booking: bool
    is_active: bool


class DoctorSchedule(BaseModel):
    timezone: str
    slot_duration_minutes: int
    working_hours: list[WorkingHourPublic]


class DoctorLeaveList(BaseModel):
    leaves: list[LeaveAdmin]


class Slot(BaseModel):
    start: datetime
    end: datetime


class SlotPreview(BaseModel):
    doctor_id: UUID
    date: date
    timezone: str
    availability: Literal[
        "available", "doctor_inactive", "on_leave", "no_working_hours"
    ]
    slots: list[Slot]
    disclaimer: str = "Preview only; appointment booking and slot holds are not implemented yet."

