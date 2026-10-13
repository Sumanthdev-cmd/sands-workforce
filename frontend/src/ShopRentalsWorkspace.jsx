import {useEffect,useMemo,useState} from "react";
import {useAuth} from "./context/AuthContext";
import {apiRequest,uploadWithProgress} from "./lib/api";

const money=(value)=>`₹${Number(value||0).toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const today=()=>new Date().toISOString().slice(0,10);

const emptyVendor={
  code:"",name:"",contact_person:"",phone:"",email:"",address:"",
  service_category:"",deposit_amount:"",deposit_payment_mode:"CASH",
  deposit_reference:"",deposit_received_on:today(),notes:"",
};

const emptyRental={
  rental_type:"OWN_BUILDING_GIVEN",building_name:"",building_code:"",
  address:"",counterparty_name:"",counterparty_contact:"",
  agreement_start_date:today(),agreement_end_date:"",
  monthly_rent_amount:"",advance_amount:"",advance_payment_mode:"CASH",
  advance_paid_on:today(),advance_reference:"",notes:"",
};

const emptyRefund={
  target_id:"",amount:"",payment_mode:"CASH",refund_date:today(),
  payment_reference:"",reason:"",
};

function errorText(error){
  const value=error?.detail??error?.message??error;
  if(typeof value==="string")return value;
  if(Array.isArray(value))return value.map(x=>x?.msg||"Invalid information.").join(" ");
  if(value&&typeof value==="object")return value.message||"The request could not be completed.";
  return "The request could not be completed.";
}

function clean(object){
  return Object.fromEntries(Object.entries(object).map(([key,value])=>{
    if(value==="")return [key,null];
    if(["deposit_amount","monthly_rent_amount","advance_amount","amount"].includes(key)){
      return [key,value===""||value===null?null:Number(value)];
    }
    return [key,value];
  }));
}

function statusText(value){
  return String(value||"").replaceAll("_"," ");
}

async function uploadDocument({ownerType,ownerId,category,title,file,onProgress}){
  if(!file)return null;
  const contentType=file.type||"application/octet-stream";
  const prepared=await apiRequest("/documents/presign-upload",{
    method:"POST",
    body:{
      owner_type:ownerType,
      owner_id:ownerId,
      category,
      title,
      description:title,
      file_name:file.name,
      content_type:contentType,
      file_size:file.size,
      is_confidential:true,
      extra_data:{source:"shop-rentals"}
    }
  });
  const etag=await uploadWithProgress(prepared.upload_url,file,contentType,onProgress);
  await apiRequest(`/documents/${prepared.document_id}/complete`,{
    method:"POST",
    body:{etag:etag?etag.replaceAll('"',""):null}
  });
  return prepared.document_id;
}

function FileField({label,file,setFile,progress}){
  return <label className="file-drop">
    {label}
    <input type="file" accept=".pdf,.csv,.xlsx,.xls,image/*" onChange={e=>setFile(e.target.files?.[0]||null)}/>
    <span>{file?`${file.name} - ${Math.round(file.size/1024)} KB`:"Choose supporting file"}</span>
    {progress>0&&<div className="progress-bar"><span style={{width:`${progress}%`}}/></div>}
  </label>
}

export default function ShopRentalsWorkspace(){
  const {roles=[]}=useAuth();
  const isMD=roles.includes("MD");
  const canManage=roles.some(role=>["ADMIN","MD","GM","MANAGER"].includes(role));
  const [rentals,setRentals]=useState([]);
  const [vendors,setVendors]=useState([]);
  const [rentalRefunds,setRentalRefunds]=useState([]);
  const [vendorRefunds,setVendorRefunds]=useState([]);
  const [vendorForm,setVendorForm]=useState(emptyVendor);
  const [rentalForm,setRentalForm]=useState(emptyRental);
  const [rentalRefund,setRentalRefund]=useState(emptyRefund);
  const [vendorRefund,setVendorRefund]=useState(emptyRefund);
  const [vendorDepositFile,setVendorDepositFile]=useState(null);
  const [agreementFile,setAgreementFile]=useState(null);
  const [advanceFile,setAdvanceFile]=useState(null);
  const [rentalRefundFile,setRentalRefundFile]=useState(null);
  const [vendorRefundFile,setVendorRefundFile]=useState(null);
  const [progress,setProgress]=useState({});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");

  async function load(){
    setError("");
    const [r,v,rr,vr]=await Promise.allSettled([
      apiRequest("/operations/shop-rentals"),
      apiRequest("/operations/vendors"),
      apiRequest("/operations/shop-rental-refunds"),
      apiRequest("/operations/vendor-deposit-refunds"),
    ]);
    if(r.status==="fulfilled")setRentals(Array.isArray(r.value)?r.value:[]);
    if(v.status==="fulfilled")setVendors(Array.isArray(v.value)?v.value:[]);
    if(rr.status==="fulfilled")setRentalRefunds(Array.isArray(rr.value)?rr.value:[]);
    if(vr.status==="fulfilled")setVendorRefunds(Array.isArray(vr.value)?vr.value:[]);
    const failed=[r,v,rr,vr].find(x=>x.status==="rejected");
    if(failed)setError(errorText(failed.reason));
  }

  useEffect(()=>{load()},[]);

  const pendingRentalRefunds=useMemo(()=>rentalRefunds.filter(x=>x.status==="PENDING_MD"),[rentalRefunds]);
  const pendingVendorRefunds=useMemo(()=>vendorRefunds.filter(x=>x.status==="PENDING_MD"),[vendorRefunds]);

  async function openDoc(id,mode="preview"){
    if(!id)return;
    const tab=window.open("about:blank","_blank");
    if(tab)tab.document.write("<p style='font-family:Arial,sans-serif;padding:24px'>Preparing secure document link...</p>");
    try{
      let data;
      try{
        data=await apiRequest(`/documents/${id}/${mode==="download"?"download-url":"preview-url"}`);
      }catch(err){
        if(mode!=="preview")throw err;
        data=await apiRequest(`/documents/${id}/download-url`);
      }
      const url=data.preview_url||data.download_url;
      if(!url)throw new Error("Document link was not returned by the server.");
      if(tab)tab.location.href=url;
      else window.open(url,"_blank");
    }catch(err){
      const text=errorText(err);
      if(tab)tab.document.body.innerHTML=`<p style="font-family:Arial,sans-serif;padding:24px;color:#b00020">${text}</p>`;
      setError(text);
    }
  }

  const previewDoc=id=>openDoc(id,"preview");
  const downloadDoc=id=>openDoc(id,"download");

  async function createVendor(e){
    e.preventDefault();
    if(busy)return;
    setBusy(true);setError("");setMessage("");
    try{
      const payload=clean(vendorForm);
      payload.deposit_document_id=null;
      const vendor=await apiRequest("/operations/vendors",{method:"POST",body:payload});
      if(vendorDepositFile){
        const docId=await uploadDocument({
          ownerType:"VENDOR",
          ownerId:vendor.id,
          category:"VENDOR_DEPOSIT",
          title:`${vendor.code} vendor deposit`,
          file:vendorDepositFile,
          onProgress:value=>setProgress(p=>({...p,vendorDeposit:value})),
        });
        await apiRequest(`/operations/vendors/${vendor.id}`,{
          method:"PATCH",
          body:{deposit_document_id:docId}
        });
      }
      setVendorForm(emptyVendor);
      setVendorDepositFile(null);
      setMessage("Vendor and deposit details saved.");
      await load();
    }catch(err){setError(errorText(err))}
    finally{setBusy(false)}
  }

  async function createRental(e){
    e.preventDefault();
    if(busy)return;
    setBusy(true);setError("");setMessage("");
    try{
      const payload=clean(rentalForm);
      payload.agreement_document_id=null;
      payload.advance_document_id=null;
      const rental=await apiRequest("/operations/shop-rentals",{method:"POST",body:payload});
      const patch={};
      if(agreementFile){
        patch.agreement_document_id=await uploadDocument({
          ownerType:"SHOP_RENTAL",
          ownerId:rental.id,
          category:"SHOP_RENTAL_AGREEMENT",
          title:`${rental.building_name} rent agreement`,
          file:agreementFile,
          onProgress:value=>setProgress(p=>({...p,agreement:value})),
        });
      }
      if(advanceFile){
        patch.advance_document_id=await uploadDocument({
          ownerType:"SHOP_RENTAL",
          ownerId:rental.id,
          category:"SHOP_RENTAL_ADVANCE",
          title:`${rental.building_name} rental advance`,
          file:advanceFile,
          onProgress:value=>setProgress(p=>({...p,advance:value})),
        });
      }
      if(Object.keys(patch).length){
        await apiRequest(`/operations/shop-rentals/${rental.id}`,{method:"PATCH",body:patch});
      }
      setRentalForm(emptyRental);
      setAgreementFile(null);
      setAdvanceFile(null);
      setMessage("Shop rental record saved.");
      await load();
    }catch(err){setError(errorText(err))}
    finally{setBusy(false)}
  }

  async function requestRentalRefund(e){
    e.preventDefault();
    if(busy)return;
    setBusy(true);setError("");setMessage("");
    try{
      const payload=clean(rentalRefund);
      const rentalId=payload.target_id;
      delete payload.target_id;
      payload.supporting_document_id=null;
      if(rentalRefundFile){
        payload.supporting_document_id=await uploadDocument({
          ownerType:"SHOP_RENTAL",
          ownerId:rentalId,
          category:"SHOP_RENTAL_ADVANCE_REFUND",
          title:"Shop rental advance refund proof",
          file:rentalRefundFile,
          onProgress:value=>setProgress(p=>({...p,rentalRefund:value})),
        });
      }
      await apiRequest(`/operations/shop-rentals/${rentalId}/refunds`,{method:"POST",body:payload});
      setRentalRefund(emptyRefund);
      setRentalRefundFile(null);
      setMessage("Rental advance refund sent to MD for approval.");
      await load();
    }catch(err){setError(errorText(err))}
    finally{setBusy(false)}
  }

  async function requestVendorRefund(e){
    e.preventDefault();
    if(busy)return;
    setBusy(true);setError("");setMessage("");
    try{
      const payload=clean(vendorRefund);
      const vendorId=payload.target_id;
      delete payload.target_id;
      payload.supporting_document_id=null;
      if(vendorRefundFile){
        payload.supporting_document_id=await uploadDocument({
          ownerType:"VENDOR",
          ownerId:vendorId,
          category:"VENDOR_DEPOSIT_REFUND",
          title:"Vendor deposit refund proof",
          file:vendorRefundFile,
          onProgress:value=>setProgress(p=>({...p,vendorRefund:value})),
        });
      }
      await apiRequest(`/operations/vendors/${vendorId}/deposit-refunds`,{method:"POST",body:payload});
      setVendorRefund(emptyRefund);
      setVendorRefundFile(null);
      setMessage("Vendor deposit refund sent to MD for approval.");
      await load();
    }catch(err){setError(errorText(err))}
    finally{setBusy(false)}
  }

  async function decide(type,row,approved){
    const note=window.prompt(approved?"MD approval note (optional):":"Reason for rejection:","");
    if(note===null)return;
    if(!approved&&note.trim().length<3){setError("Enter a rejection reason.");return}
    setBusy(true);setError("");setMessage("");
    try{
      const base=type==="rental"?"shop-rental-refunds":"vendor-deposit-refunds";
      await apiRequest(`/operations/${base}/${row.id}/${approved?"approve":"reject"}`,{
        method:"POST",
        body:approved?{note:note.trim()||null}:{reason:note.trim()},
      });
      setMessage(`Refund ${approved?"approved":"rejected"}.`);
      await load();
      window.dispatchEvent(new Event("action-alerts:refresh"));
    }catch(err){setError(errorText(err))}
    finally{setBusy(false)}
  }

  if(!canManage)return <div className="page"><div className="empty-state">Shop rental access is restricted to management roles.</div></div>;

  return <div className="page">
    <header className="page-header">
      <div>
        <span className="eyebrow">Properties and advances</span>
        <h1>Rentals/Deposits</h1>
        <p>Maintain own buildings given on rent, buildings taken on rent, advances, vendor deposits and MD-approved refunds.</p>
      </div>
      <button className="secondary-button" onClick={load} disabled={busy}>Refresh</button>
    </header>

    {error&&<div className="error-banner">{error}</div>}
    {message&&<div className="success-banner">{message}</div>}

    {isMD&&<section className="panel">
      <div className="panel-header">
        <div>
          <span className="eyebrow">MD Approval</span>
          <h2>Refund approvals</h2>
          <p>Approve or reject rental advance and vendor deposit refunds.</p>
        </div>
        <span className="pending-leave-badge">{pendingRentalRefunds.length+pendingVendorRefunds.length}</span>
      </div>
      {[...pendingRentalRefunds.map(x=>["rental",x]),...pendingVendorRefunds.map(x=>["vendor",x])].length===0
        ?<div className="empty-state">No refund requests are pending MD approval.</div>
        :<div className="simple-list">{[...pendingRentalRefunds.map(x=>["rental",x]),...pendingVendorRefunds.map(x=>["vendor",x])].map(([type,row])=>
          <article className="subpanel" key={`${type}-${row.id}`}>
            <div className="panel-header">
              <div>
                <strong>{type==="rental"?"Rental advance refund":"Vendor deposit refund"}</strong>
                <p>{money(row.amount)} - {row.payment_mode} - {row.refund_date}</p>
              </div>
              <span className="inspection-status">{statusText(row.status)}</span>
            </div>
            <p>{row.reason}</p>
            <div className="action-strip">
              {row.supporting_document_id&&<button className="secondary-button" onClick={()=>previewDoc(row.supporting_document_id)}>Preview Document</button>}
              <button className="primary-button" disabled={busy} onClick={()=>decide(type,row,true)}>Approve</button>
              <button className="secondary-button danger" disabled={busy} onClick={()=>decide(type,row,false)}>Reject</button>
            </div>
          </article>)}</div>}
    </section>}

    <section className="panel">
      <div className="panel-header"><div><span className="eyebrow">Rental records</span><h2>Add Shop Rental</h2></div></div>
      <form className="form-grid" onSubmit={createRental}>
        <label>Rental Type<select value={rentalForm.rental_type} onChange={e=>setRentalForm({...rentalForm,rental_type:e.target.value})}><option value="OWN_BUILDING_GIVEN">Own building given for rent</option><option value="BUILDING_TAKEN">Building taken for rent</option></select></label>
        <label>Building Name<input required value={rentalForm.building_name} onChange={e=>setRentalForm({...rentalForm,building_name:e.target.value})}/></label>
        <label>Building Code<input value={rentalForm.building_code} onChange={e=>setRentalForm({...rentalForm,building_code:e.target.value})}/></label>
        <label>Party Name<input required value={rentalForm.counterparty_name} onChange={e=>setRentalForm({...rentalForm,counterparty_name:e.target.value})}/></label>
        <label>Party Contact<input value={rentalForm.counterparty_contact} onChange={e=>setRentalForm({...rentalForm,counterparty_contact:e.target.value})}/></label>
        <label>Agreement Start<input type="date" required value={rentalForm.agreement_start_date} onChange={e=>setRentalForm({...rentalForm,agreement_start_date:e.target.value})}/></label>
        <label>Agreement End<input type="date" value={rentalForm.agreement_end_date} onChange={e=>setRentalForm({...rentalForm,agreement_end_date:e.target.value})}/></label>
        <label>Monthly Rent<input type="number" min="0" step="0.01" required value={rentalForm.monthly_rent_amount} onChange={e=>setRentalForm({...rentalForm,monthly_rent_amount:e.target.value})}/></label>
        <label>Advance Amount<input type="number" min="0" step="0.01" value={rentalForm.advance_amount} onChange={e=>setRentalForm({...rentalForm,advance_amount:e.target.value})}/></label>
        <label>Advance Mode<select value={rentalForm.advance_payment_mode} onChange={e=>setRentalForm({...rentalForm,advance_payment_mode:e.target.value})}><option>CASH</option><option>UPI</option><option>CHEQUE</option><option>BANK_TRANSFER</option></select></label>
        <label>Advance Paid On<input type="date" value={rentalForm.advance_paid_on} onChange={e=>setRentalForm({...rentalForm,advance_paid_on:e.target.value})}/></label>
        <label>Advance Reference<input value={rentalForm.advance_reference} onChange={e=>setRentalForm({...rentalForm,advance_reference:e.target.value})}/></label>
        <label className="full-span">Address<textarea value={rentalForm.address} onChange={e=>setRentalForm({...rentalForm,address:e.target.value})}/></label>
        <FileField label="Agreement Document" file={agreementFile} setFile={setAgreementFile} progress={progress.agreement||0}/>
        <FileField label="Advance Supporting Document" file={advanceFile} setFile={setAdvanceFile} progress={progress.advance||0}/>
        <label className="full-span">Notes<textarea value={rentalForm.notes} onChange={e=>setRentalForm({...rentalForm,notes:e.target.value})}/></label>
        <button className="primary-button full-span" disabled={busy}>{busy?"Saving...":"Save Rental"}</button>
      </form>
    </section>

    <section className="panel">
      <div className="panel-header"><div><span className="eyebrow">Vendor deposit</span><h2>Add Vendor With Deposit</h2></div></div>
      <form className="form-grid" onSubmit={createVendor}>
        <label>Vendor Code<input required value={vendorForm.code} onChange={e=>setVendorForm({...vendorForm,code:e.target.value.toUpperCase()})}/></label>
        <label>Vendor Name<input required value={vendorForm.name} onChange={e=>setVendorForm({...vendorForm,name:e.target.value})}/></label>
        <label>Contact Person<input value={vendorForm.contact_person} onChange={e=>setVendorForm({...vendorForm,contact_person:e.target.value})}/></label>
        <label>Phone<input value={vendorForm.phone} onChange={e=>setVendorForm({...vendorForm,phone:e.target.value})}/></label>
        <label>Email<input value={vendorForm.email} onChange={e=>setVendorForm({...vendorForm,email:e.target.value})}/></label>
        <label>Category<input value={vendorForm.service_category} onChange={e=>setVendorForm({...vendorForm,service_category:e.target.value})}/></label>
        <label>Deposit Amount<input type="number" min="0" step="0.01" value={vendorForm.deposit_amount} onChange={e=>setVendorForm({...vendorForm,deposit_amount:e.target.value})}/></label>
        <label>Deposit Mode<select value={vendorForm.deposit_payment_mode} onChange={e=>setVendorForm({...vendorForm,deposit_payment_mode:e.target.value})}><option>CASH</option><option>UPI</option><option>CHEQUE</option><option>BANK_TRANSFER</option></select></label>
        <label>Deposit Date<input type="date" value={vendorForm.deposit_received_on} onChange={e=>setVendorForm({...vendorForm,deposit_received_on:e.target.value})}/></label>
        <label>Deposit Reference<input value={vendorForm.deposit_reference} onChange={e=>setVendorForm({...vendorForm,deposit_reference:e.target.value})}/></label>
        <FileField label="Deposit Supporting Document" file={vendorDepositFile} setFile={setVendorDepositFile} progress={progress.vendorDeposit||0}/>
        <label className="full-span">Notes<textarea value={vendorForm.notes} onChange={e=>setVendorForm({...vendorForm,notes:e.target.value})}/></label>
        <button className="primary-button full-span" disabled={busy}>{busy?"Saving...":"Save Vendor"}</button>
      </form>
    </section>

    <section className="panel">
      <div className="panel-header"><div><span className="eyebrow">Refund requests</span><h2>Record Advance / Deposit Return</h2><p>Refunds are recorded first and become valid after MD approval.</p></div></div>
      <div className="outlet-related-grid">
        <form className="subpanel" onSubmit={requestRentalRefund}>
          <h3>Rental Advance Refund</h3>
          <label>Rental<select required value={rentalRefund.target_id} onChange={e=>setRentalRefund({...rentalRefund,target_id:e.target.value})}><option value="">Select rental...</option>{rentals.map(r=><option key={r.id} value={r.id}>{r.building_name} - {statusText(r.rental_type)}</option>)}</select></label>
          <label>Amount<input type="number" min="0" step="0.01" required value={rentalRefund.amount} onChange={e=>setRentalRefund({...rentalRefund,amount:e.target.value})}/></label>
          <label>Mode<select value={rentalRefund.payment_mode} onChange={e=>setRentalRefund({...rentalRefund,payment_mode:e.target.value})}><option>CASH</option><option>UPI</option><option>CHEQUE</option><option>BANK_TRANSFER</option></select></label>
          <label>Refund Date<input type="date" required value={rentalRefund.refund_date} onChange={e=>setRentalRefund({...rentalRefund,refund_date:e.target.value})}/></label>
          <label>Reference<input value={rentalRefund.payment_reference} onChange={e=>setRentalRefund({...rentalRefund,payment_reference:e.target.value})}/></label>
          <label>Reason<textarea required value={rentalRefund.reason} onChange={e=>setRentalRefund({...rentalRefund,reason:e.target.value})}/></label>
          <FileField label="Refund Supporting Document" file={rentalRefundFile} setFile={setRentalRefundFile} progress={progress.rentalRefund||0}/>
          <button className="primary-button" disabled={busy}>Send to MD</button>
        </form>
        <form className="subpanel" onSubmit={requestVendorRefund}>
          <h3>Vendor Deposit Refund</h3>
          <label>Vendor<select required value={vendorRefund.target_id} onChange={e=>setVendorRefund({...vendorRefund,target_id:e.target.value})}><option value="">Select vendor...</option>{vendors.map(v=><option key={v.id} value={v.id}>{v.code} - {v.name}</option>)}</select></label>
          <label>Amount<input type="number" min="0" step="0.01" required value={vendorRefund.amount} onChange={e=>setVendorRefund({...vendorRefund,amount:e.target.value})}/></label>
          <label>Mode<select value={vendorRefund.payment_mode} onChange={e=>setVendorRefund({...vendorRefund,payment_mode:e.target.value})}><option>CASH</option><option>UPI</option><option>CHEQUE</option><option>BANK_TRANSFER</option></select></label>
          <label>Refund Date<input type="date" required value={vendorRefund.refund_date} onChange={e=>setVendorRefund({...vendorRefund,refund_date:e.target.value})}/></label>
          <label>Reference<input value={vendorRefund.payment_reference} onChange={e=>setVendorRefund({...vendorRefund,payment_reference:e.target.value})}/></label>
          <label>Reason<textarea required value={vendorRefund.reason} onChange={e=>setVendorRefund({...vendorRefund,reason:e.target.value})}/></label>
          <FileField label="Refund Supporting Document" file={vendorRefundFile} setFile={setVendorRefundFile} progress={progress.vendorRefund||0}/>
          <button className="primary-button" disabled={busy}>Send to MD</button>
        </form>
      </div>
    </section>

    <section className="panel">
      <div className="panel-header"><div><span className="eyebrow">Records</span><h2>Rental Register</h2></div></div>
      {rentals.length===0?<div className="empty-state">No shop rental records yet.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Building</th><th>Type</th><th>Party</th><th>Agreement</th><th>Rent</th><th>Advance</th><th>Status</th><th>Docs</th></tr></thead><tbody>{rentals.map(r=><tr key={r.id}><td><strong>{r.building_name}</strong><div className="muted">{r.building_code||"No code"}</div></td><td>{statusText(r.rental_type)}</td><td>{r.counterparty_name}</td><td>{r.agreement_start_date} to {r.agreement_end_date||"open"}</td><td>{money(r.monthly_rent_amount)}</td><td>{money(r.advance_amount)}</td><td>{statusText(r.status)}</td><td><div className="action-strip">{r.agreement_document_id&&<><button className="secondary-button" onClick={()=>previewDoc(r.agreement_document_id)}>Agreement</button><button className="secondary-button" onClick={()=>downloadDoc(r.agreement_document_id)}>Download</button></>}{r.advance_document_id&&<><button className="secondary-button" onClick={()=>previewDoc(r.advance_document_id)}>Advance</button><button className="secondary-button" onClick={()=>downloadDoc(r.advance_document_id)}>Download</button></>}</div></td></tr>)}</tbody></table></div>}
    </section>

    <section className="panel">
      <div className="panel-header"><div><span className="eyebrow">Records</span><h2>Vendor Deposits</h2></div></div>
      {vendors.length===0?<div className="empty-state">No vendors recorded yet.</div>:<div className="table-scroll"><table className="data-table"><thead><tr><th>Vendor</th><th>Contact</th><th>Deposit</th><th>Mode</th><th>Received</th><th>Document</th></tr></thead><tbody>{vendors.map(v=><tr key={v.id}><td><strong>{v.code}</strong><div>{v.name}</div></td><td>{v.phone||v.email||"—"}</td><td>{money(v.deposit_amount)}</td><td>{v.deposit_payment_mode||"—"}</td><td>{v.deposit_received_on||"—"}</td><td>{v.deposit_document_id?<div className="action-strip"><button className="secondary-button" onClick={()=>previewDoc(v.deposit_document_id)}>Preview</button><button className="secondary-button" onClick={()=>downloadDoc(v.deposit_document_id)}>Download</button></div>:"—"}</td></tr>)}</tbody></table></div>}
    </section>
  </div>
}
