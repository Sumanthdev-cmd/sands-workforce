from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.security_overtime import (
    AttendanceWorkLookupResponse,
    OvertimeAdminReview,
    OvertimeClaimCreate,
    OvertimeClaimResponse,
    OvertimeEvidenceAttach,
    OvertimeMdDecision,
)
from app.services.device_service import get_employee_for_user
from app.services.security_overtime_service import (
    admin_review_overtime_claim,
    attach_overtime_evidence,
    attendance_work_lookup,
    create_overtime_claim,
    list_my_overtime_claims,
    list_organization_overtime_claims,
    md_decide_overtime_claim,
    submit_overtime_claim,
)


router = APIRouter(prefix="/overtime", tags=["Overtime"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/me/attendance", response_model=AttendanceWorkLookupResponse)
def read_my_overtime_attendance(
    work_date: date,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    employee = get_employee_for_user(database, current_user)
    return attendance_work_lookup(
        database,
        user=current_user,
        employee_id=employee.id,
        work_date=work_date,
        management_lookup=False,
    )


@router.get("/attendance-lookup", response_model=AttendanceWorkLookupResponse)
def read_employee_overtime_attendance(
    employee_id: UUID,
    work_date: date,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return attendance_work_lookup(
        database,
        user=current_user,
        employee_id=employee_id,
        work_date=work_date,
        management_lookup=True,
    )


@router.post(
    "/claims",
    response_model=OvertimeClaimResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_overtime_claim(
    payload: OvertimeClaimCreate,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_overtime_claim(database, user=current_user, payload=payload)


@router.post(
    "/claims/{claim_id}/evidence",
    response_model=OvertimeClaimResponse,
)
def add_overtime_evidence(
    claim_id: UUID,
    payload: OvertimeEvidenceAttach,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return attach_overtime_evidence(
        database,
        user=current_user,
        claim_id=claim_id,
        document_id=payload.document_id,
    )


@router.post(
    "/claims/{claim_id}/submit",
    response_model=OvertimeClaimResponse,
)
def submit_claim(
    claim_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return submit_overtime_claim(database, user=current_user, claim_id=claim_id)


@router.get("/claims/me", response_model=list[OvertimeClaimResponse])
def read_my_claims(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_my_overtime_claims(database, user=current_user)


@router.get("/claims/organization", response_model=list[OvertimeClaimResponse])
def read_organization_claims(
    current_user: CurrentUser,
    database: DatabaseSession,
    claim_status: str | None = Query(default=None, alias="status"),
):
    return list_organization_overtime_claims(
        database, user=current_user, claim_status=claim_status
    )


@router.post(
    "/claims/{claim_id}/admin-review",
    response_model=OvertimeClaimResponse,
)
def review_claim_as_admin(
    claim_id: UUID,
    payload: OvertimeAdminReview,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return admin_review_overtime_claim(
        database,
        user=current_user,
        claim_id=claim_id,
        payload=payload,
    )


@router.post(
    "/claims/{claim_id}/md-decision",
    response_model=OvertimeClaimResponse,
)
def decide_claim_as_md(
    claim_id: UUID,
    payload: OvertimeMdDecision,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return md_decide_overtime_claim(
        database,
        user=current_user,
        claim_id=claim_id,
        payload=payload,
    )

