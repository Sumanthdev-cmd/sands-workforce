from __future__ import annotations

import secrets
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Employee, Outlet, Role, User, user_roles
from app.services.device_service import get_employee_for_user
from app.services.notification_service import queue_user_notification


MANAGEMENT_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}
FIELD_VISITOR_ROLE = "FIELD_VISITOR"
ACTIVE_VISIT_STATUSES = {"ASSIGNED", "STARTED"}
RECENT_INSPECTION_EXCLUSION_COUNT = 3


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_management(database: Session, user: User) -> set[str]:
    roles = role_codes(database, user)

    if not roles.intersection(MANAGEMENT_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Management access is required.",
        )

    return roles


def organization_today(user: User) -> date:
    timezone_name = (
        getattr(
            getattr(user, "organization", None),
            "timezone",
            None,
        )
        or "Asia/Kolkata"
    )

    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("Asia/Kolkata")

    return datetime.now(tz).date()


def employee_name(employee: Employee, fallback: str) -> str:
    full_name = " ".join(
        part
        for part in [
            getattr(employee, "first_name", None),
            getattr(employee, "last_name", None),
        ]
        if part
    ).strip()

    return full_name or fallback


def get_outlet(
    database: Session,
    user: User,
    outlet_id: UUID,
) -> Outlet:
    outlet = database.scalar(
        select(Outlet).where(
            Outlet.id == outlet_id,
            Outlet.organization_id == user.organization_id,
            Outlet.is_active.is_(True),
        )
    )

    if outlet is None:
        raise HTTPException(
            status_code=404,
            detail="Active outlet was not found.",
        )

    return outlet


def active_field_visitors(
    database: Session,
    user: User,
) -> list[tuple[Employee, User]]:
    rows = database.execute(
        select(Employee, User)
        .join(User, Employee.user_id == User.id)
        .join(
            user_roles,
            User.id == user_roles.c.user_id,
        )
        .join(
            Role,
            Role.id == user_roles.c.role_id,
        )
        .where(
            Employee.organization_id
            == user.organization_id,
            User.organization_id
            == user.organization_id,
            User.is_active.is_(True),
            Role.code == FIELD_VISITOR_ROLE,
        )
        .order_by(User.employee_code)
    ).unique().all()

    return list(rows)


def recent_outlet_inspectors(
    database: Session,
    user: User,
    outlet_id: UUID,
    *,
    limit: int = RECENT_INSPECTION_EXCLUSION_COUNT,
) -> list[dict]:
    rows = database.execute(
        text(
            """
            SELECT
                ir.id AS report_id,
                ir.report_number,
                ir.inspector_employee_id,
                ir.inspection_started_at,
                u.employee_code,
                e.first_name,
                e.last_name
            FROM inspection_reports ir
            JOIN employees e
                ON e.id = ir.inspector_employee_id
            JOIN users u
                ON u.id = e.user_id
            WHERE
                ir.organization_id = :org
                AND ir.outlet_id = :outlet_id
                AND ir.previous_report_id IS NULL
            ORDER BY
                ir.inspection_started_at DESC,
                ir.created_at DESC
            LIMIT :limit
            """
        ),
        {
            "org": user.organization_id,
            "outlet_id": outlet_id,
            "limit": int(limit),
        },
    ).mappings().all()

    result = []

    for row in rows:
        name = " ".join(
            part
            for part in [
                row.get("first_name"),
                row.get("last_name"),
            ]
            if part
        ).strip()

        result.append(
            {
                "report_id": row["report_id"],
                "report_number": row["report_number"],
                "employee_id":
                    row["inspector_employee_id"],
                "employee_code":
                    row["employee_code"],
                "employee_name":
                    name or row["employee_code"],
                "inspection_started_at":
                    row["inspection_started_at"],
            }
        )

    return result


def approved_leave_on_date(
    database: Session,
    user: User,
    employee_id: UUID,
    scheduled_for: date,
) -> dict | None:
    row = database.execute(
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
                AND lr.start_date <= :scheduled_for
                AND lr.end_date >= :scheduled_for
            ORDER BY lr.start_date DESC
            LIMIT 1
            """
        ),
        {
            "org": user.organization_id,
            "employee_id": employee_id,
            "scheduled_for": scheduled_for,
        },
    ).mappings().first()

    return dict(row) if row else None


def daily_visit_assignment(
    database: Session,
    user: User,
    employee_id: UUID,
    scheduled_for: date,
) -> dict | None:
    """
    One field visitor may receive only one shop inspection per calendar
    day under normal AUTO_ROTATION.

    COMPLETED and SUBMITTED visits still consume that day's normal slot.
    Only a CANCELLED assignment frees the day again.

    Management may deliberately bypass this rule through MANUAL_OVERRIDE,
    where a reason is mandatory and permanently recorded.
    """
    row = database.execute(
        text(
            """
            SELECT
                iva.id,
                iva.outlet_id,
                o.code AS outlet_code,
                o.name AS outlet_name,
                iva.status,
                iva.assignment_method,
                iva.scheduled_for
            FROM inspection_visit_assignments iva
            JOIN outlets o
                ON o.id = iva.outlet_id
            WHERE
                iva.organization_id = :org
                AND iva.field_visitor_employee_id
                    = :employee_id
                AND iva.scheduled_for
                    = :scheduled_for
                AND iva.status <> 'CANCELLED'
            ORDER BY iva.created_at
            LIMIT 1
            """
        ),
        {
            "org": user.organization_id,
            "employee_id": employee_id,
            "scheduled_for": scheduled_for,
        },
    ).mappings().first()

    return dict(row) if row else None


def scheduled_workload(
    database: Session,
    user: User,
    employee_id: UUID,
    scheduled_for: date,
) -> int:
    value = database.execute(
        text(
            """
            SELECT COUNT(*)
            FROM inspection_visit_assignments
            WHERE
                organization_id = :org
                AND field_visitor_employee_id
                    = :employee_id
                AND scheduled_for = :scheduled_for
                AND status <> 'CANCELLED'
            """
        ),
        {
            "org": user.organization_id,
            "employee_id": employee_id,
            "scheduled_for": scheduled_for,
        },
    ).scalar()

    return int(value or 0)


def existing_outlet_visit(
    database: Session,
    user: User,
    outlet_id: UUID,
    scheduled_for: date,
) -> dict | None:
    row = database.execute(
        text(
            """
            SELECT id, status, scheduled_for
            FROM inspection_visit_assignments
            WHERE
                organization_id = :org
                AND outlet_id = :outlet_id
                AND status IN (
                    'ASSIGNED',
                    'STARTED'
                )
            ORDER BY scheduled_for, created_at
            LIMIT 1
            """
        ),
        {
            "org": user.organization_id,
            "outlet_id": outlet_id,
        },
    ).mappings().first()

    return dict(row) if row else None


def rotation_preview(
    database: Session,
    *,
    user: User,
    outlet_id: UUID,
    scheduled_for: date,
) -> dict:
    require_management(database, user)
    outlet = get_outlet(
        database,
        user,
        outlet_id,
    )

    if scheduled_for < organization_today(user):
        raise HTTPException(
            status_code=422,
            detail=(
                "Inspection date cannot be in the past."
            ),
        )

    existing = existing_outlet_visit(
        database,
        user,
        outlet.id,
        scheduled_for,
    )

    recent = recent_outlet_inspectors(
        database,
        user,
        outlet.id,
    )

    recent_ids = {
        row["employee_id"]
        for row in recent
    }

    visitors = active_field_visitors(
        database,
        user,
    )

    options = []
    eligible = []
    manual_override_options = []

    for employee, account in visitors:
        leave = approved_leave_on_date(
            database,
            user,
            employee.id,
            scheduled_for,
        )

        daily_assignment = daily_visit_assignment(
            database,
            user,
            employee.id,
            scheduled_for,
        )

        recent_excluded = (
            employee.id in recent_ids
        )

        workload = scheduled_workload(
            database,
            user,
            employee.id,
            scheduled_for,
        )

        reasons = []

        if recent_excluded:
            reasons.append(
                "INSPECTED_WITHIN_LAST_3"
            )

        if leave:
            leave_name = (
                leave.get("leave_type_name")
                or leave.get("leave_type_code")
                or "Approved leave"
            )
            reasons.append(
                f"ON_LEAVE:{leave_name}"
            )

        if daily_assignment:
            reasons.append(
                "DAILY_LIMIT:"
                f"{daily_assignment.get('outlet_name')}"
                f" ({daily_assignment.get('status')})"
            )

        option = {
            "employee_id": employee.id,
            "employee_code":
                account.employee_code,
            "employee_name":
                employee_name(
                    employee,
                    account.employee_code,
                ),
            "recent_excluded":
                recent_excluded,
            "on_leave":
                bool(leave),
            "has_daily_assignment":
                bool(daily_assignment),
            "daily_assignment":
                dict(daily_assignment)
                if daily_assignment
                else None,
            "workload":
                workload,
            "eligible":
                not (
                    recent_excluded
                    or leave
                    or daily_assignment
                ),
            "reasons": reasons,
        }

        options.append(option)

        if option["eligible"]:
            eligible.append(option)

        if not leave:
            manual_override_options.append(
                option
            )

    eligible.sort(
        key=lambda item: (
            item["workload"],
            item["employee_code"],
        )
    )

    manual_override_options.sort(
        key=lambda item: (
            item["workload"],
            item["employee_code"],
        )
    )

    return {
        "outlet": {
            "id": outlet.id,
            "code": outlet.code,
            "name": outlet.name,
        },
        "scheduled_for": scheduled_for,
        "rotation_rule": (
            "Auto Rotation excludes a visitor used in any of the last "
            f"{RECENT_INSPECTION_EXCLUSION_COUNT} inspections and also "
            "excludes any visitor who already has a non-cancelled shop "
            "inspection on the selected date."
        ),
        "daily_limit_rule": (
            "One shop inspection per field visitor per day under "
            "Auto Rotation. Management may use Manual Override only "
            "when operationally unavoidable; a reason is required."
        ),
        "existing_active_assignment":
            existing,
        "recent_three": recent,
        "eligible_visitors": eligible,
        "manual_override_options":
            manual_override_options,
        "all_visitors": options,
    }


def insert_visit_assignment(
    database: Session,
    *,
    user: User,
    outlet: Outlet,
    employee_id: UUID,
    scheduled_for: date,
    assignment_method: str,
    override_reason: str | None,
) -> dict:
    assignment_id = uuid4()
    now = datetime.now(timezone.utc)

    database.execute(
        text(
            """
            INSERT INTO inspection_visit_assignments (
                id,
                organization_id,
                outlet_id,
                field_visitor_employee_id,
                assigned_by_user_id,
                scheduled_for,
                status,
                assignment_method,
                override_reason,
                assigned_at,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :organization_id,
                :outlet_id,
                :employee_id,
                :assigned_by_user_id,
                :scheduled_for,
                'ASSIGNED',
                :assignment_method,
                :override_reason,
                :assigned_at,
                :created_at,
                :updated_at
            )
            """
        ),
        {
            "id": assignment_id,
            "organization_id":
                user.organization_id,
            "outlet_id": outlet.id,
            "employee_id": employee_id,
            "assigned_by_user_id":
                user.id,
            "scheduled_for":
                scheduled_for,
            "assignment_method":
                assignment_method,
            "override_reason":
                override_reason,
            "assigned_at": now,
            "created_at": now,
            "updated_at": now,
        },
    )

    employee_user = database.execute(
        select(Employee, User)
        .join(User, Employee.user_id == User.id)
        .where(
            Employee.id == employee_id,
            Employee.organization_id
            == user.organization_id,
        )
    ).first()

    if employee_user:
        employee, account = employee_user

        queue_user_notification(
            database,
            organization_id=
                user.organization_id,
            recipient_user_id=account.id,
            title=(
                "New shop inspection assignment"
            ),
            body=(
                f"{outlet.name} ({outlet.code}) "
                f"is assigned for inspection on "
                f"{scheduled_for.isoformat()}."
            ),
            dedupe_key=(
                f"inspection-visit:"
                f"{assignment_id}:assigned"
            ),
            route=(
                "/module/inspections"
                f"?visit_assignment={assignment_id}"
            ),
            module="inspections",
            event=(
                "INSPECTION_VISIT_ASSIGNED"
            ),
            entity_id=assignment_id,
            extra_payload={
                "outlet_id":
                    str(outlet.id),
                "scheduled_for":
                    scheduled_for.isoformat(),
                "assignment_method":
                    assignment_method,
            },
        )

    return {
        "id": assignment_id,
        "outlet_id": outlet.id,
        "field_visitor_employee_id":
            employee_id,
        "scheduled_for":
            scheduled_for,
        "status": "ASSIGNED",
        "assignment_method":
            assignment_method,
        "override_reason":
            override_reason,
    }


def auto_assign_visit(
    database: Session,
    *,
    user: User,
    outlet_id: UUID,
    scheduled_for: date,
) -> dict:
    preview = rotation_preview(
        database,
        user=user,
        outlet_id=outlet_id,
        scheduled_for=scheduled_for,
    )

    if preview[
        "existing_active_assignment"
    ]:
        raise HTTPException(
            status_code=409,
            detail=(
                "This outlet already has an active "
                "inspection assignment for the "
                "selected date."
            ),
        )

    eligible = preview[
        "eligible_visitors"
    ]

    if not eligible:
        excluded = [
            item["employee_code"]
            for item in preview["all_visitors"]
            if item["recent_excluded"]
        ]

        unavailable = [
            (
                f"{item['employee_code']}: "
                + ", ".join(item["reasons"])
            )
            for item in preview["all_visitors"]
            if not item["eligible"]
            and not item["recent_excluded"]
        ]

        detail = (
            "No eligible field visitor is available "
            "under the strict last-3 rotation and "
            "one-inspection-per-day rules."
        )

        if excluded:
            detail += (
                " Recently excluded: "
                + ", ".join(excluded)
                + "."
            )

        if unavailable:
            detail += (
                " Other unavailable visitors: "
                + "; ".join(unavailable)
                + "."
            )

        detail += (
            " Use Manual Override only when "
            "operationally necessary; a reason "
            "will be permanently recorded."
        )

        raise HTTPException(
            status_code=409,
            detail=detail,
        )

    minimum_workload = min(
        item["workload"]
        for item in eligible
    )

    least_loaded = [
        item
        for item in eligible
        if item["workload"]
        == minimum_workload
    ]

    chosen = secrets.choice(
        least_loaded
    )

    outlet = get_outlet(
        database,
        user,
        outlet_id,
    )

    result = insert_visit_assignment(
        database,
        user=user,
        outlet=outlet,
        employee_id=chosen["employee_id"],
        scheduled_for=scheduled_for,
        assignment_method="AUTO_ROTATION",
        override_reason=None,
    )

    try:
        database.commit()
    except IntegrityError as exc:
        database.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Another active inspection assignment "
                "was created for this outlet. Refresh "
                "the rotation preview and try again."
            ),
        ) from exc

    return {
        **result,
        "employee_code":
            chosen["employee_code"],
        "employee_name":
            chosen["employee_name"],
        "outlet_code":
            outlet.code,
        "outlet_name":
            outlet.name,
        "recent_three":
            preview["recent_three"],
    }


def manual_override_visit(
    database: Session,
    *,
    user: User,
    outlet_id: UUID,
    scheduled_for: date,
    employee_id: UUID,
    reason: str,
) -> dict:
    require_management(
        database,
        user,
    )

    reason = (reason or "").strip()

    if len(reason) < 5:
        raise HTTPException(
            status_code=422,
            detail=(
                "Manual override reason must contain "
                "at least 5 characters."
            ),
        )

    preview = rotation_preview(
        database,
        user=user,
        outlet_id=outlet_id,
        scheduled_for=scheduled_for,
    )

    if preview[
        "existing_active_assignment"
    ]:
        raise HTTPException(
            status_code=409,
            detail=(
                "This outlet already has an active "
                "inspection assignment for the "
                "selected date."
            ),
        )

    option = next(
        (
            item
            for item in preview[
                "manual_override_options"
            ]
            if item["employee_id"]
            == employee_id
        ),
        None,
    )

    if option is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Selected field visitor cannot be used "
                "because the employee is on approved "
                "leave. Approved leave cannot be bypassed "
                "by Manual Override."
            ),
        )

    outlet = get_outlet(
        database,
        user,
        outlet_id,
    )

    result = insert_visit_assignment(
        database,
        user=user,
        outlet=outlet,
        employee_id=employee_id,
        scheduled_for=scheduled_for,
        assignment_method="MANUAL_OVERRIDE",
        override_reason=reason,
    )

    try:
        database.commit()
    except IntegrityError as exc:
        database.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Another active inspection assignment "
                "was created for this outlet. Refresh "
                "and try again."
            ),
        ) from exc

    return {
        **result,
        "employee_code":
            option["employee_code"],
        "employee_name":
            option["employee_name"],
        "outlet_code":
            outlet.code,
        "outlet_name":
            outlet.name,
        "rotation_rule_overridden":
            option["recent_excluded"],
        "daily_limit_overridden":
            option.get("has_daily_assignment", False),
        "previous_same_day_assignment":
            option.get("daily_assignment"),
    }


def serialize_visit_row(row) -> dict:
    name = (
        (row.get("employee_name") or "").strip()
        or " ".join(
            part
            for part in [
                row.get("first_name"),
                row.get("last_name"),
            ]
            if part
        ).strip()
    )

    return {
        "id": row["id"],
        "outlet_id": row["outlet_id"],
        "outlet_code":
            row["outlet_code"],
        "outlet_name":
            row["outlet_name"],
        "field_visitor_employee_id":
            row[
                "field_visitor_employee_id"
            ],
        "employee_code":
            row["employee_code"],
        "employee_name":
            name or row["employee_code"],
        "assigned_by_user_id":
            row["assigned_by_user_id"],
        "assigned_by_employee_code":
            row.get(
                "assigned_by_employee_code"
            ),
        "scheduled_for":
            row["scheduled_for"],
        "status": row["status"],
        "assignment_method":
            row["assignment_method"],
        "override_reason":
            row["override_reason"],
        "inspection_report_id":
            row["inspection_report_id"],
        "report_number":
            row["report_number"],
        "assigned_at":
            row["assigned_at"],
        "started_at":
            row["started_at"],
        "submitted_at":
            row["submitted_at"],
        "completed_at":
            row["completed_at"],
        "cancelled_at":
            row["cancelled_at"],
        "cancel_reason":
            row["cancel_reason"],
        "created_at":
            row["created_at"],
    }


def list_visit_assignments(
    database: Session,
    *,
    user: User,
) -> list[dict]:
    roles = role_codes(
        database,
        user,
    )

    management = bool(
        roles.intersection(
            MANAGEMENT_ROLES
        )
    )

    employee = None

    if not management:
        if FIELD_VISITOR_ROLE not in roles:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Shop inspection access "
                    "is required."
                ),
            )

        employee = (
            get_employee_for_user(
                database,
                user,
            )
        )

    sql = """
        SELECT
            iva.*,
            o.code AS outlet_code,
            o.name AS outlet_name,
            e.first_name,
            e.last_name,
            TRIM(
                CONCAT_WS(
                    ' ',
                    e.first_name,
                    e.last_name
                )
            ) AS employee_name,
            eu.employee_code,
            au.employee_code
                AS assigned_by_employee_code,
            ir.report_number
        FROM inspection_visit_assignments iva
        JOIN outlets o
            ON o.id = iva.outlet_id
        JOIN employees e
            ON e.id
            = iva.field_visitor_employee_id
        JOIN users eu
            ON eu.id = e.user_id
        JOIN users au
            ON au.id = iva.assigned_by_user_id
        LEFT JOIN inspection_reports ir
            ON ir.id
            = iva.inspection_report_id
        WHERE
            iva.organization_id = :org
    """

    params = {
        "org": user.organization_id,
    }

    if not management:
        sql += """
            AND iva.field_visitor_employee_id
                = :employee_id
        """

        params["employee_id"] = employee.id

    sql += """
        ORDER BY
            iva.scheduled_for DESC,
            iva.created_at DESC
        LIMIT 250
    """

    rows = database.execute(
        text(sql),
        params,
    ).mappings().all()

    return [
        serialize_visit_row(row)
        for row in rows
    ]


def rotation_history(
    database: Session,
    *,
    user: User,
    outlet_id: UUID,
) -> dict:
    require_management(
        database,
        user,
    )

    outlet = get_outlet(
        database,
        user,
        outlet_id,
    )

    inspection_rows = database.execute(
        text(
            """
            SELECT
                ir.id,
                ir.report_number,
                ir.status,
                ir.inspection_started_at,
                ir.submitted_at,
                u.employee_code,
                e.first_name,
                e.last_name
            FROM inspection_reports ir
            JOIN employees e
                ON e.id = ir.inspector_employee_id
            JOIN users u
                ON u.id = e.user_id
            WHERE
                ir.organization_id = :org
                AND ir.outlet_id = :outlet_id
                AND ir.previous_report_id IS NULL
            ORDER BY
                ir.inspection_started_at DESC,
                ir.created_at DESC
            LIMIT 30
            """
        ),
        {
            "org":
                user.organization_id,
            "outlet_id":
                outlet.id,
        },
    ).mappings().all()

    assignment_rows = database.execute(
        text(
            """
            SELECT
                iva.id,
                iva.scheduled_for,
                iva.status,
                iva.assignment_method,
                iva.override_reason,
                iva.assigned_at,
                iva.started_at,
                iva.submitted_at,
                iva.completed_at,
                iva.cancelled_at,
                iva.cancel_reason,
                u.employee_code,
                e.first_name,
                e.last_name
            FROM inspection_visit_assignments iva
            JOIN employees e
                ON e.id
                = iva.field_visitor_employee_id
            JOIN users u
                ON u.id = e.user_id
            WHERE
                iva.organization_id = :org
                AND iva.outlet_id = :outlet_id
            ORDER BY
                iva.scheduled_for DESC,
                iva.created_at DESC
            LIMIT 50
            """
        ),
        {
            "org":
                user.organization_id,
            "outlet_id":
                outlet.id,
        },
    ).mappings().all()

    def with_name(row):
        value = dict(row)
        value["employee_name"] = (
            " ".join(
                part
                for part in [
                    row.get("first_name"),
                    row.get("last_name"),
                ]
                if part
            ).strip()
            or row.get("employee_code")
        )

        return value

    return {
        "outlet": {
            "id": outlet.id,
            "code": outlet.code,
            "name": outlet.name,
        },
        "recent_three":
            recent_outlet_inspectors(
                database,
                user,
                outlet.id,
            ),
        "inspection_history": [
            with_name(row)
            for row in inspection_rows
        ],
        "assignment_history": [
            with_name(row)
            for row in assignment_rows
        ],
    }


def cancel_visit_assignment(
    database: Session,
    *,
    user: User,
    assignment_id: UUID,
    reason: str,
) -> dict:
    require_management(
        database,
        user,
    )

    reason = (reason or "").strip()

    if len(reason) < 5:
        raise HTTPException(
            status_code=422,
            detail=(
                "Cancellation reason must contain "
                "at least 5 characters."
            ),
        )

    row = database.execute(
        text(
            """
            SELECT
                iva.*,
                o.code AS outlet_code,
                o.name AS outlet_name,
                e.user_id AS employee_user_id,
                eu.employee_code
            FROM inspection_visit_assignments iva
            JOIN outlets o
                ON o.id = iva.outlet_id
            JOIN employees e
                ON e.id
                = iva.field_visitor_employee_id
            JOIN users eu
                ON eu.id = e.user_id
            WHERE
                iva.id = :assignment_id
                AND iva.organization_id = :org
            """
        ),
        {
            "assignment_id":
                assignment_id,
            "org":
                user.organization_id,
        },
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Inspection assignment "
                "was not found."
            ),
        )

    if row["status"] != "ASSIGNED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only an inspection that has not "
                "started can be cancelled."
            ),
        )

    now = datetime.now(timezone.utc)

    database.execute(
        text(
            """
            UPDATE inspection_visit_assignments
            SET
                status = 'CANCELLED',
                cancel_reason = :reason,
                cancelled_at = :now,
                updated_at = :now
            WHERE
                id = :assignment_id
                AND organization_id = :org
                AND status = 'ASSIGNED'
            """
        ),
        {
            "reason": reason,
            "now": now,
            "assignment_id":
                assignment_id,
            "org":
                user.organization_id,
        },
    )

    queue_user_notification(
        database,
        organization_id=
            user.organization_id,
        recipient_user_id=
            row["employee_user_id"],
        title=(
            "Shop inspection assignment cancelled"
        ),
        body=(
            f"{row['outlet_name']} "
            f"({row['outlet_code']}) inspection "
            f"was cancelled. Reason: {reason}"
        ),
        dedupe_key=(
            f"inspection-visit:"
            f"{assignment_id}:cancelled"
        ),
        route="/module/inspections",
        module="inspections",
        event=(
            "INSPECTION_VISIT_CANCELLED"
        ),
        entity_id=assignment_id,
    )

    database.commit()

    return {
        "id": assignment_id,
        "status": "CANCELLED",
        "cancel_reason": reason,
    }


def validate_visit_assignment_for_start(
    database: Session,
    *,
    user: User,
    assignment_id: UUID,
    outlet_id: UUID,
) -> dict:
    roles = role_codes(
        database,
        user,
    )

    if (
        FIELD_VISITOR_ROLE not in roles
        or roles.intersection(
            MANAGEMENT_ROLES
        )
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Only a dedicated FIELD_VISITOR "
                "account can start a shop inspection."
            ),
        )

    employee = get_employee_for_user(
        database,
        user,
    )

    row = database.execute(
        text(
            """
            SELECT
                iva.*,
                o.code AS outlet_code,
                o.name AS outlet_name
            FROM inspection_visit_assignments iva
            JOIN outlets o
                ON o.id = iva.outlet_id
            WHERE
                iva.id = :assignment_id
                AND iva.organization_id = :org
                AND iva.field_visitor_employee_id
                    = :employee_id
            """
        ),
        {
            "assignment_id":
                assignment_id,
            "org":
                user.organization_id,
            "employee_id":
                employee.id,
        },
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Assigned shop inspection "
                "was not found."
            ),
        )

    if row["outlet_id"] != outlet_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "Inspection assignment does not "
                "belong to the selected outlet."
            ),
        )

    if row["status"] != "ASSIGNED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Inspection assignment is not "
                "available to start."
            ),
        )

    today = organization_today(user)

    if row["scheduled_for"] != today:
        raise HTTPException(
            status_code=409,
            detail=(
                "This inspection can only be started "
                "on its scheduled date "
                f"{row['scheduled_for']}."
            ),
        )

    leave = approved_leave_on_date(
        database,
        user,
        employee.id,
        row["scheduled_for"],
    )

    if leave:
        raise HTTPException(
            status_code=409,
            detail=(
                "Inspection cannot be started because "
                "the field visitor is on approved "
                "leave. Management must reassign it."
            ),
        )

    return dict(row)


def mark_visit_started(
    database: Session,
    *,
    user: User,
    assignment_id: UUID,
    report_id: UUID,
) -> None:
    now = datetime.now(timezone.utc)

    result = database.execute(
        text(
            """
            UPDATE inspection_visit_assignments
            SET
                status = 'STARTED',
                inspection_report_id = :report_id,
                started_at = :now,
                updated_at = :now
            WHERE
                id = :assignment_id
                AND organization_id = :org
                AND status = 'ASSIGNED'
                AND inspection_report_id IS NULL
            """
        ),
        {
            "report_id": report_id,
            "now": now,
            "assignment_id":
                assignment_id,
            "org":
                user.organization_id,
        },
    )

    if result.rowcount != 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Inspection assignment changed before "
                "the report could be started. Refresh "
                "and try again."
            ),
        )


def mark_visit_submitted(
    database: Session,
    *,
    organization_id: UUID,
    report_id: UUID,
) -> None:
    now = datetime.now(timezone.utc)

    database.execute(
        text(
            """
            UPDATE inspection_visit_assignments
            SET
                status = 'SUBMITTED',
                submitted_at = :now,
                updated_at = :now
            WHERE
                organization_id = :org
                AND inspection_report_id
                    = :report_id
                AND status = 'STARTED'
            """
        ),
        {
            "now": now,
            "org": organization_id,
            "report_id": report_id,
        },
    )


def mark_visit_completed(
    database: Session,
    *,
    organization_id: UUID,
    report_id: UUID,
) -> None:
    now = datetime.now(timezone.utc)

    database.execute(
        text(
            """
            UPDATE inspection_visit_assignments
            SET
                status = 'COMPLETED',
                completed_at = :now,
                updated_at = :now
            WHERE
                organization_id = :org
                AND inspection_report_id
                    = :report_id
                AND status IN (
                    'STARTED',
                    'SUBMITTED'
                )
            """
        ),
        {
            "now": now,
            "org": organization_id,
            "report_id": report_id,
        },
    )
