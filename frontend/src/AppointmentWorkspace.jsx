import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { useAuth } from "./context/AuthContext";
import { apiRequest } from "./lib/api";


function readableError(error) {
  const value = error?.detail ?? error?.message ?? error;

  if (typeof value === "string") return value;

  if (Array.isArray(value)) {
    return value
      .map((item) => item?.msg || "Invalid information.")
      .join(" ");
  }

  if (value && typeof value === "object") {
    if (typeof value.detail === "string") return value.detail;
  }

  return "The request could not be completed.";
}


function displayCode(value) {
  return String(value || "—").replaceAll("_", " ");
}


function formatDateTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}


function toLocalInput(value) {
  if (!value) return "";

  const date = new Date(value);
  const pad = (number) => String(number).padStart(2, "0");

  return [
    date.getFullYear(),
    "-",
    pad(date.getMonth() + 1),
    "-",
    pad(date.getDate()),
    "T",
    pad(date.getHours()),
    ":",
    pad(date.getMinutes()),
  ].join("");
}


function toIso(value) {
  if (!value) return null;
  return new Date(value).toISOString();
}


function newRequestForm() {
  return {
    subject: "",
    agenda: "",
    requested_start_at: "",
    requested_end_at: "",
    meeting_mode: "ONLINE",
    location: "",
    reminder_minutes: 30,
  };
}


function AppointmentDrawer({ open, title, onClose, children }) {
  if (!open) return null;

  return (
    <div className="drawer-layer">
      <button
        type="button"
        className="drawer-backdrop"
        onClick={onClose}
      />

      <aside className="drawer">
        <div className="drawer-header">
          <div>
            <span className="eyebrow">MD Appointment</span>
            <h2>{title}</h2>
          </div>

          <button
            type="button"
            className="icon-button"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}


export default function AppointmentWorkspace() {
  const { roles } = useAuth();
  const location = useLocation();

  const isMD = roles.includes("MD");

  const [myAppointments, setMyAppointments] = useState([]);
  const [managedAppointments, setManagedAppointments] = useState([]);

  const [requestForm, setRequestForm] = useState(newRequestForm);
  const [showRequest, setShowRequest] = useState(false);

  const [reviewRow, setReviewRow] = useState(null);
  const [reviewForm, setReviewForm] = useState({
    approved_start_at: "",
    approved_end_at: "",
    meeting_mode: "ONLINE",
    meeting_url: "",
    location: "",
    note: "",
    rejection_reason: "",
  });

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");

  const pendingRef = useRef(null);

  const query = useMemo(
    () => new URLSearchParams(location.search),
    [location.search]
  );

  const targetId = query.get("appointment") || "";

  const pendingAppointments = managedAppointments.filter(
    (row) => row.status === "PENDING"
  );

  const approvedAppointments = managedAppointments.filter(
    (row) => row.status === "APPROVED"
  );


  async function load() {
    setLoading(true);
    setError("");

    try {
      const minePromise = apiRequest("/appointments/me");
      const managedPromise = isMD
        ? apiRequest("/appointments/managed")
        : Promise.resolve([]);

      const [mine, managed] = await Promise.all([
        minePromise,
        managedPromise,
      ]);

      setMyAppointments(Array.isArray(mine) ? mine : []);
      setManagedAppointments(Array.isArray(managed) ? managed : []);
    } catch (err) {
      setError(readableError(err));
    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    load();
  }, [isMD]);


  useEffect(() => {
    if (loading) return;

    const queue = query.get("queue");

    if (isMD && (queue === "pending" || queue === "1")) {
      window.setTimeout(() => {
        pendingRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 100);
      return;
    }

    if (targetId) {
      window.setTimeout(() => {
        const pendingTarget = document.getElementById(
          `appointment-pending-${targetId}`
        );
        const myTarget = document.getElementById(
          `appointment-my-${targetId}`
        );

        (pendingTarget || myTarget)?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }, 100);
    }
  }, [
    loading,
    isMD,
    query,
    targetId,
    pendingAppointments.length,
    myAppointments.length,
  ]);


  function openRequest() {
    setRequestForm(newRequestForm());
    setError("");
    setSuccess("");
    setShowRequest(true);
  }


  async function submitRequest(event) {
    event.preventDefault();
    if (busy) return;

    if (
      !requestForm.requested_start_at ||
      !requestForm.requested_end_at
    ) {
      setError("Please enter the requested start and end time.");
      return;
    }

    if (
      new Date(requestForm.requested_end_at) <=
      new Date(requestForm.requested_start_at)
    ) {
      setError("Requested end time must be later than start time.");
      return;
    }

    if (
      requestForm.meeting_mode === "OFFLINE" &&
      !requestForm.location.trim()
    ) {
      setError("Please enter the physical meeting location.");
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest("/appointments", {
        method: "POST",
        body: {
          subject: requestForm.subject.trim(),
          agenda: requestForm.agenda.trim(),
          requested_start_at: toIso(requestForm.requested_start_at),
          requested_end_at: toIso(requestForm.requested_end_at),
          meeting_mode: requestForm.meeting_mode,
          location: requestForm.location.trim() || null,
          reminder_minutes: Number(
            requestForm.reminder_minutes || 30
          ),
        },
      });

      setSuccess("Appointment request submitted to MD.");
      setShowRequest(false);
      setRequestForm(newRequestForm());

      await load();
      window.dispatchEvent(new Event("action-alerts:refresh"));
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  function openReview(row) {
    setReviewRow(row);

    setReviewForm({
      approved_start_at: toLocalInput(row.requested_start_at),
      approved_end_at: toLocalInput(row.requested_end_at),
      meeting_mode: row.meeting_mode || "ONLINE",
      meeting_url: row.meeting_url || "",
      location: row.location || "",
      note: "",
      rejection_reason: "",
    });

    setError("");
    setSuccess("");
  }


  async function approveAppointment() {
    if (!reviewRow || busy) return;

    const mode = reviewForm.meeting_mode;

    if (
      ["ONLINE", "HYBRID"].includes(mode) &&
      !reviewForm.meeting_url.trim()
    ) {
      setError(
        "Enter the meeting link for an online or hybrid appointment."
      );
      return;
    }

    if (
      ["OFFLINE", "HYBRID"].includes(mode) &&
      !reviewForm.location.trim()
    ) {
      setError("Enter the physical meeting location.");
      return;
    }

    if (
      new Date(reviewForm.approved_end_at) <=
      new Date(reviewForm.approved_start_at)
    ) {
      setError("Approved end time must be later than start time.");
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(`/appointments/${reviewRow.id}/approve`, {
        method: "POST",
        body: {
          approved_start_at: toIso(reviewForm.approved_start_at),
          approved_end_at: toIso(reviewForm.approved_end_at),
          meeting_mode: mode,
          meeting_url: reviewForm.meeting_url.trim() || null,
          location: reviewForm.location.trim() || null,
          note: reviewForm.note.trim() || null,
        },
      });

      setSuccess(
        `Appointment approved for ${
          reviewRow.requester_employee_code || "employee"
        }.`
      );

      setReviewRow(null);
      await load();
      window.dispatchEvent(new Event("action-alerts:refresh"));
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  async function rejectAppointment() {
    if (!reviewRow || busy) return;

    const reason = reviewForm.rejection_reason.trim();

    if (reason.length < 3) {
      setError("Enter a rejection reason of at least 3 characters.");
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(`/appointments/${reviewRow.id}/reject`, {
        method: "POST",
        body: { reason },
      });

      setSuccess(
        `Appointment rejected for ${
          reviewRow.requester_employee_code || "employee"
        }.`
      );

      setReviewRow(null);
      await load();
      window.dispatchEvent(new Event("action-alerts:refresh"));
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  async function cancelAppointment(row) {
    if (busy) return;

    if (!window.confirm(`Cancel appointment "${row.subject}"?`)) {
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(`/appointments/${row.id}/cancel`, {
        method: "POST",
      });

      setSuccess("Appointment cancelled successfully.");
      await load();
      window.dispatchEvent(new Event("action-alerts:refresh"));
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  async function completeAppointment(row) {
    if (busy) return;

    if (!window.confirm(`Mark "${row.subject}" as completed?`)) {
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(`/appointments/${row.id}/complete`, {
        method: "POST",
      });

      setSuccess("Appointment marked completed.");
      await load();
      window.dispatchEvent(new Event("action-alerts:refresh"));
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  return (
    <div className="page">
      <header className="page-header">
        <div>
          <span className="eyebrow">Management</span>
          <h1>MD Appointments</h1>
          <p>
            Request a meeting with MD and track the confirmed schedule.
          </p>
        </div>
      </header>

      {success && (
        <div className="success-banner">✅ {success}</div>
      )}

      {error && (
        <div className="error-banner">{error}</div>
      )}

      <div className="action-strip">
        <button
          type="button"
          className="primary-button"
          onClick={openRequest}
          disabled={busy}
        >
          + Request Appointment
        </button>

        <button
          type="button"
          className="secondary-button"
          onClick={load}
          disabled={loading || busy}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>

        {isMD && pendingAppointments.length > 0 && (
          <button
            type="button"
            className="secondary-button"
            onClick={() =>
              pendingRef.current?.scrollIntoView({
                behavior: "smooth",
                block: "start",
              })
            }
          >
            Pending Requests ({pendingAppointments.length})
          </button>
        )}
      </div>


      {isMD && (
        <section className="panel" ref={pendingRef}>
          <div className="panel-header">
            <div>
              <span className="eyebrow">MD Decision Queue</span>
              <h2>Pending Appointment Requests</h2>
              <p>Only MD can approve or reject these requests.</p>
            </div>
          </div>

          {loading ? (
            <div className="skeleton-lines" />
          ) : pendingAppointments.length === 0 ? (
            <div className="empty-state">
              No appointment requests are waiting for MD.
            </div>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Requester</th>
                    <th>Subject</th>
                    <th>Requested Time</th>
                    <th>Mode</th>
                    <th>Agenda</th>
                    <th>Action</th>
                  </tr>
                </thead>

                <tbody>
                  {pendingAppointments.map((row) => (
                    <tr
                      key={row.id}
                      id={`appointment-pending-${row.id}`}
                    >
                      <td>
                        <strong>
                          {row.requester_employee_code || "—"}
                        </strong>
                        {row.requester_name && (
                          <div className="muted">
                            {row.requester_name}
                          </div>
                        )}
                      </td>

                      <td><strong>{row.subject}</strong></td>

                      <td>
                        {formatDateTime(row.requested_start_at)}
                        <div className="muted">
                          to {formatDateTime(row.requested_end_at)}
                        </div>
                      </td>

                      <td>{displayCode(row.meeting_mode)}</td>
                      <td>{row.agenda}</td>

                      <td>
                        <button
                          type="button"
                          className="primary-button"
                          onClick={() => openReview(row)}
                        >
                          Review
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}


      {isMD && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Approved / Upcoming Meetings</h2>
              <p>
                Confirmed appointments that can be marked completed.
              </p>
            </div>
          </div>

          {approvedAppointments.length === 0 ? (
            <div className="empty-state">
              No approved appointments are currently open.
            </div>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Requester</th>
                    <th>Subject</th>
                    <th>Confirmed Time</th>
                    <th>Meeting</th>
                    <th>Action</th>
                  </tr>
                </thead>

                <tbody>
                  {approvedAppointments.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>
                          {row.requester_employee_code || "—"}
                        </strong>
                        {row.requester_name && (
                          <div className="muted">
                            {row.requester_name}
                          </div>
                        )}
                      </td>

                      <td>{row.subject}</td>

                      <td>
                        {formatDateTime(row.approved_start_at)}
                        <div className="muted">
                          to {formatDateTime(row.approved_end_at)}
                        </div>
                      </td>

                      <td>
                        {displayCode(row.meeting_mode)}

                        {row.location && (
                          <div className="muted">{row.location}</div>
                        )}

                        {row.meeting_url && (
                          <div>
                            <a
                              href={row.meeting_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open meeting link
                            </a>
                          </div>
                        )}
                      </td>

                      <td>
                        <button
                          type="button"
                          className="primary-button"
                          onClick={() => completeAppointment(row)}
                          disabled={busy}
                        >
                          Mark Completed
                        </button>
                      </td>
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
            <h2>My Appointment Requests</h2>
            <p>
              Track your requests, decisions and meeting details.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="skeleton-lines" />
        ) : myAppointments.length === 0 ? (
          <div className="empty-state">
            You have not requested an appointment yet.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Subject</th>
                  <th>Status</th>
                  <th>Requested</th>
                  <th>Confirmed</th>
                  <th>Meeting Details</th>
                  <th>Decision</th>
                  <th>Action</th>
                </tr>
              </thead>

              <tbody>
                {myAppointments.map((row) => (
                  <tr
                    key={row.id}
                    id={`appointment-my-${row.id}`}
                  >
                    <td>
                      <strong>{row.subject}</strong>
                      <div className="muted">{row.agenda}</div>
                    </td>

                    <td>
                      <strong>{displayCode(row.status)}</strong>
                    </td>

                    <td>
                      {formatDateTime(row.requested_start_at)}
                      <div className="muted">
                        to {formatDateTime(row.requested_end_at)}
                      </div>
                    </td>

                    <td>
                      {row.approved_start_at
                        ? formatDateTime(row.approved_start_at)
                        : "—"}

                      {row.approved_end_at && (
                        <div className="muted">
                          to {formatDateTime(row.approved_end_at)}
                        </div>
                      )}
                    </td>

                    <td>
                      {displayCode(row.meeting_mode)}

                      {row.location && (
                        <div className="muted">{row.location}</div>
                      )}

                      {row.meeting_url && (
                        <div>
                          <a
                            href={row.meeting_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Open meeting link
                          </a>
                        </div>
                      )}
                    </td>

                    <td>{row.decision_note || "—"}</td>

                    <td>
                      {["PENDING", "APPROVED"].includes(row.status) ? (
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={busy}
                          onClick={() => cancelAppointment(row)}
                        >
                          Cancel
                        </button>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>


      <AppointmentDrawer
        open={showRequest}
        title="Request Appointment"
        onClose={() => {
          if (!busy) setShowRequest(false);
        }}
      >
        <form className="schema-form" onSubmit={submitRequest}>
          <label>
            Subject *
            <input
              required
              minLength="3"
              maxLength="220"
              disabled={busy}
              value={requestForm.subject}
              placeholder="Example: Discussion regarding field operations"
              onChange={(event) =>
                setRequestForm({
                  ...requestForm,
                  subject: event.target.value,
                })
              }
            />
          </label>

          <label>
            Agenda *
            <textarea
              required
              rows="5"
              minLength="3"
              disabled={busy}
              value={requestForm.agenda}
              placeholder="Explain what you need to discuss with MD."
              onChange={(event) =>
                setRequestForm({
                  ...requestForm,
                  agenda: event.target.value,
                })
              }
            />
          </label>

          <label>
            Requested Start *
            <input
              type="datetime-local"
              required
              disabled={busy}
              value={requestForm.requested_start_at}
              onChange={(event) =>
                setRequestForm({
                  ...requestForm,
                  requested_start_at: event.target.value,
                })
              }
            />
          </label>

          <label>
            Requested End *
            <input
              type="datetime-local"
              required
              disabled={busy}
              min={requestForm.requested_start_at || undefined}
              value={requestForm.requested_end_at}
              onChange={(event) =>
                setRequestForm({
                  ...requestForm,
                  requested_end_at: event.target.value,
                })
              }
            />
          </label>

          <label>
            Preferred Meeting Mode *
            <select
              required
              disabled={busy}
              value={requestForm.meeting_mode}
              onChange={(event) =>
                setRequestForm({
                  ...requestForm,
                  meeting_mode: event.target.value,
                })
              }
            >
              <option value="ONLINE">Online</option>
              <option value="OFFLINE">Physical / In-person</option>
              <option value="HYBRID">Hybrid</option>
            </select>
          </label>

          {["OFFLINE", "HYBRID"].includes(
            requestForm.meeting_mode
          ) && (
            <label>
              Preferred Location
              {requestForm.meeting_mode === "OFFLINE" ? " *" : ""}
              <input
                required={requestForm.meeting_mode === "OFFLINE"}
                disabled={busy}
                value={requestForm.location}
                placeholder="Office / meeting room / location"
                onChange={(event) =>
                  setRequestForm({
                    ...requestForm,
                    location: event.target.value,
                  })
                }
              />
            </label>
          )}

          <label>
            Reminder Before Meeting
            <select
              disabled={busy}
              value={requestForm.reminder_minutes}
              onChange={(event) =>
                setRequestForm({
                  ...requestForm,
                  reminder_minutes: Number(event.target.value),
                })
              }
            >
              <option value="10">10 minutes</option>
              <option value="30">30 minutes</option>
              <option value="60">1 hour</option>
              <option value="1440">1 day</option>
            </select>
          </label>

          <button
            type="submit"
            className="primary-button"
            disabled={busy}
          >
            {busy ? "Submitting…" : "Submit to MD"}
          </button>
        </form>
      </AppointmentDrawer>


      <AppointmentDrawer
        open={Boolean(reviewRow)}
        title="Review Appointment"
        onClose={() => {
          if (!busy) setReviewRow(null);
        }}
      >
        {reviewRow && (
          <>
            <section className="panel">
              <strong>
                {reviewRow.requester_employee_code || "Employee"}
              </strong>

              {reviewRow.requester_name && (
                <div className="muted">
                  {reviewRow.requester_name}
                </div>
              )}

              <h3>{reviewRow.subject}</h3>
              <p>{reviewRow.agenda}</p>

              <div className="muted">
                Requested: {formatDateTime(reviewRow.requested_start_at)}
                {" → "}
                {formatDateTime(reviewRow.requested_end_at)}
              </div>
            </section>

            <div className="schema-form">
              <label>
                Confirmed Start *
                <input
                  type="datetime-local"
                  required
                  disabled={busy}
                  value={reviewForm.approved_start_at}
                  onChange={(event) =>
                    setReviewForm({
                      ...reviewForm,
                      approved_start_at: event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Confirmed End *
                <input
                  type="datetime-local"
                  required
                  disabled={busy}
                  value={reviewForm.approved_end_at}
                  onChange={(event) =>
                    setReviewForm({
                      ...reviewForm,
                      approved_end_at: event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Meeting Mode *
                <select
                  disabled={busy}
                  value={reviewForm.meeting_mode}
                  onChange={(event) =>
                    setReviewForm({
                      ...reviewForm,
                      meeting_mode: event.target.value,
                    })
                  }
                >
                  <option value="ONLINE">Online</option>
                  <option value="OFFLINE">Physical / In-person</option>
                  <option value="HYBRID">Hybrid</option>
                </select>
              </label>

              {["ONLINE", "HYBRID"].includes(
                reviewForm.meeting_mode
              ) && (
                <label>
                  Meeting Link *
                  <input
                    type="url"
                    required
                    disabled={busy}
                    value={reviewForm.meeting_url}
                    placeholder="https://meet.example.com/..."
                    onChange={(event) =>
                      setReviewForm({
                        ...reviewForm,
                        meeting_url: event.target.value,
                      })
                    }
                  />
                </label>
              )}

              {["OFFLINE", "HYBRID"].includes(
                reviewForm.meeting_mode
              ) && (
                <label>
                  Meeting Location *
                  <input
                    required
                    disabled={busy}
                    value={reviewForm.location}
                    placeholder="Office / board room / location"
                    onChange={(event) =>
                      setReviewForm({
                        ...reviewForm,
                        location: event.target.value,
                      })
                    }
                  />
                </label>
              )}

              <label>
                Approval Note
                <textarea
                  rows="3"
                  disabled={busy}
                  value={reviewForm.note}
                  placeholder="Optional note for requester"
                  onChange={(event) =>
                    setReviewForm({
                      ...reviewForm,
                      note: event.target.value,
                    })
                  }
                />
              </label>

              <button
                type="button"
                className="primary-button"
                disabled={busy}
                onClick={approveAppointment}
              >
                {busy ? "Processing…" : "Approve Appointment"}
              </button>

              <label>
                Rejection Reason
                <textarea
                  rows="3"
                  disabled={busy}
                  value={reviewForm.rejection_reason}
                  placeholder="Required only when rejecting"
                  onChange={(event) =>
                    setReviewForm({
                      ...reviewForm,
                      rejection_reason: event.target.value,
                    })
                  }
                />
              </label>

              <button
                type="button"
                className="secondary-button"
                disabled={
                  busy ||
                  reviewForm.rejection_reason.trim().length < 3
                }
                onClick={rejectAppointment}
              >
                Reject Appointment
              </button>
            </div>
          </>
        )}
      </AppointmentDrawer>
    </div>
  );
}
