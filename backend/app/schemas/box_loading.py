from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Rate = Annotated[Decimal, Field(ge=0, le=1000000, max_digits=9, decimal_places=2, allow_inf_nan=False)]
Count = Annotated[int, Field(strict=True, ge=1, le=1000000)]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BoxLoadingInputs(StrictRequest):
    loading_date: date
    vehicle_type: Literal["OWN", "RENTED"]
    vehicle_number: str = Field(min_length=2, max_length=32)
    loading_rate: Rate
    loading_box_count: Count
    transport_rate: Rate = Decimal("0.00")
    transport_box_count: int = Field(default=0, strict=True, ge=0, le=1000000)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("vehicle_number")
    @classmethod
    def clean_number(cls, value):
        return value.upper()

    @model_validator(mode="after")
    def validate_transport(self):
        if self.vehicle_type == "OWN" and (self.transport_rate or self.transport_box_count):
            raise ValueError("Transport charges apply only to rented vehicles. Set transport rate and box count to zero for an own vehicle.")
        if self.vehicle_type == "RENTED" and self.transport_box_count < 1:
            raise ValueError("Enter the number of boxes transported for a rented vehicle.")
        return self


class CreateBoxLoading(BoxLoadingInputs):
    client_request_id: UUID


class VersionRequest(StrictRequest):
    expected_version: int = Field(strict=True, ge=1)


class UpdateBoxLoading(BoxLoadingInputs):
    expected_version: int = Field(strict=True, ge=1)


class DecisionRequest(VersionRequest):
    decision: Literal["APPROVE", "REJECT"]
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def rejection_reason(self):
        if self.decision == "REJECT" and not self.note:
            raise ValueError("Enter a reason when rejecting this request.")
        return self


class DisbursementRequest(VersionRequest):
    payment_date: date
    payment_mode: Literal["CASH", "UPI", "BANK_TRANSFER", "CHEQUE"]
    payment_reference: str = Field(min_length=1, max_length=160)
    paid_to: str = Field(min_length=1, max_length=160)
