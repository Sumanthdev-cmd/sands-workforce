"""Current work-session locations, shared by browser and Android maps."""
from datetime import datetime, timezone
from math import isfinite
from sqlalchemy import text
from app.services.mobile_tracking_policy import session_state, utc


def visible_point(row, now):
    row = dict(row)
    state = session_state(row, now)
    stamp = utc(row.get("recorded_at"))
    start = utc(row.get("check_in_at"))
    row["active"] = state["active"]
    row["requires_review"] = state["requires_review"]
    row["location_status"] = "OFF_DUTY"
    valid = False
    if state["active"]:
        row["location_status"] = "NO_SIGNAL"
        if stamp and start and stamp >= start:
            age = (utc(now) - stamp).total_seconds()
            lat, lon, accuracy = row.get("latitude"), row.get("longitude"), row.get("accuracy_meters")
            coordinates = lat is not None and lon is not None and isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
            if age < -30:
                row["location_status"] = "CLOCK_ERROR"
            elif age > 300:
                row["location_status"] = "STALE"
            elif not coordinates:
                row["location_status"] = "NO_SIGNAL"
            elif accuracy is None or not isfinite(accuracy) or accuracy > 100:
                row["location_status"] = "LOW_ACCURACY"
            else:
                row["location_status"] = "LIVE"
                valid = True
    if state["requires_review"]:
        row["location_status"] = "SHIFT_REVIEW"
    # Never let older native clients plot an off-duty, stale or unreliable point.
    if not valid:
        row["latitude"] = row["longitude"] = None
    return row


def team_locations(database, organization_id):
    employees = database.execute(text("""
        SELECT e.id AS person_id, u.employee_code AS code,
               concat_ws(' ', e.first_name, e.last_name) AS name, 'Employee' AS kind,
               l.id, l.device_id, l.latitude, l.longitude, l.accuracy_meters,
               l.speed_mps, l.battery_percentage, l.recorded_at, l.updated_at,
               e.is_field_employee, a.check_in_at, a.check_out_at
        FROM employees e JOIN users u ON u.id=e.user_id AND u.organization_id=e.organization_id
        LEFT JOIN LATERAL (SELECT check_in_at, check_out_at FROM attendance_records
            WHERE employee_id=e.id AND organization_id=e.organization_id
            ORDER BY attendance_date DESC, check_in_at DESC NULLS LAST LIMIT 1) a ON TRUE
        LEFT JOIN LATERAL (SELECT id, device_id, latitude, longitude, accuracy_meters,
            speed_mps, battery_percentage, recorded_at, created_at AS updated_at
            FROM location_history WHERE employee_id=e.id AND organization_id=e.organization_id
            AND recorded_at >= a.check_in_at AND recorded_at <= now() + interval '30 seconds'
            ORDER BY recorded_at DESC LIMIT 1) l ON TRUE
        WHERE e.organization_id=:org AND u.is_active=true AND e.employment_status='ACTIVE'
        AND NOT EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id
                        WHERE ur.user_id=u.id AND r.code='MD')
        ORDER BY u.employee_code
    """), {"org": organization_id}).mappings().all()
    vendors = database.execute(text("""
        SELECT v.id AS person_id, v.code, v.name, 'Vendor' AS kind,
               l.latitude, l.longitude, l.accuracy_meters, l.recorded_at,
               a.check_in_at, a.check_out_at
        FROM vendors v
        LEFT JOIN LATERAL (SELECT id, check_in_at, check_out_at FROM vendor_attendance_records
            WHERE vendor_id=v.id AND organization_id=v.organization_id
            ORDER BY attendance_date DESC, check_in_at DESC NULLS LAST LIMIT 1) a ON TRUE
        LEFT JOIN LATERAL (SELECT latitude, longitude, accuracy_meters, recorded_at
            FROM mobile_vendor_locations WHERE vendor_id=v.id AND organization_id=v.organization_id
            AND attendance_id=a.id AND recorded_at >= a.check_in_at
            AND recorded_at <= now() + interval '30 seconds'
            ORDER BY recorded_at DESC LIMIT 1) l ON TRUE
        WHERE v.organization_id=:org AND v.status='ACTIVE'
        AND NOT EXISTS (SELECT 1 FROM vendor_portal_accounts va WHERE va.vendor_id=v.id AND va.organization_id=v.organization_id AND va.status<>'ACTIVE') ORDER BY v.code
    """), {"org": organization_id}).mappings().all()
    now = datetime.now(timezone.utc)
    return [visible_point(r, now) for r in [*employees, *vendors]]
