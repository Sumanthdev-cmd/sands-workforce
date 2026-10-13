import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { useAuth } from "./context/AuthContext";
import { apiRequest, uploadWithProgress } from "./lib/api";
import "./account_sheet_styles.css";


const MAX_FILE_SIZE = 50_000_000;
const ACCEPTED_FILES = ".pdf,.png,.jpg,.jpeg,.webp,.xls,.xlsx,.csv";


function localDate() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}


function newSheet() {
  return {
    localId: crypto.randomUUID(),
    sheet_name: "",
    sheet_generated_on: localDate(),
    has_discrepancy: false,
    discrepancy_reason: "",
    file: null,
  };
}


function newForm() {
  return {
    submission_id: crypto.randomUUID(),
    verification_date: localDate(),
    declared_sheet_count: 1,
    notes: "",
    items: [newSheet()],
  };
}


function readableError(error) {
  const value = error?.data?.detail ?? error?.detail ?? error?.message ?? error;

  if (typeof value === "string") {
    return value === "[object Object]"
      ? "The request could not be completed."
      : value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => item?.msg || "Invalid information.").join(" ");
  }

  return "The request could not be completed.";
}


function displayStatus(value) {
  return String(value || "—").replaceAll("_", " ");
}


function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}


function formatDateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}


function contentTypeFor(file) {
  if (file?.type) return file.type;
  const extension = String(file?.name || "").split(".").pop()?.toLowerCase();
  const types = {
    pdf: "application/pdf",
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    webp: "image/webp",
    xls: "application/vnd.ms-excel",
    xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    csv: "text/csv",
  };
  return types[extension] || "application/octet-stream";
}


function StatusBadge({ value, danger = false }) {
  const normalized = String(value || "").toLowerCase();
  const warning = danger || normalized.includes("open") || normalized.includes("pending");
  return (
    <span className={`sheet-status ${warning ? "warning" : "success"}`}>
      {displayStatus(value)}
    </span>
  );
}


function DocumentActions({ item, onOpen, busyId }) {
  if (!item?.discrepancy_document_id) return null;

  return (
    <div className="sheet-document-actions">
      <span>{item.discrepancy_document_name || "Discrepancy attachment"}</span>
      <button
        type="button"
        className="secondary-button compact-button"
        disabled={busyId === item.discrepancy_document_id}
        onClick={() => onOpen(item, "preview")}
      >
        {busyId === item.discrepancy_document_id ? "Opening…" : "Preview"}
      </button>
      <button
        type="button"
        className="secondary-button compact-button"
        disabled={busyId === item.discrepancy_document_id}
        onClick={() => onOpen(item, "download")}
      >
        Download
      </button>
    </div>
  );
}


function SheetItemCard({
  item,
  onOpen,
  documentBusyId,
  onReview,
  onResolve,
  actionBusyId,
  showReviewActions = false,
  showResolveAction = false,
}) {
  return (
    <article className="sheet-item-card" id={`sheet-item-${item.id}`}>
      <div className="sheet-item-heading">
        <div>
          <strong>{item.sheet_name}</strong>
          <span>
            Generated {formatDate(item.sheet_generated_on)} · Reported by {" "}
            {item.accounts_manager_name} ({item.accounts_manager_employee_code})
          </span>
        </div>
        <div className="sheet-badge-row">
          <StatusBadge value={item.secretary_status} />
          {item.has_discrepancy && (
            <StatusBadge value={item.issue_status} danger={item.issue_status === "OPEN"} />
          )}
        </div>
      </div>

      {item.has_discrepancy ? (
        <div className="sheet-discrepancy-box">
          <strong>Reported discrepancy</strong>
          <p>{item.discrepancy_reason}</p>
          <small>Raised: {formatDateTime(item.issue_raised_at)}</small>
        </div>
      ) : (
        <p className="muted">Accounts Manager reported no discrepancy for this sheet.</p>
      )}

      <DocumentActions item={item} onOpen={onOpen} busyId={documentBusyId} />

      {item.secretary_note && (
        <p className="sheet-note">
          <strong>Accounts Secretary:</strong> {item.secretary_note}
        </p>
      )}

      {item.resolution_note && (
        <p className="sheet-note success-note">
          <strong>Resolution ({item.resolution_role}):</strong> {item.resolution_note}
        </p>
      )}

      <div className="sheet-timeline">
        {item.admin_escalated_at && (
          <span>ADMIN notified {formatDateTime(item.admin_escalated_at)}</span>
        )}
        {item.md_escalated_at && (
          <span>MD notified {formatDateTime(item.md_escalated_at)}</span>
        )}
        {item.resolved_at && <span>Resolved {formatDateTime(item.resolved_at)}</span>}
      </div>

      {showReviewActions && item.can_secretary_review && (
        <div className="sheet-card-actions">
          {item.has_discrepancy ? (
            <>
              <button
                type="button"
                className="primary-button"
                disabled={actionBusyId === item.id}
                onClick={() => onReview(item, "CONFIRMED")}
              >
                Confirm Discrepancy
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={actionBusyId === item.id}
                onClick={() => onReview(item, "NOT_FOUND")}
              >
                Discrepancy Not Found
              </button>
            </>
          ) : (
            <button
              type="button"
              className="primary-button"
              disabled={actionBusyId === item.id}
              onClick={() => onReview(item, "VERIFIED")}
            >
              Verify Sheet
            </button>
          )}
        </div>
      )}

      {showResolveAction && item.can_resolve && (
        <div className="sheet-card-actions">
          <button
            type="button"
            className="primary-button"
            disabled={actionBusyId === item.id}
            onClick={() => onResolve(item)}
          >
            Resolve Escalated Issue
          </button>
        </div>
      )}
    </article>
  );
}


export default function AccountsSheetWorkspace() {
  const { roles } = useAuth();
  const location = useLocation();

  const isAccountsManager = roles.includes("ACCOUNTS_MANAGER");
  const isAccountsSecretary = roles.includes("ACCOUNTS_SECRETARY");
  const isAdmin = roles.includes("ADMIN");
  const isMD = roles.includes("MD");

  const [form, setForm] = useState(newForm);
  const [showForm, setShowForm] = useState(false);
  const [reports, setReports] = useState([]);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [issues, setIssues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [documentBusyId, setDocumentBusyId] = useState("");
  const [actionBusyId, setActionBusyId] = useState("");
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");
  const queueRef = useRef(null);
  const submittingRef = useRef(false);

  const discrepancies = useMemo(
    () => form.items.filter((item) => item.has_discrepancy).length,
    [form.items]
  );


  async function loadData() {
    setLoading(true);
    setError("");

    const requests = [apiRequest("/account-sheet-verifications")];
    if (isAccountsSecretary) {
      requests.push(apiRequest("/account-sheet-verifications/review-queue"));
    } else {
      requests.push(Promise.resolve([]));
    }
    requests.push(apiRequest("/account-sheet-verifications/issues"));

    const [reportResult, reviewResult, issueResult] = await Promise.allSettled(requests);

    if (reportResult.status === "fulfilled") {
      setReports(Array.isArray(reportResult.value) ? reportResult.value : []);
    } else {
      setReports([]);
      setError(readableError(reportResult.reason));
    }

    setReviewQueue(
      reviewResult.status === "fulfilled" && Array.isArray(reviewResult.value)
        ? reviewResult.value
        : []
    );

    setIssues(
      issueResult.status === "fulfilled" && Array.isArray(issueResult.value)
        ? issueResult.value
        : []
    );
    setLoading(false);
  }


  useEffect(() => {
    loadData();
  }, [isAccountsManager, isAccountsSecretary, isAdmin, isMD]);


  useEffect(() => {
    if (loading) return;
    const params = new URLSearchParams(location.search);
    const itemId = params.get("item");

    window.setTimeout(() => {
      if (itemId) {
        document.getElementById(`sheet-item-${itemId}`)?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      } else if (params.get("queue") === "1") {
        queueRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 150);
  }, [loading, location.search, reviewQueue.length, issues.length]);


  function refreshActionAlerts() {
    window.dispatchEvent(new Event("action-alerts:refresh"));
  }


  function updateSheet(index, changes) {
    setForm((current) => ({
      ...current,
      items: current.items.map((item, itemIndex) =>
        itemIndex === index ? { ...item, ...changes } : item
      ),
    }));
  }


  function addSheet() {
    setForm((current) => ({
      ...current,
      declared_sheet_count: current.items.length + 1,
      items: [...current.items, newSheet()],
    }));
  }


  function removeSheet(index) {
    setForm((current) => {
      if (current.items.length === 1) return current;
      const items = current.items.filter((_, itemIndex) => itemIndex !== index);
      return { ...current, items, declared_sheet_count: items.length };
    });
  }


  async function uploadEvidence(item, itemIndex, totalUploads) {
    const file = item.file;
    if (!file) {
      throw new Error(`Upload the discrepant sheet for '${item.sheet_name}'.`);
    }
    if (file.size > MAX_FILE_SIZE) {
      throw new Error(`${file.name} is larger than the 50 MB limit.`);
    }

    const contentType = contentTypeFor(file);
    const prepared = await apiRequest("/documents/presign-upload", {
      method: "POST",
      body: {
        owner_type: "ACCOUNT_SHEET",
        owner_id: null,
        category: "ACCOUNT_SHEET_DISCREPANCY",
        title: `${item.sheet_name.trim()} - discrepancy sheet`,
        description: item.discrepancy_reason.trim(),
        file_name: file.name,
        content_type: contentType,
        file_size: file.size,
        issue_date: item.sheet_generated_on,
        expiry_date: null,
        alert_days_before: 0,
        is_confidential: true,
        extra_data: {
          purpose: "ACCOUNT_SHEET_DISCREPANCY",
          submission_id: form.submission_id,
          verification_date: form.verification_date,
          sheet_name: item.sheet_name.trim(),
        },
      },
    });

    const etag = await uploadWithProgress(
      prepared.upload_url,
      file,
      contentType,
      (percentage) => {
        const completed = itemIndex;
        setProgress(Math.round(((completed + percentage / 100) / totalUploads) * 100));
      }
    );

    await apiRequest(`/documents/${prepared.document_id}/complete`, {
      method: "POST",
      body: { etag: etag ? etag.replaceAll('"', "") : null },
    });

    return prepared.document_id;
  }


  async function submitReport(event) {
    event.preventDefault();
    if (submittingRef.current) return;

    setError("");
    setSuccess("");

    if (Number(form.declared_sheet_count) !== form.items.length) {
      setError(
        `Declared count is ${form.declared_sheet_count}, but ${form.items.length} sheet entries are listed.`
      );
      return;
    }

    for (const item of form.items) {
      if (!item.sheet_name.trim()) {
        setError("Enter the name of every verified sheet.");
        return;
      }
      if (!item.sheet_generated_on) {
        setError(`Enter the generated date for '${item.sheet_name}'.`);
        return;
      }
      if (item.has_discrepancy && !item.discrepancy_reason.trim()) {
        setError(`State the discrepancy reason for '${item.sheet_name}'.`);
        return;
      }
      if (item.has_discrepancy && !item.file) {
        setError(`Upload the discrepant sheet for '${item.sheet_name}'.`);
        return;
      }
    }

    submittingRef.current = true;
    setSubmitting(true);
    setProgress(0);

    try {
      const discrepancyItems = form.items.filter((item) => item.has_discrepancy);
      const uploadedDocuments = new Map();

      for (let index = 0; index < discrepancyItems.length; index += 1) {
        const item = discrepancyItems[index];
        const documentId = await uploadEvidence(item, index, discrepancyItems.length);
        uploadedDocuments.set(item.localId, documentId);
      }

      await apiRequest("/account-sheet-verifications", {
        method: "POST",
        body: {
          submission_id: form.submission_id,
          verification_date: form.verification_date,
          declared_sheet_count: Number(form.declared_sheet_count),
          notes: form.notes.trim() || null,
          items: form.items.map((item) => ({
            sheet_name: item.sheet_name.trim(),
            sheet_generated_on: item.sheet_generated_on,
            has_discrepancy: item.has_discrepancy,
            discrepancy_reason: item.has_discrepancy
              ? item.discrepancy_reason.trim()
              : null,
            discrepancy_document_id: item.has_discrepancy
              ? uploadedDocuments.get(item.localId)
              : null,
          })),
        },
      });

      setSuccess("Daily sheet-verification report submitted to Accounts Secretary.");
      setForm(newForm());
      setShowForm(false);
      setProgress(0);
      refreshActionAlerts();
      await loadData();
    } catch (err) {
      setError(readableError(err));
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }


  async function openDocument(item, mode) {
    if (!item?.discrepancy_document_id) return;
    const previewWindow = window.open("", "_blank");
    setDocumentBusyId(item.discrepancy_document_id);
    setError("");

    try {
      const suffix = mode === "download" ? "download-url" : "preview-url";
      const response = await apiRequest(
        `/documents/${item.discrepancy_document_id}/${suffix}`
      );
      if (!response?.download_url) {
        throw new Error("The secure document link was not returned.");
      }
      if (previewWindow) {
        previewWindow.location.href = response.download_url;
      } else {
        window.open(response.download_url, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      previewWindow?.close();
      setError(readableError(err));
    } finally {
      setDocumentBusyId("");
    }
  }


  async function reviewItem(item, decision) {
    const message =
      decision === "VERIFIED"
        ? "Verification remarks (optional):"
        : decision === "CONFIRMED"
          ? "State what you verified before confirming this discrepancy:"
          : "Explain why the reported discrepancy was not found or is closed:";

    const note = window.prompt(message, "");
    if (note === null) return;
    if (item.has_discrepancy && note.trim().length < 3) {
      setError("Accounts Secretary remarks are required for a discrepancy decision.");
      return;
    }

    setActionBusyId(item.id);
    setError("");
    setSuccess("");
    try {
      await apiRequest(
        `/account-sheet-verifications/items/${item.id}/secretary-review`,
        { method: "POST", body: { decision, note: note.trim() || null } }
      );
      setSuccess(
        decision === "CONFIRMED"
          ? "Discrepancy confirmed and ADMIN notified immediately."
          : "Accounts Secretary review recorded."
      );
      refreshActionAlerts();
      await loadData();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setActionBusyId("");
    }
  }


  async function resolveItem(item) {
    const note = window.prompt(
      "Describe exactly how this accounts discrepancy was resolved:",
      ""
    );
    if (note === null) return;
    if (note.trim().length < 3) {
      setError("A resolution note is required.");
      return;
    }

    setActionBusyId(item.id);
    setError("");
    setSuccess("");
    try {
      await apiRequest(`/account-sheet-verifications/items/${item.id}/resolve`, {
        method: "POST",
        body: { resolution_note: note.trim() },
      });
      setSuccess("The accounts discrepancy is marked resolved.");
      refreshActionAlerts();
      await loadData();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setActionBusyId("");
    }
  }


  return (
    <div className="page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Accounts Control</span>
          <h1>Daily Sheet Verification</h1>
          <p>
            Record every verified sheet, route discrepancies with evidence, and track
            the 6-hour ADMIN and 24-hour MD escalation deadlines.
          </p>
        </div>
      </header>

      {success && <div className="success-banner">✅ {success}</div>}
      {error && <div className="error-banner">{error}</div>}

      <div className="sheet-policy-banner">
        <strong>Escalation policy</strong>
        <span>Accounts Secretary receives every submission immediately.</span>
        <span>Confirmed or unresolved discrepancies notify ADMIN by 6 hours.</span>
        <span>Issues still open at 24 hours notify MD.</span>
      </div>

      <div className="action-strip">
        {isAccountsManager && !showForm && (
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              setForm(newForm());
              setShowForm(true);
              setError("");
              setSuccess("");
            }}
          >
            + Submit Daily Verification
          </button>
        )}
        {isAccountsManager && showForm && (
          <button
            type="button"
            className="secondary-button"
            disabled={submitting}
            onClick={() => setShowForm(false)}
          >
            Close Form
          </button>
        )}
        <button
          type="button"
          className="secondary-button"
          disabled={loading || submitting}
          onClick={loadData}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {isAccountsManager && showForm && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Accounts Manager Daily Declaration</h2>
              <p>The declared number must match the named sheet entries below.</p>
            </div>
          </div>

          <form className="document-form" onSubmit={submitReport}>
            <div className="form-grid">
              <label>
                Verification Date *
                <input
                  type="date"
                  required
                  max={localDate()}
                  disabled={submitting}
                  value={form.verification_date}
                  onChange={(event) =>
                    setForm({ ...form, verification_date: event.target.value })
                  }
                />
              </label>

              <label>
                Number of Sheets Verified *
                <input
                  type="number"
                  required
                  min="1"
                  max="500"
                  disabled={submitting}
                  value={form.declared_sheet_count}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      declared_sheet_count: event.target.value,
                    })
                  }
                />
              </label>
            </div>

            <label>
              Daily Remarks
              <textarea
                rows="3"
                disabled={submitting}
                value={form.notes}
                onChange={(event) => setForm({ ...form, notes: event.target.value })}
              />
            </label>

            <div className="sheet-form-summary">
              <strong>{form.items.length} sheet entries</strong>
              <span>{discrepancies} discrepancies reported</span>
            </div>

            <div className="sheet-entry-list">
              {form.items.map((item, index) => (
                <article className="sheet-entry-form" key={item.localId}>
                  <div className="sheet-entry-number">
                    <strong>Sheet {index + 1}</strong>
                    {form.items.length > 1 && (
                      <button
                        type="button"
                        className="link-button danger-link"
                        disabled={submitting}
                        onClick={() => removeSheet(index)}
                      >
                        Remove
                      </button>
                    )}
                  </div>

                  <div className="form-grid">
                    <label>
                      Sheet Name *
                      <input
                        required
                        disabled={submitting}
                        value={item.sheet_name}
                        placeholder="Example: Daily Sales Register"
                        onChange={(event) =>
                          updateSheet(index, { sheet_name: event.target.value })
                        }
                      />
                    </label>

                    <label>
                      Sheet Generated Date *
                      <input
                        type="date"
                        required
                        max={form.verification_date || localDate()}
                        disabled={submitting}
                        value={item.sheet_generated_on}
                        onChange={(event) =>
                          updateSheet(index, {
                            sheet_generated_on: event.target.value,
                          })
                        }
                      />
                    </label>
                  </div>

                  <label className="checkbox-row sheet-checkbox">
                    <input
                      type="checkbox"
                      disabled={submitting}
                      checked={item.has_discrepancy}
                      onChange={(event) =>
                        updateSheet(index, {
                          has_discrepancy: event.target.checked,
                          discrepancy_reason: event.target.checked
                            ? item.discrepancy_reason
                            : "",
                          file: event.target.checked ? item.file : null,
                        })
                      }
                    />
                    <span>A discrepancy was found in this sheet</span>
                  </label>

                  {item.has_discrepancy && (
                    <div className="sheet-discrepancy-fields">
                      <label>
                        Discrepancy Reason *
                        <textarea
                          rows="4"
                          required
                          disabled={submitting}
                          value={item.discrepancy_reason}
                          placeholder="State the mismatch, missing entry, amount difference, or other issue."
                          onChange={(event) =>
                            updateSheet(index, {
                              discrepancy_reason: event.target.value,
                            })
                          }
                        />
                      </label>

                      <label className="file-drop">
                        Upload Discrepant Sheet *
                        <input
                          type="file"
                          required
                          disabled={submitting}
                          accept={ACCEPTED_FILES}
                          onChange={(event) =>
                            updateSheet(index, {
                              file: event.target.files?.[0] || null,
                            })
                          }
                        />
                        <span>
                          {item.file
                            ? `${item.file.name} · ${Math.ceil(item.file.size / 1024)} KB`
                            : "PDF, image, Excel, or CSV · maximum 50 MB"}
                        </span>
                      </label>
                    </div>
                  )}
                </article>
              ))}
            </div>

            <button
              type="button"
              className="secondary-button"
              disabled={submitting || form.items.length >= 500}
              onClick={addSheet}
            >
              + Add Another Sheet
            </button>

            {submitting && discrepancies > 0 && (
              <div className="sheet-upload-progress">
                <span>Uploading discrepancy evidence… {progress}%</span>
                <div className="progress-bar">
                  <span style={{ width: `${progress}%` }} />
                </div>
              </div>
            )}

            <button type="submit" className="primary-button" disabled={submitting}>
              {submitting ? "Submitting…" : "Submit to Accounts Secretary"}
            </button>
          </form>
        </section>
      )}

      {isAccountsSecretary && (
        <section className="panel" ref={queueRef}>
          <div className="panel-header">
            <div>
              <span className="eyebrow">Action Required</span>
              <h2>Accounts Secretary Review Queue</h2>
              <p>Verify every sheet entry and inspect attached evidence before deciding.</p>
            </div>
            <StatusBadge value={`${reviewQueue.length} PENDING`} />
          </div>

          {reviewQueue.length === 0 ? (
            <div className="empty-state">No sheet entries are waiting for review.</div>
          ) : (
            <div className="sheet-card-list">
              {reviewQueue.map((item) => (
                <SheetItemCard
                  key={item.id}
                  item={item}
                  onOpen={openDocument}
                  documentBusyId={documentBusyId}
                  onReview={reviewItem}
                  actionBusyId={actionBusyId}
                  showReviewActions
                />
              ))}
            </div>
          )}
        </section>
      )}

      <section className="panel" ref={!isAccountsSecretary ? queueRef : undefined}>
        <div className="panel-header">
          <div>
            <span className="eyebrow">Unresolved</span>
            <h2>Open Discrepancies</h2>
            <p>
              ADMIN receives confirmed issues immediately or unresolved issues at six
              hours. MD receives only issues still open at 24 hours.
            </p>
          </div>
          <StatusBadge value={`${issues.length} OPEN`} danger={issues.length > 0} />
        </div>

        {issues.length === 0 ? (
          <div className="empty-state">No open discrepancies at your access level.</div>
        ) : (
          <div className="sheet-card-list">
            {issues.map((item) => (
              <SheetItemCard
                key={item.id}
                item={item}
                onOpen={openDocument}
                documentBusyId={documentBusyId}
                onResolve={resolveItem}
                actionBusyId={actionBusyId}
                showResolveAction={isAdmin || isMD}
              />
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="eyebrow">Register</span>
            <h2>Daily Verification History</h2>
            <p>Declared totals, named sheets, Secretary decisions, and resolution trail.</p>
          </div>
        </div>

        {loading ? (
          <div className="skeleton-lines" />
        ) : reports.length === 0 ? (
          <div className="empty-state">No daily sheet-verification reports yet.</div>
        ) : (
          <div className="sheet-report-list">
            {reports.map((report) => (
              <details className="sheet-report-card" key={report.id}>
                <summary>
                  <div>
                    <strong>{formatDate(report.verification_date)}</strong>
                    <span>
                      {report.accounts_manager_name} ({report.accounts_manager_employee_code})
                    </span>
                  </div>
                  <div className="sheet-report-metrics">
                    <span>{report.actual_sheet_count} sheets</span>
                    <span>{report.discrepancy_count} discrepancies</span>
                    <StatusBadge value={report.status} danger={report.open_issue_count > 0} />
                  </div>
                </summary>

                {report.notes && <p className="sheet-note">{report.notes}</p>}
                <div className="sheet-card-list compact-list">
                  {report.items.map((item) => (
                    <SheetItemCard
                      key={item.id}
                      item={item}
                      onOpen={openDocument}
                      documentBusyId={documentBusyId}
                      onReview={reviewItem}
                      onResolve={resolveItem}
                      actionBusyId={actionBusyId}
                      showReviewActions={isAccountsSecretary}
                      showResolveAction={isAdmin || isMD}
                    />
                  ))}
                </div>
              </details>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
