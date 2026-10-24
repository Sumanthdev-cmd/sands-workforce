"""Read-only calendar projection; never rewrites attendance or payroll."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models import Employee, User, AttendanceRecord, LeaveRequest, Holiday, Vendor, VendorClosureDay

def calendar_cell(day, today, records, leaves, joined=None, last=None, holiday=None, sunday_off=False):
    cell=dict(date=day.isoformat(),mark='—',tone='empty',status='NO_RECORD',reason='',records=records,leaves=leaves)
    present=any(r.get('check_in_at') or r.get('status') in {'PRESENT','LATE','HALF_DAY','REGULARIZED','CHECKED_OUT'} for r in records)
    if present:
        late=any((r.get('late_minutes') or 0)>0 or r.get('status')=='LATE' for r in records)
        half=any(r.get('status')=='HALF_DAY' for r in records)
        cell.update(mark='P',tone='late' if late else 'present',status='LATE' if late else ('HALF_DAY' if half else 'PRESENT'),reason='Half-day attendance recorded.' if half else '')
    elif joined and day<joined:cell.update(status='NOT_JOINED',reason='Before joining date.')
    elif last and day>last:cell.update(status='AFTER_SEPARATION',reason='After last working day.')
    elif day>today:cell.update(status='FUTURE',reason='Future date.')
    elif any(l['status']=='APPROVED' for l in leaves):
        cell.update(mark='A',tone='leave',status='ON_LEAVE',reason='Approved leave. See recorded reason below.')
    elif any(r.get('status') in {'ABSENT','ON_LEAVE'} for r in records):
        cell.update(mark='A',tone='absent',status=records[0]['status'],reason='No leave reason recorded.' if not leaves else 'See leave requests below.')
    elif holiday:cell.update(mark='OFF',tone='off',status='HOLIDAY',reason=holiday)
    elif sunday_off and day.weekday()==6:cell.update(mark='OFF',tone='off',status='WEEKLY_OFF',reason='Sunday weekly off.')
    elif day<today:
        cell.update(mark='A',tone='absent',status='NO_CHECK_IN',reason='No check-in recorded for this date. No approved leave recorded; absence is inferred for this display only.')
    else:cell.update(reason='No check-in recorded yet today.')
    return cell

def grid(db,user,start,end):
    if start>end or (end-start).days>92:raise HTTPException(400,'Select a valid date range of up to 93 days.')
    org=user.organization_id
    zone=user.organization.timezone or 'Asia/Kolkata'
    today=datetime.now(ZoneInfo(zone)).date()
    days=[start+timedelta(days=i) for i in range((end-start).days+1)]
    people=db.execute(select(Employee,User).join(User,User.id==Employee.user_id).where(Employee.organization_id==org,User.organization_id==org,Employee.date_of_joining<=end,text("NOT EXISTS (SELECT 1 FROM workforce_catalogue_state cs WHERE cs.organization_id=employees.organization_id AND cs.person_id=employees.id AND cs.kind='employee' AND cs.settled_on IS NOT NULL AND cs.archived_at IS NOT NULL)")).order_by(User.employee_code)).all()
    attendance=db.scalars(select(AttendanceRecord).where(AttendanceRecord.organization_id==org,AttendanceRecord.attendance_date.between(start,end))).all()
    indexed={}
    for r in attendance:
        indexed.setdefault((r.employee_id,r.attendance_date),[]).append({k:getattr(r,k) for k in ['status','check_in_at','check_out_at','worked_minutes','late_minutes']})
    leaves=db.scalars(select(LeaveRequest).where(LeaveRequest.organization_id==org,LeaveRequest.start_date<=end,LeaveRequest.end_date>=start)).all()
    by_leave={}
    for l in leaves:
        for d in days:
            if l.start_date<=d<=l.end_date:by_leave.setdefault((l.employee_id,d),[]).append(dict(status=l.status,reason=l.reason,start_date=l.start_date,end_date=l.end_date))
    holidays={h.holiday_date:h.name for h in db.scalars(select(Holiday).where(Holiday.organization_id==org,Holiday.is_active.is_(True),Holiday.is_optional.is_(False),Holiday.holiday_date.between(start,end)))}
    rows=[]
    for e,u in people:
        if e.last_working_day and e.last_working_day<start:continue
        if (not u.is_active or e.employment_status!='ACTIVE') and not e.last_working_day and not any(k[0]==e.id for k in indexed):continue
        rows.append(dict(id=str(e.id),name=e.full_name,code=u.employee_code,kind='Employee',cells=[calendar_cell(d,today,indexed.get((e.id,d),[]),by_leave.get((e.id,d),[]),e.date_of_joining,e.last_working_day,holidays.get(d),not e.is_field_employee) for d in days]))
    vendors=db.scalars(select(Vendor).where(Vendor.organization_id==org).order_by(Vendor.code)).all()
    records=db.execute(text("""SELECT a.vendor_id,a.attendance_date,a.status,a.check_in_at,a.check_out_at,
        a.worked_minutes,COALESCE(a.late_minutes,0) AS late_minutes,o.name AS outlet_name
        FROM vendor_attendance_records a LEFT JOIN outlets o ON o.id=a.outlet_id AND o.organization_id=a.organization_id
        WHERE a.organization_id=:org AND a.attendance_date BETWEEN :start AND :end"""),dict(org=org,start=start,end=end)).mappings().all()
    vi={}
    for r in records:vi.setdefault((r['vendor_id'],r['attendance_date']),[]).append({k:v for k,v in r.items() if k not in {'vendor_id','attendance_date'}})
    closures={c.closure_date:c.reason for c in db.scalars(select(VendorClosureDay).where(VendorClosureDay.organization_id==org,VendorClosureDay.is_active.is_(True),VendorClosureDay.closure_date.between(start,end)))}
    for v in vendors:
        if v.status!='ACTIVE' and not any(k[0]==v.id for k in vi):continue
        joined=v.created_at.astimezone(ZoneInfo(zone)).date() if v.created_at else None
        rows.append(dict(id='vendor-'+str(v.id),name=v.name,code=v.code,kind='Vendor',cells=[calendar_cell(d,today,vi.get((v.id,d),[]),[],joined=joined,holiday=closures.get(d)) for d in days]))
    return dict(dates=[d.isoformat() for d in days],rows=rows,timezone=zone,today=today.isoformat())

# attendance-notifications-cleanup-v1
