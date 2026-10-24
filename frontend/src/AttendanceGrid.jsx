import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {useEffect,useState} from 'react';
import {apiRequest} from './lib/api';
import './attendanceGrid.css';
export default function AttendanceGrid({range,search='',refreshKey}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[selected,setSelected]=useState(null);
 useEffect(()=>{let live=true;setBusy(true);setError('');setSelected(null);
 apiRequest('/workforce-improvements/attendance-grid?'+new URLSearchParams(range)).then(x=>{if(live)setData(x)}).catch(e=>{if(live){setError(e.message);setData(null)}}).finally(()=>{if(live)setBusy(false)});
 return()=>{live=false}},[range.start_date,range.end_date,refreshKey]);
 const time=v=>v?new Date(v).toLocaleString("en-GB",dateOptions({timeZone:data?.timezone,dateStyle:'medium',timeStyle:'short'},true)):'Not recorded';
 const rows=(data?.rows||[]).filter(r=>(r.name+' '+r.code+' '+r.kind+' '+r.cells.map(c=>c.status).join(' ')).toLowerCase().includes(search.toLowerCase()));
 if(busy)return <div className="empty-state">Loading attendance calendar…</div>;
 if(error)return <div role="alert" className="error-banner">{error}</div>;
 return <section className="attendance-calendar">
 <div className="calendar-legend"><span className="present">P · Present</span><span className="late">P · Late</span><span className="absent">A · Absent / no check-in</span><span className="leave">A · Approved leave</span><span className="off">OFF · Holiday</span><span>— · Not applicable / not recorded yet</span></div>
 <p>{rows.length} people · Click any date cell for timings and leave details. Swipe horizontally to view more dates.</p>
 <div className="calendar-scroll" tabIndex={0} aria-label="Attendance by person and date"><table><thead><tr><th className="calendar-person">Person</th>{data?.dates.map(d=><th key={d}><span>{d.slice(8)}/{d.slice(5,7)}</span><small>{new Date(d+'T12:00:00').toLocaleDateString("en-GB",dateOptions({weekday:'short'},false))}</small></th>)}</tr></thead>
 <tbody>{rows.map(r=><tr key={r.id}><th className="calendar-person" scope="row"><strong>{r.name}</strong><small>{r.code} · {r.kind}</small></th>{r.cells.map(c=><td key={c.date}><button className={'calendar-cell '+c.tone} title={c.status.replaceAll('_',' ')} aria-label={r.name+' '+c.date+' '+c.status} onClick={()=>setSelected({person:r,cell:c})}>{c.mark}</button></td>)}</tr>)}</tbody></table></div>
 {!rows.length&&<div className="empty-state">No people match this date range and search.</div>}
 {selected&&<div className="calendar-overlay"><section role="dialog" aria-modal="true" aria-label="Attendance details"><header><h2>{selected.person.name}</h2><button className="secondary-button" onClick={()=>setSelected(null)}>Close</button></header><p>{selected.person.code} · {formatDisplayDate(selected.cell.date)} · {selected.cell.status.replaceAll('_',' ')}</p><p>{selected.cell.reason}</p>
 {selected.cell.records.map((r,i)=><article key={i}><h3>{r.outlet_name||'Attendance timings'}</h3><dl><dt>Check in</dt><dd>{time(r.check_in_at)}</dd><dt>Check out</dt><dd>{time(r.check_out_at)}</dd><dt>Worked</dt><dd>{Math.floor((r.worked_minutes||0)/60)}h {(r.worked_minutes||0)%60}m</dd><dt>Late</dt><dd>{r.late_minutes||0} minutes</dd><dt>Recorded status</dt><dd>{r.status}</dd></dl></article>)}
 {!selected.cell.records.length&&<p>No check-in or check-out record exists for this date.</p>}
 <h3>Leave information</h3>{selected.cell.leaves.length?selected.cell.leaves.map((l,i)=><p key={i}><strong>{l.status}</strong> · {formatDisplayDate(l.start_date)} to {formatDisplayDate(l.end_date)}<br/>{l.reason||'No reason recorded.'}</p>):<p>No leave request or leave reason is recorded for this date.</p>}
 </section></div>}
 </section>
}
// date-display-ddmmyyyy-v1
