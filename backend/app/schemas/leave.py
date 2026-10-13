from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LeaveTypeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=100)
    description: str | None = None
    days_per_year: float = Field(default=0, ge=0, le=365)
    is_paid: bool = True
    document_required_after_days: int | None = Field(default=None, ge=1, le=365)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class LeaveTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name: str
    description: str | None
    days_per_year: float
    is_paid: bool
    document_required_after_days: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LeaveBalanceOut(BaseModel):
    leave_type_id: UUID
    leave_type_code: str
    leave_type_name: str
    year: int
    allocated_days: float
    used_days: float
    pending_days: float
    available_days: float


class LeaveRequestCreate(BaseModel):
    leave_type_id: UUID
    start_date: date
    end_date: date
    reason: str = Field(min_length=3, max_length=5000)
    attachment_urls: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date")
        return self


class LeaveRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    employee_id: UUID
    leave_type_id: UUID
    start_date: date
    end_date: date
    total_days: float
    reason: str
    attachment_urls: list[str] | None
    status: str
    approver_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime


class PendingLeaveOut(LeaveRequestOut):
    employee_code: str
    employee_name: str
    leave_type_code: str
    leave_type_name: str


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class HolidayCreate(BaseModel):
    holiday_date: date
    name: str = Field(min_length=2, max_length=150)
    holiday_type: str = "PUBLIC"
    is_optional: bool = False

    @field_validator("holiday_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().upper()


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    holiday_date: date
    name: str
    holiday_type: str
    is_optional: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RegularizationCreate(BaseModel):
    attendance_date: date
    requested_check_in_at: datetime | None = None
    requested_check_out_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=5000)

    @model_validator(mode="after")
    def validate_times(self):
        if self.requested_check_in_at is None and self.requested_check_out_at is None:
            raise ValueError("At least one corrected time is required")
        if self.requested_check_in_at and self.requested_check_out_at and self.requested_check_out_at < self.requested_check_in_at:
            raise ValueError("Check-out cannot be earlier than check-in")
        return self


class RegularizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    employee_id: UUID
    attendance_date: date
    requested_check_in_at: datetime | None
    requested_check_out_at: datetime | None
    reason: str
    status: str
    approver_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime


class PendingRegularizationOut(RegularizationOut):
    employee_code: str
    employee_name: str
