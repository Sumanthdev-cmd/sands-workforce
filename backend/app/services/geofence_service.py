from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Employee, EmployeeGeofenceAssignment, Geofence, User
from app.schemas.geofences import (
    GeofenceAssignmentRequest,
    GeofenceCreateRequest,
    GeofenceUpdateRequest,
)


def create_geofence(database: Session, *, user: User, payload: GeofenceCreateRequest) -> Geofence:
    geofence = Geofence(
        organization_id=user.organization_id,
        code=payload.code,
        name=payload.name.strip(),
        geofence_type=payload.geofence_type,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
        is_active=True,
    )
    database.add(geofence)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A geofence with this code already exists.",
        ) from error
    database.refresh(geofence)
    return geofence


def list_geofences(database: Session, *, organization_id: UUID, active_only: bool) -> list[Geofence]:
    statement = select(Geofence).where(Geofence.organization_id == organization_id)
    if active_only:
        statement = statement.where(Geofence.is_active.is_(True))
    return list(database.scalars(statement.order_by(Geofence.name)).all())


def update_geofence(
    database: Session,
    *,
    organization_id: UUID,
    geofence_id: UUID,
    payload: GeofenceUpdateRequest,
) -> Geofence:
    geofence = database.scalar(
        select(Geofence).where(
            Geofence.id == geofence_id,
            Geofence.organization_id == organization_id,
        )
    )
    if geofence is None:
        raise HTTPException(status_code=404, detail="Geofence was not found.")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(geofence, field_name, value)
    database.commit()
    database.refresh(geofence)
    return geofence


def assign_geofence(
    database: Session,
    *,
    organization_id: UUID,
    employee_id: UUID,
    geofence_id: UUID,
    payload: GeofenceAssignmentRequest,
) -> EmployeeGeofenceAssignment:
    employee = database.scalar(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.organization_id == organization_id,
        )
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee was not found.")

    geofence = database.scalar(
        select(Geofence).where(
            Geofence.id == geofence_id,
            Geofence.organization_id == organization_id,
            Geofence.is_active.is_(True),
        )
    )
    if geofence is None:
        raise HTTPException(status_code=404, detail="Active geofence was not found.")

    if payload.valid_to is not None and payload.valid_to < payload.valid_from:
        raise HTTPException(status_code=422, detail="valid_to cannot be earlier than valid_from.")

    if payload.is_primary:
        database.execute(
            update(EmployeeGeofenceAssignment)
            .where(
                EmployeeGeofenceAssignment.employee_id == employee_id,
                EmployeeGeofenceAssignment.is_primary.is_(True),
            )
            .values(is_primary=False)
        )

    assignment = database.scalar(
        select(EmployeeGeofenceAssignment).where(
            EmployeeGeofenceAssignment.employee_id == employee_id,
            EmployeeGeofenceAssignment.geofence_id == geofence_id,
        )
    )

    if assignment is None:
        assignment = EmployeeGeofenceAssignment(
            organization_id=organization_id,
            employee_id=employee_id,
            geofence_id=geofence_id,
            valid_from=payload.valid_from,
        )
        database.add(assignment)

    assignment.valid_from = payload.valid_from
    assignment.valid_to = payload.valid_to
    assignment.shift_start_time = payload.shift_start_time
    assignment.shift_end_time = payload.shift_end_time
    assignment.grace_minutes = payload.grace_minutes
    assignment.is_primary = payload.is_primary
    assignment.is_active = True

    database.commit()
    database.refresh(assignment)
    return assignment


def list_employee_assignments(
    database: Session,
    *,
    organization_id: UUID,
    employee_id: UUID,
) -> list[EmployeeGeofenceAssignment]:
    return list(
        database.scalars(
            select(EmployeeGeofenceAssignment)
            .where(
                EmployeeGeofenceAssignment.organization_id == organization_id,
                EmployeeGeofenceAssignment.employee_id == employee_id,
            )
            .order_by(
                EmployeeGeofenceAssignment.is_primary.desc(),
                EmployeeGeofenceAssignment.valid_from.desc(),
            )
        ).all()
    )
