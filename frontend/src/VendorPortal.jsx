import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {openNativeWorkday} from "./lib/nativeWorkday";
import {useEffect,useMemo,useRef,useState} from "react";
import "./VendorPortal.css";

const API_BASE=import.meta.env.VITE_API_BASE_URL||"/api/v1";
const TOKEN_KEY="sands_vendor_access_token";

const getToken=()=>localStorage.getItem(TOKEN_KEY);
const clearToken=()=>localStorage.removeItem(TOKEN_KEY);

function errorText(value){
  const detail=value?.detail??value?.message??value;
  if(typeof detail==="string")return detail;
  if(Array.isArray(detail))return detail.map(x=>x?.msg||"Invalid information.").join(" ");
  if(detail&&typeof detail==="object"&&typeof detail.message==="string")return detail.message;
  return "The request could not be completed.";
}

async function vendorRequest(path,{method="GET",body,token=getToken()}={}){
  const normalized=path.startsWith("/")?path:`/${path}`;
  const headers={Accept:"application/json"};
  if(token)headers.Authorization=`Bearer ${token}`;
  let payload;
  if(body!==undefined){headers["Content-Type"]="application/json";payload=JSON.stringify(body)}
  const response=await fetch(`${API_BASE}/vendor-portal${normalized}`,{
    method,headers,body:["GET","HEAD"].includes(method.toUpperCase())?undefined:payload
  });
  let data=null;
  if(response.status!==204){
    const type=response.headers.get("content-type")||"";
    data=type.includes("application/json")?await response.json():await response.text();
  }
  if(!response.ok){
    if(response.status===401&&token)clearToken();
    const err=new Error(errorText(data));err.status=response.status;err.data=data;throw err;
  }
  return data;
}

function fmtDate(value){return value?new Date(value).toLocaleString("en-GB",dateOptions({},true)):"—"}
function fmtDay(value){if(!value)return "—";const d=new Date(`${value}T00:00:00`);return Number.isNaN(d.getTime())?value:d.toLocaleDateString("en-GB",dateOptions({},false))}
function money(value,currency="INR"){return `${currency==="INR"?"₹":`${currency} `}${Number(value||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`}
function human(value){return String(value||"—").replaceAll("_"," ")}
function answerValue(answer){if(answer&&typeof answer==="object")return answer.value??answer.text??"—";return answer??"—"}
function answerDetails(answer){if(answer&&typeof answer==="object")return answer.details||answer.text||"";return ""}

function SignaturePad({onChange}){
  const ref=useRef(null);const drawing=useRef(false);const dirty=useRef(false);
  function point(e){const canvas=ref.current;const r=canvas.getBoundingClientRect();return {x:(e.clientX-r.left)*(canvas.width/r.width),y:(e.clientY-r.top)*(canvas.height/r.height)}}
  function down(e){const c=ref.current;const p=point(e);const ctx=c.getContext("2d");drawing.current=true;dirty.current=true;ctx.beginPath();ctx.moveTo(p.x,p.y);c.setPointerCapture?.(e.pointerId)}
  function move(e){if(!drawing.current)return;const c=ref.current;const p=point(e);const ctx=c.getContext("2d");ctx.lineWidth=2;ctx.lineCap="round";ctx.lineTo(p.x,p.y);ctx.stroke()}
  function up(){drawing.current=false;if(dirty.current)onChange(ref.current.toDataURL("image/png"))}
  function clear(){const c=ref.current;c.getContext("2d").clearRect(0,0,c.width,c.height);dirty.current=false;onChange(null)}
  async function upload(e){const file=e.target.files?.[0];if(!file)return;const reader=new FileReader();reader.onload=()=>onChange(String(reader.result||""));reader.readAsDataURL(file)}
  return <div className="signature-box"><strong>Optional signature</strong><p>Draw below or upload a signature image. You may also submit without a signature.</p>
    <canvas ref={ref} width="700" height="170" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}/>
    <div className="signature-actions"><button type="button" className="secondary-button" onClick={clear}>Clear drawing</button>
      <label className="file-button">Upload image<input type="file" accept="image/png,image/jpeg" onChange={upload}/></label></div></div>
}

function VendorLogin({onLogin}){
  const [form,setForm]=useState({organization_code:"SANDS",vendor_code:"",password:""});
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  async function submit(e){e.preventDefault();setBusy(true);setError("");try{
    const data=await vendorRequest("/auth/login",{method:"POST",body:form,token:null});
    localStorage.setItem(TOKEN_KEY,data.access_token);await onLogin();
  }catch(err){setError(errorText(err?.data||err))}finally{setBusy(false)}}
  return <div className="vendor-login-page"><section className="vendor-login-hero"><div><span className="login-badge">SandS Workforce Vendor Portal</span>
    <h1>Your outlet documents and inspection responses in one secure place.</h1><p>This sign-in is for external vendors only. Employee and management accounts use the normal workforce login.</p></div></section>
    <section className="vendor-login-panel"><form className="vendor-login-card" onSubmit={submit}><div className="brand-block light"><div className="brand-mark">S</div><div><strong>SandS Vendor Portal</strong><small>Restricted external access</small></div></div>
      <div><h2>Vendor sign in</h2><p className="muted">Use the vendor code and password issued by your administrator.</p></div>
      {error&&<div className="error-banner">{error}</div>}
      <label>Organization code<input required value={form.organization_code} onChange={e=>setForm({...form,organization_code:e.target.value.toUpperCase()})}/></label>
      <label>Vendor code<input required autoComplete="username" value={form.vendor_code} onChange={e=>setForm({...form,vendor_code:e.target.value.toUpperCase()})}/></label>
      <label>Password<input required minLength="8" type="password" autoComplete="current-password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/></label>
      <button className="primary-button large" disabled={busy}>{busy?"Signing in…":"Vendor sign in"}</button>
      <a className="vendor-back-link" href="/login">Employee / Management sign in</a>
    </form></section></div>
}

function PasswordChange({forced=false,onChanged}){
  const [form,setForm]=useState({current_password:"",new_password:"",confirm:""});const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [message,setMessage]=useState("");
  async function submit(e){e.preventDefault();setError("");setMessage("");if(form.new_password!==form.confirm){setError("New password and confirmation do not match.");return}setBusy(true);try{
    await vendorRequest("/change-password",{method:"POST",body:{current_password:form.current_password,new_password:form.new_password}});
    setMessage("Password changed successfully.");setForm({current_password:"",new_password:"",confirm:""});await onChanged?.();
  }catch(err){setError(errorText(err?.data||err))}finally{setBusy(false)}}
  return <section className="panel vendor-password-panel"><div><span className="eyebrow">Account security</span><h2>{forced?"Change temporary password":"Change password"}</h2>
    <p>{forced?"Your administrator issued a temporary password. Change it before continuing to the portal.":"Changing your password signs out other vendor sessions."}</p></div>
    {error&&<div className="error-banner">{error}</div>}{message&&<div className="success-banner">{message}</div>}
    <form className="vendor-password-form" onSubmit={submit}><label>Current password<input required minLength="8" type="password" value={form.current_password} onChange={e=>setForm({...form,current_password:e.target.value})}/></label>
      <label>New password<input required minLength="8" type="password" value={form.new_password} onChange={e=>setForm({...form,new_password:e.target.value})}/></label>
      <label>Confirm new password<input required minLength="8" type="password" value={form.confirm} onChange={e=>setForm({...form,confirm:e.target.value})}/></label>
      <button className="primary-button" disabled={busy}>{busy?"Changing…":"Change password"}</button></form></section>
}

function vendorPosition(){
  if(!window.isSecureContext&&!["localhost","127.0.0.1"].includes(window.location.hostname))return Promise.reject(new Error("GPS attendance requires HTTPS on a phone."));
  if(!navigator.geolocation)return Promise.reject(new Error("This device does not provide browser GPS."));
  return new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(resolve,error=>reject(new Error(error.code===1?"Location permission was denied. Allow it in browser settings.":"A fresh GPS location could not be obtained.")),{enableHighAccuracy:true,timeout:20000,maximumAge:0}));
}

function VendorAttendance({outlets,records,onChanged}){
  const [busy,setBusy]=useState("");const [error,setError]=useState("");const [message,setMessage]=useState("");
  async function mark(outlet,action){if(openNativeWorkday())return;setBusy(outlet.id);setError("");setMessage("");try{if(outlet.latitude==null||outlet.longitude==null)throw new Error("Admin must add coordinates for this outlet first.");const position=await vendorPosition();await vendorRequest(`/attendance/${action}`,{method:"POST",body:{outlet_id:outlet.id,latitude:position.coords.latitude,longitude:position.coords.longitude,accuracy_meters:position.coords.accuracy??null}});setMessage(`${action==="check-in"?"Check-in":"Check-out"} recorded at ${outlet.name}.`);await onChanged()}catch(err){setError(errorText(err?.data||err))}finally{setBusy("")}}
  return <div className="vendor-page"><span className="eyebrow">Shop geofence</span><h1>My Attendance</h1><p>Attendance is accepted only while your phone is within the allowed distance of the selected shop.</p>{error&&<div className="error-banner">{error}</div>}{message&&<div className="success-banner">{message}</div>}<div className="vendor-attendance-grid">{outlets.length===0?<div className="empty-state">No outlet is linked to this vendor account.</div>:outlets.map(outlet=>{const record=records.find(item=>item.outlet_id===outlet.id);return <article key={outlet.id}><div><span className="outlet-code">{outlet.code}</span><h3>{outlet.name}</h3><p>{outlet.address}</p><small>Allowed radius: {Math.round(outlet.attendance_radius_meters||150)} m</small></div><div className="vendor-attendance-status"><strong>{record?human(record.status):"NOT CHECKED IN"}</strong><span>In: {fmtDate(record?.check_in_at)}</span><span>Out: {fmtDate(record?.check_out_at)}</span></div><div className="vendor-attendance-actions"><button className="primary-button" disabled={Boolean(busy)||Boolean(record)} onClick={()=>mark(outlet,"check-in")}>{busy===outlet.id?"Getting GPS…":"Check in at shop"}</button><button className="secondary-button" disabled={Boolean(busy)||!record||Boolean(record.check_out_at)} onClick={()=>mark(outlet,"check-out")}>Check out</button></div></article>})}</div></div>
}

function VendorSalaryAdvance({advances,onChanged}){
  const [form,setForm]=useState({requested_amount:"",installment_amount:"",recovery_months:"1",currency:"INR",reason:""});
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");const [message,setMessage]=useState("");
  const expectedMonths=useMemo(()=>{
    const requested=Number(form.requested_amount);const installment=Number(form.installment_amount);
    if(!requested||!installment||installment<=0)return null;
    return Math.ceil(Math.round(requested*100)/Math.round(installment*100));
  },[form.requested_amount,form.installment_amount]);
  async function submit(e){e.preventDefault();setError("");setMessage("");if(expectedMonths&&Number(form.recovery_months)!==expectedMonths){setError(`Recovery duration must be ${expectedMonths} month(s) for this deduction amount.`);return}setBusy(true);try{
    await vendorRequest("/salary-advances",{method:"POST",body:{...form,requested_amount:Number(form.requested_amount),installment_amount:Number(form.installment_amount),recovery_months:Number(form.recovery_months),currency:form.currency.toUpperCase(),reason:form.reason.trim()}});
    setMessage("Salary advance request sent to MD.");setForm({requested_amount:"",installment_amount:"",recovery_months:"1",currency:"INR",reason:""});await onChanged();
  }catch(err){setError(errorText(err?.data||err))}finally{setBusy(false)}}
  async function cancel(item){const note=window.prompt("Cancellation reason:","Cancelled by vendor");if(note===null)return;if(note.trim().length<3){setError("Enter at least 3 characters for cancellation reason.");return}setBusy(true);try{await vendorRequest(`/salary-advances/${item.id}/cancel`,{method:"POST",body:{note:note.trim()}});setMessage("Salary advance request cancelled.");await onChanged()}catch(err){setError(errorText(err?.data||err))}finally{setBusy(false)}}
  return <div className="vendor-page"><span className="eyebrow">Payroll request</span><h1>Salary Advance</h1><p>Request an advance, propose the monthly recovery amount, and track MD approval, disbursement and recovery.</p>{error&&<div className="error-banner">{error}</div>}{message&&<div className="success-banner">{message}</div>}
    <section className="panel"><h2>New request</h2><form className="vendor-password-form" onSubmit={submit}>
      <label>Advance amount *<input required type="number" min="0.01" step="0.01" disabled={busy} value={form.requested_amount} onChange={e=>setForm({...form,requested_amount:e.target.value})}/></label>
      <label>Monthly recovery amount *<input required type="number" min="0.01" step="0.01" disabled={busy} value={form.installment_amount} onChange={e=>setForm({...form,installment_amount:e.target.value})}/></label>
      <label>Recovery duration months *<input required type="number" min="1" max="120" step="1" disabled={busy} value={form.recovery_months} onChange={e=>setForm({...form,recovery_months:e.target.value})}/></label>
      <label>Currency *<input required minLength="3" maxLength="10" disabled={busy} value={form.currency} onChange={e=>setForm({...form,currency:e.target.value.toUpperCase()})}/></label>
      {expectedMonths&&<p className={Number(form.recovery_months)===expectedMonths?"muted":"error-banner"}>At this monthly deduction, recovery takes {expectedMonths} month(s).</p>}
      <label>Reason *<textarea required minLength="5" maxLength="5000" rows="3" disabled={busy} value={form.reason} onChange={e=>setForm({...form,reason:e.target.value})}/></label>
      <button className="primary-button" disabled={busy}>{busy?"Submitting…":"Send Request to MD"}</button>
    </form></section>
    <section className="panel"><h2>My advance requests</h2><div className="vendor-document-list">{advances.length===0?<div className="empty-state">No salary advance requests yet.</div>:advances.map(item=><article key={item.id}><div><span className="outlet-code">{human(item.status)}</span><h3>{money(item.requested_amount,item.currency)}</h3><p>{item.reason}</p><small>Recovery: {money(item.installment_amount,item.currency)} for {item.recovery_months} month(s) · Recovered {money(item.recovered_amount,item.currency)} · Remaining {money(item.remaining_amount,item.currency)}</small>{item.recovery_start_date&&<small> Starts: {formatDisplayDate(item.recovery_start_date)}</small>}{item.decision_note&&<small> MD note: {item.decision_note}</small>}</div>{item.status==="PENDING"&&<button className="secondary-button" disabled={busy} onClick={()=>cancel(item)}>Cancel</button>}</article>)}</div></section></div>
}

function InspectionDetail({report,onClose,onResponded}){
  const [response,setResponse]=useState("ACCEPT");const [remarks,setRemarks]=useState("");const [signature,setSignature]=useState(null);const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  const sections=report?.template_snapshot?.sections||[];const canRespond=report?.status==="VENDOR_PENDING";
  async function submit(e){e.preventDefault();setError("");if(response==="DISPUTE"&&remarks.trim().length<3){setError("Please enter the dispute reason / remarks.");return}setBusy(true);try{
    const updated=await vendorRequest(`/inspections/${report.id}/respond`,{method:"POST",body:{response,remarks:remarks.trim()||null,signature_data_uri:signature||null}});await onResponded(updated);
  }catch(err){setError(errorText(err?.data||err))}finally{setBusy(false)}}
  return <div className="vendor-drawer-backdrop"><aside className="vendor-drawer"><div className="vendor-drawer-head"><div><span className="eyebrow">{report.report_number}</span><h2>{report.outlet_code} - {report.outlet_name}</h2><p>{report.outlet_address}</p></div><button className="icon-button" onClick={onClose}>✕</button></div>
    <div className="inspection-summary-strip"><span>Status <strong>{human(report.status)}</strong></span><span>Inspector <strong>{report.inspector_code||report.inspector_name||"Inspection Team"}</strong></span><span>Submitted <strong>{fmtDate(report.submitted_at)}</strong></span><span>Flags <strong>{report.attention_flag_count}</strong></span></div>
    {report.attention_flags?.length>0&&<div className="vendor-attention"><strong>Attention items</strong>{report.attention_flags.map((f,i)=><p key={i}>{f.section}: {f.question} — {f.answer}{f.details?` (${f.details})`:""}</p>)}</div>}
    <div className="vendor-checklist">{sections.map(section=><section key={section.id||section.title}><h3>{section.title}</h3>
      {(section.questions||[]).map(q=>{const a=report.answers?.[q.id];const details=answerDetails(a);return <div className="vendor-question" key={q.id}><div><strong>{q.label}</strong>{details&&<small>{details}</small>}</div><span>{human(answerValue(a))}</span></div>})}
      {report.section_remarks?.[section.id]&&<div className="section-remark"><strong>Section remarks:</strong> {report.section_remarks[section.id]}</div>}
    </section>)}</div>
    {canRespond?<form className="vendor-response-form" onSubmit={submit}><h3>Your response</h3><p>Accept the submitted report or dispute it with a reason. Signature is optional.</p>
      {error&&<div className="error-banner">{error}</div>}
      <div className="vendor-response-choice"><button type="button" className={response==="ACCEPT"?"selected":""} onClick={()=>setResponse("ACCEPT")}>✓ Accept</button><button type="button" className={response==="DISPUTE"?"selected dispute":""} onClick={()=>setResponse("DISPUTE")}>! Dispute</button></div>
      <label>{response==="DISPUTE"?"Dispute reason / remarks *":"Remarks (optional)"}<textarea rows="4" required={response==="DISPUTE"} value={remarks} onChange={e=>setRemarks(e.target.value)}/></label>
      <SignaturePad onChange={setSignature}/><button className="primary-button" disabled={busy}>{busy?"Submitting…":`Submit ${response}`}</button></form>:
      <div className="vendor-response-record"><h3>Vendor response recorded</h3><p><strong>{human(report.vendor_response)}</strong> on {fmtDate(report.vendor_responded_at)}</p>{report.vendor_remarks&&<p>{report.vendor_remarks}</p>}</div>}
  </aside></div>
}

export default function VendorPortal(){
  const [me,setMe]=useState(null);const [loading,setLoading]=useState(Boolean(getToken()));const [tab,setTab]=useState("dashboard");
  const [dashboard,setDashboard]=useState(null);const [outlets,setOutlets]=useState([]);const [attendance,setAttendance]=useState([]);const [documents,setDocuments]=useState([]);const [inspections,setInspections]=useState([]);const [notifications,setNotifications]=useState([]);const [advances,setAdvances]=useState([]);const [detail,setDetail]=useState(null);const [error,setError]=useState("");

  async function refreshProfile(){
    if(!getToken()){setMe(null);setLoading(false);return null}
    try{const profile=await vendorRequest("/me");setMe(profile);return profile}catch{clearToken();setMe(null);return null}finally{setLoading(false)}
  }
  async function loadData(){
    if(!getToken())return;setError("");
    const results=await Promise.allSettled([vendorRequest("/dashboard"),vendorRequest("/outlets"),vendorRequest("/attendance/today"),vendorRequest("/documents"),vendorRequest("/inspections"),vendorRequest("/notifications"),vendorRequest("/salary-advances")]);
    if(results[0].status==="fulfilled")setDashboard(results[0].value);if(results[1].status==="fulfilled")setOutlets(results[1].value||[]);if(results[2].status==="fulfilled")setAttendance(results[2].value||[]);if(results[3].status==="fulfilled")setDocuments(results[3].value||[]);if(results[4].status==="fulfilled")setInspections(results[4].value||[]);if(results[5].status==="fulfilled")setNotifications(results[5].value||[]);if(results[6].status==="fulfilled")setAdvances(results[6].value||[]);
    const failed=results.find(x=>x.status==="rejected");if(failed)setError(errorText(failed.reason?.data||failed.reason));
  }
  useEffect(()=>{refreshProfile().then(p=>{if(p&&!p.force_password_change)loadData()})},[]);
  useEffect(()=>{if(!me||me.force_password_change)return;const t=setInterval(()=>{vendorRequest("/notifications?unread_only=true").then(n=>setNotifications(old=>{const read=old.filter(x=>x.read_at);return [...(n||[]),...read.filter(r=>!(n||[]).some(u=>u.id===r.id))]})).catch(()=>{})},60000);return()=>clearInterval(t)},[me?.vendor_code,me?.force_password_change]);

  async function signOut(){try{await vendorRequest("/auth/logout",{method:"POST"})}catch{}finally{clearToken();setMe(null);setDashboard(null)}}
  async function openInspection(id){try{setError("");setDetail(await vendorRequest(`/inspections/${id}`))}catch(err){setError(errorText(err?.data||err))}}
  async function afterResponse(updated){setDetail(updated);await loadData()}
  async function download(id){try{const r=await vendorRequest(`/documents/${id}/download`);window.open(r.download_url,"_blank","noopener,noreferrer")}catch(err){setError(errorText(err?.data||err))}}
  async function markRead(n){try{await vendorRequest(`/notifications/${n.id}/read`,{method:"POST"});if(n.payload?.inspection_report_id)openInspection(n.payload.inspection_report_id);await loadData()}catch(err){setError(errorText(err?.data||err))}}

  if(loading)return <div className="vendor-center">Loading vendor portal…</div>;
  if(!me)return <VendorLogin onLogin={async()=>{const p=await refreshProfile();if(p&&!p.force_password_change)await loadData()}}/>;
  if(me.force_password_change)return <div className="vendor-forced-page"><div className="vendor-forced-card"><div className="brand-block light"><div className="brand-mark">S</div><div><strong>{me.vendor_name}</strong><small>{me.vendor_code}</small></div></div><PasswordChange forced onChanged={async()=>{const p=await refreshProfile();if(p)await loadData()}}/><button className="secondary-button" onClick={signOut}>Sign out</button></div></div>;

  const unread=notifications.filter(n=>!n.read_at).length;
  return <div className="vendor-portal-shell"><aside className="vendor-sidebar"><div className="brand-block"><div className="brand-mark">S</div><div><strong>SandS Vendor Portal</strong><small>{me.vendor_code}</small></div></div>
    <div className="vendor-identity"><strong>{me.vendor_name}</strong><span>{me.organization_code}</span></div>
    <nav>{[["dashboard","Dashboard","📊"],["attendance","My Attendance","📍"],["advance","Salary Advance","💳"],["outlets","My Shops / Outlets","🏪"],["documents","Documents","📄"],["inspections","Inspection Reports","📋"],["notifications",`Notifications${unread?` (${unread})`:""}`,"🔔"],["profile","Profile","👤"]].map(([id,label,icon])=><button key={id} className={tab===id?"active":""} onClick={()=>setTab(id)}><span>{icon}</span>{label}</button>)}</nav>
    <button className="secondary-button dark" onClick={signOut}>Sign out</button></aside>
    <main className="vendor-main"><header className="vendor-topbar"><div><strong>{me.vendor_name}</strong><span>Restricted vendor access</span></div><button className="secondary-button" onClick={loadData}>Refresh</button></header>
      {error&&<div className="error-banner">{error}</div>}
      {tab==="dashboard"&&<div className="vendor-page"><span className="eyebrow">Overview</span><h1>Vendor Dashboard</h1><p>Only outlets linked to {me.vendor_code} are visible here.</p><div className="vendor-metrics">{[["My outlets",dashboard?.outlet_count??"—"],["Documents",dashboard?.document_count??"—"],["Pending inspections",dashboard?.pending_inspection_count??"—"],["Unread notifications",dashboard?.unread_notification_count??"—"]].map(([l,v])=><article key={l}><span>{l}</span><strong>{v}</strong></article>)}</div>
        <section className="panel"><h2>Pending inspection responses</h2>{inspections.filter(i=>i.status==="VENDOR_PENDING").length===0?<div className="empty-compact">No inspection response is pending.</div>:inspections.filter(i=>i.status==="VENDOR_PENDING").map(i=><button className="vendor-row-button" key={i.id} onClick={()=>openInspection(i.id)}><span><strong>{i.report_number}</strong><small>{i.outlet_code} - {i.outlet_name}</small></span><b>Review →</b></button>)}</section></div>}
      {tab==="attendance"&&<VendorAttendance outlets={outlets} records={attendance} onChanged={loadData}/>} 
      {tab==="advance"&&<VendorSalaryAdvance advances={advances} onChanged={loadData}/>}
      {tab==="outlets"&&<div className="vendor-page"><span className="eyebrow">Linked locations</span><h1>My Shops / Outlets</h1><div className="vendor-outlet-grid">{outlets.length===0?<div className="empty-state">No outlets are linked to this vendor account.</div>:outlets.map(o=><article key={o.id}><div className="outlet-card-top"><span className="outlet-code">{o.code}</span><span className={`vendor-status ${o.is_active?"good":"bad"}`}>{o.status|| (o.is_active?"ACTIVE":"INACTIVE")}</span></div><h3>{o.name}</h3><p>{o.address}</p><dl><div><dt>Cluster</dt><dd>{o.cluster_name||"—"}</dd></div><div><dt>Trade licence expiry</dt><dd>{fmtDay(o.licence_expiry_date)}</dd></div><div><dt>Excise expiry</dt><dd>{fmtDay(o.excise_expiry_date)}</dd></div><div><dt>Rent agreement expiry</dt><dd>{fmtDay(o.rent_agreement_expiry_date)}</dd></div></dl></article>)}</div></div>}
      {tab==="documents"&&<div className="vendor-page"><span className="eyebrow">Read-only files</span><h1>Outlet Documents</h1><p>Only non-confidential documents belonging to your linked outlets are shown. Vendor accounts cannot replace official records.</p><div className="vendor-document-list">{documents.length===0?<div className="empty-state">No documents are available.</div>:documents.map(d=><article key={d.id}><div><span className="outlet-code">{d.outlet_code}</span><h3>{d.title}</h3><p>{d.category} · {d.file_name}</p><small>Expiry: {fmtDay(d.expiry_date)}</small></div><button className="secondary-button" onClick={()=>download(d.id)}>View / Download</button></article>)}</div></div>}
      {tab==="inspections"&&<div className="vendor-page"><span className="eyebrow">Inspection workflow</span><h1>Inspection Reports</h1><div className="vendor-inspection-list">{inspections.length===0?<div className="empty-state">No inspection reports are available.</div>:inspections.map(i=><article key={i.id}><div><span className="outlet-code">{i.report_number}</span><h3>{i.outlet_code} - {i.outlet_name}</h3><p>{fmtDate(i.submitted_at||i.inspection_started_at)} · Inspector {i.inspector_code||i.inspector_name||"Inspection Team"}</p></div><div><span className={`vendor-status ${i.status==="VENDOR_PENDING"?"warn":"good"}`}>{human(i.status)}</span><button className="secondary-button" onClick={()=>openInspection(i.id)}>Review</button></div></article>)}</div></div>}
      {tab==="notifications"&&<div className="vendor-page"><span className="eyebrow">Updates</span><h1>Notifications</h1><div className="vendor-notification-list">{notifications.length===0?<div className="empty-state">No notifications yet.</div>:notifications.map(n=><article key={n.id} className={n.read_at?"read":""}><div><strong>{n.title}</strong><p>{n.body}</p><small>{fmtDate(n.created_at)}</small></div>{!n.read_at&&<button className="secondary-button" onClick={()=>markRead(n)}>Open</button>}</article>)}</div></div>}
      {tab==="profile"&&<div className="vendor-page"><span className="eyebrow">Account</span><h1>Profile</h1><section className="panel"><div className="vendor-profile-grid"><div><small>Vendor code</small><strong>{me.vendor_code}</strong></div><div><small>Vendor name</small><strong>{me.vendor_name}</strong></div><div><small>Contact person</small><strong>{me.contact_person||"—"}</strong></div><div><small>Email</small><strong>{me.email||"—"}</strong></div><div><small>Phone</small><strong>{me.phone||"—"}</strong></div><div><small>Last login</small><strong>{fmtDate(me.last_login_at)}</strong></div></div></section><PasswordChange onChanged={refreshProfile}/></div>}
    </main>{detail&&<InspectionDetail report={detail} onClose={()=>setDetail(null)} onResponded={afterResponse}/>}</div>
}
// date-display-ddmmyyyy-v1
