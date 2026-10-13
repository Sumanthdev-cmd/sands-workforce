from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.services.management_dashboard_service import (
    management_alerts,
    management_overview,
)
from app.services.md_daily_report_service import (
    build_md_daily_report,
    list_md_daily_reports,
)


router = APIRouter(
    prefix="/dashboard/management",
    tags=["Management Dashboard"],
)
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/overview")
def read_management_overview(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return management_overview(database, user=current_user)


@router.get("/alerts")
def read_management_alerts(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return management_alerts(database, user=current_user)


@router.get("/daily-reports")
def read_md_daily_reports(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_md_daily_reports(database, user=current_user)


@router.get("/daily-reports/{report_date}")
def read_md_daily_report(
    report_date: date,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return build_md_daily_report(
        database,
        user=current_user,
        target=report_date,
    )
