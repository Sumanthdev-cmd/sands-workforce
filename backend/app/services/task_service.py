from datetime import date, datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Employee, Geofence, QuestionnaireSubmission, Role, Task, TaskAssignment, TaskProgressLog, User, user_roles
from app.schemas.tasks import AssignmentCompleteRequest, AssignmentProgressRequest, QuestionnaireSubmitRequest, TaskAssignmentCreateRequest, TaskCreateRequest, TaskUpdateRequest
from app.services.device_service import get_employee_for_user
from app.services.notification_service import queue_user_notification

MANAGER_ROLES = {"ADMIN", "MD", "GM", "MANAGER"}


def display_name(employee: Employee) -> str:
    return " ".join(part for part in [employee.first_name, employee.last_name] if part).strip()


def require_manager(database: Session, user: User) -> None:
    roles = set(database.scalars(select(Role.code).join(user_roles, Role.id == user_roles.c.role_id).where(user_roles.c.user_id == user.id)).all())
    if not roles.intersection(MANAGER_ROLES):
        raise HTTPException(status_code=403, detail="Task-management access is required")


def organization_timezone(user: User) -> ZoneInfo:
    timezone_name = (
        getattr(
            getattr(user, "organization", None),
            "timezone",
            None,
        )
        or "Asia/Kolkata"
    )

    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def local_date_for_datetime(
    value: datetime | None,
    user: User,
) -> date | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.date()

    return value.astimezone(
        organization_timezone(user)
    ).date()


def approved_leave_for_date(
    database: Session,
    *,
    organization_id: UUID,
    employee_id: UUID,
    target_date: date,
) -> dict | None:
    row = database.execute(
        text(
            """
            SELECT
                lr.start_date,
                lr.end_date,
                lt.code AS leave_type_code,
                lt.name AS leave_type_name
            FROM leave_requests lr
            LEFT JOIN leave_types lt
                ON lt.id = lr.leave_type_id
            WHERE
                lr.organization_id = :organization_id
                AND lr.employee_id = :employee_id
                AND lr.status = 'APPROVED'
                AND lr.start_date <= :target_date
                AND lr.end_date >= :target_date
            ORDER BY lr.start_date DESC
            LIMIT 1
            """
        ),
        {
            "organization_id": organization_id,
            "employee_id": employee_id,
            "target_date": target_date,
        },
    ).mappings().first()

    return dict(row) if row else None


def employee_assignment_availability(
    database: Session,
    user: User,
    *,
    scheduled_for: date,
    due_at: datetime | None = None,
) -> list[dict]:
    require_manager(database, user)

    due_date = local_date_for_datetime(
        due_at,
        user,
    )

    employees = database.execute(
        select(Employee, User)
        .join(User, Employee.user_id == User.id)
        .where(
            Employee.organization_id
            == user.organization_id
        )
        .order_by(User.employee_code)
    ).all()

    result: list[dict] = []

    for employee, account in employees:
        conflicts: list[dict] = []

        scheduled_leave = approved_leave_for_date(
            database,
            organization_id=user.organization_id,
            employee_id=employee.id,
            target_date=scheduled_for,
        )

        if scheduled_leave:
            conflicts.append(
                {
                    "date": scheduled_for.isoformat(),
                    "kind": "SCHEDULED_DATE",
                    **scheduled_leave,
                }
            )

        if (
            due_date is not None
            and due_date != scheduled_for
        ):
            due_leave = approved_leave_for_date(
                database,
                organization_id=user.organization_id,
                employee_id=employee.id,
                target_date=due_date,
            )

            if due_leave:
                conflicts.append(
                    {
                        "date": due_date.isoformat(),
                        "kind": "DUE_DATE",
                        **due_leave,
                    }
                )

        reason = None

        if conflicts:
            parts = []

            for conflict in conflicts:
                leave_name = (
                    conflict.get("leave_type_name")
                    or conflict.get("leave_type_code")
                    or "approved leave"
                )

                if conflict["kind"] == "SCHEDULED_DATE":
                    parts.append(
                        f"On {leave_name} on scheduled date "
                        f"{conflict['date']}"
                    )
                else:
                    parts.append(
                        f"On {leave_name} on due date "
                        f"{conflict['date']}"
                    )

            reason = "; ".join(parts)

        result.append(
            {
                "employee_id": employee.id,
                "employee_code": account.employee_code,
                "employee_name": display_name(employee),
                "available": not conflicts,
                "reason": reason,
                "conflicts": conflicts,
            }
        )

    return result


def human_task_duration(seconds: int | float) -> str:
    total = max(0, int(seconds))

    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts: list[str] = []

    if days:
        parts.append(
            f"{days} day{'s' if days != 1 else ''}"
        )

    if hours:
        parts.append(
            f"{hours} hour{'s' if hours != 1 else ''}"
        )

    if minutes or not parts:
        parts.append(
            f"{minutes} minute{'s' if minutes != 1 else ''}"
        )

    return " ".join(parts[:2])


def task_assignment_state(
    database: Session,
    user: User,
    assignment: TaskAssignment,
) -> dict:
    now = datetime.now(timezone.utc)

    due_at = assignment.due_at
    due_date = local_date_for_datetime(
        due_at,
        user,
    )

    leave_conflicts: list[str] = []

    scheduled_leave = approved_leave_for_date(
        database,
        organization_id=user.organization_id,
        employee_id=assignment.employee_id,
        target_date=assignment.scheduled_for,
    )

    if scheduled_leave:
        leave_name = (
            scheduled_leave.get("leave_type_name")
            or scheduled_leave.get("leave_type_code")
            or "approved leave"
        )

        leave_conflicts.append(
            f"{leave_name} on scheduled date "
            f"{assignment.scheduled_for}"
        )

    if (
        due_date is not None
        and due_date != assignment.scheduled_for
    ):
        due_leave = approved_leave_for_date(
            database,
            organization_id=user.organization_id,
            employee_id=assignment.employee_id,
            target_date=due_date,
        )

        if due_leave:
            leave_name = (
                due_leave.get("leave_type_name")
                or due_leave.get("leave_type_code")
                or "approved leave"
            )

            leave_conflicts.append(
                f"{leave_name} on due date {due_date}"
            )

    leave_conflict = bool(leave_conflicts)

    overdue_by_seconds = 0
    completed_late_by_seconds = 0

    status_code = str(
        assignment.status or ""
    ).upper()

    display_status = status_code or "ASSIGNED"

    if (
        status_code == "COMPLETED"
        and due_at is not None
        and assignment.completed_at is not None
        and assignment.completed_at > due_at
    ):
        completed_late_by_seconds = int(
            (
                assignment.completed_at
                - due_at
            ).total_seconds()
        )
        display_status = "COMPLETED_LATE"

    elif (
        status_code not in {
            "COMPLETED",
            "CANCELLED",
        }
        and leave_conflict
    ):
        display_status = "LEAVE_CONFLICT"

    elif (
        status_code not in {
            "COMPLETED",
            "CANCELLED",
        }
        and due_at is not None
        and due_at < now
    ):
        overdue_by_seconds = int(
            (now - due_at).total_seconds()
        )
        display_status = "OVERDUE"

    return {
        "display_status": display_status,
        "overdue_by_seconds":
            overdue_by_seconds,
        "completed_late_by_seconds":
            completed_late_by_seconds,
        "leave_conflict":
            leave_conflict,
        "leave_conflict_reason": (
            "; ".join(leave_conflicts)
            if leave_conflicts
            else None
        ),
    }


def assignment_parties(
    database: Session,
    assignment: TaskAssignment,
) -> tuple[User | None, User | None, Employee | None]:
    employee = database.get(
        Employee,
        assignment.employee_id,
    )

    employee_user = (
        database.get(User, employee.user_id)
        if employee is not None
        else None
    )

    assigner = database.get(
        User,
        assignment.assigned_by_user_id,
    )

    return employee_user, assigner, employee


def employee_label(
    employee_user: User | None,
    employee: Employee | None,
) -> str:
    code = (
        employee_user.employee_code
        if employee_user is not None
        else "Employee"
    )

    name = (
        display_name(employee)
        if employee is not None
        else ""
    )

    return (
        f"{code} - {name}"
        if name
        else code
    )


def queue_assignment_event_notifications(
    database: Session,
    *,
    assignment: TaskAssignment,
    task: Task,
    event: str,
    actor_user: User,
    note: str | None = None,
    event_token: str,
) -> None:
    employee_user, assigner, employee = (
        assignment_parties(
            database,
            assignment,
        )
    )

    label = employee_label(
        employee_user,
        employee,
    )

    route = (
        f"/module/tasks?assignment={assignment.id}"
        "&activity=1"
    )

    note_text = (
        f" Note: {note.strip()}"
        if note and note.strip()
        else ""
    )

    if event == "ASSIGNED":
        employee_title = "New task assigned"
        employee_body = (
            f"{actor_user.employee_code} assigned "
            f"'{task.title}' for "
            f"{assignment.scheduled_for}."
            f"{note_text}"
        )
        assigner_title = None
        assigner_body = None

    elif event == "STARTED":
        employee_title = "Task started"
        employee_body = (
            f"Your task '{task.title}' is now in progress."
            f"{note_text}"
        )
        assigner_title = "Assigned task started"
        assigner_body = (
            f"{label} started '{task.title}'."
            f"{note_text}"
        )

    elif event == "PROGRESS":
        employee_title = "Task progress recorded"
        employee_body = (
            f"Your progress update for '{task.title}' "
            f"was recorded.{note_text}"
        )
        assigner_title = "Task progress update"
        assigner_body = (
            f"{label} updated '{task.title}'."
            f"{note_text}"
        )

    elif event == "QUESTIONNAIRE_SUBMITTED":
        employee_title = "Task report submitted"
        employee_body = (
            f"Your report for '{task.title}' was submitted."
        )
        assigner_title = "Task report submitted"
        assigner_body = (
            f"{label} submitted the report for "
            f"'{task.title}'."
        )

    elif event == "COMPLETED":
        late_text = ""

        if (
            assignment.due_at is not None
            and assignment.completed_at is not None
            and assignment.completed_at
            > assignment.due_at
        ):
            late_seconds = (
                assignment.completed_at
                - assignment.due_at
            ).total_seconds()

            late_text = (
                " Completed late by "
                f"{human_task_duration(late_seconds)}."
            )

        employee_title = (
            "Task completed late"
            if late_text
            else "Task completed"
        )

        employee_body = (
            f"Your task '{task.title}' was marked completed."
            f"{late_text}"
            f"{note_text}"
        )

        assigner_title = (
            "Assigned task completed late"
            if late_text
            else "Assigned task completed"
        )

        assigner_body = (
            f"{label} completed '{task.title}'."
            f"{late_text}"
            f"{note_text}"
        )

    else:
        return

    if employee_user is not None:
        queue_user_notification(
            database,
            organization_id=assignment.organization_id,
            recipient_user_id=employee_user.id,
            title=employee_title,
            body=employee_body,
            dedupe_key=(
                f"task:{assignment.id}:{event}:"
                f"{event_token}:employee"
            ),
            route=route,
            module="tasks",
            event=f"TASK_{event}",
            entity_id=assignment.id,
        )

    if (
        assigner_title
        and assigner_body
        and assigner is not None
        and (
            employee_user is None
            or assigner.id != employee_user.id
        )
    ):
        queue_user_notification(
            database,
            organization_id=assignment.organization_id,
            recipient_user_id=assigner.id,
            title=assigner_title,
            body=assigner_body,
            dedupe_key=(
                f"task:{assignment.id}:{event}:"
                f"{event_token}:assigner"
            ),
            route=route,
            module="tasks",
            event=f"TASK_{event}",
            entity_id=assignment.id,
        )


def get_task(database: Session, organization_id: UUID, task_id: UUID) -> Task:
    task = database.scalar(select(Task).where(Task.id == task_id, Task.organization_id == organization_id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task was not found")
    return task


def create_task(database: Session, user: User, payload: TaskCreateRequest) -> Task:
    require_manager(database, user)
    if payload.geofence_id:
        geofence = database.scalar(select(Geofence).where(Geofence.id == payload.geofence_id, Geofence.organization_id == user.organization_id, Geofence.is_active.is_(True)))
        if geofence is None:
            raise HTTPException(status_code=404, detail="Active geofence was not found")
    task = Task(organization_id=user.organization_id, created_by_user_id=user.id, geofence_id=payload.geofence_id, title=payload.title.strip(), description=payload.description, task_type=payload.task_type, priority=payload.priority, recurrence_type=payload.recurrence_type, recurrence_interval=payload.recurrence_interval, recurrence_days=payload.recurrence_days, starts_at=payload.starts_at, due_at=payload.due_at, location_required=payload.location_required, questionnaire_schema=payload.questionnaire_schema)
    database.add(task)
    database.commit()
    database.refresh(task)
    return task


def list_tasks(database: Session, user: User, task_type: str | None, active_only: bool) -> list[Task]:
    require_manager(database, user)
    statement = select(Task).where(Task.organization_id == user.organization_id)
    if active_only:
        statement = statement.where(Task.is_active.is_(True))
    if task_type:
        statement = statement.where(Task.task_type == task_type.strip().upper())
    return list(database.scalars(statement.order_by(Task.created_at.desc())).all())


def update_task(database: Session, user: User, task_id: UUID, payload: TaskUpdateRequest) -> Task:
    require_manager(database, user)
    task = get_task(database, user.organization_id, task_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    database.commit()
    database.refresh(task)
    return task


def assign_task(
    database: Session,
    user: User,
    task_id: UUID,
    payload: TaskAssignmentCreateRequest,
) -> list[TaskAssignment]:
    require_manager(database, user)

    task = get_task(
        database,
        user.organization_id,
        task_id,
    )

    employees = list(
        database.scalars(
            select(Employee).where(
                Employee.organization_id
                == user.organization_id,
                Employee.id.in_(
                    payload.employee_ids
                ),
            )
        ).all()
    )

    found = {
        employee.id
        for employee in employees
    }

    missing = [
        str(value)
        for value in payload.employee_ids
        if value not in found
    ]

    if missing:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Employees not found",
                "employee_ids": missing,
            },
        )

    # Deadlines belong to assignments, not reusable catalogue definitions.
    # Do not inherit stale task-level dates from older catalogue entries.
    effective_due_at = payload.due_at

    due_date = local_date_for_datetime(
        effective_due_at,
        user,
    )

    if (
        due_date is not None
        and due_date < payload.scheduled_for
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Task due date cannot be before "
                "the scheduled date."
            ),
        )

    accounts = {
        row.id: row.employee_code
        for row in database.execute(
            select(
                Employee.id,
                User.employee_code,
            )
            .join(
                User,
                Employee.user_id == User.id,
            )
            .where(
                Employee.organization_id
                == user.organization_id,
                Employee.id.in_(
                    payload.employee_ids
                ),
            )
        ).all()
    }

    unavailable: list[str] = []

    for employee in employees:
        conflicts: list[str] = []

        scheduled_leave = approved_leave_for_date(
            database,
            organization_id=user.organization_id,
            employee_id=employee.id,
            target_date=payload.scheduled_for,
        )

        if scheduled_leave:
            conflicts.append(
                f"scheduled date "
                f"{payload.scheduled_for}"
            )

        if (
            due_date is not None
            and due_date
            != payload.scheduled_for
        ):
            due_leave = approved_leave_for_date(
                database,
                organization_id=user.organization_id,
                employee_id=employee.id,
                target_date=due_date,
            )

            if due_leave:
                conflicts.append(
                    f"due date {due_date}"
                )

        if conflicts:
            code = accounts.get(
                employee.id,
                str(employee.id),
            )

            unavailable.append(
                f"{code} is on approved leave on "
                + " and ".join(conflicts)
            )

    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Task assignment blocked. "
                + "; ".join(unavailable)
                + ". Choose an available employee "
                "or change the task dates."
            ),
        )

    result: list[TaskAssignment] = []

    for employee in employees:
        assignment = database.scalar(
            select(TaskAssignment).where(
                TaskAssignment.task_id
                == task.id,
                TaskAssignment.employee_id
                == employee.id,
                TaskAssignment.scheduled_for
                == payload.scheduled_for,
            )
        )

        if assignment is None:
            assignment = TaskAssignment(
                organization_id=user.organization_id,
                task_id=task.id,
                employee_id=employee.id,
                assigned_by_user_id=user.id,
                scheduled_for=payload.scheduled_for,
                due_at=effective_due_at,
            )

            database.add(assignment)
            database.flush()

            log = TaskProgressLog(
                organization_id=user.organization_id,
                assignment_id=assignment.id,
                actor_user_id=user.id,
                action="ASSIGNED",
                note="Task assigned",
            )

            database.add(log)
            database.flush()

            queue_assignment_event_notifications(
                database,
                assignment=assignment,
                task=task,
                event="ASSIGNED",
                actor_user=user,
                note=None,
                event_token=str(log.id),
            )

        result.append(assignment)

    database.commit()

    for assignment in result:
        database.refresh(assignment)

    return result

def list_my_tasks(
    database: Session,
    user: User,
    assignment_status: str | None,
) -> list[dict]:
    employee = get_employee_for_user(
        database,
        user,
    )

    statement = (
        select(
            TaskAssignment,
            Task,
        )
        .join(
            Task,
            TaskAssignment.task_id == Task.id,
        )
        .where(
            TaskAssignment.organization_id
            == user.organization_id,
            TaskAssignment.employee_id
            == employee.id,
        )
    )

    if assignment_status:
        statement = statement.where(
            TaskAssignment.status
            == assignment_status.strip().upper()
        )

    rows = database.execute(
        statement.order_by(
            TaskAssignment.scheduled_for.desc(),
            TaskAssignment.created_at.desc(),
        )
    ).all()

    result: list[dict] = []

    for assignment, task in rows:
        state = task_assignment_state(
            database,
            user,
            assignment,
        )

        result.append(
            {
                "id": assignment.id,
                "organization_id":
                    assignment.organization_id,
                "task_id":
                    assignment.task_id,
                "employee_id":
                    assignment.employee_id,
                "scheduled_for":
                    assignment.scheduled_for,
                "due_at":
                    assignment.due_at,
                "status":
                    assignment.status,
                "started_at":
                    assignment.started_at,
                "completed_at":
                    assignment.completed_at,
                "completion_note":
                    assignment.completion_note,
                "evidence_urls":
                    assignment.evidence_urls,
                "completion_latitude":
                    assignment.completion_latitude,
                "completion_longitude":
                    assignment.completion_longitude,
                "created_at":
                    assignment.created_at,
                "updated_at":
                    assignment.updated_at,
                "task_title":
                    task.title,
                "task_description":
                    task.description,
                "task_type":
                    task.task_type,
                "priority":
                    task.priority,
                "location_required":
                    task.location_required,
                "geofence_id":
                    task.geofence_id,
                "questionnaire_schema":
                    task.questionnaire_schema,
                **state,
            }
        )

    return result

def owned_assignment(database: Session, user: User, assignment_id: UUID):
    employee = get_employee_for_user(database, user)
    row = database.execute(select(TaskAssignment, Task).join(Task, TaskAssignment.task_id == Task.id).where(TaskAssignment.id == assignment_id, TaskAssignment.organization_id == user.organization_id, TaskAssignment.employee_id == employee.id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Assigned task was not found")
    return row[0], row[1], employee


def start_assignment(
    database: Session,
    user: User,
    assignment_id: UUID,
    payload: AssignmentProgressRequest,
) -> TaskAssignment:
    assignment, task, _ = owned_assignment(
        database,
        user,
        assignment_id,
    )

    if assignment.status == "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Completed task cannot be "
                "started again"
            ),
        )

    assignment.started_at = (
        assignment.started_at
        or datetime.now(timezone.utc)
    )
    assignment.status = "IN_PROGRESS"

    log = TaskProgressLog(
        organization_id=user.organization_id,
        assignment_id=assignment.id,
        actor_user_id=user.id,
        action="STARTED",
        note=payload.note,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )

    database.add(log)
    database.flush()

    queue_assignment_event_notifications(
        database,
        assignment=assignment,
        task=task,
        event="STARTED",
        actor_user=user,
        note=payload.note,
        event_token=str(log.id),
    )

    database.commit()
    database.refresh(assignment)
    return assignment

def add_progress(
    database: Session,
    user: User,
    assignment_id: UUID,
    payload: AssignmentProgressRequest,
) -> TaskProgressLog:
    assignment, task, _ = owned_assignment(
        database,
        user,
        assignment_id,
    )

    if assignment.status == "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail=(
                "Completed task cannot receive "
                "progress updates"
            ),
        )

    assignment.started_at = (
        assignment.started_at
        or datetime.now(timezone.utc)
    )
    assignment.status = "IN_PROGRESS"

    log = TaskProgressLog(
        organization_id=user.organization_id,
        assignment_id=assignment.id,
        actor_user_id=user.id,
        action="PROGRESS",
        note=payload.note,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )

    database.add(log)
    database.flush()

    queue_assignment_event_notifications(
        database,
        assignment=assignment,
        task=task,
        event="PROGRESS",
        actor_user=user,
        note=payload.note,
        event_token=str(log.id),
    )

    database.commit()
    database.refresh(log)
    return log

def validate_answers(schema: dict, answers: dict) -> None:
    missing = []
    for question in schema.get("questions", []):
        qid = str(question.get("id", "")).strip()
        if qid and question.get("required") is True and answers.get(qid) in (None, "", []):
            missing.append(qid)
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Required answers are missing", "question_ids": missing})


def submit_questionnaire(database: Session, user: User, assignment_id: UUID, payload: QuestionnaireSubmitRequest) -> QuestionnaireSubmission:
    assignment, task, employee = owned_assignment(database, user, assignment_id)
    if task.questionnaire_schema is None:
        raise HTTPException(status_code=400, detail="This task has no questionnaire")
    validate_answers(task.questionnaire_schema, payload.answers)
    submission = database.scalar(select(QuestionnaireSubmission).where(QuestionnaireSubmission.assignment_id == assignment.id))
    if submission is None:
        submission = QuestionnaireSubmission(organization_id=user.organization_id, assignment_id=assignment.id, employee_id=employee.id, answers=payload.answers, submitted_at=datetime.now(timezone.utc))
        database.add(submission)
    submission.answers = payload.answers
    submission.submitted_at = datetime.now(timezone.utc)
    submission.latitude = payload.latitude
    submission.longitude = payload.longitude
    submission.is_final = payload.is_final
    log = TaskProgressLog(
        organization_id=user.organization_id,
        assignment_id=assignment.id,
        actor_user_id=user.id,
        action="QUESTIONNAIRE_SUBMITTED",
        note="Questionnaire submitted",
    )
    database.add(log)
    database.flush()

    queue_assignment_event_notifications(
        database,
        assignment=assignment,
        task=task,
        event="QUESTIONNAIRE_SUBMITTED",
        actor_user=user,
        note=None,
        event_token=str(log.id),
    )

    database.commit()
    database.refresh(submission)
    return submission


def complete_assignment(
    database: Session,
    user: User,
    assignment_id: UUID,
    payload: AssignmentCompleteRequest,
) -> TaskAssignment:
    assignment, task, _ = owned_assignment(
        database,
        user,
        assignment_id,
    )

    if assignment.status == "COMPLETED":
        raise HTTPException(
            status_code=409,
            detail="Task is already completed",
        )

    if (
        task.location_required
        and (
            payload.latitude is None
            or payload.longitude is None
        )
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Completion latitude and "
                "longitude are required"
            ),
        )

    if task.questionnaire_schema is not None:
        final = database.scalar(
            select(QuestionnaireSubmission).where(
                QuestionnaireSubmission.assignment_id
                == assignment.id,
                QuestionnaireSubmission.is_final
                .is_(True),
            )
        )

        if final is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Submit the final "
                    "questionnaire first"
                ),
            )

    now = datetime.now(timezone.utc)

    assignment.started_at = (
        assignment.started_at
        or now
    )
    assignment.status = "COMPLETED"
    assignment.completed_at = now
    assignment.completion_note = (
        payload.completion_note
    )
    assignment.evidence_urls = (
        payload.evidence_urls
    )
    assignment.completion_latitude = (
        payload.latitude
    )
    assignment.completion_longitude = (
        payload.longitude
    )

    log = TaskProgressLog(
        organization_id=user.organization_id,
        assignment_id=assignment.id,
        actor_user_id=user.id,
        action="COMPLETED",
        note=payload.completion_note,
        latitude=payload.latitude,
        longitude=payload.longitude,
        extra_data={
            "evidence_urls":
                payload.evidence_urls
        },
    )

    database.add(log)
    database.flush()

    queue_assignment_event_notifications(
        database,
        assignment=assignment,
        task=task,
        event="COMPLETED",
        actor_user=user,
        note=payload.completion_note,
        event_token=str(log.id),
    )

    database.commit()
    database.refresh(assignment)
    return assignment

def list_task_assignments(database: Session, user: User, task_id: UUID) -> list[dict]:
    require_manager(database, user)
    task = get_task(database, user.organization_id, task_id)
    rows = database.execute(select(TaskAssignment, Employee, User).join(Employee, TaskAssignment.employee_id == Employee.id).join(User, Employee.user_id == User.id).where(TaskAssignment.task_id == task.id, TaskAssignment.organization_id == user.organization_id).order_by(TaskAssignment.scheduled_for.desc(), User.employee_code)).all()
    return [{"id": a.id, "organization_id": a.organization_id, "task_id": a.task_id, "employee_id": a.employee_id, "scheduled_for": a.scheduled_for, "due_at": a.due_at, "status": a.status, "started_at": a.started_at, "completed_at": a.completed_at, "completion_note": a.completion_note, "evidence_urls": a.evidence_urls, "completion_latitude": a.completion_latitude, "completion_longitude": a.completion_longitude, "created_at": a.created_at, "updated_at": a.updated_at, "employee_code": u.employee_code, "employee_name": display_name(e), "task_title": task.title, "task_type": task.task_type, "priority": task.priority} for a, e, u in rows]


def list_task_submissions(database: Session, user: User, task_id: UUID) -> list[QuestionnaireSubmission]:
    require_manager(database, user)
    task = get_task(database, user.organization_id, task_id)
    return list(database.scalars(select(QuestionnaireSubmission).join(TaskAssignment, QuestionnaireSubmission.assignment_id == TaskAssignment.id).where(TaskAssignment.task_id == task.id, QuestionnaireSubmission.organization_id == user.organization_id).order_by(QuestionnaireSubmission.submitted_at.desc())).all())


def list_progress(database: Session, user: User, assignment_id: UUID) -> list[TaskProgressLog]:
    assignment = database.scalar(select(TaskAssignment).where(TaskAssignment.id == assignment_id, TaskAssignment.organization_id == user.organization_id))
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assigned task was not found")
    employee = database.scalar(select(Employee).where(Employee.user_id == user.id, Employee.organization_id == user.organization_id))
    if employee is None or employee.id != assignment.employee_id:
        require_manager(database, user)
    return list(database.scalars(select(TaskProgressLog).where(TaskProgressLog.assignment_id == assignment.id).order_by(TaskProgressLog.created_at)).all())



def assignment_activity(
    database: Session,
    user: User,
    assignment_id: UUID,
) -> dict:
    row = database.execute(
        select(
            TaskAssignment,
            Task,
            Employee,
            User,
        )
        .join(
            Task,
            TaskAssignment.task_id == Task.id,
        )
        .join(
            Employee,
            TaskAssignment.employee_id
            == Employee.id,
        )
        .join(
            User,
            Employee.user_id == User.id,
        )
        .where(
            TaskAssignment.id == assignment_id,
            TaskAssignment.organization_id
            == user.organization_id,
        )
    ).first()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Assigned task was not found",
        )

    assignment, task, employee, account = row

    current_employee = database.scalar(
        select(Employee).where(
            Employee.user_id == user.id,
            Employee.organization_id
            == user.organization_id,
        )
    )

    if (
        current_employee is None
        or current_employee.id
        != assignment.employee_id
    ):
        require_manager(database, user)

    logs = list(
        database.scalars(
            select(TaskProgressLog)
            .where(
                TaskProgressLog.assignment_id
                == assignment.id
            )
            .order_by(
                TaskProgressLog.created_at
            )
        ).all()
    )

    state = task_assignment_state(
        database,
        user,
        assignment,
    )

    return {
        "assignment_id": assignment.id,
        "task_title": task.title,
        "employee_code": account.employee_code,
        "employee_name": display_name(employee),
        "scheduled_for": assignment.scheduled_for,
        "due_at": assignment.due_at,
        "status": assignment.status,
        **state,
        "assigned_by_user_id":
            assignment.assigned_by_user_id,
        "logs": [
            {
                "id": log.id,
                "action": log.action,
                "note": log.note,
                "created_at": log.created_at,
                "actor_user_id":
                    log.actor_user_id,
            }
            for log in logs
        ],
    }
