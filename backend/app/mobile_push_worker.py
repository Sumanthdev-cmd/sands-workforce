"""Fast, separate delivery worker for native Android alerts. No attendance polling."""
import logging
import os
from pathlib import Path
import signal
import threading
import time
from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, delete, select, text
from firebase_admin import credentials, initialize_app, messaging

from app.db.session import SessionLocal, engine
from app.services.storage_service import load_backend_env
from app.services import mobile_push_store as store

log = logging.getLogger("sands.push")
stop = threading.Event()


def firebase_client():
    load_backend_env()
    location = os.getenv("FIREBASE_CREDENTIALS_FILE", "").strip()
    if not location:
        raise RuntimeError("Set FIREBASE_CREDENTIALS_FILE in backend/.env before starting push delivery.")
    path = Path(location).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    if not path.is_file():
        raise RuntimeError("The configured Firebase server credential file is missing.")
    app = initialize_app(credentials.Certificate(str(path)), options={"httpTimeout": 15}, name="sands-mobile-push")
    expected = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    if expected and app.project_id != expected:
        raise RuntimeError("Firebase server credentials belong to a different Firebase project.")
    return app


def sync_vendors():
    """The current portal generates some alerts on page load; also generate them here."""
    from app.services.vendor_portal_service import VendorPortalContext, sync_vendor_notifications
    with SessionLocal() as database:
        rows = database.execute(text("""
            SELECT DISTINCT a.id AS account_id, a.organization_id, a.vendor_id,
                o.code AS organization_code, v.code AS vendor_code, v.name AS vendor_name,
                v.contact_person, v.phone, v.email, a.status, a.force_password_change, a.last_login_at
            FROM mobile_push_installations d
            JOIN vendor_portal_accounts a ON a.id=d.recipient_id AND a.organization_id=d.organization_id
            JOIN vendors v ON v.id=a.vendor_id AND v.organization_id=a.organization_id
            JOIN organizations o ON o.id=a.organization_id
            WHERE d.recipient_kind='vendor' AND d.enabled=true AND d.expires_at > now()
              AND a.status='ACTIVE' AND v.status='ACTIVE' AND o.is_active=true
        """)).mappings().all()
        for row in rows:
            try:
                context = VendorPortalContext(session_id=UUID(int=0), **dict(row))
                sync_vendor_notifications(database, context)
            except Exception as error:
                database.rollback()
                # Keep private record contents and credentials out of service logs.
                log.error("Vendor alert generation failed (%s); inspect the portal schema.", type(error).__name__)


def tick(app, sender=messaging.send):
    counts = {"queued": 0, "sent": 0, "retry": 0, "failed": 0}
    with engine.begin() as connection:
        # Avoid competing workers creating/delivering the same notification.
        if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(738591420)")):
            return counts
        counts["queued"] = store.enqueue(connection)
        for kind in ("employee", "vendor"):
            for item in store.ready(connection, kind, limit=30):
                if stop.is_set():
                    break
                try:
                    # Data-only prevents Android auto-displaying an alert for a previous login.
                    sender(messaging.Message(token=item["fcm_token"], data=store.payload_for(item),
                        android=messaging.AndroidConfig(priority="high", ttl=timedelta(hours=24))), app=app)
                    store.record_result(connection, item, sent=True)
                    counts["sent"] += 1
                except messaging.UnregisteredError:
                    store.record_result(connection, item, error_code="unregistered", permanent=True)
                    counts["failed"] += 1
                except messaging.SenderIdMismatchError:
                    store.record_result(connection, item, error_code="sender-project-mismatch", permanent=True)
                    counts["failed"] += 1
                    log.error("Phone and server Firebase projects do not match.")
                except Exception as error:
                    store.record_result(connection, item, error_code=type(error).__name__[:80])
                    counts["retry"] += 1
        # Retain recent delivery IDs for deduplication; source in-app records are untouched.
        connection.execute(delete(store.deliveries).where(
            store.deliveries.c.created_at < store.now_utc() - timedelta(days=30)))
    return counts


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = firebase_client()  # Fail clearly before entering a worker loop.
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    log.info("Android push worker started; checking new alerts every 5 seconds.")
    last_vendors = -60.0
    while not stop.is_set():
        if time.monotonic() - last_vendors >= 30:
            try:
                sync_vendors()
            except Exception as error:
                log.error("Vendor alert refresh failed (%s).", type(error).__name__)
            last_vendors = time.monotonic()
        try:
            counts = tick(app)
            if any(counts.values()):
                log.info("Delivery counts: %s", counts)
        except Exception as error:
            log.error("Push worker cycle failed (%s).", type(error).__name__)
        stop.wait(5)


if __name__ == "__main__":
    main()
