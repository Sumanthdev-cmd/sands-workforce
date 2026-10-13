from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Device, Employee, User
from app.schemas.devices import DeviceRegisterRequest


def get_employee_for_user(database: Session, user: User) -> Employee:
    """Return the employee profile attached to a login user."""

    employee = database.scalar(
        select(Employee).where(
            Employee.organization_id == user.organization_id,
            Employee.user_id == user.id,
        )
    )

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile was not found.",
        )

    return employee


def register_device(
    database: Session,
    *,
    user: User,
    payload: DeviceRegisterRequest,
) -> Device:
    """Register or update the authenticated employee's device."""

    employee = get_employee_for_user(database, user)

    device = database.scalar(
        select(Device).where(
            Device.organization_id == user.organization_id,
            Device.device_identifier == payload.device_identifier,
        )
    )

    if device is not None and device.employee_id != employee.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This device is already assigned to another employee.",
        )

    database.execute(
        update(Device)
        .where(
            Device.employee_id == employee.id,
            Device.is_primary.is_(True),
        )
        .values(is_primary=False)
    )

    now = datetime.now(timezone.utc)

    if device is None:
        device = Device(
            organization_id=user.organization_id,
            employee_id=employee.id,
            device_identifier=payload.device_identifier,
        )
        database.add(device)

    device.platform = payload.platform
    device.device_name = payload.device_name
    device.manufacturer = payload.manufacturer
    device.model = payload.model
    device.os_version = payload.os_version
    device.app_version = payload.app_version
    device.fcm_token = payload.fcm_token
    device.is_active = True
    device.is_primary = True
    device.last_seen_at = now

    database.commit()
    database.refresh(device)

    return device


def update_fcm_token(
    database: Session,
    *,
    user: User,
    device_id: UUID,
    fcm_token: str,
) -> Device:
    """Update FCM token for a device owned by the current employee."""

    employee = get_employee_for_user(database, user)

    device = database.scalar(
        select(Device).where(
            Device.id == device_id,
            Device.organization_id == user.organization_id,
            Device.employee_id == employee.id,
            Device.is_active.is_(True),
        )
    )

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active device was not found.",
        )

    device.fcm_token = fcm_token
    device.last_seen_at = datetime.now(timezone.utc)

    database.commit()
    database.refresh(device)

    return device


def list_own_devices(database: Session, *, user: User) -> list[Device]:
    """List devices owned by the authenticated employee."""

    employee = get_employee_for_user(database, user)

    return list(
        database.scalars(
            select(Device)
            .where(
                Device.organization_id == user.organization_id,
                Device.employee_id == employee.id,
            )
            .order_by(Device.is_primary.desc(), Device.created_at.desc())
        ).all()
    )
