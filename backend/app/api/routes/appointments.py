from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.models import Employee, Role, User, user_roles
from app.models.appointment import Appointment, AppointmentAction
from app.schemas.appointment import (
    AppointmentActionResponse,
    AppointmentApprovalRequest,
    AppointmentCreateRequest,
    AppointmentResponse,
    ReasonRequest,
)
from app.services.device_service import get_employee_for_user
from app.services.notification_service import (
    queue_role_notifications,
    queue_user_notification,
)


router = APIRouter(prefix="/appointments", tags=["MD Appointments"])
DatabaseSession = Annotated[Session, Depends(get_db)]

MD_ROLES = {"MD"}
VIEW_ROLES = {"MD"}


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_md(database: Session, user: User) -> None:
    if not role_codes(database, user).intersection(MD_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an MD can perform this action.",
        )


def get_appointment(
    database: Session,
    user: User,
    appointment_id: UUID,
) -> Appointment:
    row = database.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment was not found.",
        )
    return row


def appointment_dict(database: Session, row: Appointment) -> dict:
    employee = database.get(Employee, row.requester_employee_id)
    employee_user = (
        database.get(User, employee.user_id)
        if employee is not None
        else None
    )
    return {
        "id": row.id,
        "requester_employee_id": row.requester_employee_id,
        "subject": row.subject,
        "agenda": row.agenda,
        "requested_start_at": row.requested_start_at,
        "requested_end_at": row.requested_end_at,
        "approved_start_at": row.approved_start_at,
        "approved_end_at": row.approved_end_at,
        "meeting_mode": row.meeting_mode,
        "location": row.location,
        "meeting_url": row.meeting_url,
        "reminder_minutes": row.reminder_minutes,
        "status": row.status,
        "md_user_id": row.md_user_id,
        "decided_by_user_id": row.decided_by_user_id,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
        "completed_at": row.completed_at,
        "requester_employee_code": getattr(employee_user, "employee_code", None),
        "requester_name": getattr(employee, "full_name", None),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def requester_user(database: Session, row: Appointment) -> User:
    employee = database.get(Employee, row.requester_employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Requester employee no longer exists.",
        )

    user = database.get(User, employee.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Requester user no longer exists.",
        )
    return user


def ensure_access(
    database: Session,
    user: User,
    row: Appointment,
) -> None:
    employee = database.scalar(
        select(Employee).where(
            Employee.user_id == user.id,
            Employee.organization_id == user.organization_id,
        )
    )
    owner = employee is not None and employee.id == row.requester_employee_id

    if not owner and not role_codes(database, user).intersection(VIEW_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this appointment.",
        )


@router.post("", response_model=AppointmentResponse, status_code=201)
def create_appointment(
    payload: AppointmentCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    employee = get_employee_for_user(database, current_user)

    mode = payload.meeting_mode.strip().upper()
    location = payload.location.strip() if payload.location else None

    if payload.requested_end_at <= payload.requested_start_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Requested end time must be later than start time.",
        )

    if mode == "OFFLINE" and not location:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Physical appointments require a location.",
        )

    row = Appointment(
        organization_id=current_user.organization_id,
        requester_employee_id=employee.id,
        subject=payload.subject.strip(),
        agenda=payload.agenda.strip(),
        requested_start_at=payload.requested_start_at,
        requested_end_at=payload.requested_end_at,
        meeting_mode=mode,
        location=location,
        reminder_minutes=payload.reminder_minutes,
        status="PENDING",
    )
    database.add(row)
    database.flush()

    database.add(
        AppointmentAction(
            organization_id=current_user.organization_id,
            appointment_id=row.id,
            actor_user_id=current_user.id,
            action="REQUESTED",
            note="Appointment requested with MD.",
        )
    )

    requester_label = current_user.employee_code
    if employee.full_name:
        requester_label += f" - {employee.full_name}"

    queue_role_notifications(
        database,
        organization_id=current_user.organization_id,
        role_codes=MD_ROLES,
        title="New MD appointment request",
        body=f"{requester_label} requested an appointment: {row.subject}.",
        dedupe_prefix=f"appointment:{row.id}:requested",
        route=f"/module/appointments?queue=pending&appointment={row.id}",
        module="appointments",
        event="APPOINTMENT_REQUESTED",
        entity_id=row.id,
        exclude_user_ids={current_user.id},
    )

    database.commit()
    database.refresh(row)
    return appointment_dict(database, row)


@router.get("/me", response_model=list[AppointmentResponse])
def my_appointments(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    employee = get_employee_for_user(database, current_user)
    rows = list(
        database.scalars(
            select(Appointment)
            .where(
                Appointment.organization_id == current_user.organization_id,
                Appointment.requester_employee_id == employee.id,
            )
            .order_by(Appointment.created_at.desc())
        ).all()
    )
    return [appointment_dict(database, row) for row in rows]


@router.get("/pending", response_model=list[AppointmentResponse])
def pending_appointments(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    require_md(database, current_user)

    rows = list(
        database.scalars(
            select(Appointment)
            .where(
                Appointment.organization_id == current_user.organization_id,
                Appointment.status == "PENDING",
            )
            .order_by(Appointment.requested_start_at)
        ).all()
    )
    return [appointment_dict(database, row) for row in rows]


@router.get("/managed", response_model=list[AppointmentResponse])
def managed_appointments(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    require_md(database, current_user)

    rows = list(
        database.scalars(
            select(Appointment)
            .where(Appointment.organization_id == current_user.organization_id)
            .order_by(Appointment.created_at.desc())
            .limit(250)
        ).all()
    )
    return [appointment_dict(database, row) for row in rows]


@router.get("/{appointment_id}", response_model=AppointmentResponse)
def read_appointment(
    appointment_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    row = get_appointment(database, current_user, appointment_id)
    ensure_access(database, current_user, row)
    return appointment_dict(database, row)


@router.post("/{appointment_id}/approve", response_model=AppointmentResponse)
def approve_appointment(
    appointment_id: UUID,
    payload: AppointmentApprovalRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    require_md(database, current_user)
    row = get_appointment(database, current_user, appointment_id)

    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending appointments can be approved.",
        )

    start_at = payload.approved_start_at or row.requested_start_at
    end_at = payload.approved_end_at or row.requested_end_at

    if end_at <= start_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Approved end time must be later than start time.",
        )

    meeting_mode = (
        getattr(payload, "meeting_mode", None)
        or row.meeting_mode
        or "ONLINE"
    ).strip().upper()

    if meeting_mode not in {"ONLINE", "OFFLINE", "HYBRID"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Meeting mode must be ONLINE, OFFLINE, or HYBRID.",
        )

    location = (
        payload.location.strip()
        if payload.location
        else (row.location.strip() if row.location else None)
    )
    meeting_url = payload.meeting_url.strip() if payload.meeting_url else None

    if meeting_mode in {"OFFLINE", "HYBRID"} and not location:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Physical or hybrid appointments require a location.",
        )

    if meeting_mode in {"ONLINE", "HYBRID"} and not meeting_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Online or hybrid appointments require a meeting URL.",
        )

    row.status = "APPROVED"
    row.approved_start_at = start_at
    row.approved_end_at = end_at
    row.meeting_mode = meeting_mode
    row.meeting_url = meeting_url
    row.location = location
    row.md_user_id = current_user.id
    row.decided_by_user_id = current_user.id
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = payload.note

    database.add(
        AppointmentAction(
            organization_id=current_user.organization_id,
            appointment_id=row.id,
            actor_user_id=current_user.id,
            action="APPROVED",
            note=payload.note,
            extra_data={
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "meeting_mode": meeting_mode,
                "meeting_url": meeting_url,
                "location": location,
            },
        )
    )

    recipient = requester_user(database, row)

    queue_user_notification(
        database,
        organization_id=current_user.organization_id,
        recipient_user_id=recipient.id,
        title="MD appointment approved",
        body=(
            f"Your appointment '{row.subject}' was approved for "
            f"{start_at:%d-%m-%Y %H:%M}."
        ),
        dedupe_key=f"appointment:{row.id}:approved",
        route=f"/module/appointments?appointment={row.id}",
        module="appointments",
        event="APPOINTMENT_APPROVED",
        entity_id=row.id,
        extra_payload={
            "meeting_mode": meeting_mode,
            "meeting_url": meeting_url,
            "location": location,
        },
    )

    database.commit()
    database.refresh(row)
    return appointment_dict(database, row)


@router.post("/{appointment_id}/reject", response_model=AppointmentResponse)
def reject_appointment(
    appointment_id: UUID,
    payload: ReasonRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    require_md(database, current_user)
    row = get_appointment(database, current_user, appointment_id)

    if row.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending appointments can be rejected.",
        )

    reason = payload.reason.strip()

    row.status = "REJECTED"
    row.md_user_id = current_user.id
    row.decided_by_user_id = current_user.id
    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = reason

    database.add(
        AppointmentAction(
            organization_id=current_user.organization_id,
            appointment_id=row.id,
            actor_user_id=current_user.id,
            action="REJECTED",
            note=reason,
        )
    )

    recipient = requester_user(database, row)

    queue_user_notification(
        database,
        organization_id=current_user.organization_id,
        recipient_user_id=recipient.id,
        title="MD appointment rejected",
        body=f"Your appointment '{row.subject}' was rejected. Reason: {reason}",
        dedupe_key=f"appointment:{row.id}:rejected",
        route=f"/module/appointments?appointment={row.id}",
        module="appointments",
        event="APPOINTMENT_REJECTED",
        entity_id=row.id,
    )

    database.commit()
    database.refresh(row)
    return appointment_dict(database, row)


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment(
    appointment_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    employee = get_employee_for_user(database, current_user)
    row = get_appointment(database, current_user, appointment_id)

    if row.requester_employee_id != employee.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This appointment belongs to another employee.",
        )

    if row.status not in {"PENDING", "APPROVED"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This appointment cannot be cancelled.",
        )

    previous_status = row.status
    row.status = "CANCELLED"

    database.add(
        AppointmentAction(
            organization_id=current_user.organization_id,
            appointment_id=row.id,
            actor_user_id=current_user.id,
            action="CANCELLED",
            note="Appointment cancelled by requester.",
            extra_data={"previous_status": previous_status},
        )
    )

    requester_label = current_user.employee_code
    if employee.full_name:
        requester_label += f" - {employee.full_name}"

    queue_role_notifications(
        database,
        organization_id=current_user.organization_id,
        role_codes=MD_ROLES,
        title="MD appointment cancelled",
        body=f"{requester_label} cancelled the appointment '{row.subject}'.",
        dedupe_prefix=f"appointment:{row.id}:cancelled",
        route=f"/module/appointments?appointment={row.id}",
        module="appointments",
        event="APPOINTMENT_CANCELLED",
        entity_id=row.id,
        exclude_user_ids={current_user.id},
    )

    database.commit()
    database.refresh(row)
    return appointment_dict(database, row)


@router.post("/{appointment_id}/complete", response_model=AppointmentResponse)
def complete_appointment(
    appointment_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    require_md(database, current_user)
    row = get_appointment(database, current_user, appointment_id)

    if row.status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only approved appointments can be completed.",
        )

    row.status = "COMPLETED"
    row.completed_at = datetime.now(timezone.utc)

    database.add(
        AppointmentAction(
            organization_id=current_user.organization_id,
            appointment_id=row.id,
            actor_user_id=current_user.id,
            action="COMPLETED",
            note="Appointment marked completed.",
        )
    )

    recipient = requester_user(database, row)

    queue_user_notification(
        database,
        organization_id=current_user.organization_id,
        recipient_user_id=recipient.id,
        title="MD appointment completed",
        body=f"Your appointment '{row.subject}' was marked completed.",
        dedupe_key=f"appointment:{row.id}:completed",
        route=f"/module/appointments?appointment={row.id}",
        module="appointments",
        event="APPOINTMENT_COMPLETED",
        entity_id=row.id,
    )

    database.commit()
    database.refresh(row)
    return appointment_dict(database, row)


@router.get(
    "/{appointment_id}/actions",
    response_model=list[AppointmentActionResponse],
)
def appointment_actions(
    appointment_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    row = get_appointment(database, current_user, appointment_id)
    ensure_access(database, current_user, row)

    return list(
        database.scalars(
            select(AppointmentAction)
            .where(AppointmentAction.appointment_id == appointment_id)
            .order_by(AppointmentAction.created_at)
        ).all()
    )
