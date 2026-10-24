"""Read-only code previews; allocation is serialized with employee creation."""
import json,re
from datetime import datetime,timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select,text,func
from fastapi import HTTPException
from app.models import Organization,User,Role,Employee

PREFIXES=[('MD','MD'),('ADMIN','ADMIN'),('GM','GM'),('MANAGER','MGR'),('ACCOUNTS_MANAGER','ACCMGR'),('ACCOUNTS_SECRETARY','ACCSEC'),('CASHIER','CASH'),('HR_RECRUITER','HR'),('FIELD_VISITOR','FV'),('OFFICE_EMPLOYEE','OFF'),('EMPLOYEE','EMP')]
def prefix_for(roles):
    return next((prefix for role,prefix in PREFIXES if role in roles),'EMP')

def validate_joining(db,org,day):
    zone=db.scalar(select(Organization.timezone).where(Organization.id==org)) or 'Asia/Kolkata'
    if day and day>datetime.now(ZoneInfo(zone)).date():raise HTTPException(422,'Joining date must be today or an earlier date.')

def reserve(db,org,roles,commit=True):
    # Compatibility endpoint name: previews never reserve, insert or commit.
    active=set(db.scalars(select(Role.code).where(Role.organization_id==org,Role.is_active.is_(True),Role.code.in_(roles))))
    if not roles or active!=set(roles):raise HTTPException(422,'Choose valid active employee roles.')
    prefix=prefix_for(roles)
    codes=list(db.scalars(select(User.employee_code).where(User.organization_id==org)))
    suffixes=[int(c[len(prefix):]) for c in codes if re.fullmatch(re.escape(prefix)+r'\d+',c,flags=re.I)]
    code=prefix+str(max(suffixes,default=0)+1).zfill(3)
    return dict(reservation_id=None,employee_code=code,prefix=prefix,preview=True)

def manual_code(value):
    code=value.strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_-]{1,49}',code) or '-OLD-' in code or code.startswith('ARCH_'):
        raise HTTPException(422,'Use 2–50 characters: start with a letter, then letters, numbers, hyphens or underscores. Archive codes cannot be used.')
    return code

def reusable(owner,employee,state):
    return bool(not owner.is_active and employee is not None and
        employee.separation_type in {'RESIGNED','REMOVED'} and
        state.get('settled_on') and state.get('archived_at'))

def assign_new_code(db,org,payload,actor_id=None):
    db.execute(select(Organization.id).where(Organization.id==org).with_for_update())
    result=reserve(db,org,payload.role_codes,commit=False)
    payload.code_reservation_id=None
    if getattr(payload,'employee_code_mode','AUTO')=='AUTO':
        payload.employee_code=result['employee_code']
        return payload.employee_code
    code=manual_code(payload.employee_code)
    owners=list(db.scalars(select(User).where(User.organization_id==org,func.upper(User.employee_code)==code).with_for_update()))
    if len(owners)>1:raise HTTPException(409,'This code has conflicting historical accounts. Choose a different code.')
    if owners:
        owner=owners[0]
        employee=db.scalar(select(Employee).where(Employee.organization_id==org,Employee.user_id==owner.id).with_for_update())
        state={}
        if employee:
            state=db.execute(text("SELECT * FROM workforce_catalogue_state WHERE organization_id=:org AND person_id=:id AND kind='employee' FOR UPDATE"),dict(org=org,id=employee.id)).mappings().first() or {}
        if not reusable(owner,employee,state):
            raise HTTPException(409,'Employee code is already in use. Reuse requires the former employee to be resigned/removed, disabled, fully settled and deleted from the catalogue.')
        from app.services.catalogue_service import settlement_blockers
        blockers,_,_=settlement_blockers(db,org,employee.id,'employee')
        if blockers:raise HTTPException(409,'Code cannot be reused: '+' '.join(blockers))
        if actor_id is None:raise HTTPException(403,'An authenticated employee creator is required for code reuse.')
        retired=code[:10]+'-OLD-'+owner.id.hex
        # Preserve permanent user/employee IDs and every foreign-key relationship.
        # The archived account is disabled and cannot be re-enabled through the catalogue.
        owner.employee_code=retired
        db.flush()
        db.info['employee_code_reuse']=dict(org=org,old_user=owner.id,old_employee=employee.id,code=code,retired=retired,actor=actor_id)
    payload.employee_code=code
    return code

def finish_code_reuse(db,org,new_user):
    pending=db.info.pop('employee_code_reuse',None)
    if not pending:return
    if pending['org']!=org or pending['code']!=new_user.employee_code:
        raise HTTPException(409,'Code reuse context changed. Retry employee creation.')
    db.execute(text("INSERT INTO employee_code_reuse_history(id,organization_id,original_code,retired_code,previous_user_id,previous_employee_id,new_user_id,changed_by_user_id) VALUES (:id,:org,:code,:retired,:old_user,:old_employee,:new_user,:actor)"),dict(pending,id=uuid4(),new_user=new_user.id))
