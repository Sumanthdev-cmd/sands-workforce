import sys,importlib.util
from pathlib import Path
from datetime import date,datetime,timezone
from types import SimpleNamespace as N
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
for name in ['payroll_advance_summary','payroll_print_layout']:
    spec=importlib.util.spec_from_file_location('app.services.'+name,root/'app/services'/ (name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
m=sys.modules['app.services.payroll_print_layout']
def run():
    return N(period_start=date(2026,9,1),period_end=date(2026,9,30),status='FINALIZED',approved_at=datetime(2026,10,2,5,tzinfo=timezone.utc),approval_note='<script>bad</script>',total_employees=1,total_vendors=0,total_gross=10000,total_deductions=2000,total_net=8000)
def person():
    return dict(employee_name='Asha <Rao>',employee_code='EMP101',bank_name='Bank A',bank_ifsc='TEST0000001',bank_account_number='000000000001',currency='INR',payslip_number='SAMPLE101',gross_earned=10000,net_salary=8000,working_days=26,payable_days=26,salary_advance_deduction=2000,calculation_details={m.KEY:dict(currency='INR',disbursed=10000,previous=3000,current=2000,pending=5000,advances=[])})
def test_register_and_two_column_summary():
    html=m.render_register(run(),[person()],[])
    assert 'Bank A' in html and '000000000001' in html and 'TEST0000001' in html
    assert 'Pending recovery after payroll' in html and '5,000.00' in html
    assert 'class="left"' in html and 'class="right"' in html
    assert 'size:A4 landscape' in html and 'print-color-adjust:exact' in html
def test_dates_escape_and_real_report():
    html=m.render_register(run(),[person()],[])
    assert '01/09/2026' in html and '10:30 AM IST' in html
    assert '<script>bad</script>' not in html and '&lt;script&gt;' in html
    assert 'Preview addition' not in html and 'NOT FOR PAYMENT' not in html
def test_vendor_and_hold_legacy():
    x=person();x.update(vendor_name='Vendor',vendor_code='VND1',outlet_names=['Shop'],is_held=True,hold_reason='<hold>',calculation_details={})
    html=m.render_register(run(),[],[x])
    assert 'Individual vendor payslip' in html and 'not captured' in html
    assert 'Salary held: &lt;hold&gt;' in html
def test_repeat_headers_and_all_rows():
    rows=[{**person(),'employee_code':f'EMP{i:03}'} for i in range(40)]
    html=m.render_register(run(),rows,[])
    assert all(f'EMP{i:03}' in html for i in range(40))
    assert 'thead{display:table-header-group}' in html
def test_integrations_preserve_permissions_and_decorators():
    s=(root/'app/api/routes/payroll.py').read_text()
    assert 'get_finalized_payroll_export(database, current_user, run_id)' in s
    assert 'get_printable_payslip(database, current_user, item_id)' in s
    assert '"/payslips/{item_id}/print"' in s and '"/runs/{run_id}/print"' in s
