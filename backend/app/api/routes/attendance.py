from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.permissions import require_permissions
from app.db.session import get_db
from app.models import User
from app.schemas.attendance import (
    AdminAttendanceResponse,
    AttendanceActionRequest,
    AttendanceEvaluationResponse,
    AttendanceRecordResponse,
)
from app.services.attendance_service import (
    evaluate_attendance,
    get_today_attendance,
    list_organization_attendance,
    list_own_attendance,
    perform_check_in,
    perform_check_out,
)


router = APIRouter(prefix="/attendance", tags=["Attendance"])
DatabaseSession = Annotated[Session, Depends(get_db)]
AttendanceAdministrator = Annotated[
    User,
    Depends(require_permissions("attendance.view_all")),
]


@router.post("/check-in", response_model=AttendanceRecordResponse)
def check_in(
    payload: AttendanceActionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return perform_check_in(
        database,
        user=current_user,
        automatic=payload.automatic,
    )


@router.post("/check-out", response_model=AttendanceRecordResponse)
def check_out(
    payload: AttendanceActionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return perform_check_out(
        database,
        user=current_user,
        automatic=payload.automatic,
    )


@router.post("/auto-evaluate", response_model=AttendanceEvaluationResponse)
def auto_evaluate(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    action, message, inside, distance, attendance = evaluate_attendance(
        database,
        user=current_user,
    )
    return AttendanceEvaluationResponse(
        action=action,
        message=message,
        inside_geofence=inside,
        distance_meters=round(distance, 2),
        attendance=attendance,
    )


@router.get(
    "/me/today",
    response_model=AttendanceRecordResponse | None,
)
def read_today_attendance(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return get_today_attendance(database, user=current_user)


@router.get("/me", response_model=list[AttendanceRecordResponse])
def read_own_attendance(
    current_user: CurrentUser,
    database: DatabaseSession,
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
):
    return list_own_attendance(
        database,
        user=current_user,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("", response_model=list[AdminAttendanceResponse])
def read_organization_attendance(
    authorized_user: AttendanceAdministrator,
    database: DatabaseSession,
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    employee_id: UUID | None = Query(default=None),
):
    return list_organization_attendance(
        database,
        organization_id=authorized_user.organization_id,
        start_date=start_date,
        end_date=end_date,
        employee_id=employee_id,
    )
