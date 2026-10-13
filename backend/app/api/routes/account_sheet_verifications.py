from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.account_sheet_verification import (
    AccountSheetItemResponse,
    AccountSheetResolveRequest,
    AccountSheetSecretaryReviewRequest,
    AccountSheetVerificationCreate,
    AccountSheetVerificationResponse,
)
from app.services.account_sheet_verification_service import (
    create_report,
    get_report,
    list_open_issues,
    list_reports,
    list_review_queue,
    resolve_issue,
    secretary_review_item,
)


router = APIRouter(
    prefix="/account-sheet-verifications",
    tags=["Accounts Sheet Verification"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "",
    response_model=AccountSheetVerificationResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_daily_sheet_verification(
    payload: AccountSheetVerificationCreate,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_report(database, user=current_user, payload=payload)


@router.get(
    "",
    response_model=list[AccountSheetVerificationResponse],
)
def read_sheet_verification_reports(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_reports(database, user=current_user)


@router.get(
    "/review-queue",
    response_model=list[AccountSheetItemResponse],
)
def read_accounts_secretary_queue(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_review_queue(database, user=current_user)


@router.get(
    "/issues",
    response_model=list[AccountSheetItemResponse],
)
def read_account_sheet_issues(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_open_issues(database, user=current_user)


@router.post(
    "/items/{item_id}/secretary-review",
    response_model=AccountSheetItemResponse,
)
def review_account_sheet_item(
    item_id: UUID,
    payload: AccountSheetSecretaryReviewRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return secretary_review_item(
        database,
        user=current_user,
        item_id=item_id,
        payload=payload,
    )


@router.post(
    "/items/{item_id}/resolve",
    response_model=AccountSheetItemResponse,
)
def resolve_account_sheet_issue(
    item_id: UUID,
    payload: AccountSheetResolveRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return resolve_issue(
        database,
        user=current_user,
        item_id=item_id,
        payload=payload,
    )


@router.get(
    "/{report_id}",
    response_model=AccountSheetVerificationResponse,
)
def read_sheet_verification_report(
    report_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return get_report(
        database,
        user=current_user,
        report_id=report_id,
    )
