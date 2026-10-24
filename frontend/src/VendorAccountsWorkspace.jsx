import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {useEffect,useMemo,useState} from "react";
import {apiRequest} from "./lib/api";
import {useAuth} from "./context/AuthContext";
import "./VendorPortal.css";

function errText(error){
  const value=error?.data?.detail??error?.detail??error?.message??error;
  if(typeof value==="string")return value;
  if(Array.isArray(value))return value.map(x=>x?.msg||"Invalid information.").join(" ");
  return "The request could not be completed.";
}

function dateTime(value){return value?new Date(value).toLocaleString("en-GB",dateOptions({},true)):"Never";}

export default function VendorAccountsWorkspace(){
  const {roles}=useAuth();
  const admin=roles.includes("ADMIN");
  const [vendors,setVendors]=useState([]);
  const [accounts,setAccounts]=useState([]);
  const [vendorId,setVendorId]=useState("");
  const [temporaryPassword,setTemporaryPassword]=useState("");
  const [credential,setCredential]=useState(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");

  async function load(){
    setLoading(true);setError("");
    try{
      const [v,a]=await Promise.all([
        apiRequest("/operations/vendors"),
        apiRequest("/vendor-portal/admin/accounts")
      ]);
      setVendors(Array.isArray(v)?v:[]);
      setAccounts(Array.isArray(a)?a:[]);
    }catch(e){setError(errText(e))}finally{setLoading(false)}
  }
  useEffect(()=>{load()},[]);

  const available=useMemo(()=>{
    const used=new Set(accounts.map(a=>String(a.vendor_id)));
    return vendors.filter(v=>!used.has(String(v.id)));
  },[vendors,accounts]);

  async function create(event){
    event.preventDefault();
    if(!vendorId)return;
    setBusy(true);setError("");setMessage("");setCredential(null);
    try{
      const result=await apiRequest("/vendor-portal/admin/accounts",{
        method:"POST",
        body:{vendor_id:vendorId,temporary_password:temporaryPassword.trim()||null}
      });
      setCredential(result);setMessage("Vendor portal account created.");
      setVendorId("");setTemporaryPassword("");await load();
    }catch(e){setError(errText(e))}finally{setBusy(false)}
  }

  async function reset(account){
    if(!window.confirm(`Reset password for ${account.vendor_code} - ${account.vendor_name}?`))return;
    setBusy(true);setError("");setCredential(null);
    try{
      const result=await apiRequest(`/vendor-portal/admin/accounts/${account.id}/reset-password`,{
        method:"POST",body:{temporary_password:null}
      });
      setCredential(result);setMessage("Temporary password reset. Existing vendor sessions were signed out.");
      await load();
    }catch(e){setError(errText(e))}finally{setBusy(false)}
  }

  async function toggle(account,enable){
    const action=enable?"enable":"disable";
    if(!window.confirm(`${action[0].toUpperCase()+action.slice(1)} ${account.vendor_code}?`))return;
    setBusy(true);setError("");
    try{
      await apiRequest(`/vendor-portal/admin/accounts/${account.id}/${action}`,{method:"POST"});
      setMessage(`Vendor account ${enable?"enabled":"disabled"}.`);await load();
    }catch(e){setError(errText(e))}finally{setBusy(false)}
  }

  async function copyCredentials(){
    if(!credential?.temporary_password)return;
    const text=`Organization Code: ${credential.organization_code}\nVendor Code: ${credential.vendor_code}\nTemporary Password: ${credential.temporary_password}\nVendor Login: ${window.location.origin}/vendor-login`;
    try{await navigator.clipboard.writeText(text);setMessage("Credentials copied.")}catch{setMessage("Copy is not available. Select the credentials below manually.")}
  }

  return <div className="page vendor-admin-page">
    <header className="page-header"><div><span className="eyebrow">External access</span><h1>Vendor Access</h1>
      <p>Create and control vendor portal logins without adding vendors to employee roles.</p></div>
      <button className="secondary-button" onClick={load}>Refresh</button></header>
    {error&&<div className="error-banner">{error}</div>}
    {message&&<div className="success-banner">{message}</div>}

    {credential?.temporary_password&&<section className="panel vendor-credential-panel">
      <div><span className="eyebrow">Show once</span><h2>Vendor login credentials</h2>
        <p>Give these credentials only to the intended vendor. The temporary password is not stored in readable form.</p></div>
      <div className="credential-grid">
        <div><small>Organization Code</small><strong>{credential.organization_code}</strong></div>
        <div><small>Vendor Code</small><strong>{credential.vendor_code}</strong></div>
        <div><small>Temporary Password</small><strong>{credential.temporary_password}</strong></div>
        <div><small>Login</small><strong>{window.location.origin}/vendor-login</strong></div>
      </div>
      <button className="secondary-button" onClick={copyCredentials}>Copy credentials</button>
    </section>}

    {admin&&<section className="panel"><div className="panel-header"><div><h2>Create vendor login</h2>
      <p>Select the vendor by name/code. Internal UUIDs stay hidden.</p></div></div>
      <form className="vendor-account-form" onSubmit={create}>
        <label>Vendor *<select required value={vendorId} onChange={e=>setVendorId(e.target.value)}>
          <option value="">Select vendor</option>
          {available.map(v=><option key={v.id} value={v.id}>{v.code} - {v.name}</option>)}
        </select></label>
        <label>Temporary password <input type="password" minLength="8" value={temporaryPassword}
          onChange={e=>setTemporaryPassword(e.target.value)} placeholder="Leave blank to auto-generate"/></label>
        <button className="primary-button" disabled={busy||!vendorId}>{busy?"Working…":"Create vendor login"}</button>
      </form>
      {available.length===0&&!loading&&<div className="empty-compact">Every current vendor already has a portal account.</div>}
    </section>}

    <section className="panel"><div className="panel-header"><div><h2>Vendor portal accounts</h2>
      <p>{accounts.length} account(s). Credential changes are Admin-only.</p></div></div>
      {loading?<div className="empty-state">Loading vendor accounts…</div>:accounts.length===0?<div className="empty-state">No vendor portal accounts yet.</div>:
      <div className="vendor-account-list">{accounts.map(a=><article className="vendor-account-card" key={a.id}>
        <div><span className="outlet-code">{a.vendor_code}</span><h3>{a.vendor_name}</h3>
          <p>{a.email||"No vendor email recorded"}</p></div>
        <div className="vendor-account-meta"><span className={`vendor-status ${a.status==="ACTIVE"?"good":"bad"}`}>{a.status}</span>
          <span>{a.force_password_change?"Password change required":"Password changed"}</span>
          <span>Last login: {dateTime(a.last_login_at)}</span></div>
        {admin&&<div className="vendor-account-actions">
          <button className="secondary-button" disabled={busy} onClick={()=>reset(a)}>Reset password</button>
          {a.status==="ACTIVE"?<button className="secondary-button danger-text" disabled={busy} onClick={()=>toggle(a,false)}>Disable</button>:
            <button className="secondary-button" disabled={busy} onClick={()=>toggle(a,true)}>Enable</button>}
        </div>}
      </article>)}</div>}
    </section>
  </div>
}
// date-display-ddmmyyyy-v1
