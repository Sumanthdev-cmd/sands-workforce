from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TASK_TYPES = {"TASK", "ROUTINE", "FIELD_VISIT"}
PRIORITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}
RECURRENCE_TYPES = {"NONE", "DAILY", "WEEKLY", "MONTHLY"}


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = None
    task_type: str = "TASK"
    priority: str = "MEDIUM"
    geofence_id: UUID | None = None
    starts_at: datetime | None = None
    due_at: datetime | None = None
    recurrence_type: str = "NONE"
    recurrence_interval: int = Field(default=1, ge=1, le=365)
    recurrence_days: list[int] | None = None
    location_required: bool = False
    questionnaire_schema: dict | None = None

    @field_validator("task_type", "priority", "recurrence_type")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, value: str) -> str:
        if value not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {sorted(TASK_TYPES)}")
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        if value not in PRIORITIES:
            raise ValueError(f"priority must be one of {sorted(PRIORITIES)}")
        return value

    @field_validator("recurrence_type")
    @classmethod
    def validate_recurrence_type(cls, value: str) -> str:
        if value not in RECURRENCE_TYPES:
            raise ValueError(f"recurrence_type must be one of {sorted(RECURRENCE_TYPES)}")
        return value

    @field_validator("recurrence_days")
    @classmethod
    def validate_days(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("recurrence_days values must be between 0 and 6")
        return sorted(set(value))

    @model_validator(mode="after")
    def validate_task(self):
        if self.starts_at and self.due_at and self.due_at < self.starts_at:
            raise ValueError("due_at cannot be earlier than starts_at")
        if self.location_required and self.geofence_id is None:
            raise ValueError("geofence_id is required when location_required is true")
        return self


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    priority: str | None = None
    starts_at: datetime | None = None
    due_at: datetime | None = None
    status: str | None = None
    is_active: bool | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    geofence_id: UUID | None
    title: str
    description: str | None
    task_type: str
    priority: str
    recurrence_type: str
    recurrence_interval: int
    recurrence_days: list[int] | None
    starts_at: datetime | None
    due_at: datetime | None
    location_required: bool
    questionnaire_schema: dict | None
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TaskAssignmentCreateRequest(BaseModel):
    employee_ids: list[UUID] = Field(min_length=1, max_length=500)
    scheduled_for: date = Field(default_factory=date.today)
    due_at: datetime | None = None


class TaskAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    task_id: UUID
    employee_id: UUID
    scheduled_for: date
    due_at: datetime | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    completion_note: str | None
    evidence_urls: list[str] | None
    completion_latitude: float | None
    completion_longitude: float | None
    created_at: datetime
    updated_at: datetime

    display_status: str | None = None
    overdue_by_seconds: int = 0
    completed_late_by_seconds: int = 0
    leave_conflict: bool = False
    leave_conflict_reason: str | None = None


class MyTaskResponse(TaskAssignmentResponse):
    task_title: str
    task_description: str | None
    task_type: str
    priority: str
    location_required: bool
    geofence_id: UUID | None
    questionnaire_schema: dict | None


class AssignmentProgressRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class AssignmentCompleteRequest(BaseModel):
    completion_note: str | None = Field(default=None, max_length=5000)
    evidence_urls: list[str] = Field(default_factory=list, max_length=20)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class QuestionnaireSubmitRequest(BaseModel):
    answers: dict
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_final: bool = True


class QuestionnaireSubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    assignment_id: UUID
    employee_id: UUID
    answers: dict
    submitted_at: datetime
    latitude: float | None
    longitude: float | None
    is_final: bool
    created_at: datetime
    updated_at: datetime


class TaskProgressLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    assignment_id: UUID
    actor_user_id: UUID
    action: str
    note: str | None
    latitude: float | None
    longitude: float | None
    extra_data: dict | None
    created_at: datetime
    updated_at: datetime


class AdminAssignmentResponse(TaskAssignmentResponse):
    employee_code: str
    employee_name: str
    task_title: str
    task_type: str
    priority: str
