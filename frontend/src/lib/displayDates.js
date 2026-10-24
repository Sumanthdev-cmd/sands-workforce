export function displayDate(value){
 if(value===null||value===undefined||value==="")return "—";
 const text=String(value);
 const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
 if(m)return m[3]+"/"+m[2]+"/"+m[1];
 if(/^\d{4}-\d{2}-\d{2}T/.test(text)){
  const d=new Date(text);if(!Number.isNaN(d.getTime()))return d.toLocaleString("en-GB",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:true});
 }
 return text;
}
export function dateOptions(options={},dateTime=false){
 const result={...options};
 if(result.weekday&&!result.day&&!result.month&&!result.year&&!result.dateStyle)return result;
 delete result.dateStyle;
 const timeStyle=result.timeStyle;delete result.timeStyle;
 Object.assign(result,{day:"2-digit",month:"2-digit",year:"numeric"});
 if(dateTime){result.hour??="2-digit";result.minute??="2-digit";result.hour12??=true;if(timeStyle==="medium"||timeStyle==="long"||timeStyle==="full")result.second??="2-digit";}
 return result;
}
export function parseDisplayDate(value){
 const m=/^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
 if(!m||Number(m[3])<1)return null;
 const iso=m[3]+"-"+m[2]+"-"+m[1];
 const d=new Date(iso+"T12:00:00Z");
 return !Number.isNaN(d.getTime())&&d.toISOString().slice(0,10)===iso?iso:null;
}
