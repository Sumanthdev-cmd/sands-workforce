from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Employee,
    InspectionReport,
    Outlet,
    OutletFieldVisitorAssignment,
    Role,
    User,
    Vendor,
    user_roles,
)
from app.schemas.outlets import OutletCreateRequest, OutletUpdateRequest


READ_ROLES = {"ADMIN", "MD", "GM", "MANAGER", "FIELD_VISITOR"}
MANAGEMENT_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}
WRITE_ROLES = {"ADMIN"}


def _role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def _require(database: Session, user: User, allowed: set[str], message: str) -> set[str]:
    roles = _role_codes(database, user)
    if not roles.intersection(allowed):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)
    return roles


def _employee_for_user(database: Session, user: User) -> Employee | None:
    return database.scalar(
        select(Employee).where(
            Employee.user_id == user.id,
            Employee.organization_id == user.organization_id,
        )
    )


def _get_outlet(database: Session, user: User, outlet_id: UUID) -> Outlet:
    outlet = database.scalar(
        select(Outlet).where(
            Outlet.id == outlet_id,
            Outlet.organization_id == user.organization_id,
        )
    )
    if outlet is None:
        raise HTTPException(status_code=404, detail="Shop / outlet was not found.")
    return outlet


def _get_vendor(database: Session, user: User, vendor_id: UUID | None) -> Vendor | None:
    if vendor_id is None:
        return None
    vendor = database.scalar(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.organization_id == user.organization_id,
        )
    )
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor was not found.")
    return vendor


def _employee_name(
    employee: Employee,
    employee_code: str | None = None,
) -> str:
    full_name = " ".join(
        part
        for part in [
            getattr(employee, "first_name", None),
            getattr(employee, "last_name", None),
        ]
        if part
    ).strip()

    return full_name or employee_code or "Unnamed employee"


def _sync_vendor_snapshot(outlet: Outlet, vendor: Vendor | None) -> None:
    _sync_named_vendor_snapshot(outlet, "vendor", vendor)


def _sync_named_vendor_snapshot(
    outlet: Outlet,
    prefix: str,
    vendor: Vendor | None,
) -> None:
    if vendor is None:
        return
    setattr(outlet, f"{prefix}_id", vendor.id)
    setattr(
        outlet,
        f"{prefix}_name",
        getattr(vendor, "name", None) or getattr(outlet, f"{prefix}_name"),
    )
    setattr(
        outlet,
        f"{prefix}_contact_person",
        getattr(vendor, "contact_person", None)
        or getattr(outlet, f"{prefix}_contact_person"),
    )
    setattr(
        outlet,
        f"{prefix}_phone",
        getattr(vendor, "phone", None) or getattr(outlet, f"{prefix}_phone"),
    )
    setattr(
        outlet,
        f"{prefix}_email",
        getattr(vendor, "email", None) or getattr(outlet, f"{prefix}_email"),
    )


def _assignment_rows(database: Session, outlet: Outlet):
    rows = database.execute(
        select(
            OutletFieldVisitorAssignment,
            Employee,
            User,
        )
        .join(
            Employee,
            Employee.id == OutletFieldVisitorAssignment.employee_id,
        )
        .join(
            User,
            User.id == Employee.user_id,
        )
        .where(
            OutletFieldVisitorAssignment.organization_id
            == outlet.organization_id,
            OutletFieldVisitorAssignment.outlet_id
            == outlet.id,
            OutletFieldVisitorAssignment.is_active.is_(True),
        )
        .order_by(User.employee_code)
    ).all()

    return [
        {
            "id": assignment.id,
            "employee_id": employee.id,
            "employee_code": employee_user.employee_code,
            "employee_name": _employee_name(
                employee,
                employee_user.employee_code,
            ),
            "phone": getattr(employee, "phone", None),
            "assigned_at": assignment.assigned_at,
            "is_active": assignment.is_active,
            "notes": assignment.notes,
        }
        for assignment, employee, employee_user in rows
    ]


def _inspection_counts(database: Session, outlet: Outlet):
    reports = list(
        database.scalars(
            select(InspectionReport).where(
                InspectionReport.organization_id == outlet.organization_id,
                InspectionReport.outlet_id == outlet.id,
            )
        ).all()
    )
    return (
        len(reports),
        sum(1 for report in reports if report.status == "VENDOR_PENDING"),
    )


def serialize_outlet(database: Session, outlet: Outlet) -> dict:
    inspection_count, pending = _inspection_counts(database, outlet)
    return {
        "id": outlet.id,
        "code": outlet.code,
        "name": outlet.name,
        "outlet_type": outlet.outlet_type,
        "cluster_name": outlet.cluster_name,
        "address": outlet.address,
        "latitude": outlet.latitude,
        "longitude": outlet.longitude,
        "attendance_radius_meters": outlet.attendance_radius_meters,
        "vendor_id": outlet.vendor_id,
        "vendor_name": outlet.vendor_name,
        "vendor_contact_person": outlet.vendor_contact_person,
        "vendor_phone": outlet.vendor_phone,
        "vendor_email": outlet.vendor_email,
        "assistant_vendor_id": outlet.assistant_vendor_id,
        "assistant_vendor_name": outlet.assistant_vendor_name,
        "assistant_vendor_contact_person": outlet.assistant_vendor_contact_person,
        "assistant_vendor_phone": outlet.assistant_vendor_phone,
        "assistant_vendor_email": outlet.assistant_vendor_email,
        "parcel_vendor_id": outlet.parcel_vendor_id,
        "parcel_vendor_name": outlet.parcel_vendor_name,
        "parcel_vendor_contact_person": outlet.parcel_vendor_contact_person,
        "parcel_vendor_phone": outlet.parcel_vendor_phone,
        "parcel_vendor_email": outlet.parcel_vendor_email,
        "opening_date": outlet.opening_date,
        "licence_number": outlet.licence_number,
        "licence_expiry_date": outlet.licence_expiry_date,
        "excise_licence_number": outlet.excise_licence_number,
        "excise_expiry_date": outlet.excise_expiry_date,
        "rent_agreement_expiry_date": outlet.rent_agreement_expiry_date,
        "blueprint_document_id": outlet.blueprint_document_id,
        "status": outlet.status,
        "notes": outlet.notes,
        "is_active": outlet.is_active,
        "created_at": outlet.created_at,
        "updated_at": outlet.updated_at,
        "field_visitors": _assignment_rows(database, outlet),
        "inspection_count": inspection_count,
        "pending_vendor_inspections": pending,
    }


def create_outlet(database: Session, *, user: User, payload: OutletCreateRequest):
    _require(database, user, WRITE_ROLES, "Only Admin can add shops / outlets.")
    vendor = _get_vendor(database, user, payload.vendor_id)
    assistant_vendor = _get_vendor(database, user, payload.assistant_vendor_id)
    parcel_vendor = _get_vendor(database, user, payload.parcel_vendor_id)

    outlet = Outlet(
        organization_id=user.organization_id,
        code=payload.code,
        name=payload.name.strip(),
        outlet_type=payload.outlet_type,
        cluster_name=payload.cluster_name,
        address=payload.address.strip(),
        latitude=payload.latitude,
        longitude=payload.longitude,
        attendance_radius_meters=payload.attendance_radius_meters,
        vendor_id=payload.vendor_id,
        vendor_name=payload.vendor_name,
        vendor_contact_person=payload.vendor_contact_person,
        vendor_phone=payload.vendor_phone,
        vendor_email=payload.vendor_email,
        assistant_vendor_id=payload.assistant_vendor_id,
        assistant_vendor_name=payload.assistant_vendor_name,
        assistant_vendor_contact_person=payload.assistant_vendor_contact_person,
        assistant_vendor_phone=payload.assistant_vendor_phone,
        assistant_vendor_email=payload.assistant_vendor_email,
        parcel_vendor_id=payload.parcel_vendor_id,
        parcel_vendor_name=payload.parcel_vendor_name,
        parcel_vendor_contact_person=payload.parcel_vendor_contact_person,
        parcel_vendor_phone=payload.parcel_vendor_phone,
        parcel_vendor_email=payload.parcel_vendor_email,
        opening_date=payload.opening_date,
        licence_number=payload.licence_number,
        licence_expiry_date=payload.licence_expiry_date,
        excise_licence_number=payload.excise_licence_number,
        excise_expiry_date=payload.excise_expiry_date,
        rent_agreement_expiry_date=payload.rent_agreement_expiry_date,
        blueprint_document_id=payload.blueprint_document_id,
        notes=payload.notes,
        status="ACTIVE",
        is_active=True,
    )
    _sync_vendor_snapshot(outlet, vendor)
    _sync_named_vendor_snapshot(outlet, "assistant_vendor", assistant_vendor)
    _sync_named_vendor_snapshot(outlet, "parcel_vendor", parcel_vendor)
    database.add(outlet)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=409,
            detail="An outlet with this code already exists.",
        ) from error

    database.refresh(outlet)
    return serialize_outlet(database, outlet)


def list_outlets(database: Session, *, user: User):
    roles = _require(database, user, READ_ROLES, "Shop / outlet access is required.")
    statement = select(Outlet).where(Outlet.organization_id == user.organization_id)

    if "FIELD_VISITOR" in roles and not roles.intersection(MANAGEMENT_ROLES):
        employee = _employee_for_user(database, user)
        if employee is None:
            return []

        # Rotating inspection assignments replace permanent outlet-to-visitor
        # access. A field visitor can see only outlets that currently have an
        # ASSIGNED or STARTED visit for that employee.
        assigned_outlet_ids = list(
            database.scalars(
                text(
                    """
                    SELECT DISTINCT outlet_id
                    FROM inspection_visit_assignments
                    WHERE
                        organization_id = :org
                        AND field_visitor_employee_id = :employee_id
                        AND status IN ('ASSIGNED', 'STARTED')
                    """
                ),
                {
                    "org": user.organization_id,
                    "employee_id": employee.id,
                },
            ).all()
        )

        if not assigned_outlet_ids:
            return []

        statement = statement.where(
            Outlet.id.in_(assigned_outlet_ids)
        )

    rows = list(database.scalars(statement.order_by(Outlet.name)).unique().all())
    return [serialize_outlet(database, row) for row in rows]


def read_outlet(database: Session, *, user: User, outlet_id: UUID):
    for outlet in list_outlets(database, user=user):
        if outlet["id"] == outlet_id:
            return outlet
    raise HTTPException(
        status_code=404,
        detail="Shop / outlet was not found or is not assigned to you.",
    )


def update_outlet(database: Session, *, user: User, outlet_id: UUID, payload: OutletUpdateRequest):
    _require(database, user, WRITE_ROLES, "Only Admin can edit shops / outlets.")
    outlet = _get_outlet(database, user, outlet_id)
    values = payload.model_dump(exclude_unset=True)

    if "vendor_id" in values:
        vendor_id = values.pop("vendor_id")
        outlet.vendor_id = vendor_id
        vendor = _get_vendor(database, user, vendor_id)
        _sync_vendor_snapshot(outlet, vendor)

    if "assistant_vendor_id" in values:
        assistant_vendor_id = values.pop("assistant_vendor_id")
        outlet.assistant_vendor_id = assistant_vendor_id
        assistant_vendor = _get_vendor(database, user, assistant_vendor_id)
        _sync_named_vendor_snapshot(outlet, "assistant_vendor", assistant_vendor)

    if "parcel_vendor_id" in values:
        parcel_vendor_id = values.pop("parcel_vendor_id")
        outlet.parcel_vendor_id = parcel_vendor_id
        parcel_vendor = _get_vendor(database, user, parcel_vendor_id)
        _sync_named_vendor_snapshot(outlet, "parcel_vendor", parcel_vendor)

    for field, value in values.items():
        setattr(outlet, field, value)

    if outlet.status == "INACTIVE":
        outlet.is_active = False

    database.commit()
    database.refresh(outlet)
    return serialize_outlet(database, outlet)


def field_visitor_options(database: Session, *, user: User):
    _require(database, user, MANAGEMENT_ROLES, "Management access is required.")

    rows = database.execute(
    select(
        Employee,
        User,
    )
    .join(
        User,
        Employee.user_id == User.id,
    )
    .join(
        user_roles,
        User.id == user_roles.c.user_id,
    )
    .join(
        Role,
        Role.id == user_roles.c.role_id,
    )
    .where(
        Employee.organization_id == user.organization_id,
        User.organization_id == user.organization_id,
        User.is_active.is_(True),
        Role.code == "FIELD_VISITOR",
    )
    .order_by(User.employee_code)
).unique().all()

    return [
    {
        "employee_id": employee.id,
        "employee_code": employee_user.employee_code,
        "full_name": _employee_name(
            employee,
            employee_user.employee_code,
        ),
        "phone": getattr(employee, "phone", None),
    }
    for employee, employee_user in rows
]


def assign_field_visitor(database: Session, *, user: User, outlet_id: UUID, employee_id: UUID):
    _require(database, user, WRITE_ROLES, "Only Admin can assign field visitors.")
    outlet = _get_outlet(database, user, outlet_id)

    employee = database.scalar(
        select(Employee)
        .join(User, Employee.user_id == User.id)
        .join(user_roles, User.id == user_roles.c.user_id)
        .join(Role, Role.id == user_roles.c.role_id)
        .where(
            Employee.id == employee_id,
            Employee.organization_id == user.organization_id,
            Role.code == "FIELD_VISITOR",
        )
    )
    if employee is None:
        raise HTTPException(
            status_code=400,
            detail="Selected employee does not have the FIELD_VISITOR role.",
        )

    existing = database.scalar(
        select(OutletFieldVisitorAssignment).where(
            OutletFieldVisitorAssignment.organization_id == user.organization_id,
            OutletFieldVisitorAssignment.outlet_id == outlet.id,
            OutletFieldVisitorAssignment.employee_id == employee.id,
            OutletFieldVisitorAssignment.is_active.is_(True),
        )
    )
    if existing is None:
        database.add(
            OutletFieldVisitorAssignment(
                organization_id=user.organization_id,
                outlet_id=outlet.id,
                employee_id=employee.id,
                assigned_by_user_id=user.id,
                is_active=True,
            )
        )
        database.commit()

    return serialize_outlet(database, outlet)


def unassign_field_visitor(database: Session, *, user: User, outlet_id: UUID, assignment_id: UUID):
    _require(database, user, WRITE_ROLES, "Only Admin can unassign field visitors.")
    outlet = _get_outlet(database, user, outlet_id)

    assignment = database.scalar(
        select(OutletFieldVisitorAssignment).where(
            OutletFieldVisitorAssignment.id == assignment_id,
            OutletFieldVisitorAssignment.organization_id == user.organization_id,
            OutletFieldVisitorAssignment.outlet_id == outlet.id,
            OutletFieldVisitorAssignment.is_active.is_(True),
        )
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="Active assignment was not found.")

    assignment.is_active = False
    assignment.unassigned_at = datetime.now(timezone.utc)
    database.commit()
    return serialize_outlet(database, outlet)


def inspection_options(database: Session, *, user: User):
    rows = list_outlets(database, user=user)
    return [
        {
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "cluster_name": row["cluster_name"],
            "address": row["address"],
            "vendor_id": row["vendor_id"],
            "vendor_name": row["vendor_name"],
        }
        for row in rows
        if row["is_active"]
    ]


def outlet_inspections(database: Session, *, user: User, outlet_id: UUID):
    read_outlet(database, user=user, outlet_id=outlet_id)
    return list(
        database.scalars(
            select(InspectionReport)
            .where(
                InspectionReport.organization_id == user.organization_id,
                InspectionReport.outlet_id == outlet_id,
            )
            .order_by(InspectionReport.inspection_started_at.desc())
        ).all()
    )
