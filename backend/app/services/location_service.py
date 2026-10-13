from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Device, Employee, LiveLocation, LocationHistory, User
from app.schemas.locations import LocationBatchRequest
from app.services.device_service import get_employee_for_user


def normalize_datetime(value: datetime) -> datetime:
    """Return an aware UTC datetime."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def submit_location_batch(
    database: Session,
    *,
    user: User,
    payload: LocationBatchRequest,
) -> tuple[int, int, datetime]:
    """Store a duplicate-safe GPS batch and update live location."""

    employee = get_employee_for_user(database, user)

    device = database.scalar(
        select(Device).where(
            Device.id == payload.device_id,
            Device.organization_id == user.organization_id,
            Device.employee_id == employee.id,
            Device.is_active.is_(True),
        )
    )

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active registered device was not found.",
        )

    accepted_count = 0
    normalized_points = [
        (point, normalize_datetime(point.recorded_at))
        for point in payload.points
    ]

    for point, recorded_at in normalized_points:
        statement = (
            pg_insert(LocationHistory)
            .values(
                client_event_id=point.client_event_id,
                organization_id=user.organization_id,
                employee_id=employee.id,
                device_id=device.id,
                latitude=point.latitude,
                longitude=point.longitude,
                accuracy_meters=point.accuracy_meters,
                speed_mps=point.speed_mps,
                battery_percentage=point.battery_percentage,
                recorded_at=recorded_at,
            )
            .on_conflict_do_nothing(index_elements=["client_event_id"])
            .returning(LocationHistory.id)
        )

        inserted_id = database.execute(statement).scalar_one_or_none()
        if inserted_id is not None:
            accepted_count += 1

    latest_point, latest_recorded_at = max(
        normalized_points,
        key=lambda item: item[1],
    )

    live_location = database.scalar(
        select(LiveLocation).where(
            LiveLocation.employee_id == employee.id
        )
    )

    if live_location is None or latest_recorded_at >= live_location.recorded_at:
        if live_location is None:
            live_location = LiveLocation(
                organization_id=user.organization_id,
                employee_id=employee.id,
            )
            database.add(live_location)

        live_location.device_id = device.id
        live_location.latitude = latest_point.latitude
        live_location.longitude = latest_point.longitude
        live_location.accuracy_meters = latest_point.accuracy_meters
        live_location.speed_mps = latest_point.speed_mps
        live_location.battery_percentage = latest_point.battery_percentage
        live_location.recorded_at = latest_recorded_at

    device.last_seen_at = datetime.now(timezone.utc)
    database.commit()

    return (
        accepted_count,
        len(payload.points) - accepted_count,
        latest_recorded_at,
    )


def get_own_latest_location(
    database: Session,
    *,
    user: User,
) -> LiveLocation:
    """Return the current employee's latest location."""

    employee = get_employee_for_user(database, user)

    live_location = database.scalar(
        select(LiveLocation).where(
            LiveLocation.organization_id == user.organization_id,
            LiveLocation.employee_id == employee.id,
        )
    )

    if live_location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No location has been submitted yet.",
        )

    return live_location


def list_live_locations(
    database: Session,
    *,
    organization_id: UUID,
) -> list[dict]:
    """Return latest locations for an organization."""

    rows = database.execute(
        select(LiveLocation, Employee, User)
        .join(Employee, LiveLocation.employee_id == Employee.id)
        .join(User, Employee.user_id == User.id)
        .where(LiveLocation.organization_id == organization_id)
        .order_by(LiveLocation.recorded_at.desc())
    ).all()

    return [
        {
            "id": live_location.id,
            "employee_id": employee.id,
            "employee_code": user.employee_code,
            "employee_name": employee.full_name,
            "device_id": live_location.device_id,
            "latitude": live_location.latitude,
            "longitude": live_location.longitude,
            "accuracy_meters": live_location.accuracy_meters,
            "speed_mps": live_location.speed_mps,
            "battery_percentage": live_location.battery_percentage,
            "recorded_at": live_location.recorded_at,
            "updated_at": live_location.updated_at,
        }
        for live_location, employee, user in rows
    ]


def list_location_roster(database: Session, *, organization_id: UUID) -> list[dict]:
    """Return every active employee, including employees with no GPS signal."""
    rows = database.execute(
        select(Employee, User, LiveLocation)
        .join(User, Employee.user_id == User.id)
        .outerjoin(LiveLocation, LiveLocation.employee_id == Employee.id)
        .where(
            Employee.organization_id == organization_id,
            User.is_active.is_(True),
        )
        .order_by(User.employee_code)
    ).all()
    return [
        {
            "employee_id": employee.id,
            "employee_code": user.employee_code,
            "employee_name": employee.full_name,
            "is_field_employee": employee.is_field_employee,
            "latitude": location.latitude if location else None,
            "longitude": location.longitude if location else None,
            "accuracy_meters": location.accuracy_meters if location else None,
            "speed_mps": location.speed_mps if location else None,
            "battery_percentage": location.battery_percentage if location else None,
            "recorded_at": location.recorded_at if location else None,
            "updated_at": location.updated_at if location else None,
        }
        for employee, user, location in rows
    ]


def list_location_history(
    database: Session,
    *,
    organization_id: UUID,
    employee_id: UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    limit: int,
) -> list[LocationHistory]:
    """Return historical locations for one employee."""

    employee_exists = database.scalar(
        select(Employee.id).where(
            Employee.id == employee_id,
            Employee.organization_id == organization_id,
        )
    )

    if employee_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee was not found.",
        )

    statement = select(LocationHistory).where(
        LocationHistory.organization_id == organization_id,
        LocationHistory.employee_id == employee_id,
    )

    if start_at is not None:
        statement = statement.where(
            LocationHistory.recorded_at >= normalize_datetime(start_at)
        )

    if end_at is not None:
        statement = statement.where(
            LocationHistory.recorded_at <= normalize_datetime(end_at)
        )

    statement = (
        statement
        .order_by(LocationHistory.recorded_at.desc())
        .limit(limit)
    )

    return list(database.scalars(statement).all())
