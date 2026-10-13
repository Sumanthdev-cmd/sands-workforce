from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Employee,
    PayrollItem,
    PayrollRun,
    Role,
    SalaryAdvanceRecovery,
    SalaryAdvanceRequest,
    User,
    Vendor,
    VendorSalaryAdvanceRecovery,
    VendorSalaryAdvanceRequest,
    user_roles,
)
from app.schemas.salary_advance import (
    SalaryAdvanceCancelRequest,
    SalaryAdvanceCreateRequest,
    SalaryAdvanceDecisionRequest,
    SalaryAdvanceDisbursementRequest,
)
from app.services.device_service import get_employee_for_user
from app.services.notification_service import (
    queue_role_notifications,
    queue_user_notification,
)


ADMIN_ROLE = "ADMIN"
MD_ROLE = "MD"
ADVANCE_VIEW_ROLES = {ADMIN_ROLE, MD_ROLE}
RECOVERABLE_STATUSES = {"DISBURSED", "RECOVERING"}


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_role(database: Session, user: User, required: str, message: str) -> None:
    if required not in role_codes(database, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )


def require_advance_view(database: Session, user: User) -> None:
    if not role_codes(database, user).intersection(ADVANCE_VIEW_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN and MD can view organization salary advances.",
        )


def employee_identity(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
) -> tuple[Employee, User]:
    row = database.execute(
        select(Employee, User)
        .join(User, Employee.user_id == User.id)
        .where(
            Employee.id == employee_id,
            Employee.organization_id == organization_id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Employee was not found.")
    return row[0], row[1]


def recovery_rows(
    database: Session,
    advance_id: UUID,
) -> list[SalaryAdvanceRecovery]:
    return list(
        database.scalars(
            select(SalaryAdvanceRecovery)
            .where(
                SalaryAdvanceRecovery.salary_advance_request_id == advance_id
            )
            .order_by(SalaryAdvanceRecovery.recovered_at)
        ).all()
    )


def vendor_recovery_rows(
    database: Session,
    advance_id: UUID,
) -> list[VendorSalaryAdvanceRecovery]:
    return list(
        database.scalars(
            select(VendorSalaryAdvanceRecovery)
            .where(
                VendorSalaryAdvanceRecovery.vendor_salary_advance_request_id
                == advance_id
            )
            .order_by(VendorSalaryAdvanceRecovery.recovered_at)
        ).all()
    )


def salary_advance_dict(
    database: Session,
    row: SalaryAdvanceRequest,
) -> dict:
    employee, account = employee_identity(
        database,
        row.organization_id,
        row.employee_id,
    )
    recoveries = recovery_rows(database, row.id)
    recovered = round(row.recovered_amount or 0, 2)
    return {
        "id": row.id,
        "payee_type": "EMPLOYEE",
        "employee_id": row.employee_id,
        "employee_code": account.employee_code,
        "employee_name": employee.full_name,
        "vendor_id": None,
        "vendor_code": None,
        "vendor_name": None,
        "requested_amount": row.requested_amount,
        "installment_amount": row.installment_amount,
        "recovery_months": row.recovery_months,
        "recovered_amount": recovered,
        "remaining_amount": max(0, round(row.requested_amount - recovered, 2)),
        "installments_completed": len(recoveries),
        "currency": row.currency,
        "reason": row.reason,
        "status": row.status,
        "requested_at": row.requested_at,
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
        "disbursed_by_user_id": row.disbursed_by_user_id,
        "disbursed_at": row.disbursed_at,
        "disbursement_reference": row.disbursement_reference,
        "disbursement_note": row.disbursement_note,
        "recovery_start_date": row.recovery_start_date,
        "cancelled_at": row.cancelled_at,
        "cancellation_note": row.cancellation_note,
        "recoveries": [
            {
                "id": recovery.id,
                "payroll_run_id": recovery.payroll_run_id,
                "amount": recovery.amount,
                "recovered_at": recovery.recovered_at,
            }
            for recovery in recoveries
        ],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def vendor_identity(
    database: Session,
    organization_id: UUID,
    vendor_id: UUID,
) -> Vendor:
    vendor = database.scalar(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.organization_id == organization_id,
        )
    )
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor was not found.")
    return vendor


def vendor_salary_advance_dict(
    database: Session,
    row: VendorSalaryAdvanceRequest,
) -> dict:
    vendor = vendor_identity(database, row.organization_id, row.vendor_id)
    recoveries = vendor_recovery_rows(database, row.id)
    recovered = round(row.recovered_amount or 0, 2)
    return {
        "id": row.id,
        "payee_type": "VENDOR",
        "employee_id": None,
        "employee_code": vendor.code,
        "employee_name": vendor.name,
        "vendor_id": row.vendor_id,
        "vendor_code": vendor.code,
        "vendor_name": vendor.name,
        "requested_amount": row.requested_amount,
        "installment_amount": row.installment_amount,
        "recovery_months": row.recovery_months,
        "recovered_amount": recovered,
        "remaining_amount": max(0, round(row.requested_amount - recovered, 2)),
        "installments_completed": len(recoveries),
        "currency": row.currency,
        "reason": row.reason,
        "status": row.status,
        "requested_at": row.requested_at,
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
        "disbursed_by_user_id": row.disbursed_by_user_id,
        "disbursed_at": row.disbursed_at,
        "disbursement_reference": row.disbursement_reference,
        "disbursement_note": row.disbursement_note,
        "recovery_start_date": row.recovery_start_date,
        "cancelled_at": row.cancelled_at,
        "cancellation_note": row.cancellation_note,
        "recoveries": [
            {
                "id": recovery.id,
                "payroll_run_id": recovery.payroll_run_id,
                "amount": recovery.amount,
                "recovered_at": recovery.recovered_at,
            }
            for recovery in recoveries
        ],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get_advance(
    database: Session,
    user: User,
    request_id: UUID,
    *,
    own_only: bool = False,
) -> SalaryAdvanceRequest:
    statement = select(SalaryAdvanceRequest).where(
        SalaryAdvanceRequest.id == request_id,
        SalaryAdvanceRequest.organization_id == user.organization_id,
    )
    if own_only:
        employee = get_employee_for_user(database, user)
        statement = statement.where(
            SalaryAdvanceRequest.employee_id == employee.id
        )
    row = database.scalar(statement)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Salary advance request was not found.",
        )
    return row


def get_vendor_advance(
    database: Session,
    organization_id: UUID,
    request_id: UUID,
    *,
    vendor_id: UUID | None = None,
) -> VendorSalaryAdvanceRequest:
    statement = select(VendorSalaryAdvanceRequest).where(
        VendorSalaryAdvanceRequest.id == request_id,
        VendorSalaryAdvanceRequest.organization_id == organization_id,
    )
    if vendor_id is not None:
        statement = statement.where(
            VendorSalaryAdvanceRequest.vendor_id == vendor_id
        )
    row = database.scalar(statement)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor salary advance request was not found.",
        )
    return row


def create_salary_advance(
    database: Session,
    user: User,
    payload: SalaryAdvanceCreateRequest,
) -> dict:
    employee = get_employee_for_user(database, user)
    now = datetime.now(timezone.utc)
    row = SalaryAdvanceRequest(
        organization_id=user.organization_id,
        employee_id=employee.id,
        requested_by_user_id=user.id,
        requested_amount=round(payload.requested_amount, 2),
        installment_amount=round(payload.installment_amount, 2),
        recovery_months=payload.recovery_months,
        recovered_amount=0,
        currency=payload.currency.strip().upper(),
        reason=payload.reason.strip(),
        status="PENDING",
        requested_at=now,
    )
    database.add(row)
    database.flush()
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ADMIN_ROLE, MD_ROLE},
        title="Salary advance request submitted",
        body=(
            f"{user.employee_code} — {employee.full_name} requested "
            f"{row.currency} {row.requested_amount:,.2f}. Proposed recovery: "
            f"{row.currency} {row.installment_amount:,.2f} for "
            f"{row.recovery_months} payroll month(s). Reason: {row.reason}"
        ),
        dedupe_prefix=f"salary-advance:{row.id}:requested",
        route="/module/payroll?advance=1",
        module="payroll",
        event="SALARY_ADVANCE_REQUESTED",
        entity_id=row.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(row)
    return salary_advance_dict(database, row)


def list_my_salary_advances(database: Session, user: User) -> list[dict]:
    employee = get_employee_for_user(database, user)
    rows = database.scalars(
        select(SalaryAdvanceRequest)
        .where(
            SalaryAdvanceRequest.organization_id == user.organization_id,
            SalaryAdvanceRequest.employee_id == employee.id,
        )
        .order_by(SalaryAdvanceRequest.requested_at.desc())
        .limit(100)
    ).all()
    return [salary_advance_dict(database, row) for row in rows]


def list_organization_salary_advances(
    database: Session,
    user: User,
    status_filter: str | None,
) -> list[dict]:
    require_advance_view(database, user)
    normalized_status = status_filter.strip().upper() if status_filter else None
    statement = select(SalaryAdvanceRequest).where(
        SalaryAdvanceRequest.organization_id == user.organization_id
    )
    if normalized_status:
        statement = statement.where(
            SalaryAdvanceRequest.status == normalized_status
        )
    employee_rows = database.scalars(
        statement.order_by(SalaryAdvanceRequest.requested_at.desc()).limit(300)
    ).all()
    vendor_statement = select(VendorSalaryAdvanceRequest).where(
        VendorSalaryAdvanceRequest.organization_id == user.organization_id
    )
    if normalized_status:
        vendor_statement = vendor_statement.where(
            VendorSalaryAdvanceRequest.status == normalized_status
        )
    vendor_rows = database.scalars(
        vendor_statement.order_by(VendorSalaryAdvanceRequest.requested_at.desc()).limit(300)
    ).all()
    rows = [salary_advance_dict(database, row) for row in employee_rows]
    rows.extend(vendor_salary_advance_dict(database, row) for row in vendor_rows)
    rows.sort(key=lambda value: value["requested_at"], reverse=True)
    return rows[:300]


def create_vendor_salary_advance(
    database: Session,
    context,
    payload: SalaryAdvanceCreateRequest,
) -> dict:
    now = datetime.now(timezone.utc)
    row = VendorSalaryAdvanceRequest(
        organization_id=context.organization_id,
        vendor_id=context.vendor_id,
        requested_by_vendor_account_id=context.account_id,
        requested_amount=round(payload.requested_amount, 2),
        installment_amount=round(payload.installment_amount, 2),
        recovery_months=payload.recovery_months,
        recovered_amount=0,
        currency=payload.currency.strip().upper(),
        reason=payload.reason.strip(),
        status="PENDING",
        requested_at=now,
    )
    database.add(row)
    database.flush()
    queue_role_notifications(
        database,
        organization_id=context.organization_id,
        role_codes={ADMIN_ROLE, MD_ROLE},
        title="Vendor salary advance request submitted",
        body=(
            f"{context.vendor_code} — {context.vendor_name} requested "
            f"{row.currency} {row.requested_amount:,.2f}. Proposed recovery: "
            f"{row.currency} {row.installment_amount:,.2f} for "
            f"{row.recovery_months} payroll month(s). Reason: {row.reason}"
        ),
        dedupe_prefix=f"vendor-salary-advance:{row.id}:requested",
        route="/module/payroll?advance=1",
        module="payroll",
        event="VENDOR_SALARY_ADVANCE_REQUESTED",
        entity_id=row.id,
    )
    database.commit()
    database.refresh(row)
    return vendor_salary_advance_dict(database, row)


def list_my_vendor_salary_advances(database: Session, context) -> list[dict]:
    rows = database.scalars(
        select(VendorSalaryAdvanceRequest)
        .where(
            VendorSalaryAdvanceRequest.organization_id == context.organization_id,
            VendorSalaryAdvanceRequest.vendor_id == context.vendor_id,
        )
        .order_by(VendorSalaryAdvanceRequest.requested_at.desc())
        .limit(100)
    ).all()
    return [vendor_salary_advance_dict(database, row) for row in rows]


def decide_salary_advance(
    database: Session,
    user: User,
    request_id: UUID,
    payload: SalaryAdvanceDecisionRequest,
) -> dict:
    require_role(
        database,
        user,
        MD_ROLE,
        "Only an MD can approve or reject a salary advance.",
    )
    try:
        row = get_advance(database, user, request_id)
        is_vendor_request = False
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise
        row = get_vendor_advance(database, user.organization_id, request_id)
        is_vendor_request = True
    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a pending salary advance can be decided.",
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
    if is_vendor_request:
        vendor = vendor_identity(database, user.organization_id, row.vendor_id)
        queue_role_notifications(
            database,
            organization_id=user.organization_id,
            role_codes={ADMIN_ROLE},
            title=f"Vendor salary advance {row.status.lower()} by MD",
            body=(
                f"{vendor.code} — {vendor.name}: "
                f"{row.currency} {row.requested_amount:,.2f}."
            ),
            dedupe_prefix=f"vendor-salary-advance:{row.id}:decision:{row.status}:admin",
            route="/module/payroll?advance=1",
            module="payroll",
            event=f"VENDOR_SALARY_ADVANCE_{row.status}",
            entity_id=row.id,
            exclude_user_ids={user.id},
        )
        database.commit()
        database.refresh(row)
        return vendor_salary_advance_dict(database, row)
    employee, account = employee_identity(
        database,
        user.organization_id,
        row.employee_id,
    )
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id,
        title=f"Salary advance {row.status.lower()}",
        body=(
            f"Your request for {row.currency} {row.requested_amount:,.2f} was "
            f"{row.status.lower()} by MD."
            + (f" Note: {row.decision_note}" if row.decision_note else "")
        ),
        dedupe_key=f"salary-advance:{row.id}:decision:{row.status}:employee",
        route="/module/payroll?advance=1",
        module="payroll",
        event=f"SALARY_ADVANCE_{row.status}",
        entity_id=row.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ADMIN_ROLE},
        title=f"Salary advance {row.status.lower()} by MD",
        body=(
            f"{account.employee_code} — {employee.full_name}: "
            f"{row.currency} {row.requested_amount:,.2f}."
        ),
        dedupe_prefix=f"salary-advance:{row.id}:decision:{row.status}:admin",
        route="/module/payroll?advance=1",
        module="payroll",
        event=f"SALARY_ADVANCE_{row.status}",
        entity_id=row.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(row)
    return salary_advance_dict(database, row)


def next_month_start(now: datetime, user: User) -> date:
    timezone_name = getattr(getattr(user, "organization", None), "timezone", None)
    try:
        zone = ZoneInfo(timezone_name or "Asia/Kolkata")
    except Exception:
        zone = ZoneInfo("Asia/Kolkata")
    local_now = now.astimezone(zone)
    if local_now.month == 12:
        return date(local_now.year + 1, 1, 1)
    return date(local_now.year, local_now.month + 1, 1)


def disburse_salary_advance(
    database: Session,
    user: User,
    request_id: UUID,
    payload: SalaryAdvanceDisbursementRequest,
) -> dict:
    require_role(
        database,
        user,
        ADMIN_ROLE,
        "Only ADMIN can record salary-advance disbursement.",
    )
    try:
        row = get_advance(database, user, request_id)
        is_vendor_request = False
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise
        row = get_vendor_advance(database, user.organization_id, request_id)
        is_vendor_request = True
    if row.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="MD approval is required before an advance can be disbursed.",
        )
    now = datetime.now(timezone.utc)
    row.status = "DISBURSED"
    row.disbursed_by_user_id = user.id
    row.disbursed_at = now
    row.disbursement_reference = payload.payment_reference.strip()
    row.disbursement_note = (payload.note or "").strip() or None
    row.recovery_start_date = next_month_start(now, user)
    if is_vendor_request:
        vendor = vendor_identity(database, user.organization_id, row.vendor_id)
        queue_role_notifications(
            database,
            organization_id=user.organization_id,
            role_codes={MD_ROLE},
            title="Approved vendor salary advance disbursed",
            body=(
                f"ADMIN recorded {vendor.code} — {vendor.name}'s "
                f"advance as disbursed. Reference: {row.disbursement_reference}."
            ),
            dedupe_prefix=f"vendor-salary-advance:{row.id}:disbursed:md",
            route="/module/payroll?advance=1",
            module="payroll",
            event="VENDOR_SALARY_ADVANCE_DISBURSED",
            entity_id=row.id,
            exclude_user_ids={user.id},
        )
        database.commit()
        database.refresh(row)
        return vendor_salary_advance_dict(database, row)
    employee, account = employee_identity(
        database,
        user.organization_id,
        row.employee_id,
    )
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id,
        title="Salary advance disbursed",
        body=(
            f"Your {row.currency} {row.requested_amount:,.2f} salary advance was "
            f"recorded as disbursed. Recovery begins with payroll on or after "
            f"{row.recovery_start_date}: {row.currency} "
            f"{row.installment_amount:,.2f} per payroll month."
        ),
        dedupe_key=f"salary-advance:{row.id}:disbursed:employee",
        route="/module/payroll?advance=1",
        module="payroll",
        event="SALARY_ADVANCE_DISBURSED",
        entity_id=row.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={MD_ROLE},
        title="Approved salary advance disbursed",
        body=(
            f"ADMIN recorded {account.employee_code} — {employee.full_name}'s "
            f"advance as disbursed. Reference: {row.disbursement_reference}."
        ),
        dedupe_prefix=f"salary-advance:{row.id}:disbursed:md",
        route="/module/payroll?advance=1",
        module="payroll",
        event="SALARY_ADVANCE_DISBURSED",
        entity_id=row.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(row)
    return salary_advance_dict(database, row)


def cancel_salary_advance(
    database: Session,
    user: User,
    request_id: UUID,
    payload: SalaryAdvanceCancelRequest,
) -> dict:
    row = get_advance(database, user, request_id, own_only=True)
    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a pending salary advance request can be cancelled.",
        )
    now = datetime.now(timezone.utc)
    row.status = "CANCELLED"
    row.cancelled_at = now
    row.cancellation_note = payload.note.strip()
    employee = get_employee_for_user(database, user)
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ADMIN_ROLE, MD_ROLE},
        title="Salary advance request cancelled",
        body=(
            f"{user.employee_code} — {employee.full_name} cancelled the request for "
            f"{row.currency} {row.requested_amount:,.2f}."
        ),
        dedupe_prefix=f"salary-advance:{row.id}:cancelled",
        route="/module/payroll?advance=1",
        module="payroll",
        event="SALARY_ADVANCE_CANCELLED",
        entity_id=row.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(row)
    return salary_advance_dict(database, row)


def cancel_vendor_salary_advance(
    database: Session,
    context,
    request_id: UUID,
    payload: SalaryAdvanceCancelRequest,
) -> dict:
    row = get_vendor_advance(
        database,
        context.organization_id,
        request_id,
        vendor_id=context.vendor_id,
    )
    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a pending salary advance request can be cancelled.",
        )
    now = datetime.now(timezone.utc)
    row.status = "CANCELLED"
    row.cancelled_at = now
    row.cancellation_note = payload.note.strip()
    queue_role_notifications(
        database,
        organization_id=context.organization_id,
        role_codes={ADMIN_ROLE, MD_ROLE},
        title="Vendor salary advance request cancelled",
        body=(
            f"{context.vendor_code} — {context.vendor_name} cancelled the request for "
            f"{row.currency} {row.requested_amount:,.2f}."
        ),
        dedupe_prefix=f"vendor-salary-advance:{row.id}:cancelled",
        route="/module/payroll?advance=1",
        module="payroll",
        event="VENDOR_SALARY_ADVANCE_CANCELLED",
        entity_id=row.id,
    )
    database.commit()
    database.refresh(row)
    return vendor_salary_advance_dict(database, row)


def calculate_salary_advance_deductions(
    database: Session,
    *,
    organization_id: UUID,
    employee_id: UUID,
    payroll_period_end: date,
    available_net: float,
) -> tuple[float, list[dict]]:
    available = max(0, round(available_net, 2))
    total = 0.0
    allocations: list[dict] = []
    if available <= 0:
        return total, allocations

    rows = database.scalars(
        select(SalaryAdvanceRequest)
        .where(
            SalaryAdvanceRequest.organization_id == organization_id,
            SalaryAdvanceRequest.employee_id == employee_id,
            SalaryAdvanceRequest.status.in_(sorted(RECOVERABLE_STATUSES)),
            SalaryAdvanceRequest.recovery_start_date.is_not(None),
            SalaryAdvanceRequest.recovery_start_date <= payroll_period_end,
            SalaryAdvanceRequest.recovered_amount
            < SalaryAdvanceRequest.requested_amount,
        )
        .order_by(
            SalaryAdvanceRequest.recovery_start_date,
            SalaryAdvanceRequest.disbursed_at,
        )
    ).all()

    for row in rows:
        available_for_advance = round(available - total, 2)
        if available_for_advance <= 0:
            break
        remaining = max(
            0,
            round(row.requested_amount - (row.recovered_amount or 0), 2),
        )
        installment = min(
            round(row.installment_amount, 2),
            remaining,
            available_for_advance,
        )
        installment = round(installment, 2)
        if installment <= 0:
            continue
        allocations.append(
            {
                "salary_advance_request_id": str(row.id),
                "amount": installment,
                "currency": row.currency,
            }
        )
        total = round(total + installment, 2)

    return total, allocations


def calculate_vendor_salary_advance_deductions(
    database: Session,
    *,
    organization_id: UUID,
    vendor_id: UUID,
    payroll_period_end: date,
    available_net: float,
) -> tuple[float, list[dict]]:
    available = max(0, round(available_net, 2))
    total = 0.0
    allocations: list[dict] = []
    if available <= 0:
        return total, allocations

    rows = database.scalars(
        select(VendorSalaryAdvanceRequest)
        .where(
            VendorSalaryAdvanceRequest.organization_id == organization_id,
            VendorSalaryAdvanceRequest.vendor_id == vendor_id,
            VendorSalaryAdvanceRequest.status.in_(sorted(RECOVERABLE_STATUSES)),
            VendorSalaryAdvanceRequest.recovery_start_date.is_not(None),
            VendorSalaryAdvanceRequest.recovery_start_date <= payroll_period_end,
            VendorSalaryAdvanceRequest.recovered_amount
            < VendorSalaryAdvanceRequest.requested_amount,
        )
        .order_by(
            VendorSalaryAdvanceRequest.recovery_start_date,
            VendorSalaryAdvanceRequest.disbursed_at,
        )
    ).all()

    for row in rows:
        available_for_advance = round(available - total, 2)
        if available_for_advance <= 0:
            break
        remaining = max(
            0,
            round(row.requested_amount - (row.recovered_amount or 0), 2),
        )
        installment = min(
            round(row.installment_amount, 2),
            remaining,
            available_for_advance,
        )
        installment = round(installment, 2)
        if installment <= 0:
            continue
        allocations.append(
            {
                "vendor_salary_advance_request_id": str(row.id),
                "amount": installment,
                "currency": row.currency,
            }
        )
        total = round(total + installment, 2)

    return total, allocations


def finalize_salary_advance_recoveries(
    database: Session,
    *,
    user: User,
    payroll_run: PayrollRun,
) -> int:
    now = datetime.now(timezone.utc)
    created = 0
    items = database.scalars(
        select(PayrollItem).where(
            PayrollItem.organization_id == user.organization_id,
            PayrollItem.payroll_run_id == payroll_run.id,
            PayrollItem.salary_advance_deduction > 0,
        )
    ).all()

    for item in items:
        allocations = (item.calculation_details or {}).get(
            "salary_advance_allocations",
            [],
        )
        for allocation in allocations:
            try:
                request_id = UUID(str(allocation["salary_advance_request_id"]))
                amount = round(float(allocation["amount"]), 2)
            except (KeyError, TypeError, ValueError):
                continue
            if amount <= 0:
                continue
            existing = database.scalar(
                select(SalaryAdvanceRecovery.id).where(
                    SalaryAdvanceRecovery.salary_advance_request_id == request_id,
                    SalaryAdvanceRecovery.payroll_run_id == payroll_run.id,
                )
            )
            if existing is not None:
                continue
            advance = database.scalar(
                select(SalaryAdvanceRequest).where(
                    SalaryAdvanceRequest.id == request_id,
                    SalaryAdvanceRequest.organization_id == user.organization_id,
                    SalaryAdvanceRequest.employee_id == item.employee_id,
                    SalaryAdvanceRequest.status.in_(
                        sorted(RECOVERABLE_STATUSES)
                    ),
                )
            )
            if advance is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A salary advance changed after payroll calculation. "
                        "Return and recalculate payroll before approval."
                    ),
                )
            remaining_before = max(
                0,
                round(
                    advance.requested_amount - (advance.recovered_amount or 0),
                    2,
                ),
            )
            if amount > remaining_before:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A salary advance recovery amount is no longer current. "
                        "Return and recalculate payroll before approval."
                    ),
                )
            database.add(
                SalaryAdvanceRecovery(
                    organization_id=user.organization_id,
                    salary_advance_request_id=advance.id,
                    payroll_run_id=payroll_run.id,
                    employee_id=item.employee_id,
                    amount=amount,
                    recovered_at=now,
                    recorded_by_user_id=user.id,
                )
            )
            advance.recovered_amount = round(
                (advance.recovered_amount or 0) + amount,
                2,
            )
            remaining_after = max(
                0,
                round(advance.requested_amount - advance.recovered_amount, 2),
            )
            advance.status = "RECOVERED" if remaining_after <= 0 else "RECOVERING"
            employee, _ = employee_identity(
                database,
                user.organization_id,
                item.employee_id,
            )
            queue_user_notification(
                database,
                organization_id=user.organization_id,
                recipient_user_id=employee.user_id,
                title="Salary advance installment recovered",
                body=(
                    f"{advance.currency} {amount:,.2f} was deducted in finalized "
                    f"payroll. Remaining advance: {advance.currency} "
                    f"{remaining_after:,.2f}."
                ),
                dedupe_key=(
                    f"salary-advance:{advance.id}:recovery:{payroll_run.id}:employee"
                ),
                route="/module/payroll?advance=1",
                module="payroll",
                event=(
                    "SALARY_ADVANCE_RECOVERED"
                    if remaining_after <= 0
                    else "SALARY_ADVANCE_INSTALLMENT_RECOVERED"
                ),
                entity_id=advance.id,
            )
            created += 1

    return created


def finalize_vendor_salary_advance_recoveries(
    database: Session,
    *,
    user: User,
    payroll_run: PayrollRun,
) -> int:
    from app.models import VendorPayrollItem

    now = datetime.now(timezone.utc)
    created = 0
    items = database.scalars(
        select(VendorPayrollItem).where(
            VendorPayrollItem.organization_id == user.organization_id,
            VendorPayrollItem.payroll_run_id == payroll_run.id,
            VendorPayrollItem.salary_advance_deduction > 0,
        )
    ).all()

    for item in items:
        allocations = (item.calculation_details or {}).get(
            "vendor_salary_advance_allocations",
            [],
        )
        for allocation in allocations:
            try:
                request_id = UUID(str(allocation["vendor_salary_advance_request_id"]))
                amount = round(float(allocation["amount"]), 2)
            except (KeyError, TypeError, ValueError):
                continue
            if amount <= 0:
                continue
            existing = database.scalar(
                select(VendorSalaryAdvanceRecovery.id).where(
                    VendorSalaryAdvanceRecovery.vendor_salary_advance_request_id
                    == request_id,
                    VendorSalaryAdvanceRecovery.payroll_run_id == payroll_run.id,
                )
            )
            if existing is not None:
                continue
            advance = database.scalar(
                select(VendorSalaryAdvanceRequest).where(
                    VendorSalaryAdvanceRequest.id == request_id,
                    VendorSalaryAdvanceRequest.organization_id == user.organization_id,
                    VendorSalaryAdvanceRequest.vendor_id == item.vendor_id,
                    VendorSalaryAdvanceRequest.status.in_(
                        sorted(RECOVERABLE_STATUSES)
                    ),
                )
            )
            if advance is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A vendor salary advance changed after payroll calculation. "
                        "Return and recalculate payroll before approval."
                    ),
                )
            remaining_before = max(
                0,
                round(
                    advance.requested_amount - (advance.recovered_amount or 0),
                    2,
                ),
            )
            if amount > remaining_before:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "A vendor salary advance recovery amount is no longer current. "
                        "Return and recalculate payroll before approval."
                    ),
                )
            database.add(
                VendorSalaryAdvanceRecovery(
                    organization_id=user.organization_id,
                    vendor_salary_advance_request_id=advance.id,
                    payroll_run_id=payroll_run.id,
                    vendor_id=item.vendor_id,
                    amount=amount,
                    recovered_at=now,
                    recorded_by_user_id=user.id,
                )
            )
            advance.recovered_amount = round(
                (advance.recovered_amount or 0) + amount,
                2,
            )
            remaining_after = max(
                0,
                round(advance.requested_amount - advance.recovered_amount, 2),
            )
            advance.status = "RECOVERED" if remaining_after <= 0 else "RECOVERING"
            created += 1

    return created
