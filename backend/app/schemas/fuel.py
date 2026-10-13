from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FuelIndentCreateRequest(BaseModel):
    vehicle_id: UUID
    odometer_km: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    requested_quantity_litres: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=3
    )
    requested_amount_rupees: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2
    )
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_request(self):
        if self.requested_quantity_litres is None and self.requested_amount_rupees is None:
            raise ValueError("Enter requested fuel quantity or requested amount.")
        return self


class FuelRecordRequest(BaseModel):
    actual_quantity_litres: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    actual_amount_rupees: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    fuel_date: datetime
    fuel_station: str | None = Field(default=None, max_length=180)
    bill_number: str | None = Field(default=None, max_length=120)
    receipt_document_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=5000)


class FuelIndentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    vehicle_id: UUID
    indent_number: str
    status: str
    odometer_km: Decimal
    requested_quantity_litres: Decimal | None
    requested_amount_rupees: Decimal | None
    fuel_date: datetime | None
    actual_quantity_litres: Decimal | None
    actual_amount_rupees: Decimal | None
    price_per_litre: Decimal | None
    fuel_station: str | None
    bill_number: str | None
    receipt_document_id: UUID | None
    previous_fuel_indent_id: UUID | None
    previous_odometer_km: Decimal | None
    distance_since_previous_km: Decimal | None
    interval_fuel_quantity_litres: Decimal | None
    interval_fuel_amount_rupees: Decimal | None
    actual_mileage_kmpl: Decimal | None
    expected_mileage_kmpl_snapshot: Decimal | None
    mileage_difference_kmpl: Decimal | None
    mileage_variance_pct: Decimal | None
    mileage_status: str | None
    interval_cost_per_km: Decimal | None
    notes: str | None
    created_by_user_id: UUID
    fueled_by_user_id: UUID | None
    canceled_by_user_id: UUID | None
    fueled_at: datetime | None
    canceled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VehicleFuelSummary(BaseModel):
    vehicle_id: UUID
    vehicle_code: str
    registration_number: str
    vehicle_type: str
    make: str | None
    model: str | None
    fuel_type: str | None
    expected_mileage_kmpl: Decimal | None
    latest_actual_mileage_kmpl: Decimal | None
    average_actual_mileage_kmpl: Decimal | None
    mileage_difference_kmpl: Decimal | None
    mileage_variance_pct: Decimal | None
    mileage_status: str | None
    last_odometer_km: Decimal | None
    last_fuel_quantity_litres: Decimal | None
    last_fuel_amount_rupees: Decimal | None
    last_fuel_date: datetime | None
    current_month_fuel_litres: Decimal
    current_month_fuel_amount_rupees: Decimal
    current_month_distance_km: Decimal
    average_cost_per_km: Decimal | None
