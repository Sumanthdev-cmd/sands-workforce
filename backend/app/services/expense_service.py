from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.associations import user_roles
from app.models.employee import Employee
from app.models.expense import ExpenseClaim, ExpenseClaimAction, ExpenseClaimItem
from app.models.role import Role
from app.models.user import User
from app.schemas.expense import (
    ClaimApprovalRequest,
    ClaimPaymentRequest,
    ClaimRejectRequest,
    ClaimVerificationRequest,
    ExpenseClaimCreateRequest,
)
from app.services.device_service import get_employee_for_user
from app.services.notification_service import queue_role_notifications, queue_user_notification


VERIFIER_ROLES = {"ADMIN", "GM", "MANAGER", "MD"}
APPROVER_ROLES = {"MD"}
PAYER_ROLES = {"ADMIN", "MD"}
EXPENSE_TIMEZONE = timezone(timedelta(hours=5, minutes=30))


def validate_expense_dates(items, *, now: datetime | None = None) -> None:
    """Apply the deadline to every line at creation and actual submission."""
    today = (now or datetime.now(timezone.utc)).astimezone(EXPENSE_TIMEZONE).date()
    earliest = today - timedelta(days=2)
    if not items:
        raise HTTPException(status_code=422, detail="At least one expense item is required.")
    for index, item in enumerate(items, start=1):
        if not earliest <= item.expense_date <= today:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Expense item {index} ({item.expense_date.isoformat()}): "
                    "claims must be submitted within two calendar days after the expense date "
                    "(India time). Future dates are not allowed. "
                    f"Allowed dates today: {earliest.isoformat()} to {today.isoformat()}."
                ),
            )


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
    allowed_roles: set[str],
    message: str,
) -> None:
    if not role_codes(database, user).intersection(allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )


def get_claim(
    database: Session,
    organization_id: UUID,
    claim_id: UUID,
) -> ExpenseClaim:
    claim = database.scalar(
        select(ExpenseClaim).where(
            ExpenseClaim.id == claim_id,
            ExpenseClaim.organization_id == organization_id,
        )
    )
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense claim was not found.",
        )
    return claim


def get_items(database: Session, claim_id: UUID) -> list[ExpenseClaimItem]:
    return list(
        database.scalars(
            select(ExpenseClaimItem)
            .where(ExpenseClaimItem.claim_id == claim_id)
            .order_by(
                ExpenseClaimItem.expense_date,
                ExpenseClaimItem.created_at,
            )
        ).all()
    )


def to_dict(
    claim: ExpenseClaim,
    items: list[ExpenseClaimItem],
    employee: Employee | None = None,
    employee_user: User | None = None,
) -> dict:
    data = {
        "id": claim.id,
        "employee_id": claim.employee_id,
        "claim_number": claim.claim_number,
        "claim_type": claim.claim_type,
        "title": claim.title,
        "purpose": claim.purpose,
        "travel_start_date": claim.travel_start_date,
        "travel_end_date": claim.travel_end_date,
        "origin": claim.origin,
        "destination": claim.destination,
        "currency": claim.currency,
        "claimed_amount": claim.claimed_amount,
        "verified_amount": claim.verified_amount,
        "approved_amount": claim.approved_amount,
        "status": claim.status,
        "evidence_urls": claim.evidence_urls,
        "submitted_at": claim.submitted_at,
        "verified_by_user_id": claim.verified_by_user_id,
        "verified_at": claim.verified_at,
        "verification_note": claim.verification_note,
        "approved_by_user_id": claim.approved_by_user_id,
        "approved_at": claim.approved_at,
        "approval_note": claim.approval_note,
        "rejected_by_user_id": claim.rejected_by_user_id,
        "rejected_at": claim.rejected_at,
        "rejection_reason": claim.rejection_reason,
        "paid_by_user_id": claim.paid_by_user_id,
        "paid_at": claim.paid_at,
        "payment_reference": claim.payment_reference,
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
        "items": items,
    }
    if employee is not None and employee_user is not None:
        data["employee_code"] = employee_user.employee_code
        data["employee_name"] = employee.full_name
    return data


def create_claim(
    database: Session,
    user: User,
    payload: ExpenseClaimCreateRequest,
) -> dict:
    employee = get_employee_for_user(database, user)
    validate_expense_dates(payload.items)
    claim = ExpenseClaim(
        organization_id=user.organization_id,
        employee_id=employee.id,
        claim_number=(
            f"EXP-{datetime.now(timezone.utc):%Y%m}-"
            f"{uuid4().hex[:8].upper()}"
        ),
        claim_type=payload.claim_type,
        title=payload.title.strip(),
        purpose=payload.purpose.strip(),
        travel_start_date=payload.travel_start_date,
        travel_end_date=payload.travel_end_date,
        origin=payload.origin,
        destination=payload.destination,
        currency=payload.currency,
        status="DRAFT",
        evidence_urls=payload.evidence_urls,
        claimed_amount=0,
    )
    database.add(claim)
    database.flush()

    items: list[ExpenseClaimItem] = []
    total = 0.0
    for input_item in payload.items:
        item = ExpenseClaimItem(
            organization_id=user.organization_id,
            claim_id=claim.id,
            expense_date=input_item.expense_date,
            category=input_item.category,
            description=input_item.description.strip(),
            quantity=input_item.quantity,
            rate=input_item.rate,
            amount=round(float(input_item.amount or 0), 2),
            evidence_urls=input_item.evidence_urls,
        )
        database.add(item)
        items.append(item)
        total += item.amount

    claim.claimed_amount = round(total, 2)
    database.add(
        ExpenseClaimAction(
            organization_id=user.organization_id,
            claim_id=claim.id,
            actor_user_id=user.id,
            action="CREATED",
            note="Expense claim created as draft.",
            amount=claim.claimed_amount,
        )
    )
    database.commit()
    database.refresh(claim)
    for item in items:
        database.refresh(item)
    return to_dict(claim, items)


def list_my_claims(database: Session, user: User) -> list[dict]:
    employee = get_employee_for_user(database, user)
    claims = list(
        database.scalars(
            select(ExpenseClaim)
            .where(
                ExpenseClaim.organization_id == user.organization_id,
                ExpenseClaim.employee_id == employee.id,
            )
            .order_by(ExpenseClaim.created_at.desc())
        ).all()
    )
    return [to_dict(claim, get_items(database, claim.id)) for claim in claims]


def read_claim(database: Session, user: User, claim_id: UUID) -> dict:
    claim = get_claim(database, user.organization_id, claim_id)
    employee = database.get(Employee, claim.employee_id)
    own_employee = database.scalar(
        select(Employee).where(
            Employee.user_id == user.id,
            Employee.organization_id == user.organization_id,
        )
    )
    is_owner = own_employee is not None and own_employee.id == claim.employee_id
    if not is_owner:
        require_roles(
            database,
            user,
            VERIFIER_ROLES | APPROVER_ROLES | PAYER_ROLES,
            "Expense review access is required.",
        )
    employee_user = database.get(User, employee.user_id)
    return to_dict(
        claim,
        get_items(database, claim.id),
        employee,
        employee_user,
    )


def submit_claim(database: Session, user: User, claim_id: UUID) -> dict:
    employee = get_employee_for_user(database, user)
    claim = get_claim(database, user.organization_id, claim_id)
    if claim.employee_id != employee.id:
        raise HTTPException(status_code=403, detail="This claim belongs to another employee.")
    if claim.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only draft claims can be submitted.")
    if claim.claimed_amount <= 0:
        raise HTTPException(status_code=422, detail="Claim amount must be greater than zero.")

    items = get_items(database, claim.id)
    validate_expense_dates(items)
    claim.status = "SUBMITTED"
    claim.submitted_at = datetime.now(timezone.utc)
    database.add(
        ExpenseClaimAction(
            organization_id=user.organization_id,
            claim_id=claim.id,
            actor_user_id=user.id,
            action="SUBMITTED",
            note="Submitted for verification.",
            amount=claim.claimed_amount,
        )
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes=VERIFIER_ROLES,
        title="Expense claim awaiting verification",
        body=(
            f"{user.employee_code} submitted {claim.claim_number} - {claim.title} "
            f"for {claim.currency} {claim.claimed_amount:,.2f}."
        ),
        dedupe_prefix=f"expense:{claim.id}:submitted",
        route=f"/module/expenses?queue=1&claim={claim.id}",
        module="expenses",
        event="EXPENSE_SUBMITTED",
        entity_id=claim.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(claim)
    return to_dict(claim, get_items(database, claim.id))


def list_pending_claims(database: Session, user: User) -> list[dict]:
    require_roles(
        database,
        user,
        VERIFIER_ROLES | APPROVER_ROLES | PAYER_ROLES,
        "Expense review access is required.",
    )
    rows = database.execute(
        select(ExpenseClaim, Employee, User)
        .join(Employee, ExpenseClaim.employee_id == Employee.id)
        .join(User, Employee.user_id == User.id)
        .where(
            ExpenseClaim.organization_id == user.organization_id,
            ExpenseClaim.status.in_(["SUBMITTED", "VERIFIED", "APPROVED"]),
        )
        .order_by(ExpenseClaim.submitted_at)
    ).all()
    return [
        to_dict(claim, get_items(database, claim.id), employee, employee_user)
        for claim, employee, employee_user in rows
    ]


def verify_claim(
    database: Session,
    user: User,
    claim_id: UUID,
    payload: ClaimVerificationRequest,
) -> dict:
    require_roles(database, user, VERIFIER_ROLES, "Expense verification access is required.")
    claim = get_claim(database, user.organization_id, claim_id)
    if claim.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Only submitted claims can be verified.")
    amount = claim.claimed_amount if payload.verified_amount is None else round(payload.verified_amount, 2)
    if amount > claim.claimed_amount:
        raise HTTPException(status_code=422, detail="Verified amount cannot exceed claimed amount.")

    claim.status = "VERIFIED"
    claim.verified_amount = amount
    claim.verified_by_user_id = user.id
    claim.verified_at = datetime.now(timezone.utc)
    claim.verification_note = payload.note
    database.add(
        ExpenseClaimAction(
            organization_id=user.organization_id,
            claim_id=claim.id,
            actor_user_id=user.id,
            action="VERIFIED",
            note=payload.note,
            amount=amount,
        )
    )
    employee = database.get(Employee, claim.employee_id)
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id if employee else None,
        title="Expense claim verified",
        body=(
            f"Your claim {claim.claim_number} was verified for "
            f"{claim.currency} {amount:,.2f}."
        ),
        dedupe_key=f"expense:{claim.id}:verified",
        route=f"/module/expenses?claim={claim.id}",
        module="expenses",
        event="EXPENSE_VERIFIED",
        entity_id=claim.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes=APPROVER_ROLES,
        title="Expense claim awaiting MD approval",
        body=(
            f"{claim.claim_number} - {claim.title} was verified for "
            f"{claim.currency} {amount:,.2f}."
        ),
        dedupe_prefix=f"expense:{claim.id}:awaiting-md",
        route=f"/module/expenses?queue=1&claim={claim.id}",
        module="expenses",
        event="EXPENSE_AWAITING_MD_APPROVAL",
        entity_id=claim.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(claim)
    return to_dict(claim, get_items(database, claim.id))


def approve_claim(
    database: Session,
    user: User,
    claim_id: UUID,
    payload: ClaimApprovalRequest,
) -> dict:
    require_roles(database, user, APPROVER_ROLES, "Only an MD can approve expense claims.")
    claim = get_claim(database, user.organization_id, claim_id)
    if claim.status != "VERIFIED":
        raise HTTPException(status_code=409, detail="Only verified claims can be approved.")
    verified = claim.verified_amount or 0
    amount = verified if payload.approved_amount is None else round(payload.approved_amount, 2)
    if amount > verified:
        raise HTTPException(status_code=422, detail="Approved amount cannot exceed verified amount.")

    claim.status = "APPROVED"
    claim.approved_amount = amount
    claim.approved_by_user_id = user.id
    claim.approved_at = datetime.now(timezone.utc)
    claim.approval_note = payload.note
    database.add(
        ExpenseClaimAction(
            organization_id=user.organization_id,
            claim_id=claim.id,
            actor_user_id=user.id,
            action="APPROVED",
            note=payload.note,
            amount=amount,
        )
    )
    employee = database.get(Employee, claim.employee_id)
    requester_user_id = employee.user_id if employee else None
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=requester_user_id,
        title="Expense claim approved",
        body=(
            f"Your claim {claim.claim_number} was approved for "
            f"{claim.currency} {amount:,.2f}."
        ),
        dedupe_key=f"expense:{claim.id}:approved:requester",
        route=f"/module/expenses?claim={claim.id}",
        module="expenses",
        event="EXPENSE_APPROVED",
        entity_id=claim.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes=PAYER_ROLES,
        title="Approved expense awaiting payment",
        body=(
            f"{claim.claim_number} - {claim.title} is approved for payment: "
            f"{claim.currency} {amount:,.2f}."
        ),
        dedupe_prefix=f"expense:{claim.id}:awaiting-payment",
        route=f"/module/expenses?queue=1&claim={claim.id}",
        module="expenses",
        event="EXPENSE_AWAITING_PAYMENT",
        entity_id=claim.id,
        exclude_user_ids={user.id},
    )
    database.commit()
    database.refresh(claim)
    return to_dict(claim, get_items(database, claim.id))


def reject_claim(
    database: Session,
    user: User,
    claim_id: UUID,
    payload: ClaimRejectRequest,
) -> dict:
    require_roles(
        database,
        user,
        VERIFIER_ROLES | APPROVER_ROLES,
        "Expense rejection access is required.",
    )
    claim = get_claim(database, user.organization_id, claim_id)
    if claim.status not in {"SUBMITTED", "VERIFIED"}:
        raise HTTPException(status_code=409, detail="Only submitted or verified claims can be rejected.")

    claim.status = "REJECTED"
    claim.rejected_by_user_id = user.id
    claim.rejected_at = datetime.now(timezone.utc)
    claim.rejection_reason = payload.reason.strip()
    database.add(
        ExpenseClaimAction(
            organization_id=user.organization_id,
            claim_id=claim.id,
            actor_user_id=user.id,
            action="REJECTED",
            note=payload.reason.strip(),
        )
    )
    employee = database.get(Employee, claim.employee_id)
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id if employee else None,
        title="Expense claim rejected",
        body=(
            f"Your claim {claim.claim_number} was rejected by {user.employee_code}: "
            f"{claim.rejection_reason}"
        ),
        dedupe_key=f"expense:{claim.id}:rejected",
        route=f"/module/expenses?claim={claim.id}",
        module="expenses",
        event="EXPENSE_REJECTED",
        entity_id=claim.id,
    )
    database.commit()
    database.refresh(claim)
    return to_dict(claim, get_items(database, claim.id))


def mark_claim_paid(
    database: Session,
    user: User,
    claim_id: UUID,
    payload: ClaimPaymentRequest,
) -> dict:
    require_roles(database, user, PAYER_ROLES, "Expense payment access is required.")
    claim = get_claim(database, user.organization_id, claim_id)
    if claim.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Only approved claims can be marked paid.")

    claim.status = "PAID"
    claim.paid_by_user_id = user.id
    claim.paid_at = datetime.now(timezone.utc)
    claim.payment_reference = payload.payment_reference.strip()
    database.add(
        ExpenseClaimAction(
            organization_id=user.organization_id,
            claim_id=claim.id,
            actor_user_id=user.id,
            action="PAID",
            note=payload.note,
            amount=claim.approved_amount,
            extra_data={"payment_reference": claim.payment_reference},
        )
    )
    employee = database.get(Employee, claim.employee_id)
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=employee.user_id if employee else None,
        title="Expense claim paid",
        body=(
            f"Payment was recorded for {claim.claim_number}. Reference: "
            f"{claim.payment_reference}."
        ),
        dedupe_key=f"expense:{claim.id}:paid",
        route=f"/module/expenses?claim={claim.id}",
        module="expenses",
        event="EXPENSE_PAID",
        entity_id=claim.id,
    )
    database.commit()
    database.refresh(claim)
    return to_dict(claim, get_items(database, claim.id))


def list_actions(
    database: Session,
    user: User,
    claim_id: UUID,
) -> list[ExpenseClaimAction]:
    read_claim(database, user, claim_id)
    return list(
        database.scalars(
            select(ExpenseClaimAction)
            .where(ExpenseClaimAction.claim_id == claim_id)
            .order_by(ExpenseClaimAction.created_at)
        ).all()
    )
