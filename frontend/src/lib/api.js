const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";
const OPENAPI_URL = import.meta.env.VITE_OPENAPI_URL || "/openapi.json";
const ACCESS = "sands_access_token";
const REFRESH = "sands_refresh_token";

export const getAccessToken = () => localStorage.getItem(ACCESS);
export const getRefreshToken = () => localStorage.getItem(REFRESH);
export const clearTokens = () => { localStorage.removeItem(ACCESS); localStorage.removeItem(REFRESH); };
export function saveTokens(data){ if(data?.access_token)localStorage.setItem(ACCESS,data.access_token); if(data?.refresh_token)localStorage.setItem(REFRESH,data.refresh_token); }

async function parse(response){ if(response.status===204)return null; const type=response.headers.get("content-type")||""; if(type.includes("application/json"))return response.json(); return response.text(); }
async function refreshToken(){ const token=getRefreshToken(); if(!token)throw new Error("Session expired."); const response=await fetch(`${API_BASE}/auth/refresh`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:token})}); const data=await parse(response); if(!response.ok){clearTokens(); throw new Error(data?.detail||"Session expired.");} saveTokens(data); return data.access_token; }

function readableLocation(loc){
  if(!Array.isArray(loc))return "";
  const cleaned=loc.filter((x)=>!["body","query","path"].includes(String(x))).map((x)=>String(x).replaceAll("_"," "));
  return cleaned.length?`${cleaned.join(" > ")}: `:"";
}

export function errorText(value){
  if(!value)return "Something went wrong.";
  if(typeof value==="string")return value;
  if(value instanceof Error)return value.message || "Something went wrong.";
  const detail=value.detail ?? value.message ?? value.error;
  if(Array.isArray(detail)){
    return detail.map((item)=>{
      if(typeof item==="string")return item;
      const loc=readableLocation(item?.loc);
      return `${loc}${item?.msg || JSON.stringify(item)}`;
    }).join(" | ");
  }
  if(detail&&typeof detail==="object"){
    if(Array.isArray(detail.errors))return errorText({detail:detail.errors});
    return Object.entries(detail).map(([key,val])=>`${key.replaceAll("_"," ")}: ${typeof val==="object"?JSON.stringify(val):val}`).join(" | ");
  }
  if(detail)return String(detail);
  try{return JSON.stringify(value)}catch{return String(value)}
}

export async function apiRequest(path,{method="GET",body,headers={},retry=true}={}){
  const normalized=path.startsWith("/")?path:`/${path}`;
  const requestHeaders={Accept:"application/json",...headers};
  const token=getAccessToken(); if(token)requestHeaders.Authorization=`Bearer ${token}`;
  let payload=body;
  if(body!==undefined&&body!==null&&!(body instanceof FormData)&&typeof body!=="string"){requestHeaders["Content-Type"]="application/json"; payload=JSON.stringify(body);}
  const response=await fetch(`${API_BASE}${normalized}`,{method,headers:requestHeaders,body:["GET","HEAD"].includes(method.toUpperCase())?undefined:payload});
  if(response.status===401&&retry&&getRefreshToken()){await refreshToken(); return apiRequest(path,{method,body,headers,retry:false});}
  const data=await parse(response);
  if(!response.ok){const error=new Error(errorText(data)||`HTTP ${response.status}`); error.status=response.status; error.data=data; throw error;}
  return data;
}

export async function login(credentials){const data=await apiRequest("/auth/login",{method:"POST",body:credentials,retry:false}); saveTokens(data); return data;}
export async function logout(){const token=getRefreshToken(); try{if(token)await apiRequest("/auth/logout",{method:"POST",body:{refresh_token:token},retry:false});}finally{clearTokens();}}

let schemaCache=null;
export async function getOpenApi(){if(schemaCache)return schemaCache; const response=await fetch(OPENAPI_URL); if(!response.ok)throw new Error("Unable to load backend form schema."); schemaCache=await response.json(); return schemaCache;}
export function normalizeOpenApiPath(path){const plain=path.split("?")[0]; return plain.startsWith("/api/v1")?plain:`/api/v1${plain}`;}
export function resolveRef(schema,node){if(!node)return {}; if(!node.$ref)return node; return node.$ref.replace(/^#\//,"").split("/").reduce((value,key)=>value?.[key],schema)||{};}
export function getOperation(schema,method,path){if(!schema)return null; return schema.paths?.[normalizeOpenApiPath(path)]?.[method.toLowerCase()]||null;}
export function getRequestSchema(schema,operation){const node=operation?.requestBody?.content?.["application/json"]?.schema; return resolveRef(schema,node);}

export function uploadWithProgress(url,file,contentType,onProgress){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest(); xhr.open("PUT",url); xhr.setRequestHeader("Content-Type",contentType); xhr.upload.onprogress=(event)=>{if(event.lengthComputable)onProgress?.(Math.round(event.loaded/event.total*100));}; xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve(xhr.getResponseHeader("ETag")):reject(new Error(`Upload failed with HTTP ${xhr.status}`)); xhr.onerror=()=>reject(new Error("Upload failed.")); xhr.send(file);});}
