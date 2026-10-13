from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.permissions import require_permissions
from app.db.session import get_db
from app.models import User
from app.schemas.master_data import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    DesignationCreate,
    DesignationResponse,
    DesignationUpdate,
    RoleSummary,
)
from app.services.master_data_service import (
    create_department,
    create_designation,
    list_departments,
    list_designations,
    list_roles,
    update_department,
    update_designation,
)


router = APIRouter(
    prefix="/master-data",
    tags=["Master Data"],
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
PermissionViewer = Annotated[
    User,
    Depends(require_permissions("permission.view")),
]


def department_response(
    department,
) -> DepartmentResponse:
    return DepartmentResponse(
        id=department.id,
        code=department.code,
        name=department.name,
        description=department.description,
        is_active=department.is_active,
    )


def designation_response(
    designation,
) -> DesignationResponse:
    return DesignationResponse(
        id=designation.id,
        code=designation.code,
        name=designation.name,
        description=designation.description,
        is_active=designation.is_active,
    )


@router.get(
    "/departments",
    response_model=list[DepartmentResponse],
)
def read_departments(
    current_user: EmployeeReader,
    database: DatabaseSession,
) -> list[DepartmentResponse]:
    return [
        department_response(item)
        for item in list_departments(
            database,
            current_user.organization_id,
        )
    ]


@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_department(
    payload: DepartmentCreate,
    current_user: EmployeeCreator,
    database: DatabaseSession,
) -> DepartmentResponse:
    department = create_department(
        database,
        current_user.organization_id,
        payload,
    )
    return department_response(department)


@router.patch(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
)
def edit_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    current_user: EmployeeUpdater,
    database: DatabaseSession,
) -> DepartmentResponse:
    department = update_department(
        database,
        current_user.organization_id,
        department_id,
        payload,
    )
    return department_response(department)


@router.get(
    "/designations",
    response_model=list[DesignationResponse],
)
def read_designations(
    current_user: EmployeeReader,
    database: DatabaseSession,
) -> list[DesignationResponse]:
    return [
        designation_response(item)
        for item in list_designations(
            database,
            current_user.organization_id,
        )
    ]


@router.post(
    "/designations",
    response_model=DesignationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_designation(
    payload: DesignationCreate,
    current_user: EmployeeCreator,
    database: DatabaseSession,
) -> DesignationResponse:
    designation = create_designation(
        database,
        current_user.organization_id,
        payload,
    )
    return designation_response(designation)


@router.patch(
    "/designations/{designation_id}",
    response_model=DesignationResponse,
)
def edit_designation(
    designation_id: UUID,
    payload: DesignationUpdate,
    current_user: EmployeeUpdater,
    database: DatabaseSession,
) -> DesignationResponse:
    designation = update_designation(
        database,
        current_user.organization_id,
        designation_id,
        payload,
    )
    return designation_response(designation)


@router.get(
    "/roles",
    response_model=list[RoleSummary],
)
def read_roles(
    current_user: PermissionViewer,
    database: DatabaseSession,
) -> list[RoleSummary]:
    return [
        RoleSummary(
            id=role.id,
            code=role.code,
            name=role.name,
            description=role.description,
            is_active=role.is_active,
        )
        for role in list_roles(
            database,
            current_user.organization_id,
        )
    ]
