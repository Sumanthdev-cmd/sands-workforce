import json
import os
import smtplib
from calendar import monthrange
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    BackgroundJobExecution,
    Device,
    Employee,
    Notification,
    Role,
    Task,
    TaskAssignment,
    TaskProgressLog,
    User,
    user_roles,
)
from app.services.asset_service import upcoming_renewals
from app.services.storage_service import load_backend_env


ADMIN_ROLES = {"ADMIN", "MD"}
MAX_ATTEMPTS = 5
_firebase_app = None


def user_role_codes(database: Session, user_id: UUID) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user_id)
        ).all()
    )


def require_background_admin(database: Session, user: User) -> None:
    if not user_role_codes(database, user.id).intersection(ADMIN_ROLES):
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Background-job administration access is required.",
        )


def run_logged_job(database: Session, job_name: str, trigger_type: str, callback) -> dict:
    execution = BackgroundJobExecution(
        job_name=job_name,
        trigger_type=trigger_type,
        status="RUNNING",
        started_at=datetime.now(timezone.utc),
    )
    database.add(execution)
    database.commit()
    database.refresh(execution)

    try:
        result = callback()
        execution.status = "SUCCESS"
        execution.finished_at = datetime.now(timezone.utc)
        execution.result_summary = result
        database.commit()
        return result
    except Exception as error:
        database.rollback()
        execution = database.get(BackgroundJobExecution, execution.id)
        execution.status = "FAILED"
        execution.finished_at = datetime.now(timezone.utc)
        execution.error_message = str(error)[:5000]
        database.commit()
        raise


def recurrence_matches(task: Task, target: date) -> bool:
    base = task.starts_at.date() if task.starts_at else task.created_at.date()
    interval = max(1, task.recurrence_interval or 1)
    kind = (task.recurrence_type or "NONE").upper()

    if target < base:
        return False

    if kind == "DAILY":
        return (target - base).days % interval == 0

    if kind == "WEEKLY":
        days = task.recurrence_days or [base.weekday()]
        weeks = (target - base).days // 7
        return target.weekday() in days and weeks % interval == 0

    if kind == "MONTHLY":
        months = (target.year - base.year) * 12 + target.month - base.month
        day = min(base.day, monthrange(target.year, target.month)[1])
        return target.day == day and months % interval == 0

    return False


def recurring_due_at(task: Task, target: date):
    if task.due_at is None:
        return None
    return datetime.combine(target, task.due_at.timetz())


def generate_recurring_assignments(
    database: Session,
    target_date: date | None = None,
) -> dict:
    target = target_date or date.today()
    tasks = list(
        database.scalars(
            select(Task).where(
                Task.is_active.is_(True),
                Task.status == "ACTIVE",
                Task.recurrence_type.in_(["DAILY", "WEEKLY", "MONTHLY"]),
            )
        ).all()
    )

    created = 0
    skipped = 0
    matched = 0

    for task in tasks:
        if not recurrence_matches(task, target):
            continue

        matched += 1
        employee_ids = list(
            database.scalars(
                select(distinct(TaskAssignment.employee_id)).where(
                    TaskAssignment.task_id == task.id
                )
            ).all()
        )

        for employee_id in employee_ids:
            existing = database.scalar(
                select(TaskAssignment.id).where(
                    TaskAssignment.task_id == task.id,
                    TaskAssignment.employee_id == employee_id,
                    TaskAssignment.scheduled_for == target,
                )
            )

            if existing:
                skipped += 1
                continue

            assignment = TaskAssignment(
                organization_id=task.organization_id,
                task_id=task.id,
                employee_id=employee_id,
                assigned_by_user_id=task.created_by_user_id,
                scheduled_for=target,
                due_at=recurring_due_at(task, target),
                status="ASSIGNED",
            )
            database.add(assignment)
            database.flush()

            database.add(
                TaskProgressLog(
                    organization_id=task.organization_id,
                    assignment_id=assignment.id,
                    actor_user_id=task.created_by_user_id,
                    action="ASSIGNED",
                    note="Automatically generated from recurring task.",
                    extra_data={"automatic": True, "date": target.isoformat()},
                )
            )
            created += 1

    database.commit()

    return {
        "date": target.isoformat(),
        "matched_tasks": matched,
        "created_assignments": created,
        "skipped_existing": skipped,
    }


def add_notification(
    database: Session,
    *,
    user: User,
    channel: str,
    title: str,
    body: str,
    payload: dict,
    dedupe_key: str,
) -> bool:
    row = Notification(
        organization_id=user.organization_id,
        recipient_user_id=user.id,
        channel=channel,
        title=title,
        body=body,
        payload=payload,
        dedupe_key=dedupe_key,
        status="PENDING",
        attempts=0,
        available_at=datetime.now(timezone.utc),
    )
    try:
        with database.begin_nested():
            database.add(row)
            database.flush()
        return True
    except IntegrityError:
        return False


def enqueue_renewal_notifications(database: Session, days: int = 60) -> dict:
    load_backend_env()
    email_enabled = bool(os.getenv("SMTP_HOST", "").strip())
    fcm_enabled = bool(os.getenv("FIREBASE_CREDENTIALS_FILE", "").strip())
    today_key = date.today().isoformat()

    recipients = list(
        database.scalars(
            select(User)
            .join(user_roles, User.id == user_roles.c.user_id)
            .join(Role, Role.id == user_roles.c.role_id)
            .where(Role.code.in_(ADMIN_ROLES))
            .distinct()
        ).all()
    )

    queued = 0
    duplicate = 0
    recipients_with_items = 0

    for user in recipients:
        items = upcoming_renewals(database, user=user, days=days)

        if not items:
            continue

        recipients_with_items += 1
        item_dicts = []

        for item in items:
            if hasattr(item, "model_dump"):
                item_dicts.append(
                    item.model_dump(mode="json")
                )
                continue

            converted = {}
            for key, value in dict(item).items():
                if isinstance(value, (date, datetime, UUID)):
                    converted[key] = value.isoformat() if hasattr(
                        value,
                        "isoformat",
                    ) else str(value)
                else:
                    converted[key] = value
            item_dicts.append(converted)
        lines = [
            f"- [{item['severity']}] {item['title']} | "
            f"{item['renewal_type']} | due {item['due_date']} | "
            f"{item['days_remaining']} day(s)"
            for item in item_dicts
        ]
        title = f"Renewal reminder: {len(items)} item(s)"
        body = "Upcoming and expired renewals:\n\n" + "\n".join(lines)
        payload = {
            "type": "RENEWAL_REMINDER",
            "count": len(items),
            "items": item_dicts[:50],
        }

        channels = ["IN_APP"]
        if email_enabled:
            channels.append("EMAIL")
        if fcm_enabled:
            channels.append("FCM")

        for channel in channels:
            was_added = add_notification(
                database,
                user=user,
                channel=channel,
                title=title,
                body=body,
                payload=payload,
                dedupe_key=(
                    f"renewal:{today_key}:{user.id}:{channel}"
                ),
            )
            if was_added:
                queued += 1
            else:
                duplicate += 1

    database.commit()

    return {
        "recipients_with_items": recipients_with_items,
        "queued": queued,
        "duplicates": duplicate,
        "email_enabled": email_enabled,
        "fcm_enabled": fcm_enabled,
    }


def send_email(recipient: str, subject: str, body: str) -> None:
    load_backend_env()

    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM_EMAIL", username).strip()
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"

    if not host or not sender:
        raise RuntimeError("SMTP configuration is incomplete.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP

    with smtp_class(host, port, timeout=30) as smtp:
        if use_tls and not use_ssl:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)


def get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    load_backend_env()
    credential_path = os.getenv("FIREBASE_CREDENTIALS_FILE", "").strip()

    if not credential_path:
        raise RuntimeError("FIREBASE_CREDENTIALS_FILE is not configured.")

    path = Path(credential_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path

    if not path.exists():
        raise RuntimeError(f"Firebase credential file not found: {path}")

    import firebase_admin
    from firebase_admin import credentials

    try:
        _firebase_app = firebase_admin.get_app()
    except ValueError:
        _firebase_app = firebase_admin.initialize_app(
            credentials.Certificate(str(path))
        )

    return _firebase_app


def fcm_tokens_for_user(database: Session, user_id: UUID) -> list[str]:
    employee = database.scalar(
        select(Employee).where(Employee.user_id == user_id)
    )
    if employee is None:
        return []

    return [
        token
        for token in database.scalars(
            select(Device.fcm_token).where(
                Device.employee_id == employee.id,
                Device.is_active.is_(True),
                Device.fcm_token.is_not(None),
                Device.fcm_token != "",
            )
        ).all()
        if token
    ]


def send_fcm(database: Session, notification: Notification) -> None:
    get_firebase_app()
    from firebase_admin import messaging

    tokens = fcm_tokens_for_user(
        database,
        notification.recipient_user_id,
    )
    if not tokens:
        raise RuntimeError("No FCM tokens are registered for this user.")

    def data_value(value) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, separators=(",", ":"), default=str)
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    android_channel = os.getenv(
        "FCM_ANDROID_CHANNEL_ID",
        "sands_workforce_alerts",
    ).strip() or "sands_workforce_alerts"
    response = messaging.send_each_for_multicast(
        messaging.MulticastMessage(
            notification=messaging.Notification(
                title=notification.title,
                body=notification.body,
            ),
            data={
                str(key): data_value(value)
                for key, value in (notification.payload or {}).items()
                if value is not None
            },
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id=android_channel,
                    priority="high",
                    default_sound=True,
                    default_vibrate_timings=True,
                    visibility="private",
                ),
            ),
            tokens=tokens[:500],
        )
    )

    if response.success_count == 0:
        raise RuntimeError("FCM delivery failed for every registered token.")


def dispatch_notifications(database: Session, batch_size: int = 100) -> dict:
    now = datetime.now(timezone.utc)
    rows = list(
        database.scalars(
            select(Notification)
            .where(
                Notification.status == "PENDING",
                Notification.available_at <= now,
                Notification.attempts < MAX_ATTEMPTS,
            )
            .order_by(Notification.created_at)
            .limit(batch_size)
        ).all()
    )

    sent = 0
    failed = 0

    for row in rows:
        row.attempts += 1

        try:
            recipient = database.get(User, row.recipient_user_id)
            if recipient is None:
                raise RuntimeError("Notification recipient was deleted.")

            if row.channel == "IN_APP":
                pass
            elif row.channel == "EMAIL":
                email = getattr(recipient, "email", None)
                if not email:
                    raise RuntimeError("Recipient has no email address.")
                send_email(email, row.title, row.body)
            elif row.channel == "FCM":
                send_fcm(database, row)
            else:
                raise RuntimeError(f"Unsupported channel: {row.channel}")

            row.status = "SENT"
            row.sent_at = datetime.now(timezone.utc)
            row.error_message = None
            sent += 1
        except Exception as error:
            row.error_message = str(error)[:5000]
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "FAILED"
            failed += 1

        database.commit()

    return {"processed": len(rows), "sent": sent, "failed_attempts": failed}
