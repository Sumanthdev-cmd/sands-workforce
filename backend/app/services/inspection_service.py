from __future__ import annotations

import hashlib
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Employee,
    InspectionAuditEvent,
    InspectionReport,
    InspectionTemplate,
    Notification,
    Outlet,
    OutletFieldVisitorAssignment,
    Role,
    Task,
    TaskAssignment,
    User,
    Vendor,
    user_roles,
)
from app.schemas.inspection import (
    HoAcknowledgeRequest,
    InspectionCreateRequest,
    InspectionDraftUpdateRequest,
    InspectionSubmitRequest,
    VendorInspectionResponseRequest,
)
from app.services.device_service import get_employee_for_user
from app.services.attendance_service import calculate_distance_meters, get_latest_fresh_location
from app.services.inspection_rotation_service import (
    mark_visit_completed,
    mark_visit_started,
    mark_visit_submitted,
    validate_visit_assignment_for_start,
)
from app.services.workforce_policy_service import ensure_inspection_start_allowed


MANAGEMENT_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}

# Admin / MD / GM / Manager can review inspection records.
# FIELD_VISITOR can access their own inspection records.
INSPECTOR_ROLES = MANAGEMENT_ROLES | {"FIELD_VISITOR"}

# Only FIELD_VISITOR can start/create a shop inspection.
INSPECTION_CREATOR_ROLES = {"FIELD_VISITOR"}


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_roles(database: Session, user: User, allowed: set[str], message: str):
    if not role_codes(database, user).intersection(allowed):
        raise HTTPException(status_code=403, detail=message)


def audit(
    database: Session,
    *,
    report: InspectionReport,
    action: str,
    actor_type: str,
    actor_user_id: UUID | None = None,
    note: str | None = None,
    extra_data: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    database.add(
        InspectionAuditEvent(
            organization_id=report.organization_id,
            report_id=report.id,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            action=action,
            note=note,
            extra_data=extra_data,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )


def current_template(database: Session, organization_id: UUID) -> InspectionTemplate:
    template = database.scalar(
        select(InspectionTemplate)
        .where(
            InspectionTemplate.organization_id == organization_id,
            InspectionTemplate.code == "SHOP_VENDOR_CHECKING_LIST",
            InspectionTemplate.is_active.is_(True),
        )
        .order_by(InspectionTemplate.version.desc())
        .limit(1)
    )
    if template is None:
        raise HTTPException(
            status_code=409,
            detail="Shop inspection template has not been seeded.",
        )
    return template


def _get_outlet(database: Session, organization_id: UUID, outlet_id: UUID):
    outlet = database.scalar(
        select(Outlet).where(
            Outlet.id == outlet_id,
            Outlet.organization_id == organization_id,
        )
    )
    if outlet is None:
        raise HTTPException(status_code=404, detail="Outlet was not found.")
    return outlet


def _get_vendor(database: Session, organization_id: UUID, vendor_id: UUID | None):
    if vendor_id is None:
        return None
    vendor = database.scalar(
        select(Vendor).where(
            Vendor.id == vendor_id,
            Vendor.organization_id == organization_id,
        )
    )
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor was not found.")
    return vendor


def _report_number():
    return f"INS-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3).upper()}"


def create_report(
    database: Session,
    *,
    user: User,
    payload: InspectionCreateRequest,
) -> InspectionReport:
    current_roles = role_codes(database, user)

    if (
        "FIELD_VISITOR" not in current_roles
        or current_roles.intersection(MANAGEMENT_ROLES)
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Only a dedicated FIELD_VISITOR account "
                "can start a shop inspection."
            ),
        )

    if payload.visit_assignment_id is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Start the inspection from your assigned "
                "visit queue. A rotation assignment is required."
            ),
        )

    employee = get_employee_for_user(database, user)
    outlet = _get_outlet(
        database,
        user.organization_id,
        payload.outlet_id,
    )

    validate_visit_assignment_for_start(
        database,
        user=user,
        assignment_id=payload.visit_assignment_id,
        outlet_id=outlet.id,
    )
    ensure_inspection_start_allowed(
        database,
        user,
        payload.visit_assignment_id,
    )

    if outlet.latitude is None or outlet.longitude is None:
        raise HTTPException(
            status_code=409,
            detail="The assigned shop has no coordinates. Admin must add its latitude and longitude before inspection.",
        )

    location = get_latest_fresh_location(database, employee=employee)
    start_distance = calculate_distance_meters(
        location.latitude,
        location.longitude,
        float(outlet.latitude),
        float(outlet.longitude),
    )
    allowed_radius = float(getattr(outlet, "attendance_radius_meters", 150.0) or 150.0)
    if start_distance > allowed_radius:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "You must be at the assigned shop before starting its inspection.",
                "distance_meters": round(start_distance, 2),
                "allowed_radius_meters": allowed_radius,
            },
        )

    resolved_vendor_id = (
        payload.vendor_id
        or getattr(outlet, "vendor_id", None)
    )

    vendor = _get_vendor(
        database,
        user.organization_id,
        resolved_vendor_id,
    )

    template = current_template(
        database,
        user.organization_id,
    )

    if payload.task_assignment_id is not None:
        row = database.execute(
            select(TaskAssignment, Task)
            .join(
                Task,
                TaskAssignment.task_id == Task.id,
            )
            .where(
                TaskAssignment.id
                == payload.task_assignment_id,
                TaskAssignment.organization_id
                == user.organization_id,
                TaskAssignment.employee_id
                == employee.id,
            )
        ).first()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Assigned field-visit task "
                    "was not found."
                ),
            )

        if row[1].task_type != "FIELD_VISIT":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Only FIELD_VISIT assignments "
                    "can be linked to shop inspections."
                ),
            )

    contact_name = (
        vendor.contact_person
        if vendor
        else outlet.vendor_name
    )
    contact_email = (
        vendor.email
        if vendor
        else outlet.vendor_email
    )
    contact_phone = (
        vendor.phone
        if vendor
        else outlet.vendor_phone
    )
    vendor_name = (
        vendor.name
        if vendor
        else outlet.vendor_name
    )

    report = InspectionReport(
        organization_id=user.organization_id,
        template_id=template.id,
        report_number=_report_number(),
        outlet_id=outlet.id,
        vendor_id=vendor.id if vendor else None,
        task_assignment_id=payload.task_assignment_id,
        inspector_employee_id=employee.id,
        inspector_user_id=user.id,
        cluster_name=(
            payload.cluster_name
            or getattr(outlet, "cluster_name", None)
        ),
        inspection_started_at=
            datetime.now(timezone.utc),
        start_latitude=location.latitude,
        start_longitude=location.longitude,
        start_accuracy_meters=location.accuracy_meters,
        start_distance_meters=start_distance,
        location_verified_at=location.recorded_at,
        template_snapshot=template.schema_data,
        answers={},
        section_remarks={},
        attention_flags=[],
        status="DRAFT",
        vendor_name_snapshot=vendor_name,
        vendor_contact_name=contact_name,
        vendor_contact_email=contact_email,
        vendor_contact_phone=contact_phone,
    )

    database.add(report)
    database.flush()

    mark_visit_started(
        database,
        user=user,
        assignment_id=payload.visit_assignment_id,
        report_id=report.id,
    )

    audit(
        database,
        report=report,
        action="CREATED",
        actor_type="USER",
        actor_user_id=user.id,
        extra_data={
            "visit_assignment_id":
                str(payload.visit_assignment_id),
            "assignment_mode":
                "ROTATION",
        },
    )

    database.commit()
    database.refresh(report)
    return report

def _get_report(database: Session, organization_id: UUID, report_id: UUID):
    report = database.scalar(
        select(InspectionReport).where(
            InspectionReport.id == report_id,
            InspectionReport.organization_id == organization_id,
        )
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Inspection report was not found.")
    return report


def _can_view(database: Session, user: User, report: InspectionReport):
    roles = role_codes(database, user)
    if roles.intersection(MANAGEMENT_ROLES):
        return
    if report.inspector_user_id == user.id:
        return
    raise HTTPException(status_code=403, detail="Inspection report access is restricted.")


def get_report(database: Session, *, user: User, report_id: UUID):
    report = _get_report(database, user.organization_id, report_id)
    _can_view(database, user, report)
    return report


def list_reports(
    database: Session,
    *,
    user: User,
    status_filter: str | None = None,
    mine: bool = False,
):
    require_roles(database, user, INSPECTOR_ROLES, "Inspection access is required.")
    statement = select(InspectionReport).where(
        InspectionReport.organization_id == user.organization_id
    )

    roles = role_codes(database, user)
    if mine or not roles.intersection(MANAGEMENT_ROLES):
        statement = statement.where(InspectionReport.inspector_user_id == user.id)

    if status_filter:
        statement = statement.where(
            InspectionReport.status == status_filter.strip().upper()
        )

    return list(
        database.scalars(
            statement.order_by(
                InspectionReport.inspection_started_at.desc(),
                InspectionReport.created_at.desc(),
            )
        ).all()
    )


def _answer_value(answer):
    if isinstance(answer, dict):
        return answer.get("value")
    return answer


def validate_answers(schema: dict, answers: dict):
    missing = []
    detail_missing = []

    for section in schema.get("sections", []):
        for question in section.get("questions", []):
            qid = question["id"]
            qtype = question.get("type", "YES_NO")
            answer = answers.get(qid)

            if qtype == "CONDITIONAL_TEXT":
                depends = question.get("depends_on")
                depends_value = question.get("depends_value")
                visible = _answer_value(answers.get(depends)) == depends_value
                if visible and question.get("required_when_visible") and not str(
                    (answer or {}).get("text", "") if isinstance(answer, dict) else answer or ""
                ).strip():
                    missing.append(qid)
                continue

            value = _answer_value(answer)
            if question.get("required") and value not in {"YES", "NO"}:
                missing.append(qid)
                continue

            required_when = question.get("detail_required_when")
            if required_when and value == required_when:
                details = answer.get("details") if isinstance(answer, dict) else None
                if not (details or "").strip():
                    detail_missing.append(qid)

    if missing or detail_missing:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Inspection checklist is incomplete.",
                "missing_question_ids": missing,
                "missing_detail_question_ids": detail_missing,
            },
        )


def build_attention_flags(schema: dict, answers: dict) -> list[dict]:
    flags = []
    for section in schema.get("sections", []):
        for question in section.get("questions", []):
            risk_when = question.get("risk_when")
            if not risk_when:
                continue
            answer = answers.get(question["id"])
            value = _answer_value(answer)
            if value == risk_when:
                flags.append(
                    {
                        "section_id": section["id"],
                        "section": section["title"],
                        "question_id": question["id"],
                        "question": question["label"],
                        "answer": value,
                        "details": answer.get("details") if isinstance(answer, dict) else None,
                    }
                )
    return flags


def save_draft(
    database: Session,
    *,
    user: User,
    report_id: UUID,
    payload: InspectionDraftUpdateRequest,
):
    report = _get_report(database, user.organization_id, report_id)
    if report.inspector_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the assigned inspector can edit this draft.")
    if report.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Submitted inspection reports are locked.")

    report.answers = payload.answers
    report.section_remarks = payload.section_remarks
    report.attention_flags = build_attention_flags(report.template_snapshot, payload.answers)
    audit(
        database,
        report=report,
        action="DRAFT_SAVED",
        actor_type="USER",
        actor_user_id=user.id,
    )
    database.commit()
    database.refresh(report)
    return report


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _public_url(token: str) -> str:
    base = os.getenv("PUBLIC_FRONTEND_URL", "http://127.0.0.1:5173").strip().rstrip("/")
    return f"{base}/vendor-inspection/{token}"


# VENDOR_PORTAL_LOGIN_GATE_V1
def _vendor_portal_url() -> str:
    base = os.getenv("PUBLIC_FRONTEND_URL", "http://127.0.0.1:5173").strip().rstrip("/")
    return f"{base}/vendor-login"


def _vendor_uses_portal(database: Session, report: InspectionReport) -> bool:
    if getattr(report, "vendor_id", None) is None:
        return False
    from sqlalchemy import text as _portal_text

    return bool(
        database.execute(
            _portal_text(
                "SELECT EXISTS ("
                "SELECT 1 FROM vendor_portal_accounts "
                "WHERE organization_id=:org AND vendor_id=:vendor_id"
                ")"
            ),
            {"org": report.organization_id, "vendor_id": report.vendor_id},
        ).scalar()
    )


def _send_vendor_email(report: InspectionReport, review_url: str) -> str:
    if not report.vendor_contact_email:
        return "MANUAL_SHARE_REQUIRED"

    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return "MANUAL_SHARE_REQUIRED"

    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", username).strip()
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"

    message = EmailMessage()
    message["Subject"] = f"Shop inspection report {report.report_number} - review required"
    message["From"] = sender
    message["To"] = report.vendor_contact_email
    message.set_content(
        "A shop inspection report has been submitted for your review.\n\n"
        f"Report: {report.report_number}\n"
        f"Review link: {review_url}\n\n"
        "Please accept or dispute the report. A digital signature is optional."
    )

    try:
        smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_class(host, port, timeout=30) as smtp:
            if use_tls and not use_ssl:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return "EMAIL_SENT"
    except Exception:
        return "EMAIL_FAILED_MANUAL_SHARE_REQUIRED"


def notify_management(database: Session, report: InspectionReport, title: str, body: str, suffix: str):
    users = list(
        database.scalars(
            select(User)
            .join(user_roles, User.id == user_roles.c.user_id)
            .join(Role, Role.id == user_roles.c.role_id)
            .where(
                User.organization_id == report.organization_id,
                Role.code.in_(MANAGEMENT_ROLES),
            )
            .distinct()
        ).all()
    )
    now = datetime.now(timezone.utc)
    for recipient in users:
        database.add(
            Notification(
                organization_id=report.organization_id,
                recipient_user_id=recipient.id,
                channel="IN_APP",
                title=title,
                body=body,
                payload={
                    "type": "SHOP_INSPECTION",
                    "inspection_report_id": str(report.id),
                    "report_number": report.report_number,
                },
                dedupe_key=f"inspection:{report.id}:{suffix}:{recipient.id}",
                status="PENDING",
                attempts=0,
                available_at=now,
            )
        )


def submit_report(
    database: Session,
    *,
    user: User,
    report_id: UUID,
    payload: InspectionSubmitRequest,
):
    report = _get_report(database, user.organization_id, report_id)
    if report.inspector_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the assigned inspector can submit this report.")
    if report.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Inspection report has already been submitted.")

    validate_answers(report.template_snapshot, payload.answers)

    report.answers = payload.answers
    report.section_remarks = payload.section_remarks
    report.attention_flags = build_attention_flags(report.template_snapshot, payload.answers)
    report.inspector_signature_data_uri = payload.inspector_signature_data_uri or None
    report.submitted_at = datetime.now(timezone.utc)
    report.ho_received_at = report.submitted_at
    report.status = "VENDOR_PENDING"

    if _vendor_uses_portal(database, report):
        # A portal account means login is mandatory. Do not create a usable public token.
        report.vendor_access_token_hash = None
        report.vendor_token_expires_at = None
        review_url = _vendor_portal_url()
    else:
        # Legacy fallback for vendors that have not yet been given a portal account.
        raw_token = secrets.token_urlsafe(32)
        report.vendor_access_token_hash = _token_hash(raw_token)
        report.vendor_token_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
        review_url = _public_url(raw_token)

    audit(
        database,
        report=report,
        action="SUBMITTED_VENDOR_PENDING",
        actor_type="USER",
        actor_user_id=user.id,
        extra_data={"attention_flag_count": len(report.attention_flags)},
    )

    notify_management(
        database,
        report,
        title=f"Inspection submitted: {report.report_number}",
        body=f"Field inspection submitted and awaiting vendor response. Flags: {len(report.attention_flags)}.",
        suffix="submitted",
    )

    notification_status = _send_vendor_email(report, review_url)

    mark_visit_submitted(
        database,
        organization_id=report.organization_id,
        report_id=report.id,
    )

    database.commit()
    database.refresh(report)
    return report, review_url, notification_status


def regenerate_vendor_link(database: Session, *, user: User, report_id: UUID):
    require_roles(database, user, MANAGEMENT_ROLES, "Management access is required.")
    report = _get_report(database, user.organization_id, report_id)
    if report.status not in {"VENDOR_PENDING"}:
        raise HTTPException(status_code=409, detail="Vendor link can only be regenerated while vendor response is pending.")

    if _vendor_uses_portal(database, report):
        # A portal account means login is mandatory. Do not create a usable public token.
        report.vendor_access_token_hash = None
        report.vendor_token_expires_at = None
        review_url = _vendor_portal_url()
    else:
        # Legacy fallback for vendors that have not yet been given a portal account.
        raw_token = secrets.token_urlsafe(32)
        report.vendor_access_token_hash = _token_hash(raw_token)
        report.vendor_token_expires_at = datetime.now(timezone.utc) + timedelta(days=14)
        review_url = _public_url(raw_token)
    notification_status = _send_vendor_email(report, review_url)

    audit(
        database,
        report=report,
        action="VENDOR_LINK_REGENERATED",
        actor_type="USER",
        actor_user_id=user.id,
    )
    database.commit()
    return {"vendor_review_url": review_url, "vendor_notification_status": notification_status}


def _public_report(database: Session, token: str):
    report = database.scalar(
        select(InspectionReport).where(
            InspectionReport.vendor_access_token_hash == _token_hash(token)
        )
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Inspection review link is invalid.")
    if report.vendor_token_expires_at and report.vendor_token_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Inspection review link has expired.")
    if _vendor_uses_portal(database, report):
        raise HTTPException(
            status_code=403,
            detail="This vendor uses Vendor Portal. Sign in at /vendor-login to review this inspection.",
        )
    return report


def public_report(database: Session, *, token: str, ip_address: str | None, user_agent: str | None):
    report = _public_report(database, token)
    outlet = database.scalar(select(Outlet).where(Outlet.id == report.outlet_id))
    inspector = database.scalar(select(Employee).where(Employee.id == report.inspector_employee_id))
    if report.vendor_opened_at is None:
        report.vendor_opened_at = datetime.now(timezone.utc)
        audit(
            database,
            report=report,
            action="VENDOR_OPENED",
            actor_type="VENDOR",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        database.commit()

    inspector_name = " ".join(
        part for part in [getattr(inspector, "first_name", None), getattr(inspector, "last_name", None)] if part
    ).strip() or "Inspection Team"

    return {
        "report_number": report.report_number,
        "version": report.version,
        "outlet_name": outlet.name if outlet else "Outlet",
        "outlet_address": outlet.address if outlet else "",
        "cluster_name": report.cluster_name,
        "inspector_name": inspector_name,
        "inspection_started_at": report.inspection_started_at,
        "submitted_at": report.submitted_at,
        "template_snapshot": report.template_snapshot,
        "answers": report.answers,
        "section_remarks": report.section_remarks,
        "attention_flags": report.attention_flags,
        "status": report.status,
        "vendor_name": report.vendor_name_snapshot,
        "vendor_response": report.vendor_response,
        "vendor_response_name": report.vendor_response_name,
        "vendor_remarks": report.vendor_remarks,
        "vendor_responded_at": report.vendor_responded_at,
        "inspector_signature_data_uri": report.inspector_signature_data_uri,
        "vendor_signature_data_uri": report.vendor_signature_data_uri,
    }


def vendor_respond(
    database: Session,
    *,
    token: str,
    payload: VendorInspectionResponseRequest,
    ip_address: str | None,
    user_agent: str | None,
):
    report = _public_report(database, token)
    if report.status != "VENDOR_PENDING":
        raise HTTPException(status_code=409, detail="Vendor response has already been recorded.")

    report.vendor_response = payload.response
    report.vendor_response_name = payload.vendor_name.strip()
    report.vendor_remarks = (payload.remarks or "").strip() or None
    report.vendor_signature_data_uri = payload.signature_data_uri or None
    report.vendor_responded_at = datetime.now(timezone.utc)
    report.vendor_response_ip = ip_address
    report.vendor_response_user_agent = user_agent
    report.status = "ACCEPTED" if payload.response == "ACCEPT" else "DISPUTED"

    audit(
        database,
        report=report,
        action=f"VENDOR_{payload.response}",
        actor_type="VENDOR",
        note=report.vendor_remarks,
        ip_address=ip_address,
        user_agent=user_agent,
        extra_data={"signature_provided": bool(payload.signature_data_uri)},
    )

    notify_management(
        database,
        report,
        title=f"Vendor {payload.response.lower()}: {report.report_number}",
        body=f"Vendor response recorded for shop inspection {report.report_number}.",
        suffix=f"vendor-{payload.response.lower()}",
    )

    database.commit()
    database.refresh(report)
    return report


def acknowledge_ho(
    database: Session,
    *,
    user: User,
    report_id: UUID,
    payload: HoAcknowledgeRequest,
):
    require_roles(database, user, MANAGEMENT_ROLES, "Management access is required.")
    report = _get_report(database, user.organization_id, report_id)
    if report.status not in {"ACCEPTED", "DISPUTED"}:
        raise HTTPException(status_code=409, detail="Vendor response is required before HO acknowledgement.")

    report.status = "HO_ACKNOWLEDGED"
    report.ho_acknowledged_at = datetime.now(timezone.utc)
    report.ho_acknowledged_by_user_id = user.id
    report.ho_acknowledgement_note = payload.note
    audit(
        database,
        report=report,
        action="HO_ACKNOWLEDGED",
        actor_type="USER",
        actor_user_id=user.id,
        note=payload.note,
    )
    database.commit()
    database.refresh(report)
    return report


def close_report(database: Session, *, user: User, report_id: UUID):
    require_roles(database, user, MANAGEMENT_ROLES, "Management access is required.")
    report = _get_report(database, user.organization_id, report_id)
    if report.status != "HO_ACKNOWLEDGED":
        raise HTTPException(status_code=409, detail="HO acknowledgement is required before closing the report.")

    report.status = "CLOSED"
    report.closed_at = datetime.now(timezone.utc)
    report.closed_by_user_id = user.id
    audit(
        database,
        report=report,
        action="CLOSED",
        actor_type="USER",
        actor_user_id=user.id,
    )

    mark_visit_completed(
        database,
        organization_id=report.organization_id,
        report_id=report.id,
    )

    database.commit()
    database.refresh(report)
    return report


def create_revision(database: Session, *, user: User, report_id: UUID):
    original = _get_report(database, user.organization_id, report_id)
    _can_view(database, user, original)
    if original.inspector_user_id != user.id and not role_codes(database, user).intersection(MANAGEMENT_ROLES):
        raise HTTPException(status_code=403, detail="Revision access is restricted.")

    revision = InspectionReport(
        organization_id=original.organization_id,
        template_id=original.template_id,
        report_number=_report_number(),
        version=original.version + 1,
        previous_report_id=original.id,
        outlet_id=original.outlet_id,
        vendor_id=original.vendor_id,
        task_assignment_id=original.task_assignment_id,
        inspector_employee_id=original.inspector_employee_id,
        inspector_user_id=original.inspector_user_id,
        cluster_name=original.cluster_name,
        inspection_started_at=datetime.now(timezone.utc),
        start_latitude=original.start_latitude,
        start_longitude=original.start_longitude,
        start_accuracy_meters=original.start_accuracy_meters,
        start_distance_meters=original.start_distance_meters,
        location_verified_at=original.location_verified_at,
        template_snapshot=original.template_snapshot,
        answers=original.answers,
        section_remarks=original.section_remarks,
        attention_flags=original.attention_flags,
        status="DRAFT",
        vendor_name_snapshot=original.vendor_name_snapshot,
        vendor_contact_name=original.vendor_contact_name,
        vendor_contact_email=original.vendor_contact_email,
        vendor_contact_phone=original.vendor_contact_phone,
    )
    database.add(revision)
    database.flush()
    audit(
        database,
        report=revision,
        action="REVISION_CREATED",
        actor_type="USER",
        actor_user_id=user.id,
        extra_data={"previous_report_id": str(original.id)},
    )
    database.commit()
    database.refresh(revision)
    return revision


def dashboard(database: Session, *, user: User):
    require_roles(database, user, MANAGEMENT_ROLES, "Management access is required.")
    reports = list(
        database.scalars(
            select(InspectionReport)
            .where(InspectionReport.organization_id == user.organization_id)
            .order_by(InspectionReport.inspection_started_at.desc())
        ).all()
    )
    statuses = ["DRAFT", "VENDOR_PENDING", "ACCEPTED", "DISPUTED", "HO_ACKNOWLEDGED", "CLOSED"]
    counts = {status: sum(1 for report in reports if report.status == status) for status in statuses}
    counts["ATTENTION"] = sum(1 for report in reports if report.attention_flags)
    attention_reports = [report for report in reports if report.attention_flags][:20]
    return {"counts": counts, "attention_reports": attention_reports}
