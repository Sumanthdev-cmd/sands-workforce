from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CLAIM_TYPES = {"TA_DA", "GENERAL_EXPENSE"}
EXPENSE_CATEGORIES = {
    "TRAVEL",
    "DAILY_ALLOWANCE",
    "LODGING",
    "FOOD",
    "FUEL",
    "TOLL",
    "PARKING",
    "LOCAL_TRANSPORT",
    "OTHER",
}


class ExpenseItemInput(BaseModel):
    expense_date: date
    category: str
    description: str = Field(min_length=2, max_length=2000)
    quantity: float = Field(default=1, gt=0)
    rate: float = Field(default=0, ge=0)
    amount: float | None = Field(default=None, ge=0)
    evidence_urls: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in EXPENSE_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(EXPENSE_CATEGORIES)}")
        return value

    @model_validator(mode="after")
    def calculate_amount(self):
        calculated = round(self.quantity * self.rate, 2)
        if self.amount is None:
            self.amount = calculated
        elif calculated > 0 and abs(self.amount - calculated) > 0.01:
            raise ValueError("amount must equal quantity multiplied by rate")
        return self


class ExpenseClaimCreateRequest(BaseModel):
    claim_type: str = "TA_DA"
    title: str = Field(min_length=3, max_length=200)
    purpose: str = Field(min_length=3, max_length=5000)
    travel_start_date: date | None = None
    travel_end_date: date | None = None
    origin: str | None = Field(default=None, max_length=200)
    destination: str | None = Field(default=None, max_length=200)
    currency: str = Field(default="INR", min_length=3, max_length=10)
    evidence_urls: list[str] = Field(default_factory=list, max_length=30)
    items: list[ExpenseItemInput] = Field(min_length=1, max_length=200)

    @field_validator("claim_type", "currency")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("claim_type")
    @classmethod
    def validate_claim_type(cls, value: str) -> str:
        if value not in CLAIM_TYPES:
            raise ValueError(f"claim_type must be one of {sorted(CLAIM_TYPES)}")
        return value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.travel_start_date and self.travel_end_date:
            if self.travel_end_date < self.travel_start_date:
                raise ValueError("travel_end_date cannot be earlier than travel_start_date")
        if self.claim_type == "TA_DA" and not (
            self.travel_start_date and self.travel_end_date
        ):
            raise ValueError("TA_DA claims require travel start and end dates")
        return self


class ExpenseClaimItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    claim_id: UUID
    expense_date: date
    category: str
    description: str
    quantity: float
    rate: float
    amount: float
    evidence_urls: list[str] | None
    created_at: datetime
    updated_at: datetime


class ExpenseClaimActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    claim_id: UUID
    actor_user_id: UUID
    action: str
    note: str | None
    amount: float | None
    extra_data: dict | None
    created_at: datetime
    updated_at: datetime


class ExpenseClaimResponse(BaseModel):
    id: UUID
    employee_id: UUID
    claim_number: str
    claim_type: str
    title: str
    purpose: str
    travel_start_date: date | None
    travel_end_date: date | None
    origin: str | None
    destination: str | None
    currency: str
    claimed_amount: float
    verified_amount: float | None
    approved_amount: float | None
    status: str
    evidence_urls: list[str] | None
    submitted_at: datetime | None
    verified_by_user_id: UUID | None
    verified_at: datetime | None
    verification_note: str | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    approval_note: str | None
    rejected_by_user_id: UUID | None
    rejected_at: datetime | None
    rejection_reason: str | None
    paid_by_user_id: UUID | None
    paid_at: datetime | None
    payment_reference: str | None
    created_at: datetime
    updated_at: datetime
    items: list[ExpenseClaimItemResponse]


class AdminExpenseClaimResponse(ExpenseClaimResponse):
    employee_code: str
    employee_name: str


class ClaimVerificationRequest(BaseModel):
    verified_amount: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=5000)


class ClaimApprovalRequest(BaseModel):
    approved_amount: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=5000)


class ClaimRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=5000)


class ClaimPaymentRequest(BaseModel):
    payment_reference: str = Field(min_length=2, max_length=150)
    note: str | None = Field(default=None, max_length=5000)
