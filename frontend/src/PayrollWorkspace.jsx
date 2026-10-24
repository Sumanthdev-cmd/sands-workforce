import DateField from "./DateField";
import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import {useEffect,useMemo,useRef,useState} from "react";
import {useLocation} from "react-router-dom";
import {useAuth} from "./context/AuthContext";
import {apiRequest} from "./lib/api";

const PAYROLL_ADMIN_ROLES=["ADMIN","MD","GM"];
const PAYROLL_OPERATOR_ROLES=["ADMIN","GM"];

const today=()=>new Date().toISOString().slice(0,10);

function payrollPeriodEnded(run){
  return Boolean(run?.period_end) && run.period_end<=today();
}

function canDeletePayrollRun(run){
  return ["DRAFT","CALCULATED","RETURNED"].includes(run?.status);
}

function monthRange(){
  const now=new Date();
  const start=new Date(now.getFullYear(),now.getMonth(),1);
  const end=new Date(now.getFullYear(),now.getMonth()+1,0);
  const iso=d=>new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,10);
  return {period_start:iso(start),period_end:iso(end)};
}

const freshSalary=()=>({
  effective_from:today(),
  basic_salary:"",
  hra:"0",
  conveyance_allowance:"0",
  other_allowance:"0",
  daily_allowance:"0",
  fixed_deduction:"0",
  currency:"INR",
  reason:"",
});

const freshNotice=()=>({
  employee_id:"",
  start_date:today(),
  end_date:today(),
  reason:"",
});

const freshHold=()=>({
  employee_id:"",
  hold_from:today(),
  hold_to:"",
  reason:"",
});

const freshAdvance=()=>({
  requested_amount:"",
  installment_amount:"",
  recovery_months:"1",
  currency:"INR",
  reason:"",
});

const freshVendorSalary=()=>({
  effective_from:today(),
  basic_salary:"",
  hra:"0",
  conveyance_allowance:"0",
  other_allowance:"0",
  daily_allowance:"0",
  fixed_deduction:"0",
  currency:"INR",
  reason:"",
});

const freshVendorClosure=()=>({
  closure_date:today(),
  reason:"",
});

function errText(error){
  const value=error?.data?.detail??error?.detail??error?.message??error;
  if(typeof value==="string"){
    return value==="[object Object]"
      ?"The request could not be completed."
      :value;
  }
  if(Array.isArray(value)){
    return value.map(item=>item?.msg||"Invalid information.").join(" ");
  }
  if(value&&typeof value==="object"&&Array.isArray(value.detail)){
    return value.detail.map(item=>item?.msg||"Invalid information.").join(" ");
  }
  if(value&&typeof value==="object"&&typeof value.message==="string"){
    return value.message;
  }
  return "The request could not be completed.";
}

function vendorOutletLabel(vendor){
  const outlets=(vendor.outlets||[]).map(row=>{
    const role=row.role&&row.role!=="PRIMARY" ? ` - ${row.role.toLowerCase()}` : "";
    return `${row.name}${role}`;
  });
  return outlets.length ? outlets.join(", ") : "No assigned shop";
}

function empName(employee){
  return employee?.full_name ||
    [employee?.first_name,employee?.last_name].filter(Boolean).join(" ") ||
    employee?.name ||
    "";
}

function empCode(employee){
  return employee?.employee_code ||
    employee?.user?.employee_code ||
    employee?.code ||
    "";
}

function pretty(value){
  return String(value||"")
    .replaceAll("_"," ")
    .toLowerCase()
    .replace(/\b\w/g,char=>char.toUpperCase());
}

function money(value,currency="INR"){
  try{
    return new Intl.NumberFormat("en-IN",{
      style:"currency",
      currency:currency||"INR",
      maximumFractionDigits:2,
    }).format(Number(value||0));
  }catch{
    return `${currency||"INR"} ${Number(value||0).toFixed(2)}`;
  }
}

function Status({value}){
  return (
    <span className={`outlet-state ${String(value||"").toLowerCase()}`}>
      {pretty(value)}
    </span>
  );
}

function employeeLabel(employee){
  const name=empName(employee)||"Unnamed Employee";
  const code=empCode(employee);
  return code?`${code} — ${name}`:name;
}

export default function PayrollWorkspace(){
  const {roles=[]}=useAuth();
  const location=useLocation();

  const payrollAdmin=roles.some(role=>PAYROLL_ADMIN_ROLES.includes(role));
  const payrollOperator=roles.some(role=>PAYROLL_OPERATOR_ROLES.includes(role));
  const isMD=roles.includes("MD");
  const isAdmin=roles.includes("ADMIN");
  const isAdvanceManager=isAdmin||isMD;

  const [employees,setEmployees]=useState([]);
  const [runs,setRuns]=useState([]);
  const [holds,setHolds]=useState([]);
  const [payslips,setPayslips]=useState([]);
  const [noticePeriods,setNoticePeriods]=useState([]);
  const [myAdvances,setMyAdvances]=useState([]);
  const [organizationAdvances,setOrganizationAdvances]=useState([]);
  const [vendors,setVendors]=useState([]);
  const [vendorClosures,setVendorClosures]=useState([]);

  const [selectedRun,setSelectedRun]=useState(null);
  const [runItems,setRunItems]=useState([]);
  const [vendorItems,setVendorItems]=useState([]);
  const [workingCalendar,setWorkingCalendar]=useState(null);
  const [showWorkingCalendar,setShowWorkingCalendar]=useState(false);
  const [runFeedback,setRunFeedback]=useState({});

  const [salaryEmployeeId,setSalaryEmployeeId]=useState("");
  const [structures,setStructures]=useState([]);
  const [salaryForm,setSalaryForm]=useState(freshSalary);
  const [salaryVendorId,setSalaryVendorId]=useState("");
  const [vendorStructures,setVendorStructures]=useState([]);
  const [vendorSalaryForm,setVendorSalaryForm]=useState(freshVendorSalary);
  const [vendorClosureForm,setVendorClosureForm]=useState(freshVendorClosure);

  const [runForm,setRunForm]=useState(monthRange);
  const [holdForm,setHoldForm]=useState(freshHold);
  const [noticeForm,setNoticeForm]=useState(freshNotice);
  const [advanceForm,setAdvanceForm]=useState(freshAdvance);

  const [showRunForm,setShowRunForm]=useState(false);
  const [showSalaryForm,setShowSalaryForm]=useState(false);
  const [showHoldForm,setShowHoldForm]=useState(false);
  const [showReleasedHolds,setShowReleasedHolds]=useState(false);
  const [showNoticeForm,setShowNoticeForm]=useState(false);
  const [showAdvanceForm,setShowAdvanceForm]=useState(false);
  const [showVendorSalaryForm,setShowVendorSalaryForm]=useState(false);
  const [showVendorClosureForm,setShowVendorClosureForm]=useState(false);

  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");

  const lock=useRef(false);
  const runDetailsRef=useRef(null);
  const approvalQueueRef=useRef(null);
  const advanceRef=useRef(null);

  const sortedEmployees=useMemo(
    ()=>[...employees].sort((a,b)=>{
      const byName=empName(a).localeCompare(
        empName(b),
        undefined,
        {sensitivity:"base"}
      );
      if(byName!==0)return byName;
      return empCode(a).localeCompare(
        empCode(b),
        undefined,
        {sensitivity:"base"}
      );
    }),
    [employees]
  );

  const employeeMap=useMemo(
    ()=>Object.fromEntries(
      employees.map(employee=>[employee.id,employee])
    ),
    [employees]
  );

  const activeStructures=structures.filter(row=>row.is_active);
  const latestStructure=activeStructures[0]||structures[0]||null;
  const currentStructure=structures.find(
    row=>row.is_active&&row.effective_from<=today()
  )||null;
  function structureStatus(row){
    if(!row.is_active)return "INACTIVE";
    if(currentStructure?.id===row.id)return "CURRENT";
    if(row.effective_from>today())return "SCHEDULED";
    return "HISTORICAL";
  }
  const latestVendorStructure=vendorStructures.find(
    row=>row.is_active&&row.effective_from<=today()
  )||vendorStructures.find(row=>row.is_active)||vendorStructures[0]||null;
  const pendingApprovalRuns=runs.filter(
    row=>row.status==="SUBMITTED_FOR_MD_APPROVAL"
  );

  async function load(){
    setLoading(true);
    setError("");

    try{
      const requests=[
        apiRequest("/payroll/me/payslips").catch(()=>[]),
        apiRequest("/salary-advances/mine").catch(()=>[]),
      ];

      if(payrollAdmin){
        requests.push(
          apiRequest("/employees").catch(()=>[]),
          apiRequest("/payroll/runs").catch(()=>[]),
          apiRequest(`/payroll/holds?active_only=${showReleasedHolds?"false":"true"}`).catch(()=>[]),
          apiRequest("/workforce-policy/notice-periods").catch(()=>[]),
          apiRequest("/payroll/vendors").catch(()=>[]),
          apiRequest("/payroll/vendor-closures").catch(()=>[])
        );
      }

      if(isAdvanceManager){
        requests.push(apiRequest("/salary-advances").catch(()=>[]));
      }

      const results=await Promise.all(requests);

      setPayslips(Array.isArray(results[0])?results[0]:[]);
      setMyAdvances(Array.isArray(results[1])?results[1]:[]);

      let resultIndex=2;

      if(payrollAdmin){
        setEmployees(Array.isArray(results[resultIndex])?results[resultIndex]:[]);
        setRuns(Array.isArray(results[resultIndex+1])?results[resultIndex+1]:[]);
        setHolds(Array.isArray(results[resultIndex+2])?results[resultIndex+2]:[]);
        setNoticePeriods(Array.isArray(results[resultIndex+3])?results[resultIndex+3]:[]);
        setVendors(Array.isArray(results[resultIndex+4])?results[resultIndex+4]:[]);
        setVendorClosures(Array.isArray(results[resultIndex+5])?results[resultIndex+5]:[]);
        resultIndex+=6;
      }else{
        setEmployees([]);
        setRuns([]);
        setHolds([]);
        setNoticePeriods([]);
        setVendors([]);
        setVendorClosures([]);
      }

      if(isAdvanceManager){
        setOrganizationAdvances(
          Array.isArray(results[resultIndex])?results[resultIndex]:[]
        );
      }else{
        setOrganizationAdvances([]);
      }
    }catch(error){
      setError(errText(error));
    }finally{
      setLoading(false);
    }
  }

  useEffect(()=>{
    load();
  },[payrollAdmin,isAdvanceManager,showReleasedHolds]);

  useEffect(()=>{
    const params=new URLSearchParams(location.search);
    const runId=params.get("run");
    if(runId&&runs.length){
      const run=runs.find(row=>row.id===runId);
      if(run)openRun(run);
    }else if(params.get("queue")==="1"&&isMD){
      window.setTimeout(()=>approvalQueueRef.current?.scrollIntoView({behavior:"smooth",block:"start"}),120);
    }else if(params.get("advance")==="1"){
      window.setTimeout(()=>advanceRef.current?.scrollIntoView({behavior:"smooth",block:"start"}),120);
    }
  },[location.search,runs.length,isMD,myAdvances.length,organizationAdvances.length]);

  async function runAction(success,path,body,onError){
    if(lock.current)return;

    lock.current=true;
    setBusy(true);
    setError("");
    setMessage("");

    try{
      const result=await apiRequest(
        path,
        {
          method:"POST",
          ...(body===undefined?{}:{body}),
        }
      );

      setMessage(success);
      window.dispatchEvent(new Event("action-alerts:refresh"));
      await load();

      if(selectedRun?.id){
        const refreshed=
          result?.id===selectedRun.id
            ?result
            :runs.find(row=>row.id===selectedRun.id)||selectedRun;
        setSelectedRun(refreshed);

        const [items,vendorRows,calendar]=await Promise.all([
          apiRequest(`/payroll/runs/${selectedRun.id}/items`).catch(()=>[]),
          apiRequest(`/payroll/runs/${selectedRun.id}/vendor-items`).catch(()=>[]),
          apiRequest(`/payroll/runs/${selectedRun.id}/working-calendar`).catch(()=>null),
        ]);
        setRunItems(Array.isArray(items)?items:[]);
        setVendorItems(Array.isArray(vendorRows)?vendorRows:[]);
        setWorkingCalendar(calendar);
      }

      return result;
    }catch(error){
      const text=errText(error);
      setError(text);
      onError?.(text);
      return null;
    }finally{
      lock.current=false;
      setBusy(false);
    }
  }

  async function createAdvance(event){
    event.preventDefault();
    const amount=Number(advanceForm.requested_amount);
    const installment=Number(advanceForm.installment_amount);
    const months=Number(advanceForm.recovery_months);

    if(!(amount>0)||!(installment>0)||!Number.isInteger(months)||months<1){
      setError("Enter a valid advance amount, monthly deduction and recovery duration.");
      return;
    }
    if(installment>amount){
      setError("The monthly deduction cannot exceed the requested advance.");
      return;
    }
    const expectedMonths=Math.ceil(
      Math.round(amount*100)/Math.round(installment*100)
    );
    if(months!==expectedMonths){
      setError(
        `This deduction recovers the advance in ${expectedMonths} month(s). `+
        "Adjust the monthly deduction or recovery duration so they match."
      );
      return;
    }
    if(advanceForm.reason.trim().length<5){
      setError("Enter a reason of at least 5 characters.");
      return;
    }

    const result=await runAction(
      "Salary advance request sent to MD for approval.",
      "/salary-advances",
      {
        requested_amount:amount,
        installment_amount:installment,
        recovery_months:months,
        currency:advanceForm.currency.trim().toUpperCase(),
        reason:advanceForm.reason.trim(),
      }
    );
    if(result){
      setAdvanceForm(freshAdvance());
      setShowAdvanceForm(false);
    }
  }

  async function cancelAdvance(advance){
    const note=window.prompt(
      `Why are you cancelling this ${money(advance.requested_amount,advance.currency)} request?`,
      ""
    );
    if(note===null)return;
    if(note.trim().length<3){setError("Enter a cancellation reason of at least 3 characters.");return;}
    await runAction(
      "Salary advance request cancelled.",
      `/salary-advances/${advance.id}/cancel`,
      {note:note.trim()}
    );
  }

  async function decideAdvance(advance,approved){
    if(!isMD){setError("Only an MD can approve or reject a salary advance.");return;}
    const note=window.prompt(
      `${approved?"Approve":"Reject"} ${advance.employee_code} — ${advance.employee_name}'s `+
      `${money(advance.requested_amount,advance.currency)} request?\n\n`+
      `${approved?"Decision note (optional)":"Rejection reason (required)"}:`,
      ""
    );
    if(note===null)return;
    if(!approved&&note.trim().length<3){setError("Enter a rejection reason of at least 3 characters.");return;}
    await runAction(
      `Salary advance ${approved?"approved":"rejected"}.`,
      `/salary-advances/${advance.id}/decision`,
      {approved,note:note.trim()||null}
    );
  }

  async function disburseAdvance(advance){
    if(!isAdmin){setError("Only ADMIN can record salary-advance disbursement.");return;}
    const reference=window.prompt(
      `Record payment reference for ${advance.employee_code} — ${advance.employee_name}:`,
      ""
    );
    if(reference===null)return;
    if(reference.trim().length<2){setError("Enter a payment reference of at least 2 characters.");return;}
    const note=window.prompt("Disbursement note (optional):","");
    if(note===null)return;
    await runAction(
      "Salary advance marked as disbursed. Payroll recovery is now scheduled.",
      `/salary-advances/${advance.id}/disburse`,
      {payment_reference:reference.trim(),note:note.trim()||null}
    );
  }

  async function createRun(event){
    event.preventDefault();

    if(runForm.period_end<runForm.period_start){
      setError("Payroll period end cannot be earlier than the start date.");
      return;
    }

    const result=await runAction(
      "Payroll run created.",
      "/payroll/runs",
      {
        period_start:runForm.period_start,
        period_end:runForm.period_end,
      }
    );

    if(result){
      setShowRunForm(false);
      setSelectedRun(result);
      setRunItems([]);
      setVendorItems([]);
    }
  }

 async function openRun(run){
  setSelectedRun(run);
  setError("");

  try{
    const [items,vendorRows,calendar]=await Promise.all([
      apiRequest(`/payroll/runs/${run.id}/items`),
      apiRequest(`/payroll/runs/${run.id}/vendor-items`),
      apiRequest(`/payroll/runs/${run.id}/working-calendar`),
    ]);

    setRunItems(
      Array.isArray(items)
        ?items
        :[]
    );
    setVendorItems(Array.isArray(vendorRows)?vendorRows:[]);
    setWorkingCalendar(calendar||null);
    setShowWorkingCalendar(false);

    window.setTimeout(()=>{
      runDetailsRef.current?.scrollIntoView({
        behavior:"smooth",
        block:"start",
      });
    },100);

  }catch(error){
    setRunItems([]);
    setVendorItems([]);
    setWorkingCalendar(null);
    setError(errText(error));
  }
}

  async function downloadPayroll(run){
    setError("");
    setBusy(true);
    try{
      const csv=await apiRequest(`/payroll/runs/${run.id}/export.csv`);
      const blob=new Blob([csv],{type:"text/csv;charset=utf-8"});
      const url=URL.createObjectURL(blob);
      const link=document.createElement("a");
      link.href=url;
      link.download=`payroll_${run.period_start}_to_${run.period_end}_finalized.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setMessage("Finalized payroll downloaded.");
    }catch(error){setError(errText(error))}
    finally{setBusy(false)}
  }

  async function printPayroll(run){
    const popup=window.open("","_blank","width=1200,height=850");
    if(!popup){setError("Pop-up was blocked. Allow pop-ups to print the payroll.");return}
    popup.document.write("<p style='font-family:Arial;padding:24px'>Preparing finalized payroll…</p>");
    setError("");
    try{
      const html=await apiRequest(`/payroll/runs/${run.id}/print`);
      popup.document.open();
      popup.document.write(html);
      popup.document.close();
    }catch(error){
      popup.close();
      setError(errText(error));
    }
  }

  async function calculateRun(run){
    setRunFeedback(previous=>({...previous,[run.id]:""}));
    const result=await runAction(
      `Payroll calculated for ${formatDisplayDate(run.period_start)} to ${formatDisplayDate(run.period_end)}.`,
      `/payroll/runs/${run.id}/calculate`,
      undefined,
      text=>setRunFeedback(previous=>({...previous,[run.id]:text}))
    );

    if(result){
      setRunFeedback(previous=>({...previous,[run.id]:""}));
      setSelectedRun(result);
      const [items,vendorRows,calendar]=await Promise.all([
        apiRequest(`/payroll/runs/${run.id}/items`).catch(()=>[]),
        apiRequest(`/payroll/runs/${run.id}/vendor-items`).catch(()=>[]),
        apiRequest(`/payroll/runs/${run.id}/working-calendar`).catch(()=>null),
      ]);
      setRunItems(Array.isArray(items)?items:[]);
      setVendorItems(Array.isArray(vendorRows)?vendorRows:[]);
      setWorkingCalendar(calendar);
    }
  }

  async function deletePayrollRun(run){
    if(!canDeletePayrollRun(run))return;
    const confirmed=window.confirm(
      `Delete payroll run ${formatDisplayDate(run.period_start)} to ${formatDisplayDate(run.period_end)}?\n\n`+
      "This removes only this draft/calculated payroll run and its calculated employee/vendor rows. Attendance, salary structures and vendor records are not deleted."
    );
    if(!confirmed)return;

    setBusy(true);
    setError("");
    setMessage("");
    try{
      await apiRequest(`/payroll/runs/${run.id}`,{method:"DELETE"});
      setMessage(`Payroll run ${formatDisplayDate(run.period_start)} to ${formatDisplayDate(run.period_end)} deleted.`);
      setRuns(previous=>previous.filter(row=>row.id!==run.id));
      if(selectedRun?.id===run.id){
        setSelectedRun(null);
        setRunItems([]);
        setVendorItems([]);
        setWorkingCalendar(null);
      }
      window.dispatchEvent(new Event("action-alerts:refresh"));
      await load();
    }catch(error){
      setError(errText(error));
    }finally{
      setBusy(false);
    }
  }

  async function submitForApproval(run){
    const note=window.prompt(
      `Submit payroll for ${formatDisplayDate(run.period_start)} to ${formatDisplayDate(run.period_end)} to MD for approval?\n\nSubmission note (optional):`,
      run.submission_note||""
    );
    if(note===null)return;
    const result=await runAction(
      "Payroll submitted to MD for approval.",
      `/payroll/runs/${run.id}/submit-approval`,
      {note:note.trim()||null}
    );
    if(result)setSelectedRun(result);
  }

  async function approveRun(run){
    if(!isMD){setError("Only an MD can approve and finalize payroll.");return;}
    const note=window.prompt(
      `Approve and finalize payroll for ${formatDisplayDate(run.period_start)} to ${formatDisplayDate(run.period_end)}?\n\nMD approval note (optional):`,
      run.approval_note||""
    );
    if(note===null)return;
    if(!window.confirm("After MD approval this payroll becomes FINALIZED and cannot be recalculated. Continue?"))return;
    const result=await runAction(
      "Payroll approved and finalized by MD.",
      `/payroll/runs/${run.id}/approve`,
      {note:note.trim()||null}
    );
    if(result)setSelectedRun(result);
  }

  async function returnRun(run){
    if(!isMD){setError("Only an MD can return payroll for correction.");return;}
    const reason=window.prompt(
      `Return payroll for ${formatDisplayDate(run.period_start)} to ${formatDisplayDate(run.period_end)} for correction.\n\nReason:`,
      run.return_note||""
    );
    if(reason===null)return;
    if(reason.trim().length<3){setError("Return reason must contain at least 3 characters.");return;}
    const result=await runAction(
      "Payroll returned for correction.",
      `/payroll/runs/${run.id}/return`,
      {reason:reason.trim()}
    );
    if(result)setSelectedRun(result);
  }

  async function selectSalaryEmployee(employeeId){
    setSalaryEmployeeId(employeeId);
    setStructures([]);
    setError("");
    setSalaryForm(freshSalary());

    if(!employeeId)return;

    try{
      const data=await apiRequest(
        `/payroll/structures/${employeeId}`
      );
      const rows=Array.isArray(data)?data:[];
      setStructures(rows);

      const current=rows.find(
        row=>row.is_active&&row.effective_from<=today()
      )||rows.find(row=>row.is_active)||rows[0];
      if(current){
        setSalaryForm({
          effective_from:today(),
          basic_salary:String(current.basic_salary??""),
          hra:String(current.hra??0),
          conveyance_allowance:String(current.conveyance_allowance??0),
          other_allowance:String(current.other_allowance??0),
          daily_allowance:String(current.daily_allowance??0),
          fixed_deduction:String(current.fixed_deduction??0),
          currency:current.currency||"INR",
          reason:"",
        });
      }
    }catch(error){
      setError(errText(error));
    }
  }

  function salaryPayload(includeReason=false){
    const payload={
      effective_from:salaryForm.effective_from,
      basic_salary:Number(salaryForm.basic_salary||0),
      hra:Number(salaryForm.hra||0),
      conveyance_allowance:Number(salaryForm.conveyance_allowance||0),
      other_allowance:Number(salaryForm.other_allowance||0),
      daily_allowance:Number(salaryForm.daily_allowance||0),
      fixed_deduction:Number(salaryForm.fixed_deduction||0),
      currency:salaryForm.currency.trim().toUpperCase(),
    };

    if(includeReason){
      payload.reason=salaryForm.reason.trim();
    }

    return payload;
  }

  async function createStructure(event){
    event.preventDefault();

    if(!salaryEmployeeId){
      setError("Select an employee.");
      return;
    }

    const result=await runAction(
      "Salary structure created.",
      `/payroll/structures/${salaryEmployeeId}`,
      salaryPayload(false)
    );

    if(result){
      await selectSalaryEmployee(salaryEmployeeId);
      setShowSalaryForm(false);
    }
  }

  async function reviseStructure(event){
    event.preventDefault();

    if(!salaryEmployeeId){
      setError("Select an employee.");
      return;
    }

    if(salaryForm.reason.trim().length<3){
      setError("Enter a salary revision reason of at least 3 characters.");
      return;
    }

    const result=await runAction(
      "Salary revised successfully.",
      `/payroll/structures/${salaryEmployeeId}/revise`,
      salaryPayload(true)
    );

    if(result){
      await selectSalaryEmployee(salaryEmployeeId);
      setShowSalaryForm(false);
    }
  }

  async function selectSalaryVendor(vendorId){
    setSalaryVendorId(vendorId);
    setVendorStructures([]);
    setVendorSalaryForm(freshVendorSalary());
    setShowVendorSalaryForm(false);
    setError("");
    if(!vendorId)return;
    try{
      const data=await apiRequest(`/payroll/vendor-structures/${vendorId}`);
      const rows=Array.isArray(data)?data:[];
      setVendorStructures(rows);
      const current=rows.find(row=>row.is_active&&row.effective_from<=today())||rows[0];
      if(current){
        setVendorSalaryForm({
          effective_from:today(),
          basic_salary:String(current.basic_salary??current.monthly_salary??""),
          hra:String(current.hra??0),
          conveyance_allowance:String(current.conveyance_allowance??0),
          other_allowance:String(current.other_allowance??0),
          daily_allowance:String(current.daily_allowance??0),
          fixed_deduction:String(current.fixed_deduction??0),
          currency:current.currency||"INR",
          reason:"",
        });
      }
    }catch(error){
      setError(errText(error));
    }
  }

  async function saveVendorSalary(event){
    event.preventDefault();
    if(!salaryVendorId){setError("Select a vendor.");return;}
    if(latestVendorStructure&&vendorSalaryForm.reason.trim().length<3){
      setError("Enter a vendor salary revision reason of at least 3 characters.");
      return;
    }
    const result=await runAction(
      latestVendorStructure?"Vendor salary revised.":"Initial vendor salary fixed.",
      `/payroll/vendor-structures/${salaryVendorId}`,
      {
        effective_from:vendorSalaryForm.effective_from,
        basic_salary:Number(vendorSalaryForm.basic_salary||0),
        hra:Number(vendorSalaryForm.hra||0),
        conveyance_allowance:Number(vendorSalaryForm.conveyance_allowance||0),
        other_allowance:Number(vendorSalaryForm.other_allowance||0),
        daily_allowance:Number(vendorSalaryForm.daily_allowance||0),
        fixed_deduction:Number(vendorSalaryForm.fixed_deduction||0),
        currency:vendorSalaryForm.currency.trim().toUpperCase(),
        reason:latestVendorStructure?vendorSalaryForm.reason.trim():null,
      }
    );
    if(result){
      await selectSalaryVendor(salaryVendorId);
      setShowVendorSalaryForm(false);
    }
  }

  async function addVendorClosure(event){
    event.preventDefault();
    if(vendorClosureForm.reason.trim().length<3){
      setError("Enter the government closure reason.");
      return;
    }
    const result=await runAction(
      "Vendor government-closure day recorded.",
      "/payroll/vendor-closures",
      {
        closure_date:vendorClosureForm.closure_date,
        reason:vendorClosureForm.reason.trim(),
      }
    );
    if(result){
      setVendorClosureForm(freshVendorClosure());
      setShowVendorClosureForm(false);
    }
  }

  async function removeVendorClosure(closure){
    if(!window.confirm(`Remove vendor closure ${formatDisplayDate(closure.closure_date)}: ${closure.reason}?`))return;
    if(lock.current)return;
    lock.current=true;
    setBusy(true);
    setError("");
    try{
      await apiRequest(`/payroll/vendor-closures/${closure.id}`,{method:"DELETE"});
      setMessage("Vendor closure removed.");
      await load();
    }catch(error){
      setError(errText(error));
    }finally{
      lock.current=false;
      setBusy(false);
    }
  }

  async function createHold(event){
    event.preventDefault();

    if(!isMD){
      setError("Only an MD can place a salary hold.");
      return;
    }

    if(!holdForm.employee_id){
      setError("Select an employee.");
      return;
    }

    if(holdForm.hold_to&&holdForm.hold_to<holdForm.hold_from){
      setError("Hold end date cannot be earlier than hold start date.");
      return;
    }

    if(holdForm.reason.trim().length<3){
      setError("Enter a hold reason of at least 3 characters.");
      return;
    }

    const result=await runAction(
      "Salary hold created.",
      `/payroll/holds/${holdForm.employee_id}`,
      {
        hold_from:holdForm.hold_from,
        hold_to:holdForm.hold_to||null,
        reason:holdForm.reason.trim(),
      }
    );

    if(result){
      setHoldForm(freshHold());
      setShowHoldForm(false);
    }
  }

  async function releaseHold(hold){
    const employee=employeeMap[hold.employee_id];
    const note=window.prompt(
      `Release salary hold for ${employeeLabel(employee)}?\n\nRelease note (optional):`,
      ""
    );
    if(note===null)return;

    await runAction(
      "Salary hold released.",
      `/payroll/holds/${hold.id}/release`,
      {
        release_note:note.trim()||null,
      }
    );
  }

  async function createNoticePeriod(event){
    event.preventDefault();
    if(!isMD){setError("Only an MD can place an employee on notice period.");return}
    if(!noticeForm.employee_id){setError("Select an employee.");return}
    if(!noticeForm.end_date||noticeForm.end_date<noticeForm.start_date){
      setError("Notice end date must be on or after the start date.");
      return;
    }
    if(noticeForm.reason.trim().length<5){
      setError("Enter a notice-period reason of at least 5 characters.");
      return;
    }
    const result=await runAction(
      "Notice period recorded and salary hold applied automatically.",
      "/workforce-policy/notice-periods",
      {
        employee_id:noticeForm.employee_id,
        start_date:noticeForm.start_date,
        end_date:noticeForm.end_date,
        reason:noticeForm.reason.trim(),
      }
    );
    if(result){
      setNoticeForm(freshNotice());
      setShowNoticeForm(false);
    }
  }

  async function cancelNoticePeriod(notice){
    const note=window.prompt(
      `Reason for cancelling the notice period for ${notice.employee_code} — ${notice.employee_name}:`,
      ""
    );
    if(note===null)return;
    if(note.trim().length<3){setError("Enter a reason of at least 3 characters.");return}
    await runAction(
      "Notice period cancelled and its salary hold released.",
      `/workforce-policy/notice-periods/${notice.id}/cancel`,
      {note:note.trim()}
    );
  }

  function printPayslip(item){
    const popup=window.open("","_blank","width=900,height=800");

    if(!popup){
      setError("Pop-up was blocked. Allow pop-ups to print the payslip.");
      return;
    }

    const heldMessage=item.is_held
      ?`<p style="color:#b00020;font-weight:700">Salary held: ${String(item.hold_reason||"")}</p>`
      :"";

    popup.document.write(`
      <!doctype html>
      <html>
        <head>
          <meta charset="utf-8"/>
          <title>Payslip ${item.payslip_number}</title>
          <style>
            body{font-family:Arial,sans-serif;margin:40px;color:#111}
            table{width:100%;border-collapse:collapse;margin-top:24px}
            th,td{border:1px solid #bbb;padding:10px}
            .right{text-align:right}
            .meta{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:18px 0}
            @media print{button{display:none}}
          </style>
        </head>
        <body>
          <button onclick="window.print()">Print / Save as PDF</button>
          <h1>Salary Slip</h1>
          <div class="meta">
            <div><strong>Employee:</strong> ${item.employee_code} — ${item.employee_name}</div>
            <div><strong>Payslip:</strong> ${item.payslip_number}</div>
            <div><strong>Period:</strong> ${formatDisplayDate(item.period_start)} to ${formatDisplayDate(item.period_end)}</div>
            <div><strong>Currency:</strong> ${item.currency}</div>
          </div>
          <table>
            <tr><th>Description</th><th class="right">Amount (${item.currency})</th></tr>
            <tr><td>Basic earned</td><td class="right">${Number(item.basic_earned||0).toFixed(2)}</td></tr>
            <tr><td>HRA earned</td><td class="right">${Number(item.hra_earned||0).toFixed(2)}</td></tr>
            <tr><td>Conveyance</td><td class="right">${Number(item.conveyance_earned||0).toFixed(2)}</td></tr>
            <tr><td>Other allowance</td><td class="right">${Number(item.other_allowance_earned||0).toFixed(2)}</td></tr>
            <tr><td>Daily allowance</td><td class="right">${Number(item.daily_allowance_earned||0).toFixed(2)}</td></tr>
            <tr><td>Approved overtime benefit</td><td class="right">${Number(item.overtime_benefit||0).toFixed(2)}</td></tr>
            <tr><td>Fixed deduction</td><td class="right">-${Number(item.fixed_deduction||0).toFixed(2)}</td></tr>
            <tr><td>Late-attendance half-day deduction</td><td class="right">-${Number(item.other_deductions||0).toFixed(2)}</td></tr>
            <tr><td>Salary advance recovery</td><td class="right">-${Number(item.salary_advance_deduction||0).toFixed(2)}</td></tr>
            <tr><th>Net salary</th><th class="right">${Number(item.net_salary||0).toFixed(2)}</th></tr>
          </table>
          <p>Working days: ${Number(item.working_days||0).toFixed(2)}</p>
          <p>Payable days: ${Number(item.payable_days||0).toFixed(2)}</p>
          <p>Absent days: ${Number(item.absent_days||0).toFixed(2)}</p>
          ${heldMessage}
        </body>
      </html>
    `);

    popup.document.close();
  }

  const selectedEmployee=employeeMap[salaryEmployeeId];
  const pendingAdvanceCount=organizationAdvances.filter(
    row=>(isMD&&row.status==="PENDING")||(isAdmin&&row.status==="APPROVED")
  ).length;
  const advanceAmount=Number(advanceForm.requested_amount);
  const advanceInstallment=Number(advanceForm.installment_amount);
  const expectedAdvanceMonths=advanceAmount>0&&advanceInstallment>0
    ?Math.ceil(Math.round(advanceAmount*100)/Math.round(advanceInstallment*100))
    :null;

  return (
    <div className="page payroll-workspace">
      <header className="page-header">
        <div>
          <span className="eyebrow">Payroll</span>
          <h1>Salary & Payroll</h1>
          <p>
            ADMIN fixes the initial salary; MD controls revisions, notice-period
            holds and final payroll approval. Employee and vendor payroll remain
            separate within the same approved monthly run.
          </p>
        </div>

        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          onClick={load}
        >
          Refresh
        </button>
      </header>

      {error&&<div className="error-banner">{error}</div>}
      {message&&<div className="success-banner">✅ {message}</div>}

      <div className="outlet-summary-grid">
        <div>
          <small>My payslips</small>
          <strong>{payslips.length}</strong>
        </div>

        {payrollAdmin&&<>
          <div>
            <small>Payroll runs</small>
            <strong>{runs.length}</strong>
          </div>
          <div>
            <small>Pending MD approval</small>
            <strong>{pendingApprovalRuns.length}</strong>
          </div>
          <div>
            <small>Active holds</small>
            <strong>{holds.filter(row=>row.is_active).length}</strong>
          </div>
          <div>
            <small>Payroll access</small>
            <strong>{isMD?"MD Controls":"Payroll Admin"}</strong>
          </div>
        </>}
      </div>

      <section className="panel" ref={advanceRef}>
        <div className="panel-header">
          <div>
            <span className="eyebrow">Employee self-service</span>
            <h2>Salary Advance</h2>
            <p>
              Request an advance for yourself and define the monthly payroll
              deduction and recovery duration. MD approval is compulsory.
            </p>
          </div>
          <button
            type="button"
            className="primary-button"
            disabled={busy}
            onClick={()=>setShowAdvanceForm(value=>!value)}
          >
            {showAdvanceForm?"Close":"+ Request Salary Advance"}
          </button>
        </div>

        {showAdvanceForm&&(
          <form className="document-form" onSubmit={createAdvance}>
            <div className="form-grid">
              <label>
                Advance Amount *
                <input
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  disabled={busy}
                  value={advanceForm.requested_amount}
                  onChange={event=>setAdvanceForm({...advanceForm,requested_amount:event.target.value})}
                />
              </label>
              <label>
                Monthly Payroll Deduction *
                <input
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  disabled={busy}
                  value={advanceForm.installment_amount}
                  onChange={event=>setAdvanceForm({...advanceForm,installment_amount:event.target.value})}
                />
              </label>
              <label>
                Recovery Duration (Months) *
                <input
                  required
                  type="number"
                  min="1"
                  max="120"
                  step="1"
                  disabled={busy}
                  value={advanceForm.recovery_months}
                  onChange={event=>setAdvanceForm({...advanceForm,recovery_months:event.target.value})}
                />
              </label>
              <label>
                Currency *
                <input
                  required
                  minLength="3"
                  maxLength="10"
                  disabled={busy}
                  value={advanceForm.currency}
                  onChange={event=>setAdvanceForm({...advanceForm,currency:event.target.value.toUpperCase()})}
                />
              </label>
            </div>
            {expectedAdvanceMonths&&(
              <p className={Number(advanceForm.recovery_months)===expectedAdvanceMonths?"muted":"error-banner"}>
                At this monthly deduction, recovery takes {expectedAdvanceMonths} month(s).
                {Number(advanceForm.recovery_months)!==expectedAdvanceMonths&&" Enter this duration or change the deduction."}
              </p>
            )}
            <label>
              Reason *
              <textarea
                required
                minLength="5"
                maxLength="5000"
                rows="3"
                disabled={busy}
                value={advanceForm.reason}
                onChange={event=>setAdvanceForm({...advanceForm,reason:event.target.value})}
              />
            </label>
            <button className="primary-button" disabled={busy}>
              Send Request to MD
            </button>
          </form>
        )}

        <h3>My Requests</h3>
        <div className="simple-list">
          {loading?(
            <div className="skeleton-lines"/>
          ):myAdvances.length===0?(
            <div className="empty-state">You have not requested a salary advance.</div>
          ):myAdvances.map(advance=>(
            <article className="subpanel" key={advance.id}>
              <div className="panel-header">
                <div>
                  <strong>{money(advance.requested_amount,advance.currency)}</strong>
                  <p>{advance.reason}</p>
                </div>
                <Status value={advance.status}/>
              </div>
              <p>
                Deduction: {money(advance.installment_amount,advance.currency)} per payroll month
                {" · "}Duration: {advance.recovery_months} month(s)
              </p>
              <p className="muted">
                Recovered: {money(advance.recovered_amount,advance.currency)}
                {" · "}Remaining: {money(advance.remaining_amount,advance.currency)}
                {" · "}Installments: {advance.installments_completed}/{advance.recovery_months}
                {advance.recovery_start_date?` · Starts ${formatDisplayDate(advance.recovery_start_date)}`:""}
              </p>
              {advance.decision_note&&<p className="muted">MD note: {advance.decision_note}</p>}
              {advance.disbursement_reference&&<p className="muted">Payment reference: {advance.disbursement_reference}</p>}
              {advance.status==="PENDING"&&(
                <button
                  type="button"
                  className="secondary-button danger"
                  disabled={busy}
                  onClick={()=>cancelAdvance(advance)}
                >
                  Cancel Request
                </button>
              )}
            </article>
          ))}
        </div>

        {isAdvanceManager&&(
          <div>
            <div className="panel-header">
              <div>
                <span className="eyebrow">Approval & disbursement</span>
                <h3>Organization Salary Advances</h3>
                <p>MD decides pending requests; ADMIN records payment after approval.</p>
              </div>
              {pendingAdvanceCount>0&&<span className="pending-leave-badge">{pendingAdvanceCount}</span>}
            </div>
            <div className="simple-list">
              {organizationAdvances.length===0?(
                <div className="empty-state">No organization salary-advance requests.</div>
              ):organizationAdvances.map(advance=>(
                <article className="subpanel" key={`organization-${advance.id}`}>
                  <div className="panel-header">
                    <div>
                      <strong>{advance.employee_code} — {advance.employee_name}</strong>
                      <p className="muted">{advance.payee_type==="VENDOR"?"Vendor salary advance":"Employee salary advance"}</p>
                      <p>
                        {money(advance.requested_amount,advance.currency)} requested
                        {" · "}{money(advance.installment_amount,advance.currency)}/month
                        {" · "}{advance.recovery_months} month(s)
                      </p>
                    </div>
                    <Status value={advance.status}/>
                  </div>
                  <p>{advance.reason}</p>
                  <p className="muted">
                    Recovered: {money(advance.recovered_amount,advance.currency)}
                    {" · "}Remaining: {money(advance.remaining_amount,advance.currency)}
                    {advance.disbursement_reference?` · Payment: ${advance.disbursement_reference}`:""}
                  </p>
                  <div className="header-actions">
                    {isMD&&advance.status==="PENDING"&&<>
                      <button type="button" className="primary-button" disabled={busy} onClick={()=>decideAdvance(advance,true)}>Approve</button>
                      <button type="button" className="secondary-button danger" disabled={busy} onClick={()=>decideAdvance(advance,false)}>Reject</button>
                    </>}
                    {isAdmin&&advance.status==="APPROVED"&&(
                      <button type="button" className="primary-button" disabled={busy} onClick={()=>disburseAdvance(advance)}>
                        Record Disbursement
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>My Payslips</h2>
            <p>Finalized payslips available for the signed-in employee.</p>
          </div>
        </div>

        {loading?(
          <div className="skeleton-lines"/>
        ):payslips.length===0?(
          <div className="empty-state">No finalized payslips available.</div>
        ):(
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Payslip</th>
                  <th>Payable Days</th>
                  <th>Gross</th>
                  <th>Deductions</th>
                  <th>Net Salary</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>

              <tbody>
                {payslips.map(item=>(
                  <tr key={item.id}>
                    <td>{formatDisplayDate(item.period_start)} → {formatDisplayDate(item.period_end)}</td>
                    <td>{item.payslip_number}</td>
                    <td>{item.payable_days}</td>
                    <td>{money(item.gross_earned,item.currency)}</td>
                    <td>
                      {money(
                        Number(item.fixed_deduction||0)+
                        Number(item.other_deductions||0)+
                        Number(item.salary_advance_deduction||0),
                        item.currency
                      )}
                    </td>
                    <td><strong>{money(item.net_salary,item.currency)}</strong></td>
                    <td>{item.is_held?"HELD":"FINALIZED"}</td>
                    <td>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={()=>printPayslip(item)}
                      >
                        Print / Save PDF
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {payrollAdmin&&<>
        {isMD&&(
          <section className="panel" ref={approvalQueueRef}>
            <div className="panel-header">
              <div>
                <span className="eyebrow">MD Approval</span>
                <h2>Payroll Approval Queue</h2>
                <p>Review submitted payroll and approve/finalize or return it for correction.</p>
              </div>
              {pendingApprovalRuns.length>0&&<span className="pending-leave-badge">{pendingApprovalRuns.length}</span>}
            </div>
            <div className="simple-list">
              {pendingApprovalRuns.length===0?<div className="empty-state">No payroll runs are waiting for MD approval.</div>:pendingApprovalRuns.map(run=><article className="subpanel" key={run.id}>
                <div className="panel-header"><div><strong>{formatDisplayDate(run.period_start)} → {formatDisplayDate(run.period_end)}</strong><p>Employees: {run.total_employees||0} · Vendors: {run.total_vendors||0} · Net Payable: {money(run.total_net)}</p>{run.submission_note&&<p className="muted">Submission note: {run.submission_note}</p>}</div><Status value={run.status}/></div>
                <div className="header-actions"><button type="button" className="secondary-button" disabled={busy} onClick={()=>openRun(run)}>Review Payroll</button><button type="button" className="primary-button" disabled={busy} onClick={()=>approveRun(run)}>Approve & Finalize</button><button type="button" className="secondary-button danger" disabled={busy} onClick={()=>returnRun(run)}>Return for Correction</button></div>
              </article>)}
            </div>
          </section>
        )}

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Payroll Runs</h2>
              <p>Create a period, calculate employee and vendor attendance-based salary, then submit the combined payroll to MD.</p>
            </div>

            {payrollOperator&&(
              <button
                type="button"
                className="primary-button"
                disabled={busy}
                onClick={()=>setShowRunForm(value=>!value)}
              >
                {showRunForm?"Close":"+ Create Payroll Run"}
              </button>
            )}
          </div>

          {payrollOperator&&showRunForm&&(
            <form className="document-form" onSubmit={createRun}>
              <div className="form-grid">
                <label>
                  Period Start *
                  <DateField
                    required
                    type="date"
                    disabled={busy}
                    value={runForm.period_start}
                    onChange={event=>setRunForm({...runForm,period_start:event.target.value})}
                  />
                </label>

                <label>
                  Period End *
                  <DateField
                    required
                    type="date"
                    min={runForm.period_start||undefined}
                    disabled={busy}
                    value={runForm.period_end}
                    onChange={event=>setRunForm({...runForm,period_end:event.target.value})}
                  />
                </label>
              </div>

              <button className="primary-button" disabled={busy}>
                Create Payroll Run
              </button>
            </form>
          )}

          <div className="simple-list">
            {runs.length===0?(
              <div className="empty-state">No payroll runs yet.</div>
            ):runs.map(run=>(
              <article className="subpanel" key={run.id}>
                <div className="panel-header">
                  <button
                    type="button"
                    className="link-button"
                    onClick={()=>openRun(run)}
                  >
                    <strong>{formatDisplayDate(run.period_start)} → {formatDisplayDate(run.period_end)}</strong>
                  </button>

                  <Status value={run.status}/>
                </div>

                <div className="outlet-summary-grid">
                  <div><small>Employees</small><strong>{run.total_employees||0}</strong></div>
                  <div><small>Vendors</small><strong>{run.total_vendors||0}</strong></div>
                  <div><small>Combined Gross</small><strong>{money(run.total_gross)}</strong></div>
                  <div><small>Combined Deductions</small><strong>{money(run.total_deductions)}</strong></div>
                  <div><small>Combined Net</small><strong>{money(run.total_net)}</strong></div>
                </div>

                {run.status==="RETURNED"&&run.return_note&&<div className="error-banner">Returned by MD: {run.return_note}</div>}
                {runFeedback[run.id]&&<div className="error-banner">{runFeedback[run.id]}</div>}
                {!payrollPeriodEnded(run)&&["DRAFT","CALCULATED","RETURNED"].includes(run.status)&&(
                  <div className="warning-banner">
                    This payroll period has not ended yet. Calculation and submission are locked until {formatDisplayDate(run.period_end)}.
                  </div>
                )}
                {run.status==="SUBMITTED_FOR_MD_APPROVAL"&&!isMD&&<div className="success-banner">Waiting for MD approval.</div>}
                {run.status==="FINALIZED"&&run.approval_note&&<div className="success-banner">MD approval note: {run.approval_note}</div>}
                <div className="header-actions">
                  {payrollOperator&&payrollPeriodEnded(run)&&["DRAFT","CALCULATED","RETURNED"].includes(run.status)&&<button type="button" className="secondary-button" disabled={busy} onClick={()=>calculateRun(run)}>{run.status==="CALCULATED"?"Recalculate":run.status==="RETURNED"?"Recalculate After Return":"Calculate Payroll"}</button>}
                  {payrollOperator&&payrollPeriodEnded(run)&&run.status==="CALCULATED"&&<button type="button" className="primary-button" disabled={busy} onClick={()=>submitForApproval(run)}>Submit to MD for Approval</button>}
                  {payrollOperator&&canDeletePayrollRun(run)&&<button type="button" className="secondary-button danger" disabled={busy} onClick={()=>deletePayrollRun(run)}>Delete Run</button>}
                  {run.status==="SUBMITTED_FOR_MD_APPROVAL"&&isMD&&<><button type="button" className="primary-button" disabled={busy} onClick={()=>approveRun(run)}>Approve & Finalize</button><button type="button" className="secondary-button danger" disabled={busy} onClick={()=>returnRun(run)}>Return for Correction</button></>}
                  {run.status==="FINALIZED"&&<><button type="button" className="primary-button" disabled={busy} onClick={()=>downloadPayroll(run)}>Download CSV</button><button type="button" className="secondary-button" disabled={busy} onClick={()=>printPayroll(run)}>Print / Save PDF</button></>}
                  <button type="button" className="secondary-button" disabled={busy} onClick={()=>openRun(run)}>View Employee & Vendor Payroll</button>
                </div>
              </article>
            ))}
          </div>
        </section>

        {selectedRun&&(
  <section
    className="panel"
    ref={runDetailsRef}
  >
            <div className="panel-header">
              <div>
                <span className="eyebrow">Payroll Run</span>
                <h2>{formatDisplayDate(selectedRun.period_start)} → {formatDisplayDate(selectedRun.period_end)}</h2>
                <p>Employee and vendor payroll calculations for the selected run.</p>
              </div>
              <div className="header-actions">
                <Status value={selectedRun.status}/>
                {workingCalendar&&<button type="button" className="secondary-button" onClick={()=>setShowWorkingCalendar(value=>!value)}>{showWorkingCalendar?"Hide Working Dates":`View Working Dates (${workingCalendar.working_days})`}</button>}
                {payrollOperator&&canDeletePayrollRun(selectedRun)&&<button type="button" className="secondary-button danger" disabled={busy} onClick={()=>deletePayrollRun(selectedRun)}>Delete Run</button>}
                {selectedRun.status==="FINALIZED"&&<><button type="button" className="primary-button" disabled={busy} onClick={()=>downloadPayroll(selectedRun)}>Download CSV</button><button type="button" className="secondary-button" disabled={busy} onClick={()=>printPayroll(selectedRun)}>Print / Save PDF</button></>}
              </div>
            </div>

            {selectedRun.submission_note&&<div className="success-banner">Submission note: {selectedRun.submission_note}</div>}
            {selectedRun.return_note&&selectedRun.status==="RETURNED"&&<div className="error-banner">Returned for correction: {selectedRun.return_note}</div>}
            {selectedRun.approval_note&&selectedRun.status==="FINALIZED"&&<div className="success-banner">MD approval note: {selectedRun.approval_note}</div>}
            {showWorkingCalendar&&workingCalendar&&(
              <div className="subpanel">
                <div className="panel-header">
                  <div>
                    <h3>Working-day calculation</h3>
                    <p>Employees: {workingCalendar.working_days} days (Monday–Saturday). Vendors: {workingCalendar.vendor_working_days} days (including Sunday).</p>
                  </div>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Date</th><th>Day</th><th>Employee treatment</th><th>Reason</th></tr></thead>
                    <tbody>
                      {workingCalendar.calendar_days.map(day=>(
                        <tr key={day.date}>
                          <td><strong>{formatDisplayDate(day.date)}</strong></td>
                          <td>{day.weekday}</td>
                          <td><Status value={day.included?"INCLUDED":"EXCLUDED"}/></td>
                          <td>{day.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <h3>Vendor working calendar</h3>
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Date</th><th>Day</th><th>Vendor treatment</th><th>Reason</th></tr></thead>
                    <tbody>
                      {(workingCalendar.vendor_calendar_days||[]).map(day=>(
                        <tr key={`vendor-${day.date}`}>
                          <td><strong>{formatDisplayDate(day.date)}</strong></td>
                          <td>{day.weekday}</td>
                          <td><Status value={day.included?"INCLUDED":"EXCLUDED"}/></td>
                          <td>{day.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            <h3>Employee Payroll</h3>
            {runItems.length===0?(
              <div className="empty-state">
                No payroll items yet. Calculate the payroll run first.
              </div>
            ):(
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Employee</th>
                      <th>Working</th>
                      <th>Payable</th>
                      <th>Absent</th>
                      <th>Gross</th>
                      <th>Daily Allowance</th>
                      <th>OT Benefit</th>
                      <th>Fixed Deduction</th>
                      <th>Late Deduction</th>
                      <th>Advance Recovery</th>
                      <th>Net</th>
                      <th>Hold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runItems.map(item=>(
                      <tr key={item.id}>
                        <td>
                          <strong>{item.employee_code}</strong>
                          <br/>
                          <span>{item.employee_name}</span>
                          <br/>
                          <span>Bank: {item.bank_name||"—"}</span>
                          <br/>
                          <span>IFSC: {item.bank_ifsc||"—"} · A/C: {item.bank_account_number||"—"}</span>
                        </td>
                        <td>{workingCalendar?<button type="button" className="link-button" onClick={()=>setShowWorkingCalendar(true)} title="View the dates counted as working days">{item.working_days}</button>:item.working_days}</td>
                        <td>{item.payable_days}</td>
                        <td>{item.absent_days}</td>
                        <td>{money(item.gross_earned)}</td>
                        <td>{money(item.daily_allowance_earned)}</td>
                        <td>{money(item.overtime_benefit)}</td>
                        <td>{money(item.fixed_deduction)}</td>
                        <td>{money(item.other_deductions)}</td>
                        <td>{money(item.salary_advance_deduction)}</td>
                        <td><strong>{money(item.net_salary)}</strong></td>
                        <td>{item.is_held?item.hold_reason||"HELD":"—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <h3>Vendor Payroll</h3>
            <p>Vendors assigned to active shops work all days, including Sunday. Only recorded government closure dates are excluded.</p>
            {vendorItems.length===0?(
              <div className="empty-state">
                No vendor payroll items yet. Vendor salary must be effective on or before this payroll period end date; if the salary starts later, create or recalculate a later payroll run.
              </div>
            ):(
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Vendor</th><th>Shop / Outlet</th><th>Working</th><th>Payable</th><th>Absent</th><th>Gross</th><th>Daily Allowance</th><th>Fixed Deduction</th><th>Late Deduction</th><th>Advance Recovery</th><th>Net</th></tr></thead>
                  <tbody>
                    {vendorItems.map(item=>(
                      <tr key={item.id}>
                        <td><strong>{item.vendor_code}</strong><br/><span>{item.vendor_name}</span></td>
                        <td>{(item.outlet_names||[]).join(", ")||"—"}</td>
                        <td><button type="button" className="link-button" onClick={()=>setShowWorkingCalendar(true)}>{item.working_days}</button></td>
                        <td>{item.payable_days}</td>
                        <td>{item.absent_days}</td>
                        <td>{money(item.gross_earned,item.currency)}</td>
                        <td>{money(item.daily_allowance_earned,item.currency)}</td>
                        <td>{money(item.fixed_deduction,item.currency)}</td>
                        <td>{money(item.other_deductions,item.currency)}</td>
                        <td>{money(item.salary_advance_deduction,item.currency)}</td>
                        <td><strong>{money(item.net_salary,item.currency)}</strong></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Salary Structures</h2>
              <p>Gross is before deductions. Structure net is gross minus the fixed monthly deduction; final take-home is calculated in the payroll run.</p>
            </div>

            {salaryEmployeeId&&(latestStructure?isMD:isAdmin)&&(
              <button
                type="button"
                className="primary-button"
                disabled={busy}
                onClick={()=>setShowSalaryForm(value=>!value)}
              >
                {showSalaryForm
                  ?"Close"
                  :latestStructure
                    ?isMD?"+ Revise Salary":"View Structure"
                    :"+ Fix Initial Salary"}
              </button>
            )}
          </div>

          <div className="form-grid">
            <label>
              Employee *
              <select
                value={salaryEmployeeId}
                disabled={busy}
                onChange={event=>selectSalaryEmployee(event.target.value)}
              >
                <option value="">Select employee…</option>
                {sortedEmployees.map(employee=>(
                  <option key={employee.id} value={employee.id}>
                    {employeeLabel(employee)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {salaryEmployeeId&&structures.length>0&&(
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Effective From</th>
                    <th>Basic</th>
                    <th>HRA</th>
                    <th>Conveyance</th>
                    <th>Other Allowance</th>
                    <th>Daily Rate</th>
                    <th>Deduction</th>
                    <th>Gross Monthly</th>
                    <th>Net Monthly</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {structures.map(row=>(
                    <tr key={row.id}>
                      <td>{formatDisplayDate(row.effective_from)}</td>
                      <td>{money(row.basic_salary,row.currency)}</td>
                      <td>{money(row.hra,row.currency)}</td>
                      <td>{money(row.conveyance_allowance,row.currency)}</td>
                      <td>{money(row.other_allowance,row.currency)}</td>
                      <td>{money(row.daily_allowance,row.currency)} / payable day</td>
                      <td>{money(row.fixed_deduction,row.currency)}</td>
                      <td><strong>{money(row.gross_monthly_salary,row.currency)}</strong></td>
                      <td><strong>{money(
                        row.net_monthly_after_fixed_deduction
                          ??Math.max(0,Number(row.gross_monthly_salary||0)-Number(row.fixed_deduction||0)),
                        row.currency
                      )}</strong></td>
                      <td>{structureStatus(row)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {salaryEmployeeId&&structures.length===0&&(
            <div className="empty-compact">
              No salary structure exists for {employeeLabel(selectedEmployee)}.
            </div>
          )}

          {showSalaryForm&&salaryEmployeeId&&(latestStructure?isMD:isAdmin)&&(
            <form
              className="document-form"
              onSubmit={latestStructure?reviseStructure:createStructure}
            >
              <div className="form-grid">
                <label>
                  Effective From *
                  <DateField
                    required
                    type="date"
                    disabled={busy}
                    value={salaryForm.effective_from}
                    onChange={event=>setSalaryForm({...salaryForm,effective_from:event.target.value})}
                  />
                </label>

                <label>
                  Currency *
                  <input
                    required
                    maxLength="10"
                    disabled={busy}
                    value={salaryForm.currency}
                    onChange={event=>setSalaryForm({...salaryForm,currency:event.target.value.toUpperCase()})}
                  />
                </label>

                <label>
                  Basic Salary *
                  <input
                    required
                    type="number"
                    min="0"
                    step="0.01"
                    disabled={busy}
                    value={salaryForm.basic_salary}
                    onChange={event=>setSalaryForm({...salaryForm,basic_salary:event.target.value})}
                  />
                </label>

                <label>
                  HRA
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    disabled={busy}
                    value={salaryForm.hra}
                    onChange={event=>setSalaryForm({...salaryForm,hra:event.target.value})}
                  />
                </label>

                <label>
                  Conveyance Allowance
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    disabled={busy}
                    value={salaryForm.conveyance_allowance}
                    onChange={event=>setSalaryForm({...salaryForm,conveyance_allowance:event.target.value})}
                  />
                </label>

                <label>
                  Other Allowance
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    disabled={busy}
                    value={salaryForm.other_allowance}
                    onChange={event=>setSalaryForm({...salaryForm,other_allowance:event.target.value})}
                  />
                </label>

                <label>
                  Daily Allowance per Payable Day
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    disabled={busy}
                    value={salaryForm.daily_allowance}
                    onChange={event=>setSalaryForm({...salaryForm,daily_allowance:event.target.value})}
                  />
                </label>

                <label>
                  Fixed Deduction
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    disabled={busy}
                    value={salaryForm.fixed_deduction}
                    onChange={event=>setSalaryForm({...salaryForm,fixed_deduction:event.target.value})}
                  />
                </label>
              </div>

              {latestStructure&&isMD&&(
                <label>
                  Revision Reason *
                  <textarea
                    required
                    minLength="3"
                    maxLength="5000"
                    rows="3"
                    disabled={busy}
                    value={salaryForm.reason}
                    onChange={event=>setSalaryForm({...salaryForm,reason:event.target.value})}
                  />
                </label>
              )}

              {!latestStructure&&isAdmin&&(
                <button className="primary-button" disabled={busy}>
                  Fix Initial Salary
                </button>
              )}

              {latestStructure&&isMD&&(
                <button className="primary-button" disabled={busy}>
                  Revise Salary
                </button>
              )}

              {latestStructure&&!isMD&&(
                <div className="muted">
                  Only an MD can revise an existing salary structure.
                </div>
              )}
            </form>
          )}

          {salaryEmployeeId&&!latestStructure&&!isAdmin&&(
            <div className="muted">
              Only ADMIN can fix the initial salary. After it is fixed, only MD can revise it.
            </div>
          )}
        </section>

        {payrollAdmin&&<section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">Vendor payroll</span>
              <h2>Vendor Salary Setup</h2>
              <p>Vendor salary supports the same salary allowances as employees. ADMIN fixes the initial structure; only MD can revise it later.</p>
            </div>
            {salaryVendorId&&((!latestVendorStructure&&isAdmin)||(latestVendorStructure&&isMD))&&(
              <button type="button" className="primary-button" disabled={busy} onClick={()=>setShowVendorSalaryForm(value=>!value)}>
                {showVendorSalaryForm?"Close":latestVendorStructure?"+ Revise Vendor Salary":"+ Fix Initial Vendor Salary"}
              </button>
            )}
          </div>
          <div className="form-grid">
            <label>Vendor / Shop Operator *
              <select value={salaryVendorId} disabled={busy} onChange={event=>selectSalaryVendor(event.target.value)}>
                <option value="">Select vendor…</option>
                {vendors.map(vendor=>(
                  <option key={vendor.id} value={vendor.id}>{vendor.code} — {vendor.name} ({vendorOutletLabel(vendor)})</option>
                ))}
              </select>
            </label>
          </div>
          {salaryVendorId&&vendorStructures.length>0&&(
            <div className="table-wrap"><table>
              <thead><tr><th>Effective From</th><th>Basic</th><th>HRA</th><th>Conveyance</th><th>Other Allowance</th><th>Daily Rate</th><th>Gross Monthly</th><th>Fixed Deduction</th><th>Net Monthly</th><th>Revision Reason</th></tr></thead>
              <tbody>{vendorStructures.map(row=><tr key={row.id}>
                <td>{formatDisplayDate(row.effective_from)}</td>
                <td>{money(row.basic_salary,row.currency)}</td>
                <td>{money(row.hra,row.currency)}</td>
                <td>{money(row.conveyance_allowance,row.currency)}</td>
                <td>{money(row.other_allowance,row.currency)}</td>
                <td>{money(row.daily_allowance,row.currency)} / payable day</td>
                <td><strong>{money(row.gross_monthly_salary,row.currency)}</strong></td>
                <td>{money(row.fixed_deduction,row.currency)}</td>
                <td><strong>{money(row.net_monthly_salary,row.currency)}</strong></td>
                <td>{row.revision_reason||"—"}</td>
              </tr>)}</tbody>
            </table></div>
          )}
          {salaryVendorId&&vendorStructures.length===0&&<div className="empty-compact">No salary has been fixed for this vendor.</div>}
          {showVendorSalaryForm&&salaryVendorId&&((!latestVendorStructure&&isAdmin)||(latestVendorStructure&&isMD))&&(
            <form className="document-form" onSubmit={saveVendorSalary}>
              <div className="form-grid">
                <label>Effective From *<DateField required type="date" disabled={busy} value={vendorSalaryForm.effective_from} onChange={event=>setVendorSalaryForm({...vendorSalaryForm,effective_from:event.target.value})}/></label>
                <label>Basic Salary *<input required type="number" min="0" step="0.01" disabled={busy} value={vendorSalaryForm.basic_salary} onChange={event=>setVendorSalaryForm({...vendorSalaryForm,basic_salary:event.target.value})}/></label>
                <label>HRA<input type="number" min="0" step="0.01" disabled={busy} value={vendorSalaryForm.hra} onChange={event=>setVendorSalaryForm({...vendorSalaryForm,hra:event.target.value})}/></label>
                <label>Conveyance Allowance<input type="number" min="0" step="0.01" disabled={busy} value={vendorSalaryForm.conveyance_allowance} onChange={event=>setVendorSalaryForm({...vendorSalaryForm,conveyance_allowance:event.target.value})}/></label>
                <label>Other Allowance<input type="number" min="0" step="0.01" disabled={busy} value={vendorSalaryForm.other_allowance} onChange={event=>setVendorSalaryForm({...vendorSalaryForm,other_allowance:event.target.value})}/></label>
                <label>Daily Allowance per Payable Day<input type="number" min="0" step="0.01" disabled={busy} value={vendorSalaryForm.daily_allowance} onChange={event=>setVendorSalaryForm({...vendorSalaryForm,daily_allowance:event.target.value})}/></label>
                <label>Fixed Deduction<input type="number" min="0" step="0.01" disabled={busy} value={vendorSalaryForm.fixed_deduction} onChange={event=>setVendorSalaryForm({...vendorSalaryForm,fixed_deduction:event.target.value})}/></label>
                <label>Currency *<input required maxLength="10" disabled={busy} value={vendorSalaryForm.currency} onChange={event=>setVendorSalaryForm({...vendorSalaryForm,currency:event.target.value.toUpperCase()})}/></label>
              </div>
              {latestVendorStructure&&<label>Revision Reason *<textarea required minLength="3" rows="3" disabled={busy} value={vendorSalaryForm.reason} onChange={event=>setVendorSalaryForm({...vendorSalaryForm,reason:event.target.value})}/></label>}
              <button className="primary-button" disabled={busy}>{latestVendorStructure?"Revise Vendor Salary":"Fix Initial Vendor Salary"}</button>
            </form>
          )}
          {salaryVendorId&&!latestVendorStructure&&!isAdmin&&<div className="muted">Only ADMIN can fix the initial vendor salary.</div>}
          {salaryVendorId&&latestVendorStructure&&!isMD&&<div className="muted">Only MD can revise an existing vendor salary.</div>}
        </section>}

        {payrollAdmin&&<section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">Vendor calendar</span>
              <h2>Government Shop Closures</h2>
              <p>Vendors normally work every day, including Sunday. Add only officially closed dates here before calculating payroll.</p>
            </div>
            {payrollOperator&&<button type="button" className="primary-button" disabled={busy} onClick={()=>setShowVendorClosureForm(value=>!value)}>{showVendorClosureForm?"Close":"+ Add Closure"}</button>}
          </div>
          {payrollOperator&&showVendorClosureForm&&(
            <form className="document-form" onSubmit={addVendorClosure}>
              <div className="form-grid">
                <label>Closure Date *<DateField required type="date" disabled={busy} value={vendorClosureForm.closure_date} onChange={event=>setVendorClosureForm({...vendorClosureForm,closure_date:event.target.value})}/></label>
                <label>Government Order / Reason *<input required minLength="3" disabled={busy} value={vendorClosureForm.reason} onChange={event=>setVendorClosureForm({...vendorClosureForm,reason:event.target.value})}/></label>
              </div>
              <button className="primary-button" disabled={busy}>Record Closure</button>
            </form>
          )}
          {vendorClosures.length===0?<div className="empty-state">No government closure dates recorded. All calendar days count for vendor payroll.</div>:(
            <div className="table-wrap"><table>
              <thead><tr><th>Date</th><th>Reason</th><th>Action</th></tr></thead>
              <tbody>{vendorClosures.map(row=><tr key={row.id}><td><strong>{formatDisplayDate(row.closure_date)}</strong></td><td>{row.reason}</td><td>{payrollOperator?<button type="button" className="secondary-button danger" disabled={busy} onClick={()=>removeVendorClosure(row)}>Remove</button>:"—"}</td></tr>)}</tbody>
            </table></div>
          )}
        </section>}

        <section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">MD control</span>
              <h2>Employee Notice Periods</h2>
              <p>
                Creating a notice period automatically holds salary for the selected
                dates and notifies ADMIN, MD and General Manager.
              </p>
            </div>
            {isMD&&(
              <button
                type="button"
                className="primary-button"
                disabled={busy}
                onClick={()=>setShowNoticeForm(value=>!value)}
              >
                {showNoticeForm?"Close":"+ Put Employee on Notice"}
              </button>
            )}
          </div>

          {isMD&&showNoticeForm&&(
            <form className="document-form" onSubmit={createNoticePeriod}>
              <div className="form-grid">
                <label>
                  Employee *
                  <select
                    required
                    disabled={busy}
                    value={noticeForm.employee_id}
                    onChange={event=>setNoticeForm({...noticeForm,employee_id:event.target.value})}
                  >
                    <option value="">Select employee…</option>
                    {sortedEmployees.map(employee=>(
                      <option key={employee.id} value={employee.id}>
                        {employeeLabel(employee)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Notice Starts *
                  <DateField
                    required
                    type="date"
                    disabled={busy}
                    value={noticeForm.start_date}
                    onChange={event=>setNoticeForm({...noticeForm,start_date:event.target.value})}
                  />
                </label>
                <label>
                  Notice Ends *
                  <DateField
                    required
                    type="date"
                    min={noticeForm.start_date||undefined}
                    disabled={busy}
                    value={noticeForm.end_date}
                    onChange={event=>setNoticeForm({...noticeForm,end_date:event.target.value})}
                  />
                </label>
              </div>
              <label>
                Reason *
                <textarea
                  required
                  minLength="5"
                  maxLength="5000"
                  rows="3"
                  disabled={busy}
                  value={noticeForm.reason}
                  onChange={event=>setNoticeForm({...noticeForm,reason:event.target.value})}
                />
              </label>
              <button className="primary-button" disabled={busy}>
                Confirm Notice Period & Salary Hold
              </button>
            </form>
          )}

          <div className="simple-list">
            {noticePeriods.length===0?(
              <div className="empty-state">No notice periods recorded.</div>
            ):noticePeriods.map(notice=>(
              <article className="subpanel" key={notice.id}>
                <div className="panel-header">
                  <div>
                    <strong>{notice.employee_code} — {notice.employee_name}</strong>
                    <p>{formatDisplayDate(notice.start_date)} → {formatDisplayDate(notice.end_date)}</p>
                  </div>
                  <Status value={notice.status}/>
                </div>
                <p>{notice.reason}</p>
                <p className="muted">
                  Salary hold: {notice.salary_hold_active?"ACTIVE":"RELEASED"}
                  {notice.end_note?` · ${notice.end_note}`:""}
                </p>
                {isMD&&notice.status==="ACTIVE"&&(
                  <button
                    type="button"
                    className="secondary-button danger"
                    disabled={busy}
                    onClick={()=>cancelNoticePeriod(notice)}
                  >
                    Cancel Notice & Release Hold
                  </button>
                )}
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Salary Holds</h2>
              <p>Salary hold and release are MD-only actions enforced by the backend.</p>
            </div>

            <div className="header-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={()=>setShowReleasedHolds(value=>!value)}
              >
                {showReleasedHolds?"Show Active Only":"Show Hold History"}
              </button>

              {isMD&&(
                <button
                  type="button"
                  className="primary-button"
                  disabled={busy}
                  onClick={()=>setShowHoldForm(value=>!value)}
                >
                  {showHoldForm?"Close":"+ Hold Salary"}
                </button>
              )}
            </div>
          </div>

          {isMD&&showHoldForm&&(
            <form className="document-form" onSubmit={createHold}>
              <div className="form-grid">
                <label>
                  Employee *
                  <select
                    required
                    disabled={busy}
                    value={holdForm.employee_id}
                    onChange={event=>setHoldForm({...holdForm,employee_id:event.target.value})}
                  >
                    <option value="">Select employee…</option>
                    {sortedEmployees.map(employee=>(
                      <option key={employee.id} value={employee.id}>
                        {employeeLabel(employee)}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Hold From *
                  <DateField
                    required
                    type="date"
                    disabled={busy}
                    value={holdForm.hold_from}
                    onChange={event=>setHoldForm({...holdForm,hold_from:event.target.value})}
                  />
                </label>

                <label>
                  Hold To
                  <DateField
                    type="date"
                    min={holdForm.hold_from||undefined}
                    disabled={busy}
                    value={holdForm.hold_to}
                    onChange={event=>setHoldForm({...holdForm,hold_to:event.target.value})}
                  />
                </label>
              </div>

              <label>
                Hold Reason *
                <textarea
                  required
                  minLength="3"
                  maxLength="5000"
                  rows="3"
                  disabled={busy}
                  value={holdForm.reason}
                  onChange={event=>setHoldForm({...holdForm,reason:event.target.value})}
                />
              </label>

              <button className="primary-button" disabled={busy}>
                Hold Salary
              </button>
            </form>
          )}

          <div className="simple-list">
            {holds.length===0?(
              <div className="empty-state">
                {showReleasedHolds?"No salary holds found.":"No active salary holds."}
              </div>
            ):holds.map(hold=>{
              const employee=employeeMap[hold.employee_id];
              return (
                <article className="subpanel" key={hold.id}>
                  <div className="panel-header">
                    <div>
                      <strong>{employeeLabel(employee)}</strong>
                      <p>
                        {hold.hold_from}
                        {" → "}
                        {hold.hold_to||"Until released"}
                      </p>
                    </div>

                    <Status value={hold.is_active?"ACTIVE":"RELEASED"}/>
                  </div>

                  <p>{hold.reason}</p>

                  {!hold.is_active&&hold.release_note&&(
                    <p className="muted">
                      Release note: {hold.release_note}
                    </p>
                  )}

                  {isMD&&hold.is_active&&(
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={busy}
                      onClick={()=>releaseHold(hold)}
                    >
                      Release Hold
                    </button>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      </>}
    </div>
  );
}
// date-display-ddmmyyyy-v1
