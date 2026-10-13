from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AccountSheetVerification,
    AccountSheetVerificationItem,
    DocumentRecord,
    Employee,
    Role,
    User,
    user_roles,
)
from app.schemas.account_sheet_verification import (
    AccountSheetResolveRequest,
    AccountSheetSecretaryReviewRequest,
    AccountSheetVerificationCreate,
)
from app.services.device_service import get_employee_for_user
from app.services.notification_service import (
    queue_role_notifications,
    queue_user_notification,
)


ACCOUNTS_MANAGER_ROLE = "ACCOUNTS_MANAGER"
ACCOUNTS_SECRETARY_ROLE = "ACCOUNTS_SECRETARY"
ADMIN_ROLE = "ADMIN"
MD_ROLE = "MD"

VIEW_ROLES = {
    ACCOUNTS_MANAGER_ROLE,
    ACCOUNTS_SECRETARY_ROLE,
    ADMIN_ROLE,
    MD_ROLE,
}

ALLOWED_EVIDENCE_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
}


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_role(
    database: Session,
    user: User,
    allowed: set[str],
    message: str,
) -> set[str]:
    roles = role_codes(database, user)
    if not roles.intersection(allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )
    return roles


def _organization_today(user: User):
    timezone_name = (
        getattr(getattr(user, "organization", None), "timezone", None)
        or "Asia/Kolkata"
    )
    try:
        local_timezone = ZoneInfo(timezone_name)
    except Exception:
        local_timezone = ZoneInfo("Asia/Kolkata")
    return datetime.now(local_timezone).date()


def _report_options():
    return (
        selectinload(AccountSheetVerification.accounts_manager).selectinload(
            Employee.user
        ),
        selectinload(AccountSheetVerification.items).selectinload(
            AccountSheetVerificationItem.discrepancy_document
        ),
    )


def _manager_identity(report: AccountSheetVerification) -> tuple[str, str]:
    employee = report.accounts_manager
    code = getattr(getattr(employee, "user", None), "employee_code", None)
    return code or "Unknown", employee.full_name if employee else "Unknown"


def _can_resolve(
    item: AccountSheetVerificationItem,
    roles: set[str],
) -> bool:
    if item.issue_status != "OPEN":
        return False
    return bool(
        (ADMIN_ROLE in roles and item.admin_escalated_at is not None)
        or (MD_ROLE in roles and item.md_escalated_at is not None)
    )


def item_payload(
    item: AccountSheetVerificationItem,
    roles: set[str],
) -> dict:
    report = item.verification
    manager_code, manager_name = _manager_identity(report)
    document = item.discrepancy_document

    return {
        "id": item.id,
        "report_id": report.id,
        "verification_date": report.verification_date,
        "declared_sheet_count": report.declared_sheet_count,
        "accounts_manager_employee_id": report.accounts_manager_employee_id,
        "accounts_manager_employee_code": manager_code,
        "accounts_manager_name": manager_name,
        "sheet_name": item.sheet_name,
        "sheet_generated_on": item.sheet_generated_on,
        "has_discrepancy": item.has_discrepancy,
        "discrepancy_reason": item.discrepancy_reason,
        "discrepancy_document_id": item.discrepancy_document_id,
        "discrepancy_document_name": (
            document.file_name if document is not None else None
        ),
        "discrepancy_document_content_type": (
            document.content_type if document is not None else None
        ),
        "secretary_status": item.secretary_status,
        "secretary_reviewed_by_user_id": item.secretary_reviewed_by_user_id,
        "secretary_reviewed_at": item.secretary_reviewed_at,
        "secretary_note": item.secretary_note,
        "issue_status": item.issue_status,
        "issue_raised_at": item.issue_raised_at,
        "admin_escalated_at": item.admin_escalated_at,
        "md_escalated_at": item.md_escalated_at,
        "resolved_by_user_id": item.resolved_by_user_id,
        "resolved_at": item.resolved_at,
        "resolution_note": item.resolution_note,
        "resolution_role": item.resolution_role,
        "can_secretary_review": (
            ACCOUNTS_SECRETARY_ROLE in roles
            and item.secretary_status == "PENDING"
        ),
        "can_resolve": _can_resolve(item, roles),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def report_payload(
    report: AccountSheetVerification,
    roles: set[str],
) -> dict:
    manager_code, manager_name = _manager_identity(report)
    items = list(report.items)

    return {
        "id": report.id,
        "submission_id": report.submission_id,
        "verification_date": report.verification_date,
        "declared_sheet_count": report.declared_sheet_count,
        "actual_sheet_count": len(items),
        "discrepancy_count": sum(
            1 for item in items if item.has_discrepancy
        ),
        "open_issue_count": sum(
            1 for item in items if item.issue_status == "OPEN"
        ),
        "notes": report.notes,
        "status": report.status,
        "accounts_manager_employee_id": report.accounts_manager_employee_id,
        "accounts_manager_employee_code": manager_code,
        "accounts_manager_name": manager_name,
        "submitted_by_user_id": report.submitted_by_user_id,
        "submitted_at": report.submitted_at,
        "items": [item_payload(item, roles) for item in items],
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }


def _get_report_record(
    database: Session,
    *,
    organization_id: UUID,
    report_id: UUID,
) -> AccountSheetVerification:
    report = database.scalar(
        select(AccountSheetVerification)
        .where(
            AccountSheetVerification.id == report_id,
            AccountSheetVerification.organization_id == organization_id,
        )
        .options(*_report_options())
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily sheet-verification report was not found.",
        )
    return report


def _ensure_report_access(
    database: Session,
    *,
    user: User,
    report: AccountSheetVerification,
    roles: set[str],
) -> None:
    if roles.intersection({ACCOUNTS_SECRETARY_ROLE, ADMIN_ROLE, MD_ROLE}):
        return
    employee = get_employee_for_user(database, user)
    if report.accounts_manager_employee_id != employee.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can view only your own sheet-verification reports.",
        )


def get_report(
    database: Session,
    *,
    user: User,
    report_id: UUID,
) -> dict:
    roles = require_role(
        database,
        user,
        VIEW_ROLES,
        "Sheet verification is restricted to Accounts and authorized management.",
    )
    report = _get_report_record(
        database,
        organization_id=user.organization_id,
        report_id=report_id,
    )
    _ensure_report_access(
        database,
        user=user,
        report=report,
        roles=roles,
    )
    return report_payload(report, roles)


def list_reports(database: Session, *, user: User) -> list[dict]:
    roles = require_role(
        database,
        user,
        VIEW_ROLES,
        "Sheet verification is restricted to Accounts and authorized management.",
    )
    statement = (
        select(AccountSheetVerification)
        .where(AccountSheetVerification.organization_id == user.organization_id)
        .options(*_report_options())
        .order_by(
            AccountSheetVerification.verification_date.desc(),
            AccountSheetVerification.submitted_at.desc(),
        )
        .limit(250)
    )

    if not roles.intersection({ACCOUNTS_SECRETARY_ROLE, ADMIN_ROLE, MD_ROLE}):
        employee = get_employee_for_user(database, user)
        statement = statement.where(
            AccountSheetVerification.accounts_manager_employee_id == employee.id
        )

    return [
        report_payload(report, roles)
        for report in database.scalars(statement).unique().all()
    ]


def _validate_evidence_document(
    database: Session,
    *,
    user: User,
    employee: Employee,
    document_id: UUID,
) -> None:
    document = database.scalar(
        select(DocumentRecord).where(
            DocumentRecord.id == document_id,
            DocumentRecord.organization_id == user.organization_id,
        )
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The uploaded discrepancy sheet was not found.",
        )
    if document.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Complete the discrepancy-sheet upload before submitting.",
        )
    if (
        document.uploaded_by_user_id != user.id
        or document.owner_type != "ACCOUNT_SHEET"
        or document.owner_id != employee.id
        or document.category != "ACCOUNT_SHEET_DISCREPANCY"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The discrepancy attachment does not belong to this submission.",
        )
    content_type = (document.content_type or "").lower()
    if not (
        content_type.startswith("image/")
        or content_type in ALLOWED_EVIDENCE_CONTENT_TYPES
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Discrepancy evidence must be a PDF, image, Excel file, or CSV.",
        )
    already_used = database.scalar(
        select(AccountSheetVerificationItem.id).where(
            AccountSheetVerificationItem.discrepancy_document_id == document_id
        )
    )
    if already_used is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A discrepancy attachment cannot be reused for another sheet.",
        )


def create_report(
    database: Session,
    *,
    user: User,
    payload: AccountSheetVerificationCreate,
) -> dict:
    require_role(
        database,
        user,
        {ACCOUNTS_MANAGER_ROLE},
        "Only an Accounts Manager can submit the daily sheet-verification report.",
    )
    employee = get_employee_for_user(database, user)

    if payload.verification_date > _organization_today(user):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Verification date cannot be in the future.",
        )

    existing_submission = database.scalar(
        select(AccountSheetVerification)
        .where(
            AccountSheetVerification.organization_id == user.organization_id,
            AccountSheetVerification.submission_id == payload.submission_id,
        )
        .options(*_report_options())
    )
    if existing_submission is not None:
        if existing_submission.accounts_manager_employee_id != employee.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This submission identifier is already in use.",
            )
        return report_payload(
            existing_submission,
            role_codes(database, user),
        )

    existing_day = database.scalar(
        select(AccountSheetVerification.id).where(
            AccountSheetVerification.organization_id == user.organization_id,
            AccountSheetVerification.accounts_manager_employee_id == employee.id,
            AccountSheetVerification.verification_date
            == payload.verification_date,
        )
    )
    if existing_day is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You have already submitted the daily sheet-verification report "
                "for this date."
            ),
        )

    for item in payload.items:
        if item.sheet_generated_on > payload.verification_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"{item.sheet_name}: generated date cannot be later than "
                    "the verification date."
                ),
            )

    document_ids = [
        item.discrepancy_document_id
        for item in payload.items
        if item.discrepancy_document_id is not None
    ]
    if len(set(document_ids)) != len(document_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each discrepant sheet requires its own uploaded attachment.",
        )
    for document_id in document_ids:
        _validate_evidence_document(
            database,
            user=user,
            employee=employee,
            document_id=document_id,
        )

    now = datetime.now(timezone.utc)
    has_issues = any(item.has_discrepancy for item in payload.items)
    report = AccountSheetVerification(
        id=uuid4(),
        organization_id=user.organization_id,
        submission_id=payload.submission_id,
        accounts_manager_employee_id=employee.id,
        verification_date=payload.verification_date,
        declared_sheet_count=payload.declared_sheet_count,
        notes=payload.notes,
        status="ISSUES_OPEN" if has_issues else "PENDING_SECRETARY",
        submitted_by_user_id=user.id,
        submitted_at=now,
    )
    database.add(report)

    for submitted_item in payload.items:
        database.add(
            AccountSheetVerificationItem(
                organization_id=user.organization_id,
                verification_id=report.id,
                sheet_name=submitted_item.sheet_name,
                sheet_generated_on=submitted_item.sheet_generated_on,
                has_discrepancy=submitted_item.has_discrepancy,
                discrepancy_reason=submitted_item.discrepancy_reason,
                discrepancy_document_id=submitted_item.discrepancy_document_id,
                secretary_status="PENDING",
                issue_status="OPEN" if submitted_item.has_discrepancy else "NONE",
                issue_raised_at=now if submitted_item.has_discrepancy else None,
            )
        )

    try:
        database.flush()
        queue_role_notifications(
            database,
            organization_id=user.organization_id,
            role_codes={ACCOUNTS_SECRETARY_ROLE},
            title="Daily sheet verification requires review",
            body=(
                f"{user.employee_code} submitted {payload.declared_sheet_count} "
                f"sheet(s) for {payload.verification_date.isoformat()}. "
                f"Discrepancies reported: "
                f"{sum(1 for item in payload.items if item.has_discrepancy)}."
            ),
            dedupe_prefix=f"account-sheet-report:{report.id}:secretary-review",
            route=f"/module/sheet-verification?report={report.id}&queue=1",
            module="sheet-verification",
            event="ACCOUNT_SHEET_REVIEW_REQUIRED",
            entity_id=report.id,
        )
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A daily sheet-verification report for this date already exists, "
                "or this submission was already processed."
            ),
        ) from error

    saved = _get_report_record(
        database,
        organization_id=user.organization_id,
        report_id=report.id,
    )
    return report_payload(saved, role_codes(database, user))


def _get_item_record(
    database: Session,
    *,
    organization_id: UUID,
    item_id: UUID,
    lock: bool = False,
) -> AccountSheetVerificationItem:
    statement = (
        select(AccountSheetVerificationItem)
        .where(
            AccountSheetVerificationItem.id == item_id,
            AccountSheetVerificationItem.organization_id == organization_id,
        )
        .options(
            selectinload(AccountSheetVerificationItem.discrepancy_document),
            selectinload(AccountSheetVerificationItem.verification)
            .selectinload(AccountSheetVerification.accounts_manager)
            .selectinload(Employee.user),
        )
    )
    if lock:
        statement = statement.with_for_update()
    item = database.scalar(statement)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sheet-verification entry was not found.",
        )
    return item


def list_review_queue(database: Session, *, user: User) -> list[dict]:
    roles = require_role(
        database,
        user,
        {ACCOUNTS_SECRETARY_ROLE},
        "Only the Accounts Secretary can open the sheet-review queue.",
    )
    statement = (
        select(AccountSheetVerificationItem)
        .where(
            AccountSheetVerificationItem.organization_id == user.organization_id,
            AccountSheetVerificationItem.secretary_status == "PENDING",
        )
        .options(
            selectinload(AccountSheetVerificationItem.discrepancy_document),
            selectinload(AccountSheetVerificationItem.verification)
            .selectinload(AccountSheetVerification.accounts_manager)
            .selectinload(Employee.user),
        )
        .order_by(AccountSheetVerificationItem.created_at)
        .limit(500)
    )
    return [
        item_payload(item, roles)
        for item in database.scalars(statement).unique().all()
    ]


def list_open_issues(database: Session, *, user: User) -> list[dict]:
    roles = require_role(
        database,
        user,
        VIEW_ROLES,
        "Sheet verification is restricted to Accounts and authorized management.",
    )
    conditions = []

    if ACCOUNTS_SECRETARY_ROLE in roles:
        conditions.append(AccountSheetVerificationItem.issue_status == "OPEN")
    if ACCOUNTS_MANAGER_ROLE in roles:
        employee = get_employee_for_user(database, user)
        conditions.append(
            (
                AccountSheetVerification.accounts_manager_employee_id == employee.id
            )
            & (AccountSheetVerificationItem.issue_status == "OPEN")
        )
    if ADMIN_ROLE in roles:
        conditions.append(
            (AccountSheetVerificationItem.issue_status == "OPEN")
            & (AccountSheetVerificationItem.admin_escalated_at.is_not(None))
        )
    if MD_ROLE in roles:
        conditions.append(
            (AccountSheetVerificationItem.issue_status == "OPEN")
            & (AccountSheetVerificationItem.md_escalated_at.is_not(None))
        )

    statement = (
        select(AccountSheetVerificationItem)
        .join(
            AccountSheetVerification,
            AccountSheetVerification.id
            == AccountSheetVerificationItem.verification_id,
        )
        .where(
            AccountSheetVerificationItem.organization_id == user.organization_id,
            or_(*conditions),
        )
        .options(
            selectinload(AccountSheetVerificationItem.discrepancy_document),
            selectinload(AccountSheetVerificationItem.verification)
            .selectinload(AccountSheetVerification.accounts_manager)
            .selectinload(Employee.user),
        )
        .order_by(AccountSheetVerificationItem.issue_raised_at)
        .limit(500)
    )
    return [
        item_payload(item, roles)
        for item in database.scalars(statement).unique().all()
    ]


def _refresh_report_status(
    database: Session,
    report: AccountSheetVerification,
) -> None:
    rows = database.execute(
        select(
            AccountSheetVerificationItem.secretary_status,
            AccountSheetVerificationItem.issue_status,
        ).where(
            AccountSheetVerificationItem.verification_id == report.id
        )
    ).all()
    if any(issue_status == "OPEN" for _, issue_status in rows):
        report.status = "ISSUES_OPEN"
    elif any(secretary_status == "PENDING" for secretary_status, _ in rows):
        report.status = "PENDING_SECRETARY"
    else:
        report.status = "COMPLETED"


def secretary_review_item(
    database: Session,
    *,
    user: User,
    item_id: UUID,
    payload: AccountSheetSecretaryReviewRequest,
) -> dict:
    roles = require_role(
        database,
        user,
        {ACCOUNTS_SECRETARY_ROLE},
        "Only the Accounts Secretary can verify sheet entries.",
    )
    item = _get_item_record(
        database,
        organization_id=user.organization_id,
        item_id=item_id,
        lock=True,
    )
    if item.secretary_status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This sheet entry has already been reviewed.",
        )

    if item.has_discrepancy and payload.decision not in {"CONFIRMED", "NOT_FOUND"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A discrepant sheet must be confirmed or marked not found.",
        )
    if not item.has_discrepancy and payload.decision != "VERIFIED":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A sheet without a reported discrepancy can only be verified.",
        )
    if item.has_discrepancy and not payload.note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Accounts Secretary remarks are required for a discrepancy decision.",
        )

    now = datetime.now(timezone.utc)
    item.secretary_status = payload.decision
    item.secretary_reviewed_by_user_id = user.id
    item.secretary_reviewed_at = now
    item.secretary_note = payload.note

    route = f"/module/sheet-verification?item={item.id}&queue=1"
    if payload.decision == "CONFIRMED" and item.issue_status == "OPEN":
        if item.admin_escalated_at is None:
            item.admin_escalated_at = now
            manager_code, _ = _manager_identity(item.verification)
            queue_role_notifications(
                database,
                organization_id=user.organization_id,
                role_codes={ADMIN_ROLE},
                title="Accounts discrepancy confirmed",
                body=(
                    f"Accounts Secretary confirmed a discrepancy in "
                    f"'{item.sheet_name}' reported by "
                    f"{manager_code}."
                ),
                dedupe_prefix=f"account-sheet-item:{item.id}:admin-confirmed",
                route=route,
                module="sheet-verification",
                event="ACCOUNT_SHEET_ADMIN_ESCALATION",
                entity_id=item.id,
            )
    elif payload.decision == "NOT_FOUND" and item.issue_status == "OPEN":
        item.issue_status = "RESOLVED"
        item.resolved_by_user_id = user.id
        item.resolved_at = now
        item.resolution_note = payload.note
        item.resolution_role = ACCOUNTS_SECRETARY_ROLE

    database.flush()
    _refresh_report_status(database, item.verification)

    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=item.verification.submitted_by_user_id,
        title="Sheet verification reviewed",
        body=(
            f"Accounts Secretary marked '{item.sheet_name}' as "
            f"{payload.decision.replace('_', ' ').lower()}."
        ),
        dedupe_key=f"account-sheet-item:{item.id}:secretary:{payload.decision}",
        route=route,
        module="sheet-verification",
        event="ACCOUNT_SHEET_SECRETARY_REVIEWED",
        entity_id=item.id,
    )
    database.commit()

    saved = _get_item_record(
        database,
        organization_id=user.organization_id,
        item_id=item.id,
    )
    return item_payload(saved, roles)


def resolve_issue(
    database: Session,
    *,
    user: User,
    item_id: UUID,
    payload: AccountSheetResolveRequest,
) -> dict:
    roles = require_role(
        database,
        user,
        {ADMIN_ROLE, MD_ROLE},
        "Only Admin or MD can resolve an escalated accounts discrepancy.",
    )
    item = _get_item_record(
        database,
        organization_id=user.organization_id,
        item_id=item_id,
        lock=True,
    )
    if item.issue_status != "OPEN":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This discrepancy is already resolved.",
        )

    resolution_role = None
    if MD_ROLE in roles and item.md_escalated_at is not None:
        resolution_role = MD_ROLE
    elif ADMIN_ROLE in roles and item.admin_escalated_at is not None:
        resolution_role = ADMIN_ROLE

    if resolution_role is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This issue has not yet reached your escalation level.",
        )

    now = datetime.now(timezone.utc)
    item.issue_status = "RESOLVED"
    item.resolved_by_user_id = user.id
    item.resolved_at = now
    item.resolution_note = payload.resolution_note
    item.resolution_role = resolution_role
    database.flush()
    _refresh_report_status(database, item.verification)

    route = f"/module/sheet-verification?item={item.id}"
    queue_user_notification(
        database,
        organization_id=user.organization_id,
        recipient_user_id=item.verification.submitted_by_user_id,
        title="Accounts discrepancy resolved",
        body=(
            f"'{item.sheet_name}' was resolved by {resolution_role}. "
            f"Resolution: {payload.resolution_note}"
        ),
        dedupe_key=f"account-sheet-item:{item.id}:resolved:manager",
        route=route,
        module="sheet-verification",
        event="ACCOUNT_SHEET_RESOLVED",
        entity_id=item.id,
    )
    queue_role_notifications(
        database,
        organization_id=user.organization_id,
        role_codes={ACCOUNTS_SECRETARY_ROLE},
        title="Accounts discrepancy resolved",
        body=f"'{item.sheet_name}' was resolved by {resolution_role}.",
        dedupe_prefix=f"account-sheet-item:{item.id}:resolved:secretary",
        route=route,
        module="sheet-verification",
        event="ACCOUNT_SHEET_RESOLVED",
        entity_id=item.id,
        exclude_user_ids={user.id},
    )
    if resolution_role == MD_ROLE:
        queue_role_notifications(
            database,
            organization_id=user.organization_id,
            role_codes={ADMIN_ROLE},
            title="MD resolved accounts discrepancy",
            body=f"MD resolved the issue in '{item.sheet_name}'.",
            dedupe_prefix=f"account-sheet-item:{item.id}:resolved:admin",
            route=route,
            module="sheet-verification",
            event="ACCOUNT_SHEET_RESOLVED",
            entity_id=item.id,
            exclude_user_ids={user.id},
        )
    database.commit()

    saved = _get_item_record(
        database,
        organization_id=user.organization_id,
        item_id=item.id,
    )
    return item_payload(saved, roles)


def enqueue_account_sheet_escalations(database: Session) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    admin_cutoff = now - timedelta(hours=6)
    md_cutoff = now - timedelta(hours=24)
    rows = list(
        database.scalars(
            select(AccountSheetVerificationItem)
            .where(
                AccountSheetVerificationItem.has_discrepancy.is_(True),
                AccountSheetVerificationItem.issue_status == "OPEN",
                AccountSheetVerificationItem.issue_raised_at.is_not(None),
            )
            .options(
                selectinload(AccountSheetVerificationItem.verification)
                .selectinload(AccountSheetVerification.accounts_manager)
                .selectinload(Employee.user)
            )
            .order_by(AccountSheetVerificationItem.issue_raised_at)
            .limit(1000)
        ).unique().all()
    )

    admin_escalations = 0
    md_escalations = 0

    for item in rows:
        manager_code, _ = _manager_identity(item.verification)
        route = f"/module/sheet-verification?item={item.id}&queue=1"

        if item.admin_escalated_at is None and item.issue_raised_at <= admin_cutoff:
            queue_role_notifications(
                database,
                organization_id=item.organization_id,
                role_codes={ADMIN_ROLE},
                title="Accounts discrepancy unresolved for 6 hours",
                body=(
                    f"'{item.sheet_name}' raised by {manager_code} remains "
                    "unresolved six hours after it was reported."
                ),
                dedupe_prefix=f"account-sheet-item:{item.id}:admin-6h",
                route=route,
                module="sheet-verification",
                event="ACCOUNT_SHEET_ADMIN_ESCALATION",
                entity_id=item.id,
            )
            item.admin_escalated_at = now
            admin_escalations += 1

        if item.md_escalated_at is None and item.issue_raised_at <= md_cutoff:
            queue_role_notifications(
                database,
                organization_id=item.organization_id,
                role_codes={MD_ROLE},
                title="Accounts discrepancy unresolved for 24 hours",
                body=(
                    f"'{item.sheet_name}' raised by {manager_code} remains "
                    "unresolved 24 hours after the issue was reported."
                ),
                dedupe_prefix=f"account-sheet-item:{item.id}:md-24h",
                route=route,
                module="sheet-verification",
                event="ACCOUNT_SHEET_MD_ESCALATION",
                entity_id=item.id,
            )
            item.md_escalated_at = now
            md_escalations += 1

    if admin_escalations or md_escalations:
        database.commit()

    return {
        "scanned": len(rows),
        "admin_escalations": admin_escalations,
        "md_escalations": md_escalations,
    }
