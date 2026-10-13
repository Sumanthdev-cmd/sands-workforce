from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GeofenceCreateRequest(BaseModel):
    """Create a circular work-location boundary."""

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=150)
    geofence_type: str = Field(
        default="OFFICE",
        min_length=2,
        max_length=30,
    )
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_meters: float = Field(
        default=150,
        ge=20,
        le=5000,
    )

    @field_validator("code", "geofence_type")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class GeofenceUpdateRequest(BaseModel):
    """Update a work-location boundary."""

    name: str | None = Field(default=None, min_length=2, max_length=150)
    geofence_type: str | None = Field(default=None, min_length=2, max_length=30)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_meters: float | None = Field(default=None, ge=20, le=5000)
    is_active: bool | None = None

    @field_validator("geofence_type")
    @classmethod
    def normalize_type(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value


class GeofenceResponse(BaseModel):
    """Geofence response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    geofence_type: str
    latitude: float
    longitude: float
    radius_meters: float
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GeofenceAssignmentRequest(BaseModel):
    """Assign a geofence and shift to an employee."""

    valid_from: date = Field(default_factory=date.today)
    valid_to: date | None = None
    shift_start_time: time = time(9, 0)
    shift_end_time: time = time(18, 0)
    grace_minutes: int = Field(default=15, ge=0, le=240)
    is_primary: bool = True


class GeofenceAssignmentResponse(BaseModel):
    """Employee geofence assignment response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    geofence_id: UUID
    valid_from: date
    valid_to: date | None
    shift_start_time: time
    shift_end_time: time
    grace_minutes: int
    is_primary: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
