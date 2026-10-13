from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID
import hashlib
from sqlalchemy.exc import IntegrityError

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.models import DocumentRecord, Notification, Role, User, user_roles
from app.models.appointment import (
    DocumentApprovalAction,
    DocumentApprovalRequest,
)
from app.schemas.appointment import (
    DocumentApprovalActionResponse,
    DocumentApprovalCreateRequest,
    DocumentApprovalDecisionRequest,
    DocumentApprovalResponse,
    ReasonRequest,
)
from app.services.document_service import ensure_document_access


router = APIRouter(prefix="/approvals", tags=["Document Approvals"])
DatabaseSession = Annotated[Session, Depends(get_db)]

MD_ROLES = {"MD"}
VIEW_ROLES = {"ADMIN", "MD", "GM"}

# ACTION_ALERTS_PHASE1_APPROVAL_NOTIFICATIONS
def _approval_notification(
    database: Session,
    *,
    organization_id,
    recipient_user_id,
    title: str,
    body: str,
    dedupe_key: str,
    request_id,
    event: str,
) -> None:
    database.add(
        Notification(
            organization_id=organization_id,
            recipient_user_id=recipient_user_id,
            channel="IN_APP",
            title=title,
            body=body,
            payload={
                "type": "APPROVAL_REQUEST",
                "event": event,
                "request_id": str(request_id),
                "module": "approvals",
                "route": "/module/approvals?queue=1",
            },
            dedupe_key=dedupe_key,
            status="PENDING",
            attempts=0,
            available_at=datetime.now(timezone.utc),
        )
    )


def notify_approval_approvers(
    database: Session,
    row,
    requester: User,
) -> None:
    recipients = list(
        database.scalars(
            select(User)
            .join(user_roles, User.id == user_roles.c.user_id)
            .join(Role, Role.id == user_roles.c.role_id)
            .where(
                User.organization_id == row.organization_id,
                Role.code.in_(MD_ROLES),
            )
            .distinct()
        ).all()
    )

    requester_code = getattr(requester, "employee_code", None) or "Employee"

    for recipient in recipients:
        if recipient.id == requester.id:
            continue

        _approval_notification(
            database,
            organization_id=row.organization_id,
            recipient_user_id=recipient.id,
            title="New approval request",
            body=f"{requester_code} submitted: {row.title}",
            dedupe_key=f"approval:{row.id}:requested:{recipient.id}",
            request_id=row.id,
            event="REQUESTED",
        )


def notify_approval_requester(
    database: Session,
    row,
    approver: User,
    action: str,
) -> None:
    approver_code = getattr(approver, "employee_code", None) or "MD"

    _approval_notification(
        database,
        organization_id=row.organization_id,
        recipient_user_id=row.requester_user_id,
        title=f"Approval request {action.lower()}",
        body=f"{row.title} was {action.lower()} by {approver_code}.",
        dedupe_key=f"approval:{row.id}:{action.lower()}:{row.requester_user_id}",
        request_id=row.id,
        event=action,
    )



def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def _normalize_for_dedupe(value: str) -> str:
    return " ".join(
        value.strip().lower().split()
    )


def _approval_dedupe_key(
    *,
    user: User,
    payload: DocumentApprovalCreateRequest,
) -> str | None:
    extra_data = payload.extra_data or {}

    submission_id = extra_data.get("submission_id")

    # Older callers may not send an idempotency identifier.
    if not submission_id:
        return None

    try:
        submission_id = str(UUID(str(submission_id)))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid submission identifier.",
        )

    raw = "|".join(
        [
            str(user.organization_id),
            str(user.id),
            submission_id,
        ]
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def require_md(database: Session, user: User) -> None:

    def require_md(database: Session, user: User) -> None:
        if not role_codes(database, user).intersection(MD_ROLES):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an MD can decide document approvals.",
        )


def get_request(
    database: Session,
    user: User,
    request_id: UUID,
) -> DocumentApprovalRequest:
    row = database.scalar(
        select(DocumentApprovalRequest).where(
            DocumentApprovalRequest.id == request_id,
            DocumentApprovalRequest.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document approval request was not found.",
        )
    return row


def response_dict(database: Session, row: DocumentApprovalRequest) -> dict:
    document = (
    database.get(DocumentRecord, row.document_id)
    if row.document_id is not None
    else None
)
    requester = database.get(User, row.requester_user_id)
    return {
        "id": row.id,
        "document_id": row.document_id,
        "requester_user_id": row.requester_user_id,
        "approval_type": row.approval_type,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "approver_user_id": row.approver_user_id,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
        "extra_data": row.extra_data,
        "document_title": document.title if document else None,
        "document_category": document.category if document else None,
        "requester_employee_code": (
            getattr(requester, "employee_code", None)
            if requester else None
        ),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def ensure_request_access(
    database: Session,
    user: User,
    row: DocumentApprovalRequest,
) -> None:
    if row.requester_user_id == user.id:
        return
    if role_codes(database, user).intersection(VIEW_ROLES):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this request.",
    )


@router.post(
    "/documents",
    response_model=DocumentApprovalResponse,
    status_code=201,
)
def create_document_approval(
    payload: DocumentApprovalCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    document = None

    # Supporting image / PDF is optional.
    if payload.document_id is not None:
        document = database.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == payload.document_id,
                DocumentRecord.organization_id
                == current_user.organization_id,
            )
        )

        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supporting document was not found.",
            )

        ensure_document_access(
            database,
            user=current_user,
            document=document,
        )

        if document.status in {
            "UPLOAD_PENDING",
            "ARCHIVED",
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Upload and activate the document "
                    "before requesting approval."
                ),
            )

    # This is based on a hidden submission ID,
    # NOT the title or description.
    dedupe_key = _approval_dedupe_key(
        user=current_user,
        payload=payload,
    )

    # Same browser submission/retry must never
    # create another approval request.
    if dedupe_key is not None:
        existing = database.scalar(
            select(DocumentApprovalRequest.id).where(
                DocumentApprovalRequest.organization_id
                == current_user.organization_id,
                DocumentApprovalRequest.dedupe_key
                == dedupe_key,
            )
        )

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This approval request was already submitted."
                ),
            )

    row = DocumentApprovalRequest(
        organization_id=current_user.organization_id,
        document_id=(
            document.id
            if document is not None
            else None
        ),
        requester_user_id=current_user.id,
        approval_type=payload.approval_type,
        title=payload.title.strip(),
        description=payload.description.strip(),
        status="PENDING",
        dedupe_key=dedupe_key,
        extra_data=payload.extra_data,
    )

    database.add(row)

    try:
        database.flush()

    except IntegrityError as error:
        database.rollback()

        # Only convert our idempotency constraint
        # into the friendly duplicate message.
        if (
            "uq_document_approval_submission_dedupe"
            in str(error.orig)
            or "uq_document_approval_pending_dedupe"
            in str(error.orig)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This approval request was already submitted."
                ),
            ) from error

        raise

    database.add(
        DocumentApprovalAction(
            organization_id=current_user.organization_id,
            approval_request_id=row.id,
            actor_user_id=current_user.id,
            action="REQUESTED",
            note="Approval request submitted.",
        )
    )

    notify_approval_approvers(database, row, current_user)


    database.commit()
    database.refresh(row)

    return response_dict(database, row)


@router.get("/documents/me", response_model=list[DocumentApprovalResponse])
def my_document_approvals(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    rows = list(
        database.scalars(
            select(DocumentApprovalRequest)
            .where(
                DocumentApprovalRequest.organization_id
                == current_user.organization_id,
                DocumentApprovalRequest.requester_user_id
                == current_user.id,
            )
            .order_by(DocumentApprovalRequest.created_at.desc())
        ).all()
    )
    return [response_dict(database, row) for row in rows]


@router.get("/documents/pending", response_model=list[DocumentApprovalResponse])
def pending_document_approvals(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    if not role_codes(database, current_user).intersection(VIEW_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Document approval review access is required.",
        )
    rows = list(
        database.scalars(
            select(DocumentApprovalRequest)
            .where(
                DocumentApprovalRequest.organization_id
                == current_user.organization_id,
                DocumentApprovalRequest.status == "PENDING",
            )
            .order_by(DocumentApprovalRequest.created_at)
        ).all()
    )
    return [response_dict(database, row) for row in rows]


@router.get(
    "/documents/{request_id}",
    response_model=DocumentApprovalResponse,
)
def read_document_approval(
    request_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    row = get_request(database, current_user, request_id)
    ensure_request_access(database, current_user, row)
    return response_dict(database, row)


def decide(
    database: Session,
    user: User,
    row: DocumentApprovalRequest,
    action: str,
    note: str | None,
) -> dict:
    require_md(database, user)

    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending requests can be decided.",
        )

    row.status = action
    row.approver_user_id = user.id
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = note

    database.add(
        DocumentApprovalAction(
            organization_id=user.organization_id,
            approval_request_id=row.id,
            actor_user_id=user.id,
            action=action,
            note=note,
        )
    )
    database.add(
        Notification(
            organization_id=user.organization_id,
            recipient_user_id=row.requester_user_id,
            channel="IN_APP",
            title=f"Document approval {action.lower()}",
            body=f"Your request '{row.title}' was {action.lower()}.",
            payload={
                "type": f"DOCUMENT_APPROVAL_{action}",
                "approval_request_id": str(row.id),
                "document_id": str(row.document_id),
            },
            dedupe_key=f"document-approval:{row.id}:{action.lower()}",
            status="PENDING",
            attempts=0,
            available_at=datetime.now(timezone.utc),
        )
    )
    notify_approval_requester(database, row, user, action)

    database.commit()
    database.refresh(row)
    return response_dict(database, row)


@router.post(
    "/documents/{request_id}/approve",
    response_model=DocumentApprovalResponse,
)
def approve_document(
    request_id: UUID,
    payload: DocumentApprovalDecisionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    row = get_request(database, current_user, request_id)
    return decide(database, current_user, row, "APPROVED", payload.note)


@router.post(
    "/documents/{request_id}/reject",
    response_model=DocumentApprovalResponse,
)
def reject_document(
    request_id: UUID,
    payload: ReasonRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    row = get_request(database, current_user, request_id)
    return decide(
        database,
        current_user,
        row,
        "REJECTED",
        payload.reason.strip(),
    )


@router.post(
    "/documents/{request_id}/cancel",
    response_model=DocumentApprovalResponse,
)
def cancel_document(
    request_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    row = get_request(database, current_user, request_id)

    if row.requester_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This request belongs to another user.",
        )
    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending requests can be cancelled.",
        )

    row.status = "CANCELLED"
    database.add(
        DocumentApprovalAction(
            organization_id=current_user.organization_id,
            approval_request_id=row.id,
            actor_user_id=current_user.id,
            action="CANCELLED",
            note="Request cancelled by requester.",
        )
    )
    database.commit()
    database.refresh(row)
    return response_dict(database, row)


@router.get(
    "/documents/{request_id}/actions",
    response_model=list[DocumentApprovalActionResponse],
)
def document_approval_actions(
    request_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    row = get_request(database, current_user, request_id)
    ensure_request_access(database, current_user, row)
    return list(
        database.scalars(
            select(DocumentApprovalAction)
            .where(DocumentApprovalAction.approval_request_id == request_id)
            .order_by(DocumentApprovalAction.created_at)
        ).all()
    )
