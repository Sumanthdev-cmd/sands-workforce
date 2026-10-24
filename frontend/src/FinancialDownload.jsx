import {useState} from 'react';
import {apiRequest} from './lib/api';
export default function FinancialDownload({kind,recordId}){
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 async function download(){setBusy(true);setError('');try{
  const result=await apiRequest(`/financial-records/${kind}/${recordId}/download-link`,{method:'POST'});
  const url=new URL(result.url,window.location.origin);
  if(url.origin!==window.location.origin)throw new Error('Unexpected download address.');
  const a=document.createElement('a');a.href=url.href;a.download='';a.referrerPolicy='no-referrer';document.body.appendChild(a);a.click();a.remove();
 }catch(e){setError(e.message)}finally{setBusy(false)}}
 return <span className="financial-download"><button type="button" className="secondary-button" disabled={busy} onClick={download}>{busy?'Preparing…':'Download PDF'}</button>{error&&<span role="alert" className="error-banner">{error}</span>}</span>
}
// date-display-ddmmyyyy-v1
