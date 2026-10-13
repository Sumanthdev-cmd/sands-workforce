from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.models import Role, User, user_roles
from app.services.notification_service import (
    queue_role_notifications,
    queue_user_notification,
)

MANAGEMENT_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}
TASK_OVERDUE_REMINDER_HOURS = 24
TASK_OVERDUE_ESCALATION_HOURS = 48


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def _count(database: Session, sql: str, **params) -> int:
    value = database.execute(text(sql), params).scalar()
    return int(value or 0)



def _task_timezone(user: User) -> ZoneInfo:
    timezone_name = (
        getattr(
            getattr(
                user,
                "organization",
                None,
            ),
            "timezone",
            None,
        )
        or "Asia/Kolkata"
    )

    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def _duration_label(seconds: float) -> str:
    total = max(0, int(seconds))

    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []

    if days:
        parts.append(
            f"{days} day{'s' if days != 1 else ''}"
        )

    if hours:
        parts.append(
            f"{hours} hour{'s' if hours != 1 else ''}"
        )

    if minutes or not parts:
        parts.append(
            f"{minutes} minute{'s' if minutes != 1 else ''}"
        )

    return " ".join(parts[:2])


def _task_leave_conflict(
    database: Session,
    *,
    organization_id,
    employee_id,
    scheduled_for,
    due_date,
) -> dict | None:
    return database.execute(
        text(
            """
            SELECT
                lr.start_date,
                lr.end_date,
                lt.code AS leave_type_code,
                lt.name AS leave_type_name
            FROM leave_requests lr
            LEFT JOIN leave_types lt
                ON lt.id = lr.leave_type_id
            WHERE
                lr.organization_id = :org
                AND lr.employee_id = :employee_id
                AND lr.status = 'APPROVED'
                AND (
                    (
                        lr.start_date <= :scheduled_for
                        AND lr.end_date >= :scheduled_for
                    )
                    OR
                    (
                        :due_date IS NOT NULL
                        AND lr.start_date <= :due_date
                        AND lr.end_date >= :due_date
                    )
                )
            ORDER BY lr.start_date DESC
            LIMIT 1
            """
        ),
        {
            "org": organization_id,
            "employee_id": employee_id,
            "scheduled_for": scheduled_for,
            "due_date": due_date,
        },
    ).mappings().first()


def sync_task_time_alerts(
    database: Session,
    user: User,
    roles: set[str],
    tables: set[str],
) -> None:
    required = {
        "task_assignments",
        "tasks",
        "employees",
        "users",
        "notifications",
    }

    if not required.issubset(tables):
        return

    now = datetime.now(timezone.utc)
    org = user.organization_id
    uid = user.id

    is_executive = bool(
        roles.intersection(
            {"MD", "GM"}
        )
    )

    rows = database.execute(
        text(
            """
            SELECT
                ta.id AS assignment_id,
                ta.employee_id,
                ta.assigned_by_user_id,
                ta.scheduled_for,
                ta.due_at,
                ta.status,
                t.title AS task_title,
                e.user_id AS employee_user_id,
                u.employee_code
            FROM task_assignments ta
            JOIN tasks t
                ON t.id = ta.task_id
            JOIN employees e
                ON e.id = ta.employee_id
            JOIN users u
                ON u.id = e.user_id
            WHERE
                ta.organization_id = :org
                AND ta.status NOT IN (
                    'COMPLETED',
                    'CANCELLED'
                )
                AND ta.due_at IS NOT NULL
                AND ta.due_at < :now
                AND (
                    e.user_id = :uid
                    OR ta.assigned_by_user_id = :uid
                    OR :is_executive = TRUE
                )
            ORDER BY ta.due_at
            LIMIT 500
            """
        ),
        {
            "org": org,
            "uid": uid,
            "now": now,
            "is_executive":
                is_executive,
        },
    ).mappings().all()

    if not rows:
        return

    timezone_value = _task_timezone(user)
    queued = 0

    for row in rows:
        due_at = row["due_at"]

        if due_at is None:
            continue

        if due_at.tzinfo is None:
            due_at = due_at.replace(
                tzinfo=timezone.utc
            )

        due_date = due_at.astimezone(
            timezone_value
        ).date()

        conflict = None

        if (
            "leave_requests" in tables
            and "leave_types" in tables
        ):
            conflict = _task_leave_conflict(
                database,
                organization_id=org,
                employee_id=row["employee_id"],
                scheduled_for=row["scheduled_for"],
                due_date=due_date,
            )

        route = (
            f"/module/tasks?assignment="
            f"{row['assignment_id']}"
            "&activity=1"
        )

        employee_label = (
            row["employee_code"]
            or "Employee"
        )

        if conflict:
            leave_name = (
                conflict.get(
                    "leave_type_name"
                )
                or conflict.get(
                    "leave_type_code"
                )
                or "approved leave"
            )

            if row["employee_user_id"]:
                notification = queue_user_notification(
                    database,
                    organization_id=org,
                    recipient_user_id=
                        row["employee_user_id"],
                    title=(
                        "Task requires rescheduling"
                    ),
                    body=(
                        f"'{row['task_title']}' "
                        f"conflicts with your "
                        f"{leave_name}. The assigner "
                        "has been asked to reschedule "
                        "or reassign the task."
                    ),
                    dedupe_key=(
                        f"task:{row['assignment_id']}:"
                        "leave-conflict:employee"
                    ),
                    route=route,
                    module="tasks",
                    event=(
                        "TASK_LEAVE_CONFLICT"
                    ),
                    entity_id=
                        row["assignment_id"],
                )

                if notification is not None:
                    queued += 1

            notification = queue_user_notification(
                database,
                organization_id=org,
                recipient_user_id=
                    row["assigned_by_user_id"],
                title=(
                    "Task conflicts with approved leave"
                ),
                body=(
                    f"{employee_label} cannot be "
                    f"treated as overdue for "
                    f"'{row['task_title']}' because "
                    f"the assignment conflicts with "
                    f"{leave_name}. Please reschedule "
                    "or reassign it."
                ),
                dedupe_key=(
                    f"task:{row['assignment_id']}:"
                    "leave-conflict:assigner"
                ),
                route=route,
                module="tasks",
                event=(
                    "TASK_LEAVE_CONFLICT"
                ),
                entity_id=
                    row["assignment_id"],
            )

            if notification is not None:
                queued += 1

            continue

        overdue_seconds = max(
            0,
            (
                now - due_at.astimezone(
                    timezone.utc
                )
            ).total_seconds(),
        )

        overdue_text = _duration_label(
            overdue_seconds
        )

        if row["employee_user_id"]:
            notification = queue_user_notification(
                database,
                organization_id=org,
                recipient_user_id=
                    row["employee_user_id"],
                title="Task overdue",
                body=(
                    f"'{row['task_title']}' is "
                    f"overdue by {overdue_text}. "
                    "Please update progress or "
                    "complete the task."
                ),
                dedupe_key=(
                    f"task:{row['assignment_id']}:"
                    "overdue:employee"
                ),
                route=route,
                module="tasks",
                event="TASK_OVERDUE",
                entity_id=
                    row["assignment_id"],
            )

            if notification is not None:
                queued += 1

        if row["assigned_by_user_id"]:
            notification = queue_user_notification(
                database,
                organization_id=org,
                recipient_user_id=
                    row["assigned_by_user_id"],
                title="Assigned task overdue",
                body=(
                    f"{employee_label} has not "
                    f"completed '{row['task_title']}'. "
                    f"It is overdue by "
                    f"{overdue_text}."
                ),
                dedupe_key=(
                    f"task:{row['assignment_id']}:"
                    "overdue:assigner"
                ),
                route=route,
                module="tasks",
                event="TASK_OVERDUE",
                entity_id=
                    row["assignment_id"],
            )

            if notification is not None:
                queued += 1

        reminder_seconds = (
            TASK_OVERDUE_REMINDER_HOURS
            * 3600
        )

        if (
            overdue_seconds >= reminder_seconds
            and row["assigned_by_user_id"]
        ):
            notification = queue_user_notification(
                database,
                organization_id=org,
                recipient_user_id=
                    row["assigned_by_user_id"],
                title="Task still overdue",
                body=(
                    f"{employee_label}'s task "
                    f"'{row['task_title']}' remains "
                    f"overdue after "
                    f"{TASK_OVERDUE_REMINDER_HOURS} "
                    "hours."
                ),
                dedupe_key=(
                    f"task:{row['assignment_id']}:"
                    f"overdue:"
                    f"{TASK_OVERDUE_REMINDER_HOURS}h:"
                    "assigner"
                ),
                route=route,
                module="tasks",
                event=(
                    "TASK_OVERDUE_REMINDER"
                ),
                entity_id=
                    row["assignment_id"],
            )

            if notification is not None:
                queued += 1

        escalation_seconds = (
            TASK_OVERDUE_ESCALATION_HOURS
            * 3600
        )

        if overdue_seconds >= escalation_seconds:
            queued += queue_role_notifications(
                database,
                organization_id=org,
                role_codes={"GM", "MD"},
                title=(
                    "Task overdue escalation"
                ),
                body=(
                    f"{employee_label}'s task "
                    f"'{row['task_title']}' has been "
                    f"overdue for more than "
                    f"{TASK_OVERDUE_ESCALATION_HOURS} "
                    "hours."
                ),
                dedupe_prefix=(
                    f"task:{row['assignment_id']}:"
                    f"overdue:"
                    f"{TASK_OVERDUE_ESCALATION_HOURS}h"
                ),
                route=route,
                module="tasks",
                event=(
                    "TASK_OVERDUE_ESCALATED"
                ),
                entity_id=
                    row["assignment_id"],
            )

    if queued:
        database.commit()



def get_action_counts(database: Session, user: User) -> dict[str, int]:
    roles = role_codes(database, user)
    tables = set(inspect(database.get_bind()).get_table_names())
    org = user.organization_id
    uid = user.id

    # Task deadline notifications are generated only by the background worker's
    # 0-hour, 12-hour and 24-hour policy escalation job. Keeping this read-only
    # endpoint from generating the former 24/48-hour alerts prevents duplicates.

    counts = {
        "dashboard": 0,
        "employees": 0,
        "attendance": 0,
        "tasks": 0,
        "inspections": 0,
        "leave": 0,
        "payroll": 0,
        "expenses": 0,
        "maintenance-bills": 0,
        "sheet-verification": 0,
        "security": 0,
        "overtime": 0,
        "md-overview": 0,
        "documents": 0,
        "assets": 0,
        "outlets": 0,
        "fuel": 0,
        "inventory": 0,
        "recruitment": 0,
        "appointments": 0,
        "approvals": 0,
        "operations": 0,
        "shop-rentals": 0,
        "notifications": 0,
    }

    if "notifications" in tables:
        counts["notifications"] = _count(
            database,
            "SELECT COUNT(*) FROM notifications "
            "WHERE organization_id=:org AND recipient_user_id=:uid "
            "AND channel='IN_APP' AND read_at IS NULL",
            org=org,
            uid=uid,
        )

    if "task_assignments" in tables and "employees" in tables:
        counts["tasks"] = _count(
            database,
            """
            SELECT COUNT(*)
            FROM task_assignments ta
            JOIN employees e
                ON e.id = ta.employee_id
            WHERE e.organization_id=:org
              AND e.user_id=:uid
              AND ta.status NOT IN (
                    'COMPLETED',
                    'CANCELLED'
              )
            """,
            org=org,
            uid=uid,
        )

        if roles.intersection(MANAGEMENT_ROLES):
            counts["tasks"] += _count(
                database,
                """
                SELECT COUNT(*)
                FROM task_assignments ta
                WHERE ta.organization_id=:org
                  AND ta.assigned_by_user_id=:uid
                  AND ta.status NOT IN (
                        'COMPLETED',
                        'CANCELLED'
                  )
                  AND ta.due_at IS NOT NULL
                  AND ta.due_at < NOW()
                """,
                org=org,
                uid=uid,
            )

    # Employee leave requests are an MD-only action.
    if "MD" in roles and "leave_requests" in tables:
        counts["leave"] += _count(
            database,
            "SELECT COUNT(*) FROM leave_requests "
            "WHERE organization_id=:org AND status='PENDING'",
            org=org,
        )

    # Attendance regularization keeps the existing management workflow.
    if (
        roles.intersection(MANAGEMENT_ROLES)
        and "attendance_regularizations" in tables
    ):
        counts["leave"] += _count(
            database,
            "SELECT COUNT(*) FROM attendance_regularizations "
            "WHERE organization_id=:org AND status='PENDING'",
            org=org,
        )

    if "payroll_runs" in tables:
        if "MD" in roles:
            counts["payroll"] += _count(
                database,
                "SELECT COUNT(*) FROM payroll_runs "
                "WHERE organization_id=:org AND status='SUBMITTED_FOR_MD_APPROVAL'",
                org=org,
            )
        if roles.intersection({"ADMIN", "GM"}):
            counts["payroll"] += _count(
                database,
                "SELECT COUNT(*) FROM payroll_runs "
                "WHERE organization_id=:org AND status='RETURNED'",
                org=org,
            )

    if "expense_claims" in tables:
        statuses = []
        if roles.intersection({"ADMIN", "GM", "MANAGER", "MD"}):
            statuses.append("SUBMITTED")
        if "MD" in roles:
            statuses.append("VERIFIED")
        if roles.intersection({"ADMIN", "MD"}):
            statuses.append("APPROVED")

        if statuses:
            placeholders = ",".join(f":expense_status_{i}" for i in range(len(statuses)))
            params = {"org": org}
            params.update({f"expense_status_{i}": value for i, value in enumerate(statuses)})
            counts["expenses"] = _count(
                database,
                f"SELECT COUNT(*) FROM expense_claims "
                f"WHERE organization_id=:org AND status IN ({placeholders})",
                **params,
            )

    if "maintenance_bills" in tables:
        statuses = []
        if "ADMIN" in roles:
            statuses.extend(["SUBMITTED", "APPROVED"])
        if "MD" in roles:
            statuses.append("VERIFIED")

        if statuses:
            placeholders = ",".join(f":maintenance_status_{i}" for i in range(len(statuses)))
            params = {"org": org}
            params.update({f"maintenance_status_{i}": value for i, value in enumerate(statuses)})
            counts["maintenance-bills"] = _count(
                database,
                f"SELECT COUNT(*) FROM maintenance_bills "
                f"WHERE organization_id=:org AND status IN ({placeholders})",
                **params,
            )

    if "account_sheet_verification_items" in tables:
        is_secretary = "ACCOUNTS_SECRETARY" in roles
        is_admin = "ADMIN" in roles
        is_md = "MD" in roles

        if is_secretary or is_admin or is_md:
            counts["sheet-verification"] = _count(
                database,
                """
                SELECT COUNT(*)
                FROM account_sheet_verification_items
                WHERE organization_id=:org
                  AND (
                    (:is_secretary = TRUE AND secretary_status='PENDING')
                    OR (
                      :is_admin = TRUE
                      AND issue_status='OPEN'
                      AND admin_escalated_at IS NOT NULL
                    )
                    OR (
                      :is_md = TRUE
                      AND issue_status='OPEN'
                      AND md_escalated_at IS NOT NULL
                    )
                  )
                """,
                org=org,
                is_secretary=is_secretary,
                is_admin=is_admin,
                is_md=is_md,
            )

    if "MD" in roles and "appointments" in tables:
        counts["appointments"] = _count(
            database,
            "SELECT COUNT(*) FROM appointments "
            "WHERE organization_id=:org AND status='PENDING'",
            org=org,
        )

    if "MD" in roles and "document_approval_requests" in tables:
        counts["approvals"] = _count(
            database,
            "SELECT COUNT(*) FROM document_approval_requests "
            "WHERE organization_id=:org AND status='PENDING'",
            org=org,
        )

    if "inspection_reports" in tables:
        if "FIELD_VISITOR" in roles:
            counts["inspections"] += _count(
                database,
                "SELECT COUNT(*) FROM inspection_reports "
                "WHERE organization_id=:org AND inspector_user_id=:uid AND status='DRAFT'",
                org=org,
                uid=uid,
            )

        if roles.intersection(MANAGEMENT_ROLES):
            counts["inspections"] += _count(
                database,
                "SELECT COUNT(*) FROM inspection_reports "
                "WHERE organization_id=:org AND status IN ('ACCEPTED','DISPUTED')",
                org=org,
            )

    if "salary_advance_requests" in tables:
        if "MD" in roles:
            counts["payroll"] += _count(
                database,
                "SELECT COUNT(*) FROM salary_advance_requests "
                "WHERE organization_id=:org AND status='PENDING'",
                org=org,
            )
        if "ADMIN" in roles:
            counts["payroll"] += _count(
                database,
                "SELECT COUNT(*) FROM salary_advance_requests "
                "WHERE organization_id=:org AND status='APPROVED'",
                org=org,
            )

    if "password_reset_approvals" in tables:
        if "MD" in roles:
            counts["security"] += _count(
                database,
                "SELECT COUNT(*) FROM password_reset_approvals "
                "WHERE organization_id=:org AND status='PENDING_MD'",
                org=org,
            )
        if "ADMIN" in roles:
            counts["security"] += _count(
                database,
                "SELECT COUNT(*) FROM password_reset_approvals "
                "WHERE organization_id=:org AND status='APPROVED' "
                "AND (approval_expires_at IS NULL OR approval_expires_at >= NOW())",
                org=org,
            )

    if (
        "late_attendance_monthly_actions" in tables
        and roles.intersection({"ADMIN", "MD"})
    ):
        counts["security"] += _count(
            database,
            "SELECT COUNT(*) FROM late_attendance_monthly_actions "
            "WHERE organization_id=:org AND salary_hold_required=TRUE "
            "AND hold_released_at IS NULL",
            org=org,
        )

    if "overtime_claims" in tables:
        if "ADMIN" in roles:
            counts["overtime"] += _count(
                database,
                "SELECT COUNT(*) FROM overtime_claims "
                "WHERE organization_id=:org AND status='PENDING_ADMIN'",
                org=org,
            )
        if "MD" in roles:
            counts["overtime"] += _count(
                database,
                "SELECT COUNT(*) FROM overtime_claims "
                "WHERE organization_id=:org AND status='PENDING_MD'",
                org=org,
            )
    if "duty_exit_requests" in tables and "ADMIN" in roles:
        counts["attendance"] += _count(
            database,
            "SELECT COUNT(*) FROM duty_exit_requests "
            "WHERE organization_id=:org AND status='PENDING'",
            org=org,
        )

    if "inspection_late_start_requests" in tables and "GM" in roles:
        counts["inspections"] += _count(
            database,
            "SELECT COUNT(*) FROM inspection_late_start_requests "
            "WHERE organization_id=:org AND status='PENDING'",
            org=org,
        )

    if "MD" in roles:
        if "shop_rental_advance_refunds" in tables:
            counts["shop-rentals"] += _count(
                database,
                "SELECT COUNT(*) FROM shop_rental_advance_refunds "
                "WHERE organization_id=:org AND status='PENDING_MD'",
                org=org,
            )
        if "vendor_deposit_refunds" in tables:
            counts["shop-rentals"] += _count(
                database,
                "SELECT COUNT(*) FROM vendor_deposit_refunds "
                "WHERE organization_id=:org AND status='PENDING_MD'",
                org=org,
            )

    if (
        "FIELD_VISITOR" in roles
        and "inspection_visit_assignments" in tables
        and "employees" in tables
    ):
        counts["inspections"] += _count(
            database,
            """
            SELECT COUNT(*)
            FROM inspection_visit_assignments iva
            JOIN employees e
                ON e.id = iva.field_visitor_employee_id
            WHERE
                iva.organization_id=:org
                AND e.user_id=:uid
                AND iva.status='ASSIGNED'
            """,
            org=org,
            uid=uid,
        )

    return counts
