from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.workforce_policy import (
    DecisionRequest,
    DutyExitCreateRequest,
    InspectionLateStartCreateRequest,
    NoticePeriodCreateRequest,
    NoticePeriodEndRequest,
    WorkPolicyUpdateRequest,
)
from app.services.workforce_policy_service import (
    cancel_notice_period,
    create_duty_exit_request,
    create_inspection_late_start_request,
    create_notice_period,
    decide_duty_exit,
    decide_inspection_late_start,
    end_lunch_break,
    get_my_day_state,
    get_work_policy,
    list_inspection_late_start_requests,
    list_my_duty_exit_requests,
    list_notice_periods,
    list_organization_duty_exit_requests,
    policy_dict,
    return_from_duty_exit,
    start_duty_exit,
    start_lunch_break,
    update_work_policy,
)


router = APIRouter(
    prefix="/workforce-policy",
    tags=["Workforce Policy Controls"],
)
Database = Annotated[Session, Depends(get_db)]


@router.get("/settings")
def read_settings(current_user: CurrentUser, database: Database):
    return policy_dict(get_work_policy(database, current_user))


@router.put("/settings")
def save_settings(
    payload: WorkPolicyUpdateRequest,
    current_user: CurrentUser,
    database: Database,
):
    return update_work_policy(database, current_user, payload)


@router.get("/me/day")
def read_my_day(current_user: CurrentUser, database: Database):
    return get_my_day_state(database, current_user)


@router.post("/lunch/start", status_code=status.HTTP_201_CREATED)
def begin_lunch(current_user: CurrentUser, database: Database):
    return start_lunch_break(database, current_user)


@router.post("/lunch/end")
def finish_lunch(current_user: CurrentUser, database: Database):
    return end_lunch_break(database, current_user)


@router.post("/duty-exits", status_code=status.HTTP_201_CREATED)
def request_duty_exit(
    payload: DutyExitCreateRequest,
    current_user: CurrentUser,
    database: Database,
):
    return create_duty_exit_request(database, current_user, payload.reason)


@router.get("/duty-exits/mine")
def read_my_duty_exits(current_user: CurrentUser, database: Database):
    return list_my_duty_exit_requests(database, current_user)


@router.get("/duty-exits")
def read_duty_exits(
    current_user: CurrentUser,
    database: Database,
    status_filter: str | None = Query(default=None, alias="status"),
):
    return list_organization_duty_exit_requests(
        database, current_user, status_filter
    )


@router.post("/duty-exits/{request_id}/decision")
def review_duty_exit(
    request_id: UUID,
    payload: DecisionRequest,
    current_user: CurrentUser,
    database: Database,
):
    return decide_duty_exit(database, current_user, request_id, payload)


@router.post("/duty-exits/{request_id}/start")
def begin_duty_exit(
    request_id: UUID,
    current_user: CurrentUser,
    database: Database,
):
    return start_duty_exit(database, current_user, request_id)


@router.post("/duty-exits/{request_id}/return")
def finish_duty_exit(
    request_id: UUID,
    current_user: CurrentUser,
    database: Database,
):
    return return_from_duty_exit(database, current_user, request_id)


@router.get("/notice-periods")
def read_notice_periods(current_user: CurrentUser, database: Database):
    return list_notice_periods(database, current_user)


@router.post("/notice-periods", status_code=status.HTTP_201_CREATED)
def add_notice_period(
    payload: NoticePeriodCreateRequest,
    current_user: CurrentUser,
    database: Database,
):
    return create_notice_period(database, current_user, payload)


@router.post("/notice-periods/{notice_id}/cancel")
def cancel_notice(
    notice_id: UUID,
    payload: NoticePeriodEndRequest,
    current_user: CurrentUser,
    database: Database,
):
    return cancel_notice_period(database, current_user, notice_id, payload)


@router.get("/inspection-late-starts")
def read_late_inspection_starts(
    current_user: CurrentUser,
    database: Database,
):
    return list_inspection_late_start_requests(database, current_user)


@router.post(
    "/inspection-late-starts",
    status_code=status.HTTP_201_CREATED,
)
def request_late_inspection_start(
    payload: InspectionLateStartCreateRequest,
    current_user: CurrentUser,
    database: Database,
):
    return create_inspection_late_start_request(database, current_user, payload)


@router.post("/inspection-late-starts/{request_id}/decision")
def review_late_inspection_start(
    request_id: UUID,
    payload: DecisionRequest,
    current_user: CurrentUser,
    database: Database,
):
    return decide_inspection_late_start(
        database, current_user, request_id, payload
    )
