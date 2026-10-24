from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.notifications import (
    BackgroundJobExecutionResponse,
    BackgroundJobResult,
    NotificationResponse,
)
from app.services.action_alert_service import get_action_counts
from app.services.account_sheet_verification_service import (
    enqueue_account_sheet_escalations,
)
from app.services.background_service import (
    dispatch_notifications,
    enqueue_renewal_notifications,
    generate_recurring_assignments,
    require_background_admin,
    run_logged_job,
)
from app.services.notification_service import (
    list_executions,
    list_my_notifications,
    delete_read_notifications,
    mark_read,
)
from app.services.workforce_policy_service import enqueue_policy_escalations


router = APIRouter(
    prefix="/background",
    tags=["Background Jobs and Notifications"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/notifications/me",
    response_model=list[NotificationResponse],
)
def read_my_notifications(
    current_user: CurrentUser,
    database: DatabaseSession,
    unread_only: bool = Query(default=False),
):
    return list_my_notifications(
        database,
        current_user,
        unread_only,
    )


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
)
def read_notification(
    notification_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return mark_read(
        database,
        current_user,
        notification_id,
    )


@router.get("/action-counts")
def read_action_counts(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return get_action_counts(database, current_user)


@router.post(
    "/jobs/run-recurring-tasks",
    response_model=BackgroundJobResult,
)
def run_recurring_tasks(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    require_background_admin(database, current_user)
    result = run_logged_job(
        database,
        "generate_recurring_tasks",
        "MANUAL",
        lambda: generate_recurring_assignments(database),
    )
    return {
        "job_name": "generate_recurring_tasks",
        "status": "SUCCESS",
        "result": result,
    }


@router.post(
    "/jobs/run-renewal-reminders",
    response_model=BackgroundJobResult,
)
def run_renewals(
    current_user: CurrentUser,
    database: DatabaseSession,
    days: int = Query(default=60, ge=1, le=3650),
):
    require_background_admin(database, current_user)
    result = run_logged_job(
        database,
        "enqueue_renewal_reminders",
        "MANUAL",
        lambda: enqueue_renewal_notifications(database, days),
    )
    return {
        "job_name": "enqueue_renewal_reminders",
        "status": "SUCCESS",
        "result": result,
    }


@router.post(
    "/jobs/dispatch-notifications",
    response_model=BackgroundJobResult,
)
def dispatch_now(
    current_user: CurrentUser,
    database: DatabaseSession,
    batch_size: int = Query(default=100, ge=1, le=1000),
):
    require_background_admin(database, current_user)
    result = run_logged_job(
        database,
        "dispatch_notifications",
        "MANUAL",
        lambda: dispatch_notifications(database, batch_size),
    )
    return {
        "job_name": "dispatch_notifications",
        "status": "SUCCESS",
        "result": result,
    }


@router.post(
    "/jobs/run-workforce-policy-escalations",
    response_model=BackgroundJobResult,
)
def run_workforce_policy_escalations(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    require_background_admin(database, current_user)
    result = run_logged_job(
        database,
        "workforce_policy_escalations",
        "MANUAL",
        lambda: enqueue_policy_escalations(database),
    )
    return {
        "job_name": "workforce_policy_escalations",
        "status": "SUCCESS",
        "result": result,
    }


@router.post(
    "/jobs/run-account-sheet-escalations",
    response_model=BackgroundJobResult,
)
def run_account_sheet_escalations(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    require_background_admin(database, current_user)
    result = run_logged_job(
        database,
        "account_sheet_discrepancy_escalations",
        "MANUAL",
        lambda: enqueue_account_sheet_escalations(database),
    )
    return {
        "job_name": "account_sheet_discrepancy_escalations",
        "status": "SUCCESS",
        "result": result,
    }


@router.get(
    "/jobs/executions",
    response_model=list[BackgroundJobExecutionResponse],
)
def read_job_executions(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_executions(database, current_user)


@router.delete("/notifications/read")
def delete_my_read_notifications(current_user: CurrentUser, database: DatabaseSession):
    return delete_read_notifications(database, current_user)

# attendance-notifications-cleanup-v1
