from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ExternalLabourPayment,
    ExternalLabourPaymentAction,
    Notification,
    Outlet,
    Role,
    ShopRental,
    ShopRentalAdvanceRefund,
    User,
    Vendor,
    VendorDepositRefund,
    VendorIssue,
    VendorIssueAction,
    Wing,
    WingContact,
    user_roles,
)
from app.schemas.operations import (
    LabourPaymentCreateRequest,
    LabourPaymentPaidRequest,
    ShopRentalAdvanceRefundCreateRequest,
    ShopRentalCreateRequest,
    ShopRentalUpdateRequest,
    VendorCreateRequest,
    VendorDepositRefundCreateRequest,
    VendorIssueAssignRequest,
    VendorIssueCreateRequest,
    VendorIssueDecisionRequest,
    VendorUpdateRequest,
    WingContactCreateRequest,
    WingContactUpdateRequest,
    WingCreateRequest,
    WingUpdateRequest,
)
from app.services.notification_service import queue_role_notifications, queue_user_notification


OPS_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}
MD_ROLES = {"MD"}
PAYMENT_ROLES = {"ADMIN", "MD"}


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_roles(
    database: Session,
    user: User,
    allowed: set[str],
    message: str,
) -> None:
    if not role_codes(database, user).intersection(allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )


def notify(
    database: Session,
    *,
    recipient_user_id: UUID,
    organization_id: UUID,
    title: str,
    body: str,
    payload: dict,
    dedupe_key: str,
) -> None:
    database.add(
        Notification(
            organization_id=organization_id,
            recipient_user_id=recipient_user_id,
            channel="IN_APP",
            title=title,
            body=body,
            payload=payload,
            dedupe_key=dedupe_key,
            status="PENDING",
            attempts=0,
            available_at=datetime.now(timezone.utc),
        )
    )


def create_vendor(
    database: Session,
    *,
    user: User,
    payload: VendorCreateRequest,
) -> Vendor:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Vendor-management access is required.",
    )

    vendor = Vendor(
        organization_id=user.organization_id,
        **payload.model_dump(),
        status="ACTIVE",
    )
    database.add(vendor)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vendor with this code already exists.",
        ) from error

    database.refresh(vendor)
    return vendor


def request_vendor_deposit_refund(
    database: Session,
    *,
    user: User,
    vendor_id: UUID,
    payload: VendorDepositRefundCreateRequest,
) -> VendorDepositRefund:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Vendor-deposit refund access is required.",
    )
    vendor = database.scalar(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.organization_id == user.organization_id,
        )
    )
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor was not found.")
    if not vendor.deposit_amount or vendor.deposit_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No deposit amount is recorded for this vendor.",
        )
    if payload.amount > vendor.deposit_amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Refund amount cannot be greater than the recorded vendor deposit.",
        )
    row = VendorDepositRefund(
        organization_id=user.organization_id,
        vendor_id=vendor.id,
        requested_by_user_id=user.id,
        status="PENDING_MD",
        **payload.model_dump(),
    )
    database.add(row)
    database.flush()
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={"MD"},
        title="Vendor deposit refund needs approval",
        body=(
            f"{vendor.code} — {vendor.name}: refund {row.amount:.2f} "
            f"by {row.payment_mode}. Reason: {row.reason}"
        ),
        dedupe_prefix=f"vendor-deposit-refund:{row.id}:requested",
        route="/module/shop-rentals?vendor_refunds=1",
        module="shop-rentals",
        event="VENDOR_DEPOSIT_REFUND_REQUESTED",
        entity_id=row.id,
    )
    database.commit()
    database.refresh(row)
    return row


def list_vendor_deposit_refunds(
    database: Session,
    *,
    user: User,
) -> list[VendorDepositRefund]:
    require_roles(
        database,
        user,
        OPS_ROLES | MD_ROLES,
        "Vendor-deposit refund access is required.",
    )
    return list(
        database.scalars(
            select(VendorDepositRefund)
            .where(VendorDepositRefund.organization_id == user.organization_id)
            .order_by(VendorDepositRefund.created_at.desc())
            .limit(200)
        ).all()
    )


def decide_vendor_deposit_refund(
    database: Session,
    *,
    user: User,
    refund_id: UUID,
    note: str | None,
    approved: bool,
) -> VendorDepositRefund:
    require_roles(
        database,
        user,
        MD_ROLES,
        "Only MD can approve or reject vendor deposit refunds.",
    )
    row = database.scalar(
        select(VendorDepositRefund).where(
            VendorDepositRefund.id == refund_id,
            VendorDepositRefund.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Vendor deposit refund was not found.")
    if row.status != "PENDING_MD":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending MD refund requests can be decided.",
        )
    row.status = "APPROVED" if approved else "REJECTED"
    row.md_user_id = user.id
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = note
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=row.requested_by_user_id,
        title=f"Vendor deposit refund {row.status.lower()}",
        body=f"MD {row.status.lower()} the vendor deposit refund request.",
        dedupe_key=f"vendor-deposit-refund:{row.id}:decision:{row.status}",
        route="/module/shop-rentals?vendor_refunds=1",
        module="shop-rentals",
        event=f"VENDOR_DEPOSIT_REFUND_{row.status}",
        entity_id=row.id,
    )
    database.commit()
    database.refresh(row)
    return row


def list_vendors(database: Session, *, user: User) -> list[Vendor]:
    return list(
        database.scalars(
            select(Vendor)
            .where(Vendor.organization_id == user.organization_id)
            .order_by(Vendor.name)
        ).all()
    )


def update_vendor(
    database: Session,
    *,
    user: User,
    vendor_id: UUID,
    payload: VendorUpdateRequest,
) -> Vendor:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Vendor-management access is required.",
    )

    vendor = database.scalar(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.organization_id == user.organization_id,
        )
    )

    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor was not found.",
        )

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(vendor, key, value)

    database.commit()
    database.refresh(vendor)
    return vendor


def create_shop_rental(
    database: Session,
    *,
    user: User,
    payload: ShopRentalCreateRequest,
) -> ShopRental:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Shop-rental management access is required.",
    )
    rental = ShopRental(
        organization_id=user.organization_id,
        status="ACTIVE",
        **payload.model_dump(),
    )
    database.add(rental)
    database.commit()
    database.refresh(rental)
    return rental


def list_shop_rentals(database: Session, *, user: User) -> list[ShopRental]:
    require_roles(
        database,
        user,
        OPS_ROLES | MD_ROLES,
        "Shop-rental access is required.",
    )
    return list(
        database.scalars(
            select(ShopRental)
            .where(ShopRental.organization_id == user.organization_id)
            .order_by(ShopRental.status, ShopRental.building_name)
        ).all()
    )


def update_shop_rental(
    database: Session,
    *,
    user: User,
    rental_id: UUID,
    payload: ShopRentalUpdateRequest,
) -> ShopRental:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Shop-rental management access is required.",
    )
    rental = database.scalar(
        select(ShopRental).where(
            ShopRental.id == rental_id,
            ShopRental.organization_id == user.organization_id,
        )
    )
    if rental is None:
        raise HTTPException(status_code=404, detail="Shop rental record was not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rental, key, value)
    database.commit()
    database.refresh(rental)
    return rental


def request_shop_rental_refund(
    database: Session,
    *,
    user: User,
    rental_id: UUID,
    payload: ShopRentalAdvanceRefundCreateRequest,
) -> ShopRentalAdvanceRefund:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Shop-rental refund access is required.",
    )
    rental = database.scalar(
        select(ShopRental).where(
            ShopRental.id == rental_id,
            ShopRental.organization_id == user.organization_id,
        )
    )
    if rental is None:
        raise HTTPException(status_code=404, detail="Shop rental record was not found.")
    if not rental.advance_amount or rental.advance_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No advance amount is recorded for this rental.",
        )
    if payload.amount > rental.advance_amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Refund amount cannot be greater than the recorded rental advance.",
        )
    row = ShopRentalAdvanceRefund(
        organization_id=user.organization_id,
        rental_id=rental.id,
        requested_by_user_id=user.id,
        status="PENDING_MD",
        **payload.model_dump(),
    )
    database.add(row)
    database.flush()
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={"MD"},
        title="Shop-rental advance refund needs approval",
        body=(
            f"{rental.building_name}: refund {row.amount:.2f} "
            f"by {row.payment_mode}. Reason: {row.reason}"
        ),
        dedupe_prefix=f"shop-rental-refund:{row.id}:requested",
        route="/module/shop-rentals?refunds=1",
        module="shop-rentals",
        event="SHOP_RENTAL_REFUND_REQUESTED",
        entity_id=row.id,
    )
    database.commit()
    database.refresh(row)
    return row


def list_shop_rental_refunds(
    database: Session,
    *,
    user: User,
) -> list[ShopRentalAdvanceRefund]:
    require_roles(
        database,
        user,
        OPS_ROLES | MD_ROLES,
        "Shop-rental refund access is required.",
    )
    return list(
        database.scalars(
            select(ShopRentalAdvanceRefund)
            .where(ShopRentalAdvanceRefund.organization_id == user.organization_id)
            .order_by(ShopRentalAdvanceRefund.created_at.desc())
            .limit(200)
        ).all()
    )


def decide_shop_rental_refund(
    database: Session,
    *,
    user: User,
    refund_id: UUID,
    note: str | None,
    approved: bool,
) -> ShopRentalAdvanceRefund:
    require_roles(
        database,
        user,
        MD_ROLES,
        "Only MD can approve or reject shop-rental advance refunds.",
    )
    row = database.scalar(
        select(ShopRentalAdvanceRefund).where(
            ShopRentalAdvanceRefund.id == refund_id,
            ShopRentalAdvanceRefund.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Shop-rental refund was not found.")
    if row.status != "PENDING_MD":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending MD refund requests can be decided.",
        )
    row.status = "APPROVED" if approved else "REJECTED"
    row.md_user_id = user.id
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = note
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=row.requested_by_user_id,
        title=f"Shop-rental advance refund {row.status.lower()}",
        body=f"MD {row.status.lower()} the shop-rental advance refund request.",
        dedupe_key=f"shop-rental-refund:{row.id}:decision:{row.status}",
        route="/module/shop-rentals?refunds=1",
        module="shop-rentals",
        event=f"SHOP_RENTAL_REFUND_{row.status}",
        entity_id=row.id,
    )
    database.commit()
    database.refresh(row)
    return row


def create_vendor_issue(
    database: Session,
    *,
    user: User,
    payload: VendorIssueCreateRequest,
) -> VendorIssue:
    if payload.vendor_id:
        vendor = database.scalar(
            select(Vendor).where(
                Vendor.id == payload.vendor_id,
                Vendor.organization_id == user.organization_id,
            )
        )
        if vendor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vendor was not found.",
            )

    if payload.outlet_id:
        outlet = database.scalar(
            select(Outlet).where(
                Outlet.id == payload.outlet_id,
                Outlet.organization_id == user.organization_id,
            )
        )
        if outlet is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Outlet was not found.",
            )

    issue = VendorIssue(
        organization_id=user.organization_id,
        raised_by_user_id=user.id,
        status="OPEN",
        **payload.model_dump(),
    )
    database.add(issue)
    database.flush()

    database.add(
        VendorIssueAction(
            organization_id=user.organization_id,
            issue_id=issue.id,
            actor_user_id=user.id,
            action="RAISED",
            note="Vendor issue raised.",
        )
    )

    database.commit()
    database.refresh(issue)
    return issue


def list_my_vendor_issues(
    database: Session,
    *,
    user: User,
) -> list[VendorIssue]:
    return list(
        database.scalars(
            select(VendorIssue)
            .where(
                VendorIssue.organization_id == user.organization_id,
                VendorIssue.raised_by_user_id == user.id,
            )
            .order_by(VendorIssue.created_at.desc())
        ).all()
    )


def list_pending_vendor_issues(
    database: Session,
    *,
    user: User,
) -> list[VendorIssue]:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Vendor-issue review access is required.",
    )

    return list(
        database.scalars(
            select(VendorIssue)
            .where(
                VendorIssue.organization_id == user.organization_id,
                VendorIssue.status.in_(["OPEN", "IN_REVIEW"]),
            )
            .order_by(VendorIssue.created_at)
        ).all()
    )


def get_issue(
    database: Session,
    *,
    user: User,
    issue_id: UUID,
) -> VendorIssue:
    issue = database.scalar(
        select(VendorIssue).where(
            VendorIssue.id == issue_id,
            VendorIssue.organization_id == user.organization_id,
        )
    )

    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor issue was not found.",
        )

    return issue


def assign_vendor_issue(
    database: Session,
    *,
    user: User,
    issue_id: UUID,
    payload: VendorIssueAssignRequest,
) -> VendorIssue:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Vendor-issue assignment access is required.",
    )

    issue = get_issue(database, user=user, issue_id=issue_id)
    assigned_user = database.scalar(
        select(User).where(
            User.id == payload.assigned_to_user_id,
            User.organization_id == user.organization_id,
        )
    )

    if assigned_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assigned user was not found.",
        )

    issue.assigned_to_user_id = assigned_user.id
    issue.status = "IN_REVIEW"

    database.add(
        VendorIssueAction(
            organization_id=user.organization_id,
            issue_id=issue.id,
            actor_user_id=user.id,
            action="ASSIGNED",
            note=payload.note,
            extra_data={"assigned_to_user_id": str(assigned_user.id)},
        )
    )
    notify(
        database,
        recipient_user_id=assigned_user.id,
        organization_id=user.organization_id,
        title="Vendor issue assigned",
        body=f"Vendor issue '{issue.title}' was assigned to you.",
        payload={
            "type": "VENDOR_ISSUE_ASSIGNED",
            "issue_id": str(issue.id),
        },
        dedupe_key=f"vendor-issue:{issue.id}:assigned:{assigned_user.id}",
    )

    database.commit()
    database.refresh(issue)
    return issue


def decide_vendor_issue(
    database: Session,
    *,
    user: User,
    issue_id: UUID,
    payload: VendorIssueDecisionRequest,
    resolved: bool,
) -> VendorIssue:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Vendor-issue decision access is required.",
    )

    issue = get_issue(database, user=user, issue_id=issue_id)

    if issue.status not in {"OPEN", "IN_REVIEW"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This vendor issue has already been decided.",
        )

    action = "RESOLVED" if resolved else "REJECTED"
    issue.status = action
    issue.resolution_note = payload.note.strip()
    issue.resolved_by_user_id = user.id
    issue.resolved_at = datetime.now(timezone.utc)

    database.add(
        VendorIssueAction(
            organization_id=user.organization_id,
            issue_id=issue.id,
            actor_user_id=user.id,
            action=action,
            note=payload.note.strip(),
        )
    )
    notify(
        database,
        recipient_user_id=issue.raised_by_user_id,
        organization_id=user.organization_id,
        title=f"Vendor issue {action.lower()}",
        body=f"Your vendor issue '{issue.title}' was {action.lower()}.",
        payload={
            "type": f"VENDOR_ISSUE_{action}",
            "issue_id": str(issue.id),
        },
        dedupe_key=f"vendor-issue:{issue.id}:{action.lower()}",
    )

    database.commit()
    database.refresh(issue)
    return issue


def list_vendor_issue_actions(
    database: Session,
    *,
    user: User,
    issue_id: UUID,
) -> list[VendorIssueAction]:
    issue = get_issue(database, user=user, issue_id=issue_id)

    if (
        issue.raised_by_user_id != user.id
        and not role_codes(database, user).intersection(OPS_ROLES)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this vendor issue.",
        )

    return list(
        database.scalars(
            select(VendorIssueAction)
            .where(VendorIssueAction.issue_id == issue.id)
            .order_by(VendorIssueAction.created_at)
        ).all()
    )


def create_labour_payment(
    database: Session,
    *,
    user: User,
    payload: LabourPaymentCreateRequest,
) -> ExternalLabourPayment:
    payment = ExternalLabourPayment(
        organization_id=user.organization_id,
        requested_by_user_id=user.id,
        status="PENDING_MD",
        **payload.model_dump(),
    )
    database.add(payment)
    database.flush()

    database.add(
        ExternalLabourPaymentAction(
            organization_id=user.organization_id,
            payment_id=payment.id,
            actor_user_id=user.id,
            action="REQUESTED",
            note="External labour payment requested.",
        )
    )

    database.commit()
    database.refresh(payment)
    return payment


def list_my_labour_payments(
    database: Session,
    *,
    user: User,
) -> list[ExternalLabourPayment]:
    return list(
        database.scalars(
            select(ExternalLabourPayment)
            .where(
                ExternalLabourPayment.organization_id
                == user.organization_id,
                ExternalLabourPayment.requested_by_user_id == user.id,
            )
            .order_by(ExternalLabourPayment.created_at.desc())
        ).all()
    )


def list_pending_labour_payments(
    database: Session,
    *,
    user: User,
) -> list[ExternalLabourPayment]:
    require_roles(
        database,
        user,
        PAYMENT_ROLES,
        "Labour-payment review access is required.",
    )

    return list(
        database.scalars(
            select(ExternalLabourPayment)
            .where(
                ExternalLabourPayment.organization_id
                == user.organization_id,
                ExternalLabourPayment.status.in_(
                    ["PENDING_MD", "APPROVED"]
                ),
            )
            .order_by(ExternalLabourPayment.created_at)
        ).all()
    )


def get_payment(
    database: Session,
    *,
    user: User,
    payment_id: UUID,
) -> ExternalLabourPayment:
    payment = database.scalar(
        select(ExternalLabourPayment).where(
            ExternalLabourPayment.id == payment_id,
            ExternalLabourPayment.organization_id
            == user.organization_id,
        )
    )

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="External labour payment was not found.",
        )

    return payment


def decide_labour_payment(
    database: Session,
    *,
    user: User,
    payment_id: UUID,
    note: str | None,
    approved: bool,
) -> ExternalLabourPayment:
    require_roles(
        database,
        user,
        MD_ROLES,
        "Only an MD can decide external labour payments.",
    )

    payment = get_payment(
        database,
        user=user,
        payment_id=payment_id,
    )

    if payment.status != "PENDING_MD":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending MD requests can be decided.",
        )

    action = "APPROVED" if approved else "REJECTED"
    payment.status = action
    payment.md_user_id = user.id
    payment.decided_at = datetime.now(timezone.utc)
    payment.decision_note = note

    database.add(
        ExternalLabourPaymentAction(
            organization_id=user.organization_id,
            payment_id=payment.id,
            actor_user_id=user.id,
            action=action,
            note=note,
        )
    )
    notify(
        database,
        recipient_user_id=payment.requested_by_user_id,
        organization_id=user.organization_id,
        title=f"External labour payment {action.lower()}",
        body=(
            f"Payment request for {payment.labour_name} "
            f"was {action.lower()}."
        ),
        payload={
            "type": f"LABOUR_PAYMENT_{action}",
            "payment_id": str(payment.id),
        },
        dedupe_key=f"labour-payment:{payment.id}:{action.lower()}",
    )

    database.commit()
    database.refresh(payment)
    return payment


def mark_labour_payment_paid(
    database: Session,
    *,
    user: User,
    payment_id: UUID,
    payload: LabourPaymentPaidRequest,
) -> ExternalLabourPayment:
    require_roles(
        database,
        user,
        PAYMENT_ROLES,
        "Labour-payment settlement access is required.",
    )

    payment = get_payment(
        database,
        user=user,
        payment_id=payment_id,
    )

    if payment.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only approved requests can be marked paid.",
        )

    payment.status = "PAID"
    payment.paid_by_user_id = user.id
    payment.paid_at = datetime.now(timezone.utc)
    payment.payment_reference = payload.payment_reference.strip()

    database.add(
        ExternalLabourPaymentAction(
            organization_id=user.organization_id,
            payment_id=payment.id,
            actor_user_id=user.id,
            action="PAID",
            note=payload.note,
            extra_data={
                "payment_reference": payment.payment_reference
            },
        )
    )
    notify(
        database,
        recipient_user_id=payment.requested_by_user_id,
        organization_id=user.organization_id,
        title="External labour payment completed",
        body=f"Payment for {payment.labour_name} was marked paid.",
        payload={
            "type": "LABOUR_PAYMENT_PAID",
            "payment_id": str(payment.id),
        },
        dedupe_key=f"labour-payment:{payment.id}:paid",
    )

    database.commit()
    database.refresh(payment)
    return payment


def list_labour_payment_actions(
    database: Session,
    *,
    user: User,
    payment_id: UUID,
) -> list[ExternalLabourPaymentAction]:
    payment = get_payment(
        database,
        user=user,
        payment_id=payment_id,
    )

    if (
        payment.requested_by_user_id != user.id
        and not role_codes(database, user).intersection(PAYMENT_ROLES)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this payment request.",
        )

    return list(
        database.scalars(
            select(ExternalLabourPaymentAction)
            .where(
                ExternalLabourPaymentAction.payment_id == payment.id
            )
            .order_by(ExternalLabourPaymentAction.created_at)
        ).all()
    )


def create_wing(
    database: Session,
    *,
    user: User,
    payload: WingCreateRequest,
) -> Wing:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Wing-directory management access is required.",
    )

    wing = Wing(
        organization_id=user.organization_id,
        **payload.model_dump(),
        status="ACTIVE",
    )
    database.add(wing)

    try:
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A wing with this code already exists.",
        ) from error

    database.refresh(wing)
    return wing


def list_wings(database: Session, *, user: User) -> list[Wing]:
    return list(
        database.scalars(
            select(Wing)
            .where(Wing.organization_id == user.organization_id)
            .order_by(Wing.name)
        ).all()
    )


def update_wing(
    database: Session,
    *,
    user: User,
    wing_id: UUID,
    payload: WingUpdateRequest,
) -> Wing:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Wing-directory management access is required.",
    )

    wing = database.scalar(
        select(Wing).where(
            Wing.id == wing_id,
            Wing.organization_id == user.organization_id,
        )
    )

    if wing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wing was not found.",
        )

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(wing, key, value)

    database.commit()
    database.refresh(wing)
    return wing


def create_wing_contact(
    database: Session,
    *,
    user: User,
    wing_id: UUID,
    payload: WingContactCreateRequest,
) -> WingContact:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Wing-directory management access is required.",
    )

    wing = database.scalar(
        select(Wing).where(
            Wing.id == wing_id,
            Wing.organization_id == user.organization_id,
        )
    )

    if wing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wing was not found.",
        )

    contact = WingContact(
        organization_id=user.organization_id,
        wing_id=wing.id,
        **payload.model_dump(),
    )
    database.add(contact)
    database.commit()
    database.refresh(contact)
    return contact


def list_wing_contacts(
    database: Session,
    *,
    user: User,
    wing_id: UUID,
) -> list[WingContact]:
    return list(
        database.scalars(
            select(WingContact)
            .where(
                WingContact.organization_id == user.organization_id,
                WingContact.wing_id == wing_id,
            )
            .order_by(WingContact.organization_name)
        ).all()
    )


def update_wing_contact(
    database: Session,
    *,
    user: User,
    contact_id: UUID,
    payload: WingContactUpdateRequest,
) -> WingContact:
    require_roles(
        database,
        user,
        OPS_ROLES,
        "Wing-directory management access is required.",
    )

    contact = database.scalar(
        select(WingContact).where(
            WingContact.id == contact_id,
            WingContact.organization_id == user.organization_id,
        )
    )

    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wing contact was not found.",
        )

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)

    database.commit()
    database.refresh(contact)
    return contact
