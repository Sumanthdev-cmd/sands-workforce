from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.permissions import require_permissions
from app.db.session import get_db
from app.models import Employee, User
from app.schemas.employees import (
    EmployeeCreate,
    EmployeeDisableRequest,
    EmployeeResponse,
    EmployeeRoleUpdate,
    EmployeeUpdate,
    NamedEntitySummary,
)
from app.services.employee_service import (
    create_employee,
    list_employees,
    load_employee,
    replace_employee_roles,
    set_employee_active_state,
    update_employee,
)


router = APIRouter(
    prefix="/employees",
    tags=["Employees"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]

EmployeeReader = Annotated[
    User,
    Depends(require_permissions("employee.read")),
]
EmployeeCreator = Annotated[
    User,
    Depends(require_permissions("employee.create")),
]
EmployeeUpdater = Annotated[
    User,
    Depends(require_permissions("employee.update")),
]
EmployeeDisabler = Annotated[
    User,
    Depends(require_permissions("employee.disable")),
]
RoleAssigner = Annotated[
    User,
    Depends(require_permissions("user.assign_roles")),
]


def employee_response(
    employee: Employee,
) -> EmployeeResponse:
    department = (
        NamedEntitySummary(
            id=employee.department.id,
            code=employee.department.code,
            name=employee.department.name,
        )
        if employee.department is not None
        else None
    )

    designation = (
        NamedEntitySummary(
            id=employee.designation.id,
            code=employee.designation.code,
            name=employee.designation.name,
        )
        if employee.designation is not None
        else None
    )

    return EmployeeResponse(
        id=employee.id,
        user_id=employee.user_id,
        organization_id=employee.organization_id,
        employee_code=employee.user.employee_code,
        email=employee.user.email,
        user_is_active=employee.user.is_active,
        must_change_password=(
            employee.user.must_change_password
        ),
        first_name=employee.first_name,
        last_name=employee.last_name,
        full_name=employee.full_name,
        phone=employee.phone,
        bank_name=employee.bank_name,
        bank_ifsc=employee.bank_ifsc,
        bank_account_number=employee.bank_account_number,
        date_of_joining=employee.date_of_joining,
        employment_type=employee.employment_type,
        employment_status=employee.employment_status,
        last_working_day=employee.last_working_day,
        separation_type=employee.separation_type,
        separation_reason=employee.separation_reason,
        is_field_employee=employee.is_field_employee,
        department=department,
        designation=designation,
        manager_id=employee.manager_id,
        role_codes=sorted(
            role.code
            for role in employee.user.roles
        ),
    )


@router.get(
    "",
    response_model=list[EmployeeResponse],
)
def read_employees(
    current_user: EmployeeReader,
    database: DatabaseSession,
    search: str | None = Query(
        default=None,
        max_length=100,
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[EmployeeResponse]:
    employees = list_employees(
        database,
        current_user.organization_id,
        search=search,
        offset=offset,
        limit=limit,
    )

    return [
        employee_response(employee)
        for employee in employees
    ]


@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def read_employee(
    employee_id: UUID,
    current_user: EmployeeReader,
    database: DatabaseSession,
) -> EmployeeResponse:
    employee = load_employee(
        database,
        current_user.organization_id,
        employee_id,
    )
    return employee_response(employee)


@router.post(
    "",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_employee(
    payload: EmployeeCreate,
    current_user: EmployeeCreator,
    database: DatabaseSession,
) -> EmployeeResponse:
    employee = create_employee(
        database,
        current_user.organization_id,
        payload,
    )
    return employee_response(employee)


@router.patch(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
def edit_employee(
    employee_id: UUID,
    payload: EmployeeUpdate,
    current_user: EmployeeUpdater,
    database: DatabaseSession,
) -> EmployeeResponse:
    employee = update_employee(
        database,
        current_user.organization_id,
        employee_id,
        payload,
    )
    return employee_response(employee)


@router.put(
    "/{employee_id}/roles",
    response_model=EmployeeResponse,
)
def assign_employee_roles(
    employee_id: UUID,
    payload: EmployeeRoleUpdate,
    current_user: RoleAssigner,
    database: DatabaseSession,
) -> EmployeeResponse:
    employee = replace_employee_roles(
        database,
        current_user.organization_id,
        employee_id,
        payload.role_codes,
    )
    return employee_response(employee)


@router.post(
    "/{employee_id}/disable",
    response_model=EmployeeResponse,
)
def disable_employee(
    employee_id: UUID,
    payload: EmployeeDisableRequest,
    current_user: EmployeeDisabler,
    database: DatabaseSession,
) -> EmployeeResponse:
    employee = set_employee_active_state(
        database,
        current_user.organization_id,
        employee_id,
        is_active=False,
        last_working_day=payload.last_working_day,
        separation_type=payload.separation_type,
        separation_reason=payload.reason,
    )
    return employee_response(employee)


@router.post(
    "/{employee_id}/enable",
    response_model=EmployeeResponse,
)
def enable_employee(
    employee_id: UUID,
    current_user: EmployeeDisabler,
    database: DatabaseSession,
) -> EmployeeResponse:
    employee = set_employee_active_state(
        database,
        current_user.organization_id,
        employee_id,
        is_active=True,
    )
    return employee_response(employee)
