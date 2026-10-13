from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.fuel import (
    FuelIndentCreateRequest,
    FuelIndentResponse,
    FuelRecordRequest,
    VehicleFuelSummary,
)
from app.services.fuel_service import (
    cancel_fuel_indent,
    complete_fueling,
    create_fuel_indent,
    fuel_dashboard,
    list_fuel_indents,
    vehicle_history,
)


router = APIRouter(prefix="/fuel", tags=["Fuel and Mileage"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/dashboard", response_model=list[VehicleFuelSummary])
def read_dashboard(current_user: CurrentUser, database: DatabaseSession):
    return fuel_dashboard(database, user=current_user)


@router.get("/indents", response_model=list[FuelIndentResponse])
def read_indents(
    current_user: CurrentUser,
    database: DatabaseSession,
    vehicle_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
):
    return list_fuel_indents(
        database,
        user=current_user,
        vehicle_id=vehicle_id,
        status_filter=status_filter,
    )


@router.post("/indents", response_model=FuelIndentResponse, status_code=status.HTTP_201_CREATED)
def create_indent(
    payload: FuelIndentCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_fuel_indent(database, user=current_user, payload=payload)


@router.post("/indents/{indent_id}/fuel", response_model=FuelIndentResponse)
def fuel_indent(
    indent_id: UUID,
    payload: FuelRecordRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return complete_fueling(
        database,
        user=current_user,
        indent_id=indent_id,
        payload=payload,
    )


@router.post("/indents/{indent_id}/cancel", response_model=FuelIndentResponse)
def cancel_indent(
    indent_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return cancel_fuel_indent(
        database,
        user=current_user,
        indent_id=indent_id,
    )


@router.get("/vehicles/{vehicle_id}/history", response_model=list[FuelIndentResponse])
def read_vehicle_history(
    vehicle_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return vehicle_history(
        database,
        user=current_user,
        vehicle_id=vehicle_id,
    )
