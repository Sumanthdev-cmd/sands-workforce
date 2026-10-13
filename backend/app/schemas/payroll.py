from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SalaryStructureCreateRequest(BaseModel):
    effective_from: date
    basic_salary: float = Field(ge=0)
    hra: float = Field(default=0, ge=0)
    conveyance_allowance: float = Field(default=0, ge=0)
    other_allowance: float = Field(default=0, ge=0)
    daily_allowance: float = Field(default=0, ge=0)
    fixed_deduction: float = Field(default=0, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=10)


class SalaryRevisionRequest(SalaryStructureCreateRequest):
    reason: str = Field(min_length=3, max_length=5000)


class SalaryStructureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    effective_from: date
    basic_salary: float
    hra: float
    conveyance_allowance: float
    other_allowance: float
    daily_allowance: float
    fixed_deduction: float
    currency: str
    is_active: bool
    gross_monthly_salary: float
    net_monthly_after_fixed_deduction: float
    created_at: datetime
    updated_at: datetime


class SalaryHoldCreateRequest(BaseModel):
    hold_from: date
    hold_to: date | None = None
    reason: str = Field(min_length=3, max_length=5000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.hold_to is not None and self.hold_to < self.hold_from:
            raise ValueError("hold_to cannot be earlier than hold_from.")
        return self


class SalaryHoldReleaseRequest(BaseModel):
    release_note: str | None = Field(default=None, max_length=5000)


class SalaryHoldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    hold_from: date
    hold_to: date | None
    reason: str
    is_active: bool
    created_by_user_id: UUID
    released_by_user_id: UUID | None
    released_at: datetime | None
    release_note: str | None
    created_at: datetime
    updated_at: datetime


class PayrollRunCreateRequest(BaseModel):
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end cannot be earlier than period_start.")
        return self


class PayrollRunSubmitRequest(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class PayrollRunApprovalRequest(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class PayrollRunReturnRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=5000)


class PayrollRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    period_start: date
    period_end: date
    status: str
    total_employees: int
    total_vendors: int
    vendor_total_gross: float
    vendor_total_deductions: float
    vendor_total_net: float
    total_gross: float
    total_deductions: float
    total_net: float
    finalized_by_user_id: UUID | None
    finalized_at: datetime | None
    submitted_by_user_id: UUID | None
    submitted_at: datetime | None
    submission_note: str | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    approval_note: str | None
    returned_by_user_id: UUID | None
    returned_at: datetime | None
    return_note: str | None
    created_at: datetime
    updated_at: datetime


class PayrollItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payroll_run_id: UUID
    employee_id: UUID
    salary_structure_id: UUID
    working_days: float
    payable_days: float
    absent_days: float
    basic_earned: float
    hra_earned: float
    conveyance_earned: float
    other_allowance_earned: float
    daily_allowance_earned: float
    gross_earned: float
    loss_of_pay_deduction: float
    fixed_deduction: float
    other_deductions: float
    salary_advance_deduction: float
    overtime_benefit: float
    net_salary: float
    is_held: bool
    hold_reason: str | None
    calculation_details: dict | None
    payslip_number: str
    created_at: datetime
    updated_at: datetime


class AdminPayrollItemResponse(PayrollItemResponse):
    employee_code: str
    employee_name: str
    bank_name: str | None
    bank_ifsc: str | None
    bank_account_number: str | None


class VendorSalaryStructureRequest(BaseModel):
    effective_from: date
    basic_salary: float = Field(ge=0)
    hra: float = Field(default=0, ge=0)
    conveyance_allowance: float = Field(default=0, ge=0)
    other_allowance: float = Field(default=0, ge=0)
    daily_allowance: float = Field(default=0, ge=0)
    fixed_deduction: float = Field(default=0, ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=10)
    reason: str | None = Field(default=None, max_length=5000)


class VendorSalaryStructureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vendor_id: UUID
    effective_from: date
    monthly_salary: float
    basic_salary: float
    hra: float
    conveyance_allowance: float
    other_allowance: float
    daily_allowance: float
    gross_monthly_salary: float
    fixed_deduction: float
    currency: str
    revision_reason: str | None
    is_active: bool
    net_monthly_salary: float
    created_at: datetime
    updated_at: datetime


class VendorClosureCreateRequest(BaseModel):
    closure_date: date
    reason: str = Field(min_length=3, max_length=5000)


class VendorClosureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    closure_date: date
    reason: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class VendorPayrollItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payroll_run_id: UUID
    vendor_id: UUID
    vendor_salary_structure_id: UUID
    vendor_code: str
    vendor_name: str
    outlet_names: list[str]
    working_days: float
    payable_days: float
    absent_days: float
    basic_earned: float
    hra_earned: float
    conveyance_earned: float
    other_allowance_earned: float
    daily_allowance_earned: float
    gross_earned: float
    fixed_deduction: float
    other_deductions: float
    salary_advance_deduction: float
    net_salary: float
    calculation_details: dict | None
    payslip_number: str
    currency: str
    created_at: datetime
    updated_at: datetime


class MyPayslipResponse(PayrollItemResponse):
    period_start: date
    period_end: date
    employee_code: str
    employee_name: str
    currency: str
