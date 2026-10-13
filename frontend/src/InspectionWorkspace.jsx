import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "./lib/api";
import { useAuth } from "./context/AuthContext";
import SignaturePad from "./SignaturePad";
import {pushCurrentEmployeeLocation} from "./lib/location";

const MANAGEMENT = ["ADMIN", "MD", "GM", "MANAGER"];

function AnswerField({ question, answers, setAnswers }) {
  const current = answers[question.id] || {};
  if (question.type === "CONDITIONAL_TEXT") {
    const parent = answers[question.depends_on]?.value;
    if (parent !== question.depends_value) return null;
    return (
      <div className="inspection-question conditional">
        <strong>{question.label}</strong>
        <textarea
          rows="3"
          value={current.text || ""}
          onChange={(event) => setAnswers((old) => ({
            ...old,
            [question.id]: { text: event.target.value },
          }))}
        />
      </div>
    );
  }

  const showDetails =
    question.detail_when === "ALWAYS" ||
    question.detail_when === current.value;

  return (
    <div className="inspection-question">
      <div className="inspection-question-row">
        <strong>{question.label}</strong>
        <div className="yes-no-radios">
          <label>
            <input
              type="radio"
              name={question.id}
              checked={current.value === "YES"}
              onChange={() => setAnswers((old) => ({
                ...old,
                [question.id]: { ...old[question.id], value: "YES" },
              }))}
            />
            {question.yes_label || "Yes"}
          </label>
          <label>
            <input
              type="radio"
              name={question.id}
              checked={current.value === "NO"}
              onChange={() => setAnswers((old) => ({
                ...old,
                [question.id]: { ...old[question.id], value: "NO" },
              }))}
            />
            {question.no_label || "No"}
          </label>
        </div>
      </div>

      {showDetails && question.detail_label && (
        <textarea
          rows="2"
          placeholder={question.detail_label}
          value={current.details || ""}
          onChange={(event) => setAnswers((old) => ({
            ...old,
            [question.id]: {
              ...old[question.id],
              details: event.target.value,
            },
          }))}
        />
      )}
    </div>
  );
}

function ChecklistEditor({ report, onReload, onSubmitted }) {
  const [answers, setAnswers] = useState(report.answers || {});
  const [remarks, setRemarks] = useState(report.section_remarks || {});
  const [signature, setSignature] = useState(report.inspector_signature_data_uri || null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const editable = report.status === "DRAFT";

  useEffect(() => {
    setAnswers(report.answers || {});
    setRemarks(report.section_remarks || {});
    setSignature(report.inspector_signature_data_uri || null);
  }, [report.id]);

  async function save() {
    setMessage("");
    setError("");
    try {
      await apiRequest(`/inspections/${report.id}/draft`, {
        method: "PATCH",
        body: { answers, section_remarks: remarks },
      });
      setMessage("Draft saved.");
      onReload();
    } catch (err) {
      setError(err.message);
    }
  }

  async function submit() {
    setMessage("");
    setError("");
    try {
      const result = await apiRequest(`/inspections/${report.id}/submit`, {
        method: "POST",
        body: {
          answers,
          section_remarks: remarks,
          inspector_signature_data_uri: signature,
        },
      });
      setMessage("Inspection submitted. Vendor review is now pending.");
      onSubmitted(result);
    } catch (err) {
      const detail = err.data?.detail;
      if (detail?.missing_question_ids || detail?.missing_detail_question_ids) {
        setError(
          `Checklist incomplete. Missing answers: ${(detail.missing_question_ids || []).join(", ")}. Missing details: ${(detail.missing_detail_question_ids || []).join(", ")}`
        );
      } else {
        setError(err.message);
      }
    }
  }

  return (
    <div className="inspection-report-paper">
      <div className="inspection-report-title">
        <h2>CHECKING LIST</h2>
        <div>
          <strong>{report.report_number}</strong>
          <span>Status: {report.status.replaceAll("_", " ")}</span>
        </div>
      </div>

      <div className="inspection-meta">
        <span><strong>Shop / Outlet:</strong> {report.outlet_name || "—"}{report.outlet_code ? ` (${report.outlet_code})` : ""}</span>
        <span><strong>Address:</strong> {report.outlet_address || "—"}</span>
        <span><strong>Cluster:</strong> {report.cluster_name || "—"}</span>
        <span><strong>Inspection:</strong> {new Date(report.inspection_started_at).toLocaleString()}</span>
        <span><strong>Version:</strong> {report.version}</span>
      </div>

      {error && <div className="error-banner">{error}</div>}
      {message && <div className="success-banner">{message}</div>}

      {report.template_snapshot.sections.map((section) => (
        <section className="inspection-section" key={section.id}>
          <h3>{section.number}. {section.title}</h3>
          {section.questions.map((question) => (
            editable ? (
              <AnswerField
                key={question.id}
                question={question}
                answers={answers}
                setAnswers={setAnswers}
              />
            ) : (
              <div className="inspection-question read-only" key={question.id}>
                <div className="inspection-question-row">
                  <strong>{question.label}</strong>
                  <span className="answer-pill">
                    {answers[question.id]?.value || answers[question.id]?.text || "—"}
                  </span>
                </div>
                {answers[question.id]?.details && <p>{answers[question.id].details}</p>}
              </div>
            )
          ))}

          <label className="section-remarks">
            Remarks
            <textarea
              rows="3"
              disabled={!editable}
              value={remarks[section.id] || ""}
              onChange={(event) => setRemarks((old) => ({
                ...old,
                [section.id]: event.target.value,
              }))}
            />
          </label>
        </section>
      ))}

      {editable && (
        <SignaturePad
          value={signature}
          onChange={setSignature}
          label="Inspector signature (optional)"
        />
      )}

      {!editable && report.inspector_signature_data_uri && (
        <div className="signature-preview">
          <strong>Inspector signature</strong>
          <img src={report.inspector_signature_data_uri} alt="Inspector signature" />
        </div>
      )}

      <div className="inspection-footer-actions">
        <button type="button" className="secondary-button" onClick={() => window.print()}>Print report</button>
        {editable && <button type="button" className="secondary-button" onClick={save}>Save draft</button>}
        {editable && <button type="button" className="primary-button" onClick={submit}>Submit to vendor</button>}
      </div>
    </div>
  );
}

function inspectionError(error) {
  const value = error?.data?.detail ?? error?.detail ?? error?.message ?? error;

  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => item?.msg || "Invalid information.").join(" ");
  if (value && typeof value === "object") {
    if (typeof value.message === "string") return value.message;
    if (typeof value.detail === "string") return value.detail;
  }

  return "The request could not be completed.";
}

function localDateInput() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function visitStatusLabel(value) {
  return String(value || "—").replaceAll("_", " ");
}

function visitorLabel(item) {
  const employeeCode = item?.employee_code || "Visitor";
  const employeeName =
    item?.employee_name ||
    item?.full_name ||
    [item?.first_name, item?.last_name].filter(Boolean).join(" ").trim();

  return `${employeeCode}${employeeName ? ` — ${employeeName}` : ""}`;
}

export default function InspectionWorkspace() {
  const { roles = [] } = useAuth();

  const management = roles.some((role) => MANAGEMENT.includes(role));
  const fieldVisitor = roles.includes("FIELD_VISITOR") && !management;
  const isGM = roles.includes("GM");

  const [reports, setReports] = useState([]);
  const [visits, setVisits] = useState([]);
  const [lateRequests, setLateRequests] = useState([]);
  const [outlets, setOutlets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [vendorLink, setVendorLink] = useState("");
  const [notificationStatus, setNotificationStatus] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);

  const [rotationForm, setRotationForm] = useState({
    outlet_id: "",
    scheduled_for: localDateInput(),
  });

  const [preview, setPreview] = useState(null);
  const [manualVisitorId, setManualVisitorId] = useState("");
  const [manualReason, setManualReason] = useState("");

  const focusVisitId = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("visit_assignment") || "";
  }, []);

  async function loadReports() {
    try {
      const data = await apiRequest(
        `/inspections${management ? "" : "?mine=true"}`
      );
      setReports(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(inspectionError(err));
    }
  }

  async function loadVisits() {
    try {
      const data = await apiRequest("/inspections/visit-assignments");
      setVisits(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(inspectionError(err));
    }
  }

  async function loadOutlets() {
    if (!management) return;

    try {
      const data = await apiRequest("/outlets/inspection-options");
      setOutlets(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(inspectionError(err));
    }
  }

  async function loadLateRequests() {
    if (!management && !fieldVisitor) return;
    try {
      const data = await apiRequest(
        "/workforce-policy/inspection-late-starts"
      );
      setLateRequests(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(inspectionError(err));
    }
  }

  async function reloadAll() {
    setError("");
    await Promise.all([
      loadReports(),
      loadVisits(),
      loadOutlets(),
      loadLateRequests(),
    ]);
  }

  useEffect(() => {
    reloadAll();
  }, []);

  async function openReport(id) {
    setError("");

    try {
      const data = await apiRequest(`/inspections/${id}`);
      setSelected(data);
      setVendorLink("");
      setNotificationStatus("");
    } catch (err) {
      setError(inspectionError(err));
    }
  }

  async function startAssignedVisit(visit) {
    if (busy) return;

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await pushCurrentEmployeeLocation();
      const created = await apiRequest("/inspections", {
        method: "POST",
        body: {
          outlet_id: visit.outlet_id,
          visit_assignment_id: visit.id,
          vendor_id: null,
          task_assignment_id: null,
          cluster_name: null,
        },
      });

      setSelected(created);
      setSuccess(
        `Inspection started for ${visit.outlet_name}.`
      );

      await Promise.all([
        loadReports(),
        loadVisits(),
      ]);

      window.dispatchEvent(
        new Event("action-alerts:refresh")
      );
    } catch (err) {
      const detail = err?.data?.detail;
      if (detail?.code === "INSPECTION_LATE_START_PERMISSION_REQUIRED") {
        const reason = window.prompt(
          `${detail.message}\n\nReason for starting after 09:30:`,
          ""
        );
        if (reason === null) {
          setError(detail.message);
        } else if (reason.trim().length < 5) {
          setError("Enter a clear late-start reason of at least 5 characters.");
        } else {
          try {
            await apiRequest(
              "/workforce-policy/inspection-late-starts",
              {
                method: "POST",
                body: {
                  visit_assignment_id: visit.id,
                  reason: reason.trim(),
                },
              }
            );
            setSuccess(
              "Late-start request sent to GM. Start the inspection after approval."
            );
            await loadLateRequests();
            window.dispatchEvent(
              new Event("action-alerts:refresh")
            );
          } catch (requestError) {
            setError(inspectionError(requestError));
          }
        }
      } else {
        setError(inspectionError(err));
      }
    } finally {
      setBusy(false);
    }
  }

  async function decideLateStart(request, approved) {
    const note = window.prompt(
      approved
        ? "GM approval note (optional):"
        : "Reason for rejecting the late inspection start:",
      ""
    );
    if (note === null) return;
    if (!approved && note.trim().length < 3) {
      setError("Enter a rejection reason of at least 3 characters.");
      return;
    }
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await apiRequest(
        `/workforce-policy/inspection-late-starts/${request.id}/decision`,
        {
          method: "POST",
          body: {
            approved,
            note: note.trim() || null,
          },
        }
      );
      setSuccess(
        `Late inspection start ${approved ? "approved" : "rejected"}.`
      );
      await loadLateRequests();
      window.dispatchEvent(
        new Event("action-alerts:refresh")
      );
    } catch (err) {
      setError(inspectionError(err));
    } finally {
      setBusy(false);
    }
  }

  async function previewRotation() {
    if (!rotationForm.outlet_id || !rotationForm.scheduled_for) {
      setError("Select an outlet and inspection date.");
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      const params = new URLSearchParams({
        outlet_id: rotationForm.outlet_id,
        scheduled_for: rotationForm.scheduled_for,
      });

      const data = await apiRequest(
        `/inspections/rotation/preview?${params.toString()}`
      );

      setPreview(data || null);
      setManualVisitorId("");
      setManualReason("");
    } catch (err) {
      setPreview(null);
      setError(inspectionError(err));
    } finally {
      setBusy(false);
    }
  }

  async function autoAssign() {
    if (!rotationForm.outlet_id || !rotationForm.scheduled_for) {
      setError("Select an outlet and inspection date.");
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      const result = await apiRequest("/inspections/rotation/assign", {
        method: "POST",
        body: {
          outlet_id: rotationForm.outlet_id,
          scheduled_for: rotationForm.scheduled_for,
        },
      });

      setSuccess(
        `${result.outlet_name} assigned to ${result.employee_code} — ${result.employee_name}.`
      );

      setPreview(null);
      setManualVisitorId("");
      setManualReason("");

      await loadVisits();

      window.dispatchEvent(
        new Event("action-alerts:refresh")
      );
    } catch (err) {
      setError(inspectionError(err));

      try {
        await previewRotation();
      } catch {
        // Keep the original error.
      }
    } finally {
      setBusy(false);
    }
  }

  async function manualOverride() {
    if (!manualVisitorId) {
      setError("Select a field visitor for Manual Override.");
      return;
    }

    if ((manualReason || "").trim().length < 5) {
      setError("Enter a clear Manual Override reason.");
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      const result = await apiRequest(
        "/inspections/rotation/manual-override",
        {
          method: "POST",
          body: {
            outlet_id: rotationForm.outlet_id,
            scheduled_for: rotationForm.scheduled_for,
            employee_id: manualVisitorId,
            reason: manualReason.trim(),
          },
        }
      );

      const ruleText = result.rotation_rule_overridden
        ? " The last-3 rotation rule was overridden and the reason was recorded."
        : "";

      setSuccess(
        `${result.outlet_name} manually assigned to ${result.employee_code} — ${result.employee_name}.${ruleText}`
      );

      setPreview(null);
      setManualVisitorId("");
      setManualReason("");

      await loadVisits();

      window.dispatchEvent(
        new Event("action-alerts:refresh")
      );
    } catch (err) {
      setError(inspectionError(err));
    } finally {
      setBusy(false);
    }
  }

  async function cancelVisit(visit) {
    const reason = window.prompt(
      `Reason for cancelling ${visit.outlet_name} inspection:`,
      ""
    );

    if (reason === null) return;

    if (reason.trim().length < 5) {
      setError("Cancellation reason must contain at least 5 characters.");
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        `/inspections/visit-assignments/${visit.id}/cancel`,
        {
          method: "POST",
          body: { reason: reason.trim() },
        }
      );

      setSuccess(
        `${visit.outlet_name} inspection assignment cancelled.`
      );

      await loadVisits();

      window.dispatchEvent(
        new Event("action-alerts:refresh")
      );
    } catch (err) {
      setError(inspectionError(err));
    } finally {
      setBusy(false);
    }
  }

  async function reloadSelected() {
    if (selected) await openReport(selected.id);
    await Promise.all([
      loadReports(),
      loadVisits(),
    ]);
  }

  async function acknowledge(report) {
    const note =
      window.prompt(
        "HO acknowledgement note (optional):",
        ""
      ) ?? null;

    try {
      const data = await apiRequest(
        `/inspections/${report.id}/ho-acknowledge`,
        {
          method: "POST",
          body: { note },
        }
      );

      setSelected(data);
      await loadReports();
    } catch (err) {
      setError(inspectionError(err));
    }
  }

  async function closeReport(report) {
    try {
      const data = await apiRequest(
        `/inspections/${report.id}/close`,
        { method: "POST" }
      );

      setSelected(data);

      await Promise.all([
        loadReports(),
        loadVisits(),
      ]);
    } catch (err) {
      setError(inspectionError(err));
    }
  }

  async function regenerate(report) {
    try {
      const data = await apiRequest(
        `/inspections/${report.id}/vendor-link`,
        { method: "POST" }
      );

      setVendorLink(data.vendor_review_url);
      setNotificationStatus(
        data.vendor_notification_status
      );
    } catch (err) {
      setError(inspectionError(err));
    }
  }

  const activeFieldVisits = visits.filter((visit) =>
    ["ASSIGNED", "STARTED"].includes(
      String(visit.status || "").toUpperCase()
    )
  );
  const pendingLateRequests = lateRequests.filter(
    (request) => request.status === "PENDING"
  );

  const today = localDateInput();

  return (
    <div className="page inspection-workspace">
      <header className="page-header">
        <div>
          <span className="eyebrow">Field visits</span>
          <h1>Shop Inspections</h1>
          <p>
            Rotating field-visitor assignments, official 8-section checking list,
            vendor acceptance and HO acknowledgement.
          </p>
        </div>

        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          onClick={reloadAll}
        >
          Refresh
        </button>
      </header>

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}

      {success && (
        <div className="success-banner">
          {success}
        </div>
      )}

      {isGM && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">09:30 cutoff</span>
              <h2>Late inspection start approvals</h2>
              <p>
                A field visitor cannot begin a shop inspection after 09:30
                without GM approval and a recorded reason. MD is notified
                when the request is raised and when it is decided.
              </p>
            </div>
            <span className="pending-leave-badge">
              {pendingLateRequests.length}
            </span>
          </div>

          <div className="simple-list">
            {pendingLateRequests.length === 0 ? (
              <div className="empty-state">
                No late inspection starts are waiting for approval.
              </div>
            ) : (
              pendingLateRequests.map((request) => (
                <article className="subpanel" key={request.id}>
                  <div className="panel-header">
                    <div>
                      <strong>
                        {request.outlet_name} ({request.outlet_code})
                      </strong>
                      <p>
                        {request.employee_code} — {request.employee_name}
                        {" · "}
                        {request.scheduled_for}
                      </p>
                    </div>
                    <span className="inspection-status">
                      PENDING
                    </span>
                  </div>
                  <p>{request.reason}</p>
                  <div className="action-strip">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={busy}
                      onClick={() => decideLateStart(request, true)}
                    >
                      Approve Late Start
                    </button>
                    <button
                      type="button"
                      className="secondary-button danger"
                      disabled={busy}
                      onClick={() => decideLateStart(request, false)}
                    >
                      Reject
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      )}

      {management && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">Strict rotation</span>
              <h2>Schedule next inspection</h2>
              <p>
                A field visitor who inspected this outlet is blocked for the
                next 3 inspections. Auto Rotation also allows only one shop
                inspection per field visitor per day. Approved leave is excluded.
              </p>
            </div>
          </div>

          <div className="form-grid">
            <label>
              Shop / Outlet
              <select
                value={rotationForm.outlet_id}
                disabled={busy}
                onChange={(event) => {
                  setRotationForm((old) => ({
                    ...old,
                    outlet_id: event.target.value,
                  }));
                  setPreview(null);
                  setManualVisitorId("");
                  setManualReason("");
                }}
              >
                <option value="">
                  Select outlet…
                </option>

                {outlets.map((item) => (
                  <option
                    key={item.id}
                    value={item.id}
                  >
                    {item.name} ({item.code})
                  </option>
                ))}
              </select>
            </label>

            <label>
              Inspection date
              <input
                type="date"
                min={today}
                value={rotationForm.scheduled_for}
                disabled={busy}
                onChange={(event) => {
                  setRotationForm((old) => ({
                    ...old,
                    scheduled_for: event.target.value,
                  }));
                  setPreview(null);
                  setManualVisitorId("");
                  setManualReason("");
                }}
              />
            </label>
          </div>

          <div className="action-strip">
            <button
              type="button"
              className="secondary-button"
              disabled={
                busy ||
                !rotationForm.outlet_id ||
                !rotationForm.scheduled_for
              }
              onClick={previewRotation}
            >
              Check rotation
            </button>

            <button
              type="button"
              className="primary-button"
              disabled={
                busy ||
                !rotationForm.outlet_id ||
                !rotationForm.scheduled_for
              }
              onClick={autoAssign}
            >
              Auto Assign
            </button>
          </div>

          {preview && (
            <div className="outlet-related-grid">
              <article className="subpanel">
                <h3>Last 3 inspectors — excluded</h3>

                {(preview.recent_three || []).length === 0 ? (
                  <div className="empty-compact">
                    No previous inspections. No recent-visitor exclusions.
                  </div>
                ) : (
                  <div className="simple-list">
                    {(preview.recent_three || []).map((item, index) => (
                      <div
                        className="simple-row"
                        key={item.report_id || `${item.employee_id}-${index}`}
                      >
                        <div>
                          <strong>
                            {visitorLabel(item)}
                          </strong>
                          <span>
                            {item.report_number || "Previous inspection"}
                          </span>
                        </div>
                        <span>
                          Excluded
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </article>

              <article className="subpanel">
                <h3>Eligible for Auto Assignment</h3>

                {(preview.eligible_visitors || []).length === 0 ? (
                  <div className="error-banner">
                    No visitor currently satisfies all automatic rotation rules.
                  </div>
                ) : (
                  <div className="simple-list">
                    {(preview.eligible_visitors || []).map((item) => (
                      <div
                        className="simple-row"
                        key={item.employee_id}
                      >
                        <div>
                          <strong>
                            {visitorLabel(item)}
                          </strong>
                          <span>
                            Daily shop inspections: {item.workload || 0}
                          </span>
                        </div>
                        <span>
                          Eligible
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </article>

              <article className="subpanel">
                <h3>Unavailable visitors</h3>

                {(preview.all_visitors || []).filter(
                  (item) => !item.eligible
                ).length === 0 ? (
                  <div className="empty-compact">
                    No unavailable visitors.
                  </div>
                ) : (
                  <div className="simple-list">
                    {(preview.all_visitors || [])
                      .filter((item) => !item.eligible)
                      .map((item) => (
                        <div
                          className="simple-row"
                          key={item.employee_id}
                        >
                          <div>
                            <strong>
                              {visitorLabel(item)}
                            </strong>
                            <span>
                              {(item.reasons || [])
                                .map((reason) =>
                                  String(reason)
                                    .replace("INSPECTED_WITHIN_LAST_3", "Last 3 inspections")
                                    .replace("ON_LEAVE:", "Leave: ")
                                    .replace("DAILY_LIMIT:", "Already allotted today: ")
                                    .replace("VISIT_CONFLICT:", "Visit conflict: ")
                                )
                                .join(" · ")}
                            </span>
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </article>
            </div>
          )}

          {preview && (
            <section className="subpanel">
              <div className="panel-header">
                <div>
                  <h3>Manual Override</h3>
                  <p className="muted">
                    Use only when operationally unavoidable. It may override
                    the last-3 rule and the one-inspection-per-day limit.
                    Approved leave can never be overridden. The reason is
                    permanently recorded.
                  </p>
                </div>
              </div>

              <div className="form-grid">
                <label>
                  Field Visitor
                  <select
                    value={manualVisitorId}
                    disabled={busy}
                    onChange={(event) =>
                      setManualVisitorId(event.target.value)
                    }
                  >
                    <option value="">
                      Select visitor…
                    </option>

                    {(preview.manual_override_options || []).map((item) => (
                      <option
                        key={item.employee_id}
                        value={item.employee_id}
                      >
                        {visitorLabel(item)}
                        {item.recent_excluded ? " — LAST-3 OVERRIDE" : ""}
                        {item.has_daily_assignment ? " — ONE-DAY LIMIT OVERRIDE" : ""}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Override reason *
                  <textarea
                    rows="3"
                    value={manualReason}
                    disabled={busy}
                    placeholder="Example: emergency inspection required after the visitor completed the earlier shop visit; no other field visitor is available."
                    onChange={(event) =>
                      setManualReason(event.target.value)
                    }
                  />
                </label>
              </div>

              <button
                type="button"
                className="secondary-button"
                disabled={
                  busy ||
                  !manualVisitorId ||
                  manualReason.trim().length < 5
                }
                onClick={manualOverride}
              >
                Confirm Manual Override
              </button>
            </section>
          )}
        </section>
      )}

      {management && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Inspection visit assignments</h2>
              <p>
                Every visit is individually assigned and audit-tracked.
              </p>
            </div>
          </div>

          <div className="simple-list">
            {visits.length === 0 ? (
              <div className="empty-state">
                No rotating inspection assignments yet.
              </div>
            ) : (
              visits.slice(0, 50).map((visit) => (
                <div
                  className="simple-row"
                  key={visit.id}
                >
                  <div>
                    <strong>
                      {visit.outlet_name} ({visit.outlet_code})
                    </strong>
                    <span>
                      {visit.scheduled_for} · {visitorLabel(visit)}
                    </span>
                    <span>
                      {visit.assignment_method === "MANUAL_OVERRIDE"
                        ? `Manual Override · ${visit.override_reason || "Reason recorded"}`
                        : "Auto Rotation · One shop/day rule"}
                    </span>
                  </div>

                  <div className="action-strip">
                    <span>
                      {visitStatusLabel(visit.status)}
                    </span>

                    {visit.inspection_report_id && (
                      <button
                        type="button"
                        className="link-button"
                        onClick={() =>
                          openReport(visit.inspection_report_id)
                        }
                      >
                        Open report
                      </button>
                    )}

                    {visit.status === "ASSIGNED" && (
                      <button
                        type="button"
                        className="link-button danger"
                        disabled={busy}
                        onClick={() => cancelVisit(visit)}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      )}

      {fieldVisitor && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">My rotating assignments</span>
              <h2>Assigned shop visits</h2>
              <p>
                Normally only one shop inspection is allotted to you per day.
                If management used an unavoidable Manual Override, every assigned
                visit remains visible here. No UUID entry is required.
              </p>
            </div>
          </div>

          <div className="inspection-report-list">
            {activeFieldVisits.length === 0 ? (
              <div className="empty-state">
                No active inspection visit assigned.
              </div>
            ) : (
              activeFieldVisits.map((visit) => {
                const scheduledToday =
                  visit.scheduled_for === today;

                const canStart =
                  visit.status === "ASSIGNED" &&
                  scheduledToday;

                const highlighted =
                  focusVisitId &&
                  focusVisitId === String(visit.id);
                const lateRequest = lateRequests.find(
                  (request) =>
                    String(request.visit_assignment_id) === String(visit.id) &&
                    ["PENDING", "APPROVED"].includes(request.status)
                );

                return (
                  <div
                    className={`inspection-report-row ${highlighted ? "selected" : ""}`}
                    key={visit.id}
                  >
                    <span>
                      <strong>
                        {visit.outlet_name} ({visit.outlet_code})
                      </strong>
                      <small>
                        Scheduled: {visit.scheduled_for}
                      </small>
                    </span>

                    <span className="inspection-status">
                      {visitStatusLabel(visit.status)}
                    </span>

                    <span>
                      {visit.assignment_method === "AUTO_ROTATION"
                        ? "Rotation assignment"
                        : "Manual override"}
                      {lateRequest && (
                        <small>
                          Late start: {lateRequest.status}
                        </small>
                      )}
                    </span>

                    <span className="action-strip">
                      {canStart && (
                        <button
                          type="button"
                          className="primary-button"
                          disabled={busy}
                          onClick={() =>
                            startAssignedVisit(visit)
                          }
                        >
                          Start Inspection
                        </button>
                      )}

                      {visit.status === "ASSIGNED" && !scheduledToday && (
                        <span className="muted">
                          Start on {visit.scheduled_for}
                        </span>
                      )}

                      {visit.status === "STARTED" &&
                        visit.inspection_report_id && (
                          <button
                            type="button"
                            className="secondary-button"
                            onClick={() =>
                              openReport(
                                visit.inspection_report_id
                              )
                            }
                          >
                            Continue Inspection
                          </button>
                        )}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Inspection reports</h2>
            <p>
              Open a report to continue, review, print or complete the vendor workflow.
            </p>
          </div>

          <button
            className="secondary-button"
            onClick={loadReports}
          >
            Refresh
          </button>
        </div>

        <div className="inspection-report-list">
          {reports.length === 0 ? (
            <div className="empty-state">
              No inspection reports yet.
            </div>
          ) : (
            reports.map((report) => (
              <button
                className={`inspection-report-row ${selected?.id === report.id ? "selected" : ""}`}
                key={report.id}
                onClick={() => openReport(report.id)}
              >
                <span>
                  <strong>
                    {report.report_number}
                  </strong>
                  <small>
                    {new Date(report.inspection_started_at).toLocaleString()}
                  </small>
                </span>

                <span
                  className={`inspection-status ${String(report.status || "").toLowerCase()}`}
                >
                  {visitStatusLabel(report.status)}
                </span>

                <span>
                  {report.attention_flags?.length || 0} flag(s)
                </span>
              </button>
            ))
          )}
        </div>
      </section>

      {vendorLink && (
        <section className="panel">
          <div className="success-banner">
            Vendor notification: {notificationStatus}. The secure link is shown below
            because it may need to be shared manually.
          </div>

          <div className="vendor-link-box">
            <input
              readOnly
              value={vendorLink}
            />

            <button
              className="secondary-button"
              onClick={() =>
                navigator.clipboard?.writeText(vendorLink)
              }
            >
              Copy vendor link
            </button>
          </div>
        </section>
      )}

      {selected && (
        <>
          {management &&
            ["ACCEPTED", "DISPUTED"].includes(selected.status) && (
              <div className="action-strip">
                <button
                  className="primary-button"
                  onClick={() => acknowledge(selected)}
                >
                  HO acknowledge
                </button>
              </div>
            )}

          {management &&
            selected.status === "HO_ACKNOWLEDGED" && (
              <div className="action-strip">
                <button
                  className="primary-button"
                  onClick={() => closeReport(selected)}
                >
                  Close report
                </button>
              </div>
            )}

          {management &&
            selected.status === "VENDOR_PENDING" && (
              <div className="action-strip">
                <button
                  className="secondary-button"
                  onClick={() => regenerate(selected)}
                >
                  Regenerate / resend vendor link
                </button>
              </div>
            )}

          <ChecklistEditor
            report={selected}
            onReload={reloadSelected}
            onSubmitted={async (result) => {
              setSelected(result.report);
              setVendorLink(result.vendor_review_url);
              setNotificationStatus(
                result.vendor_notification_status
              );

              await Promise.all([
                loadReports(),
                loadVisits(),
              ]);

              window.dispatchEvent(
                new Event("action-alerts:refresh")
              );
            }}
          />

          {selected.vendor_response && (
            <section className="panel vendor-response-summary">
              <h2>Vendor response</h2>

              <p>
                <strong>
                  {selected.vendor_response}
                </strong>{" "}
                by{" "}
                {selected.vendor_response_name ||
                  selected.vendor_name_snapshot ||
                  "Vendor"}
              </p>

              <p>
                {selected.vendor_remarks || "No remarks."}
              </p>

              <p className="muted">
                Signature:{" "}
                {selected.vendor_signature_data_uri
                  ? "Provided"
                  : "Not provided (optional)"}
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}
