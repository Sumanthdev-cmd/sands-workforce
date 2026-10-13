"""Read-only assignment oversight and actionable workday/phone diagnostics."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from app.models import AttendanceRecord, Employee, Notification, Task, TaskAssignment, TaskProgressLog, User
from app.services import mobile_push_store as push
from app.services.attendance_service import get_active_assignment
from app.services.task_service import display_name, organization_timezone, require_manager, task_assignment_state


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def phone_registrations(database, organization_id, user_ids):
    if not user_ids:
        return {}
    rows = database.execute(select(
        push.devices.c.recipient_id, push.devices.c.installation_id,
        push.devices.c.binding_id, push.devices.c.enabled,
        push.devices.c.since, push.devices.c.seen_at, push.devices.c.expires_at,
        push.devices.c.fcm_token.is_not(None).label("has_token"),
    ).where(push.devices.c.organization_id == organization_id,
            push.devices.c.recipient_kind == "employee",
            push.devices.c.recipient_id.in_(user_ids))).mappings().all()
    grouped = {}
    for row in rows:
        grouped.setdefault(row["recipient_id"], []).append(row)
    return grouped


def alert_summary(notification, phones, deliveries, now=None):
    now = now or datetime.now(timezone.utc)
    active = [p for p in phones if p["enabled"] and p["has_token"] and utc(p["expires_at"]) > now]
    result = {"registered_phones": len(active), "error_code": None}
    if notification is None:
        return {**result, "state": "NO_ALERT", "message": "No assignment alert recorded"}
    # A provider acknowledgement is not proof that Android displayed a notification.
    if any(d["status"] == "SENT" for d in deliveries):
        return {**result, "state": "SENT", "message": "Sent to Firebase"}
    if notification.read_at is not None:
        return {**result, "state": "READ", "message": "Read in workspace"}
    if not active:
        return {**result, "state": "NO_PHONE", "message": "No phone registered with alerts enabled"}
    if utc(notification.created_at) < now - timedelta(hours=24):
        return {**result, "state": "EXPIRED", "message": "Alert is over 24 hours old"}
    eligible = [p for p in active if utc(p["since"]) <= utc(notification.created_at)]
    if not eligible:
        return {**result, "state": "BEFORE_REGISTRATION", "message": "Assigned before phone alerts were connected"}
    bindings = {(p["installation_id"], p["binding_id"]) for p in eligible}
    current = [d for d in deliveries if (d["installation_id"], d["binding_id"]) in bindings]
    retry = next((d for d in current if d["status"] == "PENDING"), None)
    failed = next((d for d in current if d["status"] == "FAILED"), None)
    if retry:
        return {**result, "state": "PENDING", "message": "Retrying delivery" if retry["attempts"] else "Waiting for push worker",
                "error_code": retry["error_code"]}
    if failed:
        return {**result, "state": "FAILED", "message": "Phone alert delivery failed", "error_code": failed["error_code"]}
    return {**result, "state": "WAITING", "message": "Waiting for push worker"}


def list_team_assignments(database, user, *, search="", assignment_status=None,
                          start_date=None, end_date=None, offset=0, limit=50):
    require_manager(database, user)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "From date must be on or before To date.")
    assignee = aliased(User)
    assigner = aliased(User)
    organization_id = user.organization_id
    statement = (select(TaskAssignment, Task, Employee, assignee, assigner)
        .join(Task, and_(Task.id == TaskAssignment.task_id, Task.organization_id == organization_id))
        .join(Employee, and_(Employee.id == TaskAssignment.employee_id, Employee.organization_id == organization_id))
        .join(assignee, and_(assignee.id == Employee.user_id, assignee.organization_id == organization_id))
        .outerjoin(assigner, and_(assigner.id == TaskAssignment.assigned_by_user_id, assigner.organization_id == organization_id))
        .where(TaskAssignment.organization_id == organization_id))
    if search.strip():
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = f"%{escaped}%"
        statement = statement.where(or_(*(field.ilike(term, escape="\\") for field in
            (Task.title, Employee.first_name, Employee.last_name, assignee.employee_code))))
    if start_date:
        statement = statement.where(TaskAssignment.scheduled_for >= start_date)
    if end_date:
        statement = statement.where(TaskAssignment.scheduled_for <= end_date)
    now = datetime.now(timezone.utc)
    if assignment_status == "OVERDUE":
        statement = statement.where(TaskAssignment.status.notin_(["COMPLETED", "CANCELLED"]), TaskAssignment.due_at < now)
    elif assignment_status == "COMPLETED_LATE":
        statement = statement.where(TaskAssignment.status == "COMPLETED", TaskAssignment.completed_at > TaskAssignment.due_at)
    elif assignment_status:
        if assignment_status not in {"ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"}:
            raise HTTPException(422, "Choose a supported assignment status.")
        statement = statement.where(TaskAssignment.status == assignment_status)
    total = database.scalar(select(func.count()).select_from(statement.subquery()))
    rows = database.execute(statement.order_by(TaskAssignment.scheduled_for.desc(), TaskAssignment.created_at.desc(), TaskAssignment.id)
                            .offset(offset).limit(limit)).all()
    ids = [a.id for a, *_ in rows]
    if not ids:
        return {"items": [], "total": total, "offset": offset, "limit": limit}
    latest, log_counts = {}, {}
    for log in database.scalars(select(TaskProgressLog).where(
            TaskProgressLog.organization_id == organization_id, TaskProgressLog.assignment_id.in_(ids))
            .order_by(TaskProgressLog.created_at.desc(), TaskProgressLog.id.desc())).all():
        latest.setdefault(log.assignment_id, log)
        log_counts[log.assignment_id] = log_counts.get(log.assignment_id, 0) + 1
    user_ids = [account.id for _, _, _, account, _ in rows]
    phones = phone_registrations(database, organization_id, user_ids)
    notices = database.scalars(select(Notification).where(
        Notification.organization_id == organization_id, Notification.channel == "IN_APP",
        Notification.recipient_user_id.in_(user_ids),
        Notification.payload["event"].as_string() == "TASK_ASSIGNED",
        Notification.payload["entity_id"].as_string().in_([str(i) for i in ids]))
        .order_by(Notification.created_at.desc())).all()
    notifications = {}
    for notice in notices:
        notifications.setdefault((str(notice.payload.get("entity_id")), notice.recipient_user_id), notice)
    by_notification = {}
    if notices:
        # Join through the source alert to enforce tenant ownership of delivery metadata.
        deliveries = database.execute(select(push.deliveries).join(Notification,
            push.deliveries.c.notification_id == Notification.id).where(
            Notification.organization_id == organization_id,
            push.deliveries.c.recipient_kind == "employee",
            push.deliveries.c.notification_id.in_([n.id for n in notices]))).mappings().all()
        for delivery in deliveries:
            by_notification.setdefault(delivery["notification_id"], []).append(delivery)
    items = []
    for assignment, task, employee, account, owner in rows:
        log = latest.get(assignment.id)
        notice = notifications.get((str(assignment.id), account.id))
        items.append({
            "id": assignment.id, "task_id": task.id, "task_title": task.title, "priority": task.priority,
            "employee_id": employee.id, "employee_code": account.employee_code, "employee_name": display_name(employee),
            "assigned_by": owner.employee_code if owner else "—", "scheduled_for": assignment.scheduled_for,
            "due_at": assignment.due_at, "status": assignment.status, "started_at": assignment.started_at,
            "completed_at": assignment.completed_at, "completion_note": assignment.completion_note,
            "latest_note": log.note if log else None, "latest_action": log.action if log else None,
            "latest_at": log.created_at if log else assignment.created_at, "activity_count": log_counts.get(assignment.id, 0),
            **task_assignment_state(database, user, assignment),
            "phone_alert": alert_summary(notice, phones.get(account.id, []),
                by_notification.get(notice.id, []) if notice else [], now),
        })
    return {"items": items, "total": total, "offset": offset, "limit": limit}


def employee_readiness(database, user):
    """Explain existing rules. Never create profiles or bypass location restrictions."""
    now = datetime.now(timezone.utc)
    today = now.astimezone(organization_timezone(user)).date()
    profile = database.scalar(select(Employee).where(Employee.user_id == user.id, Employee.organization_id == user.organization_id))
    messages = []
    if profile is None:
        messages.append("Employee profile is missing. Ask Admin to link your existing login to an employee profile in this organisation.")
    location = None
    attendance = None
    if profile is not None:
        try:
            _, fence = get_active_assignment(database, organization_id=user.organization_id, employee_id=profile.id, attendance_date=today)
            location = fence.name
        except HTTPException as error:
            messages.append(str(error.detail) + " Admin can assign it under Attendance → Work locations.")
        attendance = database.scalar(select(AttendanceRecord).where(
            AttendanceRecord.organization_id == user.organization_id, AttendanceRecord.employee_id == profile.id,
            AttendanceRecord.attendance_date == today))
        if attendance and attendance.check_out_at:
            messages.append("Today's attendance is already checked out. A second check-in on the same date is not supported; ask Admin if the record needs correction.")
    phones = phone_registrations(database, user.organization_id, [user.id]).get(user.id, [])
    count = sum(p["enabled"] and p["has_token"] and utc(p["expires_at"]) > now for p in phones)
    if not messages:
        messages.append("Employee profile and work location are configured. Check-in still requires a fresh location inside the assigned work area.")
    messages.append(f"Phone alerts: {count} registered phone(s) enabled." if count else
                    "Phone alerts: no enabled phone is registered. Open Notification settings / enable alerts on this employee's phone.")
    return {"profile_found": profile is not None, "work_location": location, "registered_phones": count, "messages": messages}
