from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CompanyAssetCreateRequest(BaseModel):
    asset_code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=180)
    category: str = Field(min_length=2, max_length=80)
    serial_number: str | None = Field(default=None, max_length=180)
    make: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    purchase_date: date | None = None
    purchase_cost: float | None = Field(default=None, ge=0)
    warranty_expiry_date: date | None = None
    condition: str = Field(default="GOOD", max_length=30)
    notes: str | None = Field(default=None, max_length=5000)
    extra_data: dict | None = None

    @field_validator("asset_code", "category", "condition")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class CompanyAssetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=180)
    category: str | None = Field(default=None, max_length=80)
    serial_number: str | None = Field(default=None, max_length=180)
    make: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    purchase_date: date | None = None
    purchase_cost: float | None = Field(default=None, ge=0)
    warranty_expiry_date: date | None = None
    status: str | None = Field(default=None, max_length=30)
    condition: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=5000)
    extra_data: dict | None = None


class CompanyAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_code: str
    name: str
    category: str
    serial_number: str | None
    make: str | None
    model: str | None
    purchase_date: date | None
    purchase_cost: float | None
    warranty_expiry_date: date | None
    status: str
    condition: str
    notes: str | None
    extra_data: dict | None
    created_at: datetime
    updated_at: datetime


class AssetAssignRequest(BaseModel):
    employee_id: UUID
    expected_return_at: datetime | None = None
    issue_condition: str = Field(default="GOOD", max_length=30)
    issue_note: str | None = Field(default=None, max_length=5000)


class AssetReturnRequest(BaseModel):
    return_condition: str = Field(min_length=2, max_length=30)
    return_note: str | None = Field(default=None, max_length=5000)


class AssetAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    employee_id: UUID
    assigned_by_user_id: UUID
    assigned_at: datetime
    expected_return_at: datetime | None
    returned_at: datetime | None
    assignment_status: str
    issue_condition: str
    return_condition: str | None
    issue_note: str | None
    return_note: str | None
    created_at: datetime
    updated_at: datetime


class MaintenanceCreateRequest(BaseModel):
    asset_id: UUID
    issue_title: str = Field(min_length=3, max_length=220)
    issue_description: str = Field(min_length=3, max_length=5000)
    vendor_name: str | None = Field(default=None, max_length=180)
    estimated_cost: float | None = Field(default=None, ge=0)
    evidence_urls: list[str] = Field(default_factory=list, max_length=30)


class MaintenanceCompleteRequest(BaseModel):
    actual_cost: float | None = Field(default=None, ge=0)
    resolution_note: str = Field(min_length=3, max_length=5000)
    asset_condition: str = Field(default="GOOD", max_length=30)


class MaintenanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    reported_by_user_id: UUID
    issue_title: str
    issue_description: str
    vendor_name: str | None
    estimated_cost: float | None
    actual_cost: float | None
    status: str
    opened_at: datetime
    completed_at: datetime | None
    resolution_note: str | None
    evidence_urls: list[str] | None
    created_at: datetime
    updated_at: datetime
