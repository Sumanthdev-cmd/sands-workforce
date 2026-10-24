import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {useEffect,useMemo,useState} from "react";

import {apiRequest} from "./lib/api";


const readableError=(error)=>typeof error?.data?.detail==="string"?error.data.detail:error?.message||"Unable to load the MD overview.";
const dateLabel=(value)=>new Date(`${value}T00:00:00`).toLocaleDateString("en-GB",dateOptions({weekday:"short",day:"numeric",month:"short",year:"numeric"},false));
const dateTime=(value)=>value?new Date(value).toLocaleString("en-GB",dateOptions({},true)):"—";
const duration=(value)=>`${Math.floor(Number(value||0)/60)}h ${Number(value||0)%60}m`;
const escapeHtml=(value)=>String(value??"—").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

function rowsHtml(rows,columns){
  if(!rows?.length)return "<p>No records.</p>";
  return `<table><thead><tr>${columns.map(([label])=>`<th>${escapeHtml(label)}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${columns.map(([,key])=>`<td>${escapeHtml(row[key])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function reportHtml(report){
  const summary=report.summary||{};
  return `<!doctype html><html><head><meta charset="utf-8"><title>MD Daily Overview ${escapeHtml(report.report_date)}</title><style>body{font-family:Arial,sans-serif;margin:32px;color:#14213d}h1,h2{margin-bottom:8px}.meta{color:#596780}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:20px 0}.metrics div{border:1px solid #ccd5e4;border-radius:8px;padding:12px}.metrics strong{display:block;font-size:24px;margin-top:4px}table{width:100%;border-collapse:collapse;margin:12px 0 24px}th,td{border:1px solid #ccd5e4;padding:8px;text-align:left;font-size:12px}th{background:#eef3fb}li{margin:6px 0}@media print{button{display:none}.metrics{grid-template-columns:repeat(4,1fr)}}</style></head><body><button onclick="window.print()">Print / Save as PDF</button><h1>${escapeHtml(report.organization_name)} — MD Daily Overview</h1><p class="meta">Report date: ${escapeHtml(report.report_date)} · Generated: ${escapeHtml(dateTime(report.generated_at))}</p><div class="metrics"><div>Active employees<strong>${summary.active_employees||0}</strong></div><div>Attendance<strong>${summary.attendance_records||0}</strong></div><div>Tasks completed<strong>${summary.tasks_completed||0}</strong></div><div>Tasks pending<strong>${summary.tasks_pending||0}</strong></div><div>Tasks overdue<strong>${summary.tasks_overdue||0}</strong></div><div>No attendance<strong>${summary.no_attendance_record||0}</strong></div><div>OT claims<strong>${summary.overtime_claims||0}</strong></div><div>Inspections<strong>${summary.inspections_completed||0}</strong></div></div><h2>Attention for the next office day</h2><ul>${(report.attention_items||[]).map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul><h2>Performed work</h2>${rowsHtml(report.performed_tasks,[["Task","title"],["Employee","employee_code"],["Name","employee_name"],["Completed","completed_at"],["Note","completion_note"]])}<h2>Pending work</h2>${rowsHtml(report.pending_tasks,[["Task","title"],["Employee","employee_code"],["Name","employee_name"],["Status","status"],["Due","due_at"],["Overdue","overdue"]])}<h2>Attendance</h2>${rowsHtml(report.attendance,[["Employee","employee_code"],["Name","employee_name"],["Status","status"],["Check-in","check_in_at"],["Check-out","check_out_at"],["Worked","worked_label"],["Late minutes","late_minutes"]])}<h2>Overtime</h2>${rowsHtml(report.overtime,[["Employee","employee_code"],["Name","employee_name"],["OT minutes","overtime_minutes"],["Status","status"],["Approved amount","approved_amount"]])}</body></html>`;
}

function Metrics({summary={}}){
  const items=[["Active employees",summary.active_employees],["Attendance records",summary.attendance_records],["No attendance",summary.no_attendance_record],["Worked",summary.total_work_label],["Tasks completed",summary.tasks_completed],["Tasks pending",summary.tasks_pending],["Tasks overdue",summary.tasks_overdue],["Approved leave",summary.approved_leave],["Expenses submitted",summary.expense_claims_submitted],["Inspections completed",summary.inspections_completed],["OT claims",summary.overtime_claims],["MD actions",Number(summary.pending_password_resets||0)+Number(summary.pending_md_overtime||0)]];
  return <section className="daily-metrics">{items.map(([name,value])=><article key={name}><span>{name}</span><strong>{value??0}</strong></article>)}</section>;
}

export default function MdDailyOverview(){
  const [reports,setReports]=useState([]);
  const [selectedDate,setSelectedDate]=useState("");
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");

  async function load(){
    setLoading(true);setError("");
    try{
      const data=await apiRequest("/dashboard/management/daily-reports");
      const rows=Array.isArray(data)?data:[];
      setReports(rows);
      setSelectedDate(current=>rows.some(row=>row.report_date===current)?current:(rows[0]?.report_date||""));
    }catch(err){setError(readableError(err))}
    finally{setLoading(false)}
  }

  useEffect(()=>{load()},[]);
  const report=useMemo(()=>reports.find(row=>row.report_date===selectedDate)||reports[0],[reports,selectedDate]);

  function download(){
    if(!report)return;
    const blob=new Blob([reportHtml(report)],{type:"text/html;charset=utf-8"});
    const url=URL.createObjectURL(blob);
    const anchor=document.createElement("a");
    anchor.href=url;anchor.download=`MD_Daily_Overview_${report.report_date}.html`;anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  function print(){
    if(!report)return;
    const popup=window.open("","_blank","width=1100,height=850");
    if(!popup){setError("Pop-up was blocked. Allow pop-ups to print or save the report as PDF.");return}
    popup.document.write(reportHtml(report));popup.document.close();
  }

  return <div className="page workforce-controls">
    <header className="page-header"><div><span className="eyebrow">Rolling seven-day view</span><h1>MD Daily Overview</h1><p>Today and the previous six dates only, with performed work, pending work, attendance, exceptions and planning signals.</p></div><div className="header-actions"><button className="secondary-button" onClick={load} disabled={loading}>Refresh</button><button className="secondary-button" onClick={download} disabled={!report}>Download report</button><button className="primary-button" onClick={print} disabled={!report}>Print / Save PDF</button></div></header>
    {error&&<div className="error-banner">{error}</div>}
    {loading?<div className="skeleton-lines"/>:reports.length===0?<div className="empty-state">No overview is available.</div>:<>
      <nav className="report-date-strip" aria-label="MD report dates">{reports.map(row=><button key={row.report_date} className={row.report_date===report?.report_date?"active":""} onClick={()=>setSelectedDate(row.report_date)}><span>{dateLabel(row.report_date)}</span><strong>{row.is_today?"Today":"Open"}</strong></button>)}</nav>
      <section className="panel report-heading"><div><span className="eyebrow">{report.is_today?"Live organization status":"Historical daily snapshot"}</span><h2>{dateLabel(report.report_date)}</h2><p>Generated {dateTime(report.generated_at)} · {report.organization_code}</p></div></section>
      <Metrics summary={report.summary}/>
      <section className="overview-grid">
        <article className="panel attention-panel"><span className="eyebrow">Planning</span><h2>Attention for next office day</h2><ul>{report.attention_items.map(item=><li key={item}>{item}</li>)}</ul></article>
        <article className="panel"><span className="eyebrow">Attendance exceptions</span><h2>Employees without attendance</h2>{report.employees_without_attendance.length===0?<p className="muted">Every active employee has an attendance record.</p>:<ul>{report.employees_without_attendance.map(row=><li key={row.employee_code}><strong>{row.employee_code}</strong> — {row.employee_name}</li>)}</ul>}</article>
      </section>
      <section className="panel"><div className="panel-header"><div><h2>Performed work</h2><p>Tasks completed on this report date.</p></div><span className="queue-count">{report.performed_tasks.length}</span></div>{report.performed_tasks.length===0?<div className="empty-state">No task was marked completed on this date.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Task</th><th>Employee</th><th>Completed</th><th>Completion note</th></tr></thead><tbody>{report.performed_tasks.map((row,index)=><tr key={`${row.employee_code}-${index}`}><td><strong>{row.title}</strong></td><td>{row.employee_code}<div className="muted">{row.employee_name}</div></td><td>{dateTime(row.completed_at)}</td><td>{row.completion_note||"—"}</td></tr>)}</tbody></table></div>}</section>
      <section className="panel"><div className="panel-header"><div><h2>Pending work</h2><p>Work that remained open at the end of this date.</p></div><span className="queue-count">{report.pending_tasks.length}</span></div>{report.pending_tasks.length===0?<div className="empty-state">No pending work for this date.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Task</th><th>Employee</th><th>Status</th><th>Due</th><th>Exception</th></tr></thead><tbody>{report.pending_tasks.map((row,index)=><tr key={`${row.employee_code}-${index}`}><td><strong>{row.title}</strong></td><td>{row.employee_code}<div className="muted">{row.employee_name}</div></td><td>{String(row.status).replaceAll("_"," ")}</td><td>{dateTime(row.due_at)}</td><td>{row.overdue?<span className="control-status bad">OVERDUE</span>:"—"}</td></tr>)}</tbody></table></div>}</section>
      <section className="panel"><div className="panel-header"><div><h2>Daily attendance detail</h2><p>Recorded work hours and late minutes after grace.</p></div></div>{report.attendance.length===0?<div className="empty-state">No attendance entries for this date.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Employee</th><th>Status</th><th>Check-in</th><th>Check-out</th><th>Worked</th><th>Late after grace</th></tr></thead><tbody>{report.attendance.map(row=><tr key={row.employee_code}><td><strong>{row.employee_code}</strong><div className="muted">{row.employee_name}</div></td><td>{row.status}</td><td>{dateTime(row.check_in_at)}</td><td>{dateTime(row.check_out_at)}</td><td>{duration(row.worked_minutes)}</td><td>{row.late_minutes} min</td></tr>)}</tbody></table></div>}</section>
    </>}
  </div>;
}
// date-display-ddmmyyyy-v1
