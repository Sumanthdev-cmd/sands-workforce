from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.maintenance_bill import (
    MaintenanceBillActionResponse,
    MaintenanceBillCreateRequest,
    MaintenanceBillDecisionRequest,
    MaintenanceBillPaymentRequest,
    MaintenanceBillRejectRequest,
    MaintenanceBillResponse,
    MaintenanceBillUpdateRequest,
    MaintenanceBillVerificationRejectRequest,
    MaintenanceBillVerificationRequest,
)
from app.services.maintenance_bill_service import (
    approve_bill,
    create_bill,
    get_bill,
    list_actions,
    list_bills,
    list_md_pending,
    mark_paid,
    reject_bill,
    reject_verification,
    require_view_access,
    submit_bill,
    update_bill,
    verify_bill,
)


router = APIRouter(
    prefix="/maintenance-bills",
    tags=["Maintenance & Bills"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


@router.post(
    "",
    response_model=MaintenanceBillResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_maintenance_bill(
    payload: MaintenanceBillCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_bill(
        database,
        user=current_user,
        payload=payload,
    )


@router.get(
    "",
    response_model=list[MaintenanceBillResponse],
)
def read_maintenance_bills(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_bills(
        database,
        user=current_user,
    )


@router.get(
    "/md-pending",
    response_model=list[MaintenanceBillResponse],
)
def read_md_pending_bills(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_md_pending(
        database,
        user=current_user,
    )


@router.get(
    "/{bill_id}",
    response_model=MaintenanceBillResponse,
)
def read_maintenance_bill(
    bill_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return get_bill(
        database,
        user=current_user,
        bill_id=bill_id,
    )


@router.patch(
    "/{bill_id}",
    response_model=MaintenanceBillResponse,
)
def edit_maintenance_bill(
    bill_id: UUID,
    payload: MaintenanceBillUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return update_bill(
        database,
        user=current_user,
        bill_id=bill_id,
        payload=payload,
    )


@router.post(
    "/{bill_id}/submit",
    response_model=MaintenanceBillResponse,
)
def submit_maintenance_bill(
    bill_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return submit_bill(
        database,
        user=current_user,
        bill_id=bill_id,
    )


@router.post(
    "/{bill_id}/verify",
    response_model=MaintenanceBillResponse,
)
def verify_maintenance_bill(
    bill_id: UUID,
    payload: MaintenanceBillVerificationRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return verify_bill(
        database,
        user=current_user,
        bill_id=bill_id,
        note=payload.note,
    )


@router.post(
    "/{bill_id}/verification-reject",
    response_model=MaintenanceBillResponse,
)
def reject_maintenance_bill_verification(
    bill_id: UUID,
    payload: MaintenanceBillVerificationRejectRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return reject_verification(
        database,
        user=current_user,
        bill_id=bill_id,
        reason=payload.reason,
    )


@router.post(
    "/{bill_id}/approve",
    response_model=MaintenanceBillResponse,
)
def approve_maintenance_bill(
    bill_id: UUID,
    payload: MaintenanceBillDecisionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return approve_bill(
        database,
        user=current_user,
        bill_id=bill_id,
        note=payload.note,
    )


@router.post(
    "/{bill_id}/reject",
    response_model=MaintenanceBillResponse,
)
def reject_maintenance_bill(
    bill_id: UUID,
    payload: MaintenanceBillRejectRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return reject_bill(
        database,
        user=current_user,
        bill_id=bill_id,
        reason=payload.reason,
    )


@router.post(
    "/{bill_id}/mark-paid",
    response_model=MaintenanceBillResponse,
)
def mark_maintenance_bill_paid(
    bill_id: UUID,
    payload: MaintenanceBillPaymentRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return mark_paid(
        database,
        user=current_user,
        bill_id=bill_id,
        payload=payload,
    )


@router.get(
    "/{bill_id}/actions",
    response_model=list[MaintenanceBillActionResponse],
)
def read_maintenance_bill_actions(
    bill_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    require_view_access(
        database,
        current_user,
    )
    return list_actions(
        database,
        user=current_user,
        bill_id=bill_id,
    )