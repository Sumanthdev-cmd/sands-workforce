import {useEffect,useRef,useState} from "react";
import {displayDate,parseDisplayDate} from "./lib/displayDates";
export default function DateField(props){
 if(props.type&&props.type!=="date"&&props.type!=="datetime-local")return <input {...props}/>;
 return <DateEditor {...props}/>;
}
function DateEditor({value="",onChange,min,max,required,disabled,readOnly,type="date",...props}){
 const timed=type==="datetime-local";
 const label=timed?"DD/MM/YYYY HH:mm":"DD/MM/YYYY";
 const show=v=>v?displayDate(String(v).slice(0,10))+(timed?" "+String(v).slice(11,16):""):"";
 const [draft,setDraft]=useState(show(value));
 const input=useRef(null);
 useEffect(()=>{setDraft(show(value));input.current?.setCustomValidity("")},[value,type]);
 function change(text){
  setDraft(text);
  const datePart=timed?text.slice(0,10):text;
  let iso=text?parseDisplayDate(datePart):"";
  if(timed&&text){
   const t=/^\d{2}\/\d{2}\/\d{4} ([01]\d|2[0-3]):([0-5]\d)$/.exec(text);
   iso=iso&&t?iso+"T"+t[1]+":"+t[2]:null;
  }
  const error=text&&!iso?"Enter a valid date as "+label+".":iso&&min&&iso<min?"Date must be on or after "+show(min)+".":iso&&max&&iso>max?"Date must be on or before "+show(max)+".":"";
  input.current?.setCustomValidity(error);
  if(!error)onChange?.({target:{value:iso,name:props.name},currentTarget:{value:iso,name:props.name}});
 }
 return <span style={{display:"flex",alignItems:"center",gap:6,minWidth:0,width:"100%"}}>
  <input {...props} ref={input} type="text" inputMode={timed?"text":"numeric"} placeholder={label} aria-label={props["aria-label"]||"Date ("+label+")"} value={draft} required={required} disabled={disabled} readOnly={readOnly} maxLength={timed?16:10} onChange={e=>change(e.target.value)} style={{...props.style,minWidth:0,flex:1}}/>
  {!readOnly&&<input type={type} aria-label="Choose date from calendar" title="Choose date from calendar" value={value||""} min={min} max={max} disabled={disabled} onChange={e=>change(show(e.target.value))} style={{width:38,minWidth:38,padding:"6px 2px",color:"transparent"}}/>}
 </span>
}
