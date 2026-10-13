from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MaintenanceBillCreateRequest(BaseModel):
    submission_id: UUID

    category: str = Field(
        default="GENERAL",
        min_length=2,
        max_length=60,
    )

    related_type: str = Field(
        default="GENERAL",
        min_length=2,
        max_length=30,
    )

    outlet_id: UUID | None = None
    vehicle_id: UUID | None = None
    property_id: UUID | None = None
    company_asset_id: UUID | None = None

    vendor_id: UUID | None = None
    vendor_name: str = Field(
        min_length=2,
        max_length=180,
    )

    invoice_number: str | None = Field(
        default=None,
        max_length=120,
    )

    bill_date: date
    due_date: date | None = None

    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    description: str = Field(
        min_length=3,
        max_length=5000,
    )

    bill_document_id: UUID | None = None

    @field_validator(
        "category",
        "related_type",
    )
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class MaintenanceBillUpdateRequest(BaseModel):
    category: str | None = Field(
        default=None,
        min_length=2,
        max_length=60,
    )

    related_type: str | None = Field(
        default=None,
        min_length=2,
        max_length=30,
    )

    outlet_id: UUID | None = None
    vehicle_id: UUID | None = None
    property_id: UUID | None = None
    company_asset_id: UUID | None = None

    vendor_id: UUID | None = None

    vendor_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=180,
    )

    invoice_number: str | None = Field(
        default=None,
        max_length=120,
    )

    bill_date: date | None = None
    due_date: date | None = None

    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )

    description: str | None = Field(
        default=None,
        min_length=3,
        max_length=5000,
    )

    bill_document_id: UUID | None = None

    @field_validator(
        "category",
        "related_type",
    )
    @classmethod
    def normalize_optional_codes(
        cls,
        value: str | None,
    ) -> str | None:
        return (
            value.strip().upper()
            if value is not None
            else None
        )


class MaintenanceBillVerificationRequest(BaseModel):
    note: str | None = Field(
        default=None,
        max_length=5000,
    )


class MaintenanceBillVerificationRejectRequest(BaseModel):
    reason: str = Field(
        min_length=3,
        max_length=5000,
    )


class MaintenanceBillDecisionRequest(BaseModel):
    note: str | None = Field(
        default=None,
        max_length=5000,
    )


class MaintenanceBillRejectRequest(BaseModel):
    reason: str = Field(
        min_length=3,
        max_length=5000,
    )


class MaintenanceBillPaymentRequest(BaseModel):
    payment_reference: str = Field(
        min_length=2,
        max_length=180,
    )

    note: str | None = Field(
        default=None,
        max_length=5000,
    )


class MaintenanceBillResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    organization_id: UUID

    submission_id: UUID | None

    status: str
    category: str
    related_type: str

    outlet_id: UUID | None
    vehicle_id: UUID | None
    property_id: UUID | None
    company_asset_id: UUID | None

    vendor_id: UUID | None
    vendor_name: str

    invoice_number: str | None

    bill_date: date
    due_date: date | None

    amount: Decimal
    description: str

    bill_document_id: UUID | None

    created_by_user_id: UUID
    submitted_by_user_id: UUID | None
    submitted_at: datetime | None

    verified_by_user_id: UUID | None
    verified_at: datetime | None
    verification_note: str | None

    md_user_id: UUID | None
    decided_at: datetime | None
    decision_note: str | None

    paid_by_user_id: UUID | None
    paid_at: datetime | None
    payment_reference: str | None
    payment_note: str | None

    created_at: datetime
    updated_at: datetime


class MaintenanceBillActionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: UUID
    organization_id: UUID
    bill_id: UUID
    actor_user_id: UUID

    action: str
    note: str | None
    extra_data: dict | None

    created_at: datetime
    updated_at: datetime