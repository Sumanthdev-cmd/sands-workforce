"""Tenant-scoped, server-calculated costs and an MD-gated payment register."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.models import Notification, Role, User, user_roles
from app.models.box_loading import BoxLoadingAction, BoxLoadingRequest

STATES = {"DRAFT", "PENDING_MD", "APPROVED", "REJECTED", "PAID"}
INPUT_FIELDS = ("loading_date", "vehicle_type", "vehicle_number", "loading_rate", "loading_box_count", "transport_rate", "transport_box_count", "notes")
MONEY_FIELDS = {"loading_rate", "transport_rate", "loading_cost", "transport_cost", "total_amount", "paid_amount"}


def roles_for(database, user):
    # No superuser bypass: sanctioning requires the MD role in this organisation.
    return set(database.scalars(select(Role.code).join(user_roles, Role.id == user_roles.c.role_id).where(
        user_roles.c.user_id == user.id, Role.organization_id == user.organization_id, Role.is_active.is_(True))))


def require_role(database, user, allowed):
    if not user.is_active or not roles_for(database, user).intersection(allowed):
        raise HTTPException(403, "This action requires " + " or ".join(sorted(allowed)) + " access.")


def calculated_inputs(payload):
    values = {field: getattr(payload, field) for field in INPUT_FIELDS}
    for field in ("loading_rate", "transport_rate"):
        values[field] = values[field].quantize(Decimal("0.01"))
    values["loading_cost"] = values["loading_rate"] * values["loading_box_count"]
    values["transport_cost"] = values["transport_rate"] * values["transport_box_count"]
    values["total_amount"] = values["loading_cost"] + values["transport_cost"]
    return values


def record_data(row):
    result = {}
    for column in row.__table__.columns:
        name = column.name
        if name in {"creation_fingerprint", "client_request_id", "organization_id"}:
            continue
        value = getattr(row, name)
        if value is not None:
            if name in MONEY_FIELDS:
                value = format(value, ".2f")
            elif hasattr(value, "isoformat"):
                value = value.isoformat()
            elif column.type.python_type.__name__ == "UUID":
                value = str(value)
        result[name] = value
    result["reference"] = "BOX-" + str(row.id).replace("-", "")[:12].upper()
    return result


def audit(database, row, user, action, note=None):
    database.add(BoxLoadingAction(id=uuid4(), organization_id=row.organization_id, request_id=row.id,
        actor_user_id=user.id, actor_code=user.employee_code, action=action, version=row.version,
        note=note, snapshot=record_data(row), created_at=datetime.now(timezone.utc)))


def role_recipients(database, user, roles):
    return list(database.scalars(select(User.id).join(user_roles, User.id == user_roles.c.user_id)
        .join(Role, Role.id == user_roles.c.role_id).where(User.organization_id == user.organization_id,
        User.is_active.is_(True), Role.organization_id == user.organization_id, Role.is_active.is_(True),
        Role.code.in_(roles)).distinct()))


def notify(database, row, recipients, event, title, body):
    for recipient in set(recipients):
        # Queue in the same transaction as the action. The installed worker
        # handles Android delivery; no live provider call happens in the API.
        database.add(Notification(organization_id=row.organization_id, recipient_user_id=recipient,
            channel="IN_APP", title=title, body=body, status="PENDING", attempts=0,
            available_at=datetime.now(timezone.utc),
            payload={"module": "box-loading", "event": event, "entity_id": str(row.id),
                     "route": "/module/box-loading?request=" + str(row.id)},
            dedupe_key=f"box-loading:{row.id}:{row.version}:{event}:{recipient}"))


def finish(database, row):
    database.commit()
    database.refresh(row)
    return record_data(row)


def get_record(database, user, request_id, *, lock=False):
    statement = select(BoxLoadingRequest).where(BoxLoadingRequest.id == request_id,
        BoxLoadingRequest.organization_id == user.organization_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = database.scalar(statement)
    if row is None:
        raise HTTPException(404, "Box loading request was not found in your organisation.")
    return row


def require_version(row, expected):
    if row.version != expected:
        raise HTTPException(409, "This request has changed. Refresh it before taking another action.")


def create_request(database, user, payload):
    require_role(database, user, {"ADMIN"})
    values = calculated_inputs(payload)
    fingerprint = hashlib.sha256(json.dumps(values, default=str, sort_keys=True).encode()).hexdigest()

    def existing():
        row = database.scalar(select(BoxLoadingRequest).where(BoxLoadingRequest.organization_id == user.organization_id,
            BoxLoadingRequest.created_by_user_id == user.id, BoxLoadingRequest.client_request_id == payload.client_request_id))
        if row is not None and row.creation_fingerprint != fingerprint:
            raise HTTPException(409, "An earlier save used this request ID with different details. Refresh and check the register before creating another request.")
        return row

    row = existing()
    if row:
        return record_data(row)
    row = BoxLoadingRequest(id=uuid4(), organization_id=user.organization_id, created_by_user_id=user.id,
        created_by_code=user.employee_code, client_request_id=payload.client_request_id,
        creation_fingerprint=fingerprint, status="DRAFT", version=1, **values)
    database.add(row)
    try:
        database.flush()
        audit(database, row, user, "CREATED")
        return finish(database, row)
    except IntegrityError:
        database.rollback()
        retry = existing()
        if retry is not None:
            return record_data(retry)
        raise


def update_request(database, user, request_id, payload):
    require_role(database, user, {"ADMIN"})
    row = get_record(database, user, request_id, lock=True)
    require_version(row, payload.expected_version)
    if row.status not in {"DRAFT", "REJECTED"}:
        raise HTTPException(409, "Only draft or rejected requests can be edited. Submitted and approved costs are locked.")
    for name, value in calculated_inputs(payload).items():
        setattr(row, name, value)
    row.status = "DRAFT"
    row.version += 1
    row.submitted_at = row.submitted_by_user_id = row.submitted_by_code = None
    row.md_user_id = row.md_code = row.decided_at = row.decision_note = None
    audit(database, row, user, "UPDATED", "Saved as draft. Previous decisions remain in the history.")
    return finish(database, row)


def submit_request(database, user, request_id, payload):
    require_role(database, user, {"ADMIN"})
    row = get_record(database, user, request_id, lock=True)
    require_version(row, payload.expected_version)
    if row.status != "DRAFT":
        raise HTTPException(409, "Only a draft can be submitted. Edit a rejected request before resubmitting.")
    if row.total_amount <= 0:
        raise HTTPException(422, "The total amount must be greater than zero before submission.")
    recipients = role_recipients(database, user, {"MD"})
    if not recipients:
        raise HTTPException(409, "No active MD login is configured for your organisation. The request remains a draft.")
    row.status = "PENDING_MD"
    row.version += 1
    row.submitted_by_user_id = user.id
    row.submitted_by_code = user.employee_code
    row.submitted_at = datetime.now(timezone.utc)
    audit(database, row, user, "SUBMITTED")
    notify(database, row, recipients, "BOX_LOADING_SUBMITTED", "Box loading approval required",
           f"{row.vehicle_number}: INR {row.total_amount:.2f} requested by {user.employee_code}. Review and sanction in Box Loading.")
    return finish(database, row)


def decide_request(database, user, request_id, payload):
    require_role(database, user, {"MD"})
    row = get_record(database, user, request_id, lock=True)
    require_version(row, payload.expected_version)
    if row.status != "PENDING_MD":
        raise HTTPException(409, "Only requests awaiting MD approval can be decided.")
    row.status = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
    row.version += 1
    row.md_user_id = user.id
    row.md_code = user.employee_code
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = payload.note
    audit(database, row, user, row.status, payload.note)
    notify(database, row, role_recipients(database, user, {"ADMIN"}), "BOX_LOADING_" + row.status,
           "Box loading " + row.status.lower(),
           f"{row.vehicle_number}: INR {row.total_amount:.2f} was {row.status.lower()} by {user.employee_code}.")
    return finish(database, row)


def record_disbursement(database, user, request_id, payload):
    require_role(database, user, {"ADMIN"})
    row = get_record(database, user, request_id, lock=True)
    require_version(row, payload.expected_version)
    if row.status != "APPROVED" or row.md_user_id is None or row.decided_at is None:
        raise HTTPException(409, "Disbursement can be recorded only after MD approval, and only once.")
    try:
        local_zone = ZoneInfo(getattr(user.organization, "timezone", None) or "Asia/Kolkata")
    except ZoneInfoNotFoundError:
        local_zone = ZoneInfo("Asia/Kolkata")
    approved_at = row.decided_at
    if approved_at.tzinfo is None:
        approved_at = approved_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if not approved_at.astimezone(local_zone).date() <= payload.payment_date <= now.astimezone(local_zone).date():
        raise HTTPException(422, "The payment date must be on or after MD approval and cannot be in the future.")
    row.status = "PAID"
    row.version += 1
    row.paid_by_user_id = user.id
    row.paid_by_code = user.employee_code
    row.paid_at = now
    row.paid_amount = row.total_amount
    row.payment_date = payload.payment_date
    row.payment_mode = payload.payment_mode
    row.payment_reference = payload.payment_reference
    row.paid_to = payload.paid_to
    audit(database, row, user, "PAID", "Approved amount recorded as disbursed.")
    notify(database, row, role_recipients(database, user, {"MD"}), "BOX_LOADING_PAID", "Box loading disbursement recorded",
           f"{row.vehicle_number}: INR {row.total_amount:.2f} recorded as paid to {row.paid_to} by {user.employee_code}.")
    return finish(database, row)


def list_requests(database, user, *, from_date=None, to_date=None, status=None, search="", offset=0, limit=25):
    require_role(database, user, {"ADMIN", "MD"})
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, "From date must be on or before To date.")
    if status and status not in STATES:
        raise HTTPException(422, "Choose a supported request status.")
    statement = select(BoxLoadingRequest).where(BoxLoadingRequest.organization_id == user.organization_id)
    if from_date:
        statement = statement.where(BoxLoadingRequest.loading_date >= from_date)
    if to_date:
        statement = statement.where(BoxLoadingRequest.loading_date <= to_date)
    if status:
        statement = statement.where(BoxLoadingRequest.status == status)
    if search.strip():
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = "%" + escaped + "%"
        statement = statement.where(or_(BoxLoadingRequest.vehicle_number.ilike(term, escape="\\"),
            BoxLoadingRequest.created_by_code.ilike(term, escape="\\")))
    total = database.scalar(select(func.count()).select_from(statement.subquery()))
    rows = database.scalars(statement.order_by(BoxLoadingRequest.loading_date.desc(), BoxLoadingRequest.created_at.desc(),
        BoxLoadingRequest.id).offset(offset).limit(limit))
    return {"items": [record_data(row) for row in rows], "total": total, "offset": offset, "limit": limit}


def request_detail(database, user, request_id):
    require_role(database, user, {"ADMIN", "MD"})
    row = get_record(database, user, request_id)
    actions = database.scalars(select(BoxLoadingAction).where(BoxLoadingAction.organization_id == user.organization_id,
        BoxLoadingAction.request_id == row.id).order_by(BoxLoadingAction.version))
    return {**record_data(row), "actions": [{"id": str(action.id), "action": action.action,
        "actor_code": action.actor_code, "note": action.note, "version": action.version,
        "created_at": action.created_at.isoformat(), "snapshot": action.snapshot} for action in actions]}
