from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.permissions import require_permissions
from app.db.session import get_db
from app.models import User
from app.schemas.geofences import (
    GeofenceAssignmentRequest,
    GeofenceAssignmentResponse,
    GeofenceCreateRequest,
    GeofenceResponse,
    GeofenceUpdateRequest,
)
from app.services.geofence_service import (
    assign_geofence,
    create_geofence,
    list_employee_assignments,
    list_geofences,
    update_geofence,
)


router = APIRouter(prefix="/geofences", tags=["Geofences"])
DatabaseSession = Annotated[Session, Depends(get_db)]
LocationAdministrator = Annotated[
    User,
    Depends(require_permissions("location.view_all")),
]


def require_location_admin(current_user: CurrentUser) -> User:
    if current_user.is_superuser or any(role.code == "ADMIN" for role in current_user.roles):
        return current_user
    raise HTTPException(status_code=403, detail="Only Admin can manage work locations and assignments.")


LocationWriter = Annotated[User, Depends(require_location_admin)]


@router.post("", response_model=GeofenceResponse, status_code=status.HTTP_201_CREATED)
def create_work_geofence(
    payload: GeofenceCreateRequest,
    authorized_user: LocationWriter,
    database: DatabaseSession,
):
    return create_geofence(database, user=authorized_user, payload=payload)


@router.get("", response_model=list[GeofenceResponse])
def read_geofences(
    authorized_user: LocationAdministrator,
    database: DatabaseSession,
    active_only: bool = Query(default=True),
):
    return list_geofences(
        database,
        organization_id=authorized_user.organization_id,
        active_only=active_only,
    )


@router.patch("/{geofence_id}", response_model=GeofenceResponse)
def edit_geofence(
    geofence_id: UUID,
    payload: GeofenceUpdateRequest,
    authorized_user: LocationWriter,
    database: DatabaseSession,
):
    return update_geofence(
        database,
        organization_id=authorized_user.organization_id,
        geofence_id=geofence_id,
        payload=payload,
    )


@router.post(
    "/{geofence_id}/assignments/{employee_id}",
    response_model=GeofenceAssignmentResponse,
)
def assign_employee_geofence(
    geofence_id: UUID,
    employee_id: UUID,
    payload: GeofenceAssignmentRequest,
    authorized_user: LocationWriter,
    database: DatabaseSession,
):
    return assign_geofence(
        database,
        organization_id=authorized_user.organization_id,
        employee_id=employee_id,
        geofence_id=geofence_id,
        payload=payload,
    )


@router.get(
    "/assignments/{employee_id}",
    response_model=list[GeofenceAssignmentResponse],
)
def read_employee_geofence_assignments(
    employee_id: UUID,
    authorized_user: LocationAdministrator,
    database: DatabaseSession,
):
    return list_employee_assignments(
        database,
        organization_id=authorized_user.organization_id,
        employee_id=employee_id,
    )
