import DateField from "./DateField";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  apiRequest,
  uploadWithProgress,
} from "./lib/api";

import { useAuth } from "./context/AuthContext";


const CATEGORIES = [
  ["ELECTRICAL", "Electrical"],
  ["PLUMBING", "Plumbing"],
  ["CIVIL_RENOVATION", "Civil / Renovation"],
  ["EQUIPMENT_REPAIR", "Equipment Repair"],
  ["VEHICLE_MAINTENANCE", "Vehicle Maintenance"],
  ["OUTLET_MAINTENANCE", "Outlet Maintenance"],
  ["PROPERTY_MAINTENANCE", "Property Maintenance"],
  ["IT_COMPUTER", "IT / Computer"],
  ["AMC_SERVICE_CONTRACT", "AMC / Service Contract"],
  ["UTILITY_BILL", "Utility Bill"],
  ["VENDOR_SERVICE", "Vendor Service"],
  ["GENERAL", "General"],
];


const RELATED_TYPES = [
  ["GENERAL", "General / Office"],
  ["OUTLET", "Outlet"],
  ["VEHICLE", "Vehicle"],
  ["PROPERTY", "Property"],
  ["COMPANY_ASSET", "Company Asset"],
];


function newForm() {
  return {
    submission_id: crypto.randomUUID(),

    category: "GENERAL",
    related_type: "GENERAL",

    outlet_id: "",
    vehicle_id: "",
    property_id: "",
    company_asset_id: "",

    vendor_id: "",
    vendor_name: "",

    invoice_number: "",
    bill_date: new Date().toISOString().slice(0, 10),
    due_date: "",

    amount: "",
    description: "",
  };
}


function readableError(error) {
  if (error?.status === 403) {
    return (
      error?.message ||
      "You do not have permission to perform this action."
    );
  }

  if (error?.status === 409) {
    return (
      error?.message ||
      "This action has already been completed."
    );
  }

  const value =
    error?.detail ??
    error?.message ??
    error;

  if (typeof value === "string") {
    return value === "[object Object]"
      ? "The request could not be completed."
      : value;
  }

  if (Array.isArray(value)) {
    return value
      .map((item) => item?.msg || "Invalid information.")
      .join(" ");
  }

  if (value && typeof value === "object") {
    if (typeof value.detail === "string") {
      return value.detail;
    }

    if (Array.isArray(value.detail)) {
      return value.detail
        .map((item) => item?.msg || "Invalid information.")
        .join(" ");
    }
  }

  return "The request could not be completed.";
}


function displayCode(value) {
  return String(value || "—")
    .replaceAll("_", " ");
}


function optionLabel(row, type) {
  if (!row) return "Unknown";

  if (type === "vendor") {
    return row.name
      ? `${row.code ? `${row.code} · ` : ""}${row.name}`
      : row.code || row.id;
  }

  if (type === "vehicle") {
    return (
      row.registration_number ||
      row.name ||
      row.code ||
      row.id
    );
  }

  return (
    row.name ||
    row.asset_name ||
    row.asset_tag ||
    row.code ||
    row.id
  );
}


export default function MaintenanceBillsWorkspace() {
  const { roles } = useAuth();
  const location = useLocation();

  const isAdmin = roles.includes("ADMIN");
  const isMD = roles.includes("MD");

  const [form, setForm] = useState(newForm);
  const [file, setFile] = useState(null);

  const [bills, setBills] = useState([]);
  const [mdPending, setMdPending] = useState([]);

  const [vendors, setVendors] = useState([]);
  const [outlets, setOutlets] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [properties, setProperties] = useState([]);
  const [companyAssets, setCompanyAssets] = useState([]);

  const [showForm, setShowForm] = useState(false);

  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState(0);
  const [previewingId, setPreviewingId] = useState("");

  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");

  const submittingRef = useRef(false);
  const mdQueueRef = useRef(null);
  const registerRef = useRef(null);


  async function loadBills() {
    setLoading(true);

    try {
      const data = await apiRequest(
        "/maintenance-bills"
      );

      setBills(
        Array.isArray(data) ? data : []
      );

      if (isMD) {
        const pending = await apiRequest(
          "/maintenance-bills/md-pending"
        );

        setMdPending(
          Array.isArray(pending)
            ? pending
            : []
        );
      } else {
        setMdPending([]);
      }
    } catch (err) {
      setError(readableError(err));
    } finally {
      setLoading(false);
    }
  }


  async function loadOptions() {
    if (!isAdmin) return;

    const results = await Promise.allSettled([
      apiRequest("/operations/vendors"),
      apiRequest("/outlets"),
      apiRequest("/assets/vehicles"),
      apiRequest("/assets/properties"),
      apiRequest("/asset-inventory/assets"),
    ]);

    const value = (index) =>
      results[index].status === "fulfilled" &&
      Array.isArray(results[index].value)
        ? results[index].value
        : [];

    setVendors(value(0));
    setOutlets(value(1));
    setVehicles(value(2));
    setProperties(value(3));
    setCompanyAssets(value(4));
  }


  useEffect(() => {
    loadBills();
    loadOptions();
  }, [isAdmin, isMD]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get("queue") !== "1") return;
    window.setTimeout(() => {
      (isMD ? mdQueueRef.current : registerRef.current)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 150);
  }, [location.search, isMD, mdPending.length, bills.length]);


  function refreshActionAlerts() {
    window.dispatchEvent(new Event("action-alerts:refresh"));
  }

  function startNewBill() {
    setForm(newForm());
    setFile(null);
    setProgress(0);
    setSuccess("");
    setError("");
    setShowForm(true);
  }


  function changeRelatedType(value) {
    setForm({
      ...form,

      related_type: value,

      outlet_id: "",
      vehicle_id: "",
      property_id: "",
      company_asset_id: "",
    });
  }


  function selectedRelatedId() {
    if (form.related_type === "OUTLET") {
      return form.outlet_id;
    }

    if (form.related_type === "VEHICLE") {
      return form.vehicle_id;
    }

    if (form.related_type === "PROPERTY") {
      return form.property_id;
    }

    if (form.related_type === "COMPANY_ASSET") {
      return form.company_asset_id;
    }

    return "";
  }


  function setRelatedId(value) {
    if (form.related_type === "OUTLET") {
      setForm({
        ...form,
        outlet_id: value,
      });
    }

    if (form.related_type === "VEHICLE") {
      setForm({
        ...form,
        vehicle_id: value,
      });
    }

    if (form.related_type === "PROPERTY") {
      setForm({
        ...form,
        property_id: value,
      });
    }

    if (form.related_type === "COMPANY_ASSET") {
      setForm({
        ...form,
        company_asset_id: value,
      });
    }
  }


  function relatedOptions() {
    if (form.related_type === "OUTLET") {
      return {
        type: "outlet",
        rows: outlets,
      };
    }

    if (form.related_type === "VEHICLE") {
      return {
        type: "vehicle",
        rows: vehicles,
      };
    }

    if (form.related_type === "PROPERTY") {
      return {
        type: "property",
        rows: properties,
      };
    }

    if (form.related_type === "COMPANY_ASSET") {
      return {
        type: "asset",
        rows: companyAssets,
      };
    }

    return {
      type: "",
      rows: [],
    };
  }


  async function uploadBillDocument() {
    if (!file) {
      throw new Error(
        "Please choose the bill image or PDF."
      );
    }

    const contentType =
      file.type || "application/octet-stream";

    const prepared = await apiRequest(
      "/documents/presign-upload",
      {
        method: "POST",

        body: {
          owner_type: "GENERAL",
          owner_id: null,

          category: "MAINTENANCE_BILL",

          title:
            form.invoice_number.trim()
              ? `Maintenance Bill ${form.invoice_number.trim()}`
              : `Maintenance Bill - ${form.vendor_name.trim()}`,

          description:
            form.description.trim(),

          issue_date:
            form.bill_date || null,

          expiry_date: null,

          alert_days_before: 30,

          is_confidential: true,

          file_name: file.name,
          content_type: contentType,
          file_size: file.size,

          extra_data: {
            purpose: "MAINTENANCE_BILL",
            submission_id:
              form.submission_id,
          },
        },
      }
    );

    const etag = await uploadWithProgress(
      prepared.upload_url,
      file,
      contentType,
      setProgress
    );

    await apiRequest(
      `/documents/${prepared.document_id}/complete`,
      {
        method: "POST",

        body: {
          etag: etag
            ? etag.replaceAll('"', "")
            : null,
        },
      }
    );

    setProgress(100);

    return prepared.document_id;
  }


  async function createAndSubmit(event) {
    event.preventDefault();

    if (submittingRef.current) {
      return;
    }

    if (!file) {
      setError(
        "Please upload the maintenance bill image or PDF."
      );
      return;
    }

    if (!form.vendor_name.trim()) {
      setError(
        "Please enter or select the vendor."
      );
      return;
    }

    if (
      form.related_type !== "GENERAL" &&
      !selectedRelatedId()
    ) {
      setError(
        `Please select the ${displayCode(
          form.related_type
        ).toLowerCase()}.`
      );
      return;
    }

    submittingRef.current = true;

    setBusy(true);
    setError("");
    setSuccess("");
    setProgress(0);

    try {
      const documentId =
        await uploadBillDocument();

      const created = await apiRequest(
        "/maintenance-bills",
        {
          method: "POST",

          body: {
            submission_id:
              form.submission_id,

            category:
              form.category,

            related_type:
              form.related_type,

            outlet_id:
              form.outlet_id || null,

            vehicle_id:
              form.vehicle_id || null,

            property_id:
              form.property_id || null,

            company_asset_id:
              form.company_asset_id || null,

            vendor_id:
              form.vendor_id || null,

            vendor_name:
              form.vendor_name.trim(),

            invoice_number:
              form.invoice_number.trim() ||
              null,

            bill_date:
              form.bill_date,

            due_date:
              form.due_date || null,

            amount:
              Number(form.amount),

            description:
              form.description.trim(),

            bill_document_id:
              documentId,
          },
        }
      );

      /*
       * Immediately move the created record from
       * DRAFT to SUBMITTED.
       */
      await apiRequest(
        `/maintenance-bills/${created.id}/submit`,
        {
          method: "POST",
        }
      );

      setSuccess(
        "Maintenance bill submitted successfully for Admin verification."
      );

      setShowForm(false);
      setFile(null);
      setProgress(0);
      setForm(newForm());

      refreshActionAlerts();
      await loadBills();
    } catch (err) {
      setError(readableError(err));
    } finally {
      submittingRef.current = false;
      setBusy(false);
    }
  }


  async function previewBillDocument(row) {
    if (!row?.bill_document_id) {
      setError(
        "No bill image or PDF is attached to this record."
      );
      return;
    }

    setPreviewingId(row.id);
    setError("");

    const previewWindow = window.open(
      "",
      "_blank"
    );

    try {
      const result = await apiRequest(
        `/documents/${row.bill_document_id}/preview-url`
      );

      if (!result?.download_url) {
        throw new Error(
          "The document preview URL was not returned."
        );
      }

      if (previewWindow) {
        previewWindow.location.href =
          result.download_url;
      } else {
        window.open(
          result.download_url,
          "_blank",
          "noopener,noreferrer"
        );
      }
    } catch (err) {
      previewWindow?.close();

      setError(
        readableError(err)
      );
    } finally {
      setPreviewingId("");
    }
  }


  async function verifyBill(row) {
    if (!isAdmin) return;

    const note = window.prompt(
      "Verification remarks (optional):",
      ""
    );

    if (note === null) return;

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        `/maintenance-bills/${row.id}/verify`,
        {
          method: "POST",
          body: {
            note: note || null,
          },
        }
      );

      setSuccess(
        "Bill verified successfully and sent to MD for approval."
      );

      refreshActionAlerts();
      await loadBills();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  async function rejectVerification(row) {
    if (!isAdmin) return;

    const reason = window.prompt(
      "Reason for verification rejection:"
    );

    if (!reason) return;

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        `/maintenance-bills/${row.id}/verification-reject`,
        {
          method: "POST",
          body: {
            reason,
          },
        }
      );

      setSuccess(
        "Bill verification rejected."
      );

      refreshActionAlerts();
      await loadBills();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  async function approveBill(row) {
    /*
     * IMPORTANT:
     * ADMIN cannot enter this function.
     */
    if (!isMD) return;

    const note = window.prompt(
      "MD approval remarks (optional):",
      ""
    );

    if (note === null) return;

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        `/maintenance-bills/${row.id}/approve`,
        {
          method: "POST",
          body: {
            note: note || null,
          },
        }
      );

      setSuccess(
        "Maintenance bill approved successfully."
      );

      refreshActionAlerts();
      await loadBills();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  async function rejectByMD(row) {
    if (!isMD) return;

    const reason = window.prompt(
      "Reason for rejecting this bill:"
    );

    if (!reason) return;

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        `/maintenance-bills/${row.id}/reject`,
        {
          method: "POST",
          body: {
            reason,
          },
        }
      );

      setSuccess(
        "Maintenance bill rejected by MD."
      );

      refreshActionAlerts();
      await loadBills();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  async function markPaid(row) {
    if (!isAdmin) return;

    const paymentReference = window.prompt(
      "Enter payment reference / transaction number:"
    );

    if (!paymentReference) return;

    const note = window.prompt(
      "Payment remarks (optional):",
      ""
    );

    if (note === null) return;

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        `/maintenance-bills/${row.id}/mark-paid`,
        {
          method: "POST",

          body: {
            payment_reference:
              paymentReference.trim(),

            note:
              note || null,
          },
        }
      );

      setSuccess(
        "Payment recorded successfully."
      );

      refreshActionAlerts();
      await loadBills();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }


  const related = relatedOptions();


  return (
    <div className="page">
      <header className="page-header">
        <div>
          <span className="eyebrow">
            Finance & Maintenance
          </span>

          <h1>
            Maintenance & Bills
          </h1>

          <p>
            Record maintenance charges and bills,
            verify them through Admin and obtain
            MD approval before payment.
          </p>
        </div>
      </header>


      {success && (
        <div className="success-banner">
          ✅ {success}
        </div>
      )}

      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}


      <div className="action-strip">
        {isAdmin && !showForm && (
          <button
            type="button"
            className="primary-button"
            onClick={startNewBill}
          >
            + Record Maintenance Bill
          </button>
        )}

        {isAdmin && showForm && (
          <button
            type="button"
            className="secondary-button"
            disabled={busy}
            onClick={() => setShowForm(false)}
          >
            Close
          </button>
        )}

        <button
          type="button"
          className="secondary-button"
          disabled={loading || busy}
          onClick={loadBills}
        >
          {loading
            ? "Refreshing…"
            : "Refresh"}
        </button>
      </div>


      {isAdmin && showForm && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>
                Record Maintenance Bill
              </h2>

              <p>
                Upload the original bill or invoice.
                It will be submitted for verification.
              </p>
            </div>
          </div>


          <form
            className="document-form"
            onSubmit={createAndSubmit}
          >
            <div className="form-grid">

              <label>
                Bill Category *

                <select
                  required
                  disabled={busy}
                  value={form.category}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      category: e.target.value,
                    })
                  }
                >
                  {CATEGORIES.map(
                    ([value, label]) => (
                      <option
                        key={value}
                        value={value}
                      >
                        {label}
                      </option>
                    )
                  )}
                </select>
              </label>


              <label>
                Related To *

                <select
                  required
                  disabled={busy}
                  value={form.related_type}
                  onChange={(e) =>
                    changeRelatedType(
                      e.target.value
                    )
                  }
                >
                  {RELATED_TYPES.map(
                    ([value, label]) => (
                      <option
                        key={value}
                        value={value}
                      >
                        {label}
                      </option>
                    )
                  )}
                </select>
              </label>


              {form.related_type !== "GENERAL" && (
                <label>
                  Select {displayCode(form.related_type)} *

                  <select
                    required
                    disabled={busy}
                    value={selectedRelatedId()}
                    onChange={(e) =>
                      setRelatedId(
                        e.target.value
                      )
                    }
                  >
                    <option value="">
                      Select…
                    </option>

                    {related.rows.map((row) => (
                      <option
                        key={row.id}
                        value={row.id}
                      >
                        {optionLabel(
                          row,
                          related.type
                        )}
                      </option>
                    ))}
                  </select>
                </label>
              )}


              <label>
                Existing Vendor

                <select
                  disabled={busy}
                  value={form.vendor_id}
                  onChange={(e) => {
                    const id =
                      e.target.value;

                    const vendor =
                      vendors.find(
                        (v) => v.id === id
                      );

                    setForm({
                      ...form,
                      vendor_id: id,
                      vendor_name:
                        vendor?.name ||
                        form.vendor_name,
                    });
                  }}
                >
                  <option value="">
                    Other / Manual Vendor
                  </option>

                  {vendors.map((vendor) => (
                    <option
                      key={vendor.id}
                      value={vendor.id}
                    >
                      {optionLabel(
                        vendor,
                        "vendor"
                      )}
                    </option>
                  ))}
                </select>
              </label>


              <label>
                Vendor Name *

                <input
                  required
                  disabled={busy}
                  value={form.vendor_name}
                  placeholder="Vendor / service provider"
                  onChange={(e) =>
                    setForm({
                      ...form,
                      vendor_name:
                        e.target.value,
                    })
                  }
                />
              </label>


              <label>
                Invoice / Bill Number

                <input
                  disabled={busy}
                  value={form.invoice_number}
                  placeholder="Example: INV-1024"
                  onChange={(e) =>
                    setForm({
                      ...form,
                      invoice_number:
                        e.target.value,
                    })
                  }
                />
              </label>


              <label>
                Bill Date *

                <DateField
                  type="date"
                  required
                  disabled={busy}
                  value={form.bill_date}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      bill_date:
                        e.target.value,
                    })
                  }
                />
              </label>


              <label>
                Due Date

                <DateField
                  type="date"
                  disabled={busy}
                  value={form.due_date}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      due_date:
                        e.target.value,
                    })
                  }
                />
              </label>


              <label>
                Bill Amount (₹) *

                <input
                  type="number"
                  required
                  min="0.01"
                  step="0.01"
                  disabled={busy}
                  value={form.amount}
                  placeholder="0.00"
                  onChange={(e) =>
                    setForm({
                      ...form,
                      amount:
                        e.target.value,
                    })
                  }
                />
              </label>
            </div>


            <label>
              Description *

              <textarea
                required
                minLength="3"
                maxLength="5000"
                rows="4"
                disabled={busy}
                value={form.description}
                placeholder="Describe the maintenance work, charge or service."
                onChange={(e) =>
                  setForm({
                    ...form,
                    description:
                      e.target.value,
                  })
                }
              />
            </label>


            <label className="file-drop">
              Bill Image / PDF *

              <input
                type="file"
                required
                accept=".pdf,image/*"
                disabled={busy}
                onChange={(e) => {
                  setFile(
                    e.target.files?.[0] ||
                    null
                  );

                  setProgress(0);
                }}
              />

              <span>
                {file
                  ? `${file.name} · ${Math.round(
                      file.size / 1024
                    )} KB`
                  : "Choose original bill image or PDF"}
              </span>
            </label>


            {progress > 0 && (
              <div className="progress-bar">
                <span
                  style={{
                    width: `${progress}%`,
                  }}
                />
              </div>
            )}


            <button
              type="submit"
              className="primary-button"
              disabled={busy}
            >
              {busy
                ? "Uploading & Submitting…"
                : "Record & Submit Bill"}
            </button>
          </form>
        </section>
      )}


      {isMD && (
        <section className="panel" ref={mdQueueRef}>
          <div className="panel-header">
            <div>
              <h2>
                Waiting for MD Approval
              </h2>

              <p>
                Only bills already verified by Admin
                appear here.
              </p>
            </div>
          </div>

          {mdPending.length === 0 ? (
            <div className="empty-state">
              No verified bills awaiting approval.
            </div>
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Vendor</th>
                    <th>Bill</th>
                    <th>Category</th>
                    <th>Amount</th>
                    <th>Bill Proof</th>
                    <th>Verification</th>
                    <th>Action</th>
                  </tr>
                </thead>

                <tbody>
                  {mdPending.map((row) => (
                    <tr key={row.id}>
                      <td>
                        {row.vendor_name}
                      </td>

                      <td>
                        <strong>
                          {row.invoice_number ||
                            "No invoice number"}
                        </strong>

                        <div className="muted">
                          {row.description}
                        </div>
                      </td>

                      <td>
                        {displayCode(
                          row.category
                        )}
                      </td>

                      <td>
                        ₹
                        {Number(
                          row.amount
                        ).toLocaleString(
                          "en-IN",
                          {
                            minimumFractionDigits: 2,
                          }
                        )}
                      </td>

                      <td>
                        {row.bill_document_id ? (
                          <button
                            type="button"
                            className="secondary-button"
                            disabled={previewingId === row.id}
                            onClick={() =>
                              previewBillDocument(row)
                            }
                          >
                            {previewingId === row.id
                              ? "Opening…"
                              : "View Bill / PDF"}
                          </button>
                        ) : (
                          <span className="muted">
                            No attachment
                          </span>
                        )}
                      </td>

                      <td>
                        {row.verification_note ||
                          "Verified by Admin"}
                      </td>

                      <td>
                        <div className="action-strip">
                          <button
                            type="button"
                            className="primary-button"
                            disabled={busy}
                            onClick={() =>
                              approveBill(row)
                            }
                          >
                            Approve
                          </button>

                          <button
                            type="button"
                            className="secondary-button"
                            disabled={busy}
                            onClick={() =>
                              rejectByMD(row)
                            }
                          >
                            Reject
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}


      <section className="panel" ref={registerRef}>
        <div className="panel-header">
          <div>
            <h2>
              Maintenance Bill Register
            </h2>

            <p>
              Complete record of maintenance charges,
              approvals and payment status.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="skeleton-lines" />
        ) : bills.length === 0 ? (
          <div className="empty-state">
            No maintenance bills recorded yet.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Invoice</th>
                  <th>Category</th>
                  <th>Bill Date</th>
                  <th>Amount</th>
                  <th>Bill Proof</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>

              <tbody>
                {bills.map((row) => (
                  <tr key={row.id}>
                    <td>
                      {row.vendor_name}
                    </td>

                    <td>
                      <strong>
                        {row.invoice_number ||
                          "—"}
                      </strong>

                      <div className="muted">
                        {row.description}
                      </div>
                    </td>

                    <td>
                      {displayCode(
                        row.category
                      )}
                    </td>

                    <td>
                      {row.bill_date || "—"}
                    </td>

                    <td>
                      ₹
                      {Number(
                        row.amount
                      ).toLocaleString(
                        "en-IN",
                        {
                          minimumFractionDigits: 2,
                        }
                      )}
                    </td>

                    <td>
                      {row.bill_document_id ? (
                        <button
                          type="button"
                          className="secondary-button"
                          disabled={previewingId === row.id}
                          onClick={() =>
                            previewBillDocument(row)
                          }
                        >
                          {previewingId === row.id
                            ? "Opening…"
                            : "View Bill / PDF"}
                        </button>
                      ) : (
                        <span className="muted">
                          No attachment
                        </span>
                      )}
                    </td>

                    <td>
                      <strong>
                        {displayCode(
                          row.status
                        )}
                      </strong>
                    </td>

                    <td>
                      <div className="action-strip">

                        {isAdmin &&
                          row.status ===
                            "SUBMITTED" && (
                            <>
                              <button
                                type="button"
                                className="primary-button"
                                disabled={busy}
                                onClick={() =>
                                  verifyBill(row)
                                }
                              >
                                Verify
                              </button>

                              <button
                                type="button"
                                className="secondary-button"
                                disabled={busy}
                                onClick={() =>
                                  rejectVerification(
                                    row
                                  )
                                }
                              >
                                Return
                              </button>
                            </>
                          )}


                        {/*
                          Notice there is intentionally
                          NO Admin Approve button here.
                        */}


                        {isMD &&
                          row.status ===
                            "VERIFIED" && (
                            <>
                              <button
                                type="button"
                                className="primary-button"
                                disabled={busy}
                                onClick={() =>
                                  approveBill(row)
                                }
                              >
                                Approve
                              </button>

                              <button
                                type="button"
                                className="secondary-button"
                                disabled={busy}
                                onClick={() =>
                                  rejectByMD(row)
                                }
                              >
                                Reject
                              </button>
                            </>
                          )}


                        {isAdmin &&
                          row.status ===
                            "APPROVED" && (
                            <button
                              type="button"
                              className="primary-button"
                              disabled={busy}
                              onClick={() =>
                                markPaid(row)
                              }
                            >
                              Record Payment
                            </button>
                          )}


                        {!(
                          (isAdmin &&
                            row.status ===
                              "SUBMITTED") ||
                          (isMD &&
                            row.status ===
                              "VERIFIED") ||
                          (isAdmin &&
                            row.status ===
                              "APPROVED")
                        ) && (
                          <span className="muted">
                            —
                          </span>
                        )}

                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
// date-display-ddmmyyyy-v1
