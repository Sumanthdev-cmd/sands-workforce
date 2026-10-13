from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import User


TABLE_QUERIES = {
    "employees": "SELECT COUNT(*) FROM employees WHERE organization_id = :org",
    "active_tasks": "SELECT COUNT(*) FROM tasks WHERE organization_id = :org AND status = 'ACTIVE'",
    "pending_leave_requests": "SELECT COUNT(*) FROM leave_requests WHERE organization_id = :org AND status = 'PENDING'",
    "pending_expense_claims": "SELECT COUNT(*) FROM expense_claims WHERE organization_id = :org AND status IN ('SUBMITTED','VERIFIED')",
    "pending_appointments": "SELECT COUNT(*) FROM appointments WHERE organization_id = :org AND status = 'PENDING'",
    "pending_document_approvals": "SELECT COUNT(*) FROM document_approval_requests WHERE organization_id = :org AND status = 'PENDING'",
    "open_vendor_issues": "SELECT COUNT(*) FROM vendor_issues WHERE organization_id = :org AND status IN ('OPEN','IN_REVIEW')",
    "pending_labour_payments": "SELECT COUNT(*) FROM external_labour_payments WHERE organization_id = :org AND status IN ('PENDING_MD','APPROVED')",
    "available_company_assets": "SELECT COUNT(*) FROM company_assets WHERE organization_id = :org AND status = 'AVAILABLE'",
    "assigned_company_assets": "SELECT COUNT(*) FROM company_assets WHERE organization_id = :org AND status = 'ASSIGNED'",
    "open_asset_maintenance": "SELECT COUNT(*) FROM asset_maintenance_records WHERE organization_id = :org AND status = 'OPEN'",
    "open_vacancies": "SELECT COUNT(*) FROM job_vacancies WHERE organization_id = :org AND status = 'OPEN'",
    "pending_applications": "SELECT COUNT(*) FROM job_applications WHERE organization_id = :org AND status IN ('PENDING_SCREENING','NEEDS_REVIEW')",
    "unread_notifications": "SELECT COUNT(*) FROM notifications WHERE organization_id = :org AND recipient_user_id = :user AND channel = 'IN_APP' AND read_at IS NULL",
}


def table_exists(database: Session, table_name: str) -> bool:
    return bool(
        database.scalar(
            text("SELECT to_regclass(:table_name) IS NOT NULL"),
            {"table_name": f"public.{table_name}"},
        )
    )


def scalar_count(database: Session, query: str, user: User) -> int:
    return int(
        database.scalar(
            text(query),
            {"org": user.organization_id, "user": user.id},
        )
        or 0
    )


def management_overview(database: Session, *, user: User) -> dict:
    result = {
        "organization_id": str(user.organization_id),
        "generated_for_user_id": str(user.id),
        "date": date.today().isoformat(),
    }

    for key, query in TABLE_QUERIES.items():
        table_name = query.split(" FROM ", 1)[1].split(" ", 1)[0]
        if table_exists(database, table_name):
            result[key] = scalar_count(database, query, user)
        else:
            result[key] = None

    if table_exists(database, "attendance_records"):
        result["attendance_today"] = int(
            database.scalar(
                text(
                    "SELECT COUNT(*) FROM attendance_records "
                    "WHERE organization_id = :org AND attendance_date = :today"
                ),
                {"org": user.organization_id, "today": date.today()},
            )
            or 0
        )
    else:
        result["attendance_today"] = None

    return result


def management_alerts(database: Session, *, user: User) -> dict:
    overview = management_overview(database, user=user)
    alerts = []

    alert_map = {
        "pending_leave_requests": "Pending leave requests",
        "pending_expense_claims": "Pending expense claims",
        "pending_appointments": "Pending MD appointments",
        "pending_document_approvals": "Pending document approvals",
        "open_vendor_issues": "Open vendor issues",
        "pending_labour_payments": "Pending external labour payments",
        "open_asset_maintenance": "Open asset maintenance records",
        "pending_applications": "Recruitment applications needing action",
        "unread_notifications": "Unread notifications",
    }

    for key, label in alert_map.items():
        value = overview.get(key)
        if isinstance(value, int) and value > 0:
            alerts.append({"code": key, "label": label, "count": value})

    return {
        "organization_id": str(user.organization_id),
        "alert_count": len(alerts),
        "alerts": sorted(alerts, key=lambda item: item["count"], reverse=True),
    }
