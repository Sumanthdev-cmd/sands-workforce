from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.inventory_asset import (
    AssetAssignRequest,
    AssetAssignmentResponse,
    AssetReturnRequest,
    CompanyAssetCreateRequest,
    CompanyAssetResponse,
    CompanyAssetUpdateRequest,
    MaintenanceCompleteRequest,
    MaintenanceCreateRequest,
    MaintenanceResponse,
)
from app.services.inventory_asset_service import (
    assign_asset,
    complete_maintenance,
    create_asset,
    create_maintenance,
    list_assets,
    list_assignments,
    list_maintenance,
    list_my_assignments,
    return_asset,
    update_asset,
)


router = APIRouter(
    prefix="/asset-inventory",
    tags=["Company Asset Inventory"],
)
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/assets",
    response_model=CompanyAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_asset(
    payload: CompanyAssetCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_asset(database, user=current_user, payload=payload)


@router.get("/assets", response_model=list[CompanyAssetResponse])
def read_assets(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_assets(database, user=current_user)


@router.patch(
    "/assets/{asset_id}",
    response_model=CompanyAssetResponse,
)
def edit_asset(
    asset_id: UUID,
    payload: CompanyAssetUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return update_asset(
        database,
        user=current_user,
        asset_id=asset_id,
        payload=payload,
    )


@router.post(
    "/assets/{asset_id}/assign",
    response_model=AssetAssignmentResponse,
)
def assign_company_asset(
    asset_id: UUID,
    payload: AssetAssignRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return assign_asset(
        database,
        user=current_user,
        asset_id=asset_id,
        payload=payload,
    )


@router.post(
    "/assignments/{assignment_id}/return",
    response_model=AssetAssignmentResponse,
)
def return_company_asset(
    assignment_id: UUID,
    payload: AssetReturnRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return return_asset(
        database,
        user=current_user,
        assignment_id=assignment_id,
        payload=payload,
    )


@router.get(
    "/assignments",
    response_model=list[AssetAssignmentResponse],
)
def read_assignments(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_assignments(database, user=current_user)


@router.get(
    "/assignments/me",
    response_model=list[AssetAssignmentResponse],
)
def read_my_assignments(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_my_assignments(database, user=current_user)


@router.post(
    "/maintenance",
    response_model=MaintenanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_maintenance(
    payload: MaintenanceCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_maintenance(database, user=current_user, payload=payload)


@router.get(
    "/maintenance",
    response_model=list[MaintenanceResponse],
)
def read_maintenance(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_maintenance(database, user=current_user)


@router.post(
    "/maintenance/{maintenance_id}/complete",
    response_model=MaintenanceResponse,
)
def finish_maintenance(
    maintenance_id: UUID,
    payload: MaintenanceCompleteRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return complete_maintenance(
        database,
        user=current_user,
        maintenance_id=maintenance_id,
        payload=payload,
    )
