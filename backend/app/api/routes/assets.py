from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.assets import (
    OutletCreateRequest,
    OutletResponse,
    OutletUpdateRequest,
    PropertyCreateRequest,
    PropertyResponse,
    PropertyUpdateRequest,
    RenewalItem,
    VehicleCreateRequest,
    VehicleResponse,
    VehicleUpdateRequest,
)
from app.services.asset_service import (
    create_outlet,
    create_property,
    create_vehicle,
    list_outlets,
    list_properties,
    list_vehicles,
    upcoming_renewals,
    update_outlet,
    update_property,
    update_vehicle,
)


router = APIRouter(
    prefix="/assets",
    tags=["Assets and Renewals"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/vehicles",
    response_model=VehicleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_vehicle_record(
    payload: VehicleCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> VehicleResponse:
    return create_vehicle(
        database,
        user=current_user,
        payload=payload,
    )


@router.get(
    "/vehicles",
    response_model=list[VehicleResponse],
)
def read_vehicles(
    current_user: CurrentUser,
    database: DatabaseSession,
) -> list[VehicleResponse]:
    return list_vehicles(
        database,
        user=current_user,
    )


@router.patch(
    "/vehicles/{vehicle_id}",
    response_model=VehicleResponse,
)
def edit_vehicle(
    vehicle_id: UUID,
    payload: VehicleUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> VehicleResponse:
    return update_vehicle(
        database,
        user=current_user,
        vehicle_id=vehicle_id,
        payload=payload,
    )


@router.post(
    "/properties",
    response_model=PropertyResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_property_record(
    payload: PropertyCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> PropertyResponse:
    return create_property(
        database,
        user=current_user,
        payload=payload,
    )


@router.get(
    "/properties",
    response_model=list[PropertyResponse],
)
def read_properties(
    current_user: CurrentUser,
    database: DatabaseSession,
) -> list[PropertyResponse]:
    return list_properties(
        database,
        user=current_user,
    )


@router.patch(
    "/properties/{property_id}",
    response_model=PropertyResponse,
)
def edit_property(
    property_id: UUID,
    payload: PropertyUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> PropertyResponse:
    return update_property(
        database,
        user=current_user,
        property_id=property_id,
        payload=payload,
    )


@router.post(
    "/outlets",
    response_model=OutletResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_outlet_record(
    payload: OutletCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> OutletResponse:
    return create_outlet(
        database,
        user=current_user,
        payload=payload,
    )


@router.get(
    "/outlets",
    response_model=list[OutletResponse],
)
def read_outlets(
    current_user: CurrentUser,
    database: DatabaseSession,
) -> list[OutletResponse]:
    return list_outlets(
        database,
        user=current_user,
    )


@router.patch(
    "/outlets/{outlet_id}",
    response_model=OutletResponse,
)
def edit_outlet(
    outlet_id: UUID,
    payload: OutletUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> OutletResponse:
    return update_outlet(
        database,
        user=current_user,
        outlet_id=outlet_id,
        payload=payload,
    )


@router.get(
    "/renewals/upcoming",
    response_model=list[RenewalItem],
)
def read_upcoming_renewals(
    current_user: CurrentUser,
    database: DatabaseSession,
    days: int = Query(default=60, ge=0, le=3650),
) -> list[RenewalItem]:
    return upcoming_renewals(
        database,
        user=current_user,
        days=days,
    )
