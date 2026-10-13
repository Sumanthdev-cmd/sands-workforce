from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    DocumentRecord,
    Employee,
    Outlet,
    PropertyAsset,
    Role,
    User,
    Vehicle,
    user_roles,
)
from app.schemas.assets import (
    OutletCreateRequest,
    OutletUpdateRequest,
    PropertyCreateRequest,
    PropertyUpdateRequest,
    VehicleCreateRequest,
    VehicleUpdateRequest,
)


ASSET_MANAGER_ROLES = {
    "ADMIN",
    "MD",
    "GM",
    "MANAGER",
}


def require_asset_manager(
    database: Session,
    user: User,
) -> None:
    codes = set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )

    if not codes.intersection(ASSET_MANAGER_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Asset-management access is required.",
        )


def create_vehicle(
    database: Session,
    *,
    user: User,
    payload: VehicleCreateRequest,
) -> Vehicle:
    require_asset_manager(database, user)

    if payload.employee_owner_id is not None:
        employee = database.scalar(
            select(Employee).where(
                Employee.id == payload.employee_owner_id,
                Employee.organization_id == user.organization_id,
            )
        )
        if employee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee owner was not found.",
            )

    vehicle = Vehicle(
        organization_id=user.organization_id,
        **payload.model_dump(),
        status="ACTIVE",
        is_active=True,
    )
    database.add(vehicle)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vehicle with this registration number already exists.",
        ) from error

    database.refresh(vehicle)
    return vehicle


def list_vehicles(
    database: Session,
    *,
    user: User,
) -> list[Vehicle]:
    require_asset_manager(database, user)

    return list(
        database.scalars(
            select(Vehicle)
            .where(Vehicle.organization_id == user.organization_id)
            .order_by(Vehicle.registration_number)
        ).all()
    )


def update_vehicle(
    database: Session,
    *,
    user: User,
    vehicle_id: UUID,
    payload: VehicleUpdateRequest,
) -> Vehicle:
    require_asset_manager(database, user)

    vehicle = database.scalar(
        select(Vehicle).where(
            Vehicle.id == vehicle_id,
            Vehicle.organization_id == user.organization_id,
        )
    )

    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle was not found.",
        )

    for field_name, value in payload.model_dump(
        exclude_unset=True
    ).items():
        setattr(vehicle, field_name, value)

    database.commit()
    database.refresh(vehicle)
    return vehicle


def create_property(
    database: Session,
    *,
    user: User,
    payload: PropertyCreateRequest,
) -> PropertyAsset:
    require_asset_manager(database, user)

    property_asset = PropertyAsset(
        organization_id=user.organization_id,
        **payload.model_dump(),
        status="ACTIVE",
        is_active=True,
    )
    database.add(property_asset)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A property with this code already exists.",
        ) from error

    database.refresh(property_asset)
    return property_asset


def list_properties(
    database: Session,
    *,
    user: User,
) -> list[PropertyAsset]:
    require_asset_manager(database, user)

    return list(
        database.scalars(
            select(PropertyAsset)
            .where(
                PropertyAsset.organization_id
                == user.organization_id
            )
            .order_by(PropertyAsset.name)
        ).all()
    )


def update_property(
    database: Session,
    *,
    user: User,
    property_id: UUID,
    payload: PropertyUpdateRequest,
) -> PropertyAsset:
    require_asset_manager(database, user)

    property_asset = database.scalar(
        select(PropertyAsset).where(
            PropertyAsset.id == property_id,
            PropertyAsset.organization_id
            == user.organization_id,
        )
    )

    if property_asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property was not found.",
        )

    for field_name, value in payload.model_dump(
        exclude_unset=True
    ).items():
        setattr(property_asset, field_name, value)

    database.commit()
    database.refresh(property_asset)
    return property_asset


def create_outlet(
    database: Session,
    *,
    user: User,
    payload: OutletCreateRequest,
) -> Outlet:
    require_asset_manager(database, user)

    if payload.blueprint_document_id is not None:
        document = database.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == payload.blueprint_document_id,
                DocumentRecord.organization_id
                == user.organization_id,
            )
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Blueprint document was not found.",
            )

    outlet = Outlet(
        organization_id=user.organization_id,
        **payload.model_dump(),
        status="ACTIVE",
        is_active=True,
    )
    database.add(outlet)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An outlet with this code already exists.",
        ) from error

    database.refresh(outlet)
    return outlet


def list_outlets(
    database: Session,
    *,
    user: User,
) -> list[Outlet]:
    require_asset_manager(database, user)

    return list(
        database.scalars(
            select(Outlet)
            .where(Outlet.organization_id == user.organization_id)
            .order_by(Outlet.name)
        ).all()
    )


def update_outlet(
    database: Session,
    *,
    user: User,
    outlet_id: UUID,
    payload: OutletUpdateRequest,
) -> Outlet:
    require_asset_manager(database, user)

    outlet = database.scalar(
        select(Outlet).where(
            Outlet.id == outlet_id,
            Outlet.organization_id == user.organization_id,
        )
    )

    if outlet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outlet was not found.",
        )

    for field_name, value in payload.model_dump(
        exclude_unset=True
    ).items():
        setattr(outlet, field_name, value)

    database.commit()
    database.refresh(outlet)
    return outlet


def renewal_severity(days_remaining: int) -> str:
    if days_remaining < 0:
        return "EXPIRED"
    if days_remaining <= 7:
        return "CRITICAL"
    if days_remaining <= 30:
        return "HIGH"
    return "UPCOMING"


def upcoming_renewals(
    database: Session,
    *,
    user: User,
    days: int,
) -> list[dict]:
    require_asset_manager(database, user)

    today = date.today()
    end_date = today + timedelta(days=days)
    items: list[dict] = []

    documents = database.scalars(
        select(DocumentRecord).where(
            DocumentRecord.organization_id == user.organization_id,
            DocumentRecord.expiry_date.is_not(None),
            DocumentRecord.expiry_date <= end_date,
            DocumentRecord.status != "ARCHIVED",
        )
    ).all()

    for document in documents:
        remaining = (document.expiry_date - today).days
        items.append(
            {
                "source_type": "DOCUMENT",
                "source_id": document.id,
                "code": document.category,
                "title": document.title,
                "renewal_type": document.category,
                "due_date": document.expiry_date,
                "days_remaining": remaining,
                "severity": renewal_severity(remaining),
            }
        )

    vehicles = database.scalars(
        select(Vehicle).where(
            Vehicle.organization_id == user.organization_id,
            Vehicle.is_active.is_(True),
        )
    ).all()

    for vehicle in vehicles:
        date_fields = [
            (
                "INSURANCE",
                vehicle.insurance_expiry_date,
            ),
            (
                "REGISTRATION",
                vehicle.registration_expiry_date,
            ),
            (
                "POLLUTION",
                vehicle.pollution_expiry_date,
            ),
        ]

        for renewal_type, due_date in date_fields:
            if due_date is None or due_date > end_date:
                continue

            remaining = (due_date - today).days
            items.append(
                {
                    "source_type": "VEHICLE",
                    "source_id": vehicle.id,
                    "code": vehicle.registration_number,
                    "title": (
                        f"{vehicle.registration_number} "
                        f"{renewal_type.title()}"
                    ),
                    "renewal_type": renewal_type,
                    "due_date": due_date,
                    "days_remaining": remaining,
                    "severity": renewal_severity(remaining),
                }
            )

    properties = database.scalars(
        select(PropertyAsset).where(
            PropertyAsset.organization_id == user.organization_id,
            PropertyAsset.next_tax_due_date.is_not(None),
            PropertyAsset.next_tax_due_date <= end_date,
            PropertyAsset.is_active.is_(True),
        )
    ).all()

    for property_asset in properties:
        remaining = (
            property_asset.next_tax_due_date - today
        ).days
        items.append(
            {
                "source_type": "PROPERTY",
                "source_id": property_asset.id,
                "code": property_asset.code,
                "title": property_asset.name,
                "renewal_type": "PROPERTY_TAX",
                "due_date": property_asset.next_tax_due_date,
                "days_remaining": remaining,
                "severity": renewal_severity(remaining),
            }
        )

    outlets = database.scalars(
        select(Outlet).where(
            Outlet.organization_id == user.organization_id,
            Outlet.licence_expiry_date.is_not(None),
            Outlet.licence_expiry_date <= end_date,
            Outlet.is_active.is_(True),
        )
    ).all()

    for outlet in outlets:
        remaining = (
            outlet.licence_expiry_date - today
        ).days
        items.append(
            {
                "source_type": "OUTLET",
                "source_id": outlet.id,
                "code": outlet.code,
                "title": outlet.name,
                "renewal_type": "LICENCE",
                "due_date": outlet.licence_expiry_date,
                "days_remaining": remaining,
                "severity": renewal_severity(remaining),
            }
        )

    return sorted(
        items,
        key=lambda item: (
            item["due_date"],
            item["source_type"],
            item["title"],
        ),
    )
