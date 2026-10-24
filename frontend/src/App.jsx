import DateField from "./DateField";
import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import NotificationInbox from "./NotificationInbox";
import {compareModules} from "./navigationOrder";
import FinancialRecordsWorkspace from "./FinancialRecordsWorkspace";
import CashbookWorkspace from "./CashbookWorkspace";
import VendorCatalogue from "./VendorCatalogue";
import BoxLoadingWorkspace from "./BoxLoadingWorkspace";
import {createContext,useContext,useEffect,useMemo,useRef,useState} from "react";
import {Navigate,NavLink,Outlet,Route,Routes,useLocation,useNavigate,useParams} from "react-router-dom";
import {useAuth} from "./context/AuthContext";
import {apiRequest,getOpenApi,getOperation,getRequestSchema,resolveRef,uploadWithProgress} from "./lib/api";
import OutletsWorkspace from "./OutletsWorkspace";
import InspectionWorkspace from "./InspectionWorkspace";
import VendorInspectionReview from "./VendorInspectionReview";
import ApprovalWorkspace from "./ApprovalWorkspace";
import MaintenanceBillsWorkspace from "./MaintenanceBillsWorkspace";
import FuelWorkspace from "./FuelWorkspace";
import AssetWorkspace from "./AssetWorkspace";
import TasksWorkspace from "./TasksWorkspace";
import ExpensesWorkspace from "./ExpensesWorkspace";
import PayrollWorkspace from "./PayrollWorkspace";
import AppointmentWorkspace from "./AppointmentWorkspace";
import EmployeeWorkspace from "./EmployeeWorkspace";
import AttendanceWorkspace from "./AttendanceWorkspace";
import AccountsSheetWorkspace from "./AccountsSheetWorkspace";
import SecurityWorkspace from "./SecurityWorkspace";
import OvertimeWorkspace from "./OvertimeWorkspace";
import MdDailyOverview from "./MdDailyOverview";
import ShopRentalsWorkspace from "./ShopRentalsWorkspace";

import VendorPortal from "./VendorPortal";
import VendorAccountsWorkspace from "./VendorAccountsWorkspace";
const ALL=["CASHIER","ADMIN","MD","GM","MANAGER","ACCOUNTS_MANAGER","ACCOUNTS_SECRETARY","HR_RECRUITER","FIELD_VISITOR","OFFICE_EMPLOYEE","EMPLOYEE"];
const MGMT=["ADMIN","MD","GM","MANAGER"];
const SENIOR=["ADMIN","MD","GM"];
const modules = [
  ["financial-records", "Financial Records", "📥", ["ADMIN", "MD"]],
  ["cashbook", "Credit/Debit Record", "💰", ["CASHIER", "ADMIN", "MD"]],
  ["box-loading", "Box Loading", "📦", ["ADMIN", "MD"]],
  ["dashboard", "Dashboard", "📊", ALL],
  ["employees", "Employees", "👥", MGMT],
  ["attendance", "Attendance", "🕒", ALL],
  ["overtime", "Overtime", "⏱️", ALL],
  ["tasks", "Tasks", "✅", ALL],
  ["inspections", "Shop Inspections", "📋", ["ADMIN", "MD", "GM", "MANAGER", "FIELD_VISITOR"]],
  ["leave", "Leave", "🏖️", ALL],
  ["payroll","Payroll","💳",ALL],
  ["expenses", "Expenses", "🧾", ALL],
  ["sheet-verification", "Sheet Verification", "📑", ["ACCOUNTS_MANAGER", "ACCOUNTS_SECRETARY", "ADMIN", "MD"]],
  ["security", "Security Approvals", "🔐", ["ADMIN", "MD"]],
  ["md-overview", "MD Daily Overview", "🧭", ["MD"]],
  ["maintenance-bills", "Maintenance & Bills", "🧾", ["ADMIN", "MD"]],
  ["documents", "Documents", "📄", MGMT],
  ["assets", "Properties & Vehicles", "🏢", MGMT],
  ["shop-rentals", "Rentals/Deposits", "🏬", MGMT],
  ["outlets", "Shops / Outlets", "🏪", ["ADMIN", "MD", "GM", "MANAGER", "FIELD_VISITOR"]],
  ["fuel", "Fuel & Mileage", "⛽", ["ADMIN"]],
  ["inventory", "Asset Inventory", "💻", MGMT],
  ["recruitment", "Recruitment", "🎯", SENIOR],
  ["appointments", "MD Appointments", "📅", ALL],
  ["approvals", "Approval Requests", "✍️", ALL],
  ["operations", "Vendors & Labour", "🛠️", MGMT],
  ["notifications", "Notifications", "🔔", ALL],
  ["vendor-access", "Vendor Access", "🔐", MGMT],
];
const canSee = (roles, allowed = []) =>
  !roles.length || roles.some((r) => allowed.includes(r));
const visibleModules=(roles)=>modules.filter(([, , ,allowed])=>canSee(roles,allowed)).sort(compareModules);

const ActionAlertsContext=createContext({counts:{},refresh:()=>{}});
const useActionAlerts=()=>useContext(ActionAlertsContext);
const actionCount=(counts,id)=>Number(counts?.[id]||0);

const generic={
 payroll:{title:"Payroll",subtitle:"Salary structures, payroll runs, holds and payslips.",reads:[["Payroll runs","/payroll/runs"],["Salary holds","/payroll/holds"],["My payslips","/payroll/me/payslips"]],actions:[["Create payroll run","POST","/payroll/runs"],["Calculate payroll","POST","/payroll/runs/{run_id}/calculate"],["Finalize payroll","POST","/payroll/runs/{run_id}/finalize"],["Create salary structure","POST","/payroll/structures/{employee_id}"],["Revise salary","POST","/payroll/structures/{employee_id}/revise"],["Hold salary","POST","/payroll/holds/{employee_id}"],["Release hold","POST","/payroll/holds/{hold_id}/release"]]},
 assets:{title:"Properties & Vehicles",subtitle:"Vehicles, properties, outlets and renewal tracking.",reads:[["Vehicles","/assets/vehicles"],["Properties","/assets/properties"],["Outlets","/assets/outlets"],["Upcoming renewals","/assets/renewals/upcoming?days=90"]],actions:[["Add vehicle","POST","/assets/vehicles"],["Update vehicle","PATCH","/assets/vehicles/{vehicle_id}"],["Add property","POST","/assets/properties"],["Add outlet","POST","/assets/outlets"]]},
 fuel:{title:"Fuel & Mileage",subtitle:"Fuel indenting, expected versus actual mileage, vehicle fuel history and monthly fuel cost.",reads:[["Mileage dashboard","/fuel/dashboard"],["Fuel indents & history","/fuel/indents"]],actions:[["Create fuel indent","POST","/fuel/indents"],["Record fueling","POST","/fuel/indents/{indent_id}/fuel"],["Cancel fuel indent","POST","/fuel/indents/{indent_id}/cancel"]]},
 inventory:{title:"Asset Inventory",subtitle:"Company equipment, assignments, returns and maintenance.",reads:[["Assets","/asset-inventory/assets"],["Assignments","/asset-inventory/assignments"],["My assigned assets","/asset-inventory/assignments/me"],["Maintenance","/asset-inventory/maintenance"]],actions:[["Add company asset","POST","/asset-inventory/assets"],["Assign asset","POST","/asset-inventory/assets/{asset_id}/assign"],["Return asset","POST","/asset-inventory/assignments/{assignment_id}/return"],["Add maintenance","POST","/asset-inventory/maintenance"],["Complete maintenance","POST","/asset-inventory/maintenance/{maintenance_id}/complete"]]},
 recruitment:{title:"Recruitment",subtitle:"Vacancies, candidates, applications and AI-assisted screening.",reads:[["Vacancies","/recruitment/vacancies"],["Candidates","/recruitment/candidates"],["Applications","/recruitment/applications"]],actions:[["Create vacancy","POST","/recruitment/vacancies"],["Add candidate","POST","/recruitment/candidates"],["Create application","POST","/recruitment/applications"],["Screen application","POST","/recruitment/applications/{application_id}/screen"],["Screen all candidates","POST","/recruitment/vacancies/{vacancy_id}/screen-all"]]},
 appointments:{title:"MD Appointments",subtitle:"Request meetings with MD and manage decisions.",reads:[["My appointments","/appointments/me"],["Pending appointments","/appointments/pending"]],actions:[["Request appointment","POST","/appointments"],["Approve appointment","POST","/appointments/{appointment_id}/approve"],["Reject appointment","POST","/appointments/{appointment_id}/reject"],["Cancel appointment","POST","/appointments/{appointment_id}/cancel"],["Complete appointment","POST","/appointments/{appointment_id}/complete"]]},
 operations:{title:"Vendors, Labour & Wings",subtitle:"Vendor issues, labour payments and organization contact directory.",reads:[["Vendors","/operations/vendors"],["My vendor issues","/operations/vendor-issues/me"],["Pending vendor issues","/operations/vendor-issues/pending"],["My labour payments","/operations/labour-payments/me"],["Pending labour payments","/operations/labour-payments/pending"],["Wings","/operations/wings"]],actions:[["Add vendor","POST","/operations/vendors"],["Raise vendor issue","POST","/operations/vendor-issues"],["Assign issue","POST","/operations/vendor-issues/{issue_id}/assign"],["Resolve issue","POST","/operations/vendor-issues/{issue_id}/resolve"],["Request labour payment","POST","/operations/labour-payments"],["Approve labour payment","POST","/operations/labour-payments/{payment_id}/approve"],["Mark labour paid","POST","/operations/labour-payments/{payment_id}/mark-paid"],["Add wing","POST","/operations/wings"]]}
};

function Protected(){const {user,loading}=useAuth(); const loc=useLocation(); if(loading)return <Center text="Loading workspace…"/>; return user?<Outlet/>:<Navigate to="/login" state={{from:loc.pathname}} replace/>;}
function Center({text="Loading…"}){return <div className="center-page"><div className="spinner"/><p>{text}</p></div>}

function Login(){const {user,signIn}=useAuth(); const nav=useNavigate(); const loc=useLocation(); const [form,setForm]=useState({organization_code:"SANDS",employee_code:"ADMIN001",password:""}); const [error,setError]=useState(""); const [busy,setBusy]=useState(false); if(user)return <Navigate to="/dashboard" replace/>; async function submit(e){e.preventDefault();setBusy(true);setError("");try{await signIn(form);nav(loc.state?.from||"/dashboard",{replace:true});}catch(err){setError(err.message)}finally{setBusy(false)}} return <div className="login-page"><section className="login-hero"><div><span className="login-badge">SandS Software Solutions</span><h1>Your workforce, operations and approvals in one place.</h1><p>Attendance, tasks, payroll, documents, recruitment and management workflows for office and field teams.</p></div></section><section className="login-panel"><form className="login-card" onSubmit={submit}><Brand light/><div><h2>Welcome back</h2><p className="muted">Use the employee login issued by your organization.</p></div>{error&&<div className="error-banner">{error}</div>}<label>Organization code<input required value={form.organization_code} onChange={(e)=>setForm({...form,organization_code:e.target.value.toUpperCase()})}/></label><label>Employee code<input required value={form.employee_code} autoComplete="username" onChange={(e)=>setForm({...form,employee_code:e.target.value.toUpperCase()})}/></label><label>Password<input required type="password" autoComplete="current-password" value={form.password} onChange={(e)=>setForm({...form,password:e.target.value})}/></label><button className="primary-button large" disabled={busy}>{busy?"Signing in…":"Sign in"}</button><button type="button" className="secondary-button large" onClick={()=>nav("/vendor-login")}>Vendor sign in</button></form></section></div>}
function Brand({light=false}){return <div className={`brand-block ${light?"light":""}`}><div className="brand-mark">S</div><div><strong>SandS Workforce</strong><small>Operations platform</small></div></div>}

function Shell(){
  const {user,roles,signOut}=useAuth();
  const nav=useNavigate();
  const [mobile,setMobile]=useState(false);
  const [notifs,setNotifs]=useState([]);
  const [counts,setCounts]=useState({});
  const [open,setOpen]=useState(false);
  const notificationWrapRef=useRef(null);
  const code=user?.employee_code||user?.employee?.employee_code||user?.code||"User";

  async function loadNotifications(){
    try{
      const data=await apiRequest("/background/notifications/me?unread_only=true");
      setNotifs(Array.isArray(data)?data:[]);
    }catch{setNotifs([])}
  }

  async function loadActionCounts(){
    try{
      const data=await apiRequest("/background/action-counts");
      setCounts(data&&typeof data==="object"?data:{});
    }catch{setCounts({})}
  }

  async function refreshAlerts(){
    await Promise.allSettled([loadNotifications(),loadActionCounts()]);
  }

  useEffect(()=>{
    refreshAlerts();
    const timer=setInterval(refreshAlerts,30000);
    const handler=()=>refreshAlerts();
    window.addEventListener("action-alerts:refresh",handler);
    return()=>{
      clearInterval(timer);
      window.removeEventListener("action-alerts:refresh",handler);
    };
  },[]);

  useEffect(()=>{
    if(!open)return;

    function handleNotificationOutsideClick(event){
      const wrap=notificationWrapRef.current;

      if(wrap&&!wrap.contains(event.target)){
        setOpen(false);
      }
    }

    function handleNotificationEscape(event){
      if(event.key==="Escape"){
        setOpen(false);
      }
    }

    document.addEventListener(
      "pointerdown",
      handleNotificationOutsideClick
    );

    document.addEventListener(
      "keydown",
      handleNotificationEscape
    );

    return()=>{
      document.removeEventListener(
        "pointerdown",
        handleNotificationOutsideClick
      );

      document.removeEventListener(
        "keydown",
        handleNotificationEscape
      );
    };
  },[open]);

  async function openNotification(notification){
    try{
      if(!notification.read_at){
        await apiRequest(`/background/notifications/${notification.id}/read`,{method:"POST"});
      }
    }catch{}
    setOpen(false);
    await refreshAlerts();
    nav(notification?.payload?.route||"/module/notifications");
  }

  function hrefFor(id){
    if(id==="dashboard")return "/dashboard";
    return actionCount(counts,id)>0?`/module/${id}?queue=1`:`/module/${id}`;
  }

  return <ActionAlertsContext.Provider value={{counts,refresh:refreshAlerts}}>
    <div className="app-shell">
      {mobile&&<button className="sidebar-backdrop" onClick={()=>setMobile(false)}/>}<aside className={`sidebar ${mobile?"open":""}`}><Brand/><nav className="sidebar-nav">{visibleModules(roles).map(([id,label,icon])=>{const count=id==="notifications"?notifs.length:actionCount(counts,id);return <NavLink key={id} className={({isActive})=>`sidebar-link ${isActive?"active":""}`} to={hrefFor(id)} onClick={()=>setMobile(false)}><span className="module-link-icon">{icon}{count>0&&<span className="module-action-badge">{count>99?"99+":count}</span>}</span><span>{label}</span></NavLink>})}</nav><div className="sidebar-user"><strong>{code}</strong><small>{roles.join(", ")||"Authenticated user"}</small><button className="secondary-button dark" onClick={signOut}>Sign out</button></div></aside>
      <div className="content-shell"><header className="topbar"><button className="icon-button mobile-only" onClick={()=>setMobile(true)}>☰</button><div className="topbar-title"><strong>Workforce Management</strong><span>{new Date().toLocaleDateString("en-GB",dateOptions({},false))}</span></div><div className="topbar-actions"><div className="notification-wrap" ref={notificationWrapRef}><button type="button" aria-label="Notifications" aria-expanded={open} aria-controls="header-notification-panel" className="icon-button notification-button" onClick={()=>setOpen(!open)}>🔔{notifs.length>0&&<span className="notification-badge">{notifs.length>99?"99+":notifs.length}</span>}</button>{open&&<div className="notification-popover" id="header-notification-panel" role="region" aria-label="Notifications"><div className="popover-header"><strong>Notifications</strong><div className="notification-header-actions"><button type="button" className="link-button" onClick={()=>{setOpen(false);nav("/module/notifications")}}>View all</button><button type="button" className="notification-close" aria-label="Close notifications" onClick={()=>setOpen(false)}>×</button></div></div>{notifs.length===0?<div className="empty-compact">No unread notifications.</div>:notifs.slice(0,6).map(n=><button type="button" className="notification-item notification-item-button" key={n.id} onClick={()=>openNotification(n)}><strong>{n.title}</strong><span>{n.body}</span>{n?.payload?.route&&<small>Open related action →</small>}</button>)}</div>}</div><button className="profile-chip" onClick={()=>nav("/profile")}><span className="avatar">{code.slice(0,1)}</span><span>{code}</span></button></div></header><main className="main-content"><Outlet/></main></div>
    </div>
  </ActionAlertsContext.Provider>
}

function Dashboard(){
  const {user,roles}=useAuth();
  const {counts}=useActionAlerts();
  const [overview,setOverview]=useState({});
  const [alerts,setAlerts]=useState([]);
  const [today,setToday]=useState(null);
  useEffect(()=>{Promise.allSettled([apiRequest("/dashboard/management/overview"),apiRequest("/dashboard/management/alerts"),apiRequest("/attendance/me/today")]).then(([a,b,c])=>{if(a.status==="fulfilled")setOverview(a.value||{});if(b.status==="fulfilled")setAlerts(b.value||[]);if(c.status==="fulfilled")setToday(c.value||null)})},[]);
  const code=user?.employee_code||user?.employee?.employee_code||"User";
  const get=(keys)=>{for(const k of keys){const v=overview?.[k];if(typeof v==="number")return v;if(Array.isArray(v))return v.length}return "—"};
  const pendingTotal=Object.entries(counts||{}).filter(([k])=>k!=="notifications").reduce((sum,[,v])=>sum+Number(v||0),0);
  const cards=[["Current employees",get(["employees","total_employees","employee_count"])],["Present today",get(["present_today","present_count"])],["My pending actions",pendingTotal],["Alerts",Array.isArray(alerts)?alerts.length:"—"]];
  return <div className="page"><header className="page-header"><div><span className="eyebrow">Overview</span><h1>Good day, {code}</h1><p>{roles.length?`Signed in as ${roles.join(", ")}.`:"Your workspace is ready."}</p></div>{today&&<div className="today-status"><span>Today</span><strong>{today.status||"Recorded"}</strong></div>}</header><section className="metric-grid">{cards.map(([label,value])=><article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong><small>{label==="Current employees"&&typeof overview.active_employees==="number"&&typeof overview.disabled_employees==="number" ? `${overview.active_employees} active · ${overview.disabled_employees} disabled / resigned` : "Live workspace information"}</small></article>)}</section><section className="panel"><div className="panel-header"><div><span className="eyebrow">Quick access</span><h2>Your modules</h2><p>Red badges show unresolved work waiting for your role.</p></div></div><div className="module-grid">{visibleModules(roles).filter(([id])=>id!=="dashboard").map(([id,label,icon])=>{const count=actionCount(counts,id);const href=count>0?`/module/${id}?queue=1`:`/module/${id}`;return <NavLink className="module-card" key={id} to={href}><span className="module-icon">{icon}{count>0&&<span className="module-action-badge dashboard-action-badge">{count>99?"99+":count}</span>}</span><strong>{label}</strong></NavLink>})}</div></section></div>
}

function DataTable({rows}){const data=Array.isArray(rows)?rows:(rows?[rows]:[]); const [query,setQuery]=useState(""); const [page,setPage]=useState(1); const cols=useMemo(()=>{const keys=[...new Set(data.flatMap((r)=>Object.keys(r||{})))]; const pref=["employee_code","name","full_name","title","status","date","created_at"]; return [...pref.filter((k)=>keys.includes(k)),...keys.filter((k)=>!pref.includes(k))].slice(0,9)},[data]); const filtered=data.filter((row)=>!query||Object.values(row||{}).some((v)=>String(typeof v==="object"?JSON.stringify(v):v??"").toLowerCase().includes(query.toLowerCase()))); const size=10,total=Math.max(1,Math.ceil(filtered.length/size)),safe=Math.min(page,total),visible=filtered.slice((safe-1)*size,safe*size); if(!data.length)return <div className="empty-state">No records found.</div>; return <><div className="table-toolbar"><input className="search-input" placeholder="Search records…" value={query} onChange={(e)=>{setQuery(e.target.value);setPage(1)}}/><span>{filtered.length} records</span></div><div className="table-scroll"><table className="data-table"><thead><tr>{cols.map((c)=><th key={c}>{c.replaceAll("_"," ")}</th>)}</tr></thead><tbody>{visible.map((row,i)=><tr key={row?.id||i}>{cols.map((c)=><td key={c}>{formatValue(row?.[c])}</td>)}</tr>)}</tbody></table></div>{total>1&&<div className="pagination"><button className="secondary-button" disabled={safe===1} onClick={()=>setPage(Math.max(1,safe-1))}>Previous</button><span>Page {safe} of {total}</span><button className="secondary-button" disabled={safe===total} onClick={()=>setPage(Math.min(total,safe+1))}>Next</button></div>}</>}
function formatValue(v){if(v===null||v===undefined||v==="")return "—";if(typeof v==="boolean")return v?"Yes":"No";if(typeof v==="object")return JSON.stringify(v);return formatDisplayDate(v)}
function Record({title,path,refreshKey=0}){const [data,setData]=useState([]); const [error,setError]=useState(""); const [busy,setBusy]=useState(true); async function load(){setBusy(true);setError("");try{setData(await apiRequest(path))}catch(err){setData([]);setError(err.status===403?"This section is restricted for your current role.":err.message)}finally{setBusy(false)}} useEffect(()=>{load()},[path,refreshKey]); return <section className="panel"><div className="panel-header"><div><h2>{title}</h2></div><button className="secondary-button" onClick={load} disabled={busy}>{busy?"Refreshing…":"Refresh"}</button></div>{error&&<div className="warning-banner">{error}</div>}{!error&&(busy?<div className="skeleton-lines"/>:<DataTable rows={data}/>)}</section>}

function useSchema(){const [schema,setSchema]=useState(null);useEffect(()=>{getOpenApi().then(setSchema).catch(()=>{})},[]);return schema}
function Drawer({open,title,onClose,children}){if(!open)return null;return <div className="drawer-layer"><button className="drawer-backdrop" onClick={onClose}/><aside className="drawer"><div className="drawer-header"><div><span className="eyebrow">Action</span><h2>{title}</h2></div><button className="icon-button" onClick={onClose}>✕</button></div><div className="drawer-body">{children}</div></aside></div>}
function labelize(s){return s.replaceAll("_"," ").replace(/\b\w/g,(c)=>c.toUpperCase())}
function normalizeFieldSpec(spec = {}) {
  let current = spec || {};

  // Pydantic v2 represents Optional[T] as anyOf: [T, null].
  // The old generic form only checked spec.format directly, so optional
  // datetime fields were rendered as plain text inputs.
  if (Array.isArray(current.anyOf)) {
    const concrete = current.anyOf.find(
      (item) =>
        item &&
        item.type !== "null" &&
        (item.type || item.format || item.enum)
    );

    if (concrete) {
      current = {
        ...current,
        ...concrete,
        title: current.title || concrete.title,
      };
    }
  }

  return current;
}

function Field({name,spec,value,required,onChange}) {
  const fieldSpec = normalizeFieldSpec(spec);
  const title = fieldSpec.title || labelize(name);

  if (fieldSpec.enum) {
    return (
      <label>
        {title}{required ? " *" : ""}
        <select
          required={required}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Select...</option>
          {fieldSpec.enum.map((x) => (
            <option key={x} value={x}>
              {String(x).replaceAll("_", " ")}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (fieldSpec.type === "boolean") {
    return (
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>{title}</span>
      </label>
    );
  }

  if (fieldSpec.type === "array") {
    return (
      <label>
        {title}
        <textarea
          rows="3"
          value={Array.isArray(value) ? value.join(", ") : value || ""}
          onChange={(e) =>
            onChange(
              e.target.value
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean)
            )
          }
        />
      </label>
    );
  }

  const long = [
    "description",
    "reason",
    "note",
    "agenda",
    "address",
    "work_description",
  ].some((x) => name.toLowerCase().includes(x));

  if (long) {
    return (
      <label>
        {title}{required ? " *" : ""}
        <textarea
          rows="4"
          required={required}
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      </label>
    );
  }

  let type = "text";

  if (fieldSpec.format === "date") {
    type = "date";
  } else if (fieldSpec.format === "date-time") {
    type = "datetime-local";
  } else if (fieldSpec.format === "time") {
    type = "time";
  } else if (fieldSpec.format === "email") {
    type = "email";
  } else if (["integer", "number"].includes(fieldSpec.type)) {
    type = "number";
  } else if (name.toLowerCase().includes("password")) {
    type = "password";
  }

  return (
    <label>
      {title}{required ? " *" : ""}
      <DateField
        type={type}
        required={required}
        value={value ?? ""}
        step={
          fieldSpec.type === "number"
            ? "any"
            : type === "datetime-local"
              ? "60"
              : undefined
        }
        onChange={(e) => {
          const raw = e.target.value;

          onChange(
            fieldSpec.type === "integer"
              ? (raw === "" ? "" : parseInt(raw, 10))
              : fieldSpec.type === "number"
                ? (raw === "" ? "" : parseFloat(raw))
                : raw
          );
        }}
      />
    </label>
  );
}

async function uploadVendorDepositDocument(file, values, setProgress) {
  const contentType = file.type || "application/octet-stream";
  const pre = await apiRequest("/documents/presign-upload", {
    method: "POST",
    body: {
      owner_type: "VENDOR",
      owner_id: null,
      category: "VENDOR_DEPOSIT",
      title: `${values.code || "Vendor"} deposit supporting document`,
      description: values.deposit_reference
        ? `Deposit reference: ${values.deposit_reference}`
        : "Vendor deposit supporting document",
      file_name: file.name,
      content_type: contentType,
      file_size: file.size,
      issue_date: values.deposit_received_on || null,
      expiry_date: null,
      alert_days_before: 30,
      is_confidential: true,
      extra_data: {
        source: "vendor-deposit",
        vendor_code: values.code || null,
      },
    },
  });
  const etag = await uploadWithProgress(
    pre.upload_url,
    file,
    contentType,
    setProgress
  );
  await apiRequest(`/documents/${pre.document_id}/complete`, {
    method: "POST",
    body: { etag: etag ? etag.replaceAll('"', "") : null },
  });
  return pre.document_id;
}

function ActionForm({ schema, method, path, label, onSuccess }) {
  const op = getOperation(schema, method, path);
  const bodySchema = getRequestSchema(schema, op) || {};
  const props = bodySchema.properties || {};
  const req = bodySchema.required || [];
  const pathParams = (op?.parameters || []).filter((p) => p.in === "path");
  const isVendorCreate = method === "POST" && path === "/operations/vendors";
  const [values, setValues] = useState({});
  const [params, setParams] = useState({});
  const [depositFile, setDepositFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  if (!op) {
    return (
      <div className="warning-banner">
        This action is not available in the current backend.
      </div>
    );
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMsg("");
    setProgress(0);

    try {
      const final = path
        .split("?")[0]
        .replace(/\{([^}]+)\}/g, (_, n) => encodeURIComponent(params[n] || ""));
      const body = Object.fromEntries(
        Object.entries(values).filter(([, v]) => v !== "" && v !== undefined)
      );

      if (isVendorCreate && depositFile) {
        setMsg("Uploading vendor deposit document...");
        body.deposit_document_id = await uploadVendorDepositDocument(
          depositFile,
          values,
          setProgress
        );
      }

      const result = await apiRequest(final, {
        method,
        body: ["GET", "HEAD"].includes(method) ? undefined : body,
      });

      setMsg("Saved successfully.");
      setDepositFile(null);
      setProgress(0);
      window.dispatchEvent(new Event("action-alerts:refresh"));
      onSuccess?.(result);
    } catch (err) {
      setError(err.message || "Unable to save this record.");
      setMsg("");
    } finally {
      setBusy(false);
    }
  }

  const entries = Object.entries(props).filter(
    ([name]) => !(isVendorCreate && name === "deposit_document_id")
  );

  return (
    <form className="schema-form" onSubmit={submit}>
      {error && <div className="error-banner">{error}</div>}
      {msg && <div className="success-banner">{msg}</div>}
      {pathParams.map((p) => (
        <Field
          key={p.name}
          name={p.name}
          spec={resolveRef(schema, p.schema)}
          value={params[p.name] || ""}
          required={p.required !== false}
          onChange={(v) => setParams({ ...params, [p.name]: v })}
        />
      ))}
      {entries.map(([n, s]) => (
        <Field
          key={n}
          name={n}
          spec={resolveRef(schema, s)}
          value={values[n] ?? ""}
          required={req.includes(n)}
          onChange={(v) => setValues({ ...values, [n]: v })}
        />
      ))}
      {isVendorCreate && (
        <>
          <label className="file-drop">
            Deposit supporting document
            <input
              type="file"
              accept=".pdf,image/*"
              onChange={(e) => setDepositFile(e.target.files?.[0] || null)}
            />
            <span>
              {depositFile
                ? `${depositFile.name} · ${Math.round(depositFile.size / 1024)} KB`
                : "Upload receipt, challan, cheque copy, UPI proof or cash acknowledgement"}
            </span>
          </label>
          {progress > 0 && (
            <div className="progress-bar">
              <span style={{ width: `${progress}%` }} />
            </div>
          )}
        </>
      )}
      {!entries.length && !pathParams.length && (
        <p className="muted">No additional information is required.</p>
      )}
      <button className="primary-button" disabled={busy}>
        {busy ? "Saving..." : label}
      </button>
    </form>
  );
}

function ActionPage({
  title,
  subtitle,
  reads = [],
  actions = [],
  children,
  extraActions,
}) {
  const schema = useSchema();
  const [drawer, setDrawer] = useState(null);
  const [refresh, setRefresh] = useState(0);

  const available = actions.filter(
    ([, method, path]) =>
      getOperation(schema, method, path)
  );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <span className="eyebrow">
            Workspace
          </span>

          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
      </header>

      {(available.length > 0 || extraActions) && (
        <div className="action-strip">
          {available.map(
            ([label, method, path], index) => (
              <button
                className={
                  index === 0
                    ? "primary-button"
                    : "secondary-button"
                }
                key={label}
                onClick={() =>
                  setDrawer({
                    l: label,
                    m: method,
                    p: path,
                  })
                }
              >
                {label}
              </button>
            )
          )}

          {extraActions}
        </div>
      )}

      {reads.map(([label, path]) => path === "/operations/vendors" ? <VendorCatalogue key={path} refreshKey={refresh}/> : (
        <Record
          key={path}
          title={label}
          path={path}
          refreshKey={refresh}
        />
      ))}

      {children}

      <Drawer
        open={Boolean(drawer)}
        title={drawer?.l}
        onClose={() => setDrawer(null)}
      >
        {drawer && (
          <ActionForm
            schema={schema}
            method={drawer.m}
            path={drawer.p}
            label={drawer.l}
            onSuccess={() => {
              setRefresh((x) => x + 1);
              setDrawer(null);
            }}
          />
        )}
      </Drawer>
    </div>
  );
}
function Employees(){return <ActionPage title="Employees" subtitle="Manage employee profiles, roles, MD-approved password resets and employment status." reads={[["Employee directory","/employees"],["Departments","/master-data/departments"],["Roles","/master-data/roles"]]} actions={[["Add employee","POST","/employees"],["Assign roles","POST","/employees/{employee_id}/roles"],["Request password reset","POST","/security/password-reset-requests"],["Disable employee","POST","/employees/{employee_id}/disable"],["Enable employee","POST","/employees/{employee_id}/enable"]]}/>}
function Attendance(){return <ActionPage title="Attendance" subtitle="Check in, review history and monitor field attendance." reads={[["Today","/attendance/me/today"],["My attendance history","/attendance/me"],["Organization attendance","/attendance"],["Live field locations","/locations/live"]]} actions={[["Check in","POST","/attendance/check-in"],["Check out","POST","/attendance/check-out"],["Evaluate location","POST","/attendance/auto-evaluate"]]}/>}
function Tasks(){return <ActionPage title="Tasks & Field Visits" subtitle="Plan routine work, field visits and questionnaire-based reporting." reads={[["My assignments","/tasks/me/assignments"],["Task catalogue","/tasks"]]} actions={[["Create task","POST","/tasks"],["Assign task","POST","/tasks/{task_id}/assignments"],["Start assignment","POST","/tasks/assignments/{assignment_id}/start"],["Add progress","POST","/tasks/assignments/{assignment_id}/progress"],["Submit questionnaire","POST","/tasks/assignments/{assignment_id}/questionnaire"],["Complete assignment","POST","/tasks/assignments/{assignment_id}/complete"]]}/>}
function MyLeaveRequests() {
  const [rows, setRows] = useState([]);
  const [leaveTypes, setLeaveTypes] = useState({});
  const [busyId, setBusyId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    setLoading(true);
    setError("");

    try {
      const [requestResult, balanceResult] = await Promise.allSettled([
        apiRequest("/leave/requests/me"),
        apiRequest("/leave/balances/me"),
      ]);

      if (requestResult.status === "fulfilled") {
        setRows(Array.isArray(requestResult.value) ? requestResult.value : []);
      } else {
        throw requestResult.reason;
      }

      if (balanceResult.status === "fulfilled" && Array.isArray(balanceResult.value)) {
        const map = {};
        balanceResult.value.forEach((item) => {
          if (item?.leave_type_id) {
            map[item.leave_type_id] = {
              code: item.leave_type_code,
              name: item.leave_type_name,
            };
          }
        });
        setLeaveTypes(map);
      } else {
        setLeaveTypes({});
      }
    } catch (err) {
      setRows([]);
      setError(err?.message || "Unable to load your leave requests.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();

    function handleLeaveSubmitted() {
      load();
    }

    window.addEventListener(
      "leave:submitted",
      handleLeaveSubmitted
    );

    return () => {
      window.removeEventListener(
        "leave:submitted",
        handleLeaveSubmitted
      );
    };
  }, []);

  async function withdraw(row) {
    if (busyId || row.status !== "PENDING") return;

    const confirmed = window.confirm(
      `Withdraw your leave request from ${row.start_date} to ${row.end_date}?`
    );

    if (!confirmed) return;

    setBusyId(row.id);
    setError("");
    setSuccess("");

    try {
      await apiRequest(`/leave/requests/${row.id}/cancel`, {
        method: "POST",
      });

      setSuccess("Leave request withdrawn successfully.");
      window.dispatchEvent(new Event("action-alerts:refresh"));
      await load();
    } catch (err) {
      setError(err?.message || "Unable to withdraw the leave request.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>My Leave Requests</h2>
          <p>Track your applications and withdraw a request while it is still pending.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={load}
          disabled={loading || Boolean(busyId)}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {success && <div className="success-banner">✅ {success}</div>}
      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="skeleton-lines" />
      ) : rows.length === 0 ? (
        <div className="empty-state">No leave requests submitted yet.</div>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Leave Type</th>
                <th>From</th>
                <th>To</th>
                <th>Days</th>
                <th>Reason</th>
                <th>Status</th>
                <th>Decision Note</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const type = leaveTypes[row.leave_type_id] || {};
                return (
                  <tr key={row.id}>
                    <td>
                      <strong>{type.name || row.leave_type_name || "Leave"}</strong>
                      {(type.code || row.leave_type_code) && (
                        <div className="muted">{type.code || row.leave_type_code}</div>
                      )}
                    </td>
                    <td>{row.start_date || "—"}</td>
                    <td>{row.end_date || "—"}</td>
                    <td>{row.total_days ?? "—"}</td>
                    <td>{row.reason || "—"}</td>
                    <td><strong>{String(row.status || "—").replaceAll("_", " ")}</strong></td>
                    <td>{row.decision_note || "—"}</td>
                    <td>
                      {row.status === "PENDING" ? (
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={Boolean(busyId)}
                          onClick={() => withdraw(row)}
                        >
                          {busyId === row.id ? "Withdrawing…" : "Withdraw"}
                        </button>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function PendingLeaveReview({
  sectionRef,
  onCountChange,
}) {
  const [rows, setRows] = useState([]);
  const [busyId, setBusyId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    setLoading(true);
    setError("");

    try {
      const data = await apiRequest("/leave/requests/pending");
      const pendingRows =
  Array.isArray(data) ? data : [];

setRows(pendingRows);

onCountChange?.(
  pendingRows.length
);
    } catch (err) {
      onCountChange?.(0);
      setRows([]);
      setError(err?.message || "Unable to load pending leave requests.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function approve(row) {
    if (busyId) return;

    const note = window.prompt(
      `Approve leave for ${row.employee_code} - ${row.employee_name}?

Approval note (optional):`,
      ""
    );

    if (note === null) return;

    setBusyId(row.id);
    setError("");
    setSuccess("");

    try {
      await apiRequest(`/leave/requests/${row.id}/approve`, {
        method: "POST",
        body: { note: note || null },
      });

      setSuccess(
        `Leave approved successfully for ${row.employee_code} - ${row.employee_name}.`
      );
      window.dispatchEvent(new Event("action-alerts:refresh"));
      await load();
    } catch (err) {
      setError(err?.message || "Unable to approve the leave request.");
    } finally {
      setBusyId("");
    }
  }

  async function reject(row) {
    if (busyId) return;

    const reason = window.prompt(
      `Reject leave for ${row.employee_code} - ${row.employee_name}?

Enter reason:`
    );

    if (!reason?.trim()) return;

    setBusyId(row.id);
    setError("");
    setSuccess("");

    try {
      await apiRequest(`/leave/requests/${row.id}/reject`, {
        method: "POST",
        body: { note: reason.trim() },
      });

      setSuccess(
        `Leave rejected for ${row.employee_code} - ${row.employee_name}.`
      );
      window.dispatchEvent(new Event("action-alerts:refresh"));
      await load();
    } catch (err) {
      setError(err?.message || "Unable to reject the leave request.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section
  className="panel"
  ref={sectionRef}
>
      <div className="panel-header">
        <div>
          <span className="eyebrow">Approval Queue</span>
          <h2>Pending Leave Requests</h2>
          <p>Only the MD can approve or reject employee leave requests.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={load}
          disabled={loading || Boolean(busyId)}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {success && <div className="success-banner">✅ {success}</div>}
      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="skeleton-lines" />
      ) : rows.length === 0 ? (
        <div className="empty-state">No employees are waiting for leave approval.</div>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Leave Type</th>
                <th>From</th>
                <th>To</th>
                <th>Days</th>
                <th>Reason</th>
                <th>Applied</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.employee_code}</strong>
                    <div className="muted">{row.employee_name}</div>
                  </td>
                  <td>
                    <strong>{row.leave_type_name}</strong>
                    <div className="muted">{row.leave_type_code}</div>
                  </td>
                  <td>{formatDisplayDate(row.start_date)}</td>
                  <td>{formatDisplayDate(row.end_date)}</td>
                  <td>{row.total_days}</td>
                  <td>{row.reason || "—"}</td>
                  <td>
                    {row.created_at
                      ? new Date(row.created_at).toLocaleString("en-GB",dateOptions({},true))
                      : "—"}
                  </td>
                  <td>
                    <div className="action-strip">
                      <button
                        type="button"
                        className="primary-button"
                        disabled={Boolean(busyId)}
                        onClick={() => approve(row)}
                      >
                        {busyId === row.id ? "Processing…" : "Approve"}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        disabled={Boolean(busyId)}
                        onClick={() => reject(row)}
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function regularizationDate(value) {
  if (!value) return "—";

  const raw = String(value);
  const dateOnly = raw.includes("T")
    ? raw.split("T")[0]
    : raw;

  const parts = dateOnly.split("-");

  if (parts.length === 3) {
    return `${parts[2]}-${parts[1]}-${parts[0]}`;
  }

  return raw;
}

function regularizationTime(value) {
  if (!value) return "—";

  const raw = String(value);
  const match = raw.match(/T(\d{2}):(\d{2})/);

  if (match) {
    return `${match[1]}:${match[2]}`;
  }

  return raw;
}

function PendingRegularizationReview({
  sectionRef,
  onCountChange,
  targetId,
}) {
  const [rows, setRows] = useState([]);
  const [busyId, setBusyId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    setLoading(true);
    setError("");

    try {
      const data = await apiRequest(
        "/leave/regularizations/pending"
      );

      const pendingRows =
        Array.isArray(data) ? data : [];

      setRows(pendingRows);
      onCountChange?.(pendingRows.length);
    } catch (err) {
      setRows([]);
      onCountChange?.(0);
      setError(
        err?.message ||
        "Unable to load pending attendance regularizations."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!targetId || loading) return;

    window.setTimeout(() => {
      const element = document.getElementById(
        `regularization-${targetId}`
      );

      element?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 100);
  }, [targetId, loading, rows.length]);

  async function approve(row) {
    if (busyId) return;

    const note = window.prompt(
      `Approve attendance regularization for ${row.employee_code} - ${row.employee_name || ""}?\n\nDate: ${regularizationDate(row.attendance_date)}\nRequested in: ${regularizationTime(row.requested_check_in_at)}\nRequested out: ${regularizationTime(row.requested_check_out_at)}\n\nApproval note (optional):`,
      ""
    );

    if (note === null) return;

    setBusyId(row.id);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        `/leave/regularizations/${row.id}/approve`,
        {
          method: "POST",
          body: {
            note: note.trim() || null,
          },
        }
      );

      setSuccess(
        `Attendance regularization approved for ${row.employee_code}.`
      );

      await load();

      window.dispatchEvent(
        new Event("action-alerts:refresh")
      );
    } catch (err) {
      setError(
        err?.message ||
        "Unable to approve the attendance regularization."
      );
    } finally {
      setBusyId("");
    }
  }

  async function reject(row) {
    if (busyId) return;

    const reason = window.prompt(
      `Reject attendance regularization for ${row.employee_code} - ${row.employee_name || ""}?\n\nDate: ${regularizationDate(row.attendance_date)}\n\nEnter rejection reason:`
    );

    if (!reason?.trim()) return;

    setBusyId(row.id);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        `/leave/regularizations/${row.id}/reject`,
        {
          method: "POST",
          body: {
            note: reason.trim(),
          },
        }
      );

      setSuccess(
        `Attendance regularization rejected for ${row.employee_code}.`
      );

      await load();

      window.dispatchEvent(
        new Event("action-alerts:refresh")
      );
    } catch (err) {
      setError(
        err?.message ||
        "Unable to reject the attendance regularization."
      );
    } finally {
      setBusyId("");
    }
  }

  return (
    <section
      className="panel"
      ref={sectionRef}
    >
      <div className="panel-header">
        <div>
          <span className="eyebrow">
            Approval Queue
          </span>

          <h2>
            Attendance Regularizations
          </h2>

          <p>
            Review requested attendance corrections without
            handling employee or request UUIDs.
          </p>
        </div>

        <button
          type="button"
          className="secondary-button"
          onClick={load}
          disabled={loading || Boolean(busyId)}
        >
          {loading
            ? "Refreshing…"
            : "Refresh"}
        </button>
      </div>

      {success && (
        <div className="success-banner">
          ✅ {success}
        </div>
      )}

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {loading ? (
        <div className="skeleton-lines" />
      ) : rows.length === 0 ? (
        <div className="empty-state">
          No attendance regularizations are waiting for review.
        </div>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Attendance Date</th>
                <th>Requested In</th>
                <th>Requested Out</th>
                <th>Reason</th>
                <th>Submitted</th>
                <th>Decision</th>
              </tr>
            </thead>

            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  id={`regularization-${row.id}`}
                  style={
                    targetId === row.id
                      ? {
                          outline:
                            "2px solid rgba(37, 99, 235, 0.35)",
                          outlineOffset: "-2px",
                        }
                      : undefined
                  }
                >
                  <td>
                    <strong>
                      {row.employee_code || "—"}
                    </strong>

                    {row.employee_name && (
                      <div className="muted">
                        {row.employee_name}
                      </div>
                    )}
                  </td>

                  <td>
                    {regularizationDate(
                      row.attendance_date
                    )}
                  </td>

                  <td>
                    {regularizationTime(
                      row.requested_check_in_at
                    )}
                  </td>

                  <td>
                    {regularizationTime(
                      row.requested_check_out_at
                    )}
                  </td>

                  <td>
                    {row.reason || "—"}
                  </td>

                  <td>
                    {row.created_at
                      ? new Date(
                          row.created_at
                        ).toLocaleString("en-GB",dateOptions({},true))
                      : "—"}
                  </td>

                  <td>
                    <div className="action-strip">
                      <button
                        type="button"
                        className="primary-button"
                        disabled={Boolean(busyId)}
                        onClick={() => approve(row)}
                      >
                        {busyId === row.id
                          ? "Processing…"
                          : "Approve"}
                      </button>

                      <button
                        type="button"
                        className="secondary-button"
                        disabled={Boolean(busyId)}
                        onClick={() => reject(row)}
                      >
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}


function LeaveApplicationForm({
  open,
  onClose,
}) {
  const [balances, setBalances] = useState([]);
  const [form, setForm] = useState({
    leave_type_id: "",
    start_date: "",
    end_date: "",
    reason: "",
  });

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function loadLeaveTypes() {
    setLoading(true);
    setError("");

    try {
      const data = await apiRequest(
        "/leave/balances/me"
      );

      setBalances(
        Array.isArray(data)
          ? data
          : []
      );
    } catch (err) {
      setBalances([]);
      setError(
        err?.message ||
        "Unable to load leave types."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (open) {
      loadLeaveTypes();
    }
  }, [open]);

  const selectedBalance = balances.find(
    (item) =>
      item.leave_type_id ===
      form.leave_type_id
  );

  async function submit(event) {
    event.preventDefault();

    if (busy) return;

    if (!form.leave_type_id) {
      setError(
        "Please select a leave type."
      );
      return;
    }

    if (
      form.start_date &&
      form.end_date &&
      form.end_date < form.start_date
    ) {
      setError(
        "End date cannot be before start date."
      );
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        "/leave/requests",
        {
          method: "POST",
          body: {
            leave_type_id:
              form.leave_type_id,
            start_date:
              form.start_date,
            end_date:
              form.end_date,
            reason:
              form.reason.trim(),
            attachment_urls: [],
          },
        }
      );

      setSuccess(
        "Leave request submitted successfully."
      );

      setForm({
        leave_type_id: "",
        start_date: "",
        end_date: "",
        reason: "",
      });

      window.dispatchEvent(
        new Event("leave:submitted")
      );

      window.dispatchEvent(
        new Event("action-alerts:refresh")
      );

      await loadLeaveTypes();
    } catch (err) {
      const detail =
        err?.detail ??
        err?.message ??
        "Unable to submit leave request.";

      if (Array.isArray(detail)) {
        setError(
          detail
            .map((item) =>
              item?.msg ||
              "Invalid leave request."
            )
            .join(" ")
        );
      } else if (
        detail &&
        typeof detail === "object"
      ) {
        setError(
          detail?.detail ||
          "Unable to submit leave request."
        );
      } else {
        setError(String(detail));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Drawer
      open={open}
      title="Apply for Leave"
      onClose={() => {
        if (!busy) {
          onClose();
          setError("");
          setSuccess("");
        }
      }}
    >
      <div className="drawer-form-intro">
        <span className="eyebrow">
          Employee Self Service
        </span>

        <p className="muted">
          Select the leave type by name.
          Internal IDs stay hidden.
        </p>
      </div>

      {success && (
        <div className="success-banner">
          ✅ {success}
        </div>
      )}

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      <form
        className="schema-form"
        onSubmit={submit}
      >
        <label>
          Leave Type *

          <select
            required
            disabled={busy || loading}
            value={form.leave_type_id}
            onChange={(event) =>
              setForm({
                ...form,
                leave_type_id:
                  event.target.value,
              })
            }
          >
            <option value="">
              {loading
                ? "Loading leave types..."
                : "Select leave type"}
            </option>

            {balances.map((item) => (
              <option
                key={item.leave_type_id}
                value={item.leave_type_id}
              >
                {item.leave_type_name ||
                  item.leave_type_code ||
                  "Leave"}
                {item.leave_type_code
                  ? ` (${item.leave_type_code})`
                  : ""}
                {item.available_days !==
                  undefined
                  ? ` - ${item.available_days} day(s) available`
                  : ""}
              </option>
            ))}
          </select>
        </label>

        {selectedBalance && (
          <div className="success-banner">
            Available balance:{" "}
            <strong>
              {selectedBalance.available_days ??
                "—"}{" "}
              day(s)
            </strong>
          </div>
        )}

        <label>
          Start Date *

          <DateField
            type="date"
            required
            disabled={busy}
            value={form.start_date}
            onChange={(event) =>
              setForm({
                ...form,
                start_date:
                  event.target.value,
              })
            }
          />
        </label>

        <label>
          End Date *

          <DateField
            type="date"
            required
            disabled={busy}
            min={form.start_date || undefined}
            value={form.end_date}
            onChange={(event) =>
              setForm({
                ...form,
                end_date:
                  event.target.value,
              })
            }
          />
        </label>

        <label>
          Reason *

          <textarea
            rows="4"
            required
            minLength="3"
            disabled={busy}
            value={form.reason}
            placeholder="Enter the reason for leave."
            onChange={(event) =>
              setForm({
                ...form,
                reason:
                  event.target.value,
              })
            }
          />
        </label>

        <button
          type="submit"
          className="primary-button"
          disabled={
            busy ||
            loading ||
            !form.leave_type_id
          }
        >
          {busy
            ? "Submitting..."
            : "Submit Leave Request"}
        </button>
      </form>
    </Drawer>
  );
}


function Leave() {
  const { roles } = useAuth();
  const location = useLocation();

  const management = roles.some((role) =>
    MGMT.includes(role)
  );

  const isMD = roles.includes("MD");

  const [showLeaveForm, setShowLeaveForm] =
    useState(false);

  const pendingLeaveSectionRef = useRef(null);
  const regularizationSectionRef = useRef(null);

  const [pendingLeaveCount, setPendingLeaveCount] =
    useState(0);

  const [
    pendingRegularizationCount,
    setPendingRegularizationCount,
  ] = useState(0);

  const params = new URLSearchParams(
    location.search
  );

  const targetRegularizationId =
    params.get("regularization") || "";

  const employeeReads = [
    [
      "My balances",
      "/leave/balances/me",
    ],
    [
      "Holidays",
      "/leave/holidays",
    ],
    [
      "My regularizations",
      "/leave/regularizations/me",
    ],
  ];

  const managementReads = [
    [
      "My balances",
      "/leave/balances/me",
    ],
    [
      "Holidays",
      "/leave/holidays",
    ],
    [
      "My regularizations",
      "/leave/regularizations/me",
    ],
  ];

  const employeeActions = [
    [
      "Attendance regularization",
      "POST",
      "/leave/regularizations",
    ],
  ];

  const managementActions = [
    [
      "Attendance regularization",
      "POST",
      "/leave/regularizations",
    ],
    [
      "Add holiday",
      "POST",
      "/leave/holidays",
    ],
    [
      "Add leave type",
      "POST",
      "/leave/types",
    ],
  ];

  function jumpToPendingLeave() {
    pendingLeaveSectionRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  function jumpToRegularizations() {
    regularizationSectionRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  useEffect(() => {
    if (!management) return;

    const query = new URLSearchParams(
      location.search
    );

    const queue = query.get("queue");
    const regularizationId =
      query.get("regularization");
    const leaveRequestId =
      query.get("request");

    if (
      regularizationId ||
      queue === "regularizations"
    ) {
      window.setTimeout(
        jumpToRegularizations,
        150
      );
      return;
    }

    if (
      leaveRequestId ||
      queue === "leave"
    ) {
      window.setTimeout(
        jumpToPendingLeave,
        150
      );
      return;
    }

    if (queue === "1") {
      if (pendingRegularizationCount > 0) {
        window.setTimeout(
          jumpToRegularizations,
          150
        );
      } else if (pendingLeaveCount > 0) {
        window.setTimeout(
          jumpToPendingLeave,
          150
        );
      }
    }
  }, [
    location.search,
    management,
    pendingLeaveCount,
    pendingRegularizationCount,
  ]);

  return (
    <ActionPage
      title="Leave"
      subtitle="Balances, leave applications, holidays and attendance regularization."
      reads={
        management
          ? managementReads
          : employeeReads
      }
      actions={
        management
          ? managementActions
          : employeeActions
      }
      extraActions={
        <>
          {!management && (
            <button
              type="button"
              className="primary-button"
              onClick={() =>
                setShowLeaveForm(
                  (value) => !value
                )
              }
            >
              {showLeaveForm
                ? "Close Leave Form"
                : "Apply for Leave"}
            </button>
          )}

          {management && (
            <>
            <button
              type="button"
              className="primary-button"
              onClick={() =>
                setShowLeaveForm(
                  (value) => !value
                )
              }
            >
              {showLeaveForm
                ? "Close Leave Form"
                : "Apply for Leave"}
            </button>

            {isMD && (
            <button
              type="button"
              className="secondary-button pending-leave-button"
              onClick={jumpToPendingLeave}
            >
              Pending Leave Requests

              {pendingLeaveCount > 0 && (
                <span className="pending-leave-badge">
                  {pendingLeaveCount > 99
                    ? "99+"
                    : pendingLeaveCount}
                </span>
              )}
            </button>
            )}

            <button
              type="button"
              className="secondary-button pending-leave-button"
              onClick={jumpToRegularizations}
            >
              Attendance Regularizations

              {pendingRegularizationCount > 0 && (
                <span className="pending-leave-badge">
                  {pendingRegularizationCount > 99
                    ? "99+"
                    : pendingRegularizationCount}
                </span>
              )}
            </button>
            </>
          )}
        </>
      }
    >
      <LeaveApplicationForm
        open={showLeaveForm}
        onClose={() =>
          setShowLeaveForm(false)
        }
      />

      <MyLeaveRequests />

      {management && (
        <>
          {isMD && (
            <PendingLeaveReview
              sectionRef={pendingLeaveSectionRef}
              onCountChange={setPendingLeaveCount}
            />
          )}

          <PendingRegularizationReview
            sectionRef={regularizationSectionRef}
            onCountChange={
              setPendingRegularizationCount
            }
            targetId={targetRegularizationId}
          />
        </>
      )}
    </ActionPage>
  );
}

function Expenses(){return <ActionPage title="Expenses & TA/DA" subtitle="Submit travel expenses and manage verification, approval and payment." reads={[["My claims","/expenses/claims/me"],["Pending claims","/expenses/claims/pending"]]} actions={[["Create claim","POST","/expenses/claims"],["Submit claim","POST","/expenses/claims/{claim_id}/submit"],["Verify claim","POST","/expenses/claims/{claim_id}/verify"],["Approve claim","POST","/expenses/claims/{claim_id}/approve"],["Reject claim","POST","/expenses/claims/{claim_id}/reject"],["Mark paid","POST","/expenses/claims/{claim_id}/mark-paid"]]}/>}

function Documents(){const [form,setForm]=useState({owner_type:"GENERAL",owner_id:"",category:"GENERAL",title:"",description:"",issue_date:"",expiry_date:"",alert_days_before:30,is_confidential:false});const [file,setFile]=useState(null);const [progress,setProgress]=useState(0);const [status,setStatus]=useState("");const [error,setError]=useState("");const [refresh,setRefresh]=useState(0);async function upload(e){e.preventDefault();if(!file){setError("Choose a PDF or image first.");return}setError("");setStatus("Preparing upload…");try{const payload={...form,owner_id:form.owner_id||null,issue_date:form.issue_date||null,expiry_date:form.expiry_date||null,file_name:file.name,content_type:file.type||"application/octet-stream",file_size:file.size,extra_data:null};const pre=await apiRequest("/documents/presign-upload",{method:"POST",body:payload});setStatus("Uploading to secure storage…");const etag=await uploadWithProgress(pre.upload_url,file,payload.content_type,setProgress);await apiRequest(`/documents/${pre.document_id}/complete`,{method:"POST",body:{etag:etag?etag.replaceAll('"',""):null}});setStatus("Upload completed.");setProgress(100);setFile(null);setRefresh((x)=>x+1)}catch(err){setError(err.message);setStatus("")}} return <div className="page"><header className="page-header"><div><span className="eyebrow">Secure files</span><h1>Documents</h1><p>Upload private documents, track expiry dates and submit records for approval.</p></div></header><section className="panel"><div className="panel-header"><div><h2>Upload document</h2><p>Direct private S3 upload using a temporary secure URL.</p></div></div><form className="document-form" onSubmit={upload}>{error&&<div className="error-banner">{error}</div>}{status&&<div className="success-banner">{status}</div>}<div className="form-grid"><label>Owner type<select value={form.owner_type} onChange={(e)=>setForm({...form,owner_type:e.target.value})}>{["GENERAL","EMPLOYEE","VEHICLE","PROPERTY","OUTLET","EXPENSE","MD_REFERENCE"].map((v)=><option key={v}>{v}</option>)}</select></label><label>Owner ID<input value={form.owner_id} placeholder="Optional UUID" onChange={(e)=>setForm({...form,owner_id:e.target.value})}/></label><label>Category<input value={form.category} onChange={(e)=>setForm({...form,category:e.target.value.toUpperCase()})}/></label><label>Title<input required value={form.title} onChange={(e)=>setForm({...form,title:e.target.value})}/></label><label>Issue date<DateField type="date" value={form.issue_date} onChange={(e)=>setForm({...form,issue_date:e.target.value})}/></label><label>Expiry date<DateField type="date" value={form.expiry_date} onChange={(e)=>setForm({...form,expiry_date:e.target.value})}/></label></div><label>Description<textarea rows="3" value={form.description} onChange={(e)=>setForm({...form,description:e.target.value})}/></label><label className="file-drop">Choose PDF or image<input type="file" accept=".pdf,image/*" onChange={(e)=>setFile(e.target.files?.[0]||null)}/><span>{file?`${file.name} · ${Math.round(file.size/1024)} KB`:"Select a file from your computer"}</span></label>{progress>0&&<div className="progress-bar"><span style={{width:`${progress}%`}}/></div>}<button className="primary-button">Upload document</button></form></section><Record title="Document library" path="/documents" refreshKey={refresh}/><Record title="Expiring documents" path="/documents?expiring_only=true" refreshKey={refresh}/></div>}

function Notifications(){return <NotificationInbox/>}
function Profile(){const {user,roles}=useAuth();const [form,setForm]=useState({current_password:"",new_password:""});const [msg,setMsg]=useState("");const [error,setError]=useState("");async function submit(e){e.preventDefault();setMsg("");setError("");try{await apiRequest("/auth/change-password",{method:"POST",body:form});setMsg("Password changed successfully.");setForm({current_password:"",new_password:""})}catch(err){setError(err.message)}}return <div className="page"><header className="page-header"><div><span className="eyebrow">Account</span><h1>My profile</h1><p>Account information and password security.</p></div></header><div className="two-column"><section className="panel"><h2>Account</h2><pre className="profile-data">{JSON.stringify({...user,roles},null,2)}</pre></section><section className="panel"><h2>Change password</h2><form className="schema-form" onSubmit={submit}>{error&&<div className="error-banner">{error}</div>}{msg&&<div className="success-banner">{msg}</div>}<label>Current password<input type="password" required value={form.current_password} onChange={(e)=>setForm({...form,current_password:e.target.value})}/></label><label>New password<input type="password" required minLength="8" value={form.new_password} onChange={(e)=>setForm({...form,new_password:e.target.value})}/></label><button className="primary-button">Change password</button></form></section></div></div>}

function Module(){const {moduleId}=useParams();if(moduleId==="financial-records")return <FinancialRecordsWorkspace/>;if(moduleId==="cashbook")return <CashbookWorkspace/>;if(moduleId==="box-loading")return <BoxLoadingWorkspace/>;if(moduleId==="shop-rentals")return <ShopRentalsWorkspace/>;if(moduleId==="security")return <SecurityWorkspace/>;if(moduleId==="overtime")return <OvertimeWorkspace/>;if(moduleId==="md-overview")return <MdDailyOverview/>;if(moduleId==="sheet-verification")return <AccountsSheetWorkspace/>;if(moduleId==="vendor-access")return <VendorAccountsWorkspace/>; if(moduleId==="appointments")return <AppointmentWorkspace/>; if(moduleId==="assets")return <AssetWorkspace/>; if(moduleId==="payroll") return <PayrollWorkspace/>; if(moduleId==="expenses") return <ExpensesWorkspace/>; if(moduleId==="fuel")return <FuelWorkspace/>; if(moduleId === "maintenance-bills") 
  return <MaintenanceBillsWorkspace />; if(moduleId==="approvals")return <ApprovalWorkspace/>; if(moduleId==="employees")return <EmployeeWorkspace/>;if(moduleId==="attendance")return <AttendanceWorkspace/>;if(moduleId==="tasks")return <TasksWorkspace/>;;if(moduleId==="inspections")return <InspectionWorkspace/>;if(moduleId==="leave")return <Leave/>;if(moduleId==="expenses")return <Expenses/>;if(moduleId==="documents")return <Documents/>;if(moduleId==="notifications")return <Notifications/>;if(moduleId==="outlets")return <OutletsWorkspace/>;const cfg=generic[moduleId];return cfg?<ActionPage {...cfg}/>:<div className="page"><div className="empty-state">Module configuration not found.</div></div>}

export default function App(){return <Routes><Route path="/vendor-login" element={<VendorPortal/>}/><Route path="/vendor" element={<VendorPortal/>}/><Route path="/login" element={<Login/>}/><Route path="/vendor-inspection/:token" element={<VendorInspectionReview/>}/><Route element={<Protected/>}><Route element={<Shell/>}><Route index element={<Navigate to="/dashboard" replace/>}/><Route path="/dashboard" element={<Dashboard/>}/><Route path="/profile" element={<Profile/>}/><Route path="/module/:moduleId" element={<Module/>}/></Route></Route><Route path="*" element={<Navigate to="/dashboard" replace/>}/></Routes>}

// financial-records-update-v1

// navigation-codes-update-v1

// attendance-notifications-cleanup-v1

// dashboard-catalogue-count-v1
// date-display-ddmmyyyy-v1
