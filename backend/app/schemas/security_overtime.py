from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.employees import validate_strong_password


class PasswordResetRequestCreate(BaseModel):
    employee_id: UUID
    reason: str = Field(min_length=5, max_length=2000)


class PasswordResetDecision(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_rejection_note(self):
        if not self.approved and not (self.note or "").strip():
            raise ValueError("A rejection reason is required.")
        return self


class PasswordResetComplete(BaseModel):
    temporary_password: str = Field(min_length=10, max_length=128)

    @model_validator(mode="after")
    def validate_password(self):
        self.temporary_password = validate_strong_password(self.temporary_password)
        return self


class PasswordResetRequestResponse(BaseModel):
    id: UUID
    target_employee_id: UUID
    target_employee_code: str
    target_employee_name: str
    requested_by_user_id: UUID
    requested_by_employee_code: str
    reason: str
    status: str
    requested_at: datetime
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    approval_expires_at: datetime | None
    completed_by_user_id: UUID | None
    completed_at: datetime | None


class LateAttendanceActionResponse(BaseModel):
    id: UUID
    employee_id: UUID
    employee_code: str
    employee_name: str
    month_start: date
    qualifying_late_days: int
    half_day_deduction_required: bool
    half_day_triggered_at: datetime | None
    salary_hold_required: bool
    salary_hold_triggered_at: datetime | None
    hold_released_by_user_id: UUID | None
    hold_released_at: datetime | None
    hold_release_note: str | None


class LateSalaryHoldRelease(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


class OvertimeClaimCreate(BaseModel):
    work_date: date
    reason: str = Field(min_length=5, max_length=5000)


class OvertimeEvidenceAttach(BaseModel):
    document_id: UUID


class OvertimeAdminReview(BaseModel):
    approved: bool
    proposed_amount: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_review(self):
        if self.approved and (self.proposed_amount is None or self.proposed_amount <= 0):
            raise ValueError("Enter a positive OT benefit amount.")
        if not self.approved and not (self.note or "").strip():
            raise ValueError("A rejection reason is required.")
        return self


class OvertimeMdDecision(BaseModel):
    approved: bool
    approved_amount: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_decision(self):
        if self.approved and (self.approved_amount is None or self.approved_amount <= 0):
            raise ValueError("Enter the final positive OT benefit amount.")
        if not self.approved and not (self.note or "").strip():
            raise ValueError("A rejection reason is required.")
        return self


class AttendanceWorkLookupResponse(BaseModel):
    employee_id: UUID
    employee_code: str
    employee_name: str
    work_date: date
    attendance_record_id: UUID | None
    status: str | None
    check_in_at: datetime | None
    check_out_at: datetime | None
    worked_minutes: int
    scheduled_minutes: int
    overtime_minutes: int
    eligible_for_overtime: bool
    message: str


class OvertimeClaimResponse(BaseModel):
    id: UUID
    employee_id: UUID
    employee_code: str
    employee_name: str
    attendance_record_id: UUID
    work_date: date
    check_in_at: datetime
    check_out_at: datetime
    worked_minutes: int
    scheduled_minutes: int
    overtime_minutes: int
    reason: str
    evidence_document_id: UUID | None
    status: str
    submitted_at: datetime | None
    admin_verified_by_user_id: UUID | None
    admin_verified_at: datetime | None
    admin_note: str | None
    admin_proposed_amount: float | None
    md_decided_by_user_id: UUID | None
    md_decided_at: datetime | None
    md_note: str | None
    approved_amount: float | None
    payroll_run_id: UUID | None
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime
