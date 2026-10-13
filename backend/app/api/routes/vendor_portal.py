from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.vendor_portal import (
    VendorPortalAccountResponse,
    VendorPortalAdminCreateRequest,
    VendorPortalAdminResetPasswordRequest,
    VendorPortalChangePasswordRequest,
    VendorPortalDashboardResponse,
    VendorPortalDocumentResponse,
    VendorPortalDownloadResponse,
    VendorPortalInspectionDetail,
    VendorPortalInspectionResponseRequest,
    VendorPortalInspectionSummary,
    VendorPortalLoginRequest,
    VendorPortalMeResponse,
    VendorPortalNotificationResponse,
    VendorPortalOutletResponse,
    VendorPortalTokenResponse,
    VendorAttendanceActionRequest,
    VendorAttendanceResponse,
)
from app.schemas.salary_advance import (
    SalaryAdvanceCancelRequest,
    SalaryAdvanceCreateRequest,
    SalaryAdvanceResponse,
)
from app.services.salary_advance_service import (
    cancel_vendor_salary_advance,
    create_vendor_salary_advance,
    list_my_vendor_salary_advances,
)
from app.services.vendor_portal_service import (
    VendorPortalContext,
    authenticate_vendor_session,
    change_vendor_password,
    create_admin_account,
    list_admin_accounts,
    list_vendor_documents,
    list_vendor_inspections,
    list_vendor_notifications,
    list_vendor_outlets,
    login_vendor,
    logout_vendor,
    mark_vendor_notification_read,
    read_vendor_outlet,
    reset_admin_password,
    respond_to_vendor_inspection,
    set_account_status,
    vendor_dashboard,
    vendor_document_download,
    vendor_inspection_detail,
    vendor_me,
    vendor_attendance_check_in,
    vendor_attendance_check_out,
    vendor_attendance_today,
    list_admin_vendor_attendance,
)


router = APIRouter(prefix="/vendor-portal", tags=["Vendor Portal"])
Database = Annotated[Session, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)


def current_vendor_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    database: Database,
) -> VendorPortalContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Vendor authentication is required.")
    return authenticate_vendor_session(database, credentials.credentials)


VendorCurrent = Annotated[VendorPortalContext, Depends(current_vendor_context)]


def current_vendor_ready(current_vendor: VendorCurrent) -> VendorPortalContext:
    if current_vendor.force_password_change:
        raise HTTPException(
            status_code=403,
            detail="Change the temporary password before using the vendor portal.",
        )
    return current_vendor


VendorReady = Annotated[VendorPortalContext, Depends(current_vendor_ready)]


# Employee/management side: account administration.
@router.get("/admin/accounts", response_model=list[VendorPortalAccountResponse])
def admin_accounts(current_user: CurrentUser, database: Database):
    return list_admin_accounts(database, current_user)


@router.get("/admin/attendance", response_model=list[VendorAttendanceResponse])
def admin_vendor_attendance(
    current_user: CurrentUser,
    database: Database,
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
):
    return list_admin_vendor_attendance(database, current_user, start_date, end_date)


@router.post("/admin/accounts", response_model=VendorPortalAccountResponse, status_code=status.HTTP_201_CREATED)
def admin_create_account(
    payload: VendorPortalAdminCreateRequest,
    current_user: CurrentUser,
    database: Database,
):
    return create_admin_account(database, current_user, payload.vendor_id, payload.temporary_password)


@router.post("/admin/accounts/{account_id}/reset-password", response_model=VendorPortalAccountResponse)
def admin_reset_password(
    account_id: UUID,
    payload: VendorPortalAdminResetPasswordRequest,
    current_user: CurrentUser,
    database: Database,
):
    return reset_admin_password(database, current_user, account_id, payload.temporary_password)


@router.post("/admin/accounts/{account_id}/disable", response_model=VendorPortalAccountResponse)
def admin_disable_account(account_id: UUID, current_user: CurrentUser, database: Database):
    return set_account_status(database, current_user, account_id, False)


@router.post("/admin/accounts/{account_id}/enable", response_model=VendorPortalAccountResponse)
def admin_enable_account(account_id: UUID, current_user: CurrentUser, database: Database):
    return set_account_status(database, current_user, account_id, True)


# Vendor authentication is separate from employee JWT authentication.
@router.post("/auth/login", response_model=VendorPortalTokenResponse)
def vendor_login(payload: VendorPortalLoginRequest, request: Request, database: Database):
    return login_vendor(
        database,
        payload.organization_code,
        payload.vendor_code,
        payload.password,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def vendor_logout(current_vendor: VendorCurrent, database: Database):
    logout_vendor(database, current_vendor)
    return None


@router.get("/me", response_model=VendorPortalMeResponse)
def vendor_profile(current_vendor: VendorCurrent):
    return vendor_me(current_vendor)


@router.post("/change-password", response_model=VendorPortalMeResponse)
def vendor_change_password(
    payload: VendorPortalChangePasswordRequest,
    current_vendor: VendorCurrent,
    database: Database,
):
    return change_vendor_password(
        database,
        current_vendor,
        payload.current_password,
        payload.new_password,
    )


@router.get("/dashboard", response_model=VendorPortalDashboardResponse)
def vendor_dashboard_endpoint(current_vendor: VendorReady, database: Database):
    return vendor_dashboard(database, current_vendor)


@router.get("/outlets", response_model=list[VendorPortalOutletResponse])
def vendor_outlets(current_vendor: VendorReady, database: Database):
    return list_vendor_outlets(database, current_vendor)


@router.get("/attendance/today", response_model=list[VendorAttendanceResponse])
def vendor_today_attendance(current_vendor: VendorReady, database: Database):
    return vendor_attendance_today(database, current_vendor)


@router.post("/attendance/check-in", response_model=VendorAttendanceResponse)
def vendor_check_in(
    payload: VendorAttendanceActionRequest,
    current_vendor: VendorReady,
    database: Database,
):
    return vendor_attendance_check_in(database, current_vendor, payload)


@router.post("/attendance/check-out", response_model=VendorAttendanceResponse)
def vendor_check_out(
    payload: VendorAttendanceActionRequest,
    current_vendor: VendorReady,
    database: Database,
):
    return vendor_attendance_check_out(database, current_vendor, payload)


@router.get("/salary-advances", response_model=list[SalaryAdvanceResponse])
def vendor_salary_advances(current_vendor: VendorReady, database: Database):
    return list_my_vendor_salary_advances(database, current_vendor)


@router.post("/salary-advances", response_model=SalaryAdvanceResponse, status_code=status.HTTP_201_CREATED)
def vendor_salary_advance_request(
    payload: SalaryAdvanceCreateRequest,
    current_vendor: VendorReady,
    database: Database,
):
    return create_vendor_salary_advance(database, current_vendor, payload)


@router.post("/salary-advances/{request_id}/cancel", response_model=SalaryAdvanceResponse)
def vendor_salary_advance_cancel(
    request_id: UUID,
    payload: SalaryAdvanceCancelRequest,
    current_vendor: VendorReady,
    database: Database,
):
    return cancel_vendor_salary_advance(database, current_vendor, request_id, payload)


@router.get("/outlets/{outlet_id}", response_model=VendorPortalOutletResponse)
def vendor_outlet(outlet_id: UUID, current_vendor: VendorReady, database: Database):
    return read_vendor_outlet(database, current_vendor, outlet_id)


@router.get("/documents", response_model=list[VendorPortalDocumentResponse])
def vendor_documents(
    current_vendor: VendorReady,
    database: Database,
    outlet_id: UUID | None = Query(default=None),
):
    return list_vendor_documents(database, current_vendor, outlet_id)


@router.get("/documents/{document_id}/download", response_model=VendorPortalDownloadResponse)
def vendor_download(document_id: UUID, current_vendor: VendorReady, database: Database):
    return vendor_document_download(database, current_vendor, document_id)


@router.get("/inspections", response_model=list[VendorPortalInspectionSummary])
def vendor_inspections(current_vendor: VendorReady, database: Database):
    return list_vendor_inspections(database, current_vendor)


@router.get("/inspections/{report_id}", response_model=VendorPortalInspectionDetail)
def vendor_inspection(report_id: UUID, current_vendor: VendorReady, database: Database):
    return vendor_inspection_detail(database, current_vendor, report_id)


@router.post("/inspections/{report_id}/respond", response_model=VendorPortalInspectionDetail)
def vendor_inspection_respond(
    report_id: UUID,
    payload: VendorPortalInspectionResponseRequest,
    request: Request,
    current_vendor: VendorReady,
    database: Database,
):
    return respond_to_vendor_inspection(
        database,
        current_vendor,
        report_id,
        payload.response,
        payload.remarks,
        payload.signature_data_uri,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )


@router.get("/notifications", response_model=list[VendorPortalNotificationResponse])
def vendor_notifications(
    current_vendor: VendorReady,
    database: Database,
    unread_only: bool = Query(default=False),
):
    return list_vendor_notifications(database, current_vendor, unread_only)


@router.post("/notifications/{notification_id}/read", response_model=VendorPortalNotificationResponse)
def vendor_notification_read(
    notification_id: UUID,
    current_vendor: VendorReady,
    database: Database,
):
    return mark_vendor_notification_read(database, current_vendor, notification_id)
