from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.inspection import (
    HoAcknowledgeRequest,
    InspectionCreateRequest,
    InspectionDashboardResponse,
    InspectionDraftUpdateRequest,
    InspectionReportResponse,
    InspectionRotationAssignRequest,
    InspectionRotationManualOverrideRequest,
    InspectionVisitCancelRequest,
    InspectionSubmitRequest,
    InspectionSubmitResponse,
    InspectionTemplateResponse,
    VendorInspectionResponseRequest,
    VendorPublicReportResponse,
)
from app.services.inspection_service import (
    acknowledge_ho,
    close_report,
    create_report,
    create_revision,
    current_template,
    dashboard,
    get_report,
    list_reports,
    public_report,
    regenerate_vendor_link,
    save_draft,
    submit_report,
    vendor_respond,
)

from app.services.inspection_rotation_service import (
    auto_assign_visit,
    cancel_visit_assignment,
    list_visit_assignments,
    manual_override_visit,
    rotation_history,
    rotation_preview,
)


router = APIRouter(prefix="/inspections", tags=["Shop Inspections"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/template/current", response_model=InspectionTemplateResponse)
def read_template(current_user: CurrentUser, database: Database):
    return current_template(database, current_user.organization_id)


@router.get("/dashboard", response_model=InspectionDashboardResponse)
def read_dashboard(current_user: CurrentUser, database: Database):
    return dashboard(database, user=current_user)


@router.get("", response_model=list[InspectionReportResponse])
def read_reports(
    current_user: CurrentUser,
    database: Database,
    status_filter: str | None = Query(default=None, alias="status"),
    mine: bool = Query(default=False),
):
    return list_reports(
        database,
        user=current_user,
        status_filter=status_filter,
        mine=mine,
    )


@router.post("", response_model=InspectionReportResponse, status_code=status.HTTP_201_CREATED)
def create_inspection(
    payload: InspectionCreateRequest,
    current_user: CurrentUser,
    database: Database,
):
    return create_report(database, user=current_user, payload=payload)


@router.get("/rotation/preview")
def preview_rotation(
    outlet_id: UUID,
    scheduled_for: date,
    current_user: CurrentUser,
    database: Database,
):
    return rotation_preview(
        database,
        user=current_user,
        outlet_id=outlet_id,
        scheduled_for=scheduled_for,
    )


@router.post("/rotation/assign", status_code=status.HTTP_201_CREATED)
def assign_rotation(
    payload: InspectionRotationAssignRequest,
    current_user: CurrentUser,
    database: Database,
):
    return auto_assign_visit(
        database,
        user=current_user,
        outlet_id=payload.outlet_id,
        scheduled_for=payload.scheduled_for,
    )


@router.post("/rotation/manual-override", status_code=status.HTTP_201_CREATED)
def manual_override_rotation(
    payload: InspectionRotationManualOverrideRequest,
    current_user: CurrentUser,
    database: Database,
):
    return manual_override_visit(
        database,
        user=current_user,
        outlet_id=payload.outlet_id,
        scheduled_for=payload.scheduled_for,
        employee_id=payload.employee_id,
        reason=payload.reason,
    )


@router.get("/rotation/history/{outlet_id}")
def read_rotation_history(
    outlet_id: UUID,
    current_user: CurrentUser,
    database: Database,
):
    return rotation_history(
        database,
        user=current_user,
        outlet_id=outlet_id,
    )


@router.get("/visit-assignments")
def read_visit_assignments(
    current_user: CurrentUser,
    database: Database,
):
    return list_visit_assignments(
        database,
        user=current_user,
    )


@router.post("/visit-assignments/{assignment_id}/cancel")
def cancel_visit(
    assignment_id: UUID,
    payload: InspectionVisitCancelRequest,
    current_user: CurrentUser,
    database: Database,
):
    return cancel_visit_assignment(
        database,
        user=current_user,
        assignment_id=assignment_id,
        reason=payload.reason,
    )


@router.get("/{report_id}", response_model=InspectionReportResponse)
def read_report(report_id: UUID, current_user: CurrentUser, database: Database):
    return get_report(database, user=current_user, report_id=report_id)


@router.patch("/{report_id}/draft", response_model=InspectionReportResponse)
def update_draft(
    report_id: UUID,
    payload: InspectionDraftUpdateRequest,
    current_user: CurrentUser,
    database: Database,
):
    return save_draft(
        database,
        user=current_user,
        report_id=report_id,
        payload=payload,
    )


@router.post("/{report_id}/submit", response_model=InspectionSubmitResponse)
def submit_inspection(
    report_id: UUID,
    payload: InspectionSubmitRequest,
    current_user: CurrentUser,
    database: Database,
):
    report, review_url, notification_status = submit_report(
        database,
        user=current_user,
        report_id=report_id,
        payload=payload,
    )
    return {
        "report": report,
        "vendor_review_url": review_url,
        "vendor_notification_status": notification_status,
    }


@router.post("/{report_id}/vendor-link")
def new_vendor_link(report_id: UUID, current_user: CurrentUser, database: Database):
    return regenerate_vendor_link(
        database,
        user=current_user,
        report_id=report_id,
    )


@router.post("/{report_id}/ho-acknowledge", response_model=InspectionReportResponse)
def ho_acknowledge(
    report_id: UUID,
    payload: HoAcknowledgeRequest,
    current_user: CurrentUser,
    database: Database,
):
    return acknowledge_ho(
        database,
        user=current_user,
        report_id=report_id,
        payload=payload,
    )


@router.post("/{report_id}/close", response_model=InspectionReportResponse)
def close_inspection(report_id: UUID, current_user: CurrentUser, database: Database):
    return close_report(database, user=current_user, report_id=report_id)


@router.post("/{report_id}/revision", response_model=InspectionReportResponse)
def revise_inspection(report_id: UUID, current_user: CurrentUser, database: Database):
    return create_revision(database, user=current_user, report_id=report_id)


@router.get("/public/vendor/{token}", response_model=VendorPublicReportResponse)
def public_vendor_report(token: str, request: Request, database: Database):
    return public_report(
        database,
        token=token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/public/vendor/{token}/respond", response_model=VendorPublicReportResponse)
def public_vendor_respond(
    token: str,
    payload: VendorInspectionResponseRequest,
    request: Request,
    database: Database,
):
    vendor_respond(
        database,
        token=token,
        payload=payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return public_report(
        database,
        token=token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
