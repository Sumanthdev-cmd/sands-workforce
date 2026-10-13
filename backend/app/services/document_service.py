from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    DocumentRecord,
    Employee,
    Role,
    User,
    user_roles,
)
from app.schemas.documents import (
    DocumentUpdateRequest,
    DocumentUploadRequest,
    DocumentVerifyRequest,
)
from app.services.device_service import get_employee_for_user
from app.services.storage_service import (
    DEFAULT_PRESIGN_EXPIRY_SECONDS,
    create_download_url,
    create_preview_url,
    create_upload_url,
    get_storage_config,
)


DOCUMENT_MANAGER_ROLES = {
    "ADMIN",
    "MD",
    "GM",
    "MANAGER",
}

ACCOUNT_SHEET_UPLOAD_ROLES = {
    "ACCOUNTS_MANAGER",
}

ACCOUNT_SHEET_REVIEW_ROLES = {
    "ACCOUNTS_SECRETARY",
    "ADMIN",
    "MD",
}


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def is_document_manager(database: Session, user: User) -> bool:
    return bool(
        role_codes(database, user).intersection(
            DOCUMENT_MANAGER_ROLES
        )
    )


def validate_document_owner(
    database: Session,
    *,
    user: User,
    owner_type: str,
    owner_id: UUID | None,
) -> UUID | None:
    if owner_type == "ACCOUNT_SHEET":
        roles = role_codes(database, user)
        if not roles.intersection(ACCOUNT_SHEET_UPLOAD_ROLES):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Only an Accounts Manager can upload a discrepancy sheet."
                ),
            )

        employee = get_employee_for_user(database, user)

        if owner_id is not None and owner_id != employee.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The accounts-sheet owner must be the current employee.",
            )

        return employee.id

    if is_document_manager(database, user):
        return owner_id

    employee = get_employee_for_user(database, user)

    if owner_type != "EMPLOYEE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Employees can upload only their own employee documents."
            ),
        )

    if owner_id is not None and owner_id != employee.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The employee owner ID does not match the current user.",
        )

    return employee.id


def safe_file_name(file_name: str) -> str:
    name = Path(file_name).name.strip().replace(" ", "_")
    return name or "document.bin"


def get_document(
    database: Session,
    *,
    organization_id: UUID,
    document_id: UUID,
) -> DocumentRecord:
    document = database.scalar(
        select(DocumentRecord).where(
            DocumentRecord.id == document_id,
            DocumentRecord.organization_id == organization_id,
        )
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document was not found.",
        )

    return document


def ensure_document_access(
    database: Session,
    *,
    user: User,
    document: DocumentRecord,
) -> None:
    if document.owner_type == "ACCOUNT_SHEET":
        roles = role_codes(database, user)

        if (
            document.uploaded_by_user_id == user.id
            or roles.intersection(ACCOUNT_SHEET_REVIEW_ROLES)
        ):
            return

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this discrepancy sheet.",
        )

    if is_document_manager(database, user):
        return

    employee = get_employee_for_user(database, user)

    if not (
        document.uploaded_by_user_id == user.id
        or (
            document.owner_type == "EMPLOYEE"
            and document.owner_id == employee.id
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document.",
        )


def prepare_upload(
    database: Session,
    *,
    user: User,
    payload: DocumentUploadRequest,
) -> dict:
    owner_id = validate_document_owner(
        database,
        user=user,
        owner_type=payload.owner_type,
        owner_id=payload.owner_id,
    )

    try:
        bucket, _ = get_storage_config()
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    document_id = uuid4()
    file_name = safe_file_name(payload.file_name)
    key = (
        f"organizations/{user.organization_id}/"
        f"{payload.owner_type.lower()}/"
        f"{owner_id or 'general'}/"
        f"{document_id}/{file_name}"
    )

    document = DocumentRecord(
        id=document_id,
        organization_id=user.organization_id,
        owner_type=payload.owner_type,
        owner_id=owner_id,
        category=payload.category,
        title=payload.title.strip(),
        description=payload.description,
        file_name=file_name,
        content_type=payload.content_type,
        file_size=payload.file_size,
        s3_bucket=bucket,
        s3_key=key,
        issue_date=payload.issue_date,
        expiry_date=payload.expiry_date,
        alert_days_before=payload.alert_days_before,
        status="UPLOAD_PENDING",
        is_confidential=payload.is_confidential,
        uploaded_by_user_id=user.id,
        extra_data=payload.extra_data,
    )
    database.add(document)
    database.commit()

    try:
        upload_url = create_upload_url(
            bucket=bucket,
            key=key,
            content_type=payload.content_type,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return {
        "document_id": document.id,
        "upload_url": upload_url,
        "upload_headers": {
            "Content-Type": payload.content_type,
        },
        "expires_in_seconds": DEFAULT_PRESIGN_EXPIRY_SECONDS,
        "s3_key": key,
    }


def complete_upload(
    database: Session,
    *,
    user: User,
    document_id: UUID,
    etag: str | None,
) -> DocumentRecord:
    document = get_document(
        database,
        organization_id=user.organization_id,
        document_id=document_id,
    )
    ensure_document_access(
        database,
        user=user,
        document=document,
    )

    if document.status != "UPLOAD_PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending uploads can be completed.",
        )

    document.status = "ACTIVE"
    document.etag = etag
    database.commit()
    database.refresh(document)
    return document


def list_documents(
    database: Session,
    *,
    user: User,
    owner_type: str | None,
    owner_id: UUID | None,
    category: str | None,
    expiring_only: bool,
) -> list[DocumentRecord]:
    roles = role_codes(database, user)
    statement = select(DocumentRecord).where(
        DocumentRecord.organization_id == user.organization_id,
        DocumentRecord.status != "ARCHIVED",
    )

    if is_document_manager(database, user):
        if not roles.intersection({"ADMIN", "MD"}):
            account_sheet_access = [
                DocumentRecord.owner_type != "ACCOUNT_SHEET",
                DocumentRecord.uploaded_by_user_id == user.id,
            ]
            if roles.intersection(ACCOUNT_SHEET_REVIEW_ROLES):
                account_sheet_access.append(
                    DocumentRecord.owner_type == "ACCOUNT_SHEET"
                )
            statement = statement.where(or_(*account_sheet_access))
    else:
        employee = get_employee_for_user(database, user)
        access_conditions = [
            DocumentRecord.uploaded_by_user_id == user.id,
            (
                (DocumentRecord.owner_type == "EMPLOYEE")
                & (DocumentRecord.owner_id == employee.id)
            ),
        ]

        if roles.intersection(ACCOUNT_SHEET_REVIEW_ROLES):
            access_conditions.append(
                DocumentRecord.owner_type == "ACCOUNT_SHEET"
            )

        statement = statement.where(or_(*access_conditions))

    if owner_type:
        statement = statement.where(
            DocumentRecord.owner_type == owner_type.strip().upper()
        )

    if owner_id:
        statement = statement.where(
            DocumentRecord.owner_id == owner_id
        )

    if category:
        statement = statement.where(
            DocumentRecord.category == category.strip().upper()
        )

    if expiring_only:
        statement = statement.where(
            DocumentRecord.expiry_date.is_not(None)
        )

    return list(
        database.scalars(
            statement.order_by(
                DocumentRecord.expiry_date.asc().nullslast(),
                DocumentRecord.created_at.desc(),
            )
        ).all()
    )


def update_document(
    database: Session,
    *,
    user: User,
    document_id: UUID,
    payload: DocumentUpdateRequest,
) -> DocumentRecord:
    document = get_document(
        database,
        organization_id=user.organization_id,
        document_id=document_id,
    )
    ensure_document_access(
        database,
        user=user,
        document=document,
    )

    if document.owner_type == "ACCOUNT_SHEET":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Accounts discrepancy evidence is immutable after upload. "
                "Use the Sheet Verification workflow to review it."
            ),
        )

    changes = payload.model_dump(exclude_unset=True)

    if "category" in changes and changes["category"]:
        changes["category"] = changes["category"].strip().upper()

    for field_name, value in changes.items():
        setattr(document, field_name, value)

    database.commit()
    database.refresh(document)
    return document


def verify_document(
    database: Session,
    *,
    user: User,
    document_id: UUID,
    payload: DocumentVerifyRequest,
) -> DocumentRecord:
    if not is_document_manager(database, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Document verification access is required.",
        )

    document = get_document(
        database,
        organization_id=user.organization_id,
        document_id=document_id,
    )

    if document.owner_type == "ACCOUNT_SHEET":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Accounts discrepancy evidence is verified through the "
                "Sheet Verification workflow."
            ),
        )

    if document.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only active documents can be verified.",
        )

    document.status = "VERIFIED"
    document.verified_by_user_id = user.id
    document.verified_at = datetime.now(timezone.utc)
    document.verification_note = payload.note

    database.commit()
    database.refresh(document)
    return document


def prepare_download(
    database: Session,
    *,
    user: User,
    document_id: UUID,
) -> dict:
    document = get_document(
        database,
        organization_id=user.organization_id,
        document_id=document_id,
    )
    ensure_document_access(
        database,
        user=user,
        document=document,
    )

    if document.status == "UPLOAD_PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload is not completed yet.",
        )

    try:
        download_url = create_download_url(
            bucket=document.s3_bucket,
            key=document.s3_key,
            file_name=document.file_name,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return {
        "document_id": document.id,
        "download_url": download_url,
        "expires_in_seconds": DEFAULT_PRESIGN_EXPIRY_SECONDS,
    }



def prepare_preview(
    database: Session,
    *,
    user: User,
    document_id: UUID,
) -> dict:
    document = get_document(
        database,
        organization_id=user.organization_id,
        document_id=document_id,
    )

    ensure_document_access(
        database,
        user=user,
        document=document,
    )

    if document.status == "UPLOAD_PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload is not completed yet.",
        )

    try:
        preview_url = create_preview_url(
            bucket=document.s3_bucket,
            key=document.s3_key,
            file_name=document.file_name,
            content_type=document.content_type,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return {
        "document_id": document.id,
        "download_url": preview_url,
        "expires_in_seconds": DEFAULT_PRESIGN_EXPIRY_SECONDS,
    }
