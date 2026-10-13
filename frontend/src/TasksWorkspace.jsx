import TeamAssignments from "./TeamAssignments";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import {apiRequest} from "./lib/api";
import {useAuth} from "./context/AuthContext";

const MGMT=["ADMIN","MD","GM","MANAGER"];
const TASK_TYPES=["TASK","ROUTINE","FIELD_VISIT"];
const PRIORITIES=["LOW","MEDIUM","HIGH","URGENT"];

const today=()=>new Date().toISOString().slice(0,10);
const emptyTask=()=>({
  title:"",description:"",task_type:"TASK",priority:"MEDIUM",
  location_required:false,geofence_id:""
});
const emptyAssign=()=>({task_id:"",employee_ids:[],scheduled_for:today(),due_at:""});

function errText(err){
  const v=err?.detail??err?.message??err;
  if(typeof v==="string")return v==="[object Object]"?"The request could not be completed.":v;
  if(Array.isArray(v))return v.map(x=>x?.msg||"Invalid information.").join(" ");
  if(v&&typeof v==="object"&&Array.isArray(v.detail))return v.detail.map(x=>x?.msg||"Invalid information.").join(" ");
  if(v&&typeof v==="object"&&typeof v.message==="string")return v.message;
  if(v&&typeof v==="object"&&typeof v.detail==="string")return v.detail;
  return "The request could not be completed.";
}
function toIso(v){if(!v)return null;const d=new Date(v);if(Number.isNaN(d.getTime()))throw new Error("Invalid date/time.");return d.toISOString();}
function empName(e){return e?.full_name||[e?.first_name,e?.last_name].filter(Boolean).join(" ")||e?.name||""}
function empCode(e){return e?.employee_code||e?.user?.employee_code||e?.code||""}
function taskLabel(t){return `${t.title} · ${String(t.task_type||"TASK").replaceAll("_"," ")}`}

function humanDuration(seconds){
  const total=Math.max(0,Math.floor(Number(seconds||0)));
  const days=Math.floor(total/86400);
  const hours=Math.floor((total%86400)/3600);
  const minutes=Math.floor((total%3600)/60);

  const parts=[];
  if(days)parts.push(`${days} day${days===1?"":"s"}`);
  if(hours)parts.push(`${hours} hour${hours===1?"":"s"}`);
  if(minutes||!parts.length)parts.push(`${minutes} minute${minutes===1?"":"s"}`);
  return parts.slice(0,2).join(" ");
}

function assignmentDisplay(row){
  const computed=String(row?.display_status||"").toUpperCase();

  if(computed)return computed;

  const raw=String(row?.status||"").toUpperCase();

  if(
    !["COMPLETED","CANCELLED"].includes(raw)
    &&row?.due_at
    &&new Date(row.due_at).getTime()<Date.now()
  ){
    return "OVERDUE";
  }

  if(
    raw==="COMPLETED"
    &&row?.completed_at
    &&row?.due_at
    &&new Date(row.completed_at).getTime()>new Date(row.due_at).getTime()
  ){
    return "COMPLETED_LATE";
  }

  return raw||"—";
}


export default function TasksWorkspace(){
 const { roles = [] } = useAuth();
 const location=useLocation();

const management =
  Array.isArray(roles) &&
  roles.some((role) =>
    MGMT.includes(role)
  );

  const [tasks,setTasks]=useState([]);
  const [teamVersion,setTeamVersion]=useState(0);
  const [employees,setEmployees]=useState([]);
  const [mine,setMine]=useState([]);
  const [taskForm,setTaskForm]=useState(emptyTask);
  const [assignForm,setAssignForm]=useState(emptyAssign);
  const [showCreate,setShowCreate]=useState(false);
  const [showAssign,setShowAssign]=useState(false);
  const [query,setQuery]=useState("");
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [success,setSuccess]=useState("");
  const [availability,setAvailability]=useState({});
  const [availabilityLoading,setAvailabilityLoading]=useState(false);
  const [activity,setActivity]=useState(null);
  const activityRef=useRef(null);
  const lock=useRef(false);

  const sortedTasks=useMemo(
    ()=>[...tasks].sort((a,b)=>String(a.title||"").localeCompare(String(b.title||""),undefined,{sensitivity:"base"})),
    [tasks]
  );

  const sortedEmployees=useMemo(
    ()=>[...employees].sort((a,b)=>{
      const n=empName(a).localeCompare(empName(b),undefined,{sensitivity:"base"});
      return n!==0?n:empCode(a).localeCompare(empCode(b),undefined,{sensitivity:"base"});
    }),
    [employees]
  );

  const filteredEmployees=useMemo(()=>{
    const q=query.trim().toLowerCase();
    if(!q)return sortedEmployees;
    return sortedEmployees.filter(e=>`${empName(e)} ${empCode(e)}`.toLowerCase().includes(q));
  },[query,sortedEmployees]);

  async function load(){
    setLoading(true);setError("");

    if(management){
      const results=await Promise.allSettled([
        apiRequest("/tasks"),
        apiRequest("/tasks/me/assignments"),
        apiRequest("/employees")
      ]);

      setTasks(
        results[0].status==="fulfilled"&&Array.isArray(results[0].value)
          ?results[0].value
          :[]
      );

      setMine(
        results[1].status==="fulfilled"&&Array.isArray(results[1].value)
          ?results[1].value
          :[]
      );

      setEmployees(
        results[2].status==="fulfilled"&&Array.isArray(results[2].value)
          ?results[2].value
          :[]
      );

      if(results[0].status==="rejected")setError(errText(results[0].reason));
      else if(results[1].status==="rejected")setError(errText(results[1].reason));
      else if(results[2].status==="rejected")setError(errText(results[2].reason));
    }else{
      try{
        const mineData=await apiRequest("/tasks/me/assignments");
        setMine(Array.isArray(mineData)?mineData:[]);
        setTasks([]);
        setEmployees([]);
      }catch(err){
        setMine([]);
        setError(errText(err));
      }
    }

    setTeamVersion(value=>value+1);
    setLoading(false);
  }

  useEffect(()=>{load()},[management]);

  async function loadAvailability(){
    if(!management||!showAssign||!assignForm.scheduled_for){
      setAvailability({});
      return;
    }

    setAvailabilityLoading(true);

    try{
      const params=new URLSearchParams({
        scheduled_for:assignForm.scheduled_for
      });

      const effectiveDue=assignForm.due_at
        ?toIso(assignForm.due_at)
        :"";

      if(effectiveDue){
        params.set("due_at",effectiveDue);
      }

      const data=await apiRequest(
        `/tasks/assignment-availability?${params.toString()}`
      );

      const map={};

      (Array.isArray(data)?data:[]).forEach(item=>{
        map[item.employee_id]=item;
      });

      setAvailability(map);

      setAssignForm(current=>({
        ...current,
        employee_ids:current.employee_ids.filter(
          id=>map[id]?.available!==false
        )
      }));
    }catch(err){
      setAvailability({});
      setError(errText(err));
    }finally{
      setAvailabilityLoading(false);
    }
  }

  useEffect(()=>{
    loadAvailability();
  },[
    management,
    showAssign,
    assignForm.scheduled_for,
    assignForm.due_at,
    assignForm.task_id,
    assignForm.task_id
  ]);

  async function openActivity(rowOrId){
    const id=typeof rowOrId==="string"
      ?rowOrId
      :rowOrId?.id;

    if(!id)return;

    setError("");

    try{
      const data=await apiRequest(
        `/tasks/assignments/${id}/activity`
      );

      setActivity(data||null);

      window.setTimeout(()=>{
        activityRef.current?.scrollIntoView({
          behavior:"smooth",
          block:"start"
        });
      },100);
    }catch(err){
      setActivity(null);
      setError(errText(err));
    }
  }

  useEffect(()=>{
    const params=new URLSearchParams(location.search);
    const assignmentId=params.get("assignment");

    if(assignmentId){
      openActivity(assignmentId);
    }
  },[location.search]);

  function toggleEmployee(id){
    if(availability[id]?.available===false)return;

    setAssignForm(f=>({
      ...f,
      employee_ids:f.employee_ids.includes(id)
        ?f.employee_ids.filter(x=>x!==id)
        :[...f.employee_ids,id]
    }));
  }

  async function createTask(e){
    e.preventDefault();
    if(!management||lock.current)return;
    lock.current=true;setBusy(true);setError("");setSuccess("");
    try{
      await apiRequest("/tasks",{method:"POST",body:{
        title:taskForm.title.trim(),
        description:taskForm.description.trim()||null,
        task_type:taskForm.task_type,
        priority:taskForm.priority,
        geofence_id:null,
        starts_at:null,
        due_at:null,
        recurrence_type:"NONE",
        recurrence_interval:1,
        recurrence_days:null,
        location_required:false,
        questionnaire_schema:null
      }});
      setSuccess("Task created successfully.");
      setTaskForm(emptyTask());setShowCreate(false);
      await load();
    }catch(err){setError(errText(err))}
    finally{lock.current=false;setBusy(false)}
  }

  async function assignTask(e){
    e.preventDefault();
    if(!management||lock.current)return;
    if(!assignForm.task_id){setError("Please select a task.");return}
    if(!assignForm.employee_ids.length){setError("Please select at least one employee.");return}
    lock.current=true;setBusy(true);setError("");setSuccess("");
    try{
      await apiRequest(`/tasks/${assignForm.task_id}/assignments`,{method:"POST",body:{
        employee_ids:assignForm.employee_ids,
        scheduled_for:assignForm.scheduled_for,
        due_at:toIso(assignForm.due_at)
      }});
      const count=assignForm.employee_ids.length;
      setSuccess(`Task assignment saved for ${count} employee${count===1?"":"s"}. Check Team Assignments & Progress for phone alert status.`);
      setAssignForm(emptyAssign());setQuery("");setShowAssign(false);
      await load();
      window.dispatchEvent(new Event("action-alerts:refresh"));
    }catch(err){setError(errText(err))}
    finally{lock.current=false;setBusy(false)}
  }

  async function start(row){
    if(busy)return;
    const note=window.prompt(`Start "${row.task_title}"?\n\nStart note (optional):`,"");
    if(note===null)return;
    setBusy(true);setError("");setSuccess("");
    try{
      await apiRequest(`/tasks/assignments/${row.id}/start`,{method:"POST",body:{note:note.trim()||null,latitude:null,longitude:null}});
      setSuccess(`"${row.task_title}" started.`);
      await load();
      await openActivity(row);
      window.dispatchEvent(new Event("action-alerts:refresh"));
    }catch(err){setError(errText(err))}
    finally{setBusy(false)}
  }

  async function progress(row){
    if(busy)return;
    const note=window.prompt(`Progress update for "${row.task_title}":`);
    if(!note?.trim())return;
    setBusy(true);setError("");setSuccess("");
    try{
      await apiRequest(`/tasks/assignments/${row.id}/progress`,{method:"POST",body:{note:note.trim(),latitude:null,longitude:null}});
      setSuccess(`Progress added to "${row.task_title}".`);
      await openActivity(row);
      window.dispatchEvent(new Event("action-alerts:refresh"));
    }catch(err){setError(errText(err))}
    finally{setBusy(false)}
  }

  async function complete(row){
    if(busy)return;
    const note=window.prompt(`Complete "${row.task_title}"?\n\nCompletion note (optional):`,"");
    if(note===null)return;
    setBusy(true);setError("");setSuccess("");
    try{
      await apiRequest(`/tasks/assignments/${row.id}/complete`,{method:"POST",body:{
        completion_note:note.trim()||null,evidence_urls:[],latitude:null,longitude:null
      }});
      setSuccess(`"${row.task_title}" completed.`);
      await load();
      await openActivity(row);
      window.dispatchEvent(new Event("action-alerts:refresh"));
    }catch(err){setError(errText(err))}
    finally{setBusy(false)}
  }

  return <div className="page">
    <header className="page-header"><div>
      <span className="eyebrow">Work Planning</span>
      <h1>Tasks & Field Visits</h1>
      <p>Assign work by employee name, respect approved leave, track progress, and automatically flag overdue work.</p>
    </div></header>

    {success&&<div className="success-banner">✅ {success}</div>}
    {error&&<div className="error-banner">{error}</div>}

    <div className="action-strip">
      {management&&<>
        <button type="button" className="primary-button" disabled={busy} onClick={()=>{setShowCreate(!showCreate);setShowAssign(false);setError("");setSuccess("")}}>
          {showCreate?"Close":"Create Task"}
        </button>
        <button type="button" className="secondary-button" disabled={busy} onClick={()=>{setShowAssign(!showAssign);setShowCreate(false);setError("");setSuccess("")}}>
          {showAssign?"Close":"Assign Task"}
        </button>
      </>}
      <button type="button" className="secondary-button" disabled={loading||busy} onClick={load}>{loading?"Refreshing…":"Refresh"}</button>
    </div>

    {management&&showCreate&&<section className="panel">
      <div className="panel-header"><div><h2>Create Task</h2><p>Create a reusable task definition. Choose dates only when assigning it to employees.</p></div></div>
      <form className="document-form" onSubmit={createTask}>
        <div className="form-grid">
          <label>Task Title *<input required minLength="3" maxLength="200" disabled={busy} value={taskForm.title} onChange={e=>setTaskForm({...taskForm,title:e.target.value})}/></label>
          <label>Task Type *<select required disabled={busy} value={taskForm.task_type} onChange={e=>setTaskForm({...taskForm,task_type:e.target.value})}>
            {TASK_TYPES.map(x=><option key={x} value={x}>{x.replaceAll("_"," ")}</option>)}
          </select></label>
          <label>Priority *<select required disabled={busy} value={taskForm.priority} onChange={e=>setTaskForm({...taskForm,priority:e.target.value})}>
            {PRIORITIES.map(x=><option key={x} value={x}>{x}</option>)}
          </select></label>
        </div>
        <label>Description<textarea rows="4" disabled={busy} value={taskForm.description} onChange={e=>setTaskForm({...taskForm,description:e.target.value})}/></label>
        <button className="primary-button" disabled={busy}>{busy?"Creating…":"Create Task"}</button>
      </form>
    </section>}

    {management&&showAssign&&<section className="panel">
      <div className="panel-header"><div>
        <span className="eyebrow">Assignment</span>
        <h2>Assign Task</h2>
        <p>Select the task and employees by readable name. Employee IDs remain internal.</p>
      </div></div>

      <form className="document-form" onSubmit={assignTask}>
        <div className="form-grid">
          <label>Task *<select required disabled={busy} value={assignForm.task_id} onChange={e=>setAssignForm({...assignForm,task_id:e.target.value})}>
            <option value="">Select task…</option>
            {sortedTasks.map(t=><option key={t.id} value={t.id}>{taskLabel(t)}</option>)}
          </select></label>

          <label>Scheduled For *<input required type="date" disabled={busy} value={assignForm.scheduled_for} onChange={e=>setAssignForm({...assignForm,scheduled_for:e.target.value})}/></label>

          <label>Assignment Due At<input type="datetime-local" disabled={busy} value={assignForm.due_at} onChange={e=>setAssignForm({...assignForm,due_at:e.target.value})}/></label>
        </div>

        {availabilityLoading&&(
          <div className="warning-banner">
            Checking employee leave availability…
          </div>
        )}

        <div className="employee-picker">
          <div className="employee-picker-header">
            <div><strong>Employees *</strong><span className="muted">{assignForm.employee_ids.length} selected</span></div>
            <button type="button" className="link-button" disabled={busy} onClick={()=>setAssignForm({...assignForm,employee_ids:[]})}>Clear</button>
          </div>

          <input type="search" className="search-input" placeholder="Search employee name or code…" disabled={busy} value={query} onChange={e=>setQuery(e.target.value)}/>

          <div className="employee-picker-list">
            {filteredEmployees.length===0
              ?<div className="empty-state">No employees found.</div>
              :filteredEmployees.map(emp=>{
                const checked=assignForm.employee_ids.includes(emp.id);
                const availabilityInfo=availability[emp.id];
                const unavailable=availabilityInfo?.available===false;

                return <button
                  key={emp.id}
                  type="button"
                  disabled={busy||availabilityLoading||unavailable}
                  className={`employee-picker-row ${checked?"selected":""}`}
                  onClick={()=>toggleEmployee(emp.id)}
                  aria-pressed={checked}
                  title={availabilityInfo?.reason||""}
                >
                  <span
                    className={`employee-select-box ${checked?"checked":""}`}
                    aria-hidden="true"
                  >
                    {checked ? "✓" : ""}
                  </span>

                  <span className="employee-picker-name">
                    <strong>{empName(emp)||"Unnamed Employee"}</strong>
                    <small>{empCode(emp)||"No employee code"}</small>
                    {availabilityInfo&&(
                      <small>
                        {availabilityInfo.available
                          ?"Available"
                          :`Unavailable · ${availabilityInfo.reason}`}
                      </small>
                    )}
                  </span>
                </button>
              })}
          </div>
        </div>

        <button className="primary-button" disabled={busy||!assignForm.employee_ids.length}>
          {busy?"Assigning…":`Assign Task${assignForm.employee_ids.length?` to ${assignForm.employee_ids.length} Employee${assignForm.employee_ids.length===1?"":"s"}`:""}`}
        </button>
      </form>
    </section>}

    {management&&<TeamAssignments reloadKey={teamVersion} onActivity={openActivity}/>}

    <section className="panel">
      <div className="panel-header"><div><h2>My Assignments</h2><p>Start, update and complete assigned work directly from the list.</p></div></div>
      {loading?<div className="skeleton-lines"/>:mine.length===0?<div className="empty-state">No task assignments found.</div>:<div className="task-card-grid">
        {mine.map(row=>{
          const status=String(row.status||"").toUpperCase();
          const displayStatus=assignmentDisplay(row);
          const canStart=!["IN_PROGRESS","COMPLETED","CANCELLED"].includes(status);
          const canWork=status==="IN_PROGRESS";
          return <article className="task-assignment-card" key={row.id}>
            <div className="task-assignment-top">
              <div><span className="eyebrow">{String(row.task_type||"TASK").replaceAll("_"," ")}</span><h3>{row.task_title}</h3></div>
              <span className="task-status-pill">
                {displayStatus.replaceAll("_"," ")}
              </span>
            </div>
            {row.task_description&&<p>{row.task_description}</p>}

            {displayStatus==="OVERDUE"&&(
              <div className="error-banner">
                🔴 Overdue by {humanDuration(
                  row.overdue_by_seconds
                    ||Math.max(
                      0,
                      (Date.now()-new Date(row.due_at).getTime())/1000
                    )
                )}. Progress and completion are still allowed.
              </div>
            )}

            {displayStatus==="LEAVE_CONFLICT"&&(
              <div className="warning-banner">
                🏖️ This task conflicts with approved leave.
                {row.leave_conflict_reason?` ${row.leave_conflict_reason}.`:""}
                The assigner should reschedule or reassign it.
              </div>
            )}

            {displayStatus==="COMPLETED_LATE"&&(
              <div className="warning-banner">
                Completed late by {humanDuration(
                  row.completed_late_by_seconds
                    ||Math.max(
                      0,
                      (new Date(row.completed_at).getTime()-new Date(row.due_at).getTime())/1000
                    )
                )}.
              </div>
            )}

            <div className="task-meta-grid">
              <span><small>Priority</small><strong>{row.priority}</strong></span>
              <span><small>Scheduled</small><strong>{row.scheduled_for||"—"}</strong></span>
              <span><small>Due</small><strong>{row.due_at?new Date(row.due_at).toLocaleString():"—"}</strong></span>
            </div>
            <div className="action-strip">
              {canStart&&<button type="button" className="primary-button" disabled={busy} onClick={()=>start(row)}>Start</button>}
              {canWork&&<>
                <button type="button" className="secondary-button" disabled={busy} onClick={()=>progress(row)}>Add Progress</button>
                <button type="button" className="primary-button" disabled={busy} onClick={()=>complete(row)}>Complete</button>
              </>}
              <button type="button" className="secondary-button" disabled={busy} onClick={()=>openActivity(row)}>View Activity</button>
              {!canStart&&!canWork&&<span className="muted">No action required.</span>}
            </div>
          </article>
        })}
      </div>}
    </section>


    {activity&&<section className="panel" ref={activityRef}>
      <div className="panel-header">
        <div>
          <span className="eyebrow">Task Activity</span>
          <h2>{activity.task_title}</h2>
          <p>
            {activity.employee_code}
            {activity.employee_name?` - ${activity.employee_name}`:""}
            {" · "}
            {String(activity.display_status||activity.status||"").replaceAll("_"," ")}
          </p>

          {activity.display_status==="OVERDUE"&&(
            <div className="error-banner">
              Overdue by {humanDuration(activity.overdue_by_seconds)}.
            </div>
          )}

          {activity.display_status==="LEAVE_CONFLICT"&&(
            <div className="warning-banner">
              Approved leave conflict: {activity.leave_conflict_reason||"reschedule or reassign this task"}.
            </div>
          )}

          {activity.display_status==="COMPLETED_LATE"&&(
            <div className="warning-banner">
              Completed late by {humanDuration(activity.completed_late_by_seconds)}.
            </div>
          )}
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={()=>setActivity(null)}
        >
          Close
        </button>
      </div>

      <div className="notification-list">
        {(activity.logs||[]).length===0
          ?<div className="empty-state">No activity recorded yet.</div>
          :(activity.logs||[]).map(log=>
            <article className="notification-card" key={log.id}>
              <div>
                <strong>{String(log.action||"UPDATE").replaceAll("_"," ")}</strong>
                <p>{log.note||"No note provided."}</p>
                <small>
                  {log.created_at
                    ?new Date(log.created_at).toLocaleString()
                    :""}
                </small>
              </div>
            </article>
          )
        }
      </div>
    </section>}

    {management&&<section className="panel">
      <div className="panel-header"><div><h2>Task Catalogue</h2><p>Reusable task definitions. View employee dates, status and progress under Team Assignments & Progress.</p></div><span className="muted">{sortedTasks.length} tasks</span></div>
      {loading?<div className="skeleton-lines"/>:sortedTasks.length===0?<div className="empty-state">No tasks created yet.</div>:<div className="table-scroll">
        <table className="data-table"><thead><tr><th>Task</th><th>Type</th><th>Priority</th></tr></thead>
          <tbody>{sortedTasks.map(t=><tr key={t.id}>
            <td><strong>{t.title}</strong><div className="muted">{t.description||"—"}</div></td>
            <td>{String(t.task_type||"—").replaceAll("_"," ")}</td>
            <td>{t.priority}</td>
          </tr>)}</tbody>
        </table>
      </div>}
    </section>}
  </div>
}
