"""Read-only, tenant-scoped financial record exports. No payment operations."""
from datetime import datetime, timezone, date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import MetaData, Table, select, inspect, cast, Date, func
from fastapi import HTTPException
from app.models import Role, user_roles

# Only these business tables can ever be selected by a client category.
CATEGORIES = {
 'box-loading': ('Box loading', 'box_loading_requests', 'loading_date'),
 'rentals': ('Rental agreements / advances', 'shop_rentals', 'agreement_start_date'),
 'fuel': ('Fuel records', 'vehicle_fuel_indents', 'created_at'),
 'payroll': ('Payroll runs', 'payroll_runs', 'period_end'),
 'expenses': ('Expense claims', 'expense_claims', 'created_at'),
 'employee-advances': ('Employee salary advances', 'salary_advance_requests', 'requested_at'),
 'vendor-advances': ('Vendor salary advances', 'vendor_salary_advance_requests', 'requested_at'),
 'overtime': ('Overtime claims', 'overtime_claims', 'work_date'),
 'maintenance': ('Maintenance bills', 'maintenance_bills', 'bill_date'),
 'vendor-refunds': ('Vendor deposit refunds', 'vendor_deposit_refunds', 'refund_date'),
 'rental-refunds': ('Rental advance refunds', 'shop_rental_advance_refunds', 'refund_date'),
 'labour': ('External labour payments', 'external_labour_payments', 'created_at'),
 'approvals': ('Document approval requests', 'document_approval_requests', 'created_at'),
 'cashbook': ('Credit / debit records', 'cashbook_entries', 'transaction_date'),
 'salary-revisions': ('Employee salary revisions', 'salary_revisions', 'created_at'),
 'vendor-salaries': ('Vendor salary structures', 'vendor_salary_structures', 'effective_from'),
 'salary-holds': ('Salary holds', 'salary_holds', 'hold_from'),
 'employee-settlement': ('Employee settlements', 'workforce_catalogue_state', 'settled_on'),
 'vendor-settlement': ('Vendor settlements', 'workforce_catalogue_state', 'settled_on'),
}
CHILDREN = {
 'employee-advances': [('Payroll recoveries','salary_advance_recoveries','salary_advance_request_id')],
 'vendor-advances': [('Payroll recoveries','vendor_salary_advance_recoveries','vendor_salary_advance_request_id')],
 'box-loading': [('Approval / payment history','box_loading_actions','request_id')],
 'expenses': [('Expense items','expense_claim_items','claim_id'),('Approval / payment history','expense_claim_actions','claim_id')],
 'maintenance': [('Approval / payment history','maintenance_bill_actions','bill_id')],
 'labour': [('Approval / payment history','external_labour_payment_actions','payment_id')],
 'approvals': [('Approval history','document_approval_actions','approval_request_id')],
 'payroll': [('Employee payroll','payroll_items','payroll_run_id'),('Vendor payroll','vendor_payroll_items','payroll_run_id')],
}
# Generated from reviewed source model fields, rather than exporting arbitrary new columns.
import json
from pathlib import Path
FIELDS = json.loads(Path(__file__).with_name('financial_export_fields.json').read_text())
EXCLUDE = {'organization_id','client_request_id','creation_fingerprint','dedupe_key','extra_data','snapshot','evidence_urls','fingerprint','calculation_details'}

def access(db, user):
    if not user or not user.is_active or not user.organization.is_active:
        raise HTTPException(403, 'Active organisation account required.')
    roles = set(db.scalars(select(Role.code).join(user_roles, Role.id == user_roles.c.role_id).where(
        user_roles.c.user_id == user.id, Role.organization_id == user.organization_id, Role.is_active.is_(True))))
    if not roles.intersection({'ADMIN','MD'}):raise HTTPException(403,'Admin or MD access is required.')

def table(db, name):
    cache=db.info.setdefault('financial_export_tables',{})
    if name not in cache:
        connection=db.connection()
        cache[name]=Table(name,MetaData(),autoload_with=connection,resolve_fks=False) if inspect(connection).has_table(name) else None
    return cache[name]

def category(kind):
    if kind not in CATEGORIES:raise HTTPException(404,'Unknown financial record category.')
    return CATEGORIES[kind]

def scoped(db, org, kind):
    label,name,day=category(kind);t=table(db,name)
    if t is None:raise HTTPException(404,'This record category is not installed.')
    columns=[t.c[n] for n in FIELDS.get(name,[]) if n in t.c and n not in EXCLUDE]
    q=select(*columns).where(t.c.organization_id==org)
    key='id'
    if kind.endswith('-settlement'):
        q=q.where(t.c.kind==kind.split('-')[0],t.c.settled_on.is_not(None));key='person_id'
    return t,q,key,day

def record(db,org,kind,record_id):
    t,q,key,_=scoped(db,org,kind)
    row=db.execute(q.where(t.c[key]==record_id)).mappings().first()
    if row is None:raise HTTPException(404,'Record not found in your organisation.')
    return dict(row)

def listing(db,org,kind,start=None,end=None,offset=0):
    if start and end and start>end:raise HTTPException(422,'From date must be on or before To date.')
    t,q,key,day=scoped(db,org,kind)
    if start:q=q.where(cast(t.c[day],Date)>=start)
    if end:q=q.where(cast(t.c[day],Date)<=end)
    rows=list(db.execute(q.order_by(t.c[day].desc(),t.c[key]).offset(offset).limit(51)).mappings())
    result=[]
    for row in rows[:50]:
        person=resolve(db,org,'employee_id',row.get('employee_id')) or resolve(db,org,'vendor_id',row.get('vendor_id'))
        reference=row.get('claim_number') or row.get('invoice_number') or row.get('title') or row.get('vehicle_number') or row.get('building_name') or row.get('indent_number') or person or row.get('labour_name') or row.get('counterparty') or str(row[key])
        amount=next((row[x] for x in ['total_amount','total_net','amount','requested_amount','approved_amount','claimed_amount','new_gross','monthly_salary','monthly_rent_amount','actual_amount_rupees','requested_amount_rupees'] if row.get(x) is not None),None)
        result.append({'id':str(row[key]),'date':str(row.get(day) or '')[:10],'reference':str(reference),'status':saved_status(kind,row),'amount':amount,'currency':row.get('currency') or 'INR'})
    return {'items':result,'has_more':len(rows)>50,'date_field':day.replace('_',' ')}

def resolve(db,org,key,value):
    if value is None:return None
    target = 'users' if key.endswith('_user_id') or key in {'md_user_id','settled_by','archived_by','actor_id'} else 'employees' if key=='employee_id' else 'vendors' if key=='vendor_id' else None
    if target is None:return None
    t=table(db,target)
    if t is None:return None
    names=[x for x in ['employee_code','code','full_name','first_name','last_name','name'] if x in t.c]
    r=db.execute(select(*(t.c[x] for x in names)).where(t.c.id==value,t.c.organization_id==org)).first()
    return ' '.join(str(x) for x in r if x) if r else None

def saved_status(kind,row):
    if kind=='cashbook':return 'VOIDED' if row.get('voided_at') else 'RECORDED'
    if kind.endswith('-settlement'):return 'SETTLED'
    if kind=='salary-holds':return 'ACTIVE HOLD' if row.get('is_active') else 'RELEASED'
    return row.get('status') or 'RECORDED'

def formatted(value):
    if value is None:return 'Not recorded'
    if isinstance(value,datetime):return value.strftime('%d/%m/%Y %H:%M:%S %z')
    if isinstance(value,date):return value.strftime('%d/%m/%Y')
    if isinstance(value,bool):return 'Yes' if value else 'No'
    if isinstance(value,(Decimal,float)):return f'{value:,.2f}'
    return str(value)

def fields(db,org,row):
    output=[]
    for key,value in row.items():
        if key in EXCLUDE or value is None:continue
        label=key.replace('_',' ').capitalize()
        resolved=resolve(db,org,key,value)
        output.append((label,(resolved+' ['+str(value)+']') if resolved else formatted(value)))
    return output

def export_data(db,user,kind,record_id):
    row=record(db,user.organization_id,kind,record_id)
    sections=[('Record details',fields(db,user.organization_id,row))]
    for title,name,fk in CHILDREN.get(kind,[]):
        t=table(db,name)
        if t is None:continue
        columns=[t.c[x] for x in FIELDS.get(name,[]) if x in t.c and x not in EXCLUDE]
        if not columns or fk not in t.c:continue
        q=select(*columns).where(t.c.organization_id==user.organization_id,t.c[fk]==record_id)
        if 'created_at' in t.c:q=q.order_by(t.c.created_at,t.c.id)
        for index,child in enumerate(db.execute(q).mappings(),1):sections.append((f'{title} · {index}',fields(db,user.organization_id,child)))
    # Attachment identifiers and filenames are preserved; signed storage URLs are never exported.
    docs=table(db,'document_records')
    if docs is not None:
        for key,value in row.items():
            if key.endswith('document_id') and value:
                d=db.execute(select(docs.c.id,docs.c.title,docs.c.file_name).where(docs.c.id==value,docs.c.organization_id==user.organization_id)).mappings().first()
                if d:sections.append(('Supporting document',[(k.replace('_',' ').capitalize(),formatted(v)) for k,v in d.items()]))
    return {'title':CATEGORIES[kind][0],'organization':user.organization.name,'code':user.organization.code,'id':str(record_id),'status':saved_status(kind,row),'currency':row.get('currency') or 'INR','generated_at':datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S UTC'),'exported_by':user.employee_code,'sections':sections}

# date-display-ddmmyyyy-v1
