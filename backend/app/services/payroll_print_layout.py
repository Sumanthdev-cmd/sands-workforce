"""Landscape payroll print layouts matching the approved reference."""
from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
from app.services.payroll_advance_summary import KEY

def e(v): return escape(str(v if v is not None else "—"))
def amount(v): return f"{float(v or 0):,.2f}"
def day(v): return v.strftime("%d/%m/%Y") if v else "—"
def days(v): return f"{float(v or 0):g}"
def currency(v): return "₹" if v == "INR" else e(v)+" "
def table(headers, rows, widths=None):
    col = '<colgroup>'+''.join(f'<col style="width:{w/sum(widths)*100}%">' for w in widths)+'</colgroup>' if widths else ''
    return '<table>'+col+'<thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'

def font_css():
    from pathlib import Path
    from base64 import b64encode
    css = '@font-face{font-family:Payroll;font-style:normal;font-weight:normal;src:url(FONT_0) format("truetype");}@font-face{font-family:Payroll;font-style:normal;font-weight:bold;src:url(FONT_1) format("truetype");}'
    for i, name in enumerate(['DejaVuSans.ttf', 'DejaVuSans-Bold.ttf']):
        data = (Path(__file__).with_name('payroll_fonts') / name).read_bytes()
        css = css.replace('FONT_'+str(i), 'data:font/ttf;base64,'+b64encode(data).decode('ascii'))
    return css

CSS = font_css() + """
@page { size:A4 landscape; margin:9mm 12.7mm 14mm;
 @bottom-left {content:"SandS Workforce | Payroll | DD/MM/YYYY";font:8pt Payroll;color:#52647a}
 @bottom-right {content:counter(page) " / " counter(pages);font:8pt Payroll;color:#52647a}
}
*{box-sizing:border-box}body{font-family:Payroll,"DejaVu Sans",Arial,sans-serif;color:#142d4e;font-size:9pt;line-height:1.45;margin:0}
h1{font-size:23pt;line-height:1.2;margin:4pt 0 9pt}h2{font-size:13pt;line-height:1.35;margin:12pt 0 6pt}
p{margin:0 0 7pt}.small{font-size:8pt;color:#52647a}.eyebrow{font-size:8pt;color:#52647a;margin-bottom:7pt}
table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:8pt;line-height:1.4;margin:0 0 10pt}
th,td{text-align:left;vertical-align:top;padding:6pt 7pt;border-bottom:.4pt solid #d5dfec;overflow-wrap:anywhere}
th{background:#142d4e;color:white;font-weight:bold}tbody tr:nth-child(odd){background:#f2f6fc}
thead{display:table-header-group}tr{break-inside:avoid}h2,h3{break-after:avoid}
.sheet{break-before:page}.sheet:first-of-type{break-before:auto}
.columns{display:table;width:100%;table-layout:fixed;margin-top:14pt}.left{display:table-cell;width:60.4%;padding-right:18pt;vertical-align:top}.right{display:table-cell;width:39.6%;vertical-align:top}
.right h2:first-child{margin-top:0}.held{color:#b00020;font-weight:bold}.advance{break-inside:avoid}
.actions{margin:12px 0}.actions button{padding:10px 16px}strong,b{font-weight:bold}
@media screen{body{padding:24px;max-width:1150px;margin:auto;background:white}.sheet{margin-bottom:32px}.columns{min-width:700px}.scroll{overflow-x:auto}.register{min-width:900px}}
@media print{.actions{display:none}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""
def document(body, title):
    return '<!doctype html><html><head><meta charset="utf-8"><title>'+e(title)+'</title><style>'+CSS+'</style></head><body><div class="actions"><button onclick="window.print()">Print / Save as PDF</button></div>'+body+'</body></html>'

def advance_block(details, curr):
    s=(details or {}).get(KEY)
    if not s:
        return '<h2>Salary Advance Summary</h2><p class="small">Historical advance balance was not captured for this payroll. The payroll recovery is shown in deductions; no balance is estimated.</p>'
    rows=[[label,amount(s[k])] for label,k in [
        ('Total advance disbursed','disbursed'),('Recovered before this payroll','previous'),
        ('Recovered in this payroll','current'),('<b>Pending recovery after payroll</b>','pending')]]
    rows[-1][1]='<b>'+rows[-1][1]+'</b>'
    sign=currency(curr)
    return '<div class="advance"><h2>Salary Advance Summary</h2>'+table(['Advance details','Amount ('+e(curr)+')'],rows,[63,37])+(
        '<p class="small">'+sign+amount(s['disbursed'])+' - '+sign+amount(s['previous'])+' - '+sign+amount(s['current'])+' = <b>'+sign+amount(s['pending'])+' remaining</b></p>'
        '<p class="small">Only disbursed advances count. This payroll recovery is already included in deductions on the left; it is not deducted again.</p>'
        '<p class="small">Balances recorded at payroll finalization.</p></div>')

def slip_section(item,run,name,curr,kind='employee'):
    v=lambda k:item.get(k,0)
    sign=currency(curr)
    earn=[['Basic earned',amount(v('basic_earned'))],['HRA earned',amount(v('hra_earned'))],
          ['Conveyance',amount(v('conveyance_earned'))],['Other allowance',amount(v('other_allowance_earned'))],
          ['Daily allowance ('+days(v('payable_days'))+' payable days)',amount(v('daily_allowance_earned'))]]
    if kind=='employee':earn.append(['Approved overtime benefit',amount(v('overtime_benefit'))])
    earn += [['Late-attendance half-day deduction','-'+amount(v('other_deductions'))],
             ['Salary advance recovery','-'+amount(v('salary_advance_deduction'))],
             ['Fixed deduction','-'+amount(v('fixed_deduction'))],
             ['<b>Net salary</b>','<b>'+sign+amount(v('net_salary'))+'</b>']]
    deductions=sum(float(v(k) or 0) for k in ['fixed_deduction','other_deductions','salary_advance_deduction'])
    held='<p class="held">Salary held: '+e(item.get('hold_reason') or 'Held')+'</p>' if item.get('is_held') else ''
    return '<section class="sheet"><p class="eyebrow">PAYROLL / '+e(str(run.status))+'</p><h1>Individual '+kind+' payslip</h1><p>'+kind.title()+': <b>'+e(name)+'</b> &nbsp; | &nbsp; Payslip: '+e(item.get('payslip_number'))+'</p><p>Period: <b>'+day(run.period_start)+' - '+day(run.period_end)+'</b> &nbsp; | &nbsp; Currency: '+e(curr)+'</p>'+held+'<div class="scroll"><div class="columns"><div class="left">'+table(['Description','Amount ('+e(curr)+')'],earn,[73,27])+'</div><div class="right"><h2>Attendance totals</h2><p>Working days: <b>'+days(v('working_days'))+'</b> | Payable: <b>'+days(v('payable_days'))+'</b> | Absent: <b>'+days(v('absent_days'))+'</b></p>'+advance_block(item.get('calculation_details'),curr)+'<p>Total earnings: '+sign+amount(v('gross_earned'))+'<br>Total deductions: '+sign+amount(deductions)+'<br><b>Net salary: '+sign+amount(v('net_salary'))+'</b></p><p class="small">Employee bank details appear in the combined payroll register.</p></div></div></div></section>'

def render_payslip(item,run,structure,employee):
    row={c.name:getattr(item,c.name) for c in item.__table__.columns}
    return document(slip_section(row,run,employee.full_name,structure.currency),'Payslip '+item.payslip_number)

def render_register(run,items,vendors,timezone='Asia/Kolkata'):
    currencies=sorted({str(x.get('currency') or 'INR') for x in [*items,*vendors]})
    curr=currencies[0] if len(currencies)==1 else 'INR' if not currencies else 'Mixed currencies'
    sign=currency(curr) if len(currencies)<=1 else ''
    approved=run.approved_at
    if approved:
        if approved.tzinfo is None:
            from datetime import timezone as tz
            approved=approved.replace(tzinfo=tz.utc)
        approved=approved.astimezone(ZoneInfo(timezone)).strftime('%d/%m/%Y, %I:%M %p %Z')
    summary=table(['Employees','Vendors','Combined gross','Deductions','Net payable'],[[str(run.total_employees),str(run.total_vendors),sign+amount(run.total_gross),sign+amount(run.total_deductions),sign+amount(run.total_net)]],[13,12,23,23,29])
    rows=[]
    for x in items:
        identity=e(x.get('employee_code'))+'<br><b>'+e(x.get('employee_name'))+'</b><br>Bank: '+e(x.get('bank_name') or '—')+'<br>IFSC: '+e(x.get('bank_ifsc') or '—')+'<br>A/C: '+e(x.get('bank_account_number') or '—')
        ded=sum(float(x.get(k) or 0) for k in ['fixed_deduction','other_deductions','salary_advance_deduction'])
        rows.append([identity,*[days(x.get(k)) for k in ['working_days','payable_days','absent_days']],*[amount(x.get(k)) for k in ['gross_earned','daily_allowance_earned','overtime_benefit']],amount(ded),amount(x.get('net_salary')),'HELD' if x.get('is_held') else 'PAYABLE'])
    vrows=[]
    for x in vendors:
        ded=sum(float(x.get(k) or 0) for k in ['fixed_deduction','other_deductions','salary_advance_deduction'])
        vrows.append([e(x.get('vendor_code'))+'<br><b>'+e(x.get('vendor_name'))+'</b>',e(', '.join(x.get('outlet_names') or [])),*[days(x.get(k)) for k in ['working_days','payable_days','absent_days']],amount(x.get('gross_earned')),amount(x.get('daily_allowance_earned')),amount(ded),amount(x.get('net_salary'))])
    body='<section class="sheet"><p class="eyebrow">PAYROLL / APPROVED REGISTER</p><h1>Finalized payroll</h1><p>Period: <b>'+day(run.period_start)+' - '+day(run.period_end)+'</b> &nbsp; | &nbsp; Currency: '+e(curr)+' &nbsp; | &nbsp; Status: FINALIZED</p><p class="small">Approved: '+e(approved)+' &nbsp; | &nbsp; MD approval note: '+e(run.approval_note or '—')+'</p><div class="scroll"><div class="register">'+summary+'<h2>Employee payroll</h2>'+table(['Employee / bank details','Working','Payable','Absent','Gross','Daily allowance','OT','Deductions','Net','Payment'],rows,[19,7.5,7,6.5,10,10,8.5,10,11,10.5])+'<h2>Vendor payroll</h2><p class="small">Vendors work all days, including Sundays, except recorded government closures.</p>'+table(['Vendor','Shop / outlet','Working','Payable','Absent','Gross','Daily allowance','Deductions','Net'],vrows,[14,17,7.5,7,6.5,12,12,12,12])+'</div></div><p class="small"><b>Reading this report:</b> Gross already includes daily allowance and OT where applicable; do not add those columns again. PAYABLE means eligible for payment, not confirmation that money was transferred.</p></section>'
    for x in items:body+=slip_section(x,run,x.get('employee_name'),x.get('currency') or 'INR')
    for x in vendors:body+=slip_section(x,run,x.get('vendor_name'),x.get('currency') or 'INR','vendor')
    return document(body,'Finalized payroll '+day(run.period_start)+' - '+day(run.period_end))
