from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.permissions import require_permissions
from app.db.session import get_db
from app.models import User
from app.schemas.locations import (
    LiveLocationResponse,
    LocationBatchRequest,
    LocationBatchResponse,
    LocationHistoryResponse,
    LocationRosterResponse,
    OwnLatestLocationResponse,
)
from app.services.location_service import (
    get_own_latest_location,
    list_live_locations,
    list_location_history,
    list_location_roster,
    submit_location_batch,
)


router = APIRouter(prefix="/locations", tags=["Locations"])
DatabaseSession = Annotated[Session, Depends(get_db)]
LocationViewer = Annotated[
    User,
    Depends(require_permissions("location.view_all")),
]


@router.post("/batch", response_model=LocationBatchResponse)
def push_location_batch(
    payload: LocationBatchRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> LocationBatchResponse:
    accepted_count, duplicate_count, latest_at = submit_location_batch(
        database,
        user=current_user,
        payload=payload,
    )

    return LocationBatchResponse(
        accepted_count=accepted_count,
        duplicate_count=duplicate_count,
        latest_recorded_at=latest_at,
    )


@router.get("/me/latest", response_model=OwnLatestLocationResponse)
def read_own_latest_location(
    current_user: CurrentUser,
    database: DatabaseSession,
) -> OwnLatestLocationResponse:
    return get_own_latest_location(database, user=current_user)


@router.get("/live", response_model=list[LiveLocationResponse])
def read_live_locations(
    authorized_user: LocationViewer,
    database: DatabaseSession,
) -> list[LiveLocationResponse]:
    return list_live_locations(
        database,
        organization_id=authorized_user.organization_id,
    )


@router.get("/roster", response_model=list[LocationRosterResponse])
def read_location_roster(
    authorized_user: LocationViewer,
    database: DatabaseSession,
) -> list[LocationRosterResponse]:
    return list_location_roster(
        database,
        organization_id=authorized_user.organization_id,
    )


@router.get(
    "/employees/{employee_id}/history",
    response_model=list[LocationHistoryResponse],
)
def read_employee_location_history(
    employee_id: UUID,
    authorized_user: LocationViewer,
    database: DatabaseSession,
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[LocationHistoryResponse]:
    return list_location_history(
        database,
        organization_id=authorized_user.organization_id,
        employee_id=employee_id,
        start_at=start_at,
        end_at=end_at,
        limit=limit,
    )
