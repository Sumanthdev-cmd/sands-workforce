from datetime import date, datetime
from math import ceil
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SalaryAdvanceCreateRequest(BaseModel):
    requested_amount: float = Field(ge=0.01, le=100_000_000)
    installment_amount: float = Field(ge=0.01, le=100_000_000)
    recovery_months: int = Field(ge=1, le=120)
    reason: str = Field(min_length=5, max_length=5000)
    currency: str = Field(default="INR", min_length=3, max_length=10)

    @model_validator(mode="after")
    def validate_recovery_plan(self):
        if self.installment_amount > self.requested_amount:
            raise ValueError(
                "installment_amount cannot be greater than requested_amount."
            )
        expected_months = ceil(
            round(self.requested_amount, 2) / round(self.installment_amount, 2)
        )
        if self.recovery_months != expected_months:
            raise ValueError(
                "recovery_months must match the requested amount and monthly "
                f"deduction. Use {expected_months} month(s)."
            )
        return self


class SalaryAdvanceDecisionRequest(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=5000)


class SalaryAdvanceDisbursementRequest(BaseModel):
    payment_reference: str = Field(min_length=2, max_length=200)
    note: str | None = Field(default=None, max_length=5000)


class SalaryAdvanceCancelRequest(BaseModel):
    note: str = Field(min_length=3, max_length=5000)


class SalaryAdvanceRecoveryResponse(BaseModel):
    id: UUID
    payroll_run_id: UUID
    amount: float
    recovered_at: datetime


class SalaryAdvanceResponse(BaseModel):
    id: UUID
    payee_type: str = "EMPLOYEE"
    employee_id: UUID | None = None
    employee_code: str
    employee_name: str
    vendor_id: UUID | None = None
    vendor_code: str | None = None
    vendor_name: str | None = None
    requested_amount: float
    installment_amount: float
    recovery_months: int
    recovered_amount: float
    remaining_amount: float
    installments_completed: int
    currency: str
    reason: str
    status: str
    requested_at: datetime
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    disbursed_by_user_id: UUID | None
    disbursed_at: datetime | None
    disbursement_reference: str | None
    disbursement_note: str | None
    recovery_start_date: date | None
    cancelled_at: datetime | None
    cancellation_note: str | None
    recoveries: list[SalaryAdvanceRecoveryResponse]
    created_at: datetime
    updated_at: datetime
