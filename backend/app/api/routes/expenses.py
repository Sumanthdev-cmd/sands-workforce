from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.expense import (
    AdminExpenseClaimResponse,
    ClaimApprovalRequest,
    ClaimPaymentRequest,
    ClaimRejectRequest,
    ClaimVerificationRequest,
    ExpenseClaimActionResponse,
    ExpenseClaimCreateRequest,
    ExpenseClaimResponse,
)
from app.services.expense_service import (
    approve_claim,
    create_claim,
    list_actions,
    list_my_claims,
    list_pending_claims,
    mark_claim_paid,
    read_claim,
    reject_claim,
    submit_claim,
    verify_claim,
)


router = APIRouter(prefix="/expenses", tags=["TA-DA and Expenses"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/claims",
    response_model=ExpenseClaimResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_expense_claim(
    payload: ExpenseClaimCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_claim(database, current_user, payload)


@router.get("/claims/me", response_model=list[ExpenseClaimResponse])
def read_my_expense_claims(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_my_claims(database, current_user)


@router.get(
    "/claims/pending",
    response_model=list[AdminExpenseClaimResponse],
)
def read_pending_expense_claims(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_pending_claims(database, current_user)


@router.get(
    "/claims/{claim_id}",
    response_model=AdminExpenseClaimResponse,
)
def read_expense_claim(
    claim_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return read_claim(database, current_user, claim_id)


@router.post(
    "/claims/{claim_id}/submit",
    response_model=ExpenseClaimResponse,
)
def submit_expense_claim(
    claim_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return submit_claim(database, current_user, claim_id)


@router.post(
    "/claims/{claim_id}/verify",
    response_model=ExpenseClaimResponse,
)
def verify_expense_claim(
    claim_id: UUID,
    payload: ClaimVerificationRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return verify_claim(database, current_user, claim_id, payload)


@router.post(
    "/claims/{claim_id}/approve",
    response_model=ExpenseClaimResponse,
)
def approve_expense_claim(
    claim_id: UUID,
    payload: ClaimApprovalRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return approve_claim(database, current_user, claim_id, payload)


@router.post(
    "/claims/{claim_id}/reject",
    response_model=ExpenseClaimResponse,
)
def reject_expense_claim(
    claim_id: UUID,
    payload: ClaimRejectRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return reject_claim(database, current_user, claim_id, payload)


@router.post(
    "/claims/{claim_id}/mark-paid",
    response_model=ExpenseClaimResponse,
)
def mark_expense_claim_paid(
    claim_id: UUID,
    payload: ClaimPaymentRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return mark_claim_paid(database, current_user, claim_id, payload)


@router.get(
    "/claims/{claim_id}/actions",
    response_model=list[ExpenseClaimActionResponse],
)
def read_expense_claim_actions(
    claim_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_actions(database, current_user, claim_id)
