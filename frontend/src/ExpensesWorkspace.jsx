import DateField from "./DateField";
import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {useEffect,useMemo,useRef,useState} from "react";
import {useLocation} from "react-router-dom";
import {useAuth} from "./context/AuthContext";
import {apiRequest,uploadWithProgress} from "./lib/api";

const VERIFIERS=["ADMIN","GM","MANAGER","MD"];
const PAYERS=["ADMIN","MD"];
const CATEGORIES=["TRAVEL","DAILY_ALLOWANCE","LODGING","FOOD","FUEL","TOLL","PARKING","LOCAL_TRANSPORT","OTHER"];
const today=()=>new Date(Date.now()+330*60*1000).toISOString().slice(0,10);
function expenseWindow(){
  const max=today();
  const min=new Date(Date.parse(`${max}T00:00:00Z`)-2*86400000).toISOString().slice(0,10);
  return {min,max};
}
function expenseDateError(items){
  const {min,max}=expenseWindow();
  return items.some(i=>!i.expense_date||i.expense_date<min||i.expense_date>max)
    ?`Each expense date must be between ${min} and ${max}. Submit within two calendar days after the expense date (India time). Future dates are not allowed.`:"";
}
const newItem=()=>({expense_date:today(),category:"TRAVEL",description:"",quantity:"1",rate:"",receipt:null});
const freshForm=()=>({claim_type:"TA_DA",title:"",purpose:"",travel_start_date:"",travel_end_date:"",origin:"",destination:"",currency:"INR",items:[newItem()],claimFiles:[]});

function pretty(v){return String(v||"").replaceAll("_"," ").toLowerCase().replace(/\b\w/g,c=>c.toUpperCase())}
function amount(i){return Math.round(Number(i.quantity||0)*Number(i.rate||0)*100)/100}
function money(v,c="INR"){try{return new Intl.NumberFormat("en-IN",{style:"currency",currency:c||"INR",maximumFractionDigits:2}).format(Number(v||0))}catch{return `${c||"INR"} ${Number(v||0).toFixed(2)}`}}
function errText(e){const v=e?.detail??e?.message??e;if(typeof v==="string")return v==="[object Object]"?"The request could not be completed.":v;if(Array.isArray(v))return v.map(x=>x?.msg||"Invalid information.").join(" ");return "The request could not be completed."}
function Status({value}){return <span className={`outlet-state ${String(value||"").toLowerCase()}`}>{pretty(value)}</span>}

export default function ExpensesWorkspace(){
  const {roles=[]}=useAuth();
  const location=useLocation();
  const canVerify=roles.some(r=>VERIFIERS.includes(r));
  const isMD=roles.includes("MD");
  const canPay=roles.some(r=>PAYERS.includes(r));

  const [mine,setMine]=useState([]);
  const [pending,setPending]=useState([]);
  const [selected,setSelected]=useState(null);
  const [actions,setActions]=useState([]);
  const [documents,setDocuments]=useState([]);
  const [showCreate,setShowCreate]=useState(false);
  const [form,setForm]=useState(freshForm);
  const [review,setReview]=useState({verified_amount:"",verification_note:"",approved_amount:"",approval_note:"",rejection_reason:"",payment_reference:"",payment_note:""});
  const [busy,setBusy]=useState(false);
  const [documentAction,setDocumentAction]=useState("");
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [progress,setProgress]=useState({});
  const lock=useRef(false);
  const pendingRef=useRef(null);
  const detailRef=useRef(null);

  async function load(){
    const [a,b]=await Promise.all([
      apiRequest("/expenses/claims/me").catch(()=>[]),
      (canVerify||isMD||canPay)?apiRequest("/expenses/claims/pending").catch(()=>[]):Promise.resolve([])
    ]);
    setMine(Array.isArray(a)?a:[]);
    setPending(Array.isArray(b)?b:[]);
  }

  useEffect(()=>{load().catch(e=>setError(errText(e)))},[]);

  useEffect(()=>{
    const params=new URLSearchParams(location.search);
    const claimId=params.get("claim");
    if(claimId){
      openClaim(claimId).then(()=>window.setTimeout(()=>detailRef.current?.scrollIntoView({behavior:"smooth",block:"start"}),120));
    }else if(params.get("queue")==="1"&&(canVerify||isMD||canPay)){
      window.setTimeout(()=>pendingRef.current?.scrollIntoView({behavior:"smooth",block:"start"}),120);
    }
  },[location.search]);

  const total=useMemo(()=>form.items.reduce((s,i)=>s+amount(i),0),[form.items]);
  const drafts=mine.filter(x=>x.status==="DRAFT").length;
  const dateWindow=expenseWindow();
  const draftDateError=selected?.status==="DRAFT"?expenseDateError(selected.items||[]):"";

  function updateItem(index,patch){
    setForm(f=>({...f,items:f.items.map((item,i)=>i===index?{...item,...patch}:item)}));
  }
  function addItem(){setForm(f=>({...f,items:[...f.items,newItem()]}))}
  function removeItem(index){setForm(f=>({...f,items:f.items.length===1?f.items:f.items.filter((_,i)=>i!==index)}))}

  async function uploadFile(claim,file,title,extraData,key){
    const contentType=file.type||"application/octet-stream";
    const pre=await apiRequest("/documents/presign-upload",{method:"POST",body:{
      owner_type:"EXPENSE",
      owner_id:claim.id,
      category:"EXPENSE_RECEIPT",
      title,
      description:`Supporting document for ${claim.claim_number}`,
      issue_date:null,
      expiry_date:null,
      alert_days_before:30,
      is_confidential:true,
      file_name:file.name,
      content_type:contentType,
      file_size:file.size,
      extra_data:{claim_number:claim.claim_number,...extraData}
    }});
    const etag=await uploadWithProgress(pre.upload_url,file,contentType,p=>setProgress(old=>({...old,[key]:p})));
    await apiRequest(`/documents/${pre.document_id}/complete`,{method:"POST",body:{etag:etag?etag.replaceAll('"',""):null}});
  }

  async function uploadDocuments(claim){
    const failures=[];
    for(let i=0;i<form.items.length;i++){
      const item=form.items[i];
      if(!item.receipt)continue;
      try{
        await uploadFile(claim,item.receipt,`${claim.claim_number} - ${pretty(item.category)} Receipt`,{
          item_index:i,expense_date:item.expense_date,expense_category:item.category
        },`item-${i}`);
      }catch(e){failures.push(`${pretty(item.category)} receipt: ${errText(e)}`)}
    }
    for(let i=0;i<form.claimFiles.length;i++){
      const file=form.claimFiles[i];
      try{
        await uploadFile(claim,file,`${claim.claim_number} - Supporting Document ${i+1}`,{attachment_type:"CLAIM_SUPPORT"},`claim-${i}`);
      }catch(e){failures.push(`${file.name}: ${errText(e)}`)}
    }
    return failures;
  }

  async function createClaim(e){
    e.preventDefault();
    if(lock.current)return;
    const dateError=expenseDateError(form.items);
    if(dateError){setError(dateError);return}
    if(form.claim_type==="TA_DA"&&(!form.travel_start_date||!form.travel_end_date)){setError("TA/DA claims require travel start and end dates.");return}
    if(total<=0){setError("Claim amount must be greater than zero.");return}

    lock.current=true;setBusy(true);setError("");setMessage("");setProgress({});
    try{
      const claim=await apiRequest("/expenses/claims",{method:"POST",body:{
        claim_type:form.claim_type,
        title:form.title.trim(),
        purpose:form.purpose.trim(),
        travel_start_date:form.travel_start_date||null,
        travel_end_date:form.travel_end_date||null,
        origin:form.origin.trim()||null,
        destination:form.destination.trim()||null,
        currency:form.currency.trim().toUpperCase(),
        evidence_urls:[],
        items:form.items.map(i=>({
          expense_date:i.expense_date,
          category:i.category,
          description:i.description.trim(),
          quantity:Number(i.quantity),
          rate:Number(i.rate||0),
          amount:amount(i),
          evidence_urls:[]
        }))
      }});

      const failures=await uploadDocuments(claim);
      setForm(freshForm());setShowCreate(false);
      if(failures.length){setMessage(`Draft ${claim.claim_number} created, but some receipts failed.`);setError(failures.join(" | "))}
      else setMessage(`Draft ${claim.claim_number} created successfully.`);
      await load();await openClaim(claim.id);
    }catch(e){setError(errText(e))}
    finally{lock.current=false;setBusy(false);setProgress({})}
  }

  async function openClaim(id){
    setError("");
    try{
      const [claim,history,docs]=await Promise.all([
        apiRequest(`/expenses/claims/${id}`),
        apiRequest(`/expenses/claims/${id}/actions`).catch(()=>[]),
        apiRequest(`/documents?owner_type=EXPENSE&owner_id=${id}`).catch(()=>[])
      ]);
      setSelected(claim);
      setActions(Array.isArray(history)?history:[]);
      setDocuments(Array.isArray(docs)?docs:[]);
      setReview({
        verified_amount:claim.verified_amount??claim.claimed_amount??"",
        verification_note:claim.verification_note||"",
        approved_amount:claim.approved_amount??claim.verified_amount??claim.claimed_amount??"",
        approval_note:claim.approval_note||"",
        rejection_reason:"",
        payment_reference:claim.payment_reference||"",
        payment_note:""
      });
    }catch(e){setError(errText(e))}
  }

  async function act(success,path,body){
    if(!selected||lock.current)return;
    lock.current=true;setBusy(true);setError("");setMessage("");
    try{
      await apiRequest(path,{method:"POST",...(body===undefined?{}:{body})});
      setMessage(success);window.dispatchEvent(new Event("action-alerts:refresh"));await load();await openClaim(selected.id);
    }catch(e){setError(errText(e))}
    finally{lock.current=false;setBusy(false)}
  }

  async function openDocument(file,mode){
    const actionKey=`${file.id}:${mode}`;
    const previewWindow=mode==="preview"?window.open("about:blank","_blank"):null;
    setDocumentAction(actionKey);setError("");
    try{
      const data=await apiRequest(`/documents/${file.id}/${mode}-url`);
      if(!data?.download_url)throw new Error("The document link was not returned.");

      if(mode==="preview"){
        if(previewWindow){previewWindow.opener=null;previewWindow.location.href=data.download_url}
        else window.open(data.download_url,"_blank","noopener,noreferrer");
      }else{
        const link=window.document.createElement("a");
        link.href=data.download_url;
        link.download=file.file_name||"supporting-document";
        link.rel="noopener noreferrer";
        window.document.body.appendChild(link);
        link.click();
        link.remove();
      }
    }catch(e){
      if(previewWindow)previewWindow.close();
      setError(`Unable to ${mode} ${file.file_name}: ${errText(e)}`);
    }finally{
      setDocumentAction("");
    }
  }

  function submitClaim(){
    const dateError=expenseDateError(selected.items||[]);
    if(dateError){setError(dateError);return}
    return act("Claim submitted for verification.",`/expenses/claims/${selected.id}/submit`);
  }
  function verifyClaim(){return act("Claim verified.",`/expenses/claims/${selected.id}/verify`,{verified_amount:review.verified_amount===""?null:Number(review.verified_amount),note:review.verification_note.trim()||null})}
  function approveClaim(){return act("Claim approved.",`/expenses/claims/${selected.id}/approve`,{approved_amount:review.approved_amount===""?null:Number(review.approved_amount),note:review.approval_note.trim()||null})}
  function rejectClaim(){if(review.rejection_reason.trim().length<3){setError("Enter a rejection reason of at least 3 characters.");return}return act("Claim rejected.",`/expenses/claims/${selected.id}/reject`,{reason:review.rejection_reason.trim()})}
  function markPaid(){if(review.payment_reference.trim().length<2){setError("Enter the payment reference.");return}return act("Claim marked as paid.",`/expenses/claims/${selected.id}/mark-paid`,{payment_reference:review.payment_reference.trim(),note:review.payment_note.trim()||null})}

  return <div className="page expenses-workspace">
    <header className="page-header">
      <div>
        <span className="eyebrow">Expenses & TA/DA</span>
        <h1>Expense Claims</h1>
        <p>Submit expenses, attach receipts, verify, approve and record payment without typing internal IDs.</p>
      </div>
      <div className="header-actions">
        <button type="button" className="primary-button" disabled={busy} onClick={()=>setShowCreate(v=>!v)}>{showCreate?"Close New Claim":"+ New Expense Claim"}</button>
        <button type="button" className="secondary-button" disabled={busy} onClick={()=>load().catch(e=>setError(errText(e)))}>Refresh</button>
      </div>
    </header>

    {error&&<div className="error-banner">{error}</div>}
    {message&&<div className="success-banner">✅ {message}</div>}

    <div className="outlet-summary-grid">
      <div><small>My claims</small><strong>{mine.length}</strong></div>
      <div><small>My drafts</small><strong>{drafts}</strong></div>
      <div><small>Pending review</small><strong>{pending.length}</strong></div>
      <div><small>Workflow</small><strong>Draft → Submit → Verify → Approve → Paid</strong></div>
    </div>

    {showCreate&&<section className="panel">
      <div className="panel-header">
        <div><h2>New Expense / TA-DA Claim</h2><p>Receipts are linked to the generated claim automatically.</p></div>
        <strong>Total: {money(total,form.currency)}</strong>
      </div>

      <form className="document-form" onSubmit={createClaim}>
        <p className="muted">Submit each expense within two calendar days after its date (India time). Allowed expense dates today: {dateWindow.min} to {dateWindow.max}. Saving a draft does not extend the deadline.</p>
        <div className="form-grid">
          <label>Claim Type *<select required disabled={busy} value={form.claim_type} onChange={e=>setForm({...form,claim_type:e.target.value})}><option value="TA_DA">TA / DA</option><option value="GENERAL_EXPENSE">General Expense</option></select></label>
          <label>Currency *<input required maxLength="10" disabled={busy} value={form.currency} onChange={e=>setForm({...form,currency:e.target.value.toUpperCase()})}/></label>
          <label>Title *<input required minLength="3" maxLength="200" disabled={busy} value={form.title} onChange={e=>setForm({...form,title:e.target.value})}/></label>
          <label>Origin<input maxLength="200" disabled={busy} value={form.origin} onChange={e=>setForm({...form,origin:e.target.value})}/></label>
          <label>Destination<input maxLength="200" disabled={busy} value={form.destination} onChange={e=>setForm({...form,destination:e.target.value})}/></label>
          <label>Travel Start {form.claim_type==="TA_DA"?"*":""}<DateField required={form.claim_type==="TA_DA"} type="date" disabled={busy} value={form.travel_start_date} onChange={e=>setForm({...form,travel_start_date:e.target.value})}/></label>
          <label>Travel End {form.claim_type==="TA_DA"?"*":""}<DateField required={form.claim_type==="TA_DA"} type="date" min={form.travel_start_date||undefined} disabled={busy} value={form.travel_end_date} onChange={e=>setForm({...form,travel_end_date:e.target.value})}/></label>
        </div>

        <label>Purpose *<textarea required minLength="3" maxLength="5000" rows="3" disabled={busy} value={form.purpose} onChange={e=>setForm({...form,purpose:e.target.value})}/></label>

        <div className="panel-header">
          <div><h3>Expense Items</h3><p>Amount = Quantity × Rate.</p></div>
          <button type="button" className="secondary-button" disabled={busy||form.items.length>=200} onClick={addItem}>+ Add Item</button>
        </div>

        <div className="simple-list">
          {form.items.map((item,index)=><article className="subpanel" key={index}>
            <div className="panel-header">
              <div><strong>Item {index+1}</strong><p className="muted">{money(amount(item),form.currency)}</p></div>
              {form.items.length>1&&<button type="button" className="link-button danger" disabled={busy} onClick={()=>removeItem(index)}>Remove</button>}
            </div>

            <div className="form-grid">
              <label>Expense Date *<DateField required type="date" min={dateWindow.min} max={dateWindow.max} disabled={busy} value={item.expense_date} onChange={e=>updateItem(index,{expense_date:e.target.value})}/></label>
              <label>Category *<select required disabled={busy} value={item.category} onChange={e=>updateItem(index,{category:e.target.value})}>{CATEGORIES.map(c=><option key={c} value={c}>{pretty(c)}</option>)}</select></label>
              <label>Quantity *<input required type="number" min="0.01" step="0.01" disabled={busy} value={item.quantity} onChange={e=>updateItem(index,{quantity:e.target.value})}/></label>
              <label>Rate *<input required type="number" min="0" step="0.01" disabled={busy} value={item.rate} onChange={e=>updateItem(index,{rate:e.target.value})}/></label>
            </div>

            <label>Description *<textarea required minLength="2" maxLength="2000" rows="2" disabled={busy} value={item.description} onChange={e=>updateItem(index,{description:e.target.value})}/></label>

            <label className="file-drop">Receipt / Evidence<input type="file" accept=".pdf,image/*" disabled={busy} onChange={e=>updateItem(index,{receipt:e.target.files?.[0]||null})}/><span>{item.receipt?`${item.receipt.name} · ${Math.round(item.receipt.size/1024)} KB`:"Optional PDF or image"}</span></label>
            {progress[`item-${index}`]>0&&<div className="progress-bar"><span style={{width:`${progress[`item-${index}`]}%`}}/></div>}
          </article>)}
        </div>

        <label className="file-drop">Additional Claim Documents<input type="file" multiple accept=".pdf,image/*" disabled={busy} onChange={e=>setForm({...form,claimFiles:Array.from(e.target.files||[])})}/><span>{form.claimFiles.length?`${form.claimFiles.length} file(s) selected`:"Optional tickets, hotel bills or supporting documents"}</span></label>

        <button className="primary-button" disabled={busy||total<=0}>{busy?"Saving Draft…":`Save Draft · ${money(total,form.currency)}`}</button>
      </form>
    </section>}

    <section className="panel">
      <div className="panel-header"><div><h2>My Claims</h2><p>Select a claim by number/title. No Claim ID is typed.</p></div></div>
      <div className="simple-list">
        {mine.length===0?<div className="empty-state">No expense claims yet.</div>:mine.map(c=><button type="button" className={`simple-row ${selected?.id===c.id?"selected":""}`} key={c.id} onClick={()=>openClaim(c.id)}>
          <div><strong>{c.claim_number} · {c.title}</strong><span>{pretty(c.claim_type)} · {money(c.claimed_amount,c.currency)} · {c.created_at?new Date(c.created_at).toLocaleString("en-GB",dateOptions({},true)):""}</span></div>
          <Status value={c.status}/>
        </button>)}
      </div>
    </section>

    {(canVerify||isMD||canPay)&&<section className="panel" ref={pendingRef}>
      <div className="panel-header"><div><h2>Pending Claims</h2><p>{pending.length} claim(s) awaiting action.</p></div>{pending.length>0&&<span className="pending-leave-badge">{pending.length}</span>}</div>
      <div className="simple-list">
        {pending.length===0?<div className="empty-state">No pending claims.</div>:pending.map(c=><button type="button" className={`simple-row ${selected?.id===c.id?"selected":""}`} key={c.id} onClick={()=>openClaim(c.id)}>
          <div><strong>{c.employee_code} · {c.employee_name}</strong><span>{c.claim_number} · {c.title} · {money(c.claimed_amount,c.currency)}</span></div>
          <Status value={c.status}/>
        </button>)}
      </div>
    </section>}

    {selected&&<section className="panel" ref={detailRef}>
      <div className="panel-header">
        <div><span className="eyebrow">{selected.claim_number}</span><h2>{selected.title}</h2><p>{selected.purpose}</p></div>
        <Status value={selected.status}/>
      </div>

      <div className="outlet-summary-grid">
        <div><small>Employee</small><strong>{selected.employee_name?`${selected.employee_code} · ${selected.employee_name}`:"My claim"}</strong></div>
        <div><small>Claimed</small><strong>{money(selected.claimed_amount,selected.currency)}</strong></div>
        <div><small>Verified</small><strong>{selected.verified_amount==null?"—":money(selected.verified_amount,selected.currency)}</strong></div>
        <div><small>Approved</small><strong>{selected.approved_amount==null?"—":money(selected.approved_amount,selected.currency)}</strong></div>
        <div><small>Travel</small><strong>{selected.travel_start_date||"—"} → {selected.travel_end_date||"—"}</strong></div>
        <div><small>Route</small><strong>{selected.origin||"—"} → {selected.destination||"—"}</strong></div>
      </div>

      <section className="subpanel">
        <h3>Expense Items</h3>
        <div className="table-wrap"><table><thead><tr><th>Date</th><th>Category</th><th>Description</th><th>Qty</th><th>Rate</th><th>Amount</th></tr></thead><tbody>
          {(selected.items||[]).map(i=><tr key={i.id}><td>{formatDisplayDate(i.expense_date)}</td><td>{pretty(i.category)}</td><td>{i.description}</td><td>{i.quantity}</td><td>{money(i.rate,selected.currency)}</td><td>{money(i.amount,selected.currency)}</td></tr>)}
        </tbody></table></div>
      </section>

      <div className="outlet-related-grid">
        <article className="subpanel"><h3>Receipts & Documents</h3><div className="simple-list">
          {documents.length===0?<div className="empty-compact">No linked receipts/documents.</div>:documents.map(d=><div className="simple-row" key={d.id}><div><strong>{d.title}</strong><span>{pretty(d.category)} · {d.file_name}</span></div><div style={{display:"flex",alignItems:"center",gap:".55rem",gridAutoFlow:"column"}}><span>{d.status}</span><button type="button" className="secondary-button" disabled={documentAction!==""||d.status!=="ACTIVE"} onClick={()=>openDocument(d,"preview")}>{documentAction===`${d.id}:preview`?"Opening…":"Preview"}</button><button type="button" className="link-button" disabled={documentAction!==""||d.status!=="ACTIVE"} onClick={()=>openDocument(d,"download")}>{documentAction===`${d.id}:download`?"Downloading…":"Download"}</button></div></div>)}
        </div></article>

        <article className="subpanel"><h3>Claim History</h3><div className="simple-list">
          {actions.length===0?<div className="empty-compact">No claim actions yet.</div>:actions.map(a=><div className="simple-row" key={a.id}><div><strong>{pretty(a.action)}</strong><span>{a.note||"No note"}{a.amount!=null?` · ${money(a.amount,selected.currency)}`:""}</span></div><span>{a.created_at?new Date(a.created_at).toLocaleString("en-GB",dateOptions({},true)):""}</span></div>)}
        </div></article>
      </div>

      {selected.status==="DRAFT"&&<section className="subpanel">
        <h3>Submit Claim</h3><p className="muted">Once submitted, the claim moves to management verification.</p>
        {draftDateError&&<p className="error-banner">{draftDateError}</p>}
        <button type="button" className="primary-button" disabled={busy||Boolean(draftDateError)} onClick={submitClaim}>{busy?"Submitting…":"Submit for Verification"}</button>
      </section>}

      {selected.status==="SUBMITTED"&&canVerify&&<section className="subpanel">
        <span className="eyebrow">Management Verification</span><h3>Verify Claim</h3>
        <div className="form-grid">
          <label>Verified Amount<input type="number" min="0" step="0.01" max={selected.claimed_amount} disabled={busy} value={review.verified_amount} onChange={e=>setReview({...review,verified_amount:e.target.value})}/></label>
          <label>Verification Note<textarea rows="2" maxLength="5000" disabled={busy} value={review.verification_note} onChange={e=>setReview({...review,verification_note:e.target.value})}/></label>
        </div>
        <label>Rejection Reason<textarea rows="2" minLength="3" maxLength="5000" disabled={busy} value={review.rejection_reason} onChange={e=>setReview({...review,rejection_reason:e.target.value})}/></label>
        <div className="header-actions"><button type="button" className="primary-button" disabled={busy} onClick={verifyClaim}>Verify Claim</button><button type="button" className="secondary-button danger" disabled={busy} onClick={rejectClaim}>Reject Claim</button></div>
      </section>}

      {selected.status==="VERIFIED"&&isMD&&<section className="subpanel">
        <span className="eyebrow">MD Approval</span><h3>Approve Claim</h3>
        <div className="form-grid">
          <label>Approved Amount<input type="number" min="0" step="0.01" max={selected.verified_amount??selected.claimed_amount} disabled={busy} value={review.approved_amount} onChange={e=>setReview({...review,approved_amount:e.target.value})}/></label>
          <label>Approval Note<textarea rows="2" maxLength="5000" disabled={busy} value={review.approval_note} onChange={e=>setReview({...review,approval_note:e.target.value})}/></label>
        </div>
        <label>Rejection Reason<textarea rows="2" minLength="3" maxLength="5000" disabled={busy} value={review.rejection_reason} onChange={e=>setReview({...review,rejection_reason:e.target.value})}/></label>
        <div className="header-actions"><button type="button" className="primary-button" disabled={busy} onClick={approveClaim}>Approve Claim</button><button type="button" className="secondary-button danger" disabled={busy} onClick={rejectClaim}>Reject Claim</button></div>
      </section>}

      {selected.status==="APPROVED"&&canPay&&<section className="subpanel">
        <span className="eyebrow">Payment</span><h3>Mark Claim Paid</h3>
        <div className="form-grid">
          <label>Payment Reference *<input required minLength="2" maxLength="150" disabled={busy} value={review.payment_reference} onChange={e=>setReview({...review,payment_reference:e.target.value})}/></label>
          <label>Payment Note<textarea rows="2" maxLength="5000" disabled={busy} value={review.payment_note} onChange={e=>setReview({...review,payment_note:e.target.value})}/></label>
        </div>
        <button type="button" className="primary-button" disabled={busy} onClick={markPaid}>Mark Paid</button>
      </section>}
    </section>}
  </div>
}
// date-display-ddmmyyyy-v1
