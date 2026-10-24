import importlib.util,sys
from pathlib import Path
from types import SimpleNamespace as N
from datetime import datetime,timezone
import pytest
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('summary',root/'app/services/payroll_advance_summary.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
now=datetime(2026,10,24,tzinfo=timezone.utc)
def advance(amount=10000,recovered=3000,disbursed=now,reference='REF'):
    return N(id='id',currency='INR',requested_amount=amount,recovered_amount=recovered,disbursed_at=disbursed,disbursement_reference=reference)
def test_balance_and_no_double_deduction():
    s=m.summarize([advance()],2000,'INR',now)
    assert [s[k] for k in ['disbursed','previous','current','pending']]==[10000,3000,2000,5000]
    assert '2,000.00' in m.summary_html({m.KEY:s})
def test_undisbursed_excluded_and_zero():
    assert m.summarize([advance(disbursed=None)],0,'INR',now)['disbursed']==0
    assert m.summarize([],0,'INR',now)['pending']==0
def test_multiple_completed_and_held():
    s=m.summarize([advance(10000,10000),advance(2000,500)],0,'INR',now)
    assert s['disbursed']==12000 and s['pending']==1500
def test_rounding():
    assert m.summarize([advance(10.01,3.33)],3.33,'INR',now)['pending']==3.35
def test_invalid_balances_and_currency():
    with pytest.raises(ValueError):m.summarize([advance()],8000,'INR',now)
    with pytest.raises(ValueError):m.summarize([advance()],0,'USD',now)
def test_immutable_summary_escaping_and_legacy():
    a=advance(reference='<script>alert(1)</script>')
    s=m.summarize([a],2000,'INR',now);a.recovered_amount=9000
    html=m.summary_html({m.KEY:s})
    assert '5,000.00' in html and '<script>' not in html and '&lt;script&gt;' in html
    assert 'not captured' in m.summary_html({})
def test_snapshot_scoping_preserves_details():
    from sqlalchemy.dialects import postgresql
    from uuid import uuid4
    org,run,person,structure=uuid4(),uuid4(),uuid4(),uuid4()
    item=N(id=uuid4(),employee_id=person,salary_structure_id=structure,
           salary_advance_deduction=2000,calculation_details={'working_dates':['2026-09-01']})
    class DB:
        def __init__(self):self.statements=[];self.results=iter([[item],[advance()],[]])
        def scalars(self,q):
            self.statements.append(q)
            return N(all=lambda:next(self.results))
        def get(self,*args):return N(currency='INR')
    db=DB()
    m.snapshot_run(db,N(id=run,organization_id=org,finalized_at=now))
    assert item.calculation_details['working_dates']==['2026-09-01']
    assert item.calculation_details[m.KEY]['pending']==5000
    for q in db.statements:
        c=q.compile(dialect=postgresql.dialect())
        assert org in c.params.values()
    q=db.statements[1].compile(dialect=postgresql.dialect())
    assert person in q.params.values() and now in q.params.values()
    assert 'FOR UPDATE' in str(q) and 'disbursed_at IS NOT NULL' in str(q)
def test_hooks_run_before_recoveries_and_print_both():
    s=(root/'app/services/payroll_service.py').read_text()
    assert s.index('snapshot_run(database, payroll_run)') < s.index('    finalize_salary_advance_recoveries(')
    p=(root/'app/api/routes/payroll.py').read_text()
    assert 'render_payslip(item, payroll_run, structure, employee)' in p
    assert 'render_register(payroll_run, items, vendor_items' in p
