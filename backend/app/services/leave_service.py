from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AttendanceRecord, AttendanceRegularization, Employee, Holiday, LeaveBalance, LeaveRequest, LeaveType, Role, User, user_roles
from app.schemas.leave import DecisionIn, HolidayCreate, LeaveRequestCreate, LeaveTypeCreate, RegularizationCreate
from app.services.device_service import get_employee_for_user
from app.services.notification_service import queue_role_notifications, queue_user_notification

APPROVER_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}
LEAVE_DECISION_ROLES = {"MD"}
LEAVE_APPROVAL_NOTICE_ROLES = {"ADMIN"}


def require_approver(db: Session, user: User) -> None:
    roles = set(db.scalars(select(Role.code).join(user_roles, Role.id == user_roles.c.role_id).where(user_roles.c.user_id == user.id)).all())
    if not roles.intersection(APPROVER_ROLES):
        raise HTTPException(status_code=403, detail="Leave approval access is required")



def require_leave_md(db: Session, user: User) -> None:
    roles = set(
        db.scalars(
            select(Role.code)
            .join(
                user_roles,
                Role.id == user_roles.c.role_id,
            )
            .where(
                user_roles.c.user_id == user.id
            )
        ).all()
    )

    if not roles.intersection(
        LEAVE_DECISION_ROLES
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Only an MD can approve or reject "
                "employee leave requests."
            ),
        )

def create_type(db: Session, user: User, data: LeaveTypeCreate) -> LeaveType:
    require_approver(db, user)
    item = LeaveType(organization_id=user.organization_id, **data.model_dump(), is_active=True)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Leave type code already exists") from exc
    db.refresh(item)
    return item


def list_types(db: Session, user: User) -> list[LeaveType]:
    return list(db.scalars(select(LeaveType).where(LeaveType.organization_id == user.organization_id, LeaveType.is_active.is_(True)).order_by(LeaveType.name)).all())


def create_holiday(db: Session, user: User, data: HolidayCreate) -> Holiday:
    require_approver(db, user)
    item = Holiday(organization_id=user.organization_id, **data.model_dump(), is_active=True)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Holiday already exists on this date") from exc
    db.refresh(item)
    return item


def list_holidays(db: Session, user: User, start: date, end: date) -> list[Holiday]:
    return list(db.scalars(select(Holiday).where(Holiday.organization_id == user.organization_id, Holiday.holiday_date >= start, Holiday.holiday_date <= end, Holiday.is_active.is_(True)).order_by(Holiday.holiday_date)).all())


def ensure_balance(db: Session, user: User, employee_id: UUID, leave_type: LeaveType, year: int) -> LeaveBalance:
    balance = db.scalar(select(LeaveBalance).where(LeaveBalance.employee_id == employee_id, LeaveBalance.leave_type_id == leave_type.id, LeaveBalance.year == year))
    if balance is None:
        balance = LeaveBalance(organization_id=user.organization_id, employee_id=employee_id, leave_type_id=leave_type.id, year=year, allocated_days=leave_type.days_per_year, used_days=0, pending_days=0)
        db.add(balance)
        db.flush()
    return balance


def my_balances(db: Session, user: User, year: int) -> list[dict]:
    employee = get_employee_for_user(db, user)
    result = []
    for leave_type in list_types(db, user):
        balance = ensure_balance(db, user, employee.id, leave_type, year)
        result.append({"leave_type_id": leave_type.id, "leave_type_code": leave_type.code, "leave_type_name": leave_type.name, "year": year, "allocated_days": balance.allocated_days, "used_days": balance.used_days, "pending_days": balance.pending_days, "available_days": max(0, balance.allocated_days - balance.used_days - balance.pending_days)})
    db.commit()
    return result


def working_days(db: Session, user: User, start: date, end: date) -> float:
    holidays = set(db.scalars(select(Holiday.holiday_date).where(Holiday.organization_id == user.organization_id, Holiday.holiday_date >= start, Holiday.holiday_date <= end, Holiday.is_active.is_(True), Holiday.is_optional.is_(False))).all())
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            count += 1
        current += timedelta(days=1)
    return float(count)


def submit_request(db: Session, user: User, data: LeaveRequestCreate) -> LeaveRequest:
    employee = get_employee_for_user(db, user)
    leave_type = db.scalar(select(LeaveType).where(LeaveType.id == data.leave_type_id, LeaveType.organization_id == user.organization_id, LeaveType.is_active.is_(True)))
    if leave_type is None:
        raise HTTPException(status_code=404, detail="Leave type not found")
    overlap = db.scalar(select(LeaveRequest.id).where(LeaveRequest.employee_id == employee.id, LeaveRequest.status.in_(["PENDING", "APPROVED"]), LeaveRequest.start_date <= data.end_date, LeaveRequest.end_date >= data.start_date))
    if overlap:
        raise HTTPException(status_code=409, detail="Overlapping leave request exists")
    days = working_days(db, user, data.start_date, data.end_date)
    if days <= 0:
        raise HTTPException(status_code=422, detail="Selected period has no working days")
    if leave_type.document_required_after_days and days >= leave_type.document_required_after_days and not data.attachment_urls:
        raise HTTPException(status_code=422, detail="Supporting document is required")
    balance = ensure_balance(db, user, employee.id, leave_type, data.start_date.year)
    available = balance.allocated_days - balance.used_days - balance.pending_days
    if leave_type.is_paid and days > available:
        raise HTTPException(status_code=409, detail={"message": "Insufficient leave balance", "available_days": available})
    item = LeaveRequest(organization_id=user.organization_id, employee_id=employee.id, leave_type_id=leave_type.id, start_date=data.start_date, end_date=data.end_date, total_days=days, reason=data.reason, attachment_urls=data.attachment_urls, status="PENDING")
    balance.pending_days += days
    db.add(item)
    db.flush()
    queue_role_notifications(
        db,
        organization_id=user.organization_id,
        role_codes=LEAVE_DECISION_ROLES,
        title="New leave request",
        body=(
            f"{user.employee_code} - {employee.full_name} requested "
            f"{leave_type.name} from {item.start_date} to {item.end_date}."
        ),
        dedupe_prefix=f"leave:{item.id}:submitted",
        route=f"/module/leave?queue=leave&request={item.id}",
        module="leave",
        event="LEAVE_SUBMITTED",
        entity_id=item.id,
        exclude_user_ids={user.id},
    )
    db.commit()
    db.refresh(item)
    return item


def my_requests(db: Session, user: User) -> list[LeaveRequest]:
    employee = get_employee_for_user(db, user)
    return list(db.scalars(select(LeaveRequest).where(LeaveRequest.employee_id == employee.id, LeaveRequest.organization_id == user.organization_id).order_by(LeaveRequest.created_at.desc())).all())


def pending_requests(db: Session, user: User) -> list[dict]:
    require_leave_md(db, user)
    rows = db.execute(select(LeaveRequest, Employee, User, LeaveType).join(Employee, LeaveRequest.employee_id == Employee.id).join(User, Employee.user_id == User.id).join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id).where(LeaveRequest.organization_id == user.organization_id, LeaveRequest.status == "PENDING").order_by(LeaveRequest.created_at)).all()
    return [{"id": r.id, "employee_id": e.id, "employee_code": u.employee_code, "employee_name": e.full_name, "leave_type_id": t.id, "leave_type_code": t.code, "leave_type_name": t.name, "start_date": r.start_date, "end_date": r.end_date, "total_days": r.total_days, "reason": r.reason, "attachment_urls": r.attachment_urls, "status": r.status, "approver_user_id": r.approver_user_id, "decided_at": r.decided_at, "decision_note": r.decision_note, "created_at": r.created_at, "updated_at": r.updated_at} for r, e, u, t in rows]


def decide_request(db: Session, user: User, request_id: UUID, approve: bool, data: DecisionIn) -> LeaveRequest:
    require_leave_md(db, user)
    item = db.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id, LeaveRequest.organization_id == user.organization_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if item.status != "PENDING":
        raise HTTPException(status_code=409, detail="Only pending requests can be decided")
    leave_type = db.get(LeaveType, item.leave_type_id)
    balance = ensure_balance(db, user, item.employee_id, leave_type, item.start_date.year)
    balance.pending_days = max(0, balance.pending_days - item.total_days)
    item.approver_user_id = user.id
    item.decided_at = datetime.now(timezone.utc)
    item.decision_note = data.note
    if approve:
        item.status = "APPROVED"
        balance.used_days += item.total_days
        current = item.start_date
        while current <= item.end_date:
            if current.weekday() < 5:
                attendance = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == item.employee_id, AttendanceRecord.attendance_date == current))
                if attendance is None:
                    attendance = AttendanceRecord(organization_id=user.organization_id, employee_id=item.employee_id, attendance_date=current, status="ON_LEAVE")
                    db.add(attendance)
                elif attendance.check_in_at is None:
                    attendance.status = "ON_LEAVE"
            current += timedelta(days=1)
    else:
        item.status = "REJECTED"

    employee = db.get(Employee, item.employee_id)
    recipient_user_id = employee.user_id if employee else None
    decision = "approved" if approve else "rejected"
    queue_user_notification(
        db,
        organization_id=user.organization_id,
        recipient_user_id=recipient_user_id,
        title=f"Leave request {decision}",
        body=(
            f"Your leave request from {item.start_date} to {item.end_date} "
            f"was {decision} by {user.employee_code}."
        ),
        dedupe_key=f"leave:{item.id}:{decision}",
        route="/module/leave?mine=1",
        module="leave",
        event=f"LEAVE_{item.status}",
        entity_id=item.id,
    )

    if approve:
        employee_user = (
            db.get(User, employee.user_id)
            if employee is not None
            else None
        )

        employee_code = (
            employee_user.employee_code
            if employee_user is not None
            else "Employee"
        )

        employee_name = (
            employee.full_name
            if employee is not None
            else ""
        )

        leave_name = (
            leave_type.name
            if leave_type is not None
            else "Leave"
        )

        queue_role_notifications(
            db,
            organization_id=user.organization_id,
            role_codes=LEAVE_APPROVAL_NOTICE_ROLES,
            title="Leave approved by MD",
            body=(
                f"{employee_code}"
                f"{' - ' + employee_name if employee_name else ''} "
                f"was approved for {leave_name} from "
                f"{item.start_date} to {item.end_date} "
                f"({item.total_days:g} day(s)) by "
                f"{user.employee_code}."
            ),
            dedupe_prefix=(
                f"leave:{item.id}:admin-approved"
            ),
            route="/module/leave",
            module="leave",
            event="LEAVE_APPROVED_ADMIN_NOTICE",
            entity_id=item.id,
            exclude_user_ids={user.id},
        )

    db.commit()
    db.refresh(item)
    return item


def cancel_request(db: Session, user: User, request_id: UUID) -> LeaveRequest:
    employee = get_employee_for_user(db, user)
    item = db.scalar(select(LeaveRequest).where(LeaveRequest.id == request_id, LeaveRequest.employee_id == employee.id, LeaveRequest.organization_id == user.organization_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    if item.status != "PENDING":
        raise HTTPException(status_code=409, detail="Only pending requests can be cancelled")
    leave_type = db.get(LeaveType, item.leave_type_id)
    balance = ensure_balance(db, user, employee.id, leave_type, item.start_date.year)
    balance.pending_days = max(0, balance.pending_days - item.total_days)
    item.status = "CANCELLED"
    db.commit()
    db.refresh(item)
    return item


def submit_regularization(db: Session, user: User, data: RegularizationCreate) -> AttendanceRegularization:
    employee = get_employee_for_user(db, user)
    exists = db.scalar(select(AttendanceRegularization.id).where(AttendanceRegularization.employee_id == employee.id, AttendanceRegularization.attendance_date == data.attendance_date, AttendanceRegularization.status == "PENDING"))
    if exists:
        raise HTTPException(status_code=409, detail="Pending regularisation already exists")
    item = AttendanceRegularization(organization_id=user.organization_id, employee_id=employee.id, **data.model_dump(), status="PENDING")
    db.add(item)
    db.flush()
    queue_role_notifications(
        db,
        organization_id=user.organization_id,
        role_codes=APPROVER_ROLES,
        title="Attendance regularization request",
        body=(
            f"{user.employee_code} - {employee.full_name} requested attendance "
            f"regularization for {item.attendance_date}."
        ),
        dedupe_prefix=f"regularization:{item.id}:submitted",
        route=f"/module/leave?queue=regularizations&regularization={item.id}",
        module="leave",
        event="REGULARIZATION_SUBMITTED",
        entity_id=item.id,
        exclude_user_ids={user.id},
    )
    db.commit()
    db.refresh(item)
    return item


def my_regularizations(db: Session, user: User) -> list[AttendanceRegularization]:
    employee = get_employee_for_user(db, user)
    return list(db.scalars(select(AttendanceRegularization).where(AttendanceRegularization.employee_id == employee.id, AttendanceRegularization.organization_id == user.organization_id).order_by(AttendanceRegularization.created_at.desc())).all())


def pending_regularizations(db: Session, user: User) -> list[dict]:
    require_approver(db, user)
    rows = db.execute(select(AttendanceRegularization, Employee, User).join(Employee, AttendanceRegularization.employee_id == Employee.id).join(User, Employee.user_id == User.id).where(AttendanceRegularization.organization_id == user.organization_id, AttendanceRegularization.status == "PENDING").order_by(AttendanceRegularization.created_at)).all()
    return [{"id": r.id, "employee_id": e.id, "employee_code": u.employee_code, "employee_name": e.full_name, "attendance_date": r.attendance_date, "requested_check_in_at": r.requested_check_in_at, "requested_check_out_at": r.requested_check_out_at, "reason": r.reason, "status": r.status, "approver_user_id": r.approver_user_id, "decided_at": r.decided_at, "decision_note": r.decision_note, "created_at": r.created_at, "updated_at": r.updated_at} for r, e, u in rows]


def decide_regularization(db: Session, user: User, item_id: UUID, approve: bool, data: DecisionIn) -> AttendanceRegularization:
    require_approver(db, user)
    item = db.scalar(select(AttendanceRegularization).where(AttendanceRegularization.id == item_id, AttendanceRegularization.organization_id == user.organization_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Regularisation not found")
    if item.status != "PENDING":
        raise HTTPException(status_code=409, detail="Only pending regularisations can be decided")
    item.approver_user_id = user.id
    item.decided_at = datetime.now(timezone.utc)
    item.decision_note = data.note
    if approve:
        item.status = "APPROVED"
        attendance = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == item.employee_id, AttendanceRecord.attendance_date == item.attendance_date))
        if attendance is None:
            attendance = AttendanceRecord(organization_id=user.organization_id, employee_id=item.employee_id, attendance_date=item.attendance_date)
            db.add(attendance)
        if item.requested_check_in_at is not None:
            attendance.check_in_at = item.requested_check_in_at
        if item.requested_check_out_at is not None:
            attendance.check_out_at = item.requested_check_out_at
        attendance.status = "REGULARIZED"
        if attendance.check_in_at and attendance.check_out_at:
            attendance.worked_minutes = max(0, int((attendance.check_out_at - attendance.check_in_at).total_seconds() // 60))
    else:
        item.status = "REJECTED"

    employee = db.get(Employee, item.employee_id)
    recipient_user_id = employee.user_id if employee else None
    decision = "approved" if approve else "rejected"
    queue_user_notification(
        db,
        organization_id=user.organization_id,
        recipient_user_id=recipient_user_id,
        title=f"Attendance regularization {decision}",
        body=(
            f"Your attendance regularization for {item.attendance_date} "
            f"was {decision} by {user.employee_code}."
        ),
        dedupe_key=f"regularization:{item.id}:{decision}",
        route="/module/leave?mine=1",
        module="leave",
        event=f"REGULARIZATION_{item.status}",
        entity_id=item.id,
    )
    db.commit()
    db.refresh(item)
    return item
