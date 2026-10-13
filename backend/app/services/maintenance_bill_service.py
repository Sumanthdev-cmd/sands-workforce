from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    CompanyAsset,
    DocumentRecord,
    Outlet,
    PropertyAsset,
    Role,
    User,
    Vehicle,
    Vendor,
    user_roles,
)
from app.models.maintenance_bill import (
    MaintenanceBill,
    MaintenanceBillAction,
)
from app.schemas.maintenance_bill import (
    MaintenanceBillCreateRequest,
    MaintenanceBillPaymentRequest,
    MaintenanceBillUpdateRequest,
)

from app.services.notification_service import queue_role_notifications, queue_user_notification


ADMIN_ROLES = {"ADMIN"}
MD_ROLES = {"MD"}
VIEW_ROLES = {"ADMIN", "MD"}


def role_codes(
    database: Session,
    user: User,
) -> set[str]:
    return set(
        database.scalars(
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


def require_roles(
    database: Session,
    user: User,
    allowed: set[str],
    message: str,
) -> None:
    if not role_codes(
        database,
        user,
    ).intersection(allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )


def require_admin(
    database: Session,
    user: User,
) -> None:
    require_roles(
        database,
        user,
        ADMIN_ROLES,
        "Only Admin can perform this maintenance bill action.",
    )


def require_md(
    database: Session,
    user: User,
) -> None:
    require_roles(
        database,
        user,
        MD_ROLES,
        "Only MD can approve or reject maintenance bills.",
    )


def require_view_access(
    database: Session,
    user: User,
) -> None:
    require_roles(
        database,
        user,
        VIEW_ROLES,
        "Maintenance bill access is restricted to Admin and MD.",
    )


def get_bill(
    database: Session,
    *,
    user: User,
    bill_id: UUID,
) -> MaintenanceBill:
    row = database.scalar(
        select(MaintenanceBill).where(
            MaintenanceBill.id == bill_id,
            MaintenanceBill.organization_id
            == user.organization_id,
        )
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance bill was not found.",
        )

    return row


def add_action(
    database: Session,
    *,
    user: User,
    bill: MaintenanceBill,
    action: str,
    note: str | None = None,
    extra_data: dict | None = None,
) -> None:
    database.add(
        MaintenanceBillAction(
            organization_id=user.organization_id,
            bill_id=bill.id,
            actor_user_id=user.id,
            action=action,
            note=note,
            extra_data=extra_data,
        )
    )


def validate_document(
    database: Session,
    *,
    user: User,
    document_id: UUID | None,
) -> None:
    if document_id is None:
        return

    document = database.scalar(
        select(DocumentRecord).where(
            DocumentRecord.id == document_id,
            DocumentRecord.organization_id
            == user.organization_id,
        )
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Bill attachment was not found.",
        )

    if document.status in {
        "UPLOAD_PENDING",
        "ARCHIVED",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "Upload and activate the bill attachment "
                "before using it."
            ),
        )


def validate_related_records(
    database: Session,
    *,
    user: User,
    related_type: str,
    outlet_id: UUID | None,
    vehicle_id: UUID | None,
    property_id: UUID | None,
    company_asset_id: UUID | None,
) -> None:
    allowed = {
        "GENERAL",
        "OUTLET",
        "VEHICLE",
        "PROPERTY",
        "COMPANY_ASSET",
    }

    if related_type not in allowed:
        raise HTTPException(
            status_code=422,
            detail="Invalid related type.",
        )

    if related_type == "OUTLET":
        if outlet_id is None:
            raise HTTPException(
                status_code=422,
                detail="Select an outlet.",
            )

        found = database.scalar(
            select(Outlet.id).where(
                Outlet.id == outlet_id,
                Outlet.organization_id
                == user.organization_id,
            )
        )

        if found is None:
            raise HTTPException(
                status_code=404,
                detail="Outlet was not found.",
            )

    elif related_type == "VEHICLE":
        if vehicle_id is None:
            raise HTTPException(
                status_code=422,
                detail="Select a vehicle.",
            )

        found = database.scalar(
            select(Vehicle.id).where(
                Vehicle.id == vehicle_id,
                Vehicle.organization_id
                == user.organization_id,
            )
        )

        if found is None:
            raise HTTPException(
                status_code=404,
                detail="Vehicle was not found.",
            )

    elif related_type == "PROPERTY":
        if property_id is None:
            raise HTTPException(
                status_code=422,
                detail="Select a property.",
            )

        found = database.scalar(
            select(PropertyAsset.id).where(
                PropertyAsset.id == property_id,
                PropertyAsset.organization_id
                == user.organization_id,
            )
        )

        if found is None:
            raise HTTPException(
                status_code=404,
                detail="Property was not found.",
            )

    elif related_type == "COMPANY_ASSET":
        if company_asset_id is None:
            raise HTTPException(
                status_code=422,
                detail="Select a company asset.",
            )

        found = database.scalar(
            select(CompanyAsset.id).where(
                CompanyAsset.id
                == company_asset_id,
                CompanyAsset.organization_id
                == user.organization_id,
            )
        )

        if found is None:
            raise HTTPException(
                status_code=404,
                detail="Company asset was not found.",
            )


def validate_vendor(
    database: Session,
    *,
    user: User,
    vendor_id: UUID | None,
) -> Vendor | None:
    if vendor_id is None:
        return None

    vendor = database.scalar(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.organization_id
            == user.organization_id,
        )
    )

    if vendor is None:
        raise HTTPException(
            status_code=404,
            detail="Vendor was not found.",
        )

    return vendor


def create_bill(
    database: Session,
    *,
    user: User,
    payload: MaintenanceBillCreateRequest,
) -> MaintenanceBill:
    require_admin(database, user)

    existing = database.scalar(
        select(MaintenanceBill.id).where(
            MaintenanceBill.organization_id
            == user.organization_id,
            MaintenanceBill.submission_id
            == payload.submission_id,
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "This maintenance bill was already created."
            ),
        )

    validate_document(
        database,
        user=user,
        document_id=payload.bill_document_id,
    )

    validate_related_records(
        database,
        user=user,
        related_type=payload.related_type,
        outlet_id=payload.outlet_id,
        vehicle_id=payload.vehicle_id,
        property_id=payload.property_id,
        company_asset_id=payload.company_asset_id,
    )

    vendor = validate_vendor(
        database,
        user=user,
        vendor_id=payload.vendor_id,
    )

    vendor_name = (
        vendor.name
        if vendor is not None
        else payload.vendor_name.strip()
    )

    row = MaintenanceBill(
        organization_id=user.organization_id,
        submission_id=payload.submission_id,
        status="DRAFT",
        category=payload.category,
        related_type=payload.related_type,
        outlet_id=payload.outlet_id,
        vehicle_id=payload.vehicle_id,
        property_id=payload.property_id,
        company_asset_id=payload.company_asset_id,
        vendor_id=payload.vendor_id,
        vendor_name=vendor_name,
        invoice_number=payload.invoice_number,
        bill_date=payload.bill_date,
        due_date=payload.due_date,
        amount=payload.amount,
        description=payload.description.strip(),
        bill_document_id=payload.bill_document_id,
        created_by_user_id=user.id,
    )

    database.add(row)

    try:
        database.flush()
    except IntegrityError as error:
        database.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "This maintenance bill was already created."
            ),
        ) from error

    add_action(
        database,
        user=user,
        bill=row,
        action="CREATED",
        note="Maintenance bill draft created.",
    )

    database.commit()
    database.refresh(row)

    return row


def update_bill(
    database: Session,
    *,
    user: User,
    bill_id: UUID,
    payload: MaintenanceBillUpdateRequest,
) -> MaintenanceBill:
    require_admin(database, user)

    bill = get_bill(
        database,
        user=user,
        bill_id=bill_id,
    )

    if bill.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail="Only draft bills can be edited.",
        )

    changes = payload.model_dump(
        exclude_unset=True
    )

    if "bill_document_id" in changes:
        validate_document(
            database,
            user=user,
            document_id=changes[
                "bill_document_id"
            ],
        )

    prospective_related_type = changes.get(
        "related_type",
        bill.related_type,
    )

    validate_related_records(
        database,
        user=user,
        related_type=prospective_related_type,
        outlet_id=changes.get(
            "outlet_id",
            bill.outlet_id,
        ),
        vehicle_id=changes.get(
            "vehicle_id",
            bill.vehicle_id,
        ),
        property_id=changes.get(
            "property_id",
            bill.property_id,
        ),
        company_asset_id=changes.get(
            "company_asset_id",
            bill.company_asset_id,
        ),
    )

    if "vendor_id" in changes:
        vendor = validate_vendor(
            database,
            user=user,
            vendor_id=changes["vendor_id"],
        )

        if vendor is not None:
            changes["vendor_name"] = vendor.name

    for field_name, value in changes.items():
        setattr(
            bill,
            field_name,
            value,
        )

    add_action(
        database,
        user=user,
        bill=bill,
        action="UPDATED",
        note="Maintenance bill draft updated.",
    )

    database.commit()
    database.refresh(bill)

    return bill


def submit_bill(
    database: Session,
    *,
    user: User,
    bill_id: UUID,
) -> MaintenanceBill:
    require_admin(database, user)

    bill = get_bill(
        database,
        user=user,
        bill_id=bill_id,
    )

    if bill.status != "DRAFT":
        raise HTTPException(
            status_code=409,
            detail=(
                "This maintenance bill has already "
                "been submitted."
            ),
        )

    if bill.bill_document_id is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Upload the bill image or PDF "
                "before submitting for verification."
            ),
        )

    validate_document(
        database,
        user=user,
        document_id=bill.bill_document_id,
    )

    bill.status = "SUBMITTED"
    bill.submitted_by_user_id = user.id
    bill.submitted_at = datetime.now(
        timezone.utc
    )

    add_action(
        database,
        user=user,
        bill=bill,
        action="SUBMITTED",
        note="Bill submitted for Admin verification.",
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes=ADMIN_ROLES,
        title="Maintenance bill awaiting verification",
        body=(
            f"{bill.vendor_name} bill {bill.invoice_number or str(bill.id)[:8]} "
            f"for ₹{float(bill.amount):,.2f} is awaiting Admin verification."
        ),
        dedupe_prefix=f"maintenance:{bill.id}:submitted",
        route=f"/module/maintenance-bills?queue=1&bill={bill.id}",
        module="maintenance-bills",
        event="MAINTENANCE_SUBMITTED",
        entity_id=bill.id,
        exclude_user_ids={user.id},
    )

    database.commit()
    database.refresh(bill)

    return bill


def verify_bill(
    database: Session,
    *,
    user: User,
    bill_id: UUID,
    note: str | None,
) -> MaintenanceBill:
    require_admin(database, user)

    bill = get_bill(
        database,
        user=user,
        bill_id=bill_id,
    )

    if bill.status != "SUBMITTED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only submitted bills can be verified."
            ),
        )

    bill.status = "VERIFIED"
    bill.verified_by_user_id = user.id
    bill.verified_at = datetime.now(
        timezone.utc
    )
    bill.verification_note = note

    add_action(
        database,
        user=user,
        bill=bill,
        action="VERIFIED",
        note=note or "Bill verified by Admin.",
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes=MD_ROLES,
        title="Maintenance bill awaiting MD approval",
        body=(
            f"{bill.vendor_name} bill {bill.invoice_number or str(bill.id)[:8]} "
            f"for ₹{float(bill.amount):,.2f} was verified by {user.employee_code}."
        ),
        dedupe_prefix=f"maintenance:{bill.id}:verified",
        route=f"/module/maintenance-bills?queue=1&bill={bill.id}",
        module="maintenance-bills",
        event="MAINTENANCE_AWAITING_MD_APPROVAL",
        entity_id=bill.id,
        exclude_user_ids={user.id},
    )

    database.commit()
    database.refresh(bill)

    return bill


def reject_verification(
    database: Session,
    *,
    user: User,
    bill_id: UUID,
    reason: str,
) -> MaintenanceBill:
    require_admin(database, user)

    bill = get_bill(
        database,
        user=user,
        bill_id=bill_id,
    )

    if bill.status != "SUBMITTED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only submitted bills can be "
                "rejected during verification."
            ),
        )

    bill.status = "VERIFICATION_REJECTED"
    bill.verified_by_user_id = user.id
    bill.verified_at = datetime.now(
        timezone.utc
    )
    bill.verification_note = reason

    add_action(
        database,
        user=user,
        bill=bill,
        action="VERIFICATION_REJECTED",
        note=reason,
    )
    if bill.created_by_user_id != user.id:
        queue_user_notification(
            database,
            organization_id=user.organization_id,
            recipient_user_id=bill.created_by_user_id,
            title="Maintenance bill returned during verification",
            body=f"Bill {bill.invoice_number or str(bill.id)[:8]} was returned: {reason}",
            dedupe_key=f"maintenance:{bill.id}:verification-rejected",
            route=f"/module/maintenance-bills?bill={bill.id}",
            module="maintenance-bills",
            event="MAINTENANCE_VERIFICATION_REJECTED",
            entity_id=bill.id,
        )

    database.commit()
    database.refresh(bill)

    return bill


def approve_bill(
    database: Session,
    *,
    user: User,
    bill_id: UUID,
    note: str | None,
) -> MaintenanceBill:
    # CRITICAL:
    # ADMIN is deliberately NOT allowed here.
    require_md(database, user)

    bill = get_bill(
        database,
        user=user,
        bill_id=bill_id,
    )

    if bill.status != "VERIFIED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only Admin-verified bills can "
                "be approved by MD."
            ),
        )

    bill.status = "APPROVED"
    bill.md_user_id = user.id
    bill.decided_at = datetime.now(
        timezone.utc
    )
    bill.decision_note = note

    add_action(
        database,
        user=user,
        bill=bill,
        action="APPROVED",
        note=note or "Bill approved by MD.",
    )
    recipients = {bill.created_by_user_id, bill.verified_by_user_id}
    recipients.discard(None)
    recipients.discard(user.id)
    for recipient_id in recipients:
        queue_user_notification(
            database,
            organization_id=user.organization_id,
            recipient_user_id=recipient_id,
            title="Maintenance bill approved by MD",
            body=(
                f"Bill {bill.invoice_number or str(bill.id)[:8]} for "
                f"₹{float(bill.amount):,.2f} was approved by {user.employee_code}."
            ),
            dedupe_key=f"maintenance:{bill.id}:approved:{recipient_id}",
            route=f"/module/maintenance-bills?queue=1&bill={bill.id}",
            module="maintenance-bills",
            event="MAINTENANCE_APPROVED",
            entity_id=bill.id,
        )

    database.commit()
    database.refresh(bill)

    return bill


def reject_bill(
    database: Session,
    *,
    user: User,
    bill_id: UUID,
    reason: str,
) -> MaintenanceBill:
    # CRITICAL:
    # only MD can reject at approval stage.
    require_md(database, user)

    bill = get_bill(
        database,
        user=user,
        bill_id=bill_id,
    )

    if bill.status != "VERIFIED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only Admin-verified bills can "
                "be rejected by MD."
            ),
        )

    bill.status = "REJECTED"
    bill.md_user_id = user.id
    bill.decided_at = datetime.now(
        timezone.utc
    )
    bill.decision_note = reason

    add_action(
        database,
        user=user,
        bill=bill,
        action="REJECTED",
        note=reason,
    )
    recipients = {bill.created_by_user_id, bill.verified_by_user_id}
    recipients.discard(None)
    recipients.discard(user.id)
    for recipient_id in recipients:
        queue_user_notification(
            database,
            organization_id=user.organization_id,
            recipient_user_id=recipient_id,
            title="Maintenance bill rejected by MD",
            body=f"Bill {bill.invoice_number or str(bill.id)[:8]} was rejected: {reason}",
            dedupe_key=f"maintenance:{bill.id}:rejected:{recipient_id}",
            route=f"/module/maintenance-bills?bill={bill.id}",
            module="maintenance-bills",
            event="MAINTENANCE_REJECTED",
            entity_id=bill.id,
        )

    database.commit()
    database.refresh(bill)

    return bill


def mark_paid(
    database: Session,
    *,
    user: User,
    bill_id: UUID,
    payload: MaintenanceBillPaymentRequest,
) -> MaintenanceBill:
    require_admin(database, user)

    bill = get_bill(
        database,
        user=user,
        bill_id=bill_id,
    )

    if bill.status != "APPROVED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only MD-approved bills can "
                "be marked as paid."
            ),
        )

    bill.status = "PAID"

    bill.paid_by_user_id = user.id
    bill.paid_at = datetime.now(
        timezone.utc
    )

    bill.payment_reference = (
        payload.payment_reference.strip()
    )

    bill.payment_note = payload.note

    add_action(
        database,
        user=user,
        bill=bill,
        action="PAID",
        note=payload.note,
        extra_data={
            "payment_reference":
                payload.payment_reference.strip()
        },
    )
    if bill.created_by_user_id != user.id:
        queue_user_notification(
            database,
            organization_id=user.organization_id,
            recipient_user_id=bill.created_by_user_id,
            title="Maintenance bill payment recorded",
            body=(
                f"Payment was recorded for bill {bill.invoice_number or str(bill.id)[:8]}. "
                f"Reference: {bill.payment_reference}."
            ),
            dedupe_key=f"maintenance:{bill.id}:paid",
            route=f"/module/maintenance-bills?bill={bill.id}",
            module="maintenance-bills",
            event="MAINTENANCE_PAID",
            entity_id=bill.id,
        )

    database.commit()
    database.refresh(bill)

    return bill


def list_bills(
    database: Session,
    *,
    user: User,
) -> list[MaintenanceBill]:
    require_view_access(
        database,
        user,
    )

    return list(
        database.scalars(
            select(MaintenanceBill)
            .where(
                MaintenanceBill.organization_id
                == user.organization_id
            )
            .order_by(
                MaintenanceBill.created_at.desc()
            )
        ).all()
    )


def list_md_pending(
    database: Session,
    *,
    user: User,
) -> list[MaintenanceBill]:
    require_md(
        database,
        user,
    )

    return list(
        database.scalars(
            select(MaintenanceBill)
            .where(
                MaintenanceBill.organization_id
                == user.organization_id,
                MaintenanceBill.status
                == "VERIFIED",
            )
            .order_by(
                MaintenanceBill.verified_at
            )
        ).all()
    )


def list_actions(
    database: Session,
    *,
    user: User,
    bill_id: UUID,
) -> list[MaintenanceBillAction]:
    require_view_access(
        database,
        user,
    )

    bill = get_bill(
        database,
        user=user,
        bill_id=bill_id,
    )

    return list(
        database.scalars(
            select(MaintenanceBillAction)
            .where(
                MaintenanceBillAction.bill_id
                == bill.id
            )
            .order_by(
                MaintenanceBillAction.created_at
            )
        ).all()
    )