from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AccountSheetVerificationItem,
    AttendanceRecord,
    Employee,
    ExpenseClaim,
    InspectionReport,
    LeaveRequest,
    OvertimeClaim,
    PasswordResetApproval,
    Task,
    TaskAssignment,
    User,
)
from app.services.security_overtime_service import require_role


MAX_REPORT_DAYS = 7


def _zone(user: User) -> ZoneInfo:
    name = getattr(getattr(user, "organization", None), "timezone", None)
    try:
        return ZoneInfo(name or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def _day_bounds(target: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(target, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = (datetime.combine(target, time.min, tzinfo=zone) + timedelta(days=1)).astimezone(
        timezone.utc
    )
    return start, end


def _minutes_label(value: int) -> str:
    hours, minutes = divmod(max(0, int(value)), 60)
    return f"{hours}h {minutes}m"


def _employee_roster(database: Session, organization_id: UUID):
    return list(
        database.execute(
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .where(
                Employee.organization_id == organization_id,
                User.is_active.is_(True),
            )
            .order_by(User.employee_code)
        ).all()
    )


def build_md_daily_report(
    database: Session,
    *,
    user: User,
    target: date,
) -> dict:
    require_role(database, user, "MD")
    zone = _zone(user)
    today = datetime.now(zone).date()
    oldest = today - timedelta(days=MAX_REPORT_DAYS - 1)
    if target < oldest or target > today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="MD daily reports are limited to today and the previous six days.",
        )

    start_utc, end_utc = _day_bounds(target, zone)
    roster = _employee_roster(database, user.organization_id)
    roster_ids = {employee.id for employee, _ in roster}

    attendance_rows = list(
        database.execute(
            select(AttendanceRecord, Employee, User)
            .join(Employee, AttendanceRecord.employee_id == Employee.id)
            .join(User, Employee.user_id == User.id)
            .where(
                AttendanceRecord.organization_id == user.organization_id,
                AttendanceRecord.attendance_date == target,
            )
            .order_by(User.employee_code)
        ).all()
    )
    attendance_ids = {record.employee_id for record, _, _ in attendance_rows}
    attendance_details = [
        {
            "employee_code": account.employee_code,
            "employee_name": employee.full_name,
            "status": record.status,
            "check_in_at": record.check_in_at,
            "check_out_at": record.check_out_at,
            "worked_minutes": int(record.worked_minutes or 0),
            "worked_label": _minutes_label(record.worked_minutes or 0),
            "late_minutes": int(record.late_minutes or 0),
        }
        for record, employee, account in attendance_rows
    ]
    absent_people = [
        {"employee_code": account.employee_code, "employee_name": employee.full_name}
        for employee, account in roster
        if employee.id not in attendance_ids
    ]

    completed_rows = list(
        database.execute(
            select(TaskAssignment, Task, Employee, User)
            .join(Task, TaskAssignment.task_id == Task.id)
            .join(Employee, TaskAssignment.employee_id == Employee.id)
            .join(User, Employee.user_id == User.id)
            .where(
                TaskAssignment.organization_id == user.organization_id,
                TaskAssignment.completed_at >= start_utc,
                TaskAssignment.completed_at < end_utc,
            )
            .order_by(TaskAssignment.completed_at.desc())
        ).all()
    )
    completed_tasks = [
        {
            "title": task.title,
            "employee_code": account.employee_code,
            "employee_name": employee.full_name,
            "completed_at": assignment.completed_at,
            "completion_note": assignment.completion_note,
        }
        for assignment, task, employee, account in completed_rows
    ]

    pending_rows = list(
        database.execute(
            select(TaskAssignment, Task, Employee, User)
            .join(Task, TaskAssignment.task_id == Task.id)
            .join(Employee, TaskAssignment.employee_id == Employee.id)
            .join(User, Employee.user_id == User.id)
            .where(
                TaskAssignment.organization_id == user.organization_id,
                TaskAssignment.scheduled_for <= target,
                TaskAssignment.created_at < end_utc,
                TaskAssignment.status != "CANCELLED",
                (
                    TaskAssignment.completed_at.is_(None)
                    | (TaskAssignment.completed_at >= end_utc)
                ),
            )
            .order_by(TaskAssignment.due_at.asc().nullslast())
        ).all()
    )
    pending_tasks = [
        {
            "title": task.title,
            "employee_code": account.employee_code,
            "employee_name": employee.full_name,
            "status": assignment.status,
            "due_at": assignment.due_at,
            "overdue": bool(assignment.due_at and assignment.due_at < end_utc),
        }
        for assignment, task, employee, account in pending_rows
    ]

    approved_leave = int(
        database.scalar(
            select(func.count(LeaveRequest.id)).where(
                LeaveRequest.organization_id == user.organization_id,
                LeaveRequest.status == "APPROVED",
                LeaveRequest.start_date <= target,
                LeaveRequest.end_date >= target,
            )
        )
        or 0
    )
    submitted_expenses = int(
        database.scalar(
            select(func.count(ExpenseClaim.id)).where(
                ExpenseClaim.organization_id == user.organization_id,
                ExpenseClaim.submitted_at >= start_utc,
                ExpenseClaim.submitted_at < end_utc,
            )
        )
        or 0
    )
    completed_inspections = int(
        database.scalar(
            select(func.count(InspectionReport.id)).where(
                InspectionReport.organization_id == user.organization_id,
                InspectionReport.submitted_at >= start_utc,
                InspectionReport.submitted_at < end_utc,
            )
        )
        or 0
    )
    overtime_rows = list(
        database.execute(
            select(OvertimeClaim, Employee, User)
            .join(Employee, OvertimeClaim.employee_id == Employee.id)
            .join(User, Employee.user_id == User.id)
            .where(
                OvertimeClaim.organization_id == user.organization_id,
                OvertimeClaim.work_date == target,
            )
            .order_by(User.employee_code)
        ).all()
    )
    overtime_details = [
        {
            "employee_code": account.employee_code,
            "employee_name": employee.full_name,
            "overtime_minutes": claim.overtime_minutes,
            "status": claim.status,
            "approved_amount": claim.approved_amount,
        }
        for claim, employee, account in overtime_rows
    ]

    pending_security = pending_overtime = open_discrepancies = 0
    if target == today:
        pending_security = int(
            database.scalar(
                select(func.count(PasswordResetApproval.id)).where(
                    PasswordResetApproval.organization_id == user.organization_id,
                    PasswordResetApproval.status == "PENDING_MD",
                )
            )
            or 0
        )
        pending_overtime = int(
            database.scalar(
                select(func.count(OvertimeClaim.id)).where(
                    OvertimeClaim.organization_id == user.organization_id,
                    OvertimeClaim.status == "PENDING_MD",
                )
            )
            or 0
        )
        open_discrepancies = int(
            database.scalar(
                select(func.count(AccountSheetVerificationItem.id)).where(
                    AccountSheetVerificationItem.organization_id
                    == user.organization_id,
                    AccountSheetVerificationItem.issue_status == "OPEN",
                )
            )
            or 0
        )

    late_count = sum(1 for row in attendance_details if row["late_minutes"] > 0)
    qualifying_late_count = sum(
        1 for row in attendance_details if row["late_minutes"] >= 30
    )
    total_work_minutes = sum(row["worked_minutes"] for row in attendance_details)
    overdue_count = sum(1 for row in pending_tasks if row["overdue"])

    attention_items: list[str] = []
    if absent_people:
        attention_items.append(
            f"Follow up on {len(absent_people)} employee(s) with no attendance record."
        )
    if qualifying_late_count:
        attention_items.append(
            f"Review {qualifying_late_count} check-in(s) delayed by at least 30 minutes after grace."
        )
    if overdue_count:
        attention_items.append(f"Prioritize {overdue_count} overdue task(s).")
    if pending_security:
        attention_items.append(
            f"Decide {pending_security} pending password reset approval(s)."
        )
    if pending_overtime:
        attention_items.append(f"Decide {pending_overtime} verified OT claim(s).")
    if open_discrepancies:
        attention_items.append(
            f"Review {open_discrepancies} unresolved accounts discrepancy item(s)."
        )
    if not attention_items:
        attention_items.append("No high-priority exception was detected for this day.")

    return {
        "report_date": target,
        "generated_at": datetime.now(timezone.utc),
        "organization_code": user.organization.code,
        "organization_name": user.organization.name,
        "is_today": target == today,
        "summary": {
            "active_employees": len(roster_ids),
            "attendance_records": len(attendance_details),
            "no_attendance_record": len(absent_people),
            "late_employees": late_count,
            "qualifying_late_employees": qualifying_late_count,
            "total_work_minutes": total_work_minutes,
            "total_work_label": _minutes_label(total_work_minutes),
            "tasks_completed": len(completed_rows),
            "tasks_pending": len(pending_rows),
            "tasks_overdue": overdue_count,
            "approved_leave": approved_leave,
            "expense_claims_submitted": submitted_expenses,
            "inspections_completed": completed_inspections,
            "overtime_claims": len(overtime_rows),
            "pending_password_resets": pending_security,
            "pending_md_overtime": pending_overtime,
            "open_accounts_discrepancies": open_discrepancies,
        },
        "attention_items": attention_items,
        "attendance": attendance_details,
        "employees_without_attendance": absent_people,
        "performed_tasks": completed_tasks,
        "pending_tasks": pending_tasks,
        "overtime": overtime_details,
    }


def list_md_daily_reports(database: Session, *, user: User) -> list[dict]:
    require_role(database, user, "MD")
    today = datetime.now(_zone(user)).date()
    return [
        build_md_daily_report(database, user=user, target=today - timedelta(days=offset))
        for offset in range(MAX_REPORT_DAYS)
    ]
