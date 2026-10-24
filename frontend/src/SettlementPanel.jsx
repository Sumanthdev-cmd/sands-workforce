import DateField from "./DateField";
import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import "./FinancialRecordsWorkspace.css";
import FinancialDownload from "./FinancialDownload";
import {useEffect,useState} from "react";
import {apiRequest} from "./lib/api";
export default function SettlementPanel({kind,person,onClose,onChange}){
 const [info,setInfo]=useState(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 const [form,setForm]=useState({settled_on:new Date().toISOString().slice(0,10),reference:"",note:"",all_dues_paid:false});
 const path=`/catalogue/${kind}/${person.id}`;
 async function load(){try{setInfo(await apiRequest(`${path}/settlement`))}catch(e){setError(e.message)}}
 useEffect(()=>{load()},[path]);
 async function save(e){e.preventDefault();setBusy(true);setError("");try{await apiRequest(`${path}/settlement`,{method:"POST",body:form});await load();onChange()}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function remove(){if(!confirm(`Delete ${person.full_name||person.name} from the catalogue? Historical payroll, attendance and settlement records will remain.`))return;setBusy(true);try{const result=await apiRequest(path,{method:"DELETE"});onChange(result.message);onClose()}catch(e){setError(e.message)}finally{setBusy(false)}}
 return <section className="panel"><div className="panel-header"><h2>Final settlement · {person.full_name||person.name}</h2><button className="secondary-button" onClick={onClose}>Close</button></div><p>Record this only after all salary, allowance, reimbursement, advance and deposit dues have actually been settled. Recording settlement does not transfer money.</p>{error&&<div className="error-banner">{error}</div>}{!info?<p>Checking settlement…</p>:<><p>Last working day: {info.last_working_day||"Not recorded"}</p>{info.blockers.length>0?<div className="warning-banner"><ul>{info.blockers.map(x=><li key={x}>{x}</li>)}</ul></div>:info.settlement?.settled_on?<div className="success-banner">Settled on {formatDisplayDate(info.settlement.settled_on)} · {info.settlement.settlement_reference}</div>:<form className="document-form" onSubmit={save}><label>Settlement date<DateField required type="date" value={form.settled_on} onChange={e=>setForm({...form,settled_on:e.target.value})}/></label><label>Payment / settlement reference<input required minLength="3" maxLength="200" value={form.reference} onChange={e=>setForm({...form,reference:e.target.value})}/></label><label>Settlement details<textarea required minLength="5" maxLength="2000" value={form.note} onChange={e=>setForm({...form,note:e.target.value})}/></label><label className="settlement-confirmation"><input required type="checkbox" checked={form.all_dues_paid} onChange={e=>setForm({...form,all_dues_paid:e.target.checked})}/><span>All dues have been paid or recovered and the settlement is complete.</span></label><button className="primary-button" disabled={busy}>Record completed settlement</button></form>}{info.settlement?.settled_on&&<FinancialDownload kind={`${kind}-settlement`} recordId={person.id}/>}<button className="secondary-button danger" disabled={busy||!info.can_delete} onClick={remove}>Delete from catalogue</button><p className="muted">Deletion becomes available after completed settlement is recorded and no blocking items remain.</p></>}</section>
}

// financial-records-update-v1
// date-display-ddmmyyyy-v1
