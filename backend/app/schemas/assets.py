from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VehicleCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    registration_number: str = Field(min_length=3, max_length=50)
    ownership_type: str = Field(default="COMPANY", max_length=30)
    employee_owner_id: UUID | None = None
    vehicle_type: str = Field(min_length=2, max_length=50)
    make: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    fuel_type: str = Field(min_length=2, max_length=30)
    expected_mileage_kmpl: Decimal = Field(
        gt=0,
        max_digits=8,
        decimal_places=2,
    )
    manufacture_year: int | None = Field(default=None, ge=1900, le=2200)
    insurance_expiry_date: date | None = None
    registration_expiry_date: date | None = None
    pollution_expiry_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)
    extra_data: dict | None = None

    @field_validator("code", "registration_number", "ownership_type")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class VehicleUpdateRequest(BaseModel):
    vehicle_type: str | None = Field(default=None, max_length=50)
    make: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    fuel_type: str | None = Field(default=None, max_length=30)
    expected_mileage_kmpl: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=8,
        decimal_places=2,
    )
    insurance_expiry_date: date | None = None
    registration_expiry_date: date | None = None
    pollution_expiry_date: date | None = None
    status: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=5000)
    extra_data: dict | None = None
    is_active: bool | None = None


class VehicleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    registration_number: str
    ownership_type: str
    employee_owner_id: UUID | None
    vehicle_type: str
    make: str | None
    model: str | None
    fuel_type: str | None
    expected_mileage_kmpl: Decimal | None
    manufacture_year: int | None
    insurance_expiry_date: date | None
    registration_expiry_date: date | None
    pollution_expiry_date: date | None
    status: str
    notes: str | None
    extra_data: dict | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PropertyCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=180)
    property_type: str = Field(min_length=2, max_length=50)
    address: str = Field(min_length=3, max_length=5000)
    tax_identifier: str | None = Field(default=None, max_length=120)
    last_tax_paid_date: date | None = None
    next_tax_due_date: date | None = None
    notes: str | None = Field(default=None, max_length=5000)
    extra_data: dict | None = None

    @field_validator("code", "property_type")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class PropertyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=5000)
    tax_identifier: str | None = Field(default=None, max_length=120)
    last_tax_paid_date: date | None = None
    next_tax_due_date: date | None = None
    status: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=5000)
    extra_data: dict | None = None
    is_active: bool | None = None


class PropertyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    property_type: str
    address: str
    tax_identifier: str | None
    last_tax_paid_date: date | None
    next_tax_due_date: date | None
    status: str
    notes: str | None
    extra_data: dict | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OutletCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=180)
    outlet_type: str = Field(min_length=2, max_length=50)
    address: str = Field(min_length=3, max_length=5000)
    vendor_name: str | None = Field(default=None, max_length=180)
    vendor_phone: str | None = Field(default=None, max_length=40)
    vendor_email: str | None = Field(default=None, max_length=180)
    licence_number: str | None = Field(default=None, max_length=120)
    licence_expiry_date: date | None = None
    blueprint_document_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)
    extra_data: dict | None = None

    @field_validator("code", "outlet_type")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class OutletUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=5000)
    vendor_name: str | None = Field(default=None, max_length=180)
    vendor_phone: str | None = Field(default=None, max_length=40)
    vendor_email: str | None = Field(default=None, max_length=180)
    licence_number: str | None = Field(default=None, max_length=120)
    licence_expiry_date: date | None = None
    blueprint_document_id: UUID | None = None
    status: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=5000)
    extra_data: dict | None = None
    is_active: bool | None = None


class OutletResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    outlet_type: str
    address: str
    vendor_name: str | None
    vendor_phone: str | None
    vendor_email: str | None
    licence_number: str | None
    licence_expiry_date: date | None
    blueprint_document_id: UUID | None
    status: str
    notes: str | None
    extra_data: dict | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class RenewalItem(BaseModel):
    source_type: str
    source_id: UUID
    code: str
    title: str
    renewal_type: str
    due_date: date
    days_remaining: int
    severity: str
