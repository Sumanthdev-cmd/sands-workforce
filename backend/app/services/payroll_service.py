from app.services.catalogue_service import catalogue_visible
from app.services.payroll_eligibility import has_remuneration
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AttendanceRecord,
    Employee,
    Holiday,
    LeaveRequest,
    LeaveType,
    PayrollItem,
    PayrollRun,
    Outlet,
    Role,
    SalaryHold,
    SalaryRevision,
    SalaryStructure,
    User,
    Vendor,
    VendorClosureDay,
    VendorPayrollItem,
    VendorSalaryStructure,
    user_roles,
)
from app.schemas.payroll import (
    PayrollRunApprovalRequest,
    PayrollRunCreateRequest,
    PayrollRunReturnRequest,
    PayrollRunSubmitRequest,
    SalaryHoldCreateRequest,
    SalaryHoldReleaseRequest,
    SalaryRevisionRequest,
    SalaryStructureCreateRequest,
    VendorClosureCreateRequest,
    VendorSalaryStructureRequest,
)
from app.services.device_service import get_employee_for_user
from app.services.notification_service import queue_role_notifications, queue_user_notification
from app.services.salary_advance_service import (
    calculate_salary_advance_deductions,
    calculate_vendor_salary_advance_deductions,
    finalize_salary_advance_recoveries,
    finalize_vendor_salary_advance_recoveries,
)
from app.services.security_overtime_service import (
    approved_overtime_for_period,
    finalize_overtime_benefits,
    late_payroll_policy,
)


PAYROLL_ADMIN_ROLES = {"ADMIN", "MD", "GM"}
PAYROLL_PREPARER_ROLES = {"ADMIN", "GM"}
MD_ROLE = "MD"
SALARY_CREATOR_ROLE = "ADMIN"


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_payroll_admin(database: Session, user: User) -> None:
    if not role_codes(database, user).intersection(PAYROLL_ADMIN_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payroll administration access is required.",
        )


def require_payroll_preparer(database: Session, user: User) -> None:
    if not role_codes(database, user).intersection(PAYROLL_PREPARER_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN or GM can prepare, calculate, or submit payroll.",
        )


def require_md(database: Session, user: User) -> None:
    if MD_ROLE not in role_codes(database, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an MD can perform this action.",
        )


def require_salary_creator(database: Session, user: User) -> None:
    if SALARY_CREATOR_ROLE not in role_codes(database, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN can fix an employee's initial salary.",
        )


def find_employee(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
) -> Employee:
    employee = database.scalar(
        select(Employee).where(
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


def create_salary_structure(
    database: Session,
    user: User,
    employee_id: UUID,
    payload: SalaryStructureCreateRequest,
) -> SalaryStructure:
    require_salary_creator(database, user)
    find_employee(database, user.organization_id, employee_id)

    existing = database.scalar(
        select(func.count(SalaryStructure.id)).where(
            SalaryStructure.employee_id == employee_id
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Salary structure exists. Use the MD revision endpoint.",
        )

    structure = SalaryStructure(
        organization_id=user.organization_id,
        employee_id=employee_id,
        effective_from=payload.effective_from,
        basic_salary=payload.basic_salary,
        hra=payload.hra,
        conveyance_allowance=payload.conveyance_allowance,
        other_allowance=payload.other_allowance,
        daily_allowance=payload.daily_allowance,
        fixed_deduction=payload.fixed_deduction,
        currency=payload.currency.strip().upper(),
        created_by_user_id=user.id,
    )
    database.add(structure)
    database.commit()
    database.refresh(structure)
    return structure


def list_salary_structures(
    database: Session,
    user: User,
    employee_id: UUID,
) -> list[SalaryStructure]:
    require_payroll_admin(database, user)
    find_employee(database, user.organization_id, employee_id)

    return list(
        database.scalars(
            select(SalaryStructure)
            .where(
                SalaryStructure.organization_id == user.organization_id,
                SalaryStructure.employee_id == employee_id,
            )
            .order_by(SalaryStructure.effective_from.desc())
        ).all()
    )


def revise_salary(
    database: Session,
    user: User,
    employee_id: UUID,
    payload: SalaryRevisionRequest,
) -> SalaryStructure:
    require_md(database, user)
    find_employee(database, user.organization_id, employee_id)

    previous = database.scalar(
        select(SalaryStructure)
        .where(
            SalaryStructure.employee_id == employee_id,
            SalaryStructure.effective_from <= payload.effective_from,
        )
        .order_by(SalaryStructure.effective_from.desc())
        .limit(1)
    )

    if previous is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "ADMIN must fix the initial salary before MD can create a revision. "
                "A revision date also cannot be earlier than the initial salary date."
            ),
        )

    previous_gross = previous.gross_monthly_salary
    new_gross = round(
        payload.basic_salary
        + payload.hra
        + payload.conveyance_allowance
        + payload.other_allowance,
        2,
    )
    increase = round(new_gross - previous_gross, 2)
    percentage = (
        round((increase / previous_gross) * 100, 2)
        if previous_gross > 0
        else 100
    )

    structure = SalaryStructure(
        organization_id=user.organization_id,
        employee_id=employee_id,
        effective_from=payload.effective_from,
        basic_salary=payload.basic_salary,
        hra=payload.hra,
        conveyance_allowance=payload.conveyance_allowance,
        other_allowance=payload.other_allowance,
        daily_allowance=payload.daily_allowance,
        fixed_deduction=payload.fixed_deduction,
        currency=payload.currency.strip().upper(),
        created_by_user_id=user.id,
    )
    database.add(structure)
    database.flush()

    database.add(
        SalaryRevision(
            organization_id=user.organization_id,
            employee_id=employee_id,
            previous_structure_id=previous.id if previous else None,
            new_structure_id=structure.id,
            revised_by_user_id=user.id,
            reason=payload.reason,
            previous_gross=previous_gross,
            new_gross=new_gross,
            increase_amount=increase,
            increase_percentage=percentage,
        )
    )
    database.commit()
    database.refresh(structure)
    return structure


def payroll_vendor_rows(
    database: Session,
    organization_id: UUID,
) -> list[Vendor]:
    """Active vendors assigned to at least one active shop/outlet."""
    return list(
        database.scalars(
            select(Vendor)
            .join(
                Outlet,
                or_(
                    Outlet.vendor_id == Vendor.id,
                    Outlet.assistant_vendor_id == Vendor.id,
                    Outlet.parcel_vendor_id == Vendor.id,
                ),
            )
            .where(
                Vendor.organization_id == organization_id,
                Vendor.status == "ACTIVE",
                Outlet.organization_id == organization_id,
                Outlet.is_active.is_(True),
            )
            .distinct()
            .order_by(Vendor.code)
        ).all()
    )


def list_payroll_vendors(database: Session, user: User) -> list[dict]:
    require_payroll_admin(database, user)
    vendors = list(
        database.scalars(
            select(Vendor)
            .where(
                Vendor.organization_id == user.organization_id,
                Vendor.status == "ACTIVE",
            )
            .order_by(Vendor.code, Vendor.name)
        ).all()
    )
    result = []
    for vendor in vendors:
        outlets = list(
            database.execute(
                select(
                    Outlet.id,
                    Outlet.code,
                    Outlet.name,
                    Outlet.vendor_id,
                    Outlet.assistant_vendor_id,
                    Outlet.parcel_vendor_id,
                ).where(
                    Outlet.organization_id == user.organization_id,
                    Outlet.is_active.is_(True),
                    or_(
                        Outlet.vendor_id == vendor.id,
                        Outlet.assistant_vendor_id == vendor.id,
                        Outlet.parcel_vendor_id == vendor.id,
                    ),
                ).order_by(Outlet.code)
            ).mappings().all()
        )
        outlet_rows = []
        for row in outlets:
            if row["vendor_id"] == vendor.id:
                role = "PRIMARY"
            elif row["assistant_vendor_id"] == vendor.id:
                role = "ASSISTANT"
            else:
                role = "PARCEL"
            outlet_rows.append(
                {
                    "id": row["id"],
                    "code": row["code"],
                    "name": row["name"],
                    "role": role,
                }
            )
        result.append(
            {
                "id": vendor.id,
                "code": vendor.code,
                "name": vendor.name,
                "outlets": outlet_rows,
            }
        )
    return result


def list_vendor_salary_structures(
    database: Session,
    user: User,
    vendor_id: UUID,
) -> list[VendorSalaryStructure]:
    require_payroll_admin(database, user)
    vendor = database.scalar(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.organization_id == user.organization_id,
        )
    )
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor was not found.")
    return list(
        database.scalars(
            select(VendorSalaryStructure)
            .where(
                VendorSalaryStructure.organization_id == user.organization_id,
                VendorSalaryStructure.vendor_id == vendor_id,
            )
            .order_by(VendorSalaryStructure.effective_from.desc())
        ).all()
    )


def save_vendor_salary_structure(
    database: Session,
    user: User,
    vendor_id: UUID,
    payload: VendorSalaryStructureRequest,
) -> VendorSalaryStructure:
    vendor = database.scalar(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.organization_id == user.organization_id,
        )
    )
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor was not found.")

    previous = database.scalar(
        select(VendorSalaryStructure)
        .where(
            VendorSalaryStructure.organization_id == user.organization_id,
            VendorSalaryStructure.vendor_id == vendor_id,
        )
        .order_by(VendorSalaryStructure.effective_from.desc())
        .limit(1)
    )
    if previous is None:
        require_salary_creator(database, user)
    else:
        require_md(database, user)
        if not payload.reason or len(payload.reason.strip()) < 3:
            raise HTTPException(status_code=422, detail="Vendor salary revision reason is required.")

    monthly_gross = round(
        payload.basic_salary
        + payload.hra
        + payload.conveyance_allowance
        + payload.other_allowance,
        2,
    )
    if monthly_gross <= 0:
        raise HTTPException(
            status_code=422,
            detail="Vendor monthly salary must contain a positive salary or allowance amount.",
        )

    structure = VendorSalaryStructure(
        organization_id=user.organization_id,
        vendor_id=vendor_id,
        effective_from=payload.effective_from,
        monthly_salary=monthly_gross,
        basic_salary=payload.basic_salary,
        hra=payload.hra,
        conveyance_allowance=payload.conveyance_allowance,
        other_allowance=payload.other_allowance,
        daily_allowance=payload.daily_allowance,
        fixed_deduction=payload.fixed_deduction,
        currency=payload.currency.strip().upper(),
        revision_reason=(payload.reason.strip() if payload.reason else "Initial vendor salary"),
        created_by_user_id=user.id,
    )
    database.add(structure)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=409,
            detail="A vendor salary structure already exists for that effective date.",
        ) from error
    database.refresh(structure)
    return structure


def list_vendor_closures(database: Session, user: User) -> list[VendorClosureDay]:
    require_payroll_admin(database, user)
    return list(
        database.scalars(
            select(VendorClosureDay)
            .where(
                VendorClosureDay.organization_id == user.organization_id,
                VendorClosureDay.is_active.is_(True),
            )
            .order_by(VendorClosureDay.closure_date.desc())
        ).all()
    )


def create_vendor_closure(
    database: Session,
    user: User,
    payload: VendorClosureCreateRequest,
) -> VendorClosureDay:
    require_payroll_preparer(database, user)
    closure = VendorClosureDay(
        organization_id=user.organization_id,
        closure_date=payload.closure_date,
        reason=payload.reason.strip(),
        created_by_user_id=user.id,
    )
    database.add(closure)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(status_code=409, detail="A vendor closure already exists for this date.") from error
    database.refresh(closure)
    return closure


def deactivate_vendor_closure(
    database: Session,
    user: User,
    closure_id: UUID,
) -> VendorClosureDay:
    require_payroll_preparer(database, user)
    closure = database.scalar(
        select(VendorClosureDay).where(
            VendorClosureDay.id == closure_id,
            VendorClosureDay.organization_id == user.organization_id,
        )
    )
    if closure is None:
        raise HTTPException(status_code=404, detail="Vendor closure was not found.")
    closure.is_active = False
    database.commit()
    database.refresh(closure)
    return closure


def create_salary_hold(
    database: Session,
    user: User,
    employee_id: UUID,
    payload: SalaryHoldCreateRequest,
) -> SalaryHold:
    require_md(database, user)
    find_employee(database, user.organization_id, employee_id)

    active = database.scalar(
        select(SalaryHold.id).where(
            SalaryHold.employee_id == employee_id,
            SalaryHold.is_active.is_(True),
        )
    )
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active salary hold already exists.",
        )

    hold = SalaryHold(
        organization_id=user.organization_id,
        employee_id=employee_id,
        hold_from=payload.hold_from,
        hold_to=payload.hold_to,
        reason=payload.reason,
        created_by_user_id=user.id,
    )
    database.add(hold)
    database.commit()
    database.refresh(hold)
    return hold


def release_salary_hold(
    database: Session,
    user: User,
    hold_id: UUID,
    payload: SalaryHoldReleaseRequest,
) -> SalaryHold:
    require_md(database, user)

    hold = database.scalar(
        select(SalaryHold).where(
            SalaryHold.id == hold_id,
            SalaryHold.organization_id == user.organization_id,
        )
    )
    if hold is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Salary hold was not found.",
        )
    if not hold.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Salary hold is already released.",
        )

    hold.is_active = False
    hold.released_by_user_id = user.id
    hold.released_at = datetime.now(timezone.utc)
    hold.release_note = payload.release_note
    database.commit()
    database.refresh(hold)
    return hold


def list_salary_holds(
    database: Session,
    user: User,
    active_only: bool,
) -> list[SalaryHold]:
    require_payroll_admin(database, user)

    statement = select(SalaryHold).where(
        SalaryHold.organization_id == user.organization_id
    )
    if active_only:
        statement = statement.where(SalaryHold.is_active.is_(True))

    return list(
        database.scalars(
            statement.order_by(SalaryHold.created_at.desc())
        ).all()
    )


def create_payroll_run(
    database: Session,
    user: User,
    payload: PayrollRunCreateRequest,
) -> PayrollRun:
    require_payroll_preparer(database, user)

    payroll_run = PayrollRun(
        organization_id=user.organization_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        created_by_user_id=user.id,
    )
    database.add(payroll_run)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A payroll run already exists for this period.",
        ) from error

    database.refresh(payroll_run)
    return payroll_run


def delete_payroll_run(
    database: Session,
    user: User,
    run_id: UUID,
) -> None:
    require_payroll_preparer(database, user)
    payroll_run = get_payroll_run(database, user.organization_id, run_id)

    if payroll_run.status in {"SUBMITTED_FOR_MD_APPROVAL", "FINALIZED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payroll submitted to MD or finalized payroll cannot be deleted.",
        )

    database.delete(payroll_run)
    database.commit()


def list_payroll_runs(
    database: Session,
    user: User,
) -> list[PayrollRun]:
    require_payroll_admin(database, user)

    return list(
        database.scalars(
            select(PayrollRun)
            .where(PayrollRun.organization_id == user.organization_id)
            .order_by(PayrollRun.period_start.desc())
        ).all()
    )


def get_working_dates(
    database: Session,
    organization_id: UUID,
    period_start: date,
    period_end: date,
) -> list[date]:
    holidays = set(
        database.scalars(
            select(Holiday.holiday_date).where(
                Holiday.organization_id == organization_id,
                Holiday.holiday_date >= period_start,
                Holiday.holiday_date <= period_end,
                Holiday.is_active.is_(True),
                Holiday.is_optional.is_(False),
            )
        ).all()
    )

    dates = []
    current = period_start
    while current <= period_end:
        # Internal employees work Monday through Saturday; Sunday is the
        # universal weekly holiday unless the date is handled separately.
        if current.weekday() < 6 and current not in holidays:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def get_vendor_working_dates(
    database: Session,
    organization_id: UUID,
    period_start: date,
    period_end: date,
) -> list[date]:
    closures = set(
        database.scalars(
            select(VendorClosureDay.closure_date).where(
                VendorClosureDay.organization_id == organization_id,
                VendorClosureDay.closure_date >= period_start,
                VendorClosureDay.closure_date <= period_end,
                VendorClosureDay.is_active.is_(True),
            )
        ).all()
    )
    dates = []
    current = period_start
    while current <= period_end:
        if current not in closures:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def get_payroll_working_calendar(
    database: Session,
    user: User,
    run_id: UUID,
) -> dict:
    """Explain exactly which calendar dates were counted for a payroll run."""
    require_payroll_admin(database, user)
    payroll_run = get_payroll_run(
        database,
        user.organization_id,
        run_id,
    )

    sample_item = database.scalar(
        select(PayrollItem)
        .where(
            PayrollItem.organization_id == user.organization_id,
            PayrollItem.payroll_run_id == run_id,
        )
        .order_by(PayrollItem.created_at.asc())
        .limit(1)
    )
    stored_dates = None
    if sample_item and isinstance(sample_item.calculation_details, dict):
        value = sample_item.calculation_details.get("working_dates")
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            stored_dates = set(value)

    vendor_sample = database.scalar(
        select(VendorPayrollItem)
        .where(
            VendorPayrollItem.organization_id == user.organization_id,
            VendorPayrollItem.payroll_run_id == run_id,
        )
        .order_by(VendorPayrollItem.created_at.asc())
        .limit(1)
    )
    vendor_stored_dates = None
    if vendor_sample and isinstance(vendor_sample.calculation_details, dict):
        value = vendor_sample.calculation_details.get("working_dates")
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            vendor_stored_dates = set(value)

    holiday_rows = database.execute(
        select(Holiday.holiday_date, Holiday.name).where(
            Holiday.organization_id == user.organization_id,
            Holiday.holiday_date >= payroll_run.period_start,
            Holiday.holiday_date <= payroll_run.period_end,
            Holiday.is_active.is_(True),
            Holiday.is_optional.is_(False),
        )
    ).all()
    holiday_names = {holiday_date: name for holiday_date, name in holiday_rows}
    closure_rows = database.execute(
        select(VendorClosureDay.closure_date, VendorClosureDay.reason).where(
            VendorClosureDay.organization_id == user.organization_id,
            VendorClosureDay.closure_date >= payroll_run.period_start,
            VendorClosureDay.closure_date <= payroll_run.period_end,
            VendorClosureDay.is_active.is_(True),
        )
    ).all()
    closure_reasons = {closure_date: reason for closure_date, reason in closure_rows}

    if stored_dates is None:
        stored_dates = {
            value.isoformat()
            for value in get_working_dates(
                database,
                user.organization_id,
                payroll_run.period_start,
                payroll_run.period_end,
            )
        }
    if vendor_stored_dates is None:
        vendor_stored_dates = {
            value.isoformat()
            for value in get_vendor_working_dates(
                database,
                user.organization_id,
                payroll_run.period_start,
                payroll_run.period_end,
            )
        }

    calendar_days = []
    current = payroll_run.period_start
    while current <= payroll_run.period_end:
        iso_date = current.isoformat()
        if iso_date in stored_dates:
            category = "WORKING_DAY"
            reason = "Counted as a working day"
        elif current.weekday() == 6:
            category = "WEEKEND"
            reason = "Sunday weekly holiday"
        elif current in holiday_names:
            category = "HOLIDAY"
            reason = holiday_names[current]
        else:
            category = "NON_WORKING_DAY"
            reason = "Excluded when payroll was calculated"

        calendar_days.append(
            {
                "date": iso_date,
                "weekday": current.strftime("%A"),
                "category": category,
                "included": iso_date in stored_dates,
                "reason": reason,
            }
        )
        current += timedelta(days=1)

    vendor_calendar_days = []
    current = payroll_run.period_start
    while current <= payroll_run.period_end:
        iso_date = current.isoformat()
        included = iso_date in vendor_stored_dates
        vendor_calendar_days.append(
            {
                "date": iso_date,
                "weekday": current.strftime("%A"),
                "category": "WORKING_DAY" if included else "GOVERNMENT_CLOSURE",
                "included": included,
                "reason": (
                    "Shop working day (including Sunday)"
                    if included
                    else closure_reasons.get(current, "Government/shop closure recorded at calculation")
                ),
            }
        )
        current += timedelta(days=1)

    return {
        "payroll_run_id": payroll_run.id,
        "period_start": payroll_run.period_start,
        "period_end": payroll_run.period_end,
        "working_days": len(stored_dates),
        "calendar_days": calendar_days,
        "vendor_working_days": len(vendor_stored_dates),
        "vendor_calendar_days": vendor_calendar_days,
    }


def effective_vendor_structure(
    database: Session,
    organization_id: UUID,
    vendor_id: UUID,
    period_end: date,
) -> VendorSalaryStructure | None:
    return database.scalar(
        select(VendorSalaryStructure)
        .where(
            VendorSalaryStructure.organization_id == organization_id,
            VendorSalaryStructure.vendor_id == vendor_id,
            VendorSalaryStructure.effective_from <= period_end,
            VendorSalaryStructure.is_active.is_(True),
        )
        .order_by(VendorSalaryStructure.effective_from.desc())
        .limit(1)
    )


def effective_vendor_structure_segments(
    database: Session,
    organization_id: UUID,
    vendor_id: UUID,
    period_start: date,
    period_end: date,
    working_dates: list[date],
) -> list[tuple[VendorSalaryStructure, list[date]]]:
    """Return the salary structure that applies to each vendor working-date segment."""
    if not working_dates:
        return []

    structures = list(
        database.scalars(
            select(VendorSalaryStructure)
            .where(
                VendorSalaryStructure.organization_id == organization_id,
                VendorSalaryStructure.vendor_id == vendor_id,
                VendorSalaryStructure.effective_from <= period_end,
                VendorSalaryStructure.is_active.is_(True),
            )
            .order_by(VendorSalaryStructure.effective_from.asc())
        ).all()
    )
    if not structures:
        return []

    segments: list[tuple[VendorSalaryStructure, list[date]]] = []
    for index, structure in enumerate(structures):
        next_start = (
            structures[index + 1].effective_from
            if index + 1 < len(structures)
            else None
        )
        segment_start = max(period_start, structure.effective_from)
        segment_end = (
            min(period_end, next_start - timedelta(days=1))
            if next_start is not None
            else period_end
        )
        if segment_end < segment_start:
            continue
        segment_dates = [
            value
            for value in working_dates
            if segment_start <= value <= segment_end
        ]
        if segment_dates:
            segments.append((structure, segment_dates))

    return segments


def vendor_payable_dates(
    database: Session,
    organization_id: UUID,
    vendor_id: UUID,
    period_start: date,
    period_end: date,
    working_dates: list[date],
) -> set[date]:
    valid_dates = set(working_dates)
    attended = set(
        database.scalars(
            text(
                """
                SELECT DISTINCT attendance_date
                FROM vendor_attendance_records
                WHERE organization_id = :organization_id
                  AND vendor_id = :vendor_id
                  AND attendance_date BETWEEN :period_start AND :period_end
                  AND status IN ('PRESENT', 'CHECKED_OUT')
                """
            ).bindparams(
                organization_id=organization_id,
                vendor_id=vendor_id,
                period_start=period_start,
                period_end=period_end,
            )
        ).all()
    )
    return attended.intersection(valid_dates)


def vendor_late_minutes_for_period(
    database: Session,
    organization_id: UUID,
    vendor_id: UUID,
    period_start: date,
    period_end: date,
) -> int:
    return int(
        database.scalar(
            text(
                """
                SELECT COALESCE(SUM(late_minutes), 0)
                FROM vendor_attendance_records
                WHERE organization_id = :organization_id
                  AND vendor_id = :vendor_id
                  AND attendance_date BETWEEN :period_start AND :period_end
                """
            ).bindparams(
                organization_id=organization_id,
                vendor_id=vendor_id,
                period_start=period_start,
                period_end=period_end,
            )
        )
        or 0
    )


def effective_structure(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
    period_end: date,
) -> SalaryStructure | None:
    return database.scalar(
        select(SalaryStructure)
        .where(
            SalaryStructure.organization_id == organization_id,
            SalaryStructure.employee_id == employee_id,
            SalaryStructure.effective_from <= period_end,
            SalaryStructure.is_active.is_(True),
        )
        .order_by(SalaryStructure.effective_from.desc())
        .limit(1)
    )


def payable_days(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
    period_start: date,
    period_end: date,
    working_dates: list[date],
) -> float:
    valid_dates = set(working_dates)

    paid_dates = set(
        database.scalars(
            select(AttendanceRecord.attendance_date).where(
                AttendanceRecord.organization_id == organization_id,
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.attendance_date >= period_start,
                AttendanceRecord.attendance_date <= period_end,
                AttendanceRecord.status.in_(
                    ["PRESENT", "LATE", "REGULARIZED"]
                ),
            )
        ).all()
    )

    leave_rows = database.execute(
        select(LeaveRequest.start_date, LeaveRequest.end_date)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .where(
            LeaveRequest.organization_id == organization_id,
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == "APPROVED",
            LeaveType.is_paid.is_(True),
            LeaveRequest.start_date <= period_end,
            LeaveRequest.end_date >= period_start,
        )
    ).all()

    for leave_start, leave_end in leave_rows:
        current = max(leave_start, period_start)
        finish = min(leave_end, period_end)
        while current <= finish:
            if current in valid_dates:
                paid_dates.add(current)
            current += timedelta(days=1)

    return float(len(paid_dates.intersection(valid_dates)))


def find_active_hold(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
    period_start: date,
    period_end: date,
) -> SalaryHold | None:
    return database.scalar(
        select(SalaryHold)
        .where(
            SalaryHold.organization_id == organization_id,
            SalaryHold.employee_id == employee_id,
            SalaryHold.is_active.is_(True),
            SalaryHold.hold_from <= period_end,
            (
                SalaryHold.hold_to.is_(None)
                | (SalaryHold.hold_to >= period_start)
            ),
        )
        .limit(1)
    )


def get_payroll_run(
    database: Session,
    organization_id: UUID,
    run_id: UUID,
) -> PayrollRun:
    payroll_run = database.scalar(
        select(PayrollRun).where(
            PayrollRun.id == run_id,
            PayrollRun.organization_id == organization_id,
        )
    )
    if payroll_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll run was not found.",
        )
    return payroll_run


def organization_today(user: User) -> date:
    timezone_name = (
        user.organization.timezone
        if user.organization and user.organization.timezone
        else "Asia/Kolkata"
    )
    return datetime.now(ZoneInfo(timezone_name)).date()


def payroll_employee_rows(
    database: Session,
    organization_id: UUID,
) -> list[tuple[Employee, User]]:
    return list(
        database.execute(
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .where(Employee.organization_id == organization_id, catalogue_visible("employees", "employee"))
            .order_by(User.employee_code)
        ).all()
    )


def missing_salary_structure_labels(
    database: Session,
    organization_id: UUID,
    period_end: date,
) -> list[str]:
    missing: list[str] = []

    for employee, account in payroll_employee_rows(
        database,
        organization_id,
    ):
        structure = effective_structure(
            database,
            organization_id,
            employee.id,
            period_end,
        )
        if structure is None:
            label = account.employee_code
            if employee.full_name:
                label = f"{label} - {employee.full_name}"
            missing.append(label)

    return missing


def missing_vendor_salary_labels(
    database: Session,
    organization_id: UUID,
    period_end: date,
) -> list[str]:
    missing = []
    for vendor in payroll_vendor_rows(database, organization_id):
        if effective_vendor_structure(database, organization_id, vendor.id, period_end) is None:
            any_structure = database.scalar(
                select(VendorSalaryStructure)
                .where(
                    VendorSalaryStructure.organization_id == organization_id,
                    VendorSalaryStructure.vendor_id == vendor.id,
                    VendorSalaryStructure.is_active.is_(True),
                )
                .order_by(VendorSalaryStructure.effective_from.asc())
                .limit(1)
            )
            if any_structure is None:
                missing.append(f"{vendor.code} - {vendor.name}")
    return missing


def payroll_eligible_vendor_count(
    database: Session,
    organization_id: UUID,
    period_end: date,
    period_start: date,
) -> int:
    dates = get_vendor_working_dates(database, organization_id, period_start, period_end)
    return sum(any(has_remuneration(s) for s, _ in effective_vendor_structure_segments(
        database, organization_id, v.id, period_start, period_end, dates))
        for v in payroll_vendor_rows(database, organization_id))


def validate_payroll_ready_for_calculation(
    database: Session,
    user: User,
    payroll_run: PayrollRun,
) -> None:
    local_today = organization_today(user)

    if payroll_run.period_end > local_today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Payroll cannot be calculated before the payroll "
                f"period ends on {payroll_run.period_end}."
            ),
        )

    missing = missing_salary_structure_labels(
        database,
        user.organization_id,
        payroll_run.period_end,
    )

    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Payroll cannot be calculated because salary structures "
                "are missing for: "
                + ", ".join(missing)
                + "."
            ),
        )

    missing_vendors = missing_vendor_salary_labels(
        database,
        user.organization_id,
        payroll_run.period_end,
    )
    if missing_vendors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Payroll cannot be calculated because vendor salaries are missing for: "
                + ", ".join(missing_vendors)
                + ". Fix the initial vendor salary in Payroll → Vendor Salary Setup."
            ),
        )


def validate_payroll_ready_for_submission(
    database: Session,
    user: User,
    payroll_run: PayrollRun,
) -> None:
    local_today = organization_today(user)

    if payroll_run.period_end > local_today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Payroll cannot be submitted to MD before the payroll "
                f"period ends on {payroll_run.period_end}."
            ),
        )

    missing = missing_salary_structure_labels(
        database,
        user.organization_id,
        payroll_run.period_end,
    )

    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Payroll cannot be submitted because salary structures "
                "are missing for: "
                + ", ".join(missing)
                + ". Recalculate after creating the missing structures."
            ),
        )

    missing_vendors = missing_vendor_salary_labels(
        database,
        user.organization_id,
        payroll_run.period_end,
    )
    if missing_vendors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Payroll cannot be submitted because vendor salaries are missing for: "
                + ", ".join(missing_vendors)
                + ". Recalculate after fixing them."
            ),
        )

    employee_count = sum(
        has_remuneration(effective_structure(database, user.organization_id, e.id, payroll_run.period_end))
        for e, _ in payroll_employee_rows(database, user.organization_id)
    )

    if payroll_run.total_employees != employee_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Payroll employee count is incomplete. "
                f"Calculated: {payroll_run.total_employees}; "
                f"organization employees: {employee_count}. "
                "Recalculate payroll before submitting it to MD."
            ),
        )

    vendor_count = payroll_eligible_vendor_count(
        database, user.organization_id, payroll_run.period_end, payroll_run.period_start,
    )
    if payroll_run.total_vendors != vendor_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Vendor payroll count is incomplete. "
                f"Calculated: {payroll_run.total_vendors}; salary-eligible shop vendors: {vendor_count}. "
                "Recalculate payroll before submitting it to MD."
            ),
        )


def calculate_payroll_run(
    database: Session,
    user: User,
    run_id: UUID,
) -> PayrollRun:
    require_payroll_preparer(database, user)
    payroll_run = get_payroll_run(
        database,
        user.organization_id,
        run_id,
    )

    validate_payroll_ready_for_calculation(
        database,
        user,
        payroll_run,
    )

    if payroll_run.status == "FINALIZED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Finalized payroll cannot be recalculated.",
        )
    if payroll_run.status == "SUBMITTED_FOR_MD_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payroll is waiting for MD approval and cannot be recalculated.",
        )

    database.execute(
        delete(PayrollItem).where(
            PayrollItem.payroll_run_id == payroll_run.id
        )
    )
    database.execute(
        delete(VendorPayrollItem).where(
            VendorPayrollItem.payroll_run_id == payroll_run.id
        )
    )

    dates = get_working_dates(
        database,
        user.organization_id,
        payroll_run.period_start,
        payroll_run.period_end,
    )
    working_days = float(len(dates))

    if working_days == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payroll period has no working days.",
        )

    employees = list(
        database.scalars(
            select(Employee).where(
                Employee.organization_id == user.organization_id,
                catalogue_visible("employees", "employee"),
            )
        ).all()
    )

    total_gross = total_deductions = total_net = 0.0
    item_count = 0

    for employee in employees:
        structure = effective_structure(
            database,
            user.organization_id,
            employee.id,
            payroll_run.period_end,
        )
        if not has_remuneration(structure):
            continue

        paid_days = payable_days(
            database,
            user.organization_id,
            employee.id,
            payroll_run.period_start,
            payroll_run.period_end,
            dates,
        )
        absent_days = max(0.0, working_days - paid_days)
        ratio = paid_days / working_days

        basic = round(structure.basic_salary * ratio, 2)
        hra = round(structure.hra * ratio, 2)
        conveyance = round(
            structure.conveyance_allowance * ratio,
            2,
        )
        other = round(structure.other_allowance * ratio, 2)
        daily_allowance = round(structure.daily_allowance * paid_days, 2)
        overtime_benefit, overtime_claim_ids = approved_overtime_for_period(
            database,
            organization_id=user.organization_id,
            employee_id=employee.id,
            period_start=payroll_run.period_start,
            period_end=payroll_run.period_end,
        )
        gross = round(
            basic
            + hra
            + conveyance
            + other
            + daily_allowance
            + overtime_benefit,
            2,
        )
        monthly_gross = structure.gross_monthly_salary
        lop = round(
            monthly_gross * (absent_days / working_days),
            2,
        )
        fixed = round(structure.fixed_deduction, 2)
        late_policy = late_payroll_policy(
            database,
            organization_id=user.organization_id,
            employee_id=employee.id,
            period_start=payroll_run.period_start,
            period_end=payroll_run.period_end,
        )
        half_day_basic_rate = round(
            (structure.basic_salary / working_days) * 0.5,
            2,
        )
        late_deduction = round(
            half_day_basic_rate * late_policy["half_day_penalty_count"],
            2,
        )
        calculated_net = max(
            0.0,
            round(gross - fixed - late_deduction, 2),
        )

        hold = find_active_hold(
            database,
            user.organization_id,
            employee.id,
            payroll_run.period_start,
            payroll_run.period_end,
        )
        automatic_late_hold = late_policy["salary_hold_required"]
        is_held = hold is not None or automatic_late_hold
        hold_reasons = []
        if hold is not None:
            hold_reasons.append(hold.reason)
        if automatic_late_hold:
            months = ", ".join(late_policy["hold_months"])
            hold_reasons.append(
                "Automatic hold: more than three qualifying late check-ins "
                f"in {months}. ADMIN and MD review required."
            )

        advance_deduction = 0.0
        advance_allocations: list[dict] = []
        if not is_held:
            advance_deduction, advance_allocations = (
                calculate_salary_advance_deductions(
                    database,
                    organization_id=user.organization_id,
                    employee_id=employee.id,
                    payroll_period_end=payroll_run.period_end,
                    available_net=calculated_net,
                )
            )
        net = (
            0.0
            if is_held
            else max(0, round(calculated_net - advance_deduction, 2))
        )

        item = PayrollItem(
            organization_id=user.organization_id,
            payroll_run_id=payroll_run.id,
            employee_id=employee.id,
            salary_structure_id=structure.id,
            working_days=working_days,
            payable_days=paid_days,
            absent_days=absent_days,
            basic_earned=basic,
            hra_earned=hra,
            conveyance_earned=conveyance,
            other_allowance_earned=other,
            daily_allowance_earned=daily_allowance,
            overtime_benefit=overtime_benefit,
            gross_earned=gross,
            loss_of_pay_deduction=lop,
            fixed_deduction=fixed,
            other_deductions=late_deduction,
            salary_advance_deduction=advance_deduction,
            net_salary=net,
            is_held=is_held,
            hold_reason=" | ".join(hold_reasons) or None,
            calculation_details={
                "monthly_gross": monthly_gross,
                "daily_rate": round(monthly_gross / working_days, 2),
                "working_dates": [value.isoformat() for value in dates],
                "net_before_hold": calculated_net,
                "net_before_salary_advance": calculated_net,
                "salary_advance_allocations": advance_allocations,
                "daily_allowance_rate": structure.daily_allowance,
                "daily_allowance_days": paid_days,
                "overtime_benefit": overtime_benefit,
                "overtime_claim_ids": overtime_claim_ids,
                "late_attendance": late_policy,
                "late_half_day_basic_deduction": late_deduction,
            },
            payslip_number=(
                f"{payroll_run.period_start:%Y%m}-"
                f"{str(payroll_run.id)[:6].upper()}-"
                f"{str(employee.id)[:8].upper()}"
            ),
        )
        database.add(item)

        item_count += 1
        total_gross += gross
        total_deductions += fixed + late_deduction + advance_deduction
        total_net += net

    vendor_dates = get_vendor_working_dates(
        database,
        user.organization_id,
        payroll_run.period_start,
        payroll_run.period_end,
    )
    vendor_working_days = float(len(vendor_dates))
    if vendor_working_days == 0 and payroll_vendor_rows(database, user.organization_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Vendor payroll period has no working days after government closures.",
        )

    vendor_count = 0
    vendor_total_gross = vendor_total_deductions = vendor_total_net = 0.0
    for vendor in payroll_vendor_rows(database, user.organization_id):
        segments = effective_vendor_structure_segments(
            database,
            user.organization_id,
            vendor.id,
            payroll_run.period_start,
            payroll_run.period_end,
            vendor_dates,
        )
        if not any(has_remuneration(structure) for structure, _ in segments):
            continue

        latest_structure = segments[-1][0]
        paid_date_values: set[date] = set()
        eligible_working_dates: set[date] = set()
        segment_details: list[dict] = []
        basic_earned = 0.0
        hra_earned = 0.0
        conveyance_earned = 0.0
        other_allowance_earned = 0.0
        daily_allowance_earned = 0.0

        for structure, segment_dates in segments:
            segment_paid_dates = vendor_payable_dates(
                database,
                user.organization_id,
                vendor.id,
                payroll_run.period_start,
                payroll_run.period_end,
                segment_dates,
            )
            segment_paid_days = float(len(segment_paid_dates))
            segment_working_days = float(len(segment_dates))
            period_ratio = segment_paid_days / vendor_working_days
            segment_basic = round(structure.basic_salary * period_ratio, 2)
            segment_hra = round(structure.hra * period_ratio, 2)
            segment_conveyance = round(
                structure.conveyance_allowance * period_ratio,
                2,
            )
            segment_other = round(structure.other_allowance * period_ratio, 2)
            segment_daily_allowance = round(
                structure.daily_allowance * segment_paid_days,
                2,
            )

            basic_earned += segment_basic
            hra_earned += segment_hra
            conveyance_earned += segment_conveyance
            other_allowance_earned += segment_other
            daily_allowance_earned += segment_daily_allowance
            paid_date_values.update(segment_paid_dates)
            eligible_working_dates.update(segment_dates)
            segment_details.append(
                {
                    "salary_structure_id": str(structure.id),
                    "effective_from": structure.effective_from.isoformat(),
                    "segment_start": segment_dates[0].isoformat(),
                    "segment_end": segment_dates[-1].isoformat(),
                    "working_days": segment_working_days,
                    "payable_days": segment_paid_days,
                    "basic_earned": segment_basic,
                    "hra_earned": segment_hra,
                    "conveyance_earned": segment_conveyance,
                    "other_allowance_earned": segment_other,
                    "daily_allowance_earned": segment_daily_allowance,
                }
            )

        basic_earned = round(basic_earned, 2)
        hra_earned = round(hra_earned, 2)
        conveyance_earned = round(conveyance_earned, 2)
        other_allowance_earned = round(other_allowance_earned, 2)
        daily_allowance_earned = round(daily_allowance_earned, 2)
        paid_days = float(len(paid_date_values))
        eligible_working_days = float(len(eligible_working_dates))
        absent_days = max(0.0, eligible_working_days - paid_days)
        gross = round(
            basic_earned
            + hra_earned
            + conveyance_earned
            + other_allowance_earned
            + daily_allowance_earned,
            2,
        )
        fixed = round(latest_structure.fixed_deduction, 2)
        vendor_late_minutes = vendor_late_minutes_for_period(
            database,
            user.organization_id,
            vendor.id,
            payroll_run.period_start,
            payroll_run.period_end,
        )
        late_deduction = 0.0
        calculated_net = max(0.0, round(gross - fixed - late_deduction, 2))
        advance_deduction, advance_allocations = (
            calculate_vendor_salary_advance_deductions(
                database,
                organization_id=user.organization_id,
                vendor_id=vendor.id,
                payroll_period_end=payroll_run.period_end,
                available_net=calculated_net,
            )
        )
        net = max(0.0, round(calculated_net - advance_deduction, 2))
        outlet_names = list(
            database.scalars(
                select(Outlet.name).where(
                    Outlet.organization_id == user.organization_id,
                    Outlet.vendor_id == vendor.id,
                    Outlet.is_active.is_(True),
                ).order_by(Outlet.name)
            ).all()
        )

        database.add(
            VendorPayrollItem(
                organization_id=user.organization_id,
                payroll_run_id=payroll_run.id,
                vendor_id=vendor.id,
                vendor_salary_structure_id=latest_structure.id,
                working_days=eligible_working_days,
                payable_days=paid_days,
                absent_days=absent_days,
                basic_earned=basic_earned,
                hra_earned=hra_earned,
                conveyance_earned=conveyance_earned,
                other_allowance_earned=other_allowance_earned,
                daily_allowance_earned=daily_allowance_earned,
                gross_earned=gross,
                fixed_deduction=fixed,
                other_deductions=late_deduction,
                salary_advance_deduction=advance_deduction,
                net_salary=net,
                calculation_details={
                    "monthly_salary": latest_structure.gross_monthly_salary,
                    "monthly_basic": latest_structure.basic_salary,
                    "monthly_hra": latest_structure.hra,
                    "monthly_conveyance": latest_structure.conveyance_allowance,
                    "monthly_other_allowance": latest_structure.other_allowance,
                    "daily_allowance_rate": latest_structure.daily_allowance,
                    "monthly_daily_rate": round(
                        latest_structure.gross_monthly_salary / vendor_working_days,
                        2,
                    ),
                    "salary_effective_from": latest_structure.effective_from.isoformat(),
                    "salary_segments": segment_details,
                    "period_working_dates": [value.isoformat() for value in vendor_dates],
                    "working_dates": sorted(value.isoformat() for value in eligible_working_dates),
                    "payable_dates": sorted(value.isoformat() for value in paid_date_values),
                    "outlet_names": outlet_names,
                    "vendor_late_minutes": vendor_late_minutes,
                    "vendor_late_deduction": late_deduction,
                    "net_before_salary_advance": calculated_net,
                    "vendor_salary_advance_allocations": advance_allocations,
                    "calendar_rule": (
                        "Every day including Sunday, excluding recorded government "
                        "closures; salary counted only from the vendor structure "
                        "effective date."
                    ),
                },
                payslip_number=(
                    f"VND-{payroll_run.period_start:%Y%m}-"
                    f"{str(payroll_run.id)[:6].upper()}-"
                    f"{str(vendor.id)[:8].upper()}"
                ),
            )
        )
        vendor_count += 1
        vendor_total_gross += gross
        vendor_total_deductions += fixed + late_deduction + advance_deduction
        vendor_total_net += net

    payroll_run.status = "CALCULATED"
    payroll_run.total_employees = item_count
    payroll_run.total_vendors = vendor_count
    payroll_run.vendor_total_gross = round(vendor_total_gross, 2)
    payroll_run.vendor_total_deductions = round(vendor_total_deductions, 2)
    payroll_run.vendor_total_net = round(vendor_total_net, 2)
    payroll_run.total_gross = round(total_gross + vendor_total_gross, 2)
    payroll_run.total_deductions = round(total_deductions + vendor_total_deductions, 2)
    payroll_run.total_net = round(total_net + vendor_total_net, 2)

    database.commit()
    database.refresh(payroll_run)
    return payroll_run


def submit_payroll_run(
    database: Session,
    user: User,
    run_id: UUID,
    payload: PayrollRunSubmitRequest,
) -> PayrollRun:
    require_payroll_preparer(database, user)
    payroll_run = get_payroll_run(database, user.organization_id, run_id)

    validate_payroll_ready_for_submission(
        database,
        user,
        payroll_run,
    )

    if payroll_run.status != "CALCULATED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Calculate payroll before submitting it to MD.",
        )
    if payroll_run.total_employees <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payroll has no calculated employees to submit.",
        )
    payroll_run.status = "SUBMITTED_FOR_MD_APPROVAL"
    payroll_run.submitted_by_user_id = user.id
    payroll_run.submitted_at = datetime.now(timezone.utc)
    payroll_run.submission_note = payload.note
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={"MD"},
        title="Payroll awaiting MD approval",
        body=(
            f"Payroll for {payroll_run.period_start} to {payroll_run.period_end} "
            f"was submitted by {user.employee_code}. Net payable: "
            f"₹{payroll_run.total_net:,.2f}."
        ),
        dedupe_prefix=(
            f"payroll:{payroll_run.id}:submitted:"
            f"{payroll_run.submitted_at.isoformat()}"
        ),
        route=f"/module/payroll?queue=1&run={payroll_run.id}",
        module="payroll",
        event="PAYROLL_SUBMITTED_FOR_MD_APPROVAL",
        entity_id=payroll_run.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(payroll_run)
    return payroll_run


def _approve_and_finalize_payroll(
    database: Session,
    user: User,
    run_id: UUID,
    note: str | None,
) -> PayrollRun:
    require_md(database, user)
    payroll_run = get_payroll_run(database, user.organization_id, run_id)
    if payroll_run.status != "SUBMITTED_FOR_MD_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only payroll submitted for MD approval can be approved.",
        )
    now = datetime.now(timezone.utc)
    payroll_run.status = "FINALIZED"
    payroll_run.approved_by_user_id = user.id
    payroll_run.approved_at = now
    payroll_run.approval_note = note
    payroll_run.finalized_by_user_id = user.id
    payroll_run.finalized_at = now
    from app.services.payroll_advance_summary import snapshot_run
    try:
        snapshot_run(database, payroll_run)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finalize_salary_advance_recoveries(
        database,
        user=user,
        payroll_run=payroll_run,
    )
    finalize_vendor_salary_advance_recoveries(
        database,
        user=user,
        payroll_run=payroll_run,
    )
    finalize_overtime_benefits(
        database,
        payroll_run=payroll_run,
    )
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=payroll_run.submitted_by_user_id,
        title="Payroll approved and finalized",
        body=(
            f"Payroll for {payroll_run.period_start} to {payroll_run.period_end} "
            f"was approved and finalized by {user.employee_code}."
        ),
        dedupe_key=f"payroll:{payroll_run.id}:approved:{now.isoformat()}",
        route=f"/module/payroll?run={payroll_run.id}",
        module="payroll",
        event="PAYROLL_APPROVED",
        entity_id=payroll_run.id,
    )
    database.commit()
    database.refresh(payroll_run)
    return payroll_run


def approve_payroll_run(
    database: Session,
    user: User,
    run_id: UUID,
    payload: PayrollRunApprovalRequest,
) -> PayrollRun:
    return _approve_and_finalize_payroll(database, user, run_id, payload.note)


def finalize_payroll_run(
    database: Session,
    user: User,
    run_id: UUID,
) -> PayrollRun:
    return _approve_and_finalize_payroll(
        database, user, run_id, "Approved and finalized by MD."
    )


def return_payroll_run(
    database: Session,
    user: User,
    run_id: UUID,
    payload: PayrollRunReturnRequest,
) -> PayrollRun:
    require_md(database, user)
    payroll_run = get_payroll_run(database, user.organization_id, run_id)
    if payroll_run.status != "SUBMITTED_FOR_MD_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only payroll waiting for MD approval can be returned.",
        )
    payroll_run.status = "RETURNED"
    payroll_run.returned_by_user_id = user.id
    payroll_run.returned_at = datetime.now(timezone.utc)
    payroll_run.return_note = payload.reason.strip()
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=payroll_run.submitted_by_user_id,
        title="Payroll returned for correction",
        body=(
            f"Payroll for {payroll_run.period_start} to {payroll_run.period_end} "
            f"was returned by {user.employee_code}: {payroll_run.return_note}"
        ),
        dedupe_key=(
            f"payroll:{payroll_run.id}:returned:"
            f"{payroll_run.returned_at.isoformat()}"
        ),
        route=f"/module/payroll?queue=1&run={payroll_run.id}",
        module="payroll",
        event="PAYROLL_RETURNED",
        entity_id=payroll_run.id,
    )
    database.commit()
    database.refresh(payroll_run)
    return payroll_run


def list_payroll_items(
    database: Session,
    user: User,
    run_id: UUID,
) -> list[dict]:
    require_payroll_admin(database, user)

    rows = database.execute(
        select(PayrollItem, Employee, User)
        .join(Employee, PayrollItem.employee_id == Employee.id)
        .join(User, Employee.user_id == User.id)
        .where(
            PayrollItem.organization_id == user.organization_id,
            PayrollItem.payroll_run_id == run_id,
        )
        .order_by(User.employee_code)
    ).all()

    return [
        {
            **{
                column.name: getattr(item, column.name)
                for column in PayrollItem.__table__.columns
                if column.name not in {"organization_id"}
            },
            "employee_code": employee_user.employee_code,
            "employee_name": employee.full_name,
            "bank_name": employee.bank_name,
            "bank_ifsc": employee.bank_ifsc,
            "bank_account_number": employee.bank_account_number,
        }
        for item, employee, employee_user in rows
    ]


def list_vendor_payroll_items(
    database: Session,
    user: User,
    run_id: UUID,
) -> list[dict]:
    require_payroll_admin(database, user)
    get_payroll_run(database, user.organization_id, run_id)
    rows = database.execute(
        select(VendorPayrollItem, Vendor, VendorSalaryStructure)
        .join(Vendor, VendorPayrollItem.vendor_id == Vendor.id)
        .join(
            VendorSalaryStructure,
            VendorPayrollItem.vendor_salary_structure_id == VendorSalaryStructure.id,
        )
        .where(
            VendorPayrollItem.organization_id == user.organization_id,
            VendorPayrollItem.payroll_run_id == run_id,
        )
        .order_by(Vendor.code)
    ).all()
    result = []
    for item, vendor, structure in rows:
        details = item.calculation_details if isinstance(item.calculation_details, dict) else {}
        result.append(
            {
                **{
                    column.name: getattr(item, column.name)
                    for column in VendorPayrollItem.__table__.columns
                    if column.name != "organization_id"
                },
                "vendor_code": vendor.code,
                "vendor_name": vendor.name,
                "outlet_names": details.get("outlet_names", []),
                "currency": structure.currency,
            }
        )
    return result


def get_finalized_payroll_export(
    database: Session,
    user: User,
    run_id: UUID,
) -> tuple[PayrollRun, list[dict]]:
    """Return an immutable approved payroll run and its organization-scoped rows."""
    require_payroll_admin(database, user)
    payroll_run = get_payroll_run(
        database,
        user.organization_id,
        run_id,
    )
    if payroll_run.status != "FINALIZED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only MD-approved and finalized payroll can be downloaded.",
        )

    rows = database.execute(
        select(PayrollItem, Employee, User, SalaryStructure)
        .join(Employee, PayrollItem.employee_id == Employee.id)
        .join(User, Employee.user_id == User.id)
        .join(
            SalaryStructure,
            PayrollItem.salary_structure_id == SalaryStructure.id,
        )
        .where(
            PayrollItem.organization_id == user.organization_id,
            PayrollItem.payroll_run_id == payroll_run.id,
        )
        .order_by(User.employee_code)
    ).all()

    return payroll_run, [
        {
            **{
                column.name: getattr(item, column.name)
                for column in PayrollItem.__table__.columns
                if column.name != "organization_id"
            },
            "employee_code": employee_user.employee_code,
            "employee_name": employee.full_name,
            "bank_name": employee.bank_name,
            "bank_ifsc": employee.bank_ifsc,
            "bank_account_number": employee.bank_account_number,
            "currency": structure.currency,
        }
        for item, employee, employee_user, structure in rows
    ]


def list_my_payslips(
    database: Session,
    user: User,
) -> list[dict]:
    employee = get_employee_for_user(database, user)

    rows = database.execute(
        select(PayrollItem, PayrollRun, SalaryStructure)
        .join(PayrollRun, PayrollItem.payroll_run_id == PayrollRun.id)
        .join(
            SalaryStructure,
            PayrollItem.salary_structure_id == SalaryStructure.id,
        )
        .where(
            PayrollItem.employee_id == employee.id,
            PayrollRun.status == "FINALIZED",
        )
        .order_by(PayrollRun.period_start.desc())
    ).all()

    return [
        {
            **{
                column.name: getattr(item, column.name)
                for column in PayrollItem.__table__.columns
                if column.name not in {"organization_id"}
            },
            "period_start": payroll_run.period_start,
            "period_end": payroll_run.period_end,
            "employee_code": user.employee_code,
            "employee_name": employee.full_name,
            "currency": structure.currency,
        }
        for item, payroll_run, structure in rows
    ]


def get_printable_payslip(
    database: Session,
    user: User,
    item_id: UUID,
):
    item = database.scalar(
        select(PayrollItem).where(
            PayrollItem.id == item_id,
            PayrollItem.organization_id == user.organization_id,
        )
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payslip was not found.",
        )

    employee = database.get(Employee, item.employee_id)
    own_employee = database.scalar(
        select(Employee).where(
            Employee.user_id == user.id,
            Employee.organization_id == user.organization_id,
        )
    )

    if own_employee is None or own_employee.id != item.employee_id:
        require_payroll_admin(database, user)

    payroll_run = database.get(PayrollRun, item.payroll_run_id)
    structure = database.get(SalaryStructure, item.salary_structure_id)
    return item, payroll_run, structure, employee

# payroll-advance-summary-v1

# payroll-reference-layout-v1
