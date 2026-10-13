"""Account-scoped Android push registration and delivery state; no attendance dependency."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from uuid import UUID

from sqlalchemy import (Boolean, Column, DateTime, Integer, JSON, MetaData, String,
                        Table, Text, Uuid, and_, insert, select, update)

metadata = MetaData()
devices = Table(
    "mobile_push_installations", metadata,
    Column("installation_id", Uuid, primary_key=True),
    Column("secret_hash", String(64), nullable=False),
    Column("organization_id", Uuid, nullable=False, index=True),
    Column("recipient_kind", String(10), nullable=False),
    Column("recipient_id", Uuid, nullable=False, index=True),
    Column("binding_id", Uuid, nullable=False),
    Column("fcm_token", Text),
    Column("token_hash", String(64), unique=True),
    Column("enabled", Boolean, nullable=False),
    Column("since", DateTime(timezone=True), nullable=False),
    Column("seen_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
deliveries = Table(
    "mobile_push_deliveries", metadata,
    Column("installation_id", Uuid, primary_key=True),
    Column("binding_id", Uuid, primary_key=True),
    Column("recipient_kind", String(10), primary_key=True),
    Column("notification_id", Uuid, primary_key=True),
    Column("status", String(16), nullable=False, default="PENDING"),
    Column("attempts", Integer, nullable=False, default=0),
    Column("available_at", DateTime(timezone=True), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("sent_at", DateTime(timezone=True)),
    Column("error_code", String(80)),
)

# Projections of existing application tables; never created or altered by this update.
source_metadata = MetaData()
organizations = Table("organizations", source_metadata,
    Column("id", Uuid, primary_key=True), Column("is_active", Boolean))
users = Table("users", source_metadata,
    Column("id", Uuid, primary_key=True), Column("organization_id", Uuid), Column("is_active", Boolean))
vendors = Table("vendors", source_metadata,
    Column("id", Uuid, primary_key=True), Column("organization_id", Uuid), Column("status", String))
vendor_accounts = Table("vendor_portal_accounts", source_metadata,
    Column("id", Uuid, primary_key=True), Column("organization_id", Uuid), Column("vendor_id", Uuid), Column("status", String))
notifications = Table("notifications", source_metadata,
    Column("id", Uuid, primary_key=True), Column("organization_id", Uuid),
    Column("recipient_user_id", Uuid), Column("channel", String),
    Column("title", String), Column("body", Text), Column("payload", JSON),
    Column("read_at", DateTime(timezone=True)), Column("created_at", DateTime(timezone=True)))
vendor_notifications = Table("vendor_portal_notifications", source_metadata,
    Column("id", Uuid, primary_key=True), Column("organization_id", Uuid),
    Column("account_id", Uuid), Column("title", String), Column("body", Text),
    Column("payload", JSON), Column("read_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True)))


def now_utc():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def register(connection, *, installation_id, secret, binding_id, token,
             organization_id, recipient_kind, recipient_id, enabled, now=None):
    """Only callers authenticated by the API supply the recipient and organisation."""
    now = now or now_utc()
    if recipient_kind not in {"employee", "vendor"}:
        raise ValueError("Invalid account type.")
    current = connection.execute(select(devices).where(
        devices.c.installation_id == installation_id).with_for_update()).mappings().first()
    if current and not hmac.compare_digest(current["secret_hash"], digest(secret)):
        raise PermissionError("This phone registration belongs to another installation.")
    same_binding = bool(current and current["binding_id"] == binding_id)
    if same_binding and (current["organization_id"] != organization_id or
                         current["recipient_id"] != recipient_id or
                         current["recipient_kind"] != recipient_kind):
        raise PermissionError("Sign in again to register the new account.")
    # Enabling alerts after a disabled interval does not send a backlog of old alerts.
    since = current["since"] if same_binding and current["enabled"] else now
    values = dict(secret_hash=digest(secret), binding_id=binding_id,
        organization_id=organization_id, recipient_kind=recipient_kind, recipient_id=recipient_id,
        fcm_token=token, token_hash=digest(token), enabled=enabled, since=since,
        seen_at=now, expires_at=now + timedelta(days=30))
    if current:
        connection.execute(update(devices).where(devices.c.installation_id == installation_id).values(**values))
    else:
        connection.execute(insert(devices).values(installation_id=installation_id, **values))


def unregister(connection, *, installation_id, secret, binding_id):
    """Binding check prevents a delayed logout from disabling a newly signed-in account."""
    connection.execute(update(devices).where(
        devices.c.installation_id == installation_id,
        devices.c.secret_hash == digest(secret), devices.c.binding_id == binding_id,
    ).values(enabled=False, fcm_token=None, token_hash=None))


def active_devices(now):
    return and_(devices.c.enabled.is_(True), devices.c.fcm_token.is_not(None),
                devices.c.expires_at > now, organizations.c.is_active.is_(True))


def source_join(kind):
    """Both notification and account must belong to the authenticated organisation."""
    source = notifications if kind == "employee" else vendor_notifications
    owner = users if kind == "employee" else vendor_accounts
    recipient = source.c.recipient_user_id if kind == "employee" else source.c.account_id
    joined = devices.join(organizations, devices.c.organization_id == organizations.c.id).join(
        owner, and_(owner.c.id == devices.c.recipient_id, owner.c.organization_id == devices.c.organization_id)
    ).join(source, and_(recipient == devices.c.recipient_id,
                       source.c.organization_id == devices.c.organization_id))
    conditions = [devices.c.recipient_kind == kind]
    if kind == "employee":
        conditions += [users.c.is_active.is_(True), source.c.channel == "IN_APP"]
    else:
        joined = joined.join(vendors, and_(vendor_accounts.c.vendor_id == vendors.c.id,
            vendors.c.organization_id == devices.c.organization_id))
        conditions += [vendor_accounts.c.status == "ACTIVE", vendors.c.status == "ACTIVE"]
    return source, joined, conditions


def enqueue(connection, now=None):
    """Read committed in-app notifications; the worker does not depend on an open screen."""
    now = now or now_utc()
    if connection.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as upsert
    elif connection.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as upsert
    else:
        raise RuntimeError("PostgreSQL is required for live delivery.")
    count = 0
    for kind in ("employee", "vendor"):
        source, joined, conditions = source_join(kind)
        candidates = connection.execute(select(devices.c.installation_id, devices.c.binding_id,
            source.c.id.label("notification_id")).select_from(joined).where(
                active_devices(now), *conditions, source.c.read_at.is_(None),
                source.c.created_at >= devices.c.since,
                source.c.created_at >= now - timedelta(hours=24),
                ~select(deliveries.c.notification_id).where(
                    deliveries.c.installation_id == devices.c.installation_id,
                    deliveries.c.binding_id == devices.c.binding_id,
                    deliveries.c.recipient_kind == kind,
                    deliveries.c.notification_id == source.c.id).exists()
            ).order_by(source.c.created_at).limit(500)).mappings().all()
        for item in candidates:
            result = connection.execute(upsert(deliveries).values(**dict(item), recipient_kind=kind,
                status="PENDING", attempts=0, available_at=now, created_at=now).on_conflict_do_nothing())
            count += result.rowcount
    return count


def ready(connection, kind, now=None, limit=100):
    now = now or now_utc()
    source, joined, conditions = source_join(kind)
    joined = joined.join(deliveries, and_(
        deliveries.c.installation_id == devices.c.installation_id,
        deliveries.c.binding_id == devices.c.binding_id,
        deliveries.c.recipient_kind == kind, deliveries.c.notification_id == source.c.id))
    return connection.execute(select(deliveries, devices.c.fcm_token, devices.c.token_hash,
        source.c.title, source.c.body, source.c.payload).select_from(joined).where(
            active_devices(now), *conditions, source.c.read_at.is_(None),
            source.c.created_at >= devices.c.since,
            source.c.created_at >= now - timedelta(hours=24),
            deliveries.c.status == "PENDING", deliveries.c.available_at <= now,
        ).order_by(deliveries.c.created_at).limit(limit).with_for_update(
            of=deliveries, skip_locked=True)).mappings().all()


def delivery_key(item):
    return and_(*(deliveries.c[name] == item[name] for name in
        ("installation_id", "binding_id", "recipient_kind", "notification_id")))


def record_result(connection, item, *, sent=False, error_code=None, permanent=False, now=None):
    now = now or now_utc()
    if error_code == "unregistered":
        current_hash = connection.scalar(select(devices.c.token_hash).where(
            devices.c.installation_id == item["installation_id"],
            devices.c.binding_id == item["binding_id"], devices.c.enabled.is_(True)))
        if current_hash and current_hash != item["token_hash"]:
            # Preserve the alert if token rotation beat the invalid-token response.
            connection.execute(update(deliveries).where(delivery_key(item)).values(
                status="PENDING", available_at=now, error_code="token-rotated"))
            return
    attempts = item["attempts"] + 1
    terminal = permanent or attempts >= 10
    connection.execute(update(deliveries).where(delivery_key(item)).values(
        attempts=attempts, status="SENT" if sent else "FAILED" if terminal else "PENDING",
        sent_at=now if sent else None, error_code=error_code,
        available_at=now + timedelta(seconds=min(3600, 10 * 2 ** attempts))))
    if error_code == "unregistered":
        # Do not disable a token which rotated while the request was in flight.
        connection.execute(update(devices).where(
            devices.c.installation_id == item["installation_id"],
            devices.c.binding_id == item["binding_id"],
            devices.c.token_hash == item["token_hash"],
        ).values(enabled=False, fcm_token=None, token_hash=None))


def payload_for(item):
    payload = item.get("payload") or {}
    route = payload.get("route", "") if isinstance(payload, dict) else ""
    if item["recipient_kind"] == "vendor":
        route = "/vendor"  # Existing vendor portal has a notification tab within this page.
    elif not isinstance(route, str) or not route.startswith("/module/") or any(
            character in route for character in ("..", "\\", "\n", "\r", "%")):
        route = "/module/notifications"
    return {"schema": "sands.alert.v1", "binding_id": str(item["binding_id"]),
        "event_id": str(item["notification_id"]), "route": route[:250],
        "title": (item["title"] or "Workforce update")[:160], "body": (item["body"] or "Open the app for details.")[:400]}
