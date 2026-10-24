import {useEffect,useState} from "react";
import {apiRequest} from "./lib/api";
export default function EmployeeMasterSelect({kind,label,value,onChange,current,canCreate}){
 const [roleItems,setRoleItems]=useState([]);
 const [items,setItems]=useState([]),[loading,setLoading]=useState(true),[error,setError]=useState(""),[adding,setAdding]=useState(false),[saving,setSaving]=useState(false),[code,setCode]=useState(""),[name,setName]=useState(""),[notice,setNotice]=useState("");
 const endpoint="/master-data/"+kind;
 const readable=e=>Array.isArray(e?.data?.detail)?e.data.detail.map(x=>x.msg).join(" "):e.message||"Request failed.";
 async function load(){
  setLoading(true);setError("");
  try{const data=await apiRequest(endpoint);if(!Array.isArray(data))throw new Error("Unexpected response. Please retry.");setItems(data);if(kind==="designations"){const roleData=await apiRequest("/master-data/roles");if(!Array.isArray(roleData))throw new Error("Invalid role options.");setRoleItems(roleData.filter(r=>r.is_active!==false))}}
  catch(e){setError("Could not load "+label.toLowerCase()+" options: "+readable(e))}
  finally{setLoading(false)}
 }
 useEffect(()=>{load()},[endpoint]);
 async function add(){
  if(saving)return;
  if(name.trim().length<2){setError("Enter a name with at least two characters.");return}
  setSaving(true);setError("");setNotice("");
  try{
   const internalCode=code||("D_"+crypto.randomUUID().replaceAll("-","").toUpperCase());setCode(internalCode);
   const saved=await apiRequest(endpoint,{method:"POST",body:{code:internalCode,name:name.trim()}});
   setItems(old=>[...old.filter(x=>x.id!==saved.id),saved]);onChange(saved.id);
   setAdding(false);setCode("");setName("");setNotice(label+" added and selected. Save employee to apply the assignment.");
  }catch(e){setError(readable(e))}
  finally{setSaving(false)}
 }
 async function choose(selected){
  if(kind!=="designations"||!selected.startsWith("role:")){onChange(selected);return}
  const role=roleItems.find(r=>r.code===selected.slice(5));if(!role)return;
  setSaving(true);setError("");setNotice("");
  try{
   const matches=items.filter(d=>d.code.toUpperCase()===role.code.toUpperCase()||d.name.toLowerCase()===role.name.toLowerCase());
   if(matches.length>1)throw new Error("Multiple designations match this role. Ask Admin to resolve the duplicate code/name.");
   let item=matches[0];
   if(item?.is_active===false)throw new Error("This role's designation is inactive. Ask Admin to reactivate it first.");
   if(!item){
    try{item=await apiRequest(endpoint,{method:"POST",body:{code:role.code,name:role.name}})}
    catch(e){
     if(e.status!==409)throw e;
     const latest=await apiRequest(endpoint);
     item=latest.find(d=>d.is_active!==false&&d.code===role.code&&d.name===role.name);
     if(!item)throw e;
    }
    setItems(old=>[...old.filter(d=>d.id!==item.id),item]);
   }
   onChange(item.id);setNotice("Designation selected. Save employee to apply. Login permissions are unchanged.");
  }catch(e){setError(readable(e))}finally{setSaving(false)}
 }
 const options=items.filter(x=>x.is_active!==false||x.id===value);
 const missing=value&&!options.some(x=>x.id===value);
 return <div className="emp-field">
  <label><span>{label}</span><select aria-label={label} value={value} disabled={loading||saving} onChange={e=>choose(e.target.value)}>
   <option value="">Not assigned</option>
   {missing&&<option value={value}>{current?.name||"Current assignment"} (retained)</option>}
   {kind==="designations"?<>
    {value&&options.find(x=>x.id===value)&&<option value={value}>{options.find(x=>x.id===value).name} (current)</option>}
    {roleItems.map(r=><option key={r.code} value={"role:"+r.code}>{r.name}</option>)}
   </>:options.map(x=><option key={x.id} value={x.id}>{x.name}{x.is_active===false?" (inactive)":""}</option>)}
  </select></label>
  {loading?<small>Loading {label.toLowerCase()} options…</small>:!error&&(kind==="designations"?roleItems:options).length===0&&<small>No active {kind==="designations"?"roles":kind} are available for this organisation.</small>}
  {error&&<div role="alert" style={{color:"#b91c1c",overflowWrap:"anywhere"}}>{error}</div>}
  {notice&&<small role="status" style={{color:"#047857"}}>{notice}</small>}
  <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
   <button type="button" className="secondary-button" disabled={loading||saving} onClick={load}>{error?"Retry":"Refresh options"}</button>
   {canCreate&&kind!=="designations"&&<button type="button" className="secondary-button" disabled={saving} onClick={()=>{setAdding(!adding);setError("");setNotice("")}}>{adding?"Cancel":"Add "+label.toLowerCase()}</button>}
  </div>
  {kind==="designations"&&<small>Choose an existing organisation role as the designation. This does not assign access permissions.</small>}
  {adding&&<div style={{display:"grid",gap:8,padding:12,border:"1px solid #dbe4ef",borderRadius:8}}>
   <label>Name<input aria-label={label+" name"} maxLength={120} value={name} disabled={saving} placeholder={kind==="departments"?"e.g. Accounts":"e.g. Cashier"} onChange={e=>setName(e.target.value)}/></label>
   <small>This adds an option for your organisation. It does not change login roles or permissions.</small>
   <button type="button" className="primary-button" disabled={saving} onClick={add}>{saving?"Adding…":"Save "+label.toLowerCase()}</button>
  </div>}
 </div>
}
// date-display-ddmmyyyy-v1
