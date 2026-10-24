import DateField from "./DateField";
import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {useCallback, useEffect, useRef, useState} from "react";
import {apiRequest} from "./lib/api";

const dateTime = value => value ? new Date(value).toLocaleString("en-GB",dateOptions({},true)) : "—";
const dateOnly = value => value ? new Date(`${value}T00:00:00`).toLocaleDateString("en-GB",dateOptions({},false)) : "—";
const readable = value => String(value || "—").replaceAll("_", " ");

export default function TeamAssignments({reloadKey, onActivity}) {
  const [data, setData] = useState({items: [], total: 0});
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({search: "", assignment_status: "", start_date: "", end_date: ""});
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);
  const limit = 50;
  useEffect(() => {
    const timer = setTimeout(() => {setFilters(f => ({...f, search})); setOffset(0);}, 300);
    return () => clearTimeout(timer);
  }, [search]);
  const load = useCallback(async () => {
    const current = ++request.current;
    if (filters.start_date && filters.end_date && filters.start_date > filters.end_date) {
      setError("From date must be on or before To date."); setData({items: [], total: 0}); setLoading(false); return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({offset: String(offset), limit: String(limit)});
      Object.entries(filters).forEach(([key, value]) => {if (value) params.set(key, value);});
      const result = await apiRequest(`/task-management/assignments?${params}`);
      if (current === request.current) {setData(result); setError("");}
    } catch (err) {
      if (current === request.current) {
        setData({items: [], total: 0});
        setError(err.status === 404 ? "Install the task oversight server update to load team assignments." : (err.message || "Team assignments could not be loaded."));
      }
    } finally {if (current === request.current) setLoading(false);}
  }, [filters, offset]);
  useEffect(() => {
    load();
    const refreshVisible = () => {if (document.visibilityState === "visible") load();};
    const timer = setInterval(refreshVisible, 30000);
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {request.current++; clearInterval(timer); document.removeEventListener("visibilitychange", refreshVisible);};
  }, [load, reloadKey]);
  function filter(key, value) {setFilters(f => ({...f, [key]: value})); setOffset(0);}
  return <section className="panel team-assignments" aria-label="Team assignments">
    <div className="panel-header"><div><h2>Team Assignments & Progress</h2>
      <p>Track assignments, progress and phone alerts. Refreshes automatically while open.</p></div>
      <button type="button" className="secondary-button" onClick={load} disabled={loading}>{loading ? "Refreshing…" : "Refresh team"}</button></div>
    <div className="form-grid team-filters">
      <label className="team-search">Search tasks or employees<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Task, employee name or code"/></label>
      <label className="team-status-filter">Status<select value={filters.assignment_status} onChange={e => filter("assignment_status", e.target.value)}>
        <option value="">All statuses</option>{["ASSIGNED", "IN_PROGRESS", "COMPLETED", "OVERDUE", "COMPLETED_LATE", "CANCELLED"].map(s => <option key={s} value={s}>{readable(s)}</option>)}
      </select></label>
      <label>Scheduled from<DateField type="date" value={filters.start_date} onChange={e => filter("start_date", e.target.value)}/></label>
      <label>Scheduled to<DateField type="date" value={filters.end_date} onChange={e => filter("end_date", e.target.value)}/></label>
    </div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    <p className="muted" aria-live="polite">{data.total} assignment{data.total === 1 ? "" : "s"}{loading ? " · Updating…" : ""}</p>
    {data.items.length > 0 && <ul className="team-mobile-list">{data.items.map(row => <li key={row.id} className="team-mobile-card">
      <div className="team-card-heading"><h3>{row.task_title}</h3><span className="task-status-pill" data-status={row.display_status || row.status}>{readable(row.display_status || row.status)}</span></div>
      <p className="team-assignee"><strong>{row.employee_name || row.employee_code}</strong><span>{row.employee_code}</span></p>
      <dl className="team-dates"><div><dt>Scheduled</dt><dd>{dateOnly(row.scheduled_for)}</dd></div><div><dt>Due</dt><dd>{dateTime(row.due_at)}</dd></div></dl>
      <div className="team-progress"><span className="team-field-label">Latest progress</span><p>{row.latest_note || row.completion_note || "No progress note yet"}</p>
        {row.latest_at && <small>{readable(row.latest_action)} · {dateTime(row.latest_at)}</small>}</div>
      <details className="team-card-details"><summary>Assignment & alert details</summary><dl>
        <div><dt>Assigned by</dt><dd>{row.assigned_by || "—"}</dd></div><div><dt>Priority</dt><dd>{readable(row.priority)}</dd></div>
        {row.started_at && <div><dt>Started</dt><dd>{dateTime(row.started_at)}</dd></div>}
        {row.completed_at && <div><dt>Completed</dt><dd>{dateTime(row.completed_at)}</dd></div>}
        <div><dt>Phone alert</dt><dd>{row.phone_alert?.message || "Not available"}<br/>{row.phone_alert?.registered_phones || 0} phone(s) registered
          {row.phone_alert?.error_code && <small>{row.phone_alert.error_code}</small>}</dd></div>
      </dl></details>
      <button type="button" className="secondary-button team-activity-button" onClick={() => onActivity(row.id)}>View activity ({row.activity_count})</button>
    </li>)}</ul>}
    {data.items.length ? <div className="table-scroll team-desktop-table" role="region" aria-label="Team assignment table" tabIndex={0}><table className="data-table"><thead><tr>
      <th>Task / assigned by</th><th>Employee</th><th>Scheduled / due</th><th>Status</th><th>Latest progress</th><th>Phone alert</th><th>Activity</th>
    </tr></thead><tbody>{data.items.map(row => <tr key={row.id}>
      <td><strong>{row.task_title}</strong><div className="muted">{row.priority} · Assigned by {row.assigned_by}</div></td>
      <td><strong>{row.employee_name || row.employee_code}</strong><div className="muted">{row.employee_code}</div></td>
      <td>{dateOnly(row.scheduled_for)}<div className="muted">Due: {dateTime(row.due_at)}</div></td>
      <td><span className="task-status-pill">{readable(row.display_status || row.status)}</span>
        {row.started_at && <div className="muted">Started: {dateTime(row.started_at)}</div>}
        {row.completed_at && <div className="muted">Completed: {dateTime(row.completed_at)}</div>}</td>
      <td style={{minWidth: 180, maxWidth: 360, overflowWrap: "anywhere"}}>{row.latest_note || row.completion_note || "No progress note yet"}
        <div className="muted">{readable(row.latest_action)} · {dateTime(row.latest_at)}</div></td>
      <td style={{minWidth: 160}}>{row.phone_alert.message}<div className="muted">{row.phone_alert.registered_phones} phone(s) registered</div>
        {row.phone_alert.error_code && <div className="muted">{row.phone_alert.error_code}</div>}</td>
      <td><button type="button" className="secondary-button" onClick={() => onActivity(row.id)}>View activity ({row.activity_count})</button></td>
    </tr>)}</tbody></table></div> : !loading && !error && <div className="empty-state">No assignments match these filters.</div>}
    <div className="action-strip team-pagination">
      <button type="button" className="secondary-button" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</button>
      <span>{data.total ? `${offset + 1}–${Math.min(offset + limit, data.total)} of ${data.total}` : "0 results"}</span>
      <button type="button" className="secondary-button" disabled={loading || offset + limit >= data.total} onClick={() => setOffset(offset + limit)}>Next</button>
    </div>
    <p className="muted">“Sent to Firebase” confirms the sending service accepted the alert. Display and sound also depend on the phone's notification settings.</p>
  </section>;
}
// date-display-ddmmyyyy-v1
