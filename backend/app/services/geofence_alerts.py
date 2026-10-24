"""Emit one alert for each confidently observed unapproved on-duty exit."""
from datetime import datetime,timezone,timedelta
from math import isfinite
from sqlalchemy import select,text
from app.models import AttendanceRecord,DutyExitRequest,EmployeeGeofenceAssignment,Geofence,User,Role,user_roles
from app.services.attendance_service import calculate_distance_meters
from app.services.notification_service import queue_user_notification

def utc(t):
    return t.replace(tzinfo=timezone.utc) if t and t.tzinfo is None else t

def position_state(lat,lon,accuracy,fence):
    if accuracy is None or not all(isfinite(x) for x in [lat,lon,accuracy]) or not 0<=accuracy<=100:return None
    distance=calculate_distance_meters(lat,lon,fence.latitude,fence.longitude)
    if distance-accuracy>fence.radius_meters:return True
    if distance+accuracy<=fence.radius_meters:return False
    return None

def check_exit(db,user,employee,point,stamp,now=None):
    now=now or datetime.now(timezone.utc);stamp=utc(stamp)
    if not -30<=(now-stamp).total_seconds()<=300:return
    attendance=db.scalar(select(AttendanceRecord).where(AttendanceRecord.organization_id==user.organization_id,AttendanceRecord.employee_id==employee.id,AttendanceRecord.check_in_at.is_not(None),AttendanceRecord.check_out_at.is_(None)).order_by(AttendanceRecord.check_in_at.desc()).limit(1).with_for_update())
    if not attendance or stamp<utc(attendance.check_in_at) or now-utc(attendance.check_in_at)>timedelta(hours=24):return
    fence=db.scalar(select(Geofence).join(EmployeeGeofenceAssignment,EmployeeGeofenceAssignment.geofence_id==Geofence.id).where(
        Geofence.organization_id==user.organization_id,Geofence.is_active.is_(True),
        EmployeeGeofenceAssignment.organization_id==user.organization_id,
        EmployeeGeofenceAssignment.employee_id==employee.id,EmployeeGeofenceAssignment.is_active.is_(True),
        EmployeeGeofenceAssignment.is_primary.is_(True),
        EmployeeGeofenceAssignment.valid_from<=attendance.attendance_date,
        (EmployeeGeofenceAssignment.valid_to.is_(None)|(EmployeeGeofenceAssignment.valid_to>=attendance.attendance_date))
    ).order_by(EmployeeGeofenceAssignment.valid_from.desc()).limit(1))
    if not fence:return
    outside=position_state(point.latitude,point.longitude,point.accuracy_meters,fence)
    if outside is None:return
    params=dict(id=attendance.id,org=user.organization_id,stamp=stamp)
    state=db.execute(text('SELECT * FROM geofence_alert_state WHERE attendance_id=:id'),params).mappings().first()
    if state and stamp<=utc(state['last_recorded_at']):return
    approved=db.scalar(select(DutyExitRequest.id).where(
        DutyExitRequest.organization_id==user.organization_id,DutyExitRequest.attendance_record_id==attendance.id,
        DutyExitRequest.status.in_(['APPROVED','OUTSIDE']),DutyExitRequest.decided_at<=stamp))
    unauthorized=outside and not approved
    episode=state['episode'] if state else 0
    should_alert=unauthorized and not (state and state['outside'])
    if should_alert:episode+=1
    params.update(outside=bool(unauthorized),episode=episode)
    db.execute(text("""INSERT INTO geofence_alert_state(attendance_id,organization_id,last_recorded_at,outside,episode)
        VALUES (:id,:org,:stamp,:outside,:episode) ON CONFLICT(attendance_id) DO UPDATE SET
        last_recorded_at=EXCLUDED.last_recorded_at,outside=EXCLUDED.outside,episode=EXCLUDED.episode"""),params)
    if not should_alert:return
    recipients=db.scalars(select(User.id).join(user_roles,User.id==user_roles.c.user_id).join(Role,Role.id==user_roles.c.role_id).where(User.organization_id==user.organization_id,User.is_active.is_(True),Role.organization_id==user.organization_id,Role.is_active.is_(True),Role.code.in_(['ADMIN','GM','MD'])).distinct()).all()
    for recipient in recipients:
        queue_user_notification(db,organization_id=user.organization_id,recipient_user_id=recipient,
            title='Unapproved on-duty geofence exit',
            body=f'{user.employee_code} — {employee.full_name} was detected outside {fence.name} without approved duty exit permission.',
            dedupe_key=f'geofence-exit:{attendance.id}:{episode}:{recipient}',
            route='/module/attendance',module='attendance',event='UNAPPROVED_GEOFENCE_EXIT',entity_id=attendance.id,
            extra_payload=dict(employee_id=str(employee.id),observed_at=stamp.isoformat(),geofence_name=fence.name))
