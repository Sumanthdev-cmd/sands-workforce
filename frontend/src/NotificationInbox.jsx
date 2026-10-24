import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {useEffect,useState} from "react";
import {useNavigate} from "react-router-dom";
import {apiRequest} from "./lib/api";

export default function NotificationInbox(){
  const nav=useNavigate();
  const [items,setItems]=useState([]),[error,setError]=useState(""),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
  async function load(){
    const data=await apiRequest("/background/notifications/me");
    setItems(Array.isArray(data)?data:[]);
  }
  useEffect(()=>{load().catch(e=>setError(e.message))},[]);
  async function act(work){
    if(busy)return;
    setBusy(true);setError("");setMessage("");
    try{await work();await load();window.dispatchEvent(new Event("action-alerts:refresh"))}
    catch(e){setError(e.message||"Unable to update notifications. Please try again.")}
    finally{setBusy(false)}
  }
  function removeRead(){
    if(!window.confirm("Delete all your read notifications? Unread notifications and approval records will be kept."))return;
    act(async()=>{const result=await apiRequest("/background/notifications/read",{method:"DELETE"});setMessage(result.deleted_count ? result.deleted_count+" read notification(s) deleted." : "No read notifications to delete.")});
  }
  async function open(n){
    await act(async()=>{if(!n.read_at)await apiRequest("/background/notifications/"+n.id+"/read",{method:"POST"});nav(n?.payload?.route||"/module/notifications")});
  }
  const readCount=items.filter(n=>n.read_at).length;
  return <div className="page">
    <header className="page-header" style={{flexWrap:"wrap",gap:12}}>
      <div><span className="eyebrow">Updates</span><h1>Notifications</h1><p>Approvals, renewals, assignments and workflow updates.</p></div>
      <div className="header-actions" style={{display:"flex",flexWrap:"wrap",gap:8}}>
        <button className="secondary-button" disabled={busy||readCount===0} onClick={removeRead}>Delete read{readCount>0 ? " ("+readCount+")" : ""}</button>
        <button className="secondary-button" disabled={busy} onClick={()=>act(async()=>{})}>{busy?"Updating…":"Refresh"}</button>
      </div>
    </header>
    {error&&<div className="error-banner" role="alert">{error}</div>}
    {message&&<div role="status" style={{padding:12,background:"#ecfdf5",color:"#065f46",borderRadius:8,marginBottom:12}}>{message}</div>}
    <div className="notification-list">{items.length===0?<div className="empty-state">No notifications yet.</div>:items.map(n=>
      <article className={"notification-card "+(n.read_at?"read":"")} key={n.id} style={{flexWrap:"wrap",gap:12}}>
        <div style={{minWidth:0,flex:"1 1 240px",overflowWrap:"anywhere"}}><strong>{n.title}</strong><p>{n.body}</p><small>{n.created_at?new Date(n.created_at).toLocaleString("en-GB",dateOptions({},true)):""}{n.read_at?" · Read":""}</small></div>
        <div className="header-actions" style={{flexWrap:"wrap",gap:8}}>
          {n?.payload?.route&&<button disabled={busy} className="primary-button" onClick={()=>open(n)}>Open</button>}
          {!n.read_at&&<button disabled={busy} className="secondary-button" onClick={()=>act(()=>apiRequest("/background/notifications/"+n.id+"/read",{method:"POST"}))}>Mark read</button>}
        </div>
      </article>)}</div>
  </div>
}
// date-display-ddmmyyyy-v1
