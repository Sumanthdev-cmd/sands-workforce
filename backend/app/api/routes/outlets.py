from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.inspection import InspectionReportResponse
from app.schemas.outlets import (
    FieldVisitorOption,
    OutletCreateRequest,
    OutletInspectionOption,
    OutletResponse,
    OutletUpdateRequest,
)
from app.services.outlet_service import (
    assign_field_visitor,
    create_outlet,
    field_visitor_options,
    inspection_options,
    list_outlets,
    outlet_inspections,
    read_outlet,
    unassign_field_visitor,
    update_outlet,
)


router = APIRouter(prefix="/outlets", tags=["Shops and Outlets"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[OutletResponse])
def get_outlets(current_user: CurrentUser, database: DatabaseSession):
    return list_outlets(database, user=current_user)


@router.post("", response_model=OutletResponse, status_code=status.HTTP_201_CREATED)
def add_outlet(
    payload: OutletCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_outlet(database, user=current_user, payload=payload)


@router.get("/inspection-options", response_model=list[OutletInspectionOption])
def get_inspection_options(current_user: CurrentUser, database: DatabaseSession):
    return inspection_options(database, user=current_user)


@router.get("/field-visitors/options", response_model=list[FieldVisitorOption])
def get_field_visitor_options(current_user: CurrentUser, database: DatabaseSession):
    return field_visitor_options(database, user=current_user)


@router.get("/{outlet_id}", response_model=OutletResponse)
def get_outlet(outlet_id: UUID, current_user: CurrentUser, database: DatabaseSession):
    return read_outlet(database, user=current_user, outlet_id=outlet_id)


@router.patch("/{outlet_id}", response_model=OutletResponse)
def edit_outlet(
    outlet_id: UUID,
    payload: OutletUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return update_outlet(
        database,
        user=current_user,
        outlet_id=outlet_id,
        payload=payload,
    )


@router.post(
    "/{outlet_id}/field-visitors/{employee_id}",
    response_model=OutletResponse,
)
def assign_visitor(
    outlet_id: UUID,
    employee_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return assign_field_visitor(
        database,
        user=current_user,
        outlet_id=outlet_id,
        employee_id=employee_id,
    )


@router.delete(
    "/{outlet_id}/field-visitors/{assignment_id}",
    response_model=OutletResponse,
)
def unassign_visitor(
    outlet_id: UUID,
    assignment_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return unassign_field_visitor(
        database,
        user=current_user,
        outlet_id=outlet_id,
        assignment_id=assignment_id,
    )


@router.get(
    "/{outlet_id}/inspections",
    response_model=list[InspectionReportResponse],
)
def get_outlet_inspections(
    outlet_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return outlet_inspections(
        database,
        user=current_user,
        outlet_id=outlet_id,
    )
