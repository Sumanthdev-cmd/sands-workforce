from app.services.catalogue_service import catalogue_visible, ensure_not_archived
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select, update, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_password
from app.models import (
    Department,
    Designation,
    Employee,
    RefreshToken,
    Role,
    User,
)
from app.schemas.employees import (
    EmployeeCreate,
    EmployeeUpdate,
)


def employee_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Employee was not found.",
    )


def bad_request(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


def conflict(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


def _employee_query(organization_id: UUID):
    return (
        select(Employee)
        .join(User, Employee.user_id == User.id)
        .options(
            selectinload(Employee.user).selectinload(User.roles),
            selectinload(Employee.department),
            selectinload(Employee.designation),
        )
        .where(Employee.organization_id == organization_id)
    )


def load_employee(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
) -> Employee:
    employee = database.scalar(
        _employee_query(organization_id).where(
            Employee.id == employee_id
        )
    )

    if employee is None:
        raise employee_not_found()

    return employee


def _load_department(
    database: Session,
    organization_id: UUID,
    department_id: UUID | None,
) -> Department | None:
    if department_id is None:
        return None

    department = database.scalar(
        select(Department).where(
            Department.id == department_id,
            Department.organization_id == organization_id,
            Department.is_active.is_(True),
        )
    )

    if department is None:
        raise bad_request(
            "The selected department is unavailable."
        )

    return department


def _load_designation(
    database: Session,
    organization_id: UUID,
    designation_id: UUID | None,
) -> Designation | None:
    if designation_id is None:
        return None

    designation = database.scalar(
        select(Designation).where(
            Designation.id == designation_id,
            Designation.organization_id == organization_id,
            Designation.is_active.is_(True),
        )
    )

    if designation is None:
        raise bad_request(
            "The selected designation is unavailable."
        )

    return designation


def _load_manager(
    database: Session,
    organization_id: UUID,
    manager_id: UUID | None,
    employee_id: UUID | None = None,
) -> Employee | None:
    if manager_id is None:
        return None

    if employee_id is not None and manager_id == employee_id:
        raise bad_request(
            "An employee cannot be their own manager."
        )

    manager = database.scalar(
        select(Employee).where(
            Employee.id == manager_id,
            Employee.organization_id == organization_id,
            Employee.employment_status == "ACTIVE",
        )
    )

    if manager is None:
        raise bad_request(
            "The selected manager is unavailable."
        )

    return manager


def _load_roles(
    database: Session,
    organization_id: UUID,
    role_codes: list[str],
) -> list[Role]:
    roles = list(
        database.scalars(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.code.in_(role_codes),
                Role.is_active.is_(True),
            )
        )
    )

    found_codes = {role.code for role in roles}
    missing_codes = sorted(set(role_codes) - found_codes)

    if missing_codes:
        raise bad_request(
            "Unknown or inactive role codes: "
            + ", ".join(missing_codes)
        )

    return roles


def _ensure_user_identity_is_unique(
    database: Session,
    organization_id: UUID,
    employee_code: str,
    email: str | None,
    excluded_user_id: UUID | None = None,
) -> None:
    conditions = [User.employee_code == employee_code]

    if email is not None:
        conditions.append(User.email == email)

    statement = select(User).where(
        User.organization_id == organization_id,
        or_(*conditions),
    )

    if excluded_user_id is not None:
        statement = statement.where(User.id != excluded_user_id)

    existing_user = database.scalar(statement)

    if existing_user is not None:
        raise conflict(
            "The employee code or email is already in use."
        )


def list_employees(
    database: Session,
    organization_id: UUID,
    *,
    search: str | None,
    offset: int,
    limit: int,
) -> list[Employee]:
    statement = _employee_query(organization_id).where(catalogue_visible("employees", "employee"))

    if search:
        pattern = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                User.employee_code.ilike(pattern),
                User.email.ilike(pattern),
                Employee.first_name.ilike(pattern),
                Employee.last_name.ilike(pattern),
                Employee.phone.ilike(pattern),
            )
        )

    statement = (
        statement
        .order_by(Employee.first_name, Employee.last_name)
        .offset(offset)
        .limit(limit)
    )

    return list(database.scalars(statement))


def create_employee(
    database: Session,
    organization_id: UUID,
    payload: EmployeeCreate,
) -> Employee:
    _ensure_user_identity_is_unique(
        database,
        organization_id,
        payload.employee_code,
        payload.email,
    )

    department = _load_department(
        database,
        organization_id,
        payload.department_id,
    )
    designation = _load_designation(
        database,
        organization_id,
        payload.designation_id,
    )
    manager = _load_manager(
        database,
        organization_id,
        payload.manager_id,
    )
    roles = _load_roles(
        database,
        organization_id,
        payload.role_codes,
    )

    user = User(
        organization_id=organization_id,
        employee_code=payload.employee_code,
        email=payload.email,
        password_hash=hash_password(
            payload.temporary_password
        ),
        is_active=True,
        is_superuser=False,
        must_change_password=True,
        roles=roles,
    )

    database.add(user)
    database.flush()

    employee = Employee(
        organization_id=organization_id,
        user_id=user.id,
        department_id=(
            department.id if department is not None else None
        ),
        designation_id=(
            designation.id if designation is not None else None
        ),
        manager_id=manager.id if manager is not None else None,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        bank_name=payload.bank_name,
        bank_ifsc=payload.bank_ifsc,
        bank_account_number=payload.bank_account_number,
        date_of_joining=payload.date_of_joining,
        employment_type=payload.employment_type,
        employment_status="ACTIVE",
        is_field_employee=payload.is_field_employee,
    )

    database.add(employee)
    from app.services.employee_numbering import finish_code_reuse
    finish_code_reuse(database,organization_id,user)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise conflict(
            "The employee could not be created because "
            "a unique value is already in use."
        ) from error

    return load_employee(
        database,
        organization_id,
        employee.id,
    )


def update_employee(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
    payload: EmployeeUpdate,
) -> Employee:
    employee = load_employee(
        database,
        organization_id,
        employee_id,
    )

    fields = payload.model_fields_set

    prospective_code = (
        payload.employee_code
        if "employee_code" in fields
        else employee.user.employee_code
    )
    prospective_email = (
        payload.email
        if "email" in fields
        else employee.user.email
    )

    if prospective_code is None:
        raise bad_request("Employee code cannot be empty.")

    _ensure_user_identity_is_unique(
        database,
        organization_id,
        prospective_code,
        prospective_email,
        excluded_user_id=employee.user_id,
    )

    if "employee_code" in fields:
        employee.user.employee_code = prospective_code

    if "email" in fields:
        employee.user.email = prospective_email

    if "first_name" in fields:
        if payload.first_name is None:
            raise bad_request("First name cannot be empty.")
        employee.first_name = payload.first_name

    if "last_name" in fields:
        employee.last_name = payload.last_name

    if "phone" in fields:
        employee.phone = payload.phone

    if "bank_name" in fields:
        employee.bank_name = payload.bank_name

    if "bank_ifsc" in fields:
        employee.bank_ifsc = payload.bank_ifsc

    if "bank_account_number" in fields:
        employee.bank_account_number = payload.bank_account_number

    if "date_of_joining" in fields:
        if payload.date_of_joining is None:
            raise bad_request(
                "Date of joining cannot be empty."
            )
        employee.date_of_joining = payload.date_of_joining

    if "employment_type" in fields:
        if payload.employment_type is None:
            raise bad_request(
                "Employment type cannot be empty."
            )
        employee.employment_type = payload.employment_type

    if "is_field_employee" in fields:
        employee.is_field_employee = bool(
            payload.is_field_employee
        )

    if "department_id" in fields:
        department = _load_department(
            database,
            organization_id,
            payload.department_id,
        )
        employee.department_id = (
            department.id if department is not None else None
        )

    if "designation_id" in fields:
        designation = _load_designation(
            database,
            organization_id,
            payload.designation_id,
        )
        employee.designation_id = (
            designation.id if designation is not None else None
        )

    if "manager_id" in fields:
        manager = _load_manager(
            database,
            organization_id,
            payload.manager_id,
            employee_id=employee.id,
        )
        employee.manager_id = (
            manager.id if manager is not None else None
        )

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise conflict(
            "The employee could not be updated because "
            "a unique value is already in use."
        ) from error

    return load_employee(
        database,
        organization_id,
        employee.id,
    )


def replace_employee_roles(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
    role_codes: list[str],
) -> Employee:
    employee = load_employee(
        database,
        organization_id,
        employee_id,
    )
    employee.user.roles = _load_roles(
        database,
        organization_id,
        role_codes,
    )
    database.commit()

    return load_employee(
        database,
        organization_id,
        employee.id,
    )


def reset_employee_password(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
    temporary_password: str,
) -> None:
    employee = load_employee(
        database,
        organization_id,
        employee_id,
    )

    employee.user.password_hash = hash_password(
        temporary_password
    )
    employee.user.must_change_password = True

    database.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == employee.user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )

    database.commit()


def set_employee_active_state(
    database: Session,
    organization_id: UUID,
    employee_id: UUID,
    *,
    is_active: bool,
    last_working_day=None,
    separation_type: str | None = None,
    separation_reason: str | None = None,
) -> Employee:
    database.execute(text("SELECT id FROM employees WHERE organization_id=:org AND id=:id FOR UPDATE"), {"org":organization_id,"id":employee_id})
    employee = load_employee(
        database,
        organization_id,
        employee_id,
    )

    ensure_not_archived(database, organization_id, employee_id, "employee")
    database.execute(text("DELETE FROM workforce_catalogue_state WHERE organization_id=:org AND person_id=:id AND kind='employee' AND archived_at IS NULL"), {"org":organization_id,"id":employee_id})
    employee.user.is_active = is_active
    employee.employment_status = (
        "ACTIVE" if is_active else (separation_type or "DISABLED")
    )

    if is_active:
        employee.last_working_day = None
        employee.separation_type = None
        employee.separation_reason = None
    else:
        employee.last_working_day = last_working_day
        employee.separation_type = separation_type or "DISABLED"
        employee.separation_reason = separation_reason

    if not is_active:
        database.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == employee.user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )

    database.commit()

    return load_employee(
        database,
        organization_id,
        employee.id,
    )

# manual-employee-code-v1
