"""Authenticated Android push endpoints. Employee profile/check-in is not required."""
import os
from datetime import timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.api.routes.vendor_portal import VendorReady
from app.db.session import get_db
from app.services import mobile_push_store as store
from app.services.notification_service import queue_user_notification
from app.services.storage_service import load_backend_env
from app.services.vendor_portal_service import _insert_vendor_notification

router = APIRouter(prefix="/mobile-push", tags=["Android notifications"])
DB = Annotated[Session, Depends(get_db)]


class Installation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installation_id: UUID
    binding_id: UUID
    installation_secret: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class Registration(Installation):
    fcm_token: str = Field(min_length=20, max_length=4096, pattern=r"^\S+$")
    enabled: bool = True


@router.get("/version")
def version():
    return {"version": 1}


def register(database, payload, org, recipient, kind):
    load_backend_env()
    try:
        store.register(database.connection(), installation_id=payload.installation_id,
            secret=payload.installation_secret, binding_id=payload.binding_id,
            token=payload.fcm_token, organization_id=org, recipient_kind=kind,
            recipient_id=recipient, enabled=payload.enabled)
        database.commit()
    except PermissionError as error:
        database.rollback()
        raise HTTPException(409, str(error)) from error
    except IntegrityError as error:
        database.rollback()
        raise HTTPException(409, "This phone token is already registered. Reopen the app and retry.") from error
    return {"registered": True, "enabled": payload.enabled,
            "server_configured": bool(os.getenv("FIREBASE_CREDENTIALS_FILE", "").strip())}


@router.post("/employee/register")
def register_employee(payload: Registration, user: CurrentUser, database: DB):
    return register(database, payload, user.organization_id, user.id, "employee")


@router.post("/vendor/register")
def register_vendor(payload: Registration, vendor: VendorReady, database: DB):
    return register(database, payload, vendor.organization_id, vendor.account_id, "vendor")


@router.post("/unregister")
def unregister(payload: Installation, database: DB):
    # High-entropy installation secret allows cleanup after the login token expires.
    # A caller can only disable the matching installation AND login binding.
    store.unregister(database.connection(), installation_id=payload.installation_id,
        secret=payload.installation_secret, binding_id=payload.binding_id)
    database.commit()
    return {"unregistered": True}


def throttle_test(database, source, org, owner_column, owner):
    found = database.scalar(select(source.c.id).where(source.c.organization_id == org,
        owner_column == owner, source.c.title == "Test workforce notification",
        source.c.created_at >= store.now_utc() - timedelta(minutes=1)).limit(1))
    if found:
        raise HTTPException(429, "Please wait one minute before sending another test.")


@router.post("/employee/test")
def test_employee(user: CurrentUser, database: DB):
    throttle_test(database, store.notifications, user.organization_id,
        store.notifications.c.recipient_user_id, user.id)
    queue_user_notification(database, organization_id=user.organization_id,
        recipient_user_id=user.id, title="Test workforce notification",
        body="Your phone is receiving Workforce alerts. Tap to open your notifications.",
        dedupe_key=f"mobile-push-test:{user.id}:{uuid4()}", route="/module/notifications",
        module="notifications", event="MOBILE_PUSH_TEST")
    database.commit()
    return {"queued": True}


@router.post("/vendor/test")
def test_vendor(vendor: VendorReady, database: DB):
    throttle_test(database, store.vendor_notifications, vendor.organization_id,
        store.vendor_notifications.c.account_id, vendor.account_id)
    _insert_vendor_notification(database, context=vendor,
        title="Test workforce notification", body="Your phone is receiving Workforce alerts. Tap to open your vendor workspace.",
        payload={"type": "MOBILE_PUSH_TEST"}, dedupe_key=f"mobile-push-test:{vendor.account_id}:{uuid4()}")
    database.commit()
    return {"queued": True}
