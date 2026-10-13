from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.documents import (
    DocumentCompleteRequest,
    DocumentResponse,
    DocumentUpdateRequest,
    DocumentUploadRequest,
    DocumentVerifyRequest,
    PresignedDownloadResponse,
    PresignedUploadResponse,
)
from app.services.document_service import (
    complete_upload,
    list_documents,
    prepare_download,
    prepare_preview,
    prepare_upload,
    update_document,
    verify_document,
)


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "/presign-upload",
    response_model=PresignedUploadResponse,
)
def create_document_upload_url(
    payload: DocumentUploadRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> PresignedUploadResponse:
    return prepare_upload(
        database,
        user=current_user,
        payload=payload,
    )


@router.post(
    "/{document_id}/complete",
    response_model=DocumentResponse,
)
def complete_document_upload(
    document_id: UUID,
    payload: DocumentCompleteRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> DocumentResponse:
    return complete_upload(
        database,
        user=current_user,
        document_id=document_id,
        etag=payload.etag,
    )


@router.get(
    "",
    response_model=list[DocumentResponse],
)
def read_documents(
    current_user: CurrentUser,
    database: DatabaseSession,
    owner_type: str | None = Query(default=None),
    owner_id: UUID | None = Query(default=None),
    category: str | None = Query(default=None),
    expiring_only: bool = Query(default=False),
) -> list[DocumentResponse]:
    return list_documents(
        database,
        user=current_user,
        owner_type=owner_type,
        owner_id=owner_id,
        category=category,
        expiring_only=expiring_only,
    )


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
)
def edit_document(
    document_id: UUID,
    payload: DocumentUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> DocumentResponse:
    return update_document(
        database,
        user=current_user,
        document_id=document_id,
        payload=payload,
    )


@router.post(
    "/{document_id}/verify",
    response_model=DocumentResponse,
)
def verify_stored_document(
    document_id: UUID,
    payload: DocumentVerifyRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> DocumentResponse:
    return verify_document(
        database,
        user=current_user,
        document_id=document_id,
        payload=payload,
    )


@router.get(
    "/{document_id}/download-url",
    response_model=PresignedDownloadResponse,
)
def create_document_download_url(
    document_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> PresignedDownloadResponse:
    return prepare_download(
        database,
        user=current_user,
        document_id=document_id,
    )



@router.get(
    "/{document_id}/preview-url",
    response_model=PresignedDownloadResponse,
)
def create_document_preview_url(
    document_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> PresignedDownloadResponse:
    return prepare_preview(
        database,
        user=current_user,
        document_id=document_id,
    )
