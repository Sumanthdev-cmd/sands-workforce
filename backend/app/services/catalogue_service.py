"""Settlement-backed catalogue removal; financial and attendance history is retained."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import json
from fastapi import HTTPException
from sqlalchemy import text


def organization_date(db, org):
    zone = db.scalar(text("SELECT timezone FROM organizations WHERE id=:org"), {"org":org}) or "Asia/Kolkata"
    return datetime.now(ZoneInfo(zone)).date()


def audit(db, user, kind, person, action, details):
    db.execute(text("INSERT INTO workforce_catalogue_events (organization_id,kind,person_id,action,actor_id,details) VALUES (:org,:kind,:id,:action,:actor,CAST(:details AS jsonb))"), dict(org=user.organization_id,kind=kind,id=person,action=action,actor=user.id,details=json.dumps(details,default=str)))


def catalogue_visible(table, kind):
    # Arguments are source constants only.
    return text(f"NOT EXISTS (SELECT 1 FROM workforce_catalogue_state cs WHERE cs.organization_id={table}.organization_id AND cs.person_id={table}.id AND cs.kind='{kind}' AND cs.archived_at IS NOT NULL)")


def ensure_not_archived(db, org, person, kind):
    archived = db.scalar(text("SELECT archived_at FROM workforce_catalogue_state WHERE organization_id=:org AND person_id=:id AND kind=:kind"), dict(org=org,id=person,kind=kind))
    if archived:
        raise HTTPException(409, "This person was removed after settlement. Their historical records have been retained.")


def load_person(db, org, person, kind):
    if kind == "employee":
        sql = "SELECT e.id, u.is_active AS active, e.last_working_day FROM employees e JOIN users u ON u.id=e.user_id AND u.organization_id=e.organization_id WHERE e.organization_id=:org AND e.id=:id FOR UPDATE OF e"
    else:
        sql = "SELECT id, status='ACTIVE' AS active, deposit_amount FROM vendors WHERE organization_id=:org AND id=:id FOR UPDATE"
    row = db.execute(text(sql),dict(org=org,id=person)).mappings().first()
    if not row:
        raise HTTPException(404, "Person was not found in this organisation.")
    return row


def settlement_blockers(db, org, person, kind):
    row = load_person(db, org, person, kind)
    reasons = []
    if row["active"]:
        reasons.append("Disable the person and record their last working day first.")
    state = db.execute(text("SELECT * FROM workforce_catalogue_state WHERE organization_id=:org AND kind=:kind AND person_id=:id"),dict(org=org,id=person,kind=kind)).mappings().first()
    last = row.get("last_working_day") if kind == "employee" else (state or {}).get("last_working_day")
    if not last:
        reasons.append("Record the last working day before settlement.")
    elif last > organization_date(db, org):
        reasons.append("The last working day has not passed yet.")
    prefix = "" if kind == "employee" else "vendor_"
    owner = "employee_id" if kind == "employee" else "vendor_id"
    params = dict(org=org,id=person)
    advance = db.scalar(text(f"SELECT count(*) FROM {prefix}salary_advance_requests WHERE organization_id=:org AND {owner}=:id AND (status IN ('PENDING','APPROVED') OR (status IN ('DISBURSED','RECOVERING') AND requested_amount>coalesce(recovered_amount,0)+0.005))"),params)
    if advance:
        reasons.append("Salary advances are pending or have an unrecovered balance.")
    pending = db.scalar(text(f"SELECT count(*) FROM {prefix}payroll_items p JOIN payroll_runs r ON r.id=p.payroll_run_id AND r.organization_id=p.organization_id WHERE p.organization_id=:org AND p.{owner}=:id AND r.status<>'FINALIZED'"),params)
    if pending:
        reasons.append("This person is included in an unfinished payroll run. Complete or recalculate that run first.")
    if kind == "vendor":
        refunds = db.execute(text("SELECT coalesce(sum(amount) FILTER (WHERE status='APPROVED'),0) AS returned, count(*) FILTER (WHERE status='PENDING_MD') AS pending FROM vendor_deposit_refunds WHERE organization_id=:org AND vendor_id=:id"),params).mappings().one()
        if refunds["pending"] or float(refunds["returned"]) + .005 < float(row["deposit_amount"] or 0):
            reasons.append("Complete the deposit return and its MD approval first.")
    else:
        holds = db.scalar(text("SELECT count(*) FROM salary_holds WHERE organization_id=:org AND employee_id=:id AND is_active=true"),params)
        if holds:
            reasons.append("Release active salary holds before final settlement.")
        overtime = db.scalar(text("SELECT count(*) FROM overtime_claims WHERE organization_id=:org AND employee_id=:id AND status NOT IN ('REJECTED','PAID')"),params)
        if overtime:
            reasons.append("Overtime claims have not been settled.")
        pending_expenses = db.scalar(text("SELECT count(*) FROM expense_claims WHERE organization_id=:org AND employee_id=:id AND status NOT IN ('PAID','REJECTED','CANCELLED')"), params)
        if pending_expenses:
            reasons.append("There are unsettled expense claims.")
    return reasons, dict(state) if state else {}, last
