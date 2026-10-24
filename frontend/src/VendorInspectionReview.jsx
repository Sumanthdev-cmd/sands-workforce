import {displayDate as formatDisplayDate,dateOptions} from "./lib/displayDates";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiRequest } from "./lib/api";
import SignaturePad from "./SignaturePad";

function answerText(question, answers) {
  const answer = answers?.[question.id];
  if (!answer) return "—";
  if (question.type === "CONDITIONAL_TEXT") return answer.text || "—";
  const value = answer.value;
  if (value === "YES") return question.yes_label || "Yes";
  if (value === "NO") return question.no_label || "No";
  return "—";
}

export default function VendorInspectionReview() {
  const { token } = useParams();
  const [report, setReport] = useState(null);
  const [response, setResponse] = useState("ACCEPT");
  const [vendorName, setVendorName] = useState("");
  const [remarks, setRemarks] = useState("");
  const [signature, setSignature] = useState(null);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function load() {
    try {
      const data = await apiRequest(`/inspections/public/vendor/${token}`);
      setReport(data);
      setVendorName((old) => old || data.vendor_name || "");
      if (data.vendor_response) setDone(true);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => { load(); }, [token]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      const data = await apiRequest(`/inspections/public/vendor/${token}/respond`, {
        method: "POST",
        body: {
          response,
          vendor_name: vendorName,
          remarks: remarks || null,
          signature_data_uri: signature,
        },
      });
      setReport(data);
      setDone(true);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setError(err.message);
    }
  }

  if (error && !report) return <div className="vendor-public-page"><div className="vendor-public-card"><div className="error-banner">{error}</div></div></div>;
  if (!report) return <div className="center-page"><div className="spinner"/><p>Loading inspection report…</p></div>;

  return (
    <div className="vendor-public-page">
      <div className="vendor-public-card">
        <header className="vendor-report-header">
          <div>
            <span className="eyebrow">Vendor review</span>
            <h1>CHECKING LIST</h1>
            <p>{report.outlet_name}</p>
          </div>
          <div>
            <strong>{report.report_number}</strong>
            <span>{new Date(report.inspection_started_at).toLocaleString("en-GB",dateOptions({},true))}</span>
          </div>
        </header>

        <div className="inspection-meta">
          <span><strong>Inspector:</strong> {report.inspector_name}</span>
          <span><strong>Cluster:</strong> {report.cluster_name || "—"}</span>
          <span><strong>Address:</strong> {report.outlet_address}</span>
        </div>

        {done && (
          <div className="success-banner">
            Your response has been recorded: <strong>{report.vendor_response}</strong>. Signature was {report.vendor_signature_data_uri ? "provided" : "not provided (optional)"}.
          </div>
        )}

        {report.template_snapshot.sections.map((section) => (
          <section className="inspection-section" key={section.id}>
            <h3>{section.number}. {section.title}</h3>
            {section.questions.map((question) => {
              const answer = report.answers?.[question.id];
              const parent = question.depends_on ? report.answers?.[question.depends_on]?.value : null;
              if (question.type === "CONDITIONAL_TEXT" && parent !== question.depends_value) return null;
              return (
                <div className="inspection-question read-only" key={question.id}>
                  <div className="inspection-question-row">
                    <strong>{question.label}</strong>
                    <span className="answer-pill">{answerText(question, report.answers)}</span>
                  </div>
                  {answer?.details && <p>{answer.details}</p>}
                </div>
              );
            })}
            <div className="section-remarks read-only"><strong>Remarks</strong><p>{report.section_remarks?.[section.id] || "—"}</p></div>
          </section>
        ))}

        {report.inspector_signature_data_uri ? (
          <div className="signature-preview"><strong>Inspector signature</strong><img src={report.inspector_signature_data_uri} alt="Inspector signature"/></div>
        ) : (
          <p className="muted">Inspector digital signature: Not provided (optional)</p>
        )}

        {!done && (
          <form className="vendor-response-form" onSubmit={submit}>
            <h2>Vendor response</h2>
            <p>Please review the inspection above. Digital signature is optional.</p>
            {error && <div className="error-banner">{error}</div>}

            <div className="vendor-response-options">
              <label><input type="radio" name="vendor-response" checked={response==="ACCEPT"} onChange={()=>setResponse("ACCEPT")}/> Accept report</label>
              <label><input type="radio" name="vendor-response" checked={response==="DISPUTE"} onChange={()=>setResponse("DISPUTE")}/> Dispute report</label>
            </div>

            <label>Vendor name<input required value={vendorName} onChange={(e)=>setVendorName(e.target.value)}/></label>
            <label>Remarks {response==="DISPUTE" ? "*" : "(optional)"}
              <textarea required={response==="DISPUTE"} rows="4" value={remarks} onChange={(e)=>setRemarks(e.target.value)}/>
            </label>

            <SignaturePad
              value={signature}
              onChange={setSignature}
              label="Vendor signature (optional)"
            />

            <div className="inspection-footer-actions">
              <button type="button" className="secondary-button" onClick={()=>window.print()}>Print report</button>
              <button className="primary-button" type="submit">Submit vendor response</button>
            </div>
          </form>
        )}

        {done && <button className="secondary-button" onClick={()=>window.print()}>Print report</button>}
      </div>
    </div>
  );
}
// date-display-ddmmyyyy-v1
