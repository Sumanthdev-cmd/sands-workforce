"""Freeze advance balances in payroll JSON; never change salary arithmetic."""
from decimal import Decimal
from html import escape
from sqlalchemy import select
from app.models.payroll import (PayrollItem, VendorPayrollItem, SalaryAdvanceRequest,
    VendorSalaryAdvanceRequest, SalaryStructure, VendorSalaryStructure)

KEY = "salary_advance_summary_v1"

def money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))

def summarize(advances, current, currency, as_of):
    rows = []
    for a in advances:
        if not a.disbursed_at:
            continue
        if a.currency != currency:
            raise ValueError("Advance currency differs from payroll currency; review before approval.")
        rows.append({
            "reference": a.disbursement_reference or str(a.id),
            "disbursed_on": a.disbursed_at.strftime("%d/%m/%Y"),
            "amount": float(money(a.requested_amount)),
            "previously_recovered": float(money(a.recovered_amount)),
        })
    total = sum((money(r["amount"]) for r in rows), Decimal(0))
    previous = sum((money(r["previously_recovered"]) for r in rows), Decimal(0))
    current = money(current)
    if min(total, previous, current) < 0 or previous + current > total:
        raise ValueError("Advance balances changed; return and recalculate payroll before approval.")
    return dict(as_of=as_of.isoformat(), currency=currency, advances=rows,
                disbursed=float(total), previous=float(previous), current=float(current),
                pending=float(total-previous-current))

def snapshot_run(database, payroll_run):
    # Called before recovery posting, inside the existing approval transaction.
    for Item, Advance, Structure, person_key, structure_key in [
        (PayrollItem, SalaryAdvanceRequest, SalaryStructure, "employee_id", "salary_structure_id"),
        (VendorPayrollItem, VendorSalaryAdvanceRequest, VendorSalaryStructure, "vendor_id", "vendor_salary_structure_id"),
    ]:
        items = database.scalars(select(Item).where(
            Item.organization_id == payroll_run.organization_id,
            Item.payroll_run_id == payroll_run.id).order_by(Item.id)).all()
        for item in items:
            structure = database.get(Structure, getattr(item, structure_key))
            advances = database.scalars(select(Advance).where(
                Advance.organization_id == payroll_run.organization_id,
                getattr(Advance, person_key) == getattr(item, person_key),
                Advance.disbursed_at.is_not(None),
                Advance.disbursed_at <= payroll_run.finalized_at,
            ).order_by(Advance.id).with_for_update()).all()
            summary = summarize(advances, item.salary_advance_deduction,
                                structure.currency, payroll_run.finalized_at)
            item.calculation_details = {**(item.calculation_details or {}), KEY: summary}

def summary_html(details):
    data = (details or {}).get(KEY)
    if not data:
        return ('<section><h2>Salary Advance Summary</h2><p>Historical advance balance '
                'was not captured for this payroll. The recovery deducted in this payroll '
                'is shown in the salary breakdown. No historical balance is estimated.</p></section>')
    labels = [("Total advance disbursed", "disbursed"), ("Recovered before this payroll", "previous"),
              ("Recovered in this payroll", "current"), ("Pending recovery after this payroll", "pending")]
    rows = "".join("<tr><td>"+label+"</td><td>"+format(money(data[key]), ",.2f")+"</td></tr>" for label,key in labels)
    result = ('<section style="break-inside:avoid"><h2>Salary Advance Summary</h2>'
              '<p>Balance at payroll finalization. Currency: '+escape(data["currency"])+'</p>'
              '<table><tr><th>Advance details</th><th>Amount</th></tr>'+rows+'</table>'
              '<p>This payroll recovery is already included in deductions; it is not deducted again.</p>')
    if data["advances"]:
        result += '<table><tr><th>Disbursed on</th><th>Reference</th><th>Advance disbursed</th></tr>'
        for a in data["advances"]:
            result += '<tr><td>'+escape(a["disbursed_on"])+'</td><td>'+escape(a["reference"])+'</td><td>'+format(money(a["amount"]),",.2f")+'</td></tr>'
        result += '</table>'
    return result+'</section>'
