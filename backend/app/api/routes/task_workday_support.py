from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.services.task_workday_support import employee_readiness, list_team_assignments

router = APIRouter(tags=["Task oversight and Workday support"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/task-management/assignments")
def assignments(user: CurrentUser, database: DB, search: str = Query("", max_length=100),
                assignment_status: str | None = None, start_date: date | None = None, end_date: date | None = None,
                offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return list_team_assignments(database, user, search=search, assignment_status=assignment_status,
                                 start_date=start_date, end_date=end_date, offset=offset, limit=limit)


@router.get("/workday-support/employee")
def readiness(user: CurrentUser, database: DB):
    return employee_readiness(database, user)
