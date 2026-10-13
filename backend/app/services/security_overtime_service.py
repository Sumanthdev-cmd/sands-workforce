from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_password
from app.models import (
    AttendanceRecord,
    DocumentRecord,
    Employee,
    EmployeeGeofenceAssignment,
    LateAttendanceMonthlyAction,
    OvertimeClaim,
    PasswordResetApproval,
    RefreshToken,
    Role,
    User,
    user_roles,
)
from app.schemas.security_overtime import (
    OvertimeAdminReview,
    OvertimeClaimCreate,
    OvertimeMdDecision,
    PasswordResetDecision,
    PasswordResetRequestCreate,
)
from app.services.device_service import get_employee_for_user
from app.services.notification_service import (
    queue_role_notifications,
    queue_user_notification,
)


ADMIN_ROLE = "ADMIN"
MD_ROLE = "MD"
PASSWORD_APPROVAL_HOURS = 24
QUALIFYING_LATE_MINUTES = 30


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_role(database: Session, user: User, required: str) -> None:
    if required not in role_codes(database, user) and not (
        required == ADMIN_ROLE and user.is_superuser
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {required} can perform this action.",
        )


def organization_today(user: User) -> date:
    timezone_name = getattr(getattr(user, "organization", None), "timezone", None)
    try:
        zone = ZoneInfo(timezone_name or "Asia/Kolkata")
    except Exception:
        zone = ZoneInfo("Asia/Kolkata")
    return datetime.now(zone).date()


def load_employee(
    database: Session, organization_id: UUID, employee_id: UUID
) -> Employee:
    employee = database.scalar(
        select(Employee)
        .options(selectinload(Employee.user))
        .where(
            Employee.id == employee_id,
            Employee.organization_id == organization_id,
        )
    )
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee was not found.",
        )
    return employee


def _reset_response(row: PasswordResetApproval) -> dict:
    employee = row.target_employee
    return {
        "id": row.id,
        "target_employee_id": row.target_employee_id,
        "target_employee_code": employee.user.employee_code,
        "target_employee_name": employee.full_name,
        "requested_by_user_id": row.requested_by_user_id,
        "requested_by_employee_code": row.requested_by.employee_code,
        "reason": row.reason,
        "status": row.status,
        "requested_at": row.requested_at,
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
        "approval_expires_at": row.approval_expires_at,
        "completed_by_user_id": row.completed_by_user_id,
        "completed_at": row.completed_at,
    }


def _load_reset_request(
    database: Session, organization_id: UUID, request_id: UUID
) -> PasswordResetApproval:
    row = database.scalar(
        select(PasswordResetApproval)
        .options(
            selectinload(PasswordResetApproval.target_employee).selectinload(
                Employee.user
            ),
            selectinload(PasswordResetApproval.requested_by),
        )
        .where(
            PasswordResetApproval.id == request_id,
            PasswordResetApproval.organization_id == organization_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Password reset request was not found.",
        )
    return row


def create_password_reset_request(
    database: Session,
    *,
    user: User,
    payload: PasswordResetRequestCreate,
) -> dict:
    require_role(database, user, ADMIN_ROLE)
    employee = load_employee(database, user.organization_id, payload.employee_id)

    now = datetime.now(timezone.utc)
    database.execute(
        update(PasswordResetApproval)
        .where(
            PasswordResetApproval.organization_id == user.organization_id,
            PasswordResetApproval.target_employee_id == employee.id,
            PasswordResetApproval.status == "APPROVED",
            PasswordResetApproval.approval_expires_at.is_not(None),
            PasswordResetApproval.approval_expires_at < now,
        )
        .values(status="EXPIRED")
    )

    existing = database.scalar(
        select(PasswordResetApproval.id).where(
            PasswordResetApproval.organization_id == user.organization_id,
            PasswordResetApproval.target_employee_id == employee.id,
            PasswordResetApproval.status.in_(["PENDING_MD", "APPROVED"]),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This employee already has an active password reset request.",
        )

    row = PasswordResetApproval(
        organization_id=user.organization_id,
        target_employee_id=employee.id,
        requested_by_user_id=user.id,
        reason=payload.reason.strip(),
        status="PENDING_MD",
        requested_at=now,
    )
    database.add(row)
    database.flush()

    route = f"/module/security?queue=1&reset={row.id}"
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={MD_ROLE},
        title="Password reset awaiting MD approval",
        body=(
            f"{user.employee_code} requested a password reset for "
            f"{employee.user.employee_code} — {employee.full_name}."
        ),
        dedupe_prefix=f"password-reset:{row.id}:pending-md",
        route=route,
        module="security",
        event="PASSWORD_RESET_APPROVAL_REQUIRED",
        entity_id=row.id,
    )
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id,
        title="Password reset requested",
        body=(
            "ADMIN requested MD approval to reset your password. "
            "No password has been changed yet."
        ),
        dedupe_key=f"password-reset:{row.id}:target-requested",
        route="/module/notifications",
        module="security",
        event="PASSWORD_RESET_REQUESTED",
        entity_id=row.id,
    )
    database.commit()
    return _reset_response(_load_reset_request(database, user.organization_id, row.id))


def list_password_reset_requests(database: Session, *, user: User) -> list[dict]:
    roles = role_codes(database, user)
    if not roles.intersection({ADMIN_ROLE, MD_ROLE}) and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Security approval access is required.")

    now = datetime.now(timezone.utc)
    expired = list(
        database.scalars(
            select(PasswordResetApproval).where(
                PasswordResetApproval.organization_id == user.organization_id,
                PasswordResetApproval.status == "APPROVED",
                PasswordResetApproval.approval_expires_at.is_not(None),
                PasswordResetApproval.approval_expires_at < now,
            )
        ).all()
    )
    for row in expired:
        row.status = "EXPIRED"
    if expired:
        database.commit()

    rows = list(
        database.scalars(
            select(PasswordResetApproval)
            .options(
                selectinload(PasswordResetApproval.target_employee).selectinload(
                    Employee.user
                ),
                selectinload(PasswordResetApproval.requested_by),
            )
            .where(PasswordResetApproval.organization_id == user.organization_id)
            .order_by(PasswordResetApproval.requested_at.desc())
            .limit(200)
        ).all()
    )
    return [_reset_response(row) for row in rows]


def decide_password_reset_request(
    database: Session,
    *,
    user: User,
    request_id: UUID,
    payload: PasswordResetDecision,
) -> dict:
    require_role(database, user, MD_ROLE)
    row = _load_reset_request(database, user.organization_id, request_id)
    if row.status != "PENDING_MD":
        raise HTTPException(status_code=409, detail="This request is no longer pending.")

    now = datetime.now(timezone.utc)
    row.status = "APPROVED" if payload.approved else "REJECTED"
    row.decided_by_user_id = user.id
    row.decided_at = now
    row.decision_note = (payload.note or "").strip() or None
    row.approval_expires_at = (
        now + timedelta(hours=PASSWORD_APPROVAL_HOURS) if payload.approved else None
    )

    outcome = "approved" if payload.approved else "rejected"
    route = f"/module/security?reset={row.id}"
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=row.requested_by_user_id,
        title=f"Password reset {outcome}",
        body=(
            f"MD {outcome} the password reset for "
            f"{row.target_employee.user.employee_code}."
            + (
                f" Complete it within {PASSWORD_APPROVAL_HOURS} hours."
                if payload.approved
                else ""
            )
        ),
        dedupe_key=f"password-reset:{row.id}:{outcome}:requester",
        route=route,
        module="security",
        event=f"PASSWORD_RESET_{outcome.upper()}",
        entity_id=row.id,
    )
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=row.target_employee.user_id,
        title=f"Password reset request {outcome}",
        body=(
            "MD approved the reset request. ADMIN may now assign a temporary password."
            if payload.approved
            else "MD rejected the password reset request. Your password remains unchanged."
        ),
        dedupe_key=f"password-reset:{row.id}:{outcome}:target",
        route="/module/notifications",
        module="security",
        event=f"PASSWORD_RESET_{outcome.upper()}",
        entity_id=row.id,
    )
    database.commit()
    return _reset_response(_load_reset_request(database, user.organization_id, row.id))


def complete_password_reset_request(
    database: Session,
    *,
    user: User,
    request_id: UUID,
    temporary_password: str,
) -> dict:
    require_role(database, user, ADMIN_ROLE)
    row = _load_reset_request(database, user.organization_id, request_id)
    now = datetime.now(timezone.utc)
    if row.status == "APPROVED" and row.approval_expires_at and row.approval_expires_at < now:
        row.status = "EXPIRED"
        database.commit()
    if row.status != "APPROVED":
        raise HTTPException(
            status_code=409,
            detail="An active MD approval is required before resetting this password.",
        )

    target_user = row.target_employee.user
    target_user.password_hash = hash_password(temporary_password)
    target_user.must_change_password = True
    database.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == target_user.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    row.status = "COMPLETED"
    row.completed_by_user_id = user.id
    row.completed_at = now

    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=target_user.id,
        title="Your password was reset",
        body=(
            "An MD-approved password reset was completed by ADMIN. "
            "Use the temporary password provided to you and change it at first login."
        ),
        dedupe_key=f"password-reset:{row.id}:completed:target",
        route="/profile",
        module="security",
        event="PASSWORD_RESET_COMPLETED",
        entity_id=row.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={MD_ROLE},
        title="Approved password reset completed",
        body=(
            f"{user.employee_code} completed the approved password reset for "
            f"{target_user.employee_code}."
        ),
        dedupe_prefix=f"password-reset:{row.id}:completed:md",
        route=f"/module/security?reset={row.id}",
        module="security",
        event="PASSWORD_RESET_COMPLETED",
        entity_id=row.id,
    )
    database.commit()
    return _reset_response(_load_reset_request(database, user.organization_id, row.id))


def _next_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def process_late_attendance(
    database: Session,
    *,
    user: User,
    employee: Employee,
    attendance: AttendanceRecord,
) -> None:
    if attendance.late_minutes < QUALIFYING_LATE_MINUTES:
        return

    month_start = attendance.attendance_date.replace(day=1)
    count = int(
        database.scalar(
            select(func.count(AttendanceRecord.id))
            .where(
                AttendanceRecord.organization_id == user.organization_id,
                AttendanceRecord.employee_id == employee.id,
                AttendanceRecord.attendance_date >= month_start,
                AttendanceRecord.attendance_date < _next_month(month_start),
                AttendanceRecord.late_minutes >= QUALIFYING_LATE_MINUTES,
            )
        )
        or 0
    )

    action = database.scalar(
        select(LateAttendanceMonthlyAction).where(
            LateAttendanceMonthlyAction.organization_id == user.organization_id,
            LateAttendanceMonthlyAction.employee_id == employee.id,
            LateAttendanceMonthlyAction.month_start == month_start,
        )
    )
    if action is None:
        action = LateAttendanceMonthlyAction(
            organization_id=user.organization_id,
            employee_id=employee.id,
            month_start=month_start,
        )
        database.add(action)
        database.flush()
    action.qualifying_late_days = count
    now = datetime.now(timezone.utc)
    route = "/module/security?queue=late"

    if count >= 3 and action.half_day_triggered_at is None:
        action.half_day_deduction_required = True
        action.half_day_triggered_at = now
        body = (
            f"{user.employee_code} has recorded three check-ins at least "
            f"{QUALIFYING_LATE_MINUTES} minutes after the configured grace period "
            f"in {month_start:%B %Y}. A half-day basic-salary deduction will apply."
        )
        queue_user_notification(
            database,
            organization_id=user.organization_id,
            recipient_user_id=employee.user_id,
            title="Half-day late-attendance deduction triggered",
            body=body,
            dedupe_key=f"late-policy:{employee.id}:{month_start}:half-day:employee",
            route="/module/attendance",
            module="attendance",
            event="LATE_HALF_DAY_DEDUCTION",
            entity_id=action.id,
        )
        queue_role_notifications(
            database,
            organization_id=user.organization_id,
            role_codes={ADMIN_ROLE, MD_ROLE},
            title="Half-day late-attendance deduction triggered",
            body=body,
            dedupe_prefix=f"late-policy:{employee.id}:{month_start}:half-day:management",
            route=route,
            module="security",
            event="LATE_HALF_DAY_DEDUCTION",
            entity_id=action.id,
        )

    if count > 3 and action.salary_hold_triggered_at is None:
        action.salary_hold_required = True
        action.salary_hold_triggered_at = now
        body = (
            f"{user.employee_code} has more than three qualifying late check-ins "
            f"in {month_start:%B %Y}. The monthly salary is now on automatic hold "
            "for ADMIN and MD review."
        )
        queue_user_notification(
            database,
            organization_id=user.organization_id,
            recipient_user_id=employee.user_id,
            title="Salary placed on automatic attendance hold",
            body=body,
            dedupe_key=f"late-policy:{employee.id}:{month_start}:hold:employee",
            route="/module/payroll",
            module="payroll",
            event="LATE_SALARY_AUTO_HOLD",
            entity_id=action.id,
        )
        queue_role_notifications(
            database,
            organization_id=user.organization_id,
            role_codes={ADMIN_ROLE, MD_ROLE},
            title="Salary automatically held for repeated lateness",
            body=body,
            dedupe_prefix=f"late-policy:{employee.id}:{month_start}:hold:management",
            route=route,
            module="security",
            event="LATE_SALARY_AUTO_HOLD",
            entity_id=action.id,
        )


def list_late_attendance_actions(database: Session, *, user: User) -> list[dict]:
    roles = role_codes(database, user)
    if not roles.intersection({ADMIN_ROLE, MD_ROLE}) and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Security review access is required.")
    rows = database.execute(
        select(LateAttendanceMonthlyAction, Employee, User)
        .join(Employee, LateAttendanceMonthlyAction.employee_id == Employee.id)
        .join(User, Employee.user_id == User.id)
        .where(LateAttendanceMonthlyAction.organization_id == user.organization_id)
        .order_by(
            LateAttendanceMonthlyAction.month_start.desc(),
            User.employee_code,
        )
        .limit(200)
    ).all()
    return [
        {
            "id": action.id,
            "employee_id": employee.id,
            "employee_code": account.employee_code,
            "employee_name": employee.full_name,
            "month_start": action.month_start,
            "qualifying_late_days": action.qualifying_late_days,
            "half_day_deduction_required": action.half_day_deduction_required,
            "half_day_triggered_at": action.half_day_triggered_at,
            "salary_hold_required": action.salary_hold_required,
            "salary_hold_triggered_at": action.salary_hold_triggered_at,
            "hold_released_by_user_id": action.hold_released_by_user_id,
            "hold_released_at": action.hold_released_at,
            "hold_release_note": action.hold_release_note,
        }
        for action, employee, account in rows
    ]


def release_late_salary_hold(
    database: Session,
    *,
    user: User,
    action_id: UUID,
    note: str,
) -> dict:
    require_role(database, user, MD_ROLE)
    action = database.scalar(
        select(LateAttendanceMonthlyAction).where(
            LateAttendanceMonthlyAction.id == action_id,
            LateAttendanceMonthlyAction.organization_id == user.organization_id,
        )
    )
    if action is None:
        raise HTTPException(status_code=404, detail="Late-attendance action was not found.")
    if not action.salary_hold_required or action.hold_released_at is not None:
        raise HTTPException(status_code=409, detail="This automatic hold is not active.")
    now = datetime.now(timezone.utc)
    action.salary_hold_required = False
    action.hold_released_by_user_id = user.id
    action.hold_released_at = now
    action.hold_release_note = note.strip()
    employee = load_employee(database, user.organization_id, action.employee_id)
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id,
        title="Automatic late-attendance salary hold released",
        body=(
            f"MD released the automatic salary hold for {action.month_start:%B %Y}. "
            f"Note: {action.hold_release_note}"
        ),
        dedupe_key=f"late-policy:{action.id}:hold-released:employee",
        route="/module/payroll",
        module="payroll",
        event="LATE_SALARY_HOLD_RELEASED",
        entity_id=action.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ADMIN_ROLE},
        title="Automatic late-attendance salary hold released",
        body=(
            f"MD released {employee.user.employee_code}'s automatic salary hold "
            f"for {action.month_start:%B %Y}."
        ),
        dedupe_prefix=f"late-policy:{action.id}:hold-released:admin",
        route="/module/security?queue=late",
        module="security",
        event="LATE_SALARY_HOLD_RELEASED",
        entity_id=action.id,
    )
    database.commit()
    rows = list_late_attendance_actions(database, user=user)
    return next(row for row in rows if row["id"] == action.id)


def _active_shift_assignment(
    database: Session, organization_id: UUID, employee_id: UUID, work_date: date
) -> EmployeeGeofenceAssignment | None:
    return database.scalar(
        select(EmployeeGeofenceAssignment)
        .where(
            EmployeeGeofenceAssignment.organization_id == organization_id,
            EmployeeGeofenceAssignment.employee_id == employee_id,
            EmployeeGeofenceAssignment.is_active.is_(True),
            EmployeeGeofenceAssignment.is_primary.is_(True),
            EmployeeGeofenceAssignment.valid_from <= work_date,
            (
                EmployeeGeofenceAssignment.valid_to.is_(None)
                | (EmployeeGeofenceAssignment.valid_to >= work_date)
            ),
        )
        .order_by(EmployeeGeofenceAssignment.valid_from.desc())
        .limit(1)
    )


def _scheduled_minutes(assignment: EmployeeGeofenceAssignment | None) -> int:
    if assignment is None:
        return 0
    start = datetime.combine(date.today(), assignment.shift_start_time)
    end = datetime.combine(date.today(), assignment.shift_end_time)
    if end <= start:
        end += timedelta(days=1)
    return max(0, int((end - start).total_seconds() // 60))


def attendance_work_lookup(
    database: Session,
    *,
    user: User,
    employee_id: UUID,
    work_date: date,
    management_lookup: bool,
) -> dict:
    if management_lookup:
        roles = role_codes(database, user)
        if not roles.intersection({ADMIN_ROLE, MD_ROLE}) and not user.is_superuser:
            raise HTTPException(status_code=403, detail="ADMIN or MD access is required.")
    employee = load_employee(database, user.organization_id, employee_id)
    if not management_lookup and employee.user_id != user.id:
        raise HTTPException(status_code=403, detail="You may view only your own attendance.")

    attendance = database.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.organization_id == user.organization_id,
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.attendance_date == work_date,
        )
    )
    assignment = _active_shift_assignment(
        database, user.organization_id, employee.id, work_date
    )
    scheduled = _scheduled_minutes(assignment)
    worked = 0
    if attendance is not None:
        worked = int(attendance.worked_minutes or 0)
        if (
            worked == 0
            and attendance.check_in_at is not None
            and attendance.check_out_at is not None
        ):
            worked = max(
                0,
                int(
                    (attendance.check_out_at - attendance.check_in_at).total_seconds()
                    // 60
                ),
            )
    overtime = max(0, worked - scheduled) if scheduled else 0
    eligible = bool(
        attendance
        and attendance.check_in_at
        and attendance.check_out_at
        and scheduled > 0
        and overtime > 0
    )
    if attendance is None:
        message = "No attendance record exists for this date."
    elif attendance.check_out_at is None:
        message = "Check-out is not recorded, so exact working hours are unavailable."
    elif assignment is None:
        message = "No active shift assignment exists for this date."
    elif overtime <= 0:
        message = "Recorded work time does not exceed the assigned office timing."
    else:
        message = f"Eligible attendance shows {overtime} overtime minute(s)."
    return {
        "employee_id": employee.id,
        "employee_code": employee.user.employee_code,
        "employee_name": employee.full_name,
        "work_date": work_date,
        "attendance_record_id": attendance.id if attendance else None,
        "status": attendance.status if attendance else None,
        "check_in_at": attendance.check_in_at if attendance else None,
        "check_out_at": attendance.check_out_at if attendance else None,
        "worked_minutes": worked,
        "scheduled_minutes": scheduled,
        "overtime_minutes": overtime,
        "eligible_for_overtime": eligible,
        "message": message,
    }


def _claim_response(row: OvertimeClaim) -> dict:
    employee = row.employee
    return {
        column.name: getattr(row, column.name)
        for column in OvertimeClaim.__table__.columns
        if column.name != "organization_id"
    } | {
        "employee_code": employee.user.employee_code,
        "employee_name": employee.full_name,
    }


def _load_claim(
    database: Session, organization_id: UUID, claim_id: UUID
) -> OvertimeClaim:
    row = database.scalar(
        select(OvertimeClaim)
        .options(selectinload(OvertimeClaim.employee).selectinload(Employee.user))
        .where(
            OvertimeClaim.id == claim_id,
            OvertimeClaim.organization_id == organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Overtime claim was not found.")
    return row


def create_overtime_claim(
    database: Session, *, user: User, payload: OvertimeClaimCreate
) -> dict:
    employee = get_employee_for_user(database, user)
    if payload.work_date > organization_today(user):
        raise HTTPException(status_code=422, detail="Future overtime cannot be claimed.")
    lookup = attendance_work_lookup(
        database,
        user=user,
        employee_id=employee.id,
        work_date=payload.work_date,
        management_lookup=False,
    )
    if not lookup["eligible_for_overtime"]:
        raise HTTPException(status_code=422, detail=lookup["message"])

    row = database.scalar(
        select(OvertimeClaim).where(
            OvertimeClaim.employee_id == employee.id,
            OvertimeClaim.work_date == payload.work_date,
        )
    )
    if row is not None and row.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail="An overtime claim already exists for this date.",
        )
    if row is None:
        row = OvertimeClaim(
            organization_id=user.organization_id,
            employee_id=employee.id,
            attendance_record_id=lookup["attendance_record_id"],
            work_date=payload.work_date,
            check_in_at=lookup["check_in_at"],
            check_out_at=lookup["check_out_at"],
            worked_minutes=lookup["worked_minutes"],
            scheduled_minutes=lookup["scheduled_minutes"],
            overtime_minutes=lookup["overtime_minutes"],
            reason=payload.reason.strip(),
            status="DRAFT",
        )
        database.add(row)
    else:
        row.attendance_record_id = lookup["attendance_record_id"]
        row.check_in_at = lookup["check_in_at"]
        row.check_out_at = lookup["check_out_at"]
        row.worked_minutes = lookup["worked_minutes"]
        row.scheduled_minutes = lookup["scheduled_minutes"]
        row.overtime_minutes = lookup["overtime_minutes"]
        row.reason = payload.reason.strip()
    database.commit()
    return _claim_response(_load_claim(database, user.organization_id, row.id))


def attach_overtime_evidence(
    database: Session,
    *,
    user: User,
    claim_id: UUID,
    document_id: UUID,
) -> dict:
    row = _load_claim(database, user.organization_id, claim_id)
    if row.employee.user_id != user.id or row.status != "DRAFT":
        raise HTTPException(status_code=403, detail="Only your draft claim can be edited.")
    document = database.scalar(
        select(DocumentRecord).where(
            DocumentRecord.id == document_id,
            DocumentRecord.organization_id == user.organization_id,
            DocumentRecord.owner_type == "EMPLOYEE",
            DocumentRecord.owner_id == row.employee_id,
            DocumentRecord.uploaded_by_user_id == user.id,
            DocumentRecord.status == "ACTIVE",
        )
    )
    if document is None:
        raise HTTPException(status_code=422, detail="The evidence document is unavailable.")
    row.evidence_document_id = document.id
    database.commit()
    return _claim_response(_load_claim(database, user.organization_id, row.id))


def submit_overtime_claim(database: Session, *, user: User, claim_id: UUID) -> dict:
    row = _load_claim(database, user.organization_id, claim_id)
    if row.employee.user_id != user.id:
        raise HTTPException(status_code=403, detail="This claim does not belong to you.")
    if row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only a draft claim can be submitted.")
    now = datetime.now(timezone.utc)
    row.status = "PENDING_ADMIN"
    row.submitted_at = now
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ADMIN_ROLE},
        title="Overtime claim awaiting verification",
        body=(
            f"{row.employee.user.employee_code} — {row.employee.full_name} claimed "
            f"{row.overtime_minutes} OT minute(s) for {row.work_date}."
        ),
        dedupe_prefix=f"overtime:{row.id}:pending-admin",
        route=f"/module/overtime?queue=1&claim={row.id}",
        module="overtime",
        event="OVERTIME_ADMIN_REVIEW_REQUIRED",
        entity_id=row.id,
    )
    database.commit()
    return _claim_response(_load_claim(database, user.organization_id, row.id))


def list_my_overtime_claims(database: Session, *, user: User) -> list[dict]:
    employee = get_employee_for_user(database, user)
    rows = list(
        database.scalars(
            select(OvertimeClaim)
            .options(selectinload(OvertimeClaim.employee).selectinload(Employee.user))
            .where(
                OvertimeClaim.organization_id == user.organization_id,
                OvertimeClaim.employee_id == employee.id,
            )
            .order_by(OvertimeClaim.work_date.desc())
        ).all()
    )
    return [_claim_response(row) for row in rows]


def list_organization_overtime_claims(
    database: Session, *, user: User, claim_status: str | None = None
) -> list[dict]:
    roles = role_codes(database, user)
    if not roles.intersection({ADMIN_ROLE, MD_ROLE}) and not user.is_superuser:
        raise HTTPException(status_code=403, detail="ADMIN or MD access is required.")
    statement = (
        select(OvertimeClaim)
        .options(selectinload(OvertimeClaim.employee).selectinload(Employee.user))
        .where(OvertimeClaim.organization_id == user.organization_id)
    )
    if claim_status:
        statement = statement.where(OvertimeClaim.status == claim_status.upper())
    rows = list(
        database.scalars(
            statement.order_by(OvertimeClaim.created_at.desc()).limit(300)
        ).all()
    )
    return [_claim_response(row) for row in rows]


def admin_review_overtime_claim(
    database: Session,
    *,
    user: User,
    claim_id: UUID,
    payload: OvertimeAdminReview,
) -> dict:
    require_role(database, user, ADMIN_ROLE)
    row = _load_claim(database, user.organization_id, claim_id)
    if row.status != "PENDING_ADMIN":
        raise HTTPException(status_code=409, detail="This claim is not awaiting ADMIN.")
    now = datetime.now(timezone.utc)
    row.admin_verified_by_user_id = user.id
    row.admin_verified_at = now
    row.admin_note = (payload.note or "").strip() or None
    if payload.approved:
        lookup = attendance_work_lookup(
            database,
            user=user,
            employee_id=row.employee_id,
            work_date=row.work_date,
            management_lookup=True,
        )
        if not lookup["eligible_for_overtime"]:
            raise HTTPException(status_code=422, detail=lookup["message"])
        row.worked_minutes = lookup["worked_minutes"]
        row.scheduled_minutes = lookup["scheduled_minutes"]
        row.overtime_minutes = lookup["overtime_minutes"]
        row.admin_proposed_amount = round(float(payload.proposed_amount), 2)
        row.status = "PENDING_MD"
        queue_role_notifications(
            database,
            organization_id=user.organization_id,
            role_codes={MD_ROLE},
            title="Overtime benefit awaiting MD approval",
            body=(
                f"ADMIN verified {row.employee.user.employee_code}'s OT claim for "
                f"{row.work_date} and proposed ₹{row.admin_proposed_amount:,.2f}."
            ),
            dedupe_prefix=f"overtime:{row.id}:pending-md",
            route=f"/module/overtime?queue=1&claim={row.id}",
            module="overtime",
            event="OVERTIME_MD_APPROVAL_REQUIRED",
            entity_id=row.id,
        )
        title = "Overtime claim verified by ADMIN"
        body = "Your overtime claim was verified and sent to MD for final approval."
    else:
        row.status = "REJECTED"
        title = "Overtime claim rejected by ADMIN"
        body = f"Your overtime claim was rejected: {row.admin_note}"
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=row.employee.user_id,
        title=title,
        body=body,
        dedupe_key=f"overtime:{row.id}:admin:{row.status}:employee",
        route=f"/module/overtime?claim={row.id}",
        module="overtime",
        event="OVERTIME_ADMIN_REVIEWED",
        entity_id=row.id,
    )
    database.commit()
    return _claim_response(_load_claim(database, user.organization_id, row.id))


def md_decide_overtime_claim(
    database: Session,
    *,
    user: User,
    claim_id: UUID,
    payload: OvertimeMdDecision,
) -> dict:
    require_role(database, user, MD_ROLE)
    row = _load_claim(database, user.organization_id, claim_id)
    if row.status != "PENDING_MD":
        raise HTTPException(status_code=409, detail="This claim is not awaiting MD.")
    now = datetime.now(timezone.utc)
    row.md_decided_by_user_id = user.id
    row.md_decided_at = now
    row.md_note = (payload.note or "").strip() or None
    if payload.approved:
        row.status = "APPROVED"
        row.approved_amount = round(float(payload.approved_amount), 2)
        title = "Overtime benefit approved"
        body = (
            f"MD approved ₹{row.approved_amount:,.2f} for your OT claim dated "
            f"{row.work_date}. It will be included in the eligible payroll."
        )
    else:
        row.status = "REJECTED"
        row.approved_amount = None
        title = "Overtime benefit rejected by MD"
        body = f"MD rejected your overtime claim: {row.md_note}"
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=row.employee.user_id,
        title=title,
        body=body,
        dedupe_key=f"overtime:{row.id}:md:{row.status}:employee",
        route=f"/module/overtime?claim={row.id}",
        module="overtime",
        event="OVERTIME_MD_DECIDED",
        entity_id=row.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ADMIN_ROLE},
        title=title,
        body=(
            f"MD {row.status.lower()} {row.employee.user.employee_code}'s OT claim "
            f"for {row.work_date}."
        ),
        dedupe_prefix=f"overtime:{row.id}:md:{row.status}:admin",
        route=f"/module/overtime?claim={row.id}",
        module="overtime",
        event="OVERTIME_MD_DECIDED",
        entity_id=row.id,
    )
    database.commit()
    return _claim_response(_load_claim(database, user.organization_id, row.id))


def late_payroll_policy(
    database: Session,
    *,
    organization_id: UUID,
    employee_id: UUID,
    period_start: date,
    period_end: date,
) -> dict:
    dates = list(
        database.scalars(
            select(AttendanceRecord.attendance_date).where(
                AttendanceRecord.organization_id == organization_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date >= period_start,
                AttendanceRecord.attendance_date <= period_end,
                AttendanceRecord.late_minutes >= QUALIFYING_LATE_MINUTES,
            )
        ).all()
    )
    counts = Counter((value.year, value.month) for value in dates)
    penalty_months = [key for key, value in counts.items() if value >= 3]
    raw_hold_months = [key for key, value in counts.items() if value > 3]
    released_months = set(
        database.scalars(
            select(LateAttendanceMonthlyAction.month_start).where(
                LateAttendanceMonthlyAction.organization_id == organization_id,
                LateAttendanceMonthlyAction.employee_id == employee_id,
                LateAttendanceMonthlyAction.hold_released_at.is_not(None),
            )
        ).all()
    )
    hold_months = [
        key
        for key in raw_hold_months
        if date(key[0], key[1], 1) not in released_months
    ]
    return {
        "qualifying_late_days": len(dates),
        "monthly_counts": {f"{year:04d}-{month:02d}": value for (year, month), value in counts.items()},
        "half_day_penalty_count": len(penalty_months),
        "salary_hold_required": bool(hold_months),
        "hold_months": [f"{year:04d}-{month:02d}" for year, month in hold_months],
    }


def approved_overtime_for_period(
    database: Session,
    *,
    organization_id: UUID,
    employee_id: UUID,
    period_start: date,
    period_end: date,
) -> tuple[float, list[str]]:
    rows = list(
        database.scalars(
            select(OvertimeClaim).where(
                OvertimeClaim.organization_id == organization_id,
                OvertimeClaim.employee_id == employee_id,
                OvertimeClaim.work_date >= period_start,
                OvertimeClaim.work_date <= period_end,
                OvertimeClaim.status == "APPROVED",
                OvertimeClaim.payroll_run_id.is_(None),
            )
        ).all()
    )
    return (
        round(sum(float(row.approved_amount or 0) for row in rows), 2),
        [str(row.id) for row in rows],
    )


def finalize_overtime_benefits(database: Session, *, payroll_run) -> None:
    from app.models import PayrollItem

    items = list(
        database.scalars(
            select(PayrollItem).where(PayrollItem.payroll_run_id == payroll_run.id)
        ).all()
    )
    now = datetime.now(timezone.utc)
    for item in items:
        if item.is_held:
            continue
        ids = (item.calculation_details or {}).get("overtime_claim_ids") or []
        if not ids:
            continue
        claims = list(
            database.scalars(
                select(OvertimeClaim).where(
                    OvertimeClaim.id.in_([UUID(value) for value in ids]),
                    OvertimeClaim.organization_id == payroll_run.organization_id,
                    OvertimeClaim.status == "APPROVED",
                    OvertimeClaim.payroll_run_id.is_(None),
                )
            ).all()
        )
        for claim in claims:
            claim.status = "PAID"
            claim.payroll_run_id = payroll_run.id
            claim.paid_at = now
