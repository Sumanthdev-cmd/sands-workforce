from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VendorCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=180)
    contact_person: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=5000)
    service_category: str | None = Field(default=None, max_length=100)
    deposit_amount: float | None = Field(default=None, ge=0)
    deposit_payment_mode: str | None = Field(default=None, max_length=30)
    deposit_reference: str | None = Field(default=None, max_length=180)
    deposit_received_on: date | None = None
    deposit_document_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("deposit_payment_mode")
    @classmethod
    def normalize_payment_mode(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @model_validator(mode="after")
    def validate_deposit(self):
        if self.deposit_amount and not self.deposit_payment_mode:
            raise ValueError("deposit_payment_mode is required when deposit_amount is entered.")
        return self


class VendorUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=180)
    contact_person: str | None = Field(default=None, max_length=180)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=5000)
    service_category: str | None = Field(default=None, max_length=100)
    deposit_amount: float | None = Field(default=None, ge=0)
    deposit_payment_mode: str | None = Field(default=None, max_length=30)
    deposit_reference: str | None = Field(default=None, max_length=180)
    deposit_received_on: date | None = None
    deposit_document_id: UUID | None = None
    status: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=5000)


class VendorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    address: str | None
    service_category: str | None
    deposit_amount: float | None
    deposit_payment_mode: str | None
    deposit_reference: str | None
    deposit_received_on: date | None
    deposit_document_id: UUID | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class RefundDecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class RefundRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=5000)


class VendorDepositRefundCreateRequest(BaseModel):
    amount: float = Field(gt=0)
    payment_mode: str = Field(min_length=2, max_length=30)
    refund_date: date
    payment_reference: str | None = Field(default=None, max_length=180)
    supporting_document_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=5000)

    @field_validator("payment_mode")
    @classmethod
    def normalize_payment_mode(cls, value: str) -> str:
        return value.strip().upper()


class VendorDepositRefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vendor_id: UUID
    requested_by_user_id: UUID
    amount: float
    payment_mode: str
    refund_date: date
    payment_reference: str | None
    supporting_document_id: UUID | None
    reason: str
    status: str
    md_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime


class ShopRentalCreateRequest(BaseModel):
    rental_type: str = Field(min_length=2, max_length=30)
    building_name: str = Field(min_length=2, max_length=180)
    building_code: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=5000)
    counterparty_name: str = Field(min_length=2, max_length=180)
    counterparty_contact: str | None = Field(default=None, max_length=80)
    agreement_start_date: date
    agreement_end_date: date | None = None
    monthly_rent_amount: float = Field(gt=0)
    advance_amount: float | None = Field(default=None, ge=0)
    advance_payment_mode: str | None = Field(default=None, max_length=30)
    advance_paid_on: date | None = None
    advance_reference: str | None = Field(default=None, max_length=180)
    agreement_document_id: UUID | None = None
    advance_document_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("rental_type", "advance_payment_mode")
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.agreement_end_date and self.agreement_end_date < self.agreement_start_date:
            raise ValueError("agreement_end_date cannot be earlier than agreement_start_date.")
        if self.advance_amount and not self.advance_payment_mode:
            raise ValueError("advance_payment_mode is required when advance_amount is entered.")
        return self


class ShopRentalUpdateRequest(BaseModel):
    rental_type: str | None = Field(default=None, max_length=30)
    building_name: str | None = Field(default=None, max_length=180)
    building_code: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=5000)
    counterparty_name: str | None = Field(default=None, max_length=180)
    counterparty_contact: str | None = Field(default=None, max_length=80)
    agreement_start_date: date | None = None
    agreement_end_date: date | None = None
    monthly_rent_amount: float | None = Field(default=None, gt=0)
    advance_amount: float | None = Field(default=None, ge=0)
    advance_payment_mode: str | None = Field(default=None, max_length=30)
    advance_paid_on: date | None = None
    advance_reference: str | None = Field(default=None, max_length=180)
    agreement_document_id: UUID | None = None
    advance_document_id: UUID | None = None
    status: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=5000)


class ShopRentalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rental_type: str
    building_name: str
    building_code: str | None
    address: str | None
    counterparty_name: str
    counterparty_contact: str | None
    agreement_start_date: date
    agreement_end_date: date | None
    monthly_rent_amount: float
    advance_amount: float | None
    advance_payment_mode: str | None
    advance_paid_on: date | None
    advance_reference: str | None
    agreement_document_id: UUID | None
    advance_document_id: UUID | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ShopRentalAdvanceRefundCreateRequest(BaseModel):
    amount: float = Field(gt=0)
    payment_mode: str = Field(min_length=2, max_length=30)
    refund_date: date
    payment_reference: str | None = Field(default=None, max_length=180)
    supporting_document_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=5000)

    @field_validator("payment_mode")
    @classmethod
    def normalize_payment_mode(cls, value: str) -> str:
        return value.strip().upper()


class ShopRentalAdvanceRefundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rental_id: UUID
    requested_by_user_id: UUID
    amount: float
    payment_mode: str
    refund_date: date
    payment_reference: str | None
    supporting_document_id: UUID | None
    reason: str
    status: str
    md_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime


class VendorIssueCreateRequest(BaseModel):
    vendor_id: UUID | None = None
    outlet_id: UUID | None = None
    title: str = Field(min_length=3, max_length=220)
    description: str = Field(min_length=3, max_length=5000)
    category: str = Field(default="GENERAL", max_length=60)
    priority: str = Field(default="MEDIUM", max_length=20)
    evidence_urls: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("category", "priority")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class VendorIssueAssignRequest(BaseModel):
    assigned_to_user_id: UUID
    note: str | None = Field(default=None, max_length=5000)


class VendorIssueDecisionRequest(BaseModel):
    note: str = Field(min_length=3, max_length=5000)


class VendorIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vendor_id: UUID | None
    outlet_id: UUID | None
    raised_by_user_id: UUID
    assigned_to_user_id: UUID | None
    title: str
    description: str
    category: str
    priority: str
    evidence_urls: list[str] | None
    status: str
    resolution_note: str | None
    resolved_by_user_id: UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LabourPaymentCreateRequest(BaseModel):
    labour_name: str = Field(min_length=2, max_length=180)
    labour_phone: str | None = Field(default=None, max_length=40)
    work_description: str = Field(min_length=3, max_length=5000)
    work_start_date: date
    work_end_date: date
    amount: float = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=10)
    evidence_urls: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_dates(self):
        if self.work_end_date < self.work_start_date:
            raise ValueError(
                "work_end_date cannot be earlier than work_start_date."
            )
        return self


class LabourPaymentDecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class LabourPaymentRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=5000)


class LabourPaymentPaidRequest(BaseModel):
    payment_reference: str = Field(min_length=2, max_length=180)
    note: str | None = Field(default=None, max_length=5000)


class LabourPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requested_by_user_id: UUID
    labour_name: str
    labour_phone: str | None
    work_description: str
    work_start_date: date
    work_end_date: date
    amount: float
    currency: str
    evidence_urls: list[str] | None
    status: str
    md_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None
    paid_by_user_id: UUID | None
    paid_at: datetime | None
    payment_reference: str | None
    created_at: datetime
    updated_at: datetime


class OperationActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: UUID
    action: str
    note: str | None
    extra_data: dict | None
    created_at: datetime
    updated_at: datetime


class WingCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class WingUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    status: str | None = Field(default=None, max_length=30)


class WingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class WingContactCreateRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=180)
    contact_name: str = Field(min_length=2, max_length=180)
    designation: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=5000)


class WingContactUpdateRequest(BaseModel):
    organization_name: str | None = Field(default=None, max_length=180)
    contact_name: str | None = Field(default=None, max_length=180)
    designation: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=5000)


class WingContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wing_id: UUID
    organization_name: str
    contact_name: str
    designation: str | None
    phone: str | None
    email: str | None
    address: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
