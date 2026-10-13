from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class OutletCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=180)
    outlet_type: str = Field(default="SHOP", min_length=2, max_length=50)
    cluster_name: str | None = Field(default=None, max_length=180)
    address: str = Field(min_length=3, max_length=5000)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    attendance_radius_meters: float = Field(default=150, ge=20, le=5000)

    vendor_id: UUID | None = None
    vendor_name: str | None = Field(default=None, max_length=180)
    vendor_contact_person: str | None = Field(default=None, max_length=180)
    vendor_phone: str | None = Field(default=None, max_length=40)
    vendor_email: str | None = Field(default=None, max_length=180)
    assistant_vendor_id: UUID | None = None
    assistant_vendor_name: str | None = Field(default=None, max_length=180)
    assistant_vendor_contact_person: str | None = Field(default=None, max_length=180)
    assistant_vendor_phone: str | None = Field(default=None, max_length=40)
    assistant_vendor_email: str | None = Field(default=None, max_length=180)
    parcel_vendor_id: UUID | None = None
    parcel_vendor_name: str | None = Field(default=None, max_length=180)
    parcel_vendor_contact_person: str | None = Field(default=None, max_length=180)
    parcel_vendor_phone: str | None = Field(default=None, max_length=40)
    parcel_vendor_email: str | None = Field(default=None, max_length=180)

    opening_date: date | None = None
    licence_number: str | None = Field(default=None, max_length=120)
    licence_expiry_date: date | None = None
    excise_licence_number: str | None = Field(default=None, max_length=120)
    excise_expiry_date: date | None = None
    rent_agreement_expiry_date: date | None = None
    blueprint_document_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("code", "outlet_type")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class OutletUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=180)
    outlet_type: str | None = Field(default=None, max_length=50)
    cluster_name: str | None = Field(default=None, max_length=180)
    address: str | None = Field(default=None, max_length=5000)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    attendance_radius_meters: float | None = Field(default=None, ge=20, le=5000)

    vendor_id: UUID | None = None
    vendor_name: str | None = Field(default=None, max_length=180)
    vendor_contact_person: str | None = Field(default=None, max_length=180)
    vendor_phone: str | None = Field(default=None, max_length=40)
    vendor_email: str | None = Field(default=None, max_length=180)
    assistant_vendor_id: UUID | None = None
    assistant_vendor_name: str | None = Field(default=None, max_length=180)
    assistant_vendor_contact_person: str | None = Field(default=None, max_length=180)
    assistant_vendor_phone: str | None = Field(default=None, max_length=40)
    assistant_vendor_email: str | None = Field(default=None, max_length=180)
    parcel_vendor_id: UUID | None = None
    parcel_vendor_name: str | None = Field(default=None, max_length=180)
    parcel_vendor_contact_person: str | None = Field(default=None, max_length=180)
    parcel_vendor_phone: str | None = Field(default=None, max_length=40)
    parcel_vendor_email: str | None = Field(default=None, max_length=180)

    opening_date: date | None = None
    licence_number: str | None = Field(default=None, max_length=120)
    licence_expiry_date: date | None = None
    excise_licence_number: str | None = Field(default=None, max_length=120)
    excise_expiry_date: date | None = None
    rent_agreement_expiry_date: date | None = None
    blueprint_document_id: UUID | None = None
    status: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None

    @field_validator("outlet_type", "status")
    @classmethod
    def normalize_optional_codes(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else value


class FieldVisitorOption(BaseModel):
    employee_id: UUID
    employee_code: str
    full_name: str
    phone: str | None


class OutletFieldVisitorAssignmentResponse(BaseModel):
    id: UUID
    employee_id: UUID
    employee_code: str
    employee_name: str
    phone: str | None
    assigned_at: datetime
    is_active: bool
    notes: str | None


class OutletResponse(BaseModel):
    id: UUID
    code: str
    name: str
    outlet_type: str
    cluster_name: str | None
    address: str
    latitude: Decimal | None
    longitude: Decimal | None
    attendance_radius_meters: float

    vendor_id: UUID | None
    vendor_name: str | None
    vendor_contact_person: str | None
    vendor_phone: str | None
    vendor_email: str | None
    assistant_vendor_id: UUID | None
    assistant_vendor_name: str | None
    assistant_vendor_contact_person: str | None
    assistant_vendor_phone: str | None
    assistant_vendor_email: str | None
    parcel_vendor_id: UUID | None
    parcel_vendor_name: str | None
    parcel_vendor_contact_person: str | None
    parcel_vendor_phone: str | None
    parcel_vendor_email: str | None

    opening_date: date | None
    licence_number: str | None
    licence_expiry_date: date | None
    excise_licence_number: str | None
    excise_expiry_date: date | None
    rent_agreement_expiry_date: date | None
    blueprint_document_id: UUID | None

    status: str
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    field_visitors: list[OutletFieldVisitorAssignmentResponse]
    inspection_count: int
    pending_vendor_inspections: int


class OutletInspectionOption(BaseModel):
    id: UUID
    code: str
    name: str
    cluster_name: str | None
    address: str
    vendor_id: UUID | None
    vendor_name: str | None
