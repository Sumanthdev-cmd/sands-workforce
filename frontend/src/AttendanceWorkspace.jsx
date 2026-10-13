import {isNativeWorkday,openNativeWorkday} from "./lib/nativeWorkday";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";
import {useAuth} from "./context/AuthContext";
import {apiRequest} from "./lib/api";
import {pushCurrentEmployeeLocation,submitEmployeePosition} from "./lib/location";
import LocationSetup from "./LocationSetup";

const isoDate=(date)=>date.toISOString().slice(0,10);
const today=()=>isoDate(new Date());
const monthAgo=()=>{const date=new Date();date.setDate(date.getDate()-30);return isoDate(date)};
const displayTime=(value)=>value?new Date(value).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}):"—";
const displayDate=(value)=>value?new Date(`${value}T00:00:00`).toLocaleDateString():"—";
const duration=(minutes)=>`${Math.floor((minutes||0)/60)}h ${(minutes||0)%60}m`;
const statusClass=(value)=>String(value||"absent").toLowerCase().replaceAll("_","-");
const errorText=(error)=>{
  const value=error?.data?.detail??error?.detail??error?.message??error;
  if(typeof value==="string")return value;
  if(Array.isArray(value))return value.map(item=>item?.msg||"Invalid information.").join(" ");
  if(value&&typeof value==="object")return value.message||value.detail||"The request could not be completed.";
  return "The request could not be completed.";
};

function StatusPill({value}){return <span className={`attendance-pill ${statusClass(value)}`}>{String(value||"No record").replaceAll("_"," ")}</span>}
function Initials({name}){return <span className="attendance-avatar">{String(name||"?").split(/\s+/).slice(0,2).map((part)=>part[0]).join("").toUpperCase()}</span>}
function signal(recordedAt){if(!recordedAt)return {label:"No signal",className:"offline"};const age=(Date.now()-new Date(recordedAt).getTime())/60000;if(age<=5)return {label:"Live",className:"live"};if(age<=60)return {label:"Stale",className:"stale"};return {label:"Offline",className:"offline"}}

let leafletPromise;
function loadLeaflet(){
  if(window.L)return Promise.resolve(window.L);
  if(leafletPromise)return leafletPromise;
  leafletPromise=new Promise((resolve,reject)=>{
    if(!document.querySelector('link[data-sands-leaflet]')){
      const css=document.createElement("link");
      css.rel="stylesheet";
      css.href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      css.dataset.sandsLeaflet="true";
      document.head.appendChild(css);
    }
    const old=document.querySelector('script[data-sands-leaflet]');
    if(old){
      old.addEventListener("load",()=>resolve(window.L),{once:true});
      old.addEventListener("error",()=>reject(new Error("Map library could not be loaded.")),{once:true});
      return;
    }
    const script=document.createElement("script");
    script.src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.dataset.sandsLeaflet="true";
    script.onload=()=>resolve(window.L);
    script.onerror=()=>reject(new Error("Map library could not be loaded."));
    document.head.appendChild(script);
  });
  return leafletPromise;
}

export default function AttendanceWorkspace(){
  const {roles=[]}=useAuth();
  const canMonitor=roles.some((role)=>["ADMIN","MD","GM"].includes(role));
  const isAdmin=roles.includes("ADMIN");
  const [todayRecord,setTodayRecord]=useState(null);
  const [mine,setMine]=useState([]);
  const [organization,setOrganization]=useState([]);
  const [locations,setLocations]=useState([]);
  const [employees,setEmployees]=useState([]);
  const [vendorAttendance,setVendorAttendance]=useState([]);
  const [vendorRoster,setVendorRoster]=useState([]);
  const [geofences,setGeofences]=useState([]);
  const [dayState,setDayState]=useState(null);
  const [policy,setPolicy]=useState(null);
  const [lunchMinutes,setLunchMinutes]=useState("30");
  const [dutyApprovals,setDutyApprovals]=useState([]);
  const [tab,setTab]=useState("overview");
  const [range,setRange]=useState({start_date:monthAgo(),end_date:today()});
  const [search,setSearch]=useState("");
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const [tracking,setTracking]=useState(()=>localStorage.getItem("sands_duty_tracking")==="true");
  const [gps,setGps]=useState({status:"off",lastAt:null,accuracy:null});
  const lastPushRef=useRef(0);
  const latestPositionRef=useRef(null);

  const load=useCallback(async()=>{
    setLoading(true);
    setError("");
    const query=`?start_date=${range.start_date}&end_date=${range.end_date}`;
    const jobs={
      today:apiRequest("/attendance/me/today"),
      mine:apiRequest(`/attendance/me${query}`),
      day:apiRequest("/workforce-policy/me/day"),
      policy:apiRequest("/workforce-policy/settings"),
    };
    if(canMonitor){
      jobs.organization=apiRequest(`/attendance${query}`);
      jobs.roster=apiRequest("/locations/roster");
      jobs.vendors=apiRequest(`/vendor-portal/admin/attendance${query}`);
      jobs.vendorRoster=apiRequest("/payroll/vendors");
      jobs.geofences=apiRequest("/geofences");
    }
    if(isAdmin)jobs.approvals=apiRequest("/workforce-policy/duty-exits?status=PENDING");

    const entries=Object.entries(jobs);
    const results=await Promise.allSettled(entries.map(([,promise])=>promise));
    results.forEach((result,index)=>{
      const key=entries[index][0];
      if(result.status!=="fulfilled")return;
      const value=result.value;
      if(key==="today")setTodayRecord(value||null);
      if(key==="mine")setMine(Array.isArray(value)?value:[]);
      if(key==="day")setDayState(value||null);
      if(key==="policy"){setPolicy(value||null);setLunchMinutes(String(value?.lunch_break_minutes??30))}
      if(key==="organization")setOrganization(Array.isArray(value)?value:[]);
      if(key==="roster"){const roster=Array.isArray(value)?value:[];setEmployees(roster);setLocations(roster.filter(item=>item.latitude!=null&&item.longitude!=null))}
      if(key==="vendors")setVendorAttendance(Array.isArray(value)?value:[]);
      if(key==="vendorRoster")setVendorRoster(Array.isArray(value)?value:[]);
      if(key==="geofences")setGeofences(Array.isArray(value)?value:[]);
      if(key==="approvals")setDutyApprovals(Array.isArray(value)?value:[]);
    });
    const failed=results.find((result)=>result.status==="rejected"&&result.reason?.status!==404);
    if(failed)setError(errorText(failed.reason));
    setLoading(false);
  },[canMonitor,isAdmin,range.start_date,range.end_date]);

  useEffect(()=>{load()},[load]);
  useEffect(()=>{if(!canMonitor||tab!=="locations")return;const id=setInterval(load,60000);return()=>clearInterval(id)},[canMonitor,tab,load]);
  useEffect(()=>{
    if(isNativeWorkday()||!tracking)return;
    if(!navigator.geolocation){setGps({status:"error",message:"Browser GPS is unavailable."});return}
    localStorage.setItem("sands_duty_tracking","true");
    setGps(old=>({...old,status:"waiting"}));
    const watchId=navigator.geolocation.watchPosition(async position=>{
      latestPositionRef.current=position;
      setGps({status:"live",lastAt:new Date().toISOString(),accuracy:position.coords.accuracy});
      if(Date.now()-lastPushRef.current<60000)return;
      lastPushRef.current=Date.now();
      try{await submitEmployeePosition(position)}catch(err){setGps({status:"error",message:errorText(err),lastAt:new Date().toISOString(),accuracy:position.coords.accuracy})}
    },err=>setGps({status:"error",message:err.code===1?"Location permission denied.":"GPS signal unavailable."}),{enableHighAccuracy:true,timeout:20000,maximumAge:15000});
    return()=>navigator.geolocation.clearWatch(watchId);
  },[tracking]);

  function stopTracking(){setTracking(false);latestPositionRef.current=null;localStorage.removeItem("sands_duty_tracking");setGps({status:"off",lastAt:null,accuracy:null})}

  async function pushAttendanceLocation(){
    const trackedPosition=latestPositionRef.current;
    const trackedAt=Number(trackedPosition?.timestamp||0);
    const trackedAge=Date.now()-trackedAt;
    if(trackedPosition&&trackedAge>=0&&trackedAge<=60000){
      return pushCurrentEmployeeLocation(trackedPosition);
    }
    return pushCurrentEmployeeLocation();
  }

  async function runAction(path,{body,method="POST",gpsRequired=false,success}={}){
    if(busy)return null;
    setBusy(true);setError("");setMessage("");
    try{
      if(gpsRequired)await pushAttendanceLocation();
      const data=await apiRequest(path,{method,...(body===undefined?{}:{body})});
      setMessage(data?.message||success||"Action completed successfully.");
      window.dispatchEvent(new Event("action-alerts:refresh"));
      await load();
      return data;
    }catch(err){setError(errorText(err));return null}
    finally{setBusy(false)}
  }

  function attendanceAction(path,label){
    if(openNativeWorkday())return;
    return runAction(path,{
      gpsRequired:true,
      body:path.includes("auto-evaluate")?undefined:{automatic:false},
      success:`${label} completed successfully.`,
    });
  }

  async function requestDutyExit(){
    const reason=window.prompt("Reason for leaving the geofence while remaining on duty:","");
    if(reason===null)return;
    if(reason.trim().length<5){setError("Enter a clear reason of at least 5 characters.");return}
    await runAction("/workforce-policy/duty-exits",{body:{reason:reason.trim()},success:"Request sent to ADMIN for approval."});
  }

  async function decideDutyExit(request,approved){
    const promptText=approved?"Approval note (optional):":"Reason for rejecting this request:";
    const note=window.prompt(promptText,"");
    if(note===null)return;
    if(!approved&&note.trim().length<3){setError("Enter a rejection reason of at least 3 characters.");return}
    await runAction(`/workforce-policy/duty-exits/${request.id}/decision`,{
      body:{approved,note:note.trim()||null},
      success:`Duty exit ${approved?"approved":"rejected"}.`,
    });
  }

  async function saveLunchPolicy(event){
    event.preventDefault();
    const value=Number(lunchMinutes);
    if(!Number.isInteger(value)||value<1||value>240){setError("Lunch duration must be a whole number from 1 to 240 minutes.");return}
    await runAction("/workforce-policy/settings",{method:"PUT",body:{lunch_break_minutes:value},success:"Organization lunch policy updated."});
  }

  const dutyExit=dayState?.duty_exit;
  const lunch=dayState?.lunch_break;
  const onDuty=Boolean(todayRecord?.check_in_at&&!todayRecord?.check_out_at);
  const lunchActive=lunch?.status==="ACTIVE";
  const dutyOutside=dutyExit?.status==="OUTSIDE";
  const selectedRangeLabel=range.start_date===range.end_date?displayDate(range.start_date):`${displayDate(range.start_date)} - ${displayDate(range.end_date)}`;
  const vendorOrgRows=useMemo(()=>{
    const rows=vendorAttendance.map((row)=>({
      ...row,
      id:`vendor-${row.id}`,
      person_type:"VENDOR",
      employee_id:`vendor-${row.vendor_id}-${row.outlet_id}`,
      employee_code:row.vendor_code,
      employee_name:row.vendor_name,
      outlet_label:row.outlet_name||row.outlet_code,
      has_record:true,
    }));
    const recordedKeys=new Set(rows.map(row=>`${row.vendor_id}:${row.outlet_id}`));
    vendorRoster.forEach(vendor=>{
      (vendor.outlets||[]).forEach(outlet=>{
        const key=`${vendor.id}:${outlet.id}`;
        if(recordedKeys.has(key))return;
        rows.push({
          id:`vendor-no-record-${vendor.id}-${outlet.id}`,
          person_type:"VENDOR",
          employee_id:`vendor-${vendor.id}-${outlet.id}`,
          employee_code:vendor.code,
          employee_name:vendor.name,
          vendor_id:vendor.id,
          outlet_id:outlet.id,
          outlet_code:outlet.code,
          outlet_name:outlet.name,
          outlet_label:outlet.name||outlet.code,
          attendance_date:null,
          attendance_date_label:selectedRangeLabel,
          status:"NO_RECORD",
          check_in_at:null,
          check_out_at:null,
          worked_minutes:0,
          late_minutes:0,
          has_record:false,
        });
      });
    });
    return rows;
  },[vendorAttendance,vendorRoster,selectedRangeLabel]);
  const teamRows=useMemo(()=>[
    ...organization.map(row=>({...row,person_type:"EMPLOYEE",attendance_date_label:row.has_record===false?selectedRangeLabel:null})),
    ...vendorOrgRows,
  ].filter((row)=>{
    if(row.has_record===false||!row.attendance_date)return true;
    return row.attendance_date>=range.start_date&&row.attendance_date<=range.end_date;
  }),[organization,vendorOrgRows,range.start_date,range.end_date]);
  const filtered=useMemo(()=>teamRows.filter((row)=>`${row.employee_code} ${row.employee_name} ${row.outlet_label||""} ${row.status} ${row.person_type}`.toLowerCase().includes(search.toLowerCase())),[teamRows,search]);
  const stats=useMemo(()=>({employees:new Set(teamRows.map((row)=>row.employee_id)).size,present:new Set(teamRows.filter((row)=>["PRESENT","LATE","HALF_DAY","CHECKED_OUT"].includes(String(row.status).toUpperCase())).map((row)=>row.employee_id)).size,late:teamRows.filter((row)=>Number(row.late_minutes)>0||String(row.status).toUpperCase()==="LATE").length,hours:Math.round(teamRows.reduce((sum,row)=>sum+Number(row.worked_minutes||0),0)/60)}),[teamRows]);
  const employeeLocations=useMemo(()=>employees.map(employee=>({...employee,id:employee.employee_id,full_name:employee.employee_name,location:employee.latitude==null?null:employee})),[employees]);
  const vendorMapCount=vendorAttendance.filter(item=>item.check_in_latitude).length;

  return <div className="page attendance-workspace">
    <header className="page-header attendance-heading">
      <div><span className="eyebrow">Time & field visibility</span><h1>Attendance Workspace</h1><p>GPS attendance, approved duty exits, paid lunch and live team visibility.</p></div>
      <button className="secondary-button" onClick={load} disabled={loading||busy}>↻ Refresh</button>
    </header>
    {error&&<div className="error-banner">{String(error)}</div>}
    {message&&<div className="success-banner">{message}</div>}

    <section className="attendance-hero">
      <div>
        <span className="attendance-date">{new Date().toLocaleDateString([],{weekday:"long",day:"numeric",month:"long"})}</span>
        <h2>{todayRecord?.check_in_at?"You’re checked in":"Ready to start your day?"}</h2>
        <p>{todayRecord?.check_in_at?`Check-in recorded at ${displayTime(todayRecord.check_in_at)}.`:"Enable GPS and check in from your assigned work location."}</p>
      </div>
      <div className="attendance-actions">
        {!tracking?<button className="gps-button" onClick={()=>{if(!openNativeWorkday())setTracking(true)}}>⌖ Enable GPS tracking</button>:<button className="gps-button active" onClick={stopTracking}>● Tracking active</button>}
        <button className="primary-button" disabled={busy||Boolean(todayRecord?.check_in_at)} onClick={()=>attendanceAction("/attendance/check-in","Check-in")}>● Check in</button>
        <button className="secondary-button" disabled={busy||!onDuty||lunchActive||dutyOutside} onClick={()=>attendanceAction("/attendance/check-out","Check-out")}>Check out</button>
        <button className="secondary-button" disabled={busy} onClick={()=>attendanceAction("/attendance/auto-evaluate","Location evaluation")}>Evaluate location</button>
      </div>
      <div className="attendance-actions policy-actions">
        {onDuty&&!lunch&&!dutyOutside&&<button className="secondary-button" disabled={busy} onClick={()=>runAction("/workforce-policy/lunch/start",{success:`Paid lunch started. Limit: ${policy?.lunch_break_minutes||30} minutes.`})}>Start lunch</button>}
        {lunchActive&&<button className="primary-button" disabled={busy} onClick={()=>runAction("/workforce-policy/lunch/end",{success:"Lunch break ended."})}>End lunch</button>}
        {onDuty&&(!dutyExit||["REJECTED","RETURNED","CANCELLED"].includes(dutyExit.status))&&!lunchActive&&<button className="secondary-button" disabled={busy} onClick={requestDutyExit}>Request duty exit</button>}
        {dutyExit?.status==="APPROVED"&&<button className="primary-button" disabled={busy} onClick={()=>runAction(`/workforce-policy/duty-exits/${dutyExit.id}/start`,{gpsRequired:true,success:"Approved on-duty exit started."})}>Start approved exit</button>}
        {dutyOutside&&<button className="primary-button" disabled={busy} onClick={()=>runAction(`/workforce-policy/duty-exits/${dutyExit.id}/return`,{gpsRequired:true,success:"Return to geofence recorded."})}>Record return</button>}
      </div>
      {(lunch||dutyExit)&&<div className="attendance-policy-status">
        {lunch&&<span>Lunch: <strong>{lunch.status.replaceAll("_"," ")}</strong> · {lunch.allowed_minutes} min allowed{lunch.exceeded_minutes>0?` · ${lunch.exceeded_minutes} min over`:""}</span>}
        {dutyExit&&<span>Duty exit: <strong>{dutyExit.status.replaceAll("_"," ")}</strong> · {dutyExit.reason}</span>}
      </div>}
      <div className="gps-status">GPS: <strong>{gps.status}</strong>{gps.accuracy!=null&&` · accuracy ${Math.round(gps.accuracy)} m`}{gps.message&&` · ${gps.message}`}</div>
      <div className="attendance-today-grid"><div><small>Status</small><StatusPill value={todayRecord?.status}/></div><div><small>Check in</small><strong>{displayTime(todayRecord?.check_in_at)}</strong></div><div><small>Check out</small><strong>{displayTime(todayRecord?.check_out_at)}</strong></div><div><small>Worked</small><strong>{duration(todayRecord?.worked_minutes)}</strong></div><div><small>Late</small><strong>{todayRecord?.late_minutes||0} min</strong></div></div>
    </section>

    <nav className="attendance-tabs">
      <button className={tab==="overview"?"active":""} onClick={()=>setTab("overview")}>My history</button>
      {canMonitor&&<button className={tab==="team"?"active":""} onClick={()=>setTab("team")}>Organization</button>}
      {canMonitor&&<button className={tab==="locations"?"active":""} onClick={()=>setTab("locations")}>Live map <span>{locations.length+vendorMapCount}</span></button>}
      {isAdmin&&<button className={tab==="policies"?"active":""} onClick={()=>setTab("policies")}>Policies & approvals <span>{dutyApprovals.length}</span></button>}
      {isAdmin&&<button className={tab==="setup"?"active":""} onClick={()=>setTab("setup")}>Work locations</button>}
    </nav>

    {!["locations","setup","policies"].includes(tab)&&<div className="attendance-filters"><label>From<input type="date" value={range.start_date} max={range.end_date} onChange={(e)=>setRange({...range,start_date:e.target.value})}/></label><label>To<input type="date" value={range.end_date} min={range.start_date} onChange={(e)=>setRange({...range,end_date:e.target.value})}/></label>{tab==="team"&&<label className="attendance-search">Search<input placeholder="Name, code or status" value={search} onChange={(e)=>setSearch(e.target.value)}/></label>}</div>}

    {loading?<div className="empty-state">Loading attendance…</div>
      :tab==="overview"?<AttendanceTable rows={mine}/>
      :tab==="team"?<><div className="attendance-summary"><Metric label="People" value={stats.employees}/><Metric label="Present / checked out" value={stats.present}/><Metric label="Late" value={stats.late}/><Metric label="Total hours" value={stats.hours}/></div><AttendanceTable rows={filtered} showEmployee/></>
      :tab==="setup"?<LocationSetup employees={employees} geofences={geofences} onRefresh={load}/>
      :tab==="policies"?<PolicyPanel policy={policy} lunchMinutes={lunchMinutes} setLunchMinutes={setLunchMinutes} approvals={dutyApprovals} busy={busy} onSave={saveLunchPolicy} onDecision={decideDutyExit}/>
      :<LiveMap employees={employeeLocations} vendors={vendorAttendance}/>}
  </div>;
}

function PolicyPanel({policy,lunchMinutes,setLunchMinutes,approvals,busy,onSave,onDecision}){
  return <div className="attendance-policy-grid">
    <section className="panel">
      <div className="panel-header"><div><span className="eyebrow">Organization rule</span><h2>Paid lunch duration</h2><p>The same limit applies to all employees. An overrun alerts the employee and their manager.</p></div></div>
      <form className="document-form" onSubmit={onSave}>
        <label>Allowed minutes<input required type="number" min="1" max="240" step="1" value={lunchMinutes} disabled={busy} onChange={(event)=>setLunchMinutes(event.target.value)}/></label>
        <div className="success-banner">Lunch remains paid work time. Current limit: {policy?.lunch_break_minutes||30} minutes.</div>
        <button className="primary-button" disabled={busy}>Save lunch policy</button>
      </form>
    </section>
    <section className="panel">
      <div className="panel-header"><div><span className="eyebrow">ADMIN approval</span><h2>On-duty geofence exits</h2><p>Employees remain checked in outside the geofence only after approval.</p></div><span className="pending-leave-badge">{approvals.length}</span></div>
      <div className="simple-list">
        {approvals.length===0?<div className="empty-state">No duty-exit requests are waiting.</div>:approvals.map(item=><article className="subpanel" key={item.id}>
          <div className="panel-header"><div><strong>{item.employee_code} — {item.employee_name}</strong><p>{new Date(item.requested_at).toLocaleString()}</p></div><StatusPill value={item.status}/></div>
          <p>{item.reason}</p>
          <div className="action-strip"><button className="primary-button" disabled={busy} onClick={()=>onDecision(item,true)}>Approve</button><button className="secondary-button danger" disabled={busy} onClick={()=>onDecision(item,false)}>Reject</button></div>
        </article>)}
      </div>
    </section>
  </div>;
}

function Metric({label,value}){return <div><small>{label}</small><strong>{value}</strong></div>}
function AttendanceTable({rows,showEmployee=false}){return <section className="panel attendance-table-panel"><div className="attendance-table"><div className="attendance-row attendance-table-head">{showEmployee&&<span>Person</span>}<span>Date</span><span>Status</span><span>Check in</span><span>Check out</span><span>Worked</span><span>Late</span></div>{rows.length===0?<div className="empty-state">No attendance records in this date range.</div>:rows.map((row)=><div className="attendance-row" key={row.id||`${row.employee_id}-${row.attendance_date}-no-record`}>{showEmployee&&<span className="attendance-person"><Initials name={row.employee_name}/><span><strong>{row.employee_name}</strong><small>{row.employee_code}{row.person_type==="VENDOR"?" · Vendor":" · Employee"}{row.outlet_label?` · ${row.outlet_label}`:""}</small></span></span>}<span data-label="Date">{row.attendance_date_label||displayDate(row.attendance_date)}</span><span data-label="Status"><StatusPill value={row.status}/></span><span data-label="Check in">{displayTime(row.check_in_at)}</span><span data-label="Check out">{displayTime(row.check_out_at)}</span><span data-label="Worked">{duration(row.worked_minutes)}</span><span data-label="Late">{row.late_minutes||0} min</span></div>)}</div></section>}

function LeafletMap({points}){
  const nodeRef=useRef(null);
  useEffect(()=>{
    let cancelled=false;
    let map;
    loadLeaflet().then(L=>{
      if(cancelled||!nodeRef.current)return;
      map=L.map(nodeRef.current).setView([20.5937,78.9629],5);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"&copy; OpenStreetMap contributors"}).addTo(map);
      points.forEach(point=>{
        const state=signal(point.recorded_at);
        const color=state.className==="live"?"#079455":state.className==="stale"?"#d97706":"#64748b";
        const safe=value=>String(value||"").replace(/[<>&]/g,"");
        L.circleMarker([point.latitude,point.longitude],{radius:10,color,fillColor:color,fillOpacity:.9}).addTo(map).bindPopup(`<strong>${safe(point.name)}</strong><br>${safe(point.code)} · ${safe(point.type)}<br>Last update: ${new Date(point.recorded_at).toLocaleString()}`);
      });
      if(points.length)map.fitBounds(points.map(point=>[point.latitude,point.longitude]),{padding:[35,35],maxZoom:16});
    }).catch(()=>{});
    return()=>{cancelled=true;if(map)map.remove()};
  },[points]);
  return <div ref={nodeRef} className="attendance-leaflet"/>;
}

function LiveMap({employees,vendors}){
  const employeePoints=employees.filter(item=>item.location).map(item=>({...item.location,name:item.full_name,code:item.employee_code,type:"Employee"}));
  const vendorPoints=vendors.filter(item=>item.check_in_latitude).map(item=>({latitude:item.check_in_latitude,longitude:item.check_in_longitude,recorded_at:item.check_in_at,name:item.vendor_name,code:item.vendor_code,type:`Vendor · ${item.outlet_code}`}));
  const points=[...employeePoints,...vendorPoints];
  return <div className="attendance-map-layout"><section className="attendance-map"><LeafletMap points={points}/></section><aside className="attendance-map-list"><h3>Location status</h3><p>{employees.length} employee(s) · {vendorPoints.length} vendor check-in(s)</p>{employees.map(item=>{const state=signal(item.location?.recorded_at);return <article key={item.id}><div className="attendance-person"><Initials name={item.full_name}/><span><strong>{item.full_name}</strong><small>{item.employee_code} · Employee</small></span></div><span className={`location-signal ${state.className}`}>● {state.label}</span>{item.location&&<small>{new Date(item.location.recorded_at).toLocaleString()}</small>}</article>})}{vendors.map(item=>{const state=signal(item.check_in_at);return <article key={`vendor-${item.id}`}><div className="attendance-person"><Initials name={item.vendor_name}/><span><strong>{item.vendor_name}</strong><small>{item.vendor_code} · Vendor · {item.outlet_name}</small></span></div><span className={`location-signal ${state.className}`}>● {state.label}</span><small>In: {displayTime(item.check_in_at)} · Out: {displayTime(item.check_out_at)} · Worked: {duration(item.worked_minutes)}</small></article>})}</aside></div>;
}
