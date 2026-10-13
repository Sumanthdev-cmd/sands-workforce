from __future__ import annotations

import hashlib
import secrets
import string
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InspectionAuditEvent, InspectionReport, Role, User, user_roles
from app.services.notification_service import queue_role_notifications
from app.services.storage_service import DEFAULT_PRESIGN_EXPIRY_SECONDS, create_download_url
from app.services.attendance_service import calculate_distance_meters


PASSWORD_HASHER = PasswordHash.recommended()
MANAGEMENT_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}
LOCATION_MONITOR_ROLES = {"ADMIN", "MD", "GM"}
ADMIN_ROLES = {"ADMIN"}
SESSION_HOURS = 12
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15


@dataclass(frozen=True)
class VendorPortalContext:
    account_id: UUID
    session_id: UUID
    organization_id: UUID
    vendor_id: UUID
    organization_code: str
    vendor_code: str
    vendor_name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    status: str
    force_password_change: bool
    last_login_at: datetime | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(database: Session, sql: str, params: dict) -> dict | None:
    value = database.execute(text(sql), params).mappings().first()
    return dict(value) if value else None


def _rows(database: Session, sql: str, params: dict) -> list[dict]:
    return [dict(value) for value in database.execute(text(sql), params).mappings().all()]


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_management(database: Session, user: User) -> None:
    if not role_codes(database, user).intersection(MANAGEMENT_ROLES):
        raise HTTPException(status_code=403, detail="Vendor portal management access is required.")


def require_admin(database: Session, user: User) -> None:
    if not role_codes(database, user).intersection(ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="Only Admin can manage vendor login credentials.")


def _temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "Vnd@" + "".join(secrets.choice(alphabet) for _ in range(10))


def _account_query(where_sql: str) -> str:
    return f"""
        SELECT
            a.id,
            a.vendor_id,
            a.organization_id,
            o.code AS organization_code,
            v.code AS vendor_code,
            v.name AS vendor_name,
            v.contact_person,
            v.phone,
            v.email,
            a.status,
            a.force_password_change,
            a.last_login_at,
            a.created_at
        FROM vendor_portal_accounts a
        JOIN vendors v ON v.id = a.vendor_id
        JOIN organizations o ON o.id = a.organization_id
        WHERE {where_sql}
    """


def list_admin_accounts(database: Session, user: User) -> list[dict]:
    require_management(database, user)
    return _rows(
        database,
        _account_query("a.organization_id = :org") + " ORDER BY v.code",
        {"org": user.organization_id},
    )


def create_admin_account(database: Session, user: User, vendor_id: UUID, temporary_password: str | None) -> dict:
    require_admin(database, user)
    vendor = _row(
        database,
        """
        SELECT v.id, v.code, v.name, o.code AS organization_code
        FROM vendors v
        JOIN organizations o ON o.id = v.organization_id
        WHERE v.id = :vendor_id AND v.organization_id = :org
        """,
        {"vendor_id": vendor_id, "org": user.organization_id},
    )
    if vendor is None:
        raise HTTPException(status_code=404, detail="Vendor was not found in this organization.")

    existing = _row(
        database,
        "SELECT id FROM vendor_portal_accounts WHERE organization_id=:org AND vendor_id=:vendor_id",
        {"org": user.organization_id, "vendor_id": vendor_id},
    )
    if existing:
        raise HTTPException(status_code=409, detail="This vendor already has a portal account.")

    raw_password = temporary_password or _temporary_password()
    account_id = uuid4()
    now = _now()
    try:
        database.execute(
            text(
                """
                INSERT INTO vendor_portal_accounts (
                    id, organization_id, vendor_id, password_hash, status,
                    force_password_change, created_by_user_id, failed_login_attempts,
                    created_at, updated_at
                ) VALUES (
                    :id, :org, :vendor_id, :password_hash, 'ACTIVE',
                    true, :created_by, 0, :now, :now
                )
                """
            ),
            {
                "id": account_id,
                "org": user.organization_id,
                "vendor_id": vendor_id,
                "password_hash": PASSWORD_HASHER.hash(raw_password),
                "created_by": user.id,
                "now": now,
            },
        )
        database.commit()
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(status_code=409, detail="Vendor portal account already exists.") from error

    result = _row(database, _account_query("a.id = :id"), {"id": account_id})
    result["temporary_password"] = raw_password
    return result


def _admin_account(database: Session, user: User, account_id: UUID) -> dict:
    row = _row(
        database,
        _account_query("a.id = :id AND a.organization_id = :org"),
        {"id": account_id, "org": user.organization_id},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Vendor portal account was not found.")
    return row


def reset_admin_password(database: Session, user: User, account_id: UUID, temporary_password: str | None) -> dict:
    require_admin(database, user)
    _admin_account(database, user, account_id)
    raw_password = temporary_password or _temporary_password()
    now = _now()
    database.execute(
        text(
            """
            UPDATE vendor_portal_accounts
            SET password_hash=:password_hash, force_password_change=true,
                failed_login_attempts=0, locked_until=NULL, updated_at=:now
            WHERE id=:id AND organization_id=:org
            """
        ),
        {
            "password_hash": PASSWORD_HASHER.hash(raw_password),
            "now": now,
            "id": account_id,
            "org": user.organization_id,
        },
    )
    database.execute(
        text(
            """
            UPDATE vendor_portal_sessions
            SET revoked_at=:now, updated_at=:now
            WHERE account_id=:id AND revoked_at IS NULL
            """
        ),
        {"now": now, "id": account_id},
    )
    database.commit()
    result = _admin_account(database, user, account_id)
    result["temporary_password"] = raw_password
    return result


def set_account_status(database: Session, user: User, account_id: UUID, enabled: bool) -> dict:
    require_admin(database, user)
    _admin_account(database, user, account_id)
    now = _now()
    new_status = "ACTIVE" if enabled else "DISABLED"
    database.execute(
        text(
            """
            UPDATE vendor_portal_accounts
            SET status=:status, failed_login_attempts=0, locked_until=NULL, updated_at=:now
            WHERE id=:id AND organization_id=:org
            """
        ),
        {"status": new_status, "now": now, "id": account_id, "org": user.organization_id},
    )
    if not enabled:
        database.execute(
            text(
                """
                UPDATE vendor_portal_sessions
                SET revoked_at=:now, updated_at=:now
                WHERE account_id=:id AND revoked_at IS NULL
                """
            ),
            {"now": now, "id": account_id},
        )
    database.commit()
    return _admin_account(database, user, account_id)


def login_vendor(
    database: Session,
    organization_code: str,
    vendor_code: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
) -> dict:
    account = _row(
        database,
        """
        SELECT
            a.id, a.organization_id, a.vendor_id, a.password_hash, a.status,
            a.force_password_change, a.failed_login_attempts, a.locked_until,
            v.code AS vendor_code, v.name AS vendor_name, v.contact_person,
            v.phone, v.email, o.code AS organization_code
        FROM vendor_portal_accounts a
        JOIN vendors v ON v.id = a.vendor_id
        JOIN organizations o ON o.id = a.organization_id
        WHERE UPPER(o.code) = :organization_code
          AND UPPER(v.code) = :vendor_code
        LIMIT 1
        """,
        {"organization_code": organization_code.upper(), "vendor_code": vendor_code.upper()},
    )

    generic_error = HTTPException(status_code=401, detail="Invalid organization code, vendor code or password.")
    if account is None:
        raise generic_error
    if account["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Vendor portal account is disabled. Contact your administrator.")

    now = _now()
    locked_until = account.get("locked_until")
    if locked_until and locked_until > now:
        raise HTTPException(status_code=429, detail="Too many failed sign-in attempts. Try again later.")

    try:
        valid = PASSWORD_HASHER.verify(password, account["password_hash"])
    except Exception:
        valid = False

    if not valid:
        attempts = int(account.get("failed_login_attempts") or 0) + 1
        new_lock = now + timedelta(minutes=LOCK_MINUTES) if attempts >= MAX_FAILED_LOGINS else None
        database.execute(
            text(
                """
                UPDATE vendor_portal_accounts
                SET failed_login_attempts=:attempts, locked_until=:locked_until, updated_at=:now
                WHERE id=:id
                """
            ),
            {"attempts": attempts, "locked_until": new_lock, "now": now, "id": account["id"]},
        )
        database.commit()
        if new_lock:
            raise HTTPException(status_code=429, detail="Too many failed sign-in attempts. Try again in 15 minutes.")
        raise generic_error

    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = now + timedelta(hours=SESSION_HOURS)
    session_id = uuid4()

    database.execute(
        text(
            """
            INSERT INTO vendor_portal_sessions (
                id, account_id, token_hash, expires_at, ip_address, user_agent,
                created_at, updated_at
            ) VALUES (
                :id, :account_id, :token_hash, :expires_at, :ip_address, :user_agent,
                :now, :now
            )
            """
        ),
        {
            "id": session_id,
            "account_id": account["id"],
            "token_hash": token_hash,
            "expires_at": expires_at,
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:1000] or None,
            "now": now,
        },
    )
    database.execute(
        text(
            """
            UPDATE vendor_portal_accounts
            SET last_login_at=:now, failed_login_attempts=0, locked_until=NULL, updated_at=:now
            WHERE id=:id
            """
        ),
        {"now": now, "id": account["id"]},
    )
    database.commit()

    return {
        "access_token": raw_token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "force_password_change": bool(account["force_password_change"]),
        "organization_code": account["organization_code"],
        "vendor_code": account["vendor_code"],
        "vendor_name": account["vendor_name"],
    }


def authenticate_vendor_session(database: Session, raw_token: str) -> VendorPortalContext:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    row = _row(
        database,
        """
        SELECT
            s.id AS session_id, s.expires_at, s.revoked_at,
            a.id AS account_id, a.organization_id, a.vendor_id, a.status,
            a.force_password_change, a.last_login_at,
            o.code AS organization_code,
            v.code AS vendor_code, v.name AS vendor_name, v.contact_person,
            v.phone, v.email
        FROM vendor_portal_sessions s
        JOIN vendor_portal_accounts a ON a.id = s.account_id
        JOIN organizations o ON o.id = a.organization_id
        JOIN vendors v ON v.id = a.vendor_id
        WHERE s.token_hash=:token_hash
        LIMIT 1
        """,
        {"token_hash": token_hash},
    )
    if row is None or row.get("revoked_at") is not None:
        raise HTTPException(status_code=401, detail="Vendor session is invalid or expired.")
    now = _now()
    if row["expires_at"] <= now:
        database.execute(
            text("UPDATE vendor_portal_sessions SET revoked_at=:now, updated_at=:now WHERE id=:id"),
            {"now": now, "id": row["session_id"]},
        )
        database.commit()
        raise HTTPException(status_code=401, detail="Vendor session has expired. Sign in again.")
    if row["status"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Vendor portal account is disabled.")

    return VendorPortalContext(
        account_id=row["account_id"],
        session_id=row["session_id"],
        organization_id=row["organization_id"],
        vendor_id=row["vendor_id"],
        organization_code=row["organization_code"],
        vendor_code=row["vendor_code"],
        vendor_name=row["vendor_name"],
        contact_person=row.get("contact_person"),
        phone=row.get("phone"),
        email=row.get("email"),
        status=row["status"],
        force_password_change=bool(row["force_password_change"]),
        last_login_at=row.get("last_login_at"),
    )


def vendor_me(context: VendorPortalContext) -> dict:
    return {
        "organization_code": context.organization_code,
        "vendor_code": context.vendor_code,
        "vendor_name": context.vendor_name,
        "contact_person": context.contact_person,
        "phone": context.phone,
        "email": context.email,
        "status": context.status,
        "force_password_change": context.force_password_change,
        "last_login_at": context.last_login_at,
    }


def logout_vendor(database: Session, context: VendorPortalContext) -> None:
    now = _now()
    database.execute(
        text("UPDATE vendor_portal_sessions SET revoked_at=:now, updated_at=:now WHERE id=:id"),
        {"now": now, "id": context.session_id},
    )
    database.commit()


def change_vendor_password(
    database: Session,
    context: VendorPortalContext,
    current_password: str,
    new_password: str,
) -> dict:
    row = _row(database, "SELECT password_hash FROM vendor_portal_accounts WHERE id=:id", {"id": context.account_id})
    if row is None:
        raise HTTPException(status_code=404, detail="Vendor portal account was not found.")
    try:
        valid = PASSWORD_HASHER.verify(current_password, row["password_hash"])
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    now = _now()
    database.execute(
        text(
            """
            UPDATE vendor_portal_accounts
            SET password_hash=:password_hash, force_password_change=false,
                password_changed_at=:now, failed_login_attempts=0,
                locked_until=NULL, updated_at=:now
            WHERE id=:id
            """
        ),
        {"password_hash": PASSWORD_HASHER.hash(new_password), "now": now, "id": context.account_id},
    )
    database.execute(
        text(
            """
            UPDATE vendor_portal_sessions
            SET revoked_at=:now, updated_at=:now
            WHERE account_id=:account_id AND id<>:session_id AND revoked_at IS NULL
            """
        ),
        {"now": now, "account_id": context.account_id, "session_id": context.session_id},
    )
    database.commit()
    return vendor_me(replace(context, force_password_change=False))


def list_vendor_outlets(database: Session, context: VendorPortalContext) -> list[dict]:
    return _rows(
        database,
        """
        SELECT
            id, code, name, outlet_type, cluster_name, address,
            latitude, longitude, attendance_radius_meters,
            vendor_contact_person, vendor_phone, vendor_email,
            licence_number, licence_expiry_date, excise_licence_number,
            excise_expiry_date, rent_agreement_expiry_date, status, is_active
        FROM outlets
        WHERE organization_id=:org AND vendor_id=:vendor_id
        ORDER BY code
        """,
        {"org": context.organization_id, "vendor_id": context.vendor_id},
    )


def _organization_local_date(database: Session, organization_id: UUID) -> date:
    row = _row(
        database,
        "SELECT timezone FROM organizations WHERE id=:org",
        {"org": organization_id},
    )
    timezone_name = (row or {}).get("timezone") or "Asia/Kolkata"
    return _now().astimezone(ZoneInfo(timezone_name)).date()


def _vendor_attendance_sql(where_sql: str) -> str:
    return f"""
        SELECT
            a.id, a.vendor_id, v.code AS vendor_code, v.name AS vendor_name,
            a.outlet_id, o.code AS outlet_code, o.name AS outlet_name,
            a.attendance_date, a.status, a.check_in_at, a.check_out_at,
            a.check_in_latitude, a.check_in_longitude,
            a.check_in_accuracy_meters, a.check_in_distance_meters,
            a.check_out_latitude, a.check_out_longitude,
            a.check_out_accuracy_meters, a.check_out_distance_meters,
            a.worked_minutes, COALESCE(a.late_minutes, 0) AS late_minutes
        FROM vendor_attendance_records a
        JOIN vendors v ON v.id=a.vendor_id
        JOIN outlets o ON o.id=a.outlet_id
        WHERE {where_sql}
    """


def _attendance_outlet(
    database: Session,
    context: VendorPortalContext,
    outlet_id: UUID,
) -> dict:
    outlet = _row(
        database,
        """
        SELECT id, code, name, latitude, longitude, attendance_radius_meters
        FROM outlets
        WHERE id=:outlet_id AND organization_id=:org
          AND vendor_id=:vendor_id AND is_active=true
        """,
        {
            "outlet_id": outlet_id,
            "org": context.organization_id,
            "vendor_id": context.vendor_id,
        },
    )
    if outlet is None:
        raise HTTPException(status_code=404, detail="Active outlet was not found for this vendor account.")
    if outlet["latitude"] is None or outlet["longitude"] is None:
        raise HTTPException(status_code=409, detail="This outlet has no attendance coordinates. Contact Admin.")
    return outlet


def _validate_vendor_location(outlet: dict, latitude: float, longitude: float) -> float:
    distance = calculate_distance_meters(
        latitude,
        longitude,
        float(outlet["latitude"]),
        float(outlet["longitude"]),
    )
    radius = float(outlet.get("attendance_radius_meters") or 150.0)
    if distance > radius:
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"You must be at {outlet['name']} to mark attendance.",
                "distance_meters": round(distance, 2),
                "allowed_radius_meters": radius,
            },
        )
    return distance


def vendor_attendance_today(database: Session, context: VendorPortalContext) -> list[dict]:
    attendance_date = _organization_local_date(database, context.organization_id)
    return _rows(
        database,
        _vendor_attendance_sql(
            "a.vendor_account_id=:account_id AND a.attendance_date=:attendance_date"
        ) + " ORDER BY o.code",
        {"account_id": context.account_id, "attendance_date": attendance_date},
    )


def vendor_attendance_check_in(database: Session, context: VendorPortalContext, payload) -> dict:
    outlet = _attendance_outlet(database, context, payload.outlet_id)
    distance = _validate_vendor_location(outlet, payload.latitude, payload.longitude)
    attendance_date = _organization_local_date(database, context.organization_id)
    existing = _row(
        database,
        """
        SELECT id FROM vendor_attendance_records
        WHERE vendor_account_id=:account_id AND outlet_id=:outlet_id
          AND attendance_date=:attendance_date
        """,
        {
            "account_id": context.account_id,
            "outlet_id": payload.outlet_id,
            "attendance_date": attendance_date,
        },
    )
    if existing:
        raise HTTPException(status_code=409, detail="Vendor attendance is already checked in for this outlet today.")

    record_id = uuid4()
    now = _now()
    database.execute(
        text(
            """
            INSERT INTO vendor_attendance_records (
                id, organization_id, vendor_id, vendor_account_id, outlet_id,
                attendance_date, status, check_in_at, check_in_latitude,
                check_in_longitude, check_in_accuracy_meters,
                check_in_distance_meters, worked_minutes, created_at, updated_at
            ) VALUES (
                :id, :org, :vendor_id, :account_id, :outlet_id,
                :attendance_date, 'PRESENT', :now, :latitude,
                :longitude, :accuracy, :distance, 0, :now, :now
            )
            """
        ),
        {
            "id": record_id,
            "org": context.organization_id,
            "vendor_id": context.vendor_id,
            "account_id": context.account_id,
            "outlet_id": payload.outlet_id,
            "attendance_date": attendance_date,
            "now": now,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "accuracy": payload.accuracy_meters,
            "distance": distance,
        },
    )
    database.commit()
    return _row(database, _vendor_attendance_sql("a.id=:id"), {"id": record_id})


def vendor_attendance_check_out(database: Session, context: VendorPortalContext, payload) -> dict:
    outlet = _attendance_outlet(database, context, payload.outlet_id)
    distance = _validate_vendor_location(outlet, payload.latitude, payload.longitude)
    attendance_date = _organization_local_date(database, context.organization_id)
    record = _row(
        database,
        """
        SELECT id, check_in_at, check_out_at FROM vendor_attendance_records
        WHERE vendor_account_id=:account_id AND outlet_id=:outlet_id
          AND attendance_date=:attendance_date
        """,
        {
            "account_id": context.account_id,
            "outlet_id": payload.outlet_id,
            "attendance_date": attendance_date,
        },
    )
    if record is None:
        raise HTTPException(status_code=409, detail="Vendor attendance has not been checked in for this outlet today.")
    if record["check_out_at"] is not None:
        raise HTTPException(status_code=409, detail="Vendor attendance is already checked out for this outlet today.")

    now = _now()
    check_in_at = record["check_in_at"]
    if check_in_at.tzinfo is None:
        check_in_at = check_in_at.replace(tzinfo=timezone.utc)
    worked_minutes = max(0, int((now - check_in_at).total_seconds() // 60))
    database.execute(
        text(
            """
            UPDATE vendor_attendance_records
            SET status='CHECKED_OUT', check_out_at=:now,
                check_out_latitude=:latitude, check_out_longitude=:longitude,
                check_out_accuracy_meters=:accuracy,
                check_out_distance_meters=:distance,
                worked_minutes=:worked_minutes, updated_at=:now
            WHERE id=:id
            """
        ),
        {
            "id": record["id"],
            "now": now,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "accuracy": payload.accuracy_meters,
            "distance": distance,
            "worked_minutes": worked_minutes,
        },
    )
    database.commit()
    return _row(database, _vendor_attendance_sql("a.id=:id"), {"id": record["id"]})


def list_admin_vendor_attendance(
    database: Session,
    user: User,
    start_date: date,
    end_date: date,
) -> list[dict]:
    if not role_codes(database, user).intersection(LOCATION_MONITOR_ROLES):
        raise HTTPException(status_code=403, detail="Admin, MD or GM access is required for attendance monitoring.")
    return _rows(
        database,
        _vendor_attendance_sql(
            "a.organization_id=:org AND a.attendance_date BETWEEN :start_date AND :end_date"
        ) + " ORDER BY a.attendance_date DESC, v.code, o.code",
        {"org": user.organization_id, "start_date": start_date, "end_date": end_date},
    )


def read_vendor_outlet(database: Session, context: VendorPortalContext, outlet_id: UUID) -> dict:
    row = _row(
        database,
        """
        SELECT
            id, code, name, outlet_type, cluster_name, address,
            latitude, longitude, attendance_radius_meters,
            vendor_contact_person, vendor_phone, vendor_email,
            licence_number, licence_expiry_date, excise_licence_number,
            excise_expiry_date, rent_agreement_expiry_date, status, is_active
        FROM outlets
        WHERE id=:id AND organization_id=:org AND vendor_id=:vendor_id
        """,
        {"id": outlet_id, "org": context.organization_id, "vendor_id": context.vendor_id},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Outlet was not found for this vendor account.")
    return row


def list_vendor_documents(database: Session, context: VendorPortalContext, outlet_id: UUID | None = None) -> list[dict]:
    params = {"org": context.organization_id, "vendor_id": context.vendor_id}
    extra = ""
    if outlet_id is not None:
        read_vendor_outlet(database, context, outlet_id)
        params["outlet_id"] = outlet_id
        extra = " AND o.id=:outlet_id"

    return _rows(
        database,
        f"""
        SELECT
            d.id, o.id AS outlet_id, o.code AS outlet_code, o.name AS outlet_name,
            d.category, d.title, d.description, d.file_name, d.content_type,
            d.file_size, d.issue_date, d.expiry_date, d.status, d.created_at
        FROM document_records d
        JOIN outlets o ON o.id=d.owner_id AND d.owner_type='OUTLET'
        WHERE d.organization_id=:org
          AND o.organization_id=:org
          AND o.vendor_id=:vendor_id
          AND d.is_confidential=false
          AND d.status NOT IN ('UPLOAD_PENDING','ARCHIVED')
          {extra}
        ORDER BY o.code, d.expiry_date ASC NULLS LAST, d.created_at DESC
        """,
        params,
    )


def vendor_document_download(database: Session, context: VendorPortalContext, document_id: UUID) -> dict:
    row = _row(
        database,
        """
        SELECT d.id, d.s3_bucket, d.s3_key, d.file_name, d.status
        FROM document_records d
        JOIN outlets o ON o.id=d.owner_id AND d.owner_type='OUTLET'
        WHERE d.id=:document_id
          AND d.organization_id=:org
          AND o.organization_id=:org
          AND o.vendor_id=:vendor_id
          AND d.is_confidential=false
          AND d.status NOT IN ('UPLOAD_PENDING','ARCHIVED')
        """,
        {"document_id": document_id, "org": context.organization_id, "vendor_id": context.vendor_id},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Document was not found or is not available to this vendor.")
    try:
        url = create_download_url(bucket=row["s3_bucket"], key=row["s3_key"], file_name=row["file_name"])
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"document_id": row["id"], "download_url": url, "expires_in_seconds": DEFAULT_PRESIGN_EXPIRY_SECONDS}


def _inspection_access_sql(extra_where: str = "") -> str:
    return f"""
        SELECT
            ir.id, ir.report_number, ir.version,
            o.code AS outlet_code, o.name AS outlet_name, o.address AS outlet_address,
            u.employee_code AS inspector_code,
            TRIM(CONCAT_WS(' ', e.first_name, e.last_name)) AS inspector_name,
            ir.inspection_started_at, ir.submitted_at, ir.status,
            COALESCE(jsonb_array_length(ir.attention_flags), 0) AS attention_flag_count,
            ir.vendor_response, ir.vendor_remarks, ir.vendor_responded_at,
            ir.cluster_name, ir.template_snapshot, ir.answers, ir.section_remarks,
            ir.attention_flags, ir.inspector_signature_data_uri,
            ir.vendor_signature_data_uri
        FROM inspection_reports ir
        JOIN outlets o ON o.id=ir.outlet_id
        LEFT JOIN employees e ON e.id=ir.inspector_employee_id
        LEFT JOIN users u ON u.id=e.user_id
        WHERE ir.organization_id=:org
          AND o.organization_id=:org
          AND o.vendor_id=:vendor_id
          AND ir.status IN ('VENDOR_PENDING','ACCEPTED','DISPUTED')
          {extra_where}
    """


def list_vendor_inspections(database: Session, context: VendorPortalContext) -> list[dict]:
    rows = _rows(
        database,
        _inspection_access_sql() + " ORDER BY ir.inspection_started_at DESC, ir.created_at DESC",
        {"org": context.organization_id, "vendor_id": context.vendor_id},
    )
    return [
        {key: value for key, value in row.items() if key not in {
            "cluster_name", "template_snapshot", "answers", "section_remarks",
            "attention_flags", "inspector_signature_data_uri", "vendor_signature_data_uri"
        }}
        for row in rows
    ]


def vendor_inspection_detail(database: Session, context: VendorPortalContext, report_id: UUID) -> dict:
    # _inspection_access_sql() strictly requires outlet.vendor_id to match
    # the authenticated vendor. Knowing another report UUID is never enough.
    row = _row(
        database,
        _inspection_access_sql("AND ir.id=:report_id"),
        {"org": context.organization_id, "vendor_id": context.vendor_id, "report_id": report_id},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Inspection report was not found for this vendor.")
    row["template_snapshot"] = row.get("template_snapshot") or {}
    row["answers"] = row.get("answers") or {}
    row["section_remarks"] = row.get("section_remarks") or {}
    row["attention_flags"] = row.get("attention_flags") or []
    row["attention_flag_count"] = len(row["attention_flags"])
    return row


def respond_to_vendor_inspection(
    database: Session,
    context: VendorPortalContext,
    report_id: UUID,
    response: str,
    remarks: str | None,
    signature_data_uri: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> dict:
    # First enforce vendor -> report/outlet ownership.
    vendor_inspection_detail(database, context, report_id)

    report = database.scalar(
        select(InspectionReport)
        .where(
            InspectionReport.id == report_id,
            InspectionReport.organization_id == context.organization_id,
        )
        .with_for_update()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Inspection report was not found.")
    if report.status != "VENDOR_PENDING":
        raise HTTPException(status_code=409, detail="Vendor response has already been recorded or is not currently required.")

    now = _now()
    clean_remarks = (remarks or "").strip() or None
    report.vendor_response = response
    report.vendor_response_name = context.vendor_name
    report.vendor_remarks = clean_remarks
    report.vendor_signature_data_uri = signature_data_uri or None
    report.vendor_responded_at = now
    report.vendor_response_ip = ip_address
    report.vendor_response_user_agent = (user_agent or "")[:1000] or None
    report.status = "ACCEPTED" if response == "ACCEPT" else "DISPUTED"

    database.add(
        InspectionAuditEvent(
            organization_id=context.organization_id,
            report_id=report.id,
            actor_type="VENDOR_PORTAL",
            actor_user_id=None,
            action=f"VENDOR_{response}",
            note=clean_remarks,
            extra_data={
                "vendor_account_id": str(context.account_id),
                "vendor_code": context.vendor_code,
                "signature_provided": bool(signature_data_uri),
            },
            ip_address=ip_address,
            user_agent=(user_agent or "")[:1000] or None,
        )
    )

    queue_role_notifications(
        database,
        organization_id=context.organization_id,
        role_codes=MANAGEMENT_ROLES,
        title=f"Vendor {response.lower()}: {report.report_number}",
        body=f"{context.vendor_name} responded to shop inspection {report.report_number}.",
        dedupe_prefix=f"vendor-portal-inspection:{report.id}:{response.lower()}",
        route=f"/module/inspections?report={report.id}",
        module="inspections",
        event=f"VENDOR_{response}",
        entity_id=report.id,
        extra_payload={"vendor_code": context.vendor_code},
    )

    database.execute(
        text(
            """
            UPDATE vendor_portal_notifications
            SET read_at=COALESCE(read_at, :now), updated_at=:now
            WHERE account_id=:account_id
              AND payload->>'inspection_report_id'=:report_id
            """
        ),
        {"now": now, "account_id": context.account_id, "report_id": str(report.id)},
    )
    database.commit()
    return vendor_inspection_detail(database, context, report_id)


def _insert_vendor_notification(
    database: Session,
    *,
    context: VendorPortalContext,
    title: str,
    body: str,
    payload: dict,
    dedupe_key: str,
) -> None:
    database.execute(
        text(
            """
            INSERT INTO vendor_portal_notifications (
                id, account_id, organization_id, title, body, payload,
                dedupe_key, created_at, updated_at
            ) VALUES (
                :id, :account_id, :org, :title, :body, CAST(:payload AS jsonb),
                :dedupe_key, :now, :now
            )
            ON CONFLICT (dedupe_key) DO NOTHING
            """
        ),
        {
            "id": uuid4(),
            "account_id": context.account_id,
            "org": context.organization_id,
            "title": title,
            "body": body,
            "payload": __import__("json").dumps(payload),
            "dedupe_key": dedupe_key,
            "now": _now(),
        },
    )


def sync_vendor_notifications(database: Session, context: VendorPortalContext) -> None:
    # Security cleanup: remove inspection notifications that reference a
    # report whose outlet does not currently belong to this vendor.
    database.execute(
        text(
            """
            DELETE FROM vendor_portal_notifications n
            WHERE n.account_id=:account_id
              AND n.payload->>'type'='INSPECTION'
              AND (
                  n.payload->>'inspection_report_id' IS NULL
                  OR NOT EXISTS (
                      SELECT 1
                      FROM inspection_reports ir
                      JOIN outlets o ON o.id=ir.outlet_id
                      WHERE ir.id::text=n.payload->>'inspection_report_id'
                        AND ir.organization_id=:org
                        AND o.organization_id=:org
                        AND o.vendor_id=:vendor_id
                        AND ir.status IN ('VENDOR_PENDING','ACCEPTED','DISPUTED')
                  )
              )
            """
        ),
        {
            "account_id": context.account_id,
            "org": context.organization_id,
            "vendor_id": context.vendor_id,
        },
    )

    pending = _rows(
        database,
        """
        SELECT ir.id, ir.report_number, o.code AS outlet_code, o.name AS outlet_name
        FROM inspection_reports ir
        JOIN outlets o ON o.id=ir.outlet_id
        WHERE ir.organization_id=:org
          AND o.organization_id=:org
          AND o.vendor_id=:vendor_id
          AND ir.status='VENDOR_PENDING'
        """,
        {"org": context.organization_id, "vendor_id": context.vendor_id},
    )
    for row in pending:
        _insert_vendor_notification(
            database,
            context=context,
            title="Inspection report requires your response",
            body=f"{row['outlet_code']} - {row['outlet_name']}: {row['report_number']}",
            payload={"type": "INSPECTION", "inspection_report_id": str(row["id"])},
            dedupe_key=f"vendor:{context.account_id}:inspection:{row['id']}:pending",
        )

    expiring_docs = _rows(
        database,
        """
        SELECT d.id, d.title, d.expiry_date, o.code AS outlet_code, o.name AS outlet_name
        FROM document_records d
        JOIN outlets o ON o.id=d.owner_id AND d.owner_type='OUTLET'
        WHERE d.organization_id=:org
          AND o.organization_id=:org
          AND o.vendor_id=:vendor_id
          AND d.is_confidential=false
          AND d.status NOT IN ('UPLOAD_PENDING','ARCHIVED')
          AND d.expiry_date IS NOT NULL
          AND d.expiry_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + INTERVAL '30 days')
        """,
        {"org": context.organization_id, "vendor_id": context.vendor_id},
    )
    for row in expiring_docs:
        _insert_vendor_notification(
            database,
            context=context,
            title="Outlet document expiring soon",
            body=f"{row['outlet_code']} - {row['title']} expires on {row['expiry_date']}.",
            payload={"type": "DOCUMENT", "document_id": str(row["id"])},
            dedupe_key=f"vendor:{context.account_id}:document:{row['id']}:expiry:{row['expiry_date']}",
        )
    database.commit()


def list_vendor_notifications(database: Session, context: VendorPortalContext, unread_only: bool = False) -> list[dict]:
    sync_vendor_notifications(database, context)
    extra = " AND read_at IS NULL" if unread_only else ""
    return _rows(
        database,
        f"""
        SELECT id, title, body, payload, read_at, created_at
        FROM vendor_portal_notifications
        WHERE account_id=:account_id {extra}
        ORDER BY created_at DESC
        LIMIT 250
        """,
        {"account_id": context.account_id},
    )


def mark_vendor_notification_read(database: Session, context: VendorPortalContext, notification_id: UUID) -> dict:
    row = _row(
        database,
        "SELECT id FROM vendor_portal_notifications WHERE id=:id AND account_id=:account_id",
        {"id": notification_id, "account_id": context.account_id},
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification was not found.")
    now = _now()
    database.execute(
        text("UPDATE vendor_portal_notifications SET read_at=COALESCE(read_at,:now), updated_at=:now WHERE id=:id"),
        {"now": now, "id": notification_id},
    )
    database.commit()
    return _row(
        database,
        "SELECT id, title, body, payload, read_at, created_at FROM vendor_portal_notifications WHERE id=:id",
        {"id": notification_id},
    )


def vendor_dashboard(database: Session, context: VendorPortalContext) -> dict:
    sync_vendor_notifications(database, context)
    counts = _row(
        database,
        """
        SELECT
            (SELECT COUNT(*) FROM outlets o
             WHERE o.organization_id=:org AND o.vendor_id=:vendor_id) AS outlet_count,
            (SELECT COUNT(*) FROM document_records d
             JOIN outlets o ON o.id=d.owner_id AND d.owner_type='OUTLET'
             WHERE d.organization_id=:org AND o.organization_id=:org
               AND o.vendor_id=:vendor_id AND d.is_confidential=false
               AND d.status NOT IN ('UPLOAD_PENDING','ARCHIVED')) AS document_count,
            (SELECT COUNT(*) FROM inspection_reports ir
             JOIN outlets o ON o.id=ir.outlet_id
             WHERE ir.organization_id=:org AND o.organization_id=:org
               AND o.vendor_id=:vendor_id
               AND ir.status='VENDOR_PENDING') AS pending_inspection_count,
            (SELECT COUNT(*) FROM vendor_portal_notifications n
             WHERE n.account_id=:account_id AND n.read_at IS NULL) AS unread_notification_count
        """,
        {"org": context.organization_id, "vendor_id": context.vendor_id, "account_id": context.account_id},
    )
    return {key: int(counts.get(key) or 0) for key in (
        "outlet_count", "document_count", "pending_inspection_count", "unread_notification_count"
    )}
