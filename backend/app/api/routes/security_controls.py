from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.security_overtime import (
    LateAttendanceActionResponse,
    LateSalaryHoldRelease,
    PasswordResetComplete,
    PasswordResetDecision,
    PasswordResetRequestCreate,
    PasswordResetRequestResponse,
)
from app.services.security_overtime_service import (
    complete_password_reset_request,
    create_password_reset_request,
    decide_password_reset_request,
    list_late_attendance_actions,
    list_password_reset_requests,
    release_late_salary_hold,
)


router = APIRouter(prefix="/security", tags=["Security Controls"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/password-reset-requests",
    response_model=PasswordResetRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_password_reset(
    payload: PasswordResetRequestCreate,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_password_reset_request(database, user=current_user, payload=payload)


@router.get(
    "/password-reset-requests",
    response_model=list[PasswordResetRequestResponse],
)
def read_password_reset_requests(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_password_reset_requests(database, user=current_user)


@router.post(
    "/password-reset-requests/{request_id}/decision",
    response_model=PasswordResetRequestResponse,
)
def decide_password_reset(
    request_id: UUID,
    payload: PasswordResetDecision,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return decide_password_reset_request(
        database,
        user=current_user,
        request_id=request_id,
        payload=payload,
    )


@router.post(
    "/password-reset-requests/{request_id}/complete",
    response_model=PasswordResetRequestResponse,
)
def complete_password_reset(
    request_id: UUID,
    payload: PasswordResetComplete,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return complete_password_reset_request(
        database,
        user=current_user,
        request_id=request_id,
        temporary_password=payload.temporary_password,
    )


@router.get(
    "/late-attendance-actions",
    response_model=list[LateAttendanceActionResponse],
)
def read_late_attendance_actions(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_late_attendance_actions(database, user=current_user)


@router.post(
    "/late-attendance-actions/{action_id}/release-hold",
    response_model=LateAttendanceActionResponse,
)
def release_automatic_late_hold(
    action_id: UUID,
    payload: LateSalaryHoldRelease,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return release_late_salary_hold(
        database,
        user=current_user,
        action_id=action_id,
        note=payload.note,
    )
