"""Additive Android tracking API. Organisation and person come only from auth."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, AwareDatetime, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.permissions import require_permissions
from app.api.routes.vendor_portal import VendorReady
from app.db.session import get_db
from app.models import User
from app.schemas.locations import LocationBatchRequest, LocationPointInput
from app.services.device_service import get_employee_for_user
from app.services.location_service import submit_location_batch
from app.services.mobile_tracking_policy import point_in_shift, session_state

router = APIRouter(prefix="/mobile", tags=["Android work tracking"])
DB = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permissions("location.view_all"))]


class Point(BaseModel):
    client_event_id: UUID
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    accuracy_meters: float = Field(ge=0, le=10000, allow_inf_nan=False)
    speed_mps: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    battery_percentage: int | None = Field(default=None, ge=0, le=100)
    recorded_at: AwareDatetime


class Batch(BaseModel):
    attendance_id: UUID
    device_id: UUID | None = None
    points: list[Point] = Field(min_length=1, max_length=100)


def record_for(database, org, person, kind, attendance_id=None, lock=False):
    # Both identifiers are selected from constants, never from request text.
    table = "attendance_records" if kind == "employee" else "vendor_attendance_records"
    owner = "employee_id" if kind == "employee" else "vendor_id"
    params = {"org": org, "person": person}
    if attendance_id:
        params["id"] = attendance_id
        clause = "AND id=:id"
    else:
        zone = database.scalar(text("SELECT timezone FROM organizations WHERE id=:org"), {"org": org}) or "Asia/Kolkata"
        params["today"] = datetime.now(timezone.utc).astimezone(ZoneInfo(zone)).date()
        clause = "AND attendance_date=:today"
    outlet = ", outlet_id" if kind == "vendor" else ""
    sql = f"SELECT id, attendance_date, check_in_at, check_out_at, status{outlet} FROM {table} WHERE organization_id=:org AND {owner}=:person {clause} ORDER BY check_in_at DESC NULLS LAST LIMIT 1"
    if lock:
        sql += " FOR UPDATE"
    row = database.execute(text(sql), params).mappings().first()
    if attendance_id and not row:
        raise HTTPException(404, "This attendance session does not belong to your account.")
    return dict(row) if row else None


def status_response(record):
    now = datetime.now(timezone.utc)
    return session_state(record, now) if record else {"active": False, "requires_review": False, "server_time": now, "id": None}


def ensure_vendor_active(database, vendor):
    active = database.scalar(text("""SELECT v.id FROM vendors v JOIN organizations o ON o.id=v.organization_id
        WHERE v.id=:vendor AND v.organization_id=:org AND v.status='ACTIVE' AND o.is_active=true"""),
        {"vendor": vendor.vendor_id, "org": vendor.organization_id})
    if active is None:
        raise HTTPException(403, "Your vendor account or organisation is inactive.")


@router.get("/version")
def version():
    return {"version": 1, "sample_seconds": 30, "status_seconds": 60, "offline_lease_seconds": 900}


@router.get("/employee/status")
def employee_status(user: CurrentUser, database: DB, attendance_id: UUID | None = None):
    person = get_employee_for_user(database, user)
    return status_response(record_for(database, user.organization_id, person.id, "employee", attendance_id))


@router.get("/vendor/status")
def vendor_status(vendor: VendorReady, database: DB, attendance_id: UUID | None = None):
    ensure_vendor_active(database, vendor)
    return status_response(record_for(database, vendor.organization_id, vendor.vendor_id, "vendor", attendance_id))


def split_points(payload, record):
    now = datetime.now(timezone.utc)
    valid = [p for p in payload.points if point_in_shift(record, p.recorded_at, now)]
    return valid, len(payload.points) - len(valid)


@router.post("/employee/locations")
def employee_locations(payload: Batch, user: CurrentUser, database: DB):
    person = get_employee_for_user(database, user)
    record = record_for(database, user.organization_id, person.id, "employee", payload.attendance_id, lock=True)
    if not payload.device_id:
        raise HTTPException(422, "Register this Android device before sending locations.")
    valid, rejected = split_points(payload, record)
    accepted = duplicates = 0
    if valid:
        accepted, duplicates, _ = submit_location_batch(database, user=user, payload=LocationBatchRequest(
            device_id=payload.device_id,
            points=[LocationPointInput(**p.model_dump()) for p in valid],
        ))
    else:
        database.rollback()
    return {"accepted_count": accepted, "duplicate_count": duplicates, "rejected_count": rejected, "session": status_response(record)}


@router.post("/vendor/locations")
def vendor_locations(payload: Batch, vendor: VendorReady, database: DB):
    # VendorReady checks the existing vendor session and password-change policy.
    ensure_vendor_active(database, vendor)
    record = record_for(database, vendor.organization_id, vendor.vendor_id, "vendor", payload.attendance_id, lock=True)
    valid, rejected = split_points(payload, record)
    accepted = 0
    for point in valid:
        params = point.model_dump()
        params.update(org=vendor.organization_id, vendor=vendor.vendor_id, attendance=payload.attendance_id)
        inserted = database.execute(text("""
            INSERT INTO mobile_vendor_locations
              (organization_id, vendor_id, attendance_id, client_event_id,
               latitude, longitude, accuracy_meters, speed_mps, battery_percentage, recorded_at)
            VALUES (:org, :vendor, :attendance, :client_event_id, :latitude, :longitude,
                    :accuracy_meters, :speed_mps, :battery_percentage, :recorded_at)
            ON CONFLICT (organization_id, vendor_id, client_event_id) DO NOTHING
            RETURNING client_event_id
        """), params).scalar_one_or_none()
        accepted += inserted is not None
    database.commit()
    return {"accepted_count": accepted, "duplicate_count": len(valid)-accepted, "rejected_count": rejected, "session": status_response(record)}


@router.get("/live")
def live_locations(user: Viewer, database: DB):
    from app.services.team_location_service import team_locations
    return team_locations(database, user.organization_id)
