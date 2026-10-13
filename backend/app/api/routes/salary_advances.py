from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.salary_advance import (
    SalaryAdvanceCancelRequest,
    SalaryAdvanceCreateRequest,
    SalaryAdvanceDecisionRequest,
    SalaryAdvanceDisbursementRequest,
    SalaryAdvanceResponse,
)
from app.services.salary_advance_service import (
    cancel_salary_advance,
    create_salary_advance,
    decide_salary_advance,
    disburse_salary_advance,
    list_my_salary_advances,
    list_organization_salary_advances,
)


router = APIRouter(
    prefix="/salary-advances",
    tags=["Salary Advances"],
)
Database = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=SalaryAdvanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_salary_advance(
    payload: SalaryAdvanceCreateRequest,
    current_user: CurrentUser,
    database: Database,
):
    return create_salary_advance(database, current_user, payload)


@router.get(
    "/mine",
    response_model=list[SalaryAdvanceResponse],
)
def read_my_salary_advances(
    current_user: CurrentUser,
    database: Database,
):
    return list_my_salary_advances(database, current_user)


@router.get(
    "",
    response_model=list[SalaryAdvanceResponse],
)
def read_organization_salary_advances(
    current_user: CurrentUser,
    database: Database,
    status_filter: str | None = Query(default=None, alias="status"),
):
    return list_organization_salary_advances(
        database,
        current_user,
        status_filter,
    )


@router.post(
    "/{request_id}/decision",
    response_model=SalaryAdvanceResponse,
)
def review_salary_advance(
    request_id: UUID,
    payload: SalaryAdvanceDecisionRequest,
    current_user: CurrentUser,
    database: Database,
):
    return decide_salary_advance(
        database,
        current_user,
        request_id,
        payload,
    )


@router.post(
    "/{request_id}/disburse",
    response_model=SalaryAdvanceResponse,
)
def record_salary_advance_disbursement(
    request_id: UUID,
    payload: SalaryAdvanceDisbursementRequest,
    current_user: CurrentUser,
    database: Database,
):
    return disburse_salary_advance(
        database,
        current_user,
        request_id,
        payload,
    )


@router.post(
    "/{request_id}/cancel",
    response_model=SalaryAdvanceResponse,
)
def cancel_my_salary_advance(
    request_id: UUID,
    payload: SalaryAdvanceCancelRequest,
    current_user: CurrentUser,
    database: Database,
):
    return cancel_salary_advance(
        database,
        current_user,
        request_id,
        payload,
    )
