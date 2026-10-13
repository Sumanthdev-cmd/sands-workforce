from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AttendanceActionRequest(BaseModel):
    """Optional frontend choice for automatic attendance actions."""

    automatic: bool = False


class AttendanceRecordResponse(BaseModel):
    """Employee attendance record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    attendance_date: date
    status: str
    check_in_at: datetime | None
    check_out_at: datetime | None
    check_in_latitude: float | None
    check_in_longitude: float | None
    check_out_latitude: float | None
    check_out_longitude: float | None
    check_in_geofence_id: UUID | None
    check_out_geofence_id: UUID | None
    late_minutes: int
    worked_minutes: int
    is_auto_check_in: bool
    is_auto_check_out: bool
    created_at: datetime
    updated_at: datetime


class AttendanceEvaluationResponse(BaseModel):
    """Result of evaluating the latest pushed GPS location."""

    action: str
    message: str
    inside_geofence: bool
    distance_meters: float
    attendance: AttendanceRecordResponse | None


class AdminAttendanceResponse(BaseModel):
    """Organization attendance row, including employees without a record."""

    id: UUID | None
    employee_id: UUID
    employee_code: str
    employee_name: str
    attendance_date: date
    status: str
    check_in_at: datetime | None
    check_out_at: datetime | None
    check_in_latitude: float | None
    check_in_longitude: float | None
    check_out_latitude: float | None
    check_out_longitude: float | None
    check_in_geofence_id: UUID | None
    check_out_geofence_id: UUID | None
    late_minutes: int
    worked_minutes: int
    is_auto_check_in: bool
    is_auto_check_out: bool
    created_at: datetime | None
    updated_at: datetime | None
    has_record: bool
