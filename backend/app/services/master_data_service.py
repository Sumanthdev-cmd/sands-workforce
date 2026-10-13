from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Department, Designation, Role
from app.schemas.master_data import (
    DepartmentCreate,
    DepartmentUpdate,
    DesignationCreate,
    DesignationUpdate,
)


def conflict(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


def bad_request(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail,
    )


def not_found(entity_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{entity_name} was not found.",
    )


def list_departments(
    database: Session,
    organization_id: UUID,
) -> list[Department]:
    return list(
        database.scalars(
            select(Department)
            .where(Department.organization_id == organization_id)
            .order_by(Department.name)
        )
    )


def create_department(
    database: Session,
    organization_id: UUID,
    payload: DepartmentCreate,
) -> Department:
    existing = database.scalar(
        select(Department).where(
            Department.organization_id == organization_id,
            (
                (Department.code == payload.code)
                | (Department.name == payload.name)
            ),
        )
    )

    if existing is not None:
        raise conflict(
            "A department with the same code or name already exists."
        )

    department = Department(
        organization_id=organization_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_active=True,
    )

    database.add(department)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise conflict(
            "A department with the same code or name already exists."
        ) from error

    database.refresh(department)
    return department


def update_department(
    database: Session,
    organization_id: UUID,
    department_id: UUID,
    payload: DepartmentUpdate,
) -> Department:
    department = database.scalar(
        select(Department).where(
            Department.id == department_id,
            Department.organization_id == organization_id,
        )
    )

    if department is None:
        raise not_found("Department")

    fields = payload.model_fields_set

    if "code" in fields:
        if payload.code is None:
            raise bad_request("Department code cannot be empty.")
        department.code = payload.code

    if "name" in fields:
        if payload.name is None:
            raise bad_request("Department name cannot be empty.")
        department.name = payload.name

    if "description" in fields:
        department.description = payload.description

    if "is_active" in fields:
        if payload.is_active is None:
            raise bad_request("Department active state cannot be empty.")
        department.is_active = payload.is_active

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise conflict(
            "A department with the same code or name already exists."
        ) from error

    database.refresh(department)
    return department


def list_designations(
    database: Session,
    organization_id: UUID,
) -> list[Designation]:
    return list(
        database.scalars(
            select(Designation)
            .where(Designation.organization_id == organization_id)
            .order_by(Designation.name)
        )
    )


def create_designation(
    database: Session,
    organization_id: UUID,
    payload: DesignationCreate,
) -> Designation:
    existing = database.scalar(
        select(Designation).where(
            Designation.organization_id == organization_id,
            (
                (Designation.code == payload.code)
                | (Designation.name == payload.name)
            ),
        )
    )

    if existing is not None:
        raise conflict(
            "A designation with the same code or name already exists."
        )

    designation = Designation(
        organization_id=organization_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        is_active=True,
    )

    database.add(designation)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise conflict(
            "A designation with the same code or name already exists."
        ) from error

    database.refresh(designation)
    return designation


def update_designation(
    database: Session,
    organization_id: UUID,
    designation_id: UUID,
    payload: DesignationUpdate,
) -> Designation:
    designation = database.scalar(
        select(Designation).where(
            Designation.id == designation_id,
            Designation.organization_id == organization_id,
        )
    )

    if designation is None:
        raise not_found("Designation")

    fields = payload.model_fields_set

    if "code" in fields:
        if payload.code is None:
            raise bad_request("Designation code cannot be empty.")
        designation.code = payload.code

    if "name" in fields:
        if payload.name is None:
            raise bad_request("Designation name cannot be empty.")
        designation.name = payload.name

    if "description" in fields:
        designation.description = payload.description

    if "is_active" in fields:
        if payload.is_active is None:
            raise bad_request("Designation active state cannot be empty.")
        designation.is_active = payload.is_active

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise conflict(
            "A designation with the same code or name already exists."
        ) from error

    database.refresh(designation)
    return designation


def list_roles(
    database: Session,
    organization_id: UUID,
) -> list[Role]:
    return list(
        database.scalars(
            select(Role)
            .where(
                Role.organization_id == organization_id,
                Role.is_active.is_(True),
            )
            .order_by(Role.name)
        )
    )
