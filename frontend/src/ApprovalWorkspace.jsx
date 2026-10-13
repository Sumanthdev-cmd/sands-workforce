import {useEffect,useRef,useState} from "react";
import {useLocation} from "react-router-dom";
import {apiRequest,uploadWithProgress} from "./lib/api";
import {useAuth} from "./context/AuthContext";

const REVIEW_ROLES=["ADMIN","MD","GM"];
const makeNewForm=()=>({approval_type:"GENERAL_APPROVAL",title:"",description:"",submission_id:crypto.randomUUID()});

function readableError(error){
  if(error?.status===409)return error?.message||"This request has already been processed.";
  const value=error?.detail??error?.message??error;
  if(typeof value==="string")return value==="[object Object]"?"The request could not be completed.":value;
  if(Array.isArray(value))return value.map(item=>item?.msg||"Invalid information.").join(" ");
  return "The request could not be completed.";
}

function displayCode(value){return String(value||"—").replaceAll("_"," ")}

export default function ApprovalWorkspace(){
  const {roles=[]}=useAuth();
  const location=useLocation();
  const reviewer=roles.some(role=>REVIEW_ROLES.includes(role));
  const canDecide=roles.includes("MD");

  const [form,setForm]=useState(makeNewForm);
  const [file,setFile]=useState(null);
  const [myRequests,setMyRequests]=useState([]);
  const [pendingRequests,setPendingRequests]=useState([]);
  const [selected,setSelected]=useState(null);
  const [actions,setActions]=useState([]);
  const [decisionNote,setDecisionNote]=useState("");
  const [rejectionReason,setRejectionReason]=useState("");
  const [showForm,setShowForm]=useState(false);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [progress,setProgress]=useState(0);
  const [success,setSuccess]=useState("");
  const [error,setError]=useState("");

  const submittingRef=useRef(false);
  const uploadedDocumentIdRef=useRef(null);
  const pendingRef=useRef(null);
  const reviewRef=useRef(null);

  function refreshGlobalAlerts(){
    window.dispatchEvent(new Event("action-alerts:refresh"));
  }

  async function loadRequests(){
    setLoading(true);
    setError("");
    try{
      const mine=await apiRequest("/approvals/documents/me");
      setMyRequests(Array.isArray(mine)?mine:[]);
      if(reviewer){
        const pending=await apiRequest("/approvals/documents/pending");
        setPendingRequests(Array.isArray(pending)?pending:[]);
      }else{
        setPendingRequests([]);
      }
    }catch(err){
      setError(readableError(err));
    }finally{
      setLoading(false);
    }
  }

  useEffect(()=>{loadRequests()},[reviewer]);

  useEffect(()=>{
    if(new URLSearchParams(location.search).get("queue")==="1"&&reviewer){
      window.setTimeout(()=>pendingRef.current?.scrollIntoView({behavior:"smooth",block:"start"}),150);
    }
  },[location.search,reviewer,loading]);

  function startNewRequest(){
    setForm(makeNewForm());
    setFile(null);
    uploadedDocumentIdRef.current=null;
    setProgress(0);
    setError("");
    setSuccess("");
    setShowForm(true);
  }

  async function uploadAttachment(){
    if(!file)return null;
    if(uploadedDocumentIdRef.current)return uploadedDocumentIdRef.current;
    const contentType=file.type||"application/octet-stream";
    const prepared=await apiRequest("/documents/presign-upload",{method:"POST",body:{
      owner_type:"GENERAL",
      owner_id:null,
      category:"APPROVAL_SUPPORT",
      title:`${form.title.trim()} - Supporting Attachment`,
      description:"Supporting attachment for an approval request.",
      issue_date:null,
      expiry_date:null,
      alert_days_before:30,
      is_confidential:true,
      file_name:file.name,
      content_type:contentType,
      file_size:file.size,
      extra_data:{purpose:"APPROVAL_REQUEST",submission_id:form.submission_id}
    }});
    const etag=await uploadWithProgress(prepared.upload_url,file,contentType,setProgress);
    await apiRequest(`/documents/${prepared.document_id}/complete`,{method:"POST",body:{etag:etag?etag.replaceAll('"',""):null}});
    uploadedDocumentIdRef.current=prepared.document_id;
    setProgress(100);
    return prepared.document_id;
  }

  async function submitRequest(event){
    event.preventDefault();
    if(submittingRef.current)return;
    if(!form.title.trim()||!form.description.trim()){
      setError("Title and description are required.");
      return;
    }
    submittingRef.current=true;
    setBusy(true);
    setError("");
    setSuccess("");
    try{
      const documentId=await uploadAttachment();
      await apiRequest("/approvals/documents",{method:"POST",body:{
        document_id:documentId,
        approval_type:form.approval_type,
        title:form.title.trim(),
        description:form.description.trim(),
        extra_data:{submission_id:form.submission_id}
      }});
      setSuccess("Approval request submitted. The assigned approver has been notified.");
      setForm(makeNewForm());
      setFile(null);
      uploadedDocumentIdRef.current=null;
      setProgress(0);
      setShowForm(false);
      await loadRequests();
      refreshGlobalAlerts();
    }catch(err){setError(readableError(err));}
    finally{submittingRef.current=false;setBusy(false);}
  }

  async function review(row){
    setSelected(row);
    setDecisionNote("");
    setRejectionReason("");
    setActions([]);
    setError("");
    try{
      const history=await apiRequest(`/approvals/documents/${row.id}/actions`);
      setActions(Array.isArray(history)?history:[]);
    }catch{}
    window.setTimeout(()=>reviewRef.current?.scrollIntoView({behavior:"smooth",block:"start"}),80);
  }

  async function approve(){
    if(!canDecide||!selected||busy)return;
    setBusy(true);
    setError("");
    setSuccess("");
    try{
      await apiRequest(`/approvals/documents/${selected.id}/approve`,{method:"POST",body:{note:decisionNote.trim()||null}});
      setSuccess(`Approved: ${selected.title}`);
      setSelected(null);
      await loadRequests();
      refreshGlobalAlerts();
    }catch(err){setError(readableError(err));}
    finally{setBusy(false);}
  }

  async function reject(){
    if(!canDecide||!selected||busy)return;
    if(rejectionReason.trim().length<3){
      setError("Enter a rejection reason of at least 3 characters.");
      return;
    }
    setBusy(true);
    setError("");
    setSuccess("");
    try{
      await apiRequest(`/approvals/documents/${selected.id}/reject`,{method:"POST",body:{reason:rejectionReason.trim()}});
      setSuccess(`Rejected: ${selected.title}`);
      setSelected(null);
      await loadRequests();
      refreshGlobalAlerts();
    }catch(err){setError(readableError(err));}
    finally{setBusy(false);}
  }

  return <div className="page">
    <header className="page-header"><div><span className="eyebrow">Workflow</span><h1>Approval Requests</h1><p>Submit requests, review pending work and complete MD decisions without entering internal IDs.</p></div></header>
    {success&&<div className="success-banner">✅ {success}</div>}
    {error&&<div className="error-banner">{error}</div>}

    <div className="action-strip">
      {!showForm?<button type="button" className="primary-button" onClick={startNewRequest}>+ New Approval Request</button>:<button type="button" className="secondary-button" disabled={busy} onClick={()=>setShowForm(false)}>Close</button>}
      <button type="button" className="secondary-button" disabled={loading||busy} onClick={loadRequests}>{loading?"Refreshing…":"Refresh"}</button>
      {reviewer&&pendingRequests.length>0&&<button type="button" className="secondary-button pending-leave-button" onClick={()=>pendingRef.current?.scrollIntoView({behavior:"smooth",block:"start"})}>Pending Requests <span className="pending-leave-badge">{pendingRequests.length>99?"99+":pendingRequests.length}</span></button>}
    </div>

    {showForm&&<section className="panel">
      <div className="panel-header"><div><h2>New Approval Request</h2><p>Supporting image/PDF is optional.</p></div></div>
      <form className="document-form" onSubmit={submitRequest}>
        <div className="form-grid">
          <label>Approval Type *<select required disabled={busy} value={form.approval_type} onChange={e=>setForm({...form,approval_type:e.target.value})}>{["GENERAL_APPROVAL","FINANCE","PAYMENT","PURCHASE","WORK_COMPLETION","MAINTENANCE","VENDOR","MANAGEMENT"].map(value=><option key={value} value={value}>{displayCode(value)}</option>)}</select></label>
          <label>Title *<input required minLength="3" maxLength="220" disabled={busy} value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/></label>
        </div>
        <label>Description *<textarea required rows="5" minLength="3" maxLength="5000" disabled={busy} value={form.description} onChange={e=>setForm({...form,description:e.target.value})}/></label>
        <label className="file-drop">Supporting Image / PDF <small>Optional</small><input type="file" accept=".pdf,image/*" disabled={busy} onChange={e=>{setFile(e.target.files?.[0]||null);uploadedDocumentIdRef.current=null;setProgress(0)}}/><span>{file?`${file.name} · ${Math.round(file.size/1024)} KB`:"Choose image or PDF"}</span></label>
        {progress>0&&<div className="progress-bar"><span style={{width:`${progress}%`}}/></div>}
        <button className="primary-button" disabled={busy}>{busy?"Submitting…":"Submit for Approval"}</button>
      </form>
    </section>}

    <section className="panel">
      <div className="panel-header"><div><h2>My Requests</h2><p>Track requests you submitted and their decision.</p></div></div>
      {loading?<div className="skeleton-lines"/>:myRequests.length===0?<div className="empty-state">No approval requests submitted yet.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Attachment</th><th>Decision</th><th>Submitted</th></tr></thead><tbody>{myRequests.map(row=><tr key={row.id}><td><strong>{row.title}</strong><div className="muted">{row.description}</div></td><td>{displayCode(row.approval_type)}</td><td><strong>{displayCode(row.status)}</strong></td><td>{row.document_title||"No attachment"}</td><td>{row.decision_note||"—"}</td><td>{row.created_at?new Date(row.created_at).toLocaleString():"—"}</td></tr>)}</tbody></table></div>}
    </section>

    {reviewer&&<section className="panel" ref={pendingRef}>
      <div className="panel-header"><div><span className="eyebrow">Action Queue</span><h2>Pending Requests</h2><p>{canDecide?"Requests awaiting your MD decision.":"You can review these requests; MD approval is required for the final decision."}</p></div>{pendingRequests.length>0&&<span className="pending-leave-badge">{pendingRequests.length>99?"99+":pendingRequests.length}</span>}</div>
      {loading?<div className="skeleton-lines"/>:pendingRequests.length===0?<div className="empty-state">No pending approval requests.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Requester</th><th>Title</th><th>Type</th><th>Attachment</th><th>Submitted</th><th>Action</th></tr></thead><tbody>{pendingRequests.map(row=><tr key={row.id}><td>{row.requester_employee_code||"—"}</td><td><strong>{row.title}</strong><div className="muted">{row.description}</div></td><td>{displayCode(row.approval_type)}</td><td>{row.document_title||"No attachment"}</td><td>{row.created_at?new Date(row.created_at).toLocaleString():"—"}</td><td><button type="button" className="secondary-button" onClick={()=>review(row)}>Review</button></td></tr>)}</tbody></table></div>}
    </section>}

    {selected&&<section className="panel approval-review-panel" ref={reviewRef}>
      <div className="panel-header"><div><span className="eyebrow">Review Request</span><h2>{selected.title}</h2><p>{selected.requester_employee_code||"Requester"} · {displayCode(selected.approval_type)}</p></div><button type="button" className="secondary-button" disabled={busy} onClick={()=>setSelected(null)}>Close</button></div>
      <div className="approval-review-grid"><div><small>Description</small><p>{selected.description}</p></div><div><small>Attachment</small><p>{selected.document_title||"No attachment"}</p></div><div><small>Submitted</small><p>{selected.created_at?new Date(selected.created_at).toLocaleString():"—"}</p></div></div>
      {actions.length>0&&<div className="simple-list"><h3>History</h3>{actions.map(item=><div className="simple-row" key={item.id}><div><strong>{displayCode(item.action)}</strong><span>{item.note||"No note"}</span></div><span>{item.created_at?new Date(item.created_at).toLocaleString():""}</span></div>)}</div>}
      {canDecide?<><label>Approval Note<textarea rows="3" maxLength="5000" disabled={busy} value={decisionNote} onChange={e=>setDecisionNote(e.target.value)} placeholder="Optional note for approval"/></label><label>Rejection Reason<textarea rows="3" minLength="3" maxLength="5000" disabled={busy} value={rejectionReason} onChange={e=>setRejectionReason(e.target.value)} placeholder="Required only when rejecting"/></label><div className="action-strip"><button type="button" className="primary-button" disabled={busy} onClick={approve}>{busy?"Processing…":"Approve"}</button><button type="button" className="secondary-button danger" disabled={busy} onClick={reject}>Reject</button></div></>:<div className="warning-banner">Only MD can approve or reject this request. Your role has review-only access.</div>}
    </section>}
  </div>;
}
