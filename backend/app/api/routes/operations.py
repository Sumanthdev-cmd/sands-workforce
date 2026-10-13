from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.operations import (
    LabourPaymentCreateRequest,
    LabourPaymentDecisionRequest,
    LabourPaymentPaidRequest,
    LabourPaymentRejectRequest,
    LabourPaymentResponse,
    OperationActionResponse,
    RefundDecisionRequest,
    RefundRejectRequest,
    ShopRentalAdvanceRefundCreateRequest,
    ShopRentalAdvanceRefundResponse,
    ShopRentalCreateRequest,
    ShopRentalResponse,
    ShopRentalUpdateRequest,
    VendorCreateRequest,
    VendorDepositRefundCreateRequest,
    VendorDepositRefundResponse,
    VendorIssueAssignRequest,
    VendorIssueCreateRequest,
    VendorIssueDecisionRequest,
    VendorIssueResponse,
    VendorResponse,
    VendorUpdateRequest,
    WingContactCreateRequest,
    WingContactResponse,
    WingContactUpdateRequest,
    WingCreateRequest,
    WingResponse,
    WingUpdateRequest,
)
from app.services.operations_service import (
    assign_vendor_issue,
    create_labour_payment,
    create_shop_rental,
    create_vendor,
    create_vendor_issue,
    create_wing,
    create_wing_contact,
    decide_shop_rental_refund,
    decide_vendor_deposit_refund,
    decide_labour_payment,
    decide_vendor_issue,
    list_labour_payment_actions,
    list_my_labour_payments,
    list_my_vendor_issues,
    list_pending_labour_payments,
    list_pending_vendor_issues,
    list_shop_rental_refunds,
    list_shop_rentals,
    list_vendor_deposit_refunds,
    list_vendor_issue_actions,
    list_vendors,
    list_wing_contacts,
    list_wings,
    mark_labour_payment_paid,
    request_shop_rental_refund,
    request_vendor_deposit_refund,
    update_shop_rental,
    update_vendor,
    update_wing,
    update_wing_contact,
)


router = APIRouter(
    prefix="/operations",
    tags=["Vendor, Labour and Wings"],
)

DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/vendors",
    response_model=VendorResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_vendor(
    payload: VendorCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_vendor(database, user=current_user, payload=payload)


@router.get("/vendors", response_model=list[VendorResponse])
def read_vendors(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_vendors(database, user=current_user)


@router.patch(
    "/vendors/{vendor_id}",
    response_model=VendorResponse,
)
def edit_vendor(
    vendor_id: UUID,
    payload: VendorUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return update_vendor(
        database,
        user=current_user,
        vendor_id=vendor_id,
        payload=payload,
    )


@router.get(
    "/vendor-deposit-refunds",
    response_model=list[VendorDepositRefundResponse],
)
def read_vendor_deposit_refunds(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_vendor_deposit_refunds(database, user=current_user)


@router.post(
    "/vendors/{vendor_id}/deposit-refunds",
    response_model=VendorDepositRefundResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_vendor_deposit_return(
    vendor_id: UUID,
    payload: VendorDepositRefundCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return request_vendor_deposit_refund(
        database,
        user=current_user,
        vendor_id=vendor_id,
        payload=payload,
    )


@router.post(
    "/vendor-deposit-refunds/{refund_id}/approve",
    response_model=VendorDepositRefundResponse,
)
def approve_vendor_deposit_return(
    refund_id: UUID,
    payload: RefundDecisionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return decide_vendor_deposit_refund(
        database,
        user=current_user,
        refund_id=refund_id,
        note=payload.note,
        approved=True,
    )


@router.post(
    "/vendor-deposit-refunds/{refund_id}/reject",
    response_model=VendorDepositRefundResponse,
)
def reject_vendor_deposit_return(
    refund_id: UUID,
    payload: RefundRejectRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return decide_vendor_deposit_refund(
        database,
        user=current_user,
        refund_id=refund_id,
        note=payload.reason,
        approved=False,
    )


@router.post(
    "/shop-rentals",
    response_model=ShopRentalResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_shop_rental(
    payload: ShopRentalCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_shop_rental(database, user=current_user, payload=payload)


@router.get("/shop-rentals", response_model=list[ShopRentalResponse])
def read_shop_rentals(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_shop_rentals(database, user=current_user)


@router.patch("/shop-rentals/{rental_id}", response_model=ShopRentalResponse)
def edit_shop_rental(
    rental_id: UUID,
    payload: ShopRentalUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return update_shop_rental(
        database,
        user=current_user,
        rental_id=rental_id,
        payload=payload,
    )


@router.get(
    "/shop-rental-refunds",
    response_model=list[ShopRentalAdvanceRefundResponse],
)
def read_shop_rental_refunds(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_shop_rental_refunds(database, user=current_user)


@router.post(
    "/shop-rentals/{rental_id}/refunds",
    response_model=ShopRentalAdvanceRefundResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_shop_rental_advance_return(
    rental_id: UUID,
    payload: ShopRentalAdvanceRefundCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return request_shop_rental_refund(
        database,
        user=current_user,
        rental_id=rental_id,
        payload=payload,
    )


@router.post(
    "/shop-rental-refunds/{refund_id}/approve",
    response_model=ShopRentalAdvanceRefundResponse,
)
def approve_shop_rental_advance_return(
    refund_id: UUID,
    payload: RefundDecisionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return decide_shop_rental_refund(
        database,
        user=current_user,
        refund_id=refund_id,
        note=payload.note,
        approved=True,
    )


@router.post(
    "/shop-rental-refunds/{refund_id}/reject",
    response_model=ShopRentalAdvanceRefundResponse,
)
def reject_shop_rental_advance_return(
    refund_id: UUID,
    payload: RefundRejectRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return decide_shop_rental_refund(
        database,
        user=current_user,
        refund_id=refund_id,
        note=payload.reason,
        approved=False,
    )


@router.post(
    "/vendor-issues",
    response_model=VendorIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
def raise_vendor_issue(
    payload: VendorIssueCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_vendor_issue(
        database,
        user=current_user,
        payload=payload,
    )


@router.get(
    "/vendor-issues/me",
    response_model=list[VendorIssueResponse],
)
def read_my_vendor_issues(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_my_vendor_issues(database, user=current_user)


@router.get(
    "/vendor-issues/pending",
    response_model=list[VendorIssueResponse],
)
def read_pending_vendor_issues(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_pending_vendor_issues(database, user=current_user)


@router.post(
    "/vendor-issues/{issue_id}/assign",
    response_model=VendorIssueResponse,
)
def assign_issue(
    issue_id: UUID,
    payload: VendorIssueAssignRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return assign_vendor_issue(
        database,
        user=current_user,
        issue_id=issue_id,
        payload=payload,
    )


@router.post(
    "/vendor-issues/{issue_id}/resolve",
    response_model=VendorIssueResponse,
)
def resolve_issue(
    issue_id: UUID,
    payload: VendorIssueDecisionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return decide_vendor_issue(
        database,
        user=current_user,
        issue_id=issue_id,
        payload=payload,
        resolved=True,
    )


@router.post(
    "/vendor-issues/{issue_id}/reject",
    response_model=VendorIssueResponse,
)
def reject_issue(
    issue_id: UUID,
    payload: VendorIssueDecisionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return decide_vendor_issue(
        database,
        user=current_user,
        issue_id=issue_id,
        payload=payload,
        resolved=False,
    )


@router.get(
    "/vendor-issues/{issue_id}/actions",
    response_model=list[OperationActionResponse],
)
def read_issue_actions(
    issue_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_vendor_issue_actions(
        database,
        user=current_user,
        issue_id=issue_id,
    )


@router.post(
    "/labour-payments",
    response_model=LabourPaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_labour_payment(
    payload: LabourPaymentCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_labour_payment(
        database,
        user=current_user,
        payload=payload,
    )


@router.get(
    "/labour-payments/me",
    response_model=list[LabourPaymentResponse],
)
def read_my_labour_payments(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_my_labour_payments(database, user=current_user)


@router.get(
    "/labour-payments/pending",
    response_model=list[LabourPaymentResponse],
)
def read_pending_labour_payments(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_pending_labour_payments(database, user=current_user)


@router.post(
    "/labour-payments/{payment_id}/approve",
    response_model=LabourPaymentResponse,
)
def approve_labour_payment(
    payment_id: UUID,
    payload: LabourPaymentDecisionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return decide_labour_payment(
        database,
        user=current_user,
        payment_id=payment_id,
        note=payload.note,
        approved=True,
    )


@router.post(
    "/labour-payments/{payment_id}/reject",
    response_model=LabourPaymentResponse,
)
def reject_labour_payment(
    payment_id: UUID,
    payload: LabourPaymentRejectRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return decide_labour_payment(
        database,
        user=current_user,
        payment_id=payment_id,
        note=payload.reason,
        approved=False,
    )


@router.post(
    "/labour-payments/{payment_id}/mark-paid",
    response_model=LabourPaymentResponse,
)
def pay_labour_payment(
    payment_id: UUID,
    payload: LabourPaymentPaidRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return mark_labour_payment_paid(
        database,
        user=current_user,
        payment_id=payment_id,
        payload=payload,
    )


@router.get(
    "/labour-payments/{payment_id}/actions",
    response_model=list[OperationActionResponse],
)
def read_labour_payment_actions(
    payment_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_labour_payment_actions(
        database,
        user=current_user,
        payment_id=payment_id,
    )


@router.post(
    "/wings",
    response_model=WingResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_wing(
    payload: WingCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_wing(database, user=current_user, payload=payload)


@router.get("/wings", response_model=list[WingResponse])
def read_wings(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_wings(database, user=current_user)


@router.patch(
    "/wings/{wing_id}",
    response_model=WingResponse,
)
def edit_wing(
    wing_id: UUID,
    payload: WingUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return update_wing(
        database,
        user=current_user,
        wing_id=wing_id,
        payload=payload,
    )


@router.post(
    "/wings/{wing_id}/contacts",
    response_model=WingContactResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_wing_contact(
    wing_id: UUID,
    payload: WingContactCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_wing_contact(
        database,
        user=current_user,
        wing_id=wing_id,
        payload=payload,
    )


@router.get(
    "/wings/{wing_id}/contacts",
    response_model=list[WingContactResponse],
)
def read_wing_contacts(
    wing_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_wing_contacts(
        database,
        user=current_user,
        wing_id=wing_id,
    )


@router.patch(
    "/wing-contacts/{contact_id}",
    response_model=WingContactResponse,
)
def edit_wing_contact(
    contact_id: UUID,
    payload: WingContactUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return update_wing_contact(
        database,
        user=current_user,
        contact_id=contact_id,
        payload=payload,
    )
