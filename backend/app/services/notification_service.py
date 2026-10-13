from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BackgroundJobExecution,
    Device,
    Employee,
    Notification,
    Role,
    User,
    user_roles,
)
from app.services.background_service import require_background_admin


def users_with_roles(
    database: Session,
    organization_id: UUID,
    role_codes: set[str],
) -> list[UUID]:
    if not role_codes:
        return []

    return list(
        database.scalars(
            select(User.id)
            .join(user_roles, User.id == user_roles.c.user_id)
            .join(Role, Role.id == user_roles.c.role_id)
            .where(
                User.organization_id == organization_id,
                Role.code.in_(sorted(role_codes)),
            )
            .distinct()
        ).all()
    )


def has_registered_push_device(
    database: Session,
    organization_id: UUID,
    user_id: UUID,
) -> bool:
    """Return whether the user currently has an active FCM-enabled device."""

    device_id = database.scalar(
        select(Device.id)
        .join(Employee, Device.employee_id == Employee.id)
        .where(
            Device.organization_id == organization_id,
            Employee.organization_id == organization_id,
            Employee.user_id == user_id,
            Device.is_active.is_(True),
            Device.fcm_token.is_not(None),
            Device.fcm_token != "",
        )
        .limit(1)
    )
    return device_id is not None


def queue_user_notification(
    database: Session,
    *,
    organization_id: UUID,
    recipient_user_id: UUID | None,
    title: str,
    body: str,
    dedupe_key: str,
    route: str | None = None,
    module: str | None = None,
    event: str | None = None,
    entity_id: UUID | str | None = None,
    extra_payload: dict | None = None,
) -> Notification | None:
    if recipient_user_id is None:
        return None

    existing = database.scalar(
        select(Notification.id).where(
            Notification.dedupe_key == dedupe_key
        )
    )
    if existing is not None:
        return None

    payload = dict(extra_payload or {})
    if route:
        payload["route"] = route
    if module:
        payload["module"] = module
    if event:
        payload["event"] = event
    if entity_id is not None:
        payload["entity_id"] = str(entity_id)

    row = Notification(
        organization_id=organization_id,
        recipient_user_id=recipient_user_id,
        channel="IN_APP",
        title=title[:250],
        body=body,
        payload=payload or None,
        dedupe_key=dedupe_key[:500],
        status="PENDING",
        attempts=0,
        available_at=datetime.now(timezone.utc),
    )
    database.add(row)

    # A notification always remains available in the web inbox. Once the
    # employee has registered an app device, queue a second durable delivery
    # for Firebase so the same event can reach Android while the app is closed.
    if has_registered_push_device(
        database,
        organization_id,
        recipient_user_id,
    ):
        push_key = f"{dedupe_key}:FCM"[:500]
        push_exists = database.scalar(
            select(Notification.id).where(Notification.dedupe_key == push_key)
        )
        if push_exists is None:
            database.add(
                Notification(
                    organization_id=organization_id,
                    recipient_user_id=recipient_user_id,
                    channel="FCM",
                    title=title[:250],
                    body=body,
                    payload=payload or None,
                    dedupe_key=push_key,
                    status="PENDING",
                    attempts=0,
                    available_at=datetime.now(timezone.utc),
                )
            )
    return row


def queue_role_notifications(
    database: Session,
    *,
    organization_id: UUID,
    role_codes: set[str],
    title: str,
    body: str,
    dedupe_prefix: str,
    route: str | None = None,
    module: str | None = None,
    event: str | None = None,
    entity_id: UUID | str | None = None,
    exclude_user_ids: set[UUID] | None = None,
    extra_payload: dict | None = None,
) -> int:
    excluded = exclude_user_ids or set()
    queued = 0

    for recipient_id in users_with_roles(
        database, organization_id, role_codes
    ):
        if recipient_id in excluded:
            continue
        row = queue_user_notification(
            database,
            organization_id=organization_id,
            recipient_user_id=recipient_id,
            title=title,
            body=body,
            dedupe_key=f"{dedupe_prefix}:{recipient_id}",
            route=route,
            module=module,
            event=event,
            entity_id=entity_id,
            extra_payload=extra_payload,
        )
        if row is not None:
            queued += 1

    return queued


def list_my_notifications(
    database: Session,
    user: User,
    unread_only: bool,
) -> list[Notification]:
    statement = select(Notification).where(
        Notification.organization_id == user.organization_id,
        Notification.recipient_user_id == user.id,
        Notification.channel == "IN_APP",
    )

    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))

    return list(
        database.scalars(
            statement.order_by(Notification.created_at.desc())
        ).all()
    )


def mark_read(
    database: Session,
    user: User,
    notification_id: UUID,
) -> Notification:
    row = database.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.organization_id == user.organization_id,
            Notification.recipient_user_id == user.id,
            Notification.channel == "IN_APP",
        )
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification was not found.",
        )

    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        database.commit()
        database.refresh(row)

    return row


def list_executions(
    database: Session,
    user: User,
) -> list[BackgroundJobExecution]:
    require_background_admin(database, user)

    return list(
        database.scalars(
            select(BackgroundJobExecution)
            .order_by(BackgroundJobExecution.started_at.desc())
            .limit(200)
        ).all()
    )
