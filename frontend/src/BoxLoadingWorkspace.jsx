import DateField from "./DateField";
import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import FinancialDownload from "./FinancialDownload";
import {useCallback,useEffect,useRef,useState} from "react";
import {useSearchParams} from "react-router-dom";
import {useAuth} from "./context/AuthContext";
import {apiRequest} from "./lib/api";
import {calculatedCosts,localDate,money,moneyCents,newRequestId,statusLabels} from "./lib/boxLoading";
import "./box_loading.css";

const API="/box-loading/requests";
const initialForm=()=>({loading_date:localDate(),vehicle_type:"OWN",vehicle_number:"",loading_rate:"",loading_box_count:"",transport_rate:"",transport_box_count:"",notes:""});
const dateText=value=>value ? new Date(`${value}T12:00:00`).toLocaleDateString("en-GB",dateOptions({},false)) : "—";
const timeText=value=>value ? new Date(value).toLocaleString("en-GB",dateOptions({},true)) : "—";

function CostBreakdown({row}) {
  return <dl className="box-costs">
    <div><dt>Loading <small>{row.loading_box_count} boxes × {money(row.loading_rate)}</small></dt><dd>{money(row.loading_cost)}</dd></div>
    {row.vehicle_type==="RENTED"&&<div><dt>Transport <small>{row.transport_box_count} boxes × {money(row.transport_rate)}</small></dt><dd>{money(row.transport_cost)}</dd></div>}
    <div className="box-grand-total"><dt>Total amount</dt><dd>{money(row.total_amount)}</dd></div>
  </dl>;
}

function LoadingForm({record,onSave,busy,onCancel}) {
  const [form,setForm]=useState(()=>record ? Object.fromEntries(Object.keys(initialForm()).map(k=>[k,record[k]??""])) : initialForm());
  const [error,setError]=useState("");
  const id=useRef(newRequestId());
  const costs=calculatedCosts(form);
  const set=(key,value)=>setForm(previous=>({...previous,[key]:value}));
  async function save(event) {
    event.preventDefault();setError("");
    if(costs.total===null){setError("Enter whole box counts and rates with no more than two decimal places.");return;}
    const payload={...form,vehicle_number:form.vehicle_number.trim().toUpperCase(),
      loading_box_count:Number(form.loading_box_count),
      transport_rate:form.vehicle_type==="RENTED"?String(form.transport_rate):"0.00",
      transport_box_count:form.vehicle_type==="RENTED"?Number(form.transport_box_count):0};
    if(record)payload.expected_version=record.version;else payload.client_request_id=id.current;
    try {await onSave(payload,record?.id);} catch(err){setError(err.message);}
  }
  return <form className="box-form" onSubmit={save}>
    {error&&<div className="error-banner" role="alert">{error}</div>}
    <fieldset disabled={busy}>
      <div className="box-form-grid">
        <label>Loading date<DateField type="date" required value={form.loading_date} onChange={e=>set("loading_date",e.target.value)}/></label>
        <label>Vehicle type<select value={form.vehicle_type} onChange={e=>setForm(previous=>({...previous,vehicle_type:e.target.value,transport_rate:"",transport_box_count:""}))}><option value="OWN">Own vehicle</option><option value="RENTED">Rented vehicle</option></select></label>
        <label className="box-wide">Vehicle number<input required minLength={2} maxLength={32} autoCapitalize="characters" placeholder="e.g. KA 01 AB 1234" value={form.vehicle_number} onChange={e=>set("vehicle_number",e.target.value.toUpperCase())}/></label>
        <label>Loading cost per box (₹)<input required type="number" inputMode="decimal" min="0" max="1000000" step="0.01" value={form.loading_rate} onChange={e=>set("loading_rate",e.target.value)}/></label>
        <label>Total boxes loaded<input required type="number" inputMode="numeric" min="1" max="1000000" step="1" value={form.loading_box_count} onChange={e=>set("loading_box_count",e.target.value)}/></label>
        {form.vehicle_type==="RENTED"&&<>
          <label>Transport cost per box (₹)<input required type="number" inputMode="decimal" min="0" max="1000000" step="0.01" value={form.transport_rate} onChange={e=>set("transport_rate",e.target.value)}/></label>
          <label>Total boxes transported<input required type="number" inputMode="numeric" min="1" max="1000000" step="1" value={form.transport_box_count} onChange={e=>set("transport_box_count",e.target.value)}/></label>
        </>}
        <label className="box-wide">Notes (optional)<textarea rows={3} maxLength={2000} value={form.notes} onChange={e=>set("notes",e.target.value)}/></label>
      </div>
      <div className="box-preview" aria-live="polite"><span>Loading <strong>{moneyCents(costs.loading)}</strong></span>{form.vehicle_type==="RENTED"&&<span>Transport <strong>{moneyCents(costs.transport)}</strong></span>}<span>Total amount <strong>{moneyCents(costs.total)}</strong></span></div>
      <p className="muted">{form.vehicle_type==="OWN"?"Own vehicles include loading costs only.":"The total includes both loading and transport costs."} Save a draft, then send it to MD for approval.</p>
      <div className="box-buttons"><button className="primary-button" type="submit">{busy?"Saving…":"Save draft"}</button><button className="secondary-button" type="button" onClick={onCancel}>Cancel</button></div>
    </fieldset>
  </form>;
}

function DecisionForm({row,onAction,busy}) {
  const [note,setNote]=useState("");
  const [error,setError]=useState("");
  const [decision,setDecision]=useState("APPROVE");
  async function submit(event){event.preventDefault();setError("");try{await onAction(row,"decision",{decision,note:note.trim()||null},decision==="APPROVE"?"Request approved. Admin can now record the disbursement.":"Request rejected. Admin can correct it and resubmit.");}catch(err){setError(err.message);}}
  return <form onSubmit={submit} className="box-decision"><h3>MD decision</h3><p>Review the vehicle, box counts and total before sanctioning this request.</p>{error&&<div className="error-banner" role="alert">{error}</div>}<fieldset disabled={busy}>
    <label>Decision<select value={decision} onChange={e=>setDecision(e.target.value)}><option value="APPROVE">Approve the full amount</option><option value="REJECT">Reject for correction</option></select></label>
    <label>{decision==="REJECT"?"Rejection reason":"Approval note (optional)"}<textarea required={decision==="REJECT"} maxLength={2000} rows={3} value={note} onChange={e=>setNote(e.target.value)}/></label>
    <button type="submit" className="primary-button">{busy?"Saving decision…":decision==="APPROVE"?`Approve ${money(row.total_amount)}`:"Reject request"}</button>
  </fieldset></form>;
}

function PaymentForm({row,onAction,busy}) {
  const [form,setForm]=useState({payment_date:localDate(),payment_mode:"UPI",paid_to:"",payment_reference:""});
  const [error,setError]=useState("");
  async function submit(event){event.preventDefault();setError("");try{await onAction(row,"disbursement",form,"Disbursement recorded successfully. This request is now marked Disbursed.");}catch(err){setError(err.message);}}
  return <form className="box-payment" onSubmit={submit}><h3>Record disbursement</h3><p>MD approved <strong>{money(row.total_amount)}</strong>. Record the payment after making it through your usual payment method.</p>{error&&<div className="error-banner" role="alert">{error}</div>}<fieldset disabled={busy}><div className="box-form-grid">
    <label>Payment date<DateField required type="date" max={localDate()} value={form.payment_date} onChange={e=>setForm({...form,payment_date:e.target.value})}/></label>
    <label>Payment mode<select value={form.payment_mode} onChange={e=>setForm({...form,payment_mode:e.target.value})}><option value="UPI">UPI</option><option value="CASH">Cash</option><option value="BANK_TRANSFER">Bank transfer</option><option value="CHEQUE">Cheque</option></select></label>
    <label className="box-wide">Paid to<input required maxLength={160} value={form.paid_to} onChange={e=>setForm({...form,paid_to:e.target.value})}/></label>
    <label className="box-wide">Transaction / cheque / cash voucher reference<input required maxLength={160} value={form.payment_reference} onChange={e=>setForm({...form,payment_reference:e.target.value})}/></label>
  </div><button className="primary-button" type="submit">{busy?"Recording…":`Record ${money(row.total_amount)} as disbursed`}</button></fieldset></form>;
}

export default function BoxLoadingWorkspace(){
  const {roles}=useAuth();
  const admin=roles.includes("ADMIN"), md=roles.includes("MD"), allowed=admin||md;
  const [params,setParams]=useSearchParams();
  const selectedId=params.get("request");
  const [items,setItems]=useState([]), [total,setTotal]=useState(0);
  const [filters,setFilters]=useState({from_date:"",to_date:"",status:"",search:""});
  const [applied,setApplied]=useState(filters), [offset,setOffset]=useState(0);
  const [loading,setLoading]=useState(false), [busy,setBusy]=useState(false);
  const [error,setError]=useState(""), [message,setMessage]=useState("");
  const [detail,setDetail]=useState(null), [detailError,setDetailError]=useState("");
  const [editing,setEditing]=useState(null), [creating,setCreating]=useState(false);
  const [detailLoading,setDetailLoading]=useState(false);
  const requestSequence=useRef(0), detailSequence=useRef(0), mutationBusy=useRef(false);
  const formRef=useRef(null), detailRef=useRef(null);
  const load=useCallback(async()=>{
    if(!allowed)return;
    const sequence=++requestSequence.current;setLoading(true);setError("");
    try{const query=new URLSearchParams({offset:String(offset),limit:"25"});Object.entries(applied).forEach(([k,v])=>{if(v)query.set(k,v);});const data=await apiRequest(`${API}?${query}`);if(sequence!==requestSequence.current)return;setItems(data.items);setTotal(data.total);}
    catch(err){if(sequence===requestSequence.current){setError(err.message);setItems([]);setTotal(0);}}
    finally{if(sequence===requestSequence.current)setLoading(false);}
  },[allowed,applied,offset]);
  const loadDetail=useCallback(async()=>{
    const sequence=++detailSequence.current;
    if(!selectedId||!allowed){setDetail(null);setDetailLoading(false);return;}
    setDetailLoading(true);setDetail(null);setDetailError("");
    try{const row=await apiRequest(`${API}/${encodeURIComponent(selectedId)}`);if(sequence===detailSequence.current)setDetail(row);}
    catch(err){if(sequence===detailSequence.current)setDetailError(err.message);}
    finally{if(sequence===detailSequence.current)setDetailLoading(false);}
  },[selectedId,allowed]);
  useEffect(()=>{load();return()=>{requestSequence.current++;};},[load]);
  useEffect(()=>{loadDetail();return()=>{detailSequence.current++;};},[loadDetail]);
  useEffect(()=>{if(creating||editing)formRef.current?.scrollIntoView({behavior:"smooth",block:"start"});},[creating,editing]);
  useEffect(()=>{if(selectedId)detailRef.current?.scrollIntoView({behavior:"smooth",block:"start"});},[selectedId]);
  function closeDetail(){setParams({}, {replace:true});setDetail(null);setDetailError("");}
  async function mutate(work){
    if(mutationBusy.current)throw new Error("Please wait for the current action to finish.");
    mutationBusy.current=true;setBusy(true);setMessage("");
    try{return await work();}finally{mutationBusy.current=false;setBusy(false);}
  }
  async function save(payload,id){return mutate(async()=>{
    const row=await apiRequest(id?`${API}/${id}`:API,{method:id?"PUT":"POST",body:payload});
    setCreating(false);setEditing(null);setParams({request:row.id});setMessage("Draft saved successfully. Review it and select Send to MD for approval.");await load();
  });}
  async function action(row,endpoint,payload,success){return mutate(async()=>{
    await apiRequest(`${API}/${row.id}/${endpoint}`,{method:"POST",body:{expected_version:row.version,...payload}});
    setMessage(success);window.dispatchEvent(new Event("action-alerts:refresh"));await Promise.all([load(),loadDetail()]);
  });}
  async function submitToMd(row){setDetailError("");try{await action(row,"submit",{},"Sent to MD for approval. Costs are locked until a decision is made.");}catch(err){setDetailError(err.message);}}
  function startEdit(row){closeDetail();setCreating(false);setEditing(row);setMessage("");}
  if(!allowed)return <div className="page"><div className="empty-state">Box Loading is available to Admin and MD.</div></div>;
  return <div className="page box-loading-page">
    <header className="page-header"><div><span className="eyebrow">Operations</span><h1>Box Loading</h1><p>Loading and transport costs, MD sanction and disbursement records.</p></div><div className="box-buttons"><button type="button" className="secondary-button" disabled={loading||busy} onClick={()=>{load();loadDetail();}}>Refresh</button>{admin&&<button type="button" className="primary-button" disabled={busy||creating||Boolean(editing)} onClick={()=>{closeDetail();setCreating(true);setMessage("");}}>+ New loading record</button>}</div></header>
    {message&&<div className="box-success" role="status">{message}<button type="button" aria-label="Dismiss success message" onClick={()=>setMessage("")}>×</button></div>}
    {error&&<div className="error-banner" role="alert">{error}</div>}
    {(creating||editing)&&<section className="panel box-editor" ref={formRef}><div className="panel-header"><h2>{editing?"Edit loading record":"New loading record"}</h2></div><LoadingForm key={editing?.id||"new"} record={editing} onSave={save} busy={busy} onCancel={()=>{setCreating(false);setEditing(null);}}/></section>}
    {selectedId&&<section className="panel box-detail" ref={detailRef} aria-label="Selected loading request"><div className="panel-header"><h2>Request details</h2><button type="button" className="secondary-button" disabled={busy} onClick={closeDetail}>Close details</button></div>
      {detailLoading&&<p role="status">Loading request…</p>}{detailError&&<div className="error-banner" role="alert">{detailError}</div>}
      {detail&&<><div className="box-record-heading"><div><span className="eyebrow">{detail.reference}</span><h3>{detail.vehicle_number}</h3><p>{detail.vehicle_type==="OWN"?"Own vehicle":"Rented vehicle"} · {dateText(detail.loading_date)}</p></div><span className={`box-status box-status-${detail.status.toLowerCase()}`}>{statusLabels[detail.status]}</span></div>
        <CostBreakdown row={detail}/><FinancialDownload kind="box-loading" recordId={detail.id}/>{detail.notes&&<p className="box-notes">{detail.notes}</p>}
        <dl className="box-metadata"><div><dt>Created by</dt><dd>{detail.created_by_code} · {timeText(detail.created_at)}</dd></div>{detail.submitted_at&&<div><dt>Submitted by</dt><dd>{detail.submitted_by_code} · {timeText(detail.submitted_at)}</dd></div>}{detail.decided_at&&<div><dt>MD decision</dt><dd>{detail.md_code} · {timeText(detail.decided_at)}{detail.decision_note&&<p>{detail.decision_note}</p>}</dd></div>}</dl>
        {admin&&["DRAFT","REJECTED"].includes(detail.status)&&<div className="box-buttons"><button type="button" className="secondary-button" disabled={busy} onClick={()=>startEdit(detail)}>Edit record</button>{detail.status==="DRAFT"&&<button type="button" className="primary-button" disabled={busy} onClick={()=>submitToMd(detail)}>{busy?"Submitting…":"Send to MD for approval"}</button>}</div>}
        {detail.status==="PENDING_MD"&&(md?<DecisionForm key={`${detail.id}:${detail.version}`} row={detail} busy={busy} onAction={action}/>:<p className="box-info">Awaiting MD approval. Disbursement is unavailable.</p>)}
        {detail.status==="REJECTED"&&admin&&<p className="box-info">Edit and save this request as a draft before sending it to MD again.</p>}
        {detail.status==="APPROVED"&&(admin?<PaymentForm key={`${detail.id}:${detail.version}`} row={detail} busy={busy} onAction={action}/>:<p className="box-info">Approved. Awaiting Admin's disbursement record.</p>)}
        {detail.status==="PAID"&&<section className="box-paid"><h3>Disbursement recorded</h3><dl className="box-metadata"><div><dt>Amount</dt><dd>{money(detail.paid_amount)}</dd></div><div><dt>Paid to</dt><dd>{detail.paid_to}</dd></div><div><dt>Payment date / mode</dt><dd>{dateText(detail.payment_date)} · {detail.payment_mode.replaceAll("_"," ")}</dd></div><div><dt>Reference</dt><dd>{detail.payment_reference}</dd></div><div><dt>Recorded by</dt><dd>{detail.paid_by_code} · {timeText(detail.paid_at)}</dd></div></dl></section>}
        <details className="box-history"><summary>Approval and payment history ({detail.actions.length})</summary><ol>{detail.actions.map(item=><li key={item.id}><strong>{item.action.replaceAll("_"," ")} · {item.actor_code}</strong><small>{timeText(item.created_at)}</small>{item.note&&<p>{item.note}</p>}<details><summary>Amounts at this step</summary><p>{item.snapshot.vehicle_number} · {dateText(item.snapshot.loading_date)}</p><CostBreakdown row={item.snapshot}/></details></li>)}</ol></details>
      </>}
    </section>}
    <section className="panel"><div className="panel-header"><h2>Loading register</h2><span className="muted">{total} record{total===1?"":"s"}</span></div>
      <form className="box-filters" onSubmit={e=>{e.preventDefault();setOffset(0);setApplied({...filters});}}><label>From date<DateField type="date" value={filters.from_date} onChange={e=>setFilters({...filters,from_date:e.target.value})}/></label><label>To date<DateField type="date" value={filters.to_date} onChange={e=>setFilters({...filters,to_date:e.target.value})}/></label><label>Status<select value={filters.status} onChange={e=>setFilters({...filters,status:e.target.value})}><option value="">All statuses</option>{Object.entries(statusLabels).map(([key,value])=><option key={key} value={key}>{value}</option>)}</select></label><label>Search<input maxLength={100} placeholder="Vehicle number or Admin code" value={filters.search} onChange={e=>setFilters({...filters,search:e.target.value})}/></label><button type="submit" className="secondary-button" disabled={busy||loading}>Apply filters</button><button type="button" className="link-button" disabled={busy||loading} onClick={()=>{const empty={from_date:"",to_date:"",status:"",search:""};setFilters(empty);setApplied(empty);setOffset(0);}}>Clear filters</button></form>
      {loading?<p role="status">Loading records…</p>:items.length===0?<div className="empty-state">{error?"Unable to load the register. Try Refresh.":"No loading records match these filters."}</div>:<div className="box-records">{items.map(row=><article className="box-record" key={row.id}><div className="box-record-heading"><div><span className="eyebrow">{row.reference}</span><h3>{row.vehicle_number}</h3><p>{dateText(row.loading_date)} · {row.vehicle_type==="OWN"?"Own vehicle":"Rented vehicle"}</p></div><span className={`box-status box-status-${row.status.toLowerCase()}`}>{statusLabels[row.status]}</span></div><CostBreakdown row={row}/><div className="box-record-footer"><small>Created by {row.created_by_code}</small><button type="button" className="secondary-button" disabled={busy} onClick={()=>{setParams({request:row.id});setCreating(false);setEditing(null);}}>View request</button></div></article>)}</div>}
      <div className="box-pagination"><button className="secondary-button" type="button" disabled={busy||loading||offset===0} onClick={()=>setOffset(Math.max(0,offset-25))}>Previous</button><span>{total?`${offset+1}–${Math.min(offset+25,total)} of ${total}`:"0 records"}</span><button type="button" className="secondary-button" disabled={busy||loading||offset+25>=total} onClick={()=>setOffset(offset+25)}>Next</button></div>
    </section>
  </div>;
}

// financial-records-update-v1
// date-display-ddmmyyyy-v1
