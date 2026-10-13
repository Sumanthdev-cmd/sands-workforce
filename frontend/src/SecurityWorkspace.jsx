import {useEffect,useMemo,useState} from "react";

import {useAuth} from "./context/AuthContext";
import {apiRequest} from "./lib/api";


const readableError=(error)=>{
  const detail=error?.data?.detail??error?.message??error;
  if(Array.isArray(detail))return detail.map(item=>item?.msg||"Invalid information.").join(" ");
  if(typeof detail==="object")return detail?.message||"The request could not be completed.";
  return String(detail||"The request could not be completed.");
};

const label=(value)=>String(value||"—").replaceAll("_"," ");
const when=(value)=>value?new Date(value).toLocaleString():"—";

function Status({value}){
  const tone=["APPROVED","COMPLETED","RELEASED"].includes(value)?"good":["REJECTED","EXPIRED"].includes(value)?"bad":"warn";
  return <span className={`control-status ${tone}`}>{label(value)}</span>;
}

export default function SecurityWorkspace(){
  const {roles}=useAuth();
  const isAdmin=roles.includes("ADMIN");
  const isMD=roles.includes("MD");
  const [requests,setRequests]=useState([]);
  const [lateActions,setLateActions]=useState([]);
  const [passwords,setPasswords]=useState({});
  const [busyId,setBusyId]=useState("");
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");

  async function load(){
    setLoading(true);
    setError("");
    try{
      const [resetRows,lateRows]=await Promise.all([
        apiRequest("/security/password-reset-requests"),
        apiRequest("/security/late-attendance-actions"),
      ]);
      setRequests(Array.isArray(resetRows)?resetRows:[]);
      setLateActions(Array.isArray(lateRows)?lateRows:[]);
    }catch(err){setError(readableError(err))}
    finally{setLoading(false)}
  }

  useEffect(()=>{load()},[]);

  async function run(id,path,body,success){
    setBusyId(id);
    setError("");
    setNotice("");
    try{
      await apiRequest(path,{method:"POST",body});
      setNotice(success);
      window.dispatchEvent(new Event("action-alerts:refresh"));
      await load();
    }catch(err){setError(readableError(err))}
    finally{setBusyId("")}
  }

  async function decide(row,approved){
    const promptText=approved
      ?"Approval note (optional):"
      :"Security reason for rejecting this reset request:";
    const note=window.prompt(promptText,"");
    if(note===null)return;
    if(!approved&&!note.trim()){
      setError("A rejection reason is required.");
      return;
    }
    await run(
      row.id,
      `/security/password-reset-requests/${row.id}/decision`,
      {approved,note:note.trim()||null},
      approved
        ?"MD approval recorded. ADMIN may now assign a temporary password within 24 hours."
        :"Password reset request rejected. The employee's current password was not changed.",
    );
  }

  async function complete(row){
    const temporary_password=passwords[row.id]||"";
    if(temporary_password.length<10){
      setError("Enter a strong temporary password of at least 10 characters.");
      return;
    }
    await run(
      row.id,
      `/security/password-reset-requests/${row.id}/complete`,
      {temporary_password},
      `Password reset completed for ${row.target_employee_code}. Their existing sessions were revoked.`,
    );
    setPasswords(current=>({...current,[row.id]:""}));
  }

  async function releaseHold(row){
    const note=window.prompt(
      `Reason for releasing ${row.employee_code}'s automatic salary hold for ${row.month_start}:`,
      "",
    );
    if(note===null)return;
    if(note.trim().length<3){setError("Enter a release note of at least 3 characters.");return}
    await run(
      row.id,
      `/security/late-attendance-actions/${row.id}/release-hold`,
      {note:note.trim()},
      "MD released the automatic late-attendance salary hold.",
    );
  }

  const resetQueue=useMemo(()=>requests.filter(row=>(isMD&&row.status==="PENDING_MD")||(isAdmin&&row.status==="APPROVED")),[requests,isAdmin,isMD]);
  const activeHolds=lateActions.filter(row=>row.salary_hold_required&&!row.hold_released_at);

  return <div className="page workforce-controls">
    <header className="page-header">
      <div><span className="eyebrow">Protected actions</span><h1>Security Approvals</h1><p>Password resets require MD approval. Repeated-lateness deductions and salary holds remain fully auditable.</p></div>
      <button className="secondary-button" onClick={load} disabled={loading}>{loading?"Refreshing…":"Refresh"}</button>
    </header>

    {error&&<div className="error-banner">{error}</div>}
    {notice&&<div className="success-banner">{notice}</div>}

    <section className="control-metrics">
      <article><span>My reset actions</span><strong>{resetQueue.length}</strong></article>
      <article><span>Active salary holds</span><strong>{activeHolds.length}</strong></article>
      <article><span>Late-policy records</span><strong>{lateActions.length}</strong></article>
    </section>

    <section className="panel">
      <div className="panel-header"><div><span className="eyebrow">MD-gated reset</span><h2>Password reset queue</h2><p>ADMIN states the reason, MD decides, and only then can ADMIN assign a temporary password. Approval expires after 24 hours.</p></div></div>
      {loading?<div className="skeleton-lines"/>:requests.length===0?<div className="empty-state">No password reset requests have been raised.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Employee</th><th>Requested by</th><th>Reason</th><th>Requested</th><th>Status</th><th>Decision / completion</th></tr></thead><tbody>{requests.map(row=><tr key={row.id}>
        <td><strong>{row.target_employee_code}</strong><div className="muted">{row.target_employee_name}</div></td>
        <td>{row.requested_by_employee_code}</td>
        <td>{row.reason}{row.decision_note&&<div className="muted">MD: {row.decision_note}</div>}</td>
        <td>{when(row.requested_at)}{row.approval_expires_at&&row.status==="APPROVED"&&<div className="muted">Expires {when(row.approval_expires_at)}</div>}</td>
        <td><Status value={row.status}/></td>
        <td>
          {isMD&&row.status==="PENDING_MD"&&<div className="control-actions"><button className="primary-button compact-button" disabled={Boolean(busyId)} onClick={()=>decide(row,true)}>Approve</button><button className="secondary-button compact-button" disabled={Boolean(busyId)} onClick={()=>decide(row,false)}>Reject</button></div>}
          {isAdmin&&row.status==="APPROVED"&&<div className="secure-complete"><input type="password" minLength="10" autoComplete="new-password" placeholder="Strong temporary password" value={passwords[row.id]||""} onChange={event=>setPasswords(current=>({...current,[row.id]:event.target.value}))}/><button className="primary-button compact-button" disabled={busyId===row.id} onClick={()=>complete(row)}>{busyId===row.id?"Resetting…":"Complete reset"}</button></div>}
          {row.completed_at&&<span className="muted">Completed {when(row.completed_at)}</span>}
          {!((isMD&&row.status==="PENDING_MD")||(isAdmin&&row.status==="APPROVED")||row.completed_at)&&<span className="muted">No action for this role</span>}
        </td>
      </tr>)}</tbody></table></div>}
    </section>

    <section className="panel">
      <div className="panel-header"><div><span className="eyebrow">Automatic payroll policy</span><h2>Late-attendance actions</h2><p>Only check-ins at least 30 minutes after the configured grace period qualify. Three in a calendar month trigger a half-day basic deduction; the fourth triggers a salary hold.</p></div></div>
      {loading?<div className="skeleton-lines"/>:lateActions.length===0?<div className="empty-state">No monthly late-attendance action has been triggered.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Employee</th><th>Month</th><th>Qualifying days</th><th>Half-day deduction</th><th>Salary hold</th><th>Action</th></tr></thead><tbody>{lateActions.map(row=><tr key={row.id}>
        <td><strong>{row.employee_code}</strong><div className="muted">{row.employee_name}</div></td>
        <td>{row.month_start}</td><td>{row.qualifying_late_days}</td>
        <td>{row.half_day_deduction_required?<Status value="REQUIRED"/>:<span>—</span>}</td>
        <td>{row.salary_hold_required?<Status value="ACTIVE"/>:row.hold_released_at?<><Status value="RELEASED"/><div className="muted">{row.hold_release_note}</div></>:<span>—</span>}</td>
        <td>{isMD&&row.salary_hold_required&&!row.hold_released_at?<button className="secondary-button compact-button" disabled={busyId===row.id} onClick={()=>releaseHold(row)}>Release after review</button>:<span className="muted">{row.salary_hold_triggered_at?`Triggered ${when(row.salary_hold_triggered_at)}`:"—"}</span>}</td>
      </tr>)}</tbody></table></div>}
    </section>
  </div>;
}
