from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord,
    DutyExitRequest,
    Employee,
    EmployeeNoticePeriod,
    InspectionLateStartRequest,
    LunchBreak,
    Organization,
    OrganizationWorkPolicy,
    Role,
    SalaryHold,
    Task,
    TaskAssignment,
    User,
    user_roles,
)
from app.schemas.workforce_policy import (
    DecisionRequest,
    InspectionLateStartCreateRequest,
    NoticePeriodCreateRequest,
    NoticePeriodEndRequest,
    WorkPolicyUpdateRequest,
)
from app.services.device_service import get_employee_for_user
from app.services.notification_service import (
    queue_role_notifications,
    queue_user_notification,
)


ADMIN_ROLE = "ADMIN"
MD_ROLE = "MD"
GM_ROLE = "GM"
MANAGEMENT_ROLES = {"ADMIN", "MD", "GM"}
FIELD_VISITOR_ROLE = "FIELD_VISITOR"
OPEN_DUTY_EXIT_STATUSES = {"PENDING", "APPROVED", "OUTSIDE"}
FINISHED_TASK_STATUSES = {"COMPLETED", "CANCELLED"}


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_role(database: Session, user: User, role: str, message: str) -> None:
    if role not in role_codes(database, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def require_management(database: Session, user: User) -> None:
    if not role_codes(database, user).intersection(MANAGEMENT_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Management access is required.",
        )


def organization_zone(user: User) -> ZoneInfo:
    timezone_name = getattr(getattr(user, "organization", None), "timezone", None)
    try:
        return ZoneInfo(timezone_name or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def organization_now(user: User) -> datetime:
    return datetime.now(organization_zone(user))


def get_work_policy(database: Session, user: User) -> OrganizationWorkPolicy:
    policy = database.scalar(
        select(OrganizationWorkPolicy).where(
            OrganizationWorkPolicy.organization_id == user.organization_id
        )
    )
    if policy is None:
        policy = OrganizationWorkPolicy(
            organization_id=user.organization_id,
            lunch_break_minutes=30,
            lunch_is_paid=True,
            inspection_start_cutoff="09:30",
        )
        database.add(policy)
        database.commit()
        database.refresh(policy)
    return policy


def policy_dict(policy: OrganizationWorkPolicy) -> dict:
    return {
        "id": policy.id,
        "organization_id": policy.organization_id,
        "lunch_break_minutes": policy.lunch_break_minutes,
        "lunch_is_paid": policy.lunch_is_paid,
        "inspection_start_cutoff": policy.inspection_start_cutoff,
        "updated_by_user_id": policy.updated_by_user_id,
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


def update_work_policy(
    database: Session,
    user: User,
    payload: WorkPolicyUpdateRequest,
) -> dict:
    require_role(
        database,
        user,
        ADMIN_ROLE,
        "Only ADMIN can set the organization lunch-break duration.",
    )
    policy = get_work_policy(database, user)
    policy.lunch_break_minutes = payload.lunch_break_minutes
    policy.lunch_is_paid = True
    policy.inspection_start_cutoff = "09:30"
    policy.updated_by_user_id = user.id
    database.commit()
    database.refresh(policy)
    return policy_dict(policy)


def today_attendance(database: Session, user: User, employee: Employee) -> AttendanceRecord:
    local_today = organization_now(user).date()
    attendance = database.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.organization_id == user.organization_id,
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.attendance_date == local_today,
        )
    )
    if attendance is None or attendance.check_in_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Check in before using an on-duty exit or lunch break.",
        )
    if attendance.check_out_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance is already checked out for today.",
        )
    return attendance


def employee_identity(database: Session, employee_id: UUID) -> tuple[Employee, User]:
    row = database.execute(
        select(Employee, User)
        .join(User, Employee.user_id == User.id)
        .where(Employee.id == employee_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Employee was not found.")
    return row[0], row[1]


def duty_exit_dict(database: Session, row: DutyExitRequest) -> dict:
    employee, account = employee_identity(database, row.employee_id)
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "employee_code": account.employee_code,
        "employee_name": employee.full_name,
        "attendance_record_id": row.attendance_record_id,
        "reason": row.reason,
        "status": row.status,
        "requested_at": row.requested_at,
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
        "exited_at": row.exited_at,
        "exit_latitude": row.exit_latitude,
        "exit_longitude": row.exit_longitude,
        "returned_at": row.returned_at,
        "return_latitude": row.return_latitude,
        "return_longitude": row.return_longitude,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def create_duty_exit_request(database: Session, user: User, reason: str) -> dict:
    employee = get_employee_for_user(database, user)
    attendance = today_attendance(database, user, employee)
    active = database.scalar(
        select(DutyExitRequest).where(
            DutyExitRequest.organization_id == user.organization_id,
            DutyExitRequest.employee_id == employee.id,
            DutyExitRequest.attendance_record_id == attendance.id,
            DutyExitRequest.status.in_(sorted(OPEN_DUTY_EXIT_STATUSES)),
        )
    )
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An on-duty geofence exit request is already open.",
        )
    active_lunch = database.scalar(
        select(LunchBreak.id).where(
            LunchBreak.employee_id == employee.id,
            LunchBreak.status == "ACTIVE",
        )
    )
    if active_lunch is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="End the active lunch break before requesting an on-duty exit.",
        )

    now = datetime.now(timezone.utc)
    row = DutyExitRequest(
        organization_id=user.organization_id,
        employee_id=employee.id,
        attendance_record_id=attendance.id,
        reason=reason.strip(),
        status="PENDING",
        requested_at=now,
    )
    database.add(row)
    database.flush()
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ADMIN_ROLE, MD_ROLE},
        title="On-duty geofence exit needs approval",
        body=f"{user.employee_code} — {employee.full_name}: {row.reason}",
        dedupe_prefix=f"duty-exit:{row.id}:requested",
        route="/module/attendance?policy=1",
        module="attendance",
        event="DUTY_EXIT_REQUESTED",
        entity_id=row.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(row)
    return duty_exit_dict(database, row)


def list_my_duty_exit_requests(database: Session, user: User) -> list[dict]:
    employee = get_employee_for_user(database, user)
    rows = database.scalars(
        select(DutyExitRequest)
        .where(
            DutyExitRequest.organization_id == user.organization_id,
            DutyExitRequest.employee_id == employee.id,
        )
        .order_by(DutyExitRequest.requested_at.desc())
        .limit(50)
    ).all()
    return [duty_exit_dict(database, row) for row in rows]


def list_organization_duty_exit_requests(
    database: Session,
    user: User,
    status_filter: str | None,
) -> list[dict]:
    require_role(
        database,
        user,
        ADMIN_ROLE,
        "Only ADMIN can review on-duty geofence exit requests.",
    )
    statement = select(DutyExitRequest).where(
        DutyExitRequest.organization_id == user.organization_id
    )
    if status_filter:
        statement = statement.where(
            DutyExitRequest.status == status_filter.strip().upper()
        )
    rows = database.scalars(
        statement.order_by(DutyExitRequest.requested_at.desc()).limit(200)
    ).all()
    return [duty_exit_dict(database, row) for row in rows]


def get_duty_exit(
    database: Session,
    user: User,
    request_id: UUID,
    *,
    own: bool,
) -> DutyExitRequest:
    statement = select(DutyExitRequest).where(
        DutyExitRequest.id == request_id,
        DutyExitRequest.organization_id == user.organization_id,
    )
    if own:
        employee = get_employee_for_user(database, user)
        statement = statement.where(DutyExitRequest.employee_id == employee.id)
    row = database.scalar(statement)
    if row is None:
        raise HTTPException(status_code=404, detail="On-duty exit request was not found.")
    return row


def decide_duty_exit(
    database: Session,
    user: User,
    request_id: UUID,
    payload: DecisionRequest,
) -> dict:
    require_role(
        database,
        user,
        ADMIN_ROLE,
        "Only ADMIN can approve or reject an on-duty geofence exit.",
    )
    row = get_duty_exit(database, user, request_id, own=False)
    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a pending on-duty exit request can be decided.",
        )
    note = (payload.note or "").strip()
    if not payload.approved and len(note) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A rejection reason of at least 3 characters is required.",
        )
    row.status = "APPROVED" if payload.approved else "REJECTED"
    row.decided_by_user_id = user.id
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = note or None
    employee, account = employee_identity(database, row.employee_id)
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id,
        title=f"On-duty exit {row.status.lower()}",
        body=(
            f"Your geofence exit request was {row.status.lower()} by "
            f"{user.employee_code}."
            + (f" Note: {row.decision_note}" if row.decision_note else "")
        ),
        dedupe_key=f"duty-exit:{row.id}:decision:{row.status}",
        route="/module/attendance",
        module="attendance",
        event=f"DUTY_EXIT_{row.status}",
        entity_id=row.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={MD_ROLE},
        title=f"On-duty exit {row.status.lower()} by ADMIN",
        body=(
            f"ADMIN {user.employee_code} {row.status.lower()} the on-duty exit "
            f"for {account.employee_code} — {employee.full_name}."
            + (f" Note: {row.decision_note}" if row.decision_note else "")
        ),
        dedupe_prefix=f"duty-exit:{row.id}:decision:{row.status}:md",
        route="/module/attendance?policy=1",
        module="attendance",
        event=f"DUTY_EXIT_{row.status}",
        entity_id=row.id,
    )
    database.commit()
    database.refresh(row)
    return duty_exit_dict(database, row)


def start_duty_exit(database: Session, user: User, request_id: UUID) -> dict:
    row = get_duty_exit(database, user, request_id, own=True)
    if row.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ADMIN approval is required before leaving the geofence on duty.",
        )
    employee = get_employee_for_user(database, user)
    attendance = today_attendance(database, user, employee)
    if attendance.id != row.attendance_record_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This permission does not belong to today's attendance record.",
        )
    from app.services.attendance_service import get_latest_fresh_location

    location = get_latest_fresh_location(database, employee=employee)
    row.status = "OUTSIDE"
    row.exited_at = location.recorded_at
    row.exit_latitude = location.latitude
    row.exit_longitude = location.longitude
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ADMIN_ROLE, MD_ROLE},
        title="Employee began approved on-duty exit",
        body=f"{user.employee_code} — {employee.full_name} has left on approved duty.",
        dedupe_prefix=f"duty-exit:{row.id}:started",
        route="/module/attendance?policy=1",
        module="attendance",
        event="DUTY_EXIT_STARTED",
        entity_id=row.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(row)
    return duty_exit_dict(database, row)


def return_from_duty_exit(database: Session, user: User, request_id: UUID) -> dict:
    row = get_duty_exit(database, user, request_id, own=True)
    if row.status != "OUTSIDE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There is no active on-duty geofence exit to close.",
        )
    employee = get_employee_for_user(database, user)
    attendance = today_attendance(database, user, employee)
    from app.services.attendance_service import (
        evaluate_location,
        get_active_assignment,
        get_latest_fresh_location,
    )

    location = get_latest_fresh_location(database, employee=employee)
    recorded_at = location.recorded_at
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    local_date = recorded_at.astimezone(organization_zone(user)).date()
    _, geofence = get_active_assignment(
        database,
        organization_id=user.organization_id,
        employee_id=employee.id,
        attendance_date=local_date,
    )
    distance, inside = evaluate_location(location, geofence)
    if not inside:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Return to the assigned geofence before ending the on-duty exit.",
                "distance_meters": round(distance, 2),
                "allowed_radius_meters": geofence.radius_meters,
            },
        )
    if attendance.id != row.attendance_record_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This permission does not belong to today's attendance record.",
        )
    row.status = "RETURNED"
    row.returned_at = location.recorded_at
    row.return_latitude = location.latitude
    row.return_longitude = location.longitude
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ADMIN_ROLE, MD_ROLE},
        title="Employee returned from on-duty exit",
        body=f"{user.employee_code} — {employee.full_name} returned to the work geofence.",
        dedupe_prefix=f"duty-exit:{row.id}:returned",
        route="/module/attendance?policy=1",
        module="attendance",
        event="DUTY_EXIT_RETURNED",
        entity_id=row.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(row)
    return duty_exit_dict(database, row)


def lunch_break_dict(row: LunchBreak, *, now: datetime | None = None) -> dict:
    reference = row.ended_at or now or datetime.now(timezone.utc)
    started = row.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    elapsed = max(0, int((reference - started).total_seconds() // 60))
    exceeded = max(row.exceeded_minutes or 0, elapsed - row.allowed_minutes)
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "attendance_record_id": row.attendance_record_id,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "allowed_minutes": row.allowed_minutes,
        "elapsed_minutes": elapsed,
        "exceeded_minutes": exceeded,
        "status": row.status,
        "overrun_notified_at": row.overrun_notified_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def queue_lunch_overrun(
    database: Session,
    lunch: LunchBreak,
    *,
    now: datetime,
) -> int:
    employee, account = employee_identity(database, lunch.employee_id)
    started_at = lunch.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    elapsed = max(0, int((now - started_at).total_seconds() // 60))
    exceeded = max(0, elapsed - lunch.allowed_minutes)
    if exceeded <= 0 or lunch.overrun_notified_at is not None:
        return 0
    recipients = {employee.user_id}
    if employee.manager_id:
        manager = database.get(Employee, employee.manager_id)
        if manager is not None:
            recipients.add(manager.user_id)
    queued = 0
    for recipient_id in recipients:
        notification = queue_user_notification(
            database,
            organization_id=lunch.organization_id,
            recipient_user_id=recipient_id,
            title="Lunch break time exceeded",
            body=(
                f"{account.employee_code} — {employee.full_name} exceeded the "
                f"{lunch.allowed_minutes}-minute paid lunch limit by {exceeded} minute(s)."
            ),
            dedupe_key=f"lunch:{lunch.id}:overrun:{recipient_id}",
            route="/module/attendance",
            module="attendance",
            event="LUNCH_BREAK_OVERRUN",
            entity_id=lunch.id,
        )
        queued += int(notification is not None)
    lunch.exceeded_minutes = exceeded
    lunch.overrun_notified_at = now
    return queued


def start_lunch_break(database: Session, user: User) -> dict:
    employee = get_employee_for_user(database, user)
    attendance = today_attendance(database, user, employee)
    existing = database.scalar(
        select(LunchBreak).where(LunchBreak.attendance_record_id == attendance.id)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The lunch break has already been used for today's attendance.",
        )
    active_exit = database.scalar(
        select(DutyExitRequest.id).where(
            DutyExitRequest.employee_id == employee.id,
            DutyExitRequest.status == "OUTSIDE",
        )
    )
    if active_exit is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Return from the active on-duty exit before starting lunch.",
        )
    policy = get_work_policy(database, user)
    row = LunchBreak(
        organization_id=user.organization_id,
        employee_id=employee.id,
        attendance_record_id=attendance.id,
        started_at=datetime.now(timezone.utc),
        allowed_minutes=policy.lunch_break_minutes,
        status="ACTIVE",
    )
    database.add(row)
    database.commit()
    database.refresh(row)
    return lunch_break_dict(row)


def end_lunch_break(database: Session, user: User) -> dict:
    employee = get_employee_for_user(database, user)
    attendance = today_attendance(database, user, employee)
    row = database.scalar(
        select(LunchBreak).where(
            LunchBreak.attendance_record_id == attendance.id,
            LunchBreak.status == "ACTIVE",
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There is no active lunch break to end.",
        )
    now = datetime.now(timezone.utc)
    row.ended_at = now
    row.status = "COMPLETED"
    started_at = row.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    row.exceeded_minutes = max(
        0, int((now - started_at).total_seconds() // 60) - row.allowed_minutes
    )
    queue_lunch_overrun(database, row, now=now)
    database.commit()
    database.refresh(row)
    return lunch_break_dict(row)


def get_my_day_state(database: Session, user: User) -> dict:
    employee = get_employee_for_user(database, user)
    local_today = organization_now(user).date()
    attendance = database.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.organization_id == user.organization_id,
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.attendance_date == local_today,
        )
    )
    duty_exit = None
    lunch = None
    if attendance is not None:
        duty_exit = database.scalar(
            select(DutyExitRequest)
            .where(DutyExitRequest.attendance_record_id == attendance.id)
            .order_by(DutyExitRequest.requested_at.desc())
            .limit(1)
        )
        lunch = database.scalar(
            select(LunchBreak)
            .where(LunchBreak.attendance_record_id == attendance.id)
            .order_by(LunchBreak.started_at.desc())
            .limit(1)
        )
    return {
        "policy": policy_dict(get_work_policy(database, user)),
        "duty_exit": duty_exit_dict(database, duty_exit) if duty_exit else None,
        "lunch_break": lunch_break_dict(lunch) if lunch else None,
    }


def notice_period_dict(database: Session, row: EmployeeNoticePeriod) -> dict:
    employee, account = employee_identity(database, row.employee_id)
    hold = database.get(SalaryHold, row.salary_hold_id)
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "employee_code": account.employee_code,
        "employee_name": employee.full_name,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "reason": row.reason,
        "status": row.status,
        "salary_hold_id": row.salary_hold_id,
        "salary_hold_active": bool(hold and hold.is_active),
        "created_by_user_id": row.created_by_user_id,
        "ended_by_user_id": row.ended_by_user_id,
        "ended_at": row.ended_at,
        "end_note": row.end_note,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_notice_periods(database: Session, user: User) -> list[dict]:
    require_management(database, user)
    rows = database.scalars(
        select(EmployeeNoticePeriod)
        .where(EmployeeNoticePeriod.organization_id == user.organization_id)
        .order_by(EmployeeNoticePeriod.created_at.desc())
        .limit(200)
    ).all()
    return [notice_period_dict(database, row) for row in rows]


def create_notice_period(
    database: Session,
    user: User,
    payload: NoticePeriodCreateRequest,
) -> dict:
    require_role(
        database,
        user,
        MD_ROLE,
        "Only an MD can place an employee on notice period.",
    )
    employee, account = employee_identity(database, payload.employee_id)
    if employee.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Employee was not found.")
    active_notice = database.scalar(
        select(EmployeeNoticePeriod.id).where(
            EmployeeNoticePeriod.employee_id == employee.id,
            EmployeeNoticePeriod.status == "ACTIVE",
        )
    )
    if active_notice is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This employee already has an active notice period.",
        )
    active_hold = database.scalar(
        select(SalaryHold.id).where(
            SalaryHold.employee_id == employee.id,
            SalaryHold.is_active.is_(True),
        )
    )
    if active_hold is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This employee already has an active salary hold. Release it before "
                "creating the automatic notice-period hold."
            ),
        )
    hold = SalaryHold(
        organization_id=user.organization_id,
        employee_id=employee.id,
        hold_from=payload.start_date,
        hold_to=payload.end_date,
        reason=f"Notice period: {payload.reason.strip()}",
        is_active=True,
        created_by_user_id=user.id,
    )
    database.add(hold)
    database.flush()
    notice = EmployeeNoticePeriod(
        organization_id=user.organization_id,
        employee_id=employee.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason.strip(),
        status="ACTIVE",
        salary_hold_id=hold.id,
        created_by_user_id=user.id,
    )
    database.add(notice)
    database.flush()
    body = (
        f"{account.employee_code} — {employee.full_name} is on notice from "
        f"{notice.start_date} through {notice.end_date}. Salary is automatically held. "
        f"Reason: {notice.reason}"
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={"ADMIN", "MD", "GM"},
        title="Employee placed on notice period",
        body=body,
        dedupe_prefix=f"notice:{notice.id}:created",
        route="/module/payroll?notice=1",
        module="payroll",
        event="NOTICE_PERIOD_STARTED",
        entity_id=notice.id,
    )
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id,
        title="Notice period recorded",
        body=(
            f"Your notice period is recorded from {notice.start_date} through "
            f"{notice.end_date}. Please contact management for any clarification."
        ),
        dedupe_key=f"notice:{notice.id}:employee",
        route="/module/payroll",
        module="payroll",
        event="NOTICE_PERIOD_STARTED",
        entity_id=notice.id,
    )
    database.commit()
    database.refresh(notice)
    return notice_period_dict(database, notice)


def cancel_notice_period(
    database: Session,
    user: User,
    notice_id: UUID,
    payload: NoticePeriodEndRequest,
) -> dict:
    require_role(
        database,
        user,
        MD_ROLE,
        "Only an MD can cancel a notice period.",
    )
    notice = database.scalar(
        select(EmployeeNoticePeriod).where(
            EmployeeNoticePeriod.id == notice_id,
            EmployeeNoticePeriod.organization_id == user.organization_id,
        )
    )
    if notice is None:
        raise HTTPException(status_code=404, detail="Notice period was not found.")
    if notice.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an active notice period can be cancelled.",
        )
    now = datetime.now(timezone.utc)
    notice.status = "CANCELLED"
    notice.ended_by_user_id = user.id
    notice.ended_at = now
    notice.end_note = payload.note.strip()
    hold = database.get(SalaryHold, notice.salary_hold_id)
    if hold is not None and hold.is_active:
        hold.is_active = False
        hold.released_by_user_id = user.id
        hold.released_at = now
        hold.release_note = f"Notice period cancelled: {notice.end_note}"
    employee, account = employee_identity(database, notice.employee_id)
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={"ADMIN", "MD", "GM"},
        title="Notice period cancelled",
        body=f"{account.employee_code} — {employee.full_name}: {notice.end_note}",
        dedupe_prefix=f"notice:{notice.id}:cancelled",
        route="/module/payroll?notice=1",
        module="payroll",
        event="NOTICE_PERIOD_CANCELLED",
        entity_id=notice.id,
    )
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id,
        title="Notice period cancelled",
        body=f"Management cancelled your notice period. Note: {notice.end_note}",
        dedupe_key=f"notice:{notice.id}:employee-cancelled",
        route="/module/payroll",
        module="payroll",
        event="NOTICE_PERIOD_CANCELLED",
        entity_id=notice.id,
    )
    database.commit()
    database.refresh(notice)
    return notice_period_dict(database, notice)


def cutoff_time(policy: OrganizationWorkPolicy) -> time:
    try:
        hour, minute = [int(part) for part in policy.inspection_start_cutoff.split(":", 1)]
        return time(hour=hour, minute=minute)
    except Exception:
        return time(hour=9, minute=30)


def inspection_assignment(
    database: Session,
    user: User,
    assignment_id: UUID,
    employee: Employee,
) -> dict:
    row = database.execute(
        text(
            """
            SELECT iva.*, o.code AS outlet_code, o.name AS outlet_name
            FROM inspection_visit_assignments iva
            JOIN outlets o ON o.id = iva.outlet_id
            WHERE iva.id = :assignment_id
              AND iva.organization_id = :org
              AND iva.field_visitor_employee_id = :employee_id
            """
        ),
        {
            "assignment_id": assignment_id,
            "org": user.organization_id,
            "employee_id": employee.id,
        },
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Assigned shop inspection was not found.")
    if row["status"] != "ASSIGNED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an assigned inspection can request a late start.",
        )
    if row["scheduled_for"] != organization_now(user).date():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Late-start permission can only be requested on the scheduled date.",
        )
    return dict(row)


def late_start_dict(database: Session, row: InspectionLateStartRequest) -> dict:
    employee, account = employee_identity(database, row.employee_id)
    assignment = database.execute(
        text(
            """
            SELECT o.code AS outlet_code, o.name AS outlet_name
            FROM inspection_visit_assignments iva
            JOIN outlets o ON o.id = iva.outlet_id
            WHERE iva.id = :assignment_id
            """
        ),
        {"assignment_id": row.visit_assignment_id},
    ).mappings().first()
    return {
        "id": row.id,
        "visit_assignment_id": row.visit_assignment_id,
        "employee_id": row.employee_id,
        "employee_code": account.employee_code,
        "employee_name": employee.full_name,
        "outlet_code": assignment["outlet_code"] if assignment else None,
        "outlet_name": assignment["outlet_name"] if assignment else None,
        "scheduled_for": row.scheduled_for,
        "reason": row.reason,
        "status": row.status,
        "requested_at": row.requested_at,
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
        "consumed_at": row.consumed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def create_inspection_late_start_request(
    database: Session,
    user: User,
    payload: InspectionLateStartCreateRequest,
) -> dict:
    roles = role_codes(database, user)
    if FIELD_VISITOR_ROLE not in roles or roles.intersection(MANAGEMENT_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only a dedicated FIELD_VISITOR can request a late inspection start.",
        )
    employee = get_employee_for_user(database, user)
    assignment = inspection_assignment(
        database, user, payload.visit_assignment_id, employee
    )
    policy = get_work_policy(database, user)
    if organization_now(user).time() <= cutoff_time(policy):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"GM permission is not required before {policy.inspection_start_cutoff}."
            ),
        )
    existing = database.scalar(
        select(InspectionLateStartRequest)
        .where(
            InspectionLateStartRequest.organization_id == user.organization_id,
            InspectionLateStartRequest.visit_assignment_id == payload.visit_assignment_id,
            InspectionLateStartRequest.employee_id == employee.id,
            InspectionLateStartRequest.status.in_(["PENDING", "APPROVED"]),
        )
        .order_by(InspectionLateStartRequest.requested_at.desc())
        .limit(1)
    )
    if existing is not None:
        if existing.status == "APPROVED":
            return late_start_dict(database, existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INSPECTION_LATE_START_PERMISSION_PENDING",
                "message": "The late-start request is already waiting for GM approval.",
            },
        )
    row = InspectionLateStartRequest(
        organization_id=user.organization_id,
        visit_assignment_id=payload.visit_assignment_id,
        employee_id=employee.id,
        scheduled_for=assignment["scheduled_for"],
        reason=payload.reason.strip(),
        status="PENDING",
        requested_at=datetime.now(timezone.utc),
    )
    database.add(row)
    database.flush()
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={GM_ROLE},
        title="Late shop-inspection start needs approval",
        body=(
            f"{user.employee_code} — {employee.full_name} requested permission to start "
            f"{assignment['outlet_name']} after 09:30. Reason: {row.reason}"
        ),
        dedupe_prefix=f"inspection-late:{row.id}:requested",
        route="/module/inspections?late=1",
        module="inspections",
        event="INSPECTION_LATE_START_REQUESTED",
        entity_id=row.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={MD_ROLE},
        title="Late shop-inspection start requested",
        body=(
            f"{user.employee_code} — {employee.full_name} requested GM approval to start "
            f"{assignment['outlet_name']} after 09:30. Reason: {row.reason}"
        ),
        dedupe_prefix=f"inspection-late:{row.id}:requested-md-copy",
        route="/module/inspections?late=1",
        module="inspections",
        event="INSPECTION_LATE_START_REQUESTED_MD_COPY",
        entity_id=row.id,
    )
    database.commit()
    database.refresh(row)
    return late_start_dict(database, row)


def list_inspection_late_start_requests(
    database: Session,
    user: User,
) -> list[dict]:
    roles = role_codes(database, user)
    statement = select(InspectionLateStartRequest).where(
        InspectionLateStartRequest.organization_id == user.organization_id
    )
    if not roles.intersection(MANAGEMENT_ROLES):
        employee = get_employee_for_user(database, user)
        statement = statement.where(
            InspectionLateStartRequest.employee_id == employee.id
        )
    rows = database.scalars(
        statement.order_by(InspectionLateStartRequest.requested_at.desc()).limit(200)
    ).all()
    return [late_start_dict(database, row) for row in rows]


def decide_inspection_late_start(
    database: Session,
    user: User,
    request_id: UUID,
    payload: DecisionRequest,
) -> dict:
    require_role(
        database,
        user,
        GM_ROLE,
        "Only a General Manager can approve or reject a late shop-inspection start.",
    )
    row = database.scalar(
        select(InspectionLateStartRequest).where(
            InspectionLateStartRequest.id == request_id,
            InspectionLateStartRequest.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Late-start request was not found.")
    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a pending late-start request can be decided.",
        )
    note = (payload.note or "").strip()
    if not payload.approved and len(note) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A rejection reason of at least 3 characters is required.",
        )
    row.status = "APPROVED" if payload.approved else "REJECTED"
    row.decided_by_user_id = user.id
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = note or None
    employee, _ = employee_identity(database, row.employee_id)
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id,
        title=f"Late inspection start {row.status.lower()}",
        body=(
            f"Your request to begin the shop inspection after 09:30 was "
            f"{row.status.lower()}."
            + (f" Note: {row.decision_note}" if row.decision_note else "")
        ),
        dedupe_key=f"inspection-late:{row.id}:decision:{row.status}",
        route=f"/module/inspections?visit_assignment={row.visit_assignment_id}",
        module="inspections",
        event=f"INSPECTION_LATE_START_{row.status}",
        entity_id=row.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={MD_ROLE},
        title=f"Late inspection start {row.status.lower()} by GM",
        body=(
            f"GM {user.employee_code} {row.status.lower()} the late-start request "
            f"for an inspection assignment."
            + (f" Note: {row.decision_note}" if row.decision_note else "")
        ),
        dedupe_prefix=f"inspection-late:{row.id}:decision-md-copy:{row.status}",
        route="/module/inspections?late=1",
        module="inspections",
        event=f"INSPECTION_LATE_START_{row.status}_MD_COPY",
        entity_id=row.id,
    )
    database.commit()
    database.refresh(row)
    return late_start_dict(database, row)


def ensure_inspection_start_allowed(
    database: Session,
    user: User,
    assignment_id: UUID,
) -> None:
    policy = get_work_policy(database, user)
    local_now = organization_now(user)
    if local_now.time() <= cutoff_time(policy):
        return
    employee = get_employee_for_user(database, user)
    approved = database.scalar(
        select(InspectionLateStartRequest)
        .where(
            InspectionLateStartRequest.organization_id == user.organization_id,
            InspectionLateStartRequest.visit_assignment_id == assignment_id,
            InspectionLateStartRequest.employee_id == employee.id,
            InspectionLateStartRequest.scheduled_for == local_now.date(),
            InspectionLateStartRequest.status == "APPROVED",
        )
        .order_by(InspectionLateStartRequest.decided_at.desc())
        .limit(1)
    )
    if approved is not None:
        approved.consumed_at = datetime.now(timezone.utc)
        return
    pending = database.scalar(
        select(InspectionLateStartRequest.id).where(
            InspectionLateStartRequest.organization_id == user.organization_id,
            InspectionLateStartRequest.visit_assignment_id == assignment_id,
            InspectionLateStartRequest.employee_id == employee.id,
            InspectionLateStartRequest.status == "PENDING",
        )
    )
    if pending is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "INSPECTION_LATE_START_PERMISSION_PENDING",
                "message": "The inspection cannot begin until GM approves the late start.",
                "cutoff": policy.inspection_start_cutoff,
            },
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "INSPECTION_LATE_START_PERMISSION_REQUIRED",
            "message": (
                f"Shop inspections must begin by {policy.inspection_start_cutoff}. "
                "Enter a reason and request GM permission for a late start."
            ),
            "cutoff": policy.inspection_start_cutoff,
        },
    )


def enqueue_policy_escalations(
    database: Session,
    *,
    now: datetime | None = None,
) -> dict:
    current = now or datetime.now(timezone.utc)
    lunch_notifications = 0
    task_notifications = 0
    completed_notices = 0

    active_lunches = database.scalars(
        select(LunchBreak).where(
            LunchBreak.status == "ACTIVE",
            LunchBreak.overrun_notified_at.is_(None),
        )
    ).all()
    for lunch in active_lunches:
        started = lunch.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
            lunch.started_at = started
        if current >= started + timedelta(minutes=lunch.allowed_minutes):
            lunch_notifications += queue_lunch_overrun(
                database, lunch, now=current
            )

    overdue_rows = database.execute(
        select(TaskAssignment, Task, Employee)
        .join(Task, TaskAssignment.task_id == Task.id)
        .join(Employee, TaskAssignment.employee_id == Employee.id)
        .where(
            TaskAssignment.due_at.is_not(None),
            TaskAssignment.due_at <= current,
            TaskAssignment.status.not_in(sorted(FINISHED_TASK_STATUSES)),
        )
    ).all()
    for assignment, task, employee in overdue_rows:
        due_at = assignment.due_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        elapsed_hours = (current - due_at).total_seconds() / 3600
        stages: list[tuple[str, set[UUID], str]] = [
            (
                "deadline",
                {employee.user_id, assignment.assigned_by_user_id},
                "Task deadline missed",
            )
        ]
        if elapsed_hours >= 12:
            recipients = {assignment.assigned_by_user_id}
            if employee.manager_id:
                manager = database.get(Employee, employee.manager_id)
                if manager is not None:
                    recipients.add(manager.user_id)
            stages.append(("12h", recipients, "Task overdue by 12 hours"))
        if elapsed_hours >= 24:
            md_ids = set(
                database.scalars(
                    select(User.id)
                    .join(user_roles, User.id == user_roles.c.user_id)
                    .join(Role, Role.id == user_roles.c.role_id)
                    .where(
                        User.organization_id == assignment.organization_id,
                        Role.code == MD_ROLE,
                    )
                ).all()
            )
            stages.append(("24h", md_ids, "Task overdue by 24 hours"))
        for stage, recipients, title in stages:
            for recipient_id in recipients:
                notification = queue_user_notification(
                    database,
                    organization_id=assignment.organization_id,
                    recipient_user_id=recipient_id,
                    title=title,
                    body=(
                        f"{task.title} for {employee.full_name} remains unfinished. "
                        f"Deadline: {due_at.isoformat()}."
                    ),
                    dedupe_key=(
                        f"task:{assignment.id}:overdue:{stage}:{recipient_id}"
                    ),
                    route=f"/module/tasks?assignment={assignment.id}",
                    module="tasks",
                    event=f"TASK_OVERDUE_{stage.upper()}",
                    entity_id=assignment.id,
                )
                task_notifications += int(notification is not None)

    active_notices = database.scalars(
        select(EmployeeNoticePeriod).where(
            EmployeeNoticePeriod.status == "ACTIVE"
        )
    ).all()
    for notice in active_notices:
        organization = database.get(Organization, notice.organization_id)
        try:
            zone = ZoneInfo(organization.timezone if organization else "Asia/Kolkata")
        except Exception:
            zone = ZoneInfo("Asia/Kolkata")
        if notice.end_date >= current.astimezone(zone).date():
            continue
        notice.status = "COMPLETED"
        notice.ended_at = current
        notice.end_note = "Notice period completed automatically."
        hold = database.get(SalaryHold, notice.salary_hold_id)
        if hold is not None and hold.is_active:
            hold.is_active = False
            hold.released_at = current
            hold.release_note = "Notice period completed automatically."
        employee, account = employee_identity(database, notice.employee_id)
        queue_role_notifications(
            database,
            organization_id=notice.organization_id,
            role_codes={"ADMIN", "MD", "GM"},
            title="Notice period completed",
            body=(
                f"{account.employee_code} — {employee.full_name} completed the notice "
                f"period on {notice.end_date}. The automatic salary hold was released."
            ),
            dedupe_prefix=f"notice:{notice.id}:completed",
            route="/module/payroll?notice=1",
            module="payroll",
            event="NOTICE_PERIOD_COMPLETED",
            entity_id=notice.id,
        )
        completed_notices += 1

    database.commit()
    return {
        "lunch_overrun_notifications": lunch_notifications,
        "task_escalation_notifications": task_notifications,
        "completed_notice_periods": completed_notices,
    }
