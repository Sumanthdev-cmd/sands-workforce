import {useEffect,useMemo,useState} from "react";

import {useAuth} from "./context/AuthContext";
import {apiRequest,uploadWithProgress} from "./lib/api";


const today=()=>{
  const now=new Date();
  return new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,10);
};
const display=(value)=>String(value||"—").replaceAll("_"," ");
const money=(value)=>`₹${Number(value||0).toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const time=(value)=>value?new Date(value).toLocaleString():"—";
const duration=(minutes)=>`${Math.floor(Number(minutes||0)/60)}h ${Number(minutes||0)%60}m`;
const readableError=(error)=>{
  const detail=error?.data?.detail??error?.message??error;
  if(Array.isArray(detail))return detail.map(item=>item?.msg||"Invalid information.").join(" ");
  if(typeof detail==="object")return detail?.message||"The request could not be completed.";
  return String(detail||"The request could not be completed.");
};

function Status({value}){return <span className={`control-status ${["APPROVED","PAID"].includes(value)?"good":value==="REJECTED"?"bad":"warn"}`}>{display(value)}</span>}

export default function OvertimeWorkspace(){
  const {roles}=useAuth();
  const isAdmin=roles.includes("ADMIN");
  const isMD=roles.includes("MD");
  const canManage=isAdmin||isMD;
  const [form,setForm]=useState({work_date:today(),reason:""});
  const [file,setFile]=useState(null);
  const [progress,setProgress]=useState(0);
  const [lookup,setLookup]=useState(null);
  const [claims,setClaims]=useState([]);
  const [organizationClaims,setOrganizationClaims]=useState([]);
  const [employees,setEmployees]=useState([]);
  const [searchEmployee,setSearchEmployee]=useState("");
  const [searchEmployeeText,setSearchEmployeeText]=useState("");
  const [searchDate,setSearchDate]=useState(today());
  const [managementLookup,setManagementLookup]=useState(null);
  const [amounts,setAmounts]=useState({});
  const [notes,setNotes]=useState({});
  const [busyId,setBusyId]=useState("");
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");

  async function load(){
    setLoading(true);
    setError("");
    try{
      const requests=[apiRequest("/overtime/claims/me")];
      if(canManage)requests.push(apiRequest("/overtime/claims/organization"),apiRequest("/employees?limit=200"));
      const values=await Promise.all(requests);
      setClaims(Array.isArray(values[0])?values[0]:[]);
      if(canManage){
        const orgRows=Array.isArray(values[1])?values[1]:[];
        setOrganizationClaims(orgRows);
        setEmployees(Array.isArray(values[2])?values[2]:[]);
        setAmounts(current=>Object.fromEntries(orgRows.map(row=>[row.id,current[row.id]??row.approved_amount??row.admin_proposed_amount??""])));
      }
    }catch(err){setError(readableError(err))}
    finally{setLoading(false)}
  }

  useEffect(()=>{load()},[canManage]);

  async function lookupMine(){
    setBusyId("mine-lookup");setError("");setLookup(null);
    try{setLookup(await apiRequest(`/overtime/me/attendance?work_date=${form.work_date}`))}
    catch(err){setError(readableError(err))}
    finally{setBusyId("")}
  }

  async function uploadEvidence(claim,fileValue){
    if(!fileValue)return null;
    if(fileValue.size>50_000_000)throw new Error("The evidence file exceeds the 50 MB limit.");
    const content_type=fileValue.type||"application/octet-stream";
    const prepared=await apiRequest("/documents/presign-upload",{method:"POST",body:{
      owner_type:"EMPLOYEE",owner_id:null,category:"OVERTIME_CLAIM",
      title:`OT evidence - ${claim.work_date}`,description:form.reason.trim(),
      file_name:fileValue.name,content_type,file_size:fileValue.size,
      issue_date:claim.work_date,expiry_date:null,alert_days_before:0,is_confidential:true,
      extra_data:{purpose:"OVERTIME_CLAIM",claim_id:claim.id},
    }});
    const etag=await uploadWithProgress(prepared.upload_url,fileValue,content_type,setProgress);
    await apiRequest(`/documents/${prepared.document_id}/complete`,{method:"POST",body:{etag:etag?etag.replaceAll('"',""):null}});
    await apiRequest(`/overtime/claims/${claim.id}/evidence`,{method:"POST",body:{document_id:prepared.document_id}});
    return prepared.document_id;
  }

  async function submitClaim(event){
    event.preventDefault();
    setBusyId("submit");setError("");setNotice("");setProgress(0);
    try{
      const claim=await apiRequest("/overtime/claims",{method:"POST",body:{work_date:form.work_date,reason:form.reason.trim()}});
      await uploadEvidence(claim,file);
      await apiRequest(`/overtime/claims/${claim.id}/submit`,{method:"POST"});
      setNotice("Overtime claim sent to ADMIN for attendance verification and benefit proposal.");
      setForm({work_date:today(),reason:""});setFile(null);setLookup(null);setProgress(0);
      window.dispatchEvent(new Event("action-alerts:refresh"));
      await load();
    }catch(err){setError(readableError(err))}
    finally{setBusyId("")}
  }

  async function lookupEmployee(){
    const typed=searchEmployeeText.trim().toLowerCase();
    const matched=employees.find(employee=>
      employee.id===searchEmployee||
      `${employee.employee_code} — ${employee.full_name}`.toLowerCase()===typed||
      employee.employee_code.toLowerCase()===typed||
      employee.full_name.toLowerCase()===typed
    );
    if(!matched){setError("Type and select a valid employee code or name.");return}
    setSearchEmployee(matched.id);
    setBusyId("management-lookup");setError("");setManagementLookup(null);
    try{setManagementLookup(await apiRequest(`/overtime/attendance-lookup?employee_id=${matched.id}&work_date=${searchDate}`))}
    catch(err){setError(readableError(err))}
    finally{setBusyId("")}
  }

  async function openEvidence(row,mode){
    if(!row.evidence_document_id)return;
    const popup=window.open("","_blank");
    setBusyId(`document-${row.id}`);setError("");
    try{
      const result=await apiRequest(`/documents/${row.evidence_document_id}/${mode==="download"?"download-url":"preview-url"}`);
      if(!result?.download_url)throw new Error("A secure document URL was not returned.");
      if(popup)popup.location.href=result.download_url;else window.open(result.download_url,"_blank","noopener,noreferrer");
    }catch(err){popup?.close();setError(readableError(err))}
    finally{setBusyId("")}
  }

  async function review(row,approved,stage){
    const amount=Number(amounts[row.id]);
    const note=(notes[row.id]||"").trim();
    if(approved&&(!Number.isFinite(amount)||amount<=0)){setError("Enter a positive OT benefit amount.");return}
    if(!approved&&!note){setError("Enter a rejection reason in the notes field.");return}
    setBusyId(row.id);setError("");setNotice("");
    try{
      const path=stage==="admin"?`/overtime/claims/${row.id}/admin-review`:`/overtime/claims/${row.id}/md-decision`;
      const body=stage==="admin"
        ?{approved,proposed_amount:approved?amount:null,note:note||null}
        :{approved,approved_amount:approved?amount:null,note:note||null};
      await apiRequest(path,{method:"POST",body});
      setNotice(stage==="admin"?(approved?"OT claim verified and sent to MD.":"OT claim rejected by ADMIN."):(approved?"Final OT benefit approved for payroll.":"OT claim rejected by MD."));
      window.dispatchEvent(new Event("action-alerts:refresh"));
      await load();
    }catch(err){setError(readableError(err))}
    finally{setBusyId("")}
  }

  const queue=useMemo(()=>organizationClaims.filter(row=>(isAdmin&&row.status==="PENDING_ADMIN")||(isMD&&row.status==="PENDING_MD")),[organizationClaims,isAdmin,isMD]);

  return <div className="page workforce-controls">
    <header className="page-header"><div><span className="eyebrow">Attendance-backed benefit</span><h1>Overtime</h1><p>Employees claim completed overtime; ADMIN verifies exact work time and proposes the benefit; MD makes the final decision.</p></div><button className="secondary-button" onClick={load} disabled={loading}>Refresh</button></header>
    {error&&<div className="error-banner">{error}</div>}{notice&&<div className="success-banner">{notice}</div>}

    <section className="panel">
      <div className="panel-header"><div><h2>Claim my overtime</h2><p>Check-out must be completed and recorded work must exceed the assigned shift. Supporting evidence is optional.</p></div></div>
      <form className="control-form" onSubmit={submitClaim}>
        <label>Work date<input type="date" required max={today()} value={form.work_date} onChange={event=>{setForm({...form,work_date:event.target.value});setLookup(null)}}/></label>
        <button type="button" className="secondary-button align-end" disabled={busyId==="mine-lookup"} onClick={lookupMine}>{busyId==="mine-lookup"?"Checking…":"Check exact work hours"}</button>
        <label className="wide">Reason for overtime<textarea required minLength="5" rows="3" value={form.reason} onChange={event=>setForm({...form,reason:event.target.value})} placeholder="Describe the work completed beyond office timing."/></label>
        <label className="wide">Supporting document (optional)<input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.xls,.xlsx,.csv,.doc,.docx" onChange={event=>setFile(event.target.files?.[0]||null)}/><small>{file?`${file.name} · ${Math.round(file.size/1024)} KB`:"PDF, image, spreadsheet or document; maximum 50 MB."}</small></label>
        {lookup&&<div className={`work-lookup wide ${lookup.eligible_for_overtime?"eligible":"not-eligible"}`}><strong>{lookup.message}</strong><span>Check-in {time(lookup.check_in_at)} · Check-out {time(lookup.check_out_at)}</span><span>Worked {duration(lookup.worked_minutes)} · Shift {duration(lookup.scheduled_minutes)} · OT {duration(lookup.overtime_minutes)}</span></div>}
        {progress>0&&<div className="control-progress wide"><span style={{width:`${progress}%`}}/></div>}
        <div className="wide"><button className="primary-button" disabled={busyId==="submit"}>{busyId==="submit"?"Submitting…":"Submit OT claim"}</button></div>
      </form>
    </section>

    <section className="panel">
      <div className="panel-header"><div><h2>My OT claims</h2><p>Track verification, MD decision and payroll payment.</p></div></div>
      {loading?<div className="skeleton-lines"/>:claims.length===0?<div className="empty-state">No overtime claims yet.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Date</th><th>Exact work</th><th>Overtime</th><th>Status</th><th>ADMIN proposal</th><th>MD amount</th></tr></thead><tbody>{claims.map(row=><tr key={row.id}><td>{row.work_date}<div className="muted">{row.reason}</div></td><td>{duration(row.worked_minutes)}<div className="muted">{time(row.check_in_at)} → {time(row.check_out_at)}</div></td><td>{duration(row.overtime_minutes)}</td><td><Status value={row.status}/></td><td>{row.admin_proposed_amount!=null?money(row.admin_proposed_amount):"—"}</td><td>{row.approved_amount!=null?money(row.approved_amount):"—"}</td></tr>)}</tbody></table></div>}
    </section>

    {canManage&&<>
      <section className="panel">
        <div className="panel-header"><div><span className="eyebrow">Independent verification</span><h2>Employee work-hours lookup</h2><p>Search by employee and date to view the exact recorded shift, check-in, check-out, worked time and OT.</p></div></div>
        <div className="control-form lookup-form"><label>Employee name or code<input list="ot-employee-options" value={searchEmployeeText} onChange={event=>{setSearchEmployeeText(event.target.value);setSearchEmployee("")}} placeholder="Start typing a name or employee code"/><datalist id="ot-employee-options">{employees.map(employee=><option key={employee.id} value={`${employee.employee_code} — ${employee.full_name}`}/>)}</datalist></label><label>Date<input type="date" max={today()} value={searchDate} onChange={event=>setSearchDate(event.target.value)}/></label><button className="primary-button align-end" type="button" disabled={busyId==="management-lookup"} onClick={lookupEmployee}>{busyId==="management-lookup"?"Checking…":"Show exact hours"}</button>{managementLookup&&<div className={`work-lookup wide ${managementLookup.eligible_for_overtime?"eligible":"not-eligible"}`}><strong>{managementLookup.employee_code} — {managementLookup.employee_name}</strong><span>{managementLookup.message}</span><span>Check-in {time(managementLookup.check_in_at)} · Check-out {time(managementLookup.check_out_at)}</span><span>Worked {duration(managementLookup.worked_minutes)} · Assigned shift {duration(managementLookup.scheduled_minutes)} · OT {duration(managementLookup.overtime_minutes)}</span></div>}</div>
      </section>

      <section className="panel">
        <div className="panel-header"><div><span className="eyebrow">Approval queue</span><h2>{isMD?"MD overtime decisions":"ADMIN overtime verification"}</h2><p>{isMD?"The MD can retain or change ADMIN's proposed benefit before approval.":"Verify recorded hours, inspect evidence, and enter the proposed benefit for MD."}</p></div><span className="queue-count">{queue.length} waiting</span></div>
        {queue.length===0?<div className="empty-state">No overtime claims are waiting for your role.</div>:<div className="ot-queue">{queue.map(row=><article className="ot-card" key={row.id}><div className="ot-card-head"><div><strong>{row.employee_code} — {row.employee_name}</strong><span>{row.work_date} · {row.reason}</span></div><Status value={row.status}/></div><div className="ot-facts"><span>Check-in<strong>{time(row.check_in_at)}</strong></span><span>Check-out<strong>{time(row.check_out_at)}</strong></span><span>Worked<strong>{duration(row.worked_minutes)}</strong></span><span>Assigned shift<strong>{duration(row.scheduled_minutes)}</strong></span><span>Overtime<strong>{duration(row.overtime_minutes)}</strong></span></div>{row.evidence_document_id&&<div className="control-actions"><button className="secondary-button compact-button" type="button" onClick={()=>openEvidence(row,"preview")}>Preview evidence</button><button className="secondary-button compact-button" type="button" onClick={()=>openEvidence(row,"download")}>Download</button></div>}<div className="review-form"><label>{isMD?"Final benefit amount":"Proposed benefit amount"}<input type="number" min="0.01" step="0.01" value={amounts[row.id]??""} onChange={event=>setAmounts(current=>({...current,[row.id]:event.target.value}))}/>{isMD&&row.admin_proposed_amount!=null&&<small>ADMIN proposed {money(row.admin_proposed_amount)}</small>}</label><label>Review note<textarea rows="2" value={notes[row.id]||""} onChange={event=>setNotes(current=>({...current,[row.id]:event.target.value}))} placeholder="Required when rejecting; optional when approving."/></label><div className="control-actions align-end"><button className="primary-button" disabled={busyId===row.id} onClick={()=>review(row,true,isMD?"md":"admin")}>{busyId===row.id?"Saving…":isMD?"Approve final benefit":"Verify & send to MD"}</button><button className="secondary-button" disabled={busyId===row.id} onClick={()=>review(row,false,isMD?"md":"admin")}>Reject</button></div></div></article>)}</div>}
      </section>

      <section className="panel">
        <div className="panel-header"><div><span className="eyebrow">Audit history</span><h2>Organization OT claims</h2><p>All submitted, approved, rejected and paid OT claims remain available for review.</p></div></div>
        {organizationClaims.length===0?<div className="empty-state">No organization overtime claims yet.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Employee</th><th>Date</th><th>Worked / OT</th><th>Status</th><th>ADMIN proposal</th><th>MD amount</th><th>Evidence</th></tr></thead><tbody>{organizationClaims.map(row=><tr key={row.id}><td><strong>{row.employee_code}</strong><div className="muted">{row.employee_name}</div></td><td>{row.work_date}<div className="muted">{row.reason}</div></td><td>{duration(row.worked_minutes)}<div className="muted">OT {duration(row.overtime_minutes)}</div></td><td><Status value={row.status}/></td><td>{row.admin_proposed_amount!=null?money(row.admin_proposed_amount):"—"}</td><td>{row.approved_amount!=null?money(row.approved_amount):"—"}</td><td>{row.evidence_document_id?<div className="control-actions"><button className="secondary-button compact-button" type="button" onClick={()=>openEvidence(row,"preview")}>Preview</button><button className="secondary-button compact-button" type="button" onClick={()=>openEvidence(row,"download")}>Download</button></div>:"—"}</td></tr>)}</tbody></table></div>}
      </section>
    </>}
  </div>;
}
