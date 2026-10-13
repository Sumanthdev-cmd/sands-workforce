from datetime import date, datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceEvent,
    AttendanceRecord,
    DutyExitRequest,
    Employee,
    EmployeeGeofenceAssignment,
    Geofence,
    LiveLocation,
    LunchBreak,
    User,
)
from app.services.device_service import get_employee_for_user


MAX_LOCATION_AGE_MINUTES = 15
AUTO_CHECKOUT_BUFFER_METERS = 50.0


def calculate_distance_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    earth_radius_meters = 6_371_000.0
    latitude_a_rad = radians(latitude_a)
    latitude_b_rad = radians(latitude_b)
    latitude_delta = radians(latitude_b - latitude_a)
    longitude_delta = radians(longitude_b - longitude_a)
    haversine_value = (
        sin(latitude_delta / 2) ** 2
        + cos(latitude_a_rad)
        * cos(latitude_b_rad)
        * sin(longitude_delta / 2) ** 2
    )
    return earth_radius_meters * 2 * asin(sqrt(haversine_value))


def get_latest_fresh_location(database: Session, *, employee: Employee) -> LiveLocation:
    location = database.scalar(
        select(LiveLocation).where(LiveLocation.employee_id == employee.id)
    )
    if location is None:
        raise HTTPException(
            status_code=400,
            detail="No GPS location is available. Push a location batch first.",
        )
    recorded_at = location.recorded_at
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - recorded_at > timedelta(minutes=MAX_LOCATION_AGE_MINUTES):
        raise HTTPException(
            status_code=400,
            detail="The latest GPS location is too old. Push a fresh location before attendance.",
        )
    return location


def get_local_context(user: User, recorded_at: datetime):
    zone = ZoneInfo(user.organization.timezone if user.organization else "Asia/Kolkata")
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    local_dt = recorded_at.astimezone(zone)
    return zone, local_dt, local_dt.date()


def get_active_assignment(
    database: Session,
    *,
    organization_id: UUID,
    employee_id: UUID,
    attendance_date: date,
):
    row = database.execute(
        select(EmployeeGeofenceAssignment, Geofence)
        .join(Geofence, EmployeeGeofenceAssignment.geofence_id == Geofence.id)
        .where(
            EmployeeGeofenceAssignment.organization_id == organization_id,
            EmployeeGeofenceAssignment.employee_id == employee_id,
            EmployeeGeofenceAssignment.is_active.is_(True),
            EmployeeGeofenceAssignment.is_primary.is_(True),
            EmployeeGeofenceAssignment.valid_from <= attendance_date,
            (
                EmployeeGeofenceAssignment.valid_to.is_(None)
                | (EmployeeGeofenceAssignment.valid_to >= attendance_date)
            ),
            Geofence.is_active.is_(True),
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=400,
            detail="No active primary geofence is assigned to this employee.",
        )
    return row[0], row[1]


def evaluate_location(location: LiveLocation, geofence: Geofence):
    distance = calculate_distance_meters(
        location.latitude,
        location.longitude,
        geofence.latitude,
        geofence.longitude,
    )
    return distance, distance <= geofence.radius_meters


def perform_check_in(database: Session, *, user: User, automatic: bool) -> AttendanceRecord:
    employee = get_employee_for_user(database, user)
    location = get_latest_fresh_location(database, employee=employee)
    zone, local_dt, attendance_date = get_local_context(user, location.recorded_at)
    assignment, geofence = get_active_assignment(
        database,
        organization_id=user.organization_id,
        employee_id=employee.id,
        attendance_date=attendance_date,
    )
    distance, inside = evaluate_location(location, geofence)
    if not inside:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Employee is outside the assigned geofence.",
                "distance_meters": round(distance, 2),
                "allowed_radius_meters": geofence.radius_meters,
            },
        )

    attendance = database.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.attendance_date == attendance_date,
        )
    )
    if attendance is not None and attendance.check_in_at is not None:
        raise HTTPException(status_code=409, detail="Attendance is already checked in.")

    expected_start = datetime.combine(
        attendance_date,
        assignment.shift_start_time,
        tzinfo=zone,
    ) + timedelta(minutes=assignment.grace_minutes)
    late_minutes = max(0, int((local_dt - expected_start).total_seconds() // 60))

    if attendance is None:
        attendance = AttendanceRecord(
            organization_id=user.organization_id,
            employee_id=employee.id,
            attendance_date=attendance_date,
        )
        database.add(attendance)
        database.flush()

    attendance.status = "LATE" if late_minutes > 0 else "PRESENT"
    attendance.check_in_at = location.recorded_at
    attendance.check_in_latitude = location.latitude
    attendance.check_in_longitude = location.longitude
    attendance.check_in_geofence_id = geofence.id
    attendance.late_minutes = late_minutes
    attendance.is_auto_check_in = automatic

    database.add(
        AttendanceEvent(
            organization_id=user.organization_id,
            attendance_record_id=attendance.id,
            employee_id=employee.id,
            geofence_id=geofence.id,
            event_type="CHECK_IN",
            latitude=location.latitude,
            longitude=location.longitude,
            distance_meters=distance,
            inside_geofence=True,
            recorded_at=location.recorded_at,
        )
    )
    database.flush()
    from app.services.security_overtime_service import process_late_attendance

    process_late_attendance(
        database,
        user=user,
        employee=employee,
        attendance=attendance,
    )
    database.commit()
    database.refresh(attendance)
    return attendance


def perform_check_out(database: Session, *, user: User, automatic: bool) -> AttendanceRecord:
    employee = get_employee_for_user(database, user)
    location = get_latest_fresh_location(database, employee=employee)
    _, _, attendance_date = get_local_context(user, location.recorded_at)
    _, geofence = get_active_assignment(
        database,
        organization_id=user.organization_id,
        employee_id=employee.id,
        attendance_date=attendance_date,
    )
    distance, inside = evaluate_location(location, geofence)

    attendance = database.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.attendance_date == attendance_date,
        )
    )
    if attendance is None or attendance.check_in_at is None:
        raise HTTPException(status_code=409, detail="Attendance has not been checked in.")
    if attendance.check_out_at is not None:
        raise HTTPException(status_code=409, detail="Attendance is already checked out.")

    active_duty_exit = database.scalar(
        select(DutyExitRequest.id).where(
            DutyExitRequest.attendance_record_id == attendance.id,
            DutyExitRequest.status == "OUTSIDE",
        )
    )
    if active_duty_exit is not None:
        raise HTTPException(
            status_code=409,
            detail="Record your return from the approved on-duty exit before checking out.",
        )

    active_lunch = database.scalar(
        select(LunchBreak.id).where(
            LunchBreak.attendance_record_id == attendance.id,
            LunchBreak.status == "ACTIVE",
        )
    )
    if active_lunch is not None:
        raise HTTPException(
            status_code=409,
            detail="End the active lunch break before checking out.",
        )

    attendance.check_out_at = location.recorded_at
    attendance.check_out_latitude = location.latitude
    attendance.check_out_longitude = location.longitude
    attendance.check_out_geofence_id = geofence.id
    attendance.is_auto_check_out = automatic
    attendance.worked_minutes = max(
        0,
        int((attendance.check_out_at - attendance.check_in_at).total_seconds() // 60),
    )

    database.add(
        AttendanceEvent(
            organization_id=user.organization_id,
            attendance_record_id=attendance.id,
            employee_id=employee.id,
            geofence_id=geofence.id,
            event_type="CHECK_OUT",
            latitude=location.latitude,
            longitude=location.longitude,
            distance_meters=distance,
            inside_geofence=inside,
            recorded_at=location.recorded_at,
        )
    )
    database.commit()
    database.refresh(attendance)
    return attendance


def evaluate_attendance(database: Session, *, user: User):
    employee = get_employee_for_user(database, user)
    location = get_latest_fresh_location(database, employee=employee)
    _, _, attendance_date = get_local_context(user, location.recorded_at)
    _, geofence = get_active_assignment(
        database,
        organization_id=user.organization_id,
        employee_id=employee.id,
        attendance_date=attendance_date,
    )
    distance, inside = evaluate_location(location, geofence)
    attendance = database.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.attendance_date == attendance_date,
        )
    )

    if inside and (attendance is None or attendance.check_in_at is None):
        attendance = perform_check_in(database, user=user, automatic=True)
        return "CHECKED_IN", "Automatic check-in completed.", True, distance, attendance

    if (
        distance > geofence.radius_meters + AUTO_CHECKOUT_BUFFER_METERS
        and attendance is not None
        and attendance.check_in_at is not None
        and attendance.check_out_at is None
    ):
        active_duty_exit = database.scalar(
            select(DutyExitRequest.id).where(
                DutyExitRequest.attendance_record_id == attendance.id,
                DutyExitRequest.status == "OUTSIDE",
            )
        )
        if active_duty_exit is not None:
            return (
                "DUTY_EXIT_ACTIVE",
                "Outside the geofence under an ADMIN-approved on-duty exit.",
                False,
                distance,
                attendance,
            )

        active_lunch = database.scalar(
            select(LunchBreak.id).where(
                LunchBreak.attendance_record_id == attendance.id,
                LunchBreak.status == "ACTIVE",
            )
        )
        if active_lunch is not None:
            return (
                "LUNCH_BREAK_ACTIVE",
                "Outside the geofence during the active paid lunch break.",
                False,
                distance,
                attendance,
            )

        attendance = perform_check_out(database, user=user, automatic=True)
        return "CHECKED_OUT", "Automatic check-out completed.", False, distance, attendance

    return "NO_ACTION", "No attendance state change was required.", inside, distance, attendance


def get_today_attendance(
    database: Session,
    *,
    user: User,
) -> AttendanceRecord | None:
    employee = get_employee_for_user(
        database,
        user,
    )

    local_today = datetime.now(
        ZoneInfo(
            user.organization.timezone
            if user.organization
            else "Asia/Kolkata"
        )
    ).date()

    attendance = database.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id
            == employee.id,
            AttendanceRecord.attendance_date
            == local_today,
        )
    )

    return attendance


def list_own_attendance(
    database: Session,
    *,
    user: User,
    start_date: date,
    end_date: date,
) -> list[AttendanceRecord]:
    employee = get_employee_for_user(database, user)
    return list(
        database.scalars(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.employee_id == employee.id,
                AttendanceRecord.attendance_date >= start_date,
                AttendanceRecord.attendance_date <= end_date,
            )
            .order_by(AttendanceRecord.attendance_date.desc())
        ).all()
    )


def list_organization_attendance(
    database: Session,
    *,
    organization_id: UUID,
    start_date: date,
    end_date: date,
    employee_id: UUID | None,
) -> list[dict]:
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The From date must be on or before the To date.",
        )

    attendance_in_range = and_(
        AttendanceRecord.employee_id == Employee.id,
        AttendanceRecord.organization_id == organization_id,
        AttendanceRecord.attendance_date >= start_date,
        AttendanceRecord.attendance_date <= end_date,
    )

    # Begin with the active employee roster. The outer join keeps employees
    # visible even when they have not generated an attendance record.
    statement = (
        select(Employee, User, AttendanceRecord)
        .join(User, Employee.user_id == User.id)
        .outerjoin(AttendanceRecord, attendance_in_range)
        .where(
            Employee.organization_id == organization_id,
            Employee.employment_status == "ACTIVE",
            User.is_active.is_(True),
        )
    )
    if employee_id is not None:
        statement = statement.where(Employee.id == employee_id)

    rows = database.execute(
        statement.order_by(User.employee_code, AttendanceRecord.attendance_date.desc())
    ).all()

    return [
        {
            "id": attendance.id if attendance is not None else None,
            "employee_id": employee.id,
            "employee_code": account.employee_code,
            "employee_name": employee.full_name,
            "attendance_date": (
                attendance.attendance_date if attendance is not None else end_date
            ),
            "status": attendance.status if attendance is not None else "NO_RECORD",
            "check_in_at": attendance.check_in_at if attendance is not None else None,
            "check_out_at": attendance.check_out_at if attendance is not None else None,
            "check_in_latitude": (
                attendance.check_in_latitude if attendance is not None else None
            ),
            "check_in_longitude": (
                attendance.check_in_longitude if attendance is not None else None
            ),
            "check_out_latitude": (
                attendance.check_out_latitude if attendance is not None else None
            ),
            "check_out_longitude": (
                attendance.check_out_longitude if attendance is not None else None
            ),
            "check_in_geofence_id": (
                attendance.check_in_geofence_id if attendance is not None else None
            ),
            "check_out_geofence_id": (
                attendance.check_out_geofence_id if attendance is not None else None
            ),
            "late_minutes": attendance.late_minutes if attendance is not None else 0,
            "worked_minutes": attendance.worked_minutes if attendance is not None else 0,
            "is_auto_check_in": (
                attendance.is_auto_check_in if attendance is not None else False
            ),
            "is_auto_check_out": (
                attendance.is_auto_check_out if attendance is not None else False
            ),
            "created_at": attendance.created_at if attendance is not None else None,
            "updated_at": attendance.updated_at if attendance is not None else None,
            "has_record": attendance is not None,
        }
        for employee, account, attendance in rows
    ]
