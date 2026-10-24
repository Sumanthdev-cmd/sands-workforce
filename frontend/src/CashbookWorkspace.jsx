import DateField from "./DateField";
import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {useEffect,useRef,useState} from 'react';
import {useAuth} from './context/AuthContext';
import {apiRequest,uploadWithProgress} from './lib/api';
import './cashbook.css';
const today=()=>{const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-')};
const initial=()=>({transaction_date:today(),direction:'DEBIT',amount:'',organization_account:'',payment_mode:'CASH',counterparty:'',counterparty_account:'',payment_reference:'',notes:''});
const money=v=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(Number(v));
export default function CashbookWorkspace(){
 const {roles}=useAuth();const allowed=roles.some(r=>['CASHIER','ADMIN','MD'].includes(r));
 const [form,setForm]=useState(initial),[file,setFile]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [data,setData]=useState({items:[],total:0,totals:{credit:'0',debit:'0'}}),[loading,setLoading]=useState(false),[filters,setFilters]=useState({from_date:'',to_date:'',direction:''}),[page,setPage]=useState(0),[refresh,setRefresh]=useState(0);
 const [preview,setPreview]=useState(null),[voidRow,setVoidRow]=useState(null),[reason,setReason]=useState('');
 const request=useRef(crypto.randomUUID()),uploaded=useRef(null),fileInput=useRef(null),saving=useRef(false);
 useEffect(()=>{if(!allowed)return;let live=true;setLoading(true);const q=new URLSearchParams({offset:String(page*25),limit:'25'});Object.entries(filters).forEach(([k,v])=>{if(v)q.set(k,v)});apiRequest('/cashbook/entries?'+q).then(r=>{if(live)setData(r)}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setLoading(false)});return()=>{live=false}},[allowed,filters,page,refresh]);
 const set=(k,v)=>setForm(p=>({...p,[k]:v}));
 async function save(e){e.preventDefault();if(saving.current)return;saving.current=true;setBusy(true);setError('');setNotice('');
 try{
  if(file&&!uploaded.current){
   if(!['application/pdf','image/jpeg','image/png','image/webp'].includes(file.type)||file.size>10000000)throw new Error('Choose a PDF, JPG, PNG or WebP up to 10 MB.');
   const pre=await apiRequest('/documents/presign-upload',{method:'POST',body:{owner_type:'EMPLOYEE',category:'CASHBOOK',title:'Credit/debit supporting document',file_name:file.name,content_type:file.type,file_size:file.size,is_confidential:true}});
   const etag=await uploadWithProgress(pre.upload_url,file,file.type);
   await apiRequest(`/documents/${pre.document_id}/complete`,{method:'POST',body:{etag:etag?etag.replaceAll('"',''):null}});uploaded.current=pre.document_id;
  }
  const row=await apiRequest('/cashbook/entries',{method:'POST',body:{...form,client_request_id:request.current,document_id:uploaded.current}});
  setNotice(`${row.reference}: ${form.direction==='CREDIT'?'Credit':'Debit'} of ${money(row.amount)} recorded successfully.`);
  request.current=crypto.randomUUID();uploaded.current=null;setForm(initial());setFile(null);if(fileInput.current)fileInput.current.value='';setPage(0);setRefresh(x=>x+1);
 }catch(e){setError(e.message)}finally{saving.current=false;setBusy(false)}}
 async function openDocument(row){setError('');try{const result=await apiRequest(`/cashbook/entries/${row.id}/document`);if(!result.download_url)throw new Error('Document preview is unavailable.');setPreview({url:result.download_url,reference:row.reference})}catch(e){setError(e.message)}}
 async function voidEntry(e){e.preventDefault();if(saving.current)return;saving.current=true;setBusy(true);setError('');try{await apiRequest(`/cashbook/entries/${voidRow.id}/void`,{method:'POST',body:{reason}});setVoidRow(null);setReason('');setNotice('Record voided. The original entry and reason remain in the register.');setRefresh(x=>x+1)}catch(e){setError(e.message)}finally{saving.current=false;setBusy(false)}}
 if(!allowed)return <div className="page"><h1>Credit/Debit Record</h1><p>Cashier, Admin or MD access is required.</p></div>;
 return <div className="page cashbook"><header className="page-header"><div><span className="eyebrow">Cashier workspace</span><h1>Credit/Debit Record</h1><p>Record money received and paid. Amounts are in INR. This register does not initiate payments.</p></div></header>
 {error&&<div className="error-banner" role="alert">{error}</div>}{notice&&<div className="success-banner" role="status">{notice}</div>}
 <section className="panel"><h2>Add transaction</h2><form onSubmit={save}><fieldset disabled={busy}><div className="cashbook-grid">
 <label>Date<DateField required type="date" max={today()} value={form.transaction_date} onChange={e=>set('transaction_date',e.target.value)}/></label>
 <label>Transaction type<select value={form.direction} onChange={e=>set('direction',e.target.value)}><option value="DEBIT">Debit — money paid out</option><option value="CREDIT">Credit — money received</option></select></label>
 <label>Amount (₹)<input required type="number" min="0.01" max="99999999999999.99" step="0.01" inputMode="decimal" value={form.amount} onChange={e=>set('amount',e.target.value)}/></label>
 <label>{form.direction==='CREDIT'?'Organisation account receiving money':'Organisation account paying money'}<input required maxLength={160} placeholder="e.g. Office cash or SBI current account •1234" value={form.organization_account} onChange={e=>set('organization_account',e.target.value)}/></label>
 <label>Payment mode<select value={form.payment_mode} onChange={e=>set('payment_mode',e.target.value)}>{[['CASH','Cash'],['UPI','UPI'],['BANK_TRANSFER','Bank transfer'],['CHEQUE','Cheque'],['CARD','Card'],['OTHER','Other']].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label>
 <label>{form.direction==='CREDIT'?'Received from':'Paid to'}<input required maxLength={160} value={form.counterparty} onChange={e=>set('counterparty',e.target.value)}/></label>
 <label>{form.direction==='CREDIT'?'Sender account number (optional)':'Recipient account number (optional)'}<input type="text" maxLength={64} value={form.counterparty_account} onChange={e=>set('counterparty_account',e.target.value)}/></label>
 <label>Transaction / cheque reference (optional)<input maxLength={160} value={form.payment_reference} onChange={e=>set('payment_reference',e.target.value)}/></label>
 <label>Supporting document (optional)<input ref={fileInput} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={e=>{setFile(e.target.files?.[0]||null);uploaded.current=null}}/><small>PDF or image, maximum 10 MB.</small></label>
 <label>Purpose / notes (optional)<textarea maxLength={2000} value={form.notes} onChange={e=>set('notes',e.target.value)}/></label>
 </div><button className="primary-button" type="submit">{busy?'Saving…':'Save transaction'}</button></fieldset></form></section>
 <section className="panel"><h2>Transaction register</h2><p>{data.management?'All cashiers in your organisation.':'Your recorded transactions.'} Voided records are excluded from totals.</p>
 <div className="cashbook-grid"><label>From<DateField type="date" value={filters.from_date} onChange={e=>{setFilters({...filters,from_date:e.target.value});setPage(0)}}/></label><label>To<DateField type="date" value={filters.to_date} onChange={e=>{setFilters({...filters,to_date:e.target.value});setPage(0)}}/></label><label>Type<select value={filters.direction} onChange={e=>{setFilters({...filters,direction:e.target.value});setPage(0)}}><option value="">All transactions</option><option value="CREDIT">Credit</option><option value="DEBIT">Debit</option></select></label></div>
 <div className="cashbook-totals"><span>Credits in filter <strong>{money(data.totals.credit)}</strong></span><span>Debits in filter <strong>{money(data.totals.debit)}</strong></span><button className="secondary-button" onClick={()=>setRefresh(x=>x+1)}>Refresh</button></div>
 {loading?<p>Loading records…</p>:!data.items.length?<p>No transactions match these filters.</p>:<div className="cashbook-records">{data.items.map(row=><article key={row.id}><div className="cashbook-row"><strong>{row.reference}</strong><b>{row.direction} {money(row.amount)}</b></div><dl>{[['Date',row.transaction_date],['Organisation account',row.organization_account],[row.direction==='CREDIT'?'Received from':'Paid to',row.counterparty],['Payment mode',row.payment_mode.replaceAll('_',' ')],['Counterparty account',row.counterparty_account],['Payment reference',row.payment_reference],['Notes',row.notes],['Recorded by',row.created_by_code],['Recorded at',new Date(row.created_at).toLocaleString("en-GB",dateOptions({},true))]].filter(([,v])=>v).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>{row.voided_at?<p className="cashbook-void">Voided: {row.void_reason} · {new Date(row.voided_at).toLocaleString("en-GB",dateOptions({},true))}</p>:<button className="secondary-button" onClick={()=>{setVoidRow(row);setReason('')}}>Void incorrect record</button>}{row.document_id&&<button className="secondary-button" onClick={()=>openDocument(row)}>View supporting document</button>}</article>)}</div>}
 <div className="cashbook-row"><button disabled={!page||loading} onClick={()=>setPage(p=>p-1)}>Previous</button><span>Page {page+1} · {data.total} records</span><button disabled={(page+1)*25>=data.total||loading} onClick={()=>setPage(p=>p+1)}>Next</button></div></section>
 {voidRow&&<div className="cashbook-overlay"><section role="dialog" aria-modal="true" aria-label="Void record"><h2>Void {voidRow.reference}</h2>{error&&<div role="alert" className="error-banner">{error}</div>}<p>The original record remains visible. You can create a replacement after voiding.</p><form onSubmit={voidEntry}><label>Reason<textarea required minLength={3} maxLength={2000} value={reason} onChange={e=>setReason(e.target.value)}/></label><button disabled={busy} className="primary-button">{busy?'Saving…':'Confirm void'}</button><button disabled={busy} type="button" className="secondary-button" onClick={()=>setVoidRow(null)}>Cancel</button></form></section></div>}
 {preview&&<div className="cashbook-overlay"><section role="dialog" aria-modal="true" aria-label="Supporting document"><div className="cashbook-row"><h2>{preview.reference} document</h2><button onClick={()=>setPreview(null)}>Close</button></div><a href={preview.url} target="_blank" rel="noopener noreferrer">Open document in a new tab</a><iframe title="Supporting document" src={preview.url}/><p>If this file cannot be previewed, use the link above.</p></section></div>}
 </div>
}
// date-display-ddmmyyyy-v1
