import DateField from "./DateField";
import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {useEffect,useMemo,useRef,useState} from "react";
import {useAuth} from "./context/AuthContext";
import {apiRequest,uploadWithProgress} from "./lib/api";

const MGMT=["ADMIN","MD","GM","MANAGER"];

const emptyForm={
  code:"",name:"",outlet_type:"SHOP",cluster_name:"",address:"",
  latitude:"",longitude:"",attendance_radius_meters:150,vendor_id:"",vendor_name:"",
  vendor_contact_person:"",vendor_phone:"",vendor_email:"",
  assistant_vendor_id:"",assistant_vendor_name:"",
  assistant_vendor_contact_person:"",assistant_vendor_phone:"",assistant_vendor_email:"",
  parcel_vendor_id:"",parcel_vendor_name:"",
  parcel_vendor_contact_person:"",parcel_vendor_phone:"",parcel_vendor_email:"",
  opening_date:"",licence_number:"",licence_expiry_date:"",
  excise_licence_number:"",excise_expiry_date:"",
  rent_agreement_expiry_date:"",blueprint_document_id:"",notes:""
};

const DOC_TYPES=[
  {key:"excise",category:"OUTLET_EXCISE_LICENSE",label:"Excise Licence",expiryField:"excise_expiry_date"},
  {key:"trade",category:"OUTLET_TRADE_LICENSE",label:"Trade / Business Licence",expiryField:"licence_expiry_date"},
  {key:"rent",category:"OUTLET_RENT_AGREEMENT",label:"Rent Agreement",expiryField:"rent_agreement_expiry_date"},
  {key:"blueprint",category:"OUTLET_BLUEPRINT",label:"Blueprint / Approved Plan",blueprint:true},
  {key:"fire",category:"OUTLET_FIRE_NOC",label:"Fire NOC",customExpiry:"fire_noc_expiry_date"},
  {key:"local",category:"OUTLET_LOCAL_APPROVAL",label:"Police / Local Approval",customExpiry:"local_approval_expiry_date"},
  {key:"other",category:"OUTLET_OTHER",label:"Other Outlet Document",customExpiry:"other_document_expiry_date"},
];

const blankFiles=()=>Object.fromEntries(DOC_TYPES.map(x=>[x.key,null]));
const blankExtraExpiry=()=>({
  fire_noc_expiry_date:"",
  local_approval_expiry_date:"",
  other_document_expiry_date:"",
});

const ALLOWED=[
  "code","name","outlet_type","cluster_name","address","latitude","longitude","attendance_radius_meters",
  "vendor_id","vendor_name","vendor_contact_person","vendor_phone","vendor_email",
  "assistant_vendor_id","assistant_vendor_name","assistant_vendor_contact_person","assistant_vendor_phone","assistant_vendor_email",
  "parcel_vendor_id","parcel_vendor_name","parcel_vendor_contact_person","parcel_vendor_phone","parcel_vendor_email",
  "opening_date","licence_number","licence_expiry_date","excise_licence_number",
  "excise_expiry_date","rent_agreement_expiry_date","blueprint_document_id",
  "status","notes","is_active"
];

function clean(form){
  const out={};
  for(const key of ALLOWED){
    if(!(key in form))continue;
    let value=form[key];
    if(value==="")value=null;
    if(value!==null&&["latitude","longitude","attendance_radius_meters"].includes(key))value=Number(value);
    out[key]=value;
  }
  return out;
}

function errorText(error){
  const value=error?.detail??error?.message??error;
  if(typeof value==="string")return value==="[object Object]"?"The request could not be completed.":value;
  if(Array.isArray(value))return value.map(x=>x?.msg||"Invalid information.").join(" ");
  if(value&&typeof value==="object"&&Array.isArray(value.detail))return value.detail.map(x=>x?.msg||"Invalid information.").join(" ");
  return "The request could not be completed.";
}

function getExpiry(type,form,extra){
  if(type.expiryField)return form[type.expiryField]||null;
  if(type.customExpiry)return extra[type.customExpiry]||null;
  return null;
}

function docMeta(type,form){
  if(type.key==="excise")return {licence_number:form.excise_licence_number||null,licence_type:"EXCISE"};
  if(type.key==="trade")return {licence_number:form.licence_number||null,licence_type:"TRADE_BUSINESS"};
  return {};
}


function CreateDocumentGrid({
  form,files,setFiles,extraExpiry,setExtraExpiry,progress,busy
}){
  return <div className="outlet-related-grid">
    {DOC_TYPES.map(type=>{
      const expiry=type.customExpiry?extraExpiry[type.customExpiry]||"":null;
      return <article className="subpanel" key={type.key}>
        <h3>{type.label}</h3>
        <p className="muted">
          {type.expiryField
            ?`Uses the matching expiry date entered in Outlet Details above.`
            :type.blueprint
              ?"Upload the approved blueprint / plan."
              :"Upload an image or PDF and optionally record expiry."}
        </p>

        <label className="file-drop">
          Document File
          <input
            type="file"
            accept=".pdf,image/*"
            disabled={busy}
            onChange={e=>setFiles({...files,[type.key]:e.target.files?.[0]||null})}
          />
          <span>
            {files[type.key]
              ?`${files[type.key].name} · ${Math.round(files[type.key].size/1024)} KB`
              :"Choose image or PDF"}
          </span>
        </label>

        {type.customExpiry&&<label>
          Expiry / Renewal Date
          <DateField
            type="date"
            disabled={busy}
            value={expiry}
            onChange={e=>setExtraExpiry({...extraExpiry,[type.customExpiry]:e.target.value})}
          />
        </label>}

        {progress[type.key]>0&&<div className="progress-bar">
          <span style={{width:`${progress[type.key]}%`}}/>
        </div>}
      </article>
    })}
  </div>
}

export default function OutletsWorkspace(){
  const {roles=[]}=useAuth();
  const admin=Array.isArray(roles)&&roles.includes("ADMIN");
  const management=Array.isArray(roles)&&roles.some(r=>MGMT.includes(r));

  const [rows,setRows]=useState([]);
  const [vendors,setVendors]=useState([]);
  const [selected,setSelected]=useState(null);
  const [inspections,setInspections]=useState([]);
  const [documents,setDocuments]=useState([]);
  const [form,setForm]=useState(emptyForm);
  const [edit,setEdit]=useState(null);
  const [createFiles,setCreateFiles]=useState(blankFiles);
  const [createExtraExpiry,setCreateExtraExpiry]=useState(blankExtraExpiry);
  const [createProgress,setCreateProgress]=useState({});
  const [manageType,setManageType]=useState("OUTLET_OTHER");
  const [manageTitle,setManageTitle]=useState("");
  const [manageIssueDate,setManageIssueDate]=useState("");
  const [manageExpiryDate,setManageExpiryDate]=useState("");
  const [manageDescription,setManageDescription]=useState("");
  const [manageFile,setManageFile]=useState(null);
  const [manageProgress,setManageProgress]=useState(0);
  const [showDocumentManager,setShowDocumentManager]=useState(false);
  const documentManagerRef=useRef(null);
  const [search,setSearch]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const lock=useRef(false);

  async function load(){
    try{
      const data=await apiRequest("/outlets");
      setRows(Array.isArray(data)?data:[]);
    }catch(err){setError(errorText(err))}
  }

  async function loadOptions(){
    if(!management)return;
    const v=await apiRequest("/operations/vendors").catch(()=>[]);
    setVendors(Array.isArray(v)?v:[]);
  }

  useEffect(()=>{load();loadOptions()},[]);

  const filtered=useMemo(()=>{
    const q=search.trim().toLowerCase();
    if(!q)return rows;
    return rows.filter(r=>[r.code,r.name,r.cluster_name,r.address,r.vendor_name]
      .filter(Boolean).join(" ").toLowerCase().includes(q));
  },[rows,search]);

  function applyVendor(id,target="create",prefix="vendor"){
    const v=vendors.find(x=>x.id===id);
    const patch={
      [`${prefix}_id`]:id,
      [`${prefix}_name`]:v?.name||"",
      [`${prefix}_contact_person`]:v?.contact_person||"",
      [`${prefix}_phone`]:v?.phone||"",
      [`${prefix}_email`]:v?.email||""
    };
    target==="edit"
      ?setEdit(old=>({...old,...patch}))
      :setForm(old=>({...old,...patch}));
  }

  async function uploadDoc({
    outlet,type,file,expiryDate=null,issueDate=null,title=null,description=null,onProgress,extraData={}
  }){
    const contentType=file.type||"application/octet-stream";
    const prepared=await apiRequest("/documents/presign-upload",{method:"POST",body:{
      owner_type:"OUTLET",
      owner_id:outlet.id,
      category:type.category,
      title:title?.trim()||`${outlet.code} - ${type.label}`,
      description:description?.trim()||`${type.label} for ${outlet.name}`,
      issue_date:issueDate||null,
      expiry_date:expiryDate||null,
      alert_days_before:30,
      is_confidential:true,
      file_name:file.name,
      content_type:contentType,
      file_size:file.size,
      extra_data:{outlet_code:outlet.code,outlet_name:outlet.name,...extraData}
    }});

    const etag=await uploadWithProgress(
      prepared.upload_url,file,contentType,onProgress
    );

    await apiRequest(`/documents/${prepared.document_id}/complete`,{
      method:"POST",
      body:{etag:etag?etag.replaceAll('"',""):null}
    });

    return prepared.document_id;
  }

  async function uploadCreateDocuments(outlet){
    const failures=[];
    let blueprintId=null;

    for(const type of DOC_TYPES){
      const file=createFiles[type.key];
      if(!file)continue;

      try{
        const id=await uploadDoc({
          outlet,type,file,
          expiryDate:getExpiry(type,form,createExtraExpiry),
          extraData:docMeta(type,form),
          onProgress:value=>setCreateProgress(p=>({...p,[type.key]:value}))
        });
        if(type.blueprint)blueprintId=id;
      }catch(err){
        failures.push(`${type.label}: ${errorText(err)}`);
      }
    }

    if(blueprintId){
      try{
        await apiRequest(`/outlets/${outlet.id}`,{
          method:"PATCH",
          body:{blueprint_document_id:blueprintId}
        });
      }catch(err){
        failures.push(`Blueprint link: ${errorText(err)}`);
      }
    }

    return failures;
  }

  async function create(e){
    e.preventDefault();
    if(lock.current)return;
    lock.current=true;setBusy(true);setError("");setMessage("");setCreateProgress({});

    try{
      const outlet=await apiRequest("/outlets",{
        method:"POST",
        body:clean({...form,blueprint_document_id:null})
      });

      const failures=await uploadCreateDocuments(outlet);
      const count=DOC_TYPES.filter(type=>createFiles[type.key]).length;

      if(failures.length){
        setMessage(`Outlet ${outlet.code} was created. Some documents need attention.`);
        setError(failures.join(" | "));
      }else{
        setMessage(count
          ?`Outlet ${outlet.code} created with ${count} document${count===1?"":"s"}.`
          :`Outlet ${outlet.code} created.`);
      }

      setForm(emptyForm);
      setCreateFiles(blankFiles());
      setCreateExtraExpiry(blankExtraExpiry());
      setCreateProgress({});
      await load();
      await open(outlet.id,{editing:false});
    }catch(err){setError(errorText(err))}
    finally{lock.current=false;setBusy(false)}
  }

  async function open(id,{editing=true}={}){
    try{
      const [outlet,history,docs]=await Promise.all([
        apiRequest(`/outlets/${id}`),
        apiRequest(`/outlets/${id}/inspections`).catch(()=>[]),
        apiRequest(`/documents?owner_type=OUTLET&owner_id=${id}`).catch(()=>[])
      ]);

      setSelected(outlet);
      setInspections(Array.isArray(history)?history:[]);
      setDocuments(Array.isArray(docs)?docs:[]);
      setEdit(editing?{
        name:outlet.name||"",outlet_type:outlet.outlet_type||"SHOP",
        cluster_name:outlet.cluster_name||"",address:outlet.address||"",
        latitude:outlet.latitude??"",longitude:outlet.longitude??"",
        attendance_radius_meters:outlet.attendance_radius_meters??150,
        vendor_id:outlet.vendor_id||"",vendor_name:outlet.vendor_name||"",
        vendor_contact_person:outlet.vendor_contact_person||"",
        vendor_phone:outlet.vendor_phone||"",vendor_email:outlet.vendor_email||"",
        assistant_vendor_id:outlet.assistant_vendor_id||"",
        assistant_vendor_name:outlet.assistant_vendor_name||"",
        assistant_vendor_contact_person:outlet.assistant_vendor_contact_person||"",
        assistant_vendor_phone:outlet.assistant_vendor_phone||"",
        assistant_vendor_email:outlet.assistant_vendor_email||"",
        parcel_vendor_id:outlet.parcel_vendor_id||"",
        parcel_vendor_name:outlet.parcel_vendor_name||"",
        parcel_vendor_contact_person:outlet.parcel_vendor_contact_person||"",
        parcel_vendor_phone:outlet.parcel_vendor_phone||"",
        parcel_vendor_email:outlet.parcel_vendor_email||"",
        opening_date:outlet.opening_date||"",licence_number:outlet.licence_number||"",
        licence_expiry_date:outlet.licence_expiry_date||"",
        excise_licence_number:outlet.excise_licence_number||"",
        excise_expiry_date:outlet.excise_expiry_date||"",
        rent_agreement_expiry_date:outlet.rent_agreement_expiry_date||"",
        blueprint_document_id:outlet.blueprint_document_id||"",
        status:outlet.status||"ACTIVE",notes:outlet.notes||"",is_active:outlet.is_active
      }:null);
      setManageFile(null);setManageProgress(0);setManageTitle("");
      setManageIssueDate("");setManageExpiryDate("");setManageDescription("");
    }catch(err){setError(errorText(err))}
  }

  async function save(e){
    e.preventDefault();
    if(!selected||!edit||lock.current)return;
    lock.current=true;setBusy(true);setError("");setMessage("");

    try{
      const updated=await apiRequest(`/outlets/${selected.id}`,{
        method:"PATCH",body:clean(edit)
      });
      setMessage("Outlet changes saved. The outlet details were refreshed.");
      await load();
      await open(updated.id,{editing:false});
    }catch(err){setError(errorText(err))}
    finally{lock.current=false;setBusy(false)}
  }

  async function uploadManagedDocument(e){
    e.preventDefault();
    if(!admin||!selected||!manageFile){
      setError("Please choose a document file.");
      return;
    }
    if(lock.current)return;

    const type=DOC_TYPES.find(x=>x.category===manageType)||
      {category:manageType,label:manageType.replaceAll("_"," ")};

    lock.current=true;setBusy(true);setError("");setMessage("");setManageProgress(0);

    try{
      const id=await uploadDoc({
        outlet:selected,type,file:manageFile,
        expiryDate:manageExpiryDate||null,
        issueDate:manageIssueDate||null,
        title:manageTitle||null,
        description:manageDescription||null,
        onProgress:setManageProgress,
        extraData:docMeta(type,edit||{})
      });

      if(type.blueprint){
        await apiRequest(`/outlets/${selected.id}`,{
          method:"PATCH",body:{blueprint_document_id:id}
        });
      }

      setMessage(`${type.label} uploaded successfully. The document list was refreshed.`);
      setManageFile(null);setManageProgress(0);setManageTitle("");
      setManageIssueDate("");setManageExpiryDate("");setManageDescription("");
      setShowDocumentManager(false);
      await open(selected.id,{editing:false});
      await load();
    }catch(err){setError(errorText(err))}
    finally{lock.current=false;setBusy(false)}
  }


  function showUploadManager(){
    setShowDocumentManager(true);
    setError("");
    setMessage("");

    window.setTimeout(()=>{
      documentManagerRef.current?.scrollIntoView({
        behavior:"smooth",
        block:"start",
      });
    },0);
  }

  return <div className="page outlets-workspace">
    <header className="page-header">
      <div>
        <span className="eyebrow">Assets & operations</span>
        <h1>Shops / Outlets</h1>
        <p>Manage outlet data, vendors, licences, compliance documents and inspection history.</p>
      </div>
      <button className="secondary-button" onClick={load} disabled={busy}>Refresh</button>
    </header>

    {error&&<div className="error-banner">{error}</div>}
    {message&&<div className="success-banner">✅ {message}</div>}

    {admin&&<section className="panel">
      <div className="panel-header"><div>
        <h2>Add shop / outlet</h2>
        <p>Create the outlet and upload its documents in one workflow. Field visitors are assigned later for each inspection.</p>
      </div></div>

      <div className="info-banner">
        Field visitors are assigned per inspection from Shop Inspections.
        Creating an outlet does not permanently assign any field visitor.
      </div>

      <form className="outlet-form" onSubmit={create}>
        <div className="form-grid">
          <label>Outlet code *<input required disabled={busy} value={form.code} onChange={e=>setForm({...form,code:e.target.value.toUpperCase()})}/></label>
          <label>Shop / outlet name *<input required disabled={busy} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label>
          <label>Outlet type<select disabled={busy} value={form.outlet_type} onChange={e=>setForm({...form,outlet_type:e.target.value})}>
            {["SHOP","OUTLET","WAREHOUSE","OFFICE","OTHER"].map(x=><option key={x}>{x}</option>)}
          </select></label>
          <label>Cluster<input disabled={busy} value={form.cluster_name} onChange={e=>setForm({...form,cluster_name:e.target.value})}/></label>
          <label>Latitude<input type="number" step="any" disabled={busy} value={form.latitude} onChange={e=>setForm({...form,latitude:e.target.value})}/></label>
          <label>Longitude<input type="number" step="any" disabled={busy} value={form.longitude} onChange={e=>setForm({...form,longitude:e.target.value})}/></label>
          <label>Attendance / inspection radius (metres)<input type="number" min="20" max="5000" disabled={busy} value={form.attendance_radius_meters} onChange={e=>setForm({...form,attendance_radius_meters:e.target.value})}/></label>
          <label>Opening date<DateField type="date" disabled={busy} value={form.opening_date} onChange={e=>setForm({...form,opening_date:e.target.value})}/></label>
          <label>Vendor<select disabled={busy} value={form.vendor_id} onChange={e=>applyVendor(e.target.value)}>
            <option value="">No linked vendor</option>
            {vendors.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}
          </select></label>
          <label>Vendor contact<input disabled={busy} value={form.vendor_contact_person} onChange={e=>setForm({...form,vendor_contact_person:e.target.value})}/></label>
          <label>Vendor phone<input disabled={busy} value={form.vendor_phone} onChange={e=>setForm({...form,vendor_phone:e.target.value})}/></label>
          <label>Vendor email<input type="email" disabled={busy} value={form.vendor_email} onChange={e=>setForm({...form,vendor_email:e.target.value})}/></label>
          <label>Assistant vendor<select disabled={busy} value={form.assistant_vendor_id} onChange={e=>applyVendor(e.target.value,"create","assistant_vendor")}>
            <option value="">No assistant vendor</option>
            {vendors.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}
          </select></label>
          <label>Assistant vendor phone<input disabled={busy} value={form.assistant_vendor_phone} onChange={e=>setForm({...form,assistant_vendor_phone:e.target.value})}/></label>
          <label>Parcel vendor (optional)<select disabled={busy} value={form.parcel_vendor_id} onChange={e=>applyVendor(e.target.value,"create","parcel_vendor")}>
            <option value="">No parcel vendor</option>
            {vendors.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}
          </select></label>
          <label>Parcel vendor phone<input disabled={busy} value={form.parcel_vendor_phone} onChange={e=>setForm({...form,parcel_vendor_phone:e.target.value})}/></label>
          <label>Trade / Business Licence Number<input disabled={busy} value={form.licence_number} onChange={e=>setForm({...form,licence_number:e.target.value})}/></label>
          <label>Trade / Business Licence Expiry<DateField type="date" disabled={busy} value={form.licence_expiry_date} onChange={e=>setForm({...form,licence_expiry_date:e.target.value})}/></label>
          <label>Excise Licence Number<input disabled={busy} value={form.excise_licence_number} onChange={e=>setForm({...form,excise_licence_number:e.target.value})}/></label>
          <label>Excise Expiry<DateField type="date" disabled={busy} value={form.excise_expiry_date} onChange={e=>setForm({...form,excise_expiry_date:e.target.value})}/></label>
          <label>Rent Agreement Expiry<DateField type="date" disabled={busy} value={form.rent_agreement_expiry_date} onChange={e=>setForm({...form,rent_agreement_expiry_date:e.target.value})}/></label>
        </div>

        <label>Address *<textarea required rows="3" disabled={busy} value={form.address} onChange={e=>setForm({...form,address:e.target.value})}/></label>

        <label>Notes<textarea rows="3" disabled={busy} value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></label>

        <div>
          <span className="eyebrow">Compliance Documents</span>
          <h3>Upload outlet documents</h3>
          <p className="muted">Files are linked to the new outlet automatically. No owner ID or document UUID is typed.</p>
        </div>

        <CreateDocumentGrid
          form={form}
          files={createFiles}
          setFiles={setCreateFiles}
          extraExpiry={createExtraExpiry}
          setExtraExpiry={setCreateExtraExpiry}
          progress={createProgress}
          busy={busy}
        />

        <button className="primary-button" disabled={busy}>
          {busy?"Saving Outlet & Documents…":"Add Outlet & Documents"}
        </button>
      </form>
    </section>}

    <section className="panel">
      <div className="panel-header">
        <div><h2>{management?"All outlets":"My assigned outlets"}</h2><p>{rows.length} outlet(s).</p></div>
        <input className="outlet-search" placeholder="Search outlet, cluster or vendor…" value={search} onChange={e=>setSearch(e.target.value)}/>
      </div>

      <div className="outlet-grid">
        {filtered.length===0?<div className="empty-state">No shops / outlets found.</div>:filtered.map(o=>
          <button type="button" className={`outlet-card ${selected?.id===o.id?"selected":""}`} key={o.id} onClick={()=>open(o.id)}>
            <div className="outlet-card-top">
              <span className="outlet-code">{o.code}</span>
              <span className={`outlet-state ${o.is_active?"active":"inactive"}`}>{o.is_active?"ACTIVE":"INACTIVE"}</span>
            </div>
            <h3>{o.name}</h3><p>{o.address}</p>
            <dl>
              <div><dt>Cluster</dt><dd>{o.cluster_name||"—"}</dd></div>
              <div><dt>Vendor</dt><dd>{o.vendor_name||"—"}</dd></div>
              <div><dt>Assistant</dt><dd>{o.assistant_vendor_name||"—"}</dd></div>
              <div><dt>Parcel</dt><dd>{o.parcel_vendor_name||"—"}</dd></div>
              <div><dt>Visitor Assignment</dt><dd>Per inspection</dd></div>
              <div><dt>Inspections</dt><dd>{o.inspection_count||0}</dd></div>
            </dl>
          </button>)}
      </div>
    </section>

    {selected&&<section className="panel outlet-detail">
      <div className="panel-header">
        <div><span className="eyebrow">{selected.code}</span><h2>{selected.name}</h2><p>{selected.address}</p></div>
        <div style={{display:"flex",gap:".6rem",alignItems:"center"}}>
          {admin&&!edit&&<button type="button" className="secondary-button" disabled={busy} onClick={()=>open(selected.id)}>
            Edit outlet
          </button>}
          <span className={`outlet-state ${selected.is_active?"active":"inactive"}`}>{selected.status}</span>
        </div>
      </div>

      <div className="outlet-summary-grid">
        <div><small>Cluster</small><strong>{selected.cluster_name||"—"}</strong></div>
        <div><small>Vendor</small><strong>{selected.vendor_name||"—"}</strong></div>
        <div><small>Assistant vendor</small><strong>{selected.assistant_vendor_name||"—"}</strong></div>
        <div><small>Parcel vendor</small><strong>{selected.parcel_vendor_name||"—"}</strong></div>
        <div><small>Vendor phone</small><strong>{selected.vendor_phone||"—"}</strong></div>
        <div><small>Licence expiry</small><strong>{selected.licence_expiry_date||"—"}</strong></div>
        <div><small>Excise expiry</small><strong>{selected.excise_expiry_date||"—"}</strong></div>
        <div><small>Inspections</small><strong>{selected.inspection_count||0}</strong></div>
      </div>

      {admin&&edit&&<form className="outlet-edit-form" onSubmit={save}>
        <h3>Edit outlet</h3>
        <div className="form-grid">
          <label>Name<input disabled={busy} value={edit.name} onChange={e=>setEdit({...edit,name:e.target.value})}/></label>
          <label>Type<input disabled={busy} value={edit.outlet_type} onChange={e=>setEdit({...edit,outlet_type:e.target.value.toUpperCase()})}/></label>
          <label>Cluster<input disabled={busy} value={edit.cluster_name} onChange={e=>setEdit({...edit,cluster_name:e.target.value})}/></label>
          <label>Latitude<input type="number" step="any" disabled={busy} value={edit.latitude} onChange={e=>setEdit({...edit,latitude:e.target.value})}/></label>
          <label>Longitude<input type="number" step="any" disabled={busy} value={edit.longitude} onChange={e=>setEdit({...edit,longitude:e.target.value})}/></label>
          <label>Attendance / inspection radius (metres)<input type="number" min="20" max="5000" disabled={busy} value={edit.attendance_radius_meters} onChange={e=>setEdit({...edit,attendance_radius_meters:e.target.value})}/></label>
          <label>Vendor<select disabled={busy} value={edit.vendor_id} onChange={e=>applyVendor(e.target.value,"edit")}>
            <option value="">No linked vendor</option>
            {vendors.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}
          </select></label>
          <label>Assistant vendor<select disabled={busy} value={edit.assistant_vendor_id} onChange={e=>applyVendor(e.target.value,"edit","assistant_vendor")}>
            <option value="">No assistant vendor</option>
            {vendors.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}
          </select></label>
          <label>Parcel vendor (optional)<select disabled={busy} value={edit.parcel_vendor_id} onChange={e=>applyVendor(e.target.value,"edit","parcel_vendor")}>
            <option value="">No parcel vendor</option>
            {vendors.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}
          </select></label>
          <label>Status<select disabled={busy} value={edit.status} onChange={e=>setEdit({...edit,status:e.target.value,is_active:e.target.value==="ACTIVE"})}>
            {["ACTIVE","INACTIVE","TEMPORARILY_CLOSED"].map(x=><option key={x}>{x}</option>)}
          </select></label>
          <label>Trade Licence Number<input disabled={busy} value={edit.licence_number} onChange={e=>setEdit({...edit,licence_number:e.target.value})}/></label>
          <label>Licence Expiry<DateField type="date" disabled={busy} value={edit.licence_expiry_date} onChange={e=>setEdit({...edit,licence_expiry_date:e.target.value})}/></label>
          <label>Excise Licence Number<input disabled={busy} value={edit.excise_licence_number} onChange={e=>setEdit({...edit,excise_licence_number:e.target.value})}/></label>
          <label>Excise Expiry<DateField type="date" disabled={busy} value={edit.excise_expiry_date} onChange={e=>setEdit({...edit,excise_expiry_date:e.target.value})}/></label>
          <label>Rent Expiry<DateField type="date" disabled={busy} value={edit.rent_agreement_expiry_date} onChange={e=>setEdit({...edit,rent_agreement_expiry_date:e.target.value})}/></label>
        </div>
        <label>Address<textarea rows="3" disabled={busy} value={edit.address} onChange={e=>setEdit({...edit,address:e.target.value})}/></label>
        <label>Notes<textarea rows="3" disabled={busy} value={edit.notes} onChange={e=>setEdit({...edit,notes:e.target.value})}/></label>
        <button className="primary-button" disabled={busy}>{busy?"Saving…":"Save outlet changes"}</button>
      </form>}

      <div className="outlet-related-grid">
        <article className="subpanel">
          <h3>Inspection visitor rotation</h3>
          <div className="empty-compact">
            Field visitors are assigned per inspection visit, not permanently to this outlet.
          </div>
          <p className="muted">
            The same field visitor is blocked for this outlet's next 3 inspections.
            Approved leave is excluded automatically and assignments are workload-balanced.
            Use Shop Inspections to schedule the next visit.
          </p>
        </article>

        <article className="subpanel">
          <h3>Inspection history</h3>
          <div className="simple-list">
            {inspections.length===0?<div className="empty-compact">No inspections yet.</div>:inspections.slice(0,12).map(r=>
              <div className="simple-row" key={r.id}>
                <div><strong>{r.report_number}</strong><span>{new Date(r.inspection_started_at).toLocaleString("en-GB",dateOptions({},true))}</span></div>
                <span>{String(r.status).replaceAll("_"," ")}</span>
              </div>)}
          </div>
        </article>

        <article className="subpanel">
          <div className="panel-header">
            <div>
              <h3>Outlet documents</h3>
              <p className="muted">
                Upload licences, agreements, blueprint, Fire NOC and other outlet documents.
              </p>
            </div>

            {admin&&<button
              type="button"
              className="primary-button"
              disabled={busy}
              onClick={showUploadManager}
            >
              + Upload Document
            </button>}
          </div>

          <div className="simple-list">
            {documents.length===0?<div className="empty-compact">No linked documents yet.</div>:documents.slice(0,20).map(d=>
              <div className="simple-row" key={d.id}>
                <div><strong>{d.title}</strong><span>{String(d.category).replaceAll("_"," ")} · {d.expiry_date||"No expiry"}</span></div>
                <span>{d.status}</span>
              </div>)}
          </div>
        </article>
      </div>

      {admin&&showDocumentManager&&<section
        className="subpanel"
        ref={documentManagerRef}
      >
        <div className="panel-header">
          <div>
            <span className="eyebrow">Document Manager</span>
            <h3>Upload / Renew Outlet Document</h3>
            <p className="muted">
              The selected outlet is linked automatically. No owner ID or document UUID is required.
            </p>
          </div>

          <button
            type="button"
            className="secondary-button"
            disabled={busy}
            onClick={()=>setShowDocumentManager(false)}
          >
            Close
          </button>
        </div>

        <form className="outlet-form" onSubmit={uploadManagedDocument}>
          <div className="form-grid">
            <label>Document Type *<select required disabled={busy} value={manageType} onChange={e=>setManageType(e.target.value)}>
              {DOC_TYPES.map(type=><option key={type.category} value={type.category}>{type.label}</option>)}
            </select></label>
            <label>Custom Title<input disabled={busy} value={manageTitle} onChange={e=>setManageTitle(e.target.value)}/></label>
            <label>Issue Date<DateField type="date" disabled={busy} value={manageIssueDate} onChange={e=>setManageIssueDate(e.target.value)}/></label>
            <label>Expiry / Renewal Date<DateField type="date" disabled={busy} value={manageExpiryDate} onChange={e=>setManageExpiryDate(e.target.value)}/></label>
          </div>

          <label>Description<textarea rows="3" disabled={busy} value={manageDescription} onChange={e=>setManageDescription(e.target.value)}/></label>

          <label className="file-drop">
            Document File *
            <input required type="file" accept=".pdf,image/*" disabled={busy}
              onChange={e=>{setManageFile(e.target.files?.[0]||null);setManageProgress(0)}}/>
            <span>{manageFile?`${manageFile.name} · ${Math.round(manageFile.size/1024)} KB`:"Choose image or PDF"}</span>
          </label>

          {manageProgress>0&&<div className="progress-bar"><span style={{width:`${manageProgress}%`}}/></div>}

          <button className="primary-button" disabled={busy}>{busy?"Uploading…":"Upload Outlet Document"}</button>
        </form>
      </section>}
    </section>}
  </div>
}
// date-display-ddmmyyyy-v1
