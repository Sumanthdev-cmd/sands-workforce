from datetime import datetime
from uuid import UUID
import hashlib
from sqlalchemy.exc import IntegrityError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MEETING_MODES = {"ONLINE", "OFFLINE", "HYBRID"}


class AppointmentCreateRequest(BaseModel):
    subject: str = Field(min_length=3, max_length=220)
    agenda: str = Field(min_length=3, max_length=5000)
    requested_start_at: datetime
    requested_end_at: datetime
    meeting_mode: str = "ONLINE"
    location: str | None = Field(default=None, max_length=500)
    reminder_minutes: int = Field(default=30, ge=0, le=10080)

    @field_validator("meeting_mode")
    @classmethod
    def normalize_mode(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in MEETING_MODES:
            raise ValueError(
                f"meeting_mode must be one of {sorted(MEETING_MODES)}"
            )
        return normalized

    @model_validator(mode="after")
    def validate_request(self):
        if self.requested_end_at <= self.requested_start_at:
            raise ValueError(
                "requested_end_at must be later than requested_start_at."
            )
        if self.meeting_mode == "OFFLINE" and not self.location:
            raise ValueError("Offline appointments require a location.")
        return self


class AppointmentApprovalRequest(BaseModel):
    approved_start_at: datetime | None = None
    approved_end_at: datetime | None = None
    meeting_mode: str | None = Field(default=None, max_length=20)
    meeting_url: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("meeting_mode")
    @classmethod
    def normalize_meeting_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().upper()

        if normalized not in {"ONLINE", "OFFLINE", "HYBRID"}:
            raise ValueError(
                "meeting_mode must be ONLINE, OFFLINE, or HYBRID."
            )

        return normalized

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.approved_start_at is not None
            and self.approved_end_at is not None
            and self.approved_end_at <= self.approved_start_at
        ):
            raise ValueError(
                "approved_end_at must be later than approved_start_at."
            )
        return self


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=5000)


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requester_employee_id: UUID
    subject: str
    agenda: str
    requested_start_at: datetime
    requested_end_at: datetime
    approved_start_at: datetime | None
    approved_end_at: datetime | None
    meeting_mode: str
    location: str | None
    meeting_url: str | None
    reminder_minutes: int
    status: str
    md_user_id: UUID | None
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    completed_at: datetime | None
    requester_employee_code: str | None = None
    requester_name: str | None = None
    created_at: datetime
    updated_at: datetime


class AppointmentActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    appointment_id: UUID
    actor_user_id: UUID
    action: str
    note: str | None
    extra_data: dict | None
    created_at: datetime
    updated_at: datetime


class DocumentApprovalCreateRequest(BaseModel):
    document_id: UUID | None = None
    approval_type: str = Field(
        default="GENERAL_APPROVAL",
        min_length=2,
        max_length=60,
    )
    title: str = Field(min_length=3, max_length=220)
    description: str = Field(min_length=3, max_length=5000)
    extra_data: dict | None = None

    @field_validator("approval_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().upper()


class DocumentApprovalDecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class DocumentApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID | None
    requester_user_id: UUID
    approval_type: str
    title: str
    description: str
    status: str
    approver_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    extra_data: dict | None
    document_title: str | None = None
    document_category: str | None = None
    requester_employee_code: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentApprovalActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    approval_request_id: UUID
    actor_user_id: UUID
    action: str
    note: str | None
    extra_data: dict | None
    created_at: datetime
    updated_at: datetime
