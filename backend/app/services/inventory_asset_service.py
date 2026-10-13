from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AssetAssignment,
    AssetMaintenance,
    CompanyAsset,
    Employee,
    Role,
    User,
    user_roles,
)
from app.schemas.inventory_asset import (
    AssetAssignRequest,
    AssetReturnRequest,
    CompanyAssetCreateRequest,
    CompanyAssetUpdateRequest,
    MaintenanceCompleteRequest,
    MaintenanceCreateRequest,
)
from app.services.device_service import get_employee_for_user


MANAGER_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_manager(database: Session, user: User) -> None:
    if not role_codes(database, user).intersection(MANAGER_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Asset inventory management access is required.",
        )


def get_asset(database: Session, user: User, asset_id: UUID) -> CompanyAsset:
    row = database.scalar(
        select(CompanyAsset).where(
            CompanyAsset.id == asset_id,
            CompanyAsset.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company asset was not found.",
        )
    return row


def create_asset(
    database: Session,
    *,
    user: User,
    payload: CompanyAssetCreateRequest,
) -> CompanyAsset:
    require_manager(database, user)
    row = CompanyAsset(
        organization_id=user.organization_id,
        **payload.model_dump(),
        status="AVAILABLE",
    )
    database.add(row)
    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An asset with this code already exists.",
        ) from error
    database.refresh(row)
    return row


def list_assets(database: Session, *, user: User) -> list[CompanyAsset]:
    return list(
        database.scalars(
            select(CompanyAsset)
            .where(CompanyAsset.organization_id == user.organization_id)
            .order_by(CompanyAsset.asset_code)
        ).all()
    )


def update_asset(
    database: Session,
    *,
    user: User,
    asset_id: UUID,
    payload: CompanyAssetUpdateRequest,
) -> CompanyAsset:
    require_manager(database, user)
    row = get_asset(database, user, asset_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    database.commit()
    database.refresh(row)
    return row


def assign_asset(
    database: Session,
    *,
    user: User,
    asset_id: UUID,
    payload: AssetAssignRequest,
) -> AssetAssignment:
    require_manager(database, user)
    asset = get_asset(database, user, asset_id)

    if asset.status != "AVAILABLE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only available assets can be assigned.",
        )

    employee = database.scalar(
        select(Employee).where(
            Employee.id == payload.employee_id,
            Employee.organization_id == user.organization_id,
        )
    )
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee was not found.",
        )

    row = AssetAssignment(
        organization_id=user.organization_id,
        asset_id=asset.id,
        employee_id=employee.id,
        assigned_by_user_id=user.id,
        assigned_at=datetime.now(timezone.utc),
        expected_return_at=payload.expected_return_at,
        assignment_status="ASSIGNED",
        issue_condition=payload.issue_condition.strip().upper(),
        issue_note=payload.issue_note,
    )
    asset.status = "ASSIGNED"
    database.add(row)
    database.commit()
    database.refresh(row)
    return row


def return_asset(
    database: Session,
    *,
    user: User,
    assignment_id: UUID,
    payload: AssetReturnRequest,
) -> AssetAssignment:
    require_manager(database, user)
    row = database.scalar(
        select(AssetAssignment).where(
            AssetAssignment.id == assignment_id,
            AssetAssignment.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset assignment was not found.",
        )
    if row.assignment_status != "ASSIGNED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This asset assignment is already closed.",
        )

    row.assignment_status = "RETURNED"
    row.returned_at = datetime.now(timezone.utc)
    row.return_condition = payload.return_condition.strip().upper()
    row.return_note = payload.return_note

    asset = database.get(CompanyAsset, row.asset_id)
    if asset is not None:
        asset.status = "AVAILABLE"
        asset.condition = row.return_condition

    database.commit()
    database.refresh(row)
    return row


def list_assignments(database: Session, *, user: User) -> list[AssetAssignment]:
    require_manager(database, user)
    return list(
        database.scalars(
            select(AssetAssignment)
            .where(AssetAssignment.organization_id == user.organization_id)
            .order_by(AssetAssignment.assigned_at.desc())
        ).all()
    )


def list_my_assignments(database: Session, *, user: User) -> list[AssetAssignment]:
    employee = get_employee_for_user(database, user)
    return list(
        database.scalars(
            select(AssetAssignment)
            .where(
                AssetAssignment.organization_id == user.organization_id,
                AssetAssignment.employee_id == employee.id,
            )
            .order_by(AssetAssignment.assigned_at.desc())
        ).all()
    )


def create_maintenance(
    database: Session,
    *,
    user: User,
    payload: MaintenanceCreateRequest,
) -> AssetMaintenance:
    require_manager(database, user)
    asset = get_asset(database, user, payload.asset_id)
    row = AssetMaintenance(
        organization_id=user.organization_id,
        asset_id=asset.id,
        reported_by_user_id=user.id,
        issue_title=payload.issue_title.strip(),
        issue_description=payload.issue_description.strip(),
        vendor_name=payload.vendor_name,
        estimated_cost=payload.estimated_cost,
        status="OPEN",
        opened_at=datetime.now(timezone.utc),
        evidence_urls=payload.evidence_urls,
    )
    asset.status = "MAINTENANCE"
    database.add(row)
    database.commit()
    database.refresh(row)
    return row


def list_maintenance(database: Session, *, user: User) -> list[AssetMaintenance]:
    require_manager(database, user)
    return list(
        database.scalars(
            select(AssetMaintenance)
            .where(AssetMaintenance.organization_id == user.organization_id)
            .order_by(AssetMaintenance.opened_at.desc())
        ).all()
    )


def complete_maintenance(
    database: Session,
    *,
    user: User,
    maintenance_id: UUID,
    payload: MaintenanceCompleteRequest,
) -> AssetMaintenance:
    require_manager(database, user)
    row = database.scalar(
        select(AssetMaintenance).where(
            AssetMaintenance.id == maintenance_id,
            AssetMaintenance.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance record was not found.",
        )
    if row.status != "OPEN":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This maintenance record is already completed.",
        )

    row.status = "COMPLETED"
    row.completed_at = datetime.now(timezone.utc)
    row.actual_cost = payload.actual_cost
    row.resolution_note = payload.resolution_note.strip()

    asset = database.get(CompanyAsset, row.asset_id)
    if asset is not None:
        asset.status = "AVAILABLE"
        asset.condition = payload.asset_condition.strip().upper()

    database.commit()
    database.refresh(row)
    return row
