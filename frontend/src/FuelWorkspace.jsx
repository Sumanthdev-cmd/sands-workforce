import { useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, uploadWithProgress } from "./lib/api";

function nowLocalInput() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");

  return (
    `${d.getFullYear()}-` +
    `${pad(d.getMonth() + 1)}-` +
    `${pad(d.getDate())}T` +
    `${pad(d.getHours())}:` +
    `${pad(d.getMinutes())}`
  );
}

function money(value) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "—";
  }

  return `₹${number.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function readableError(error) {
  const value =
    error?.detail ??
    error?.message ??
    error;

  if (typeof value === "string") {
    return value === "[object Object]"
      ? "The request could not be completed. Please check the entered information."
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

function vehicleLabel(vehicle) {
  if (!vehicle) {
    return "Unknown vehicle";
  }

  const registration =
    vehicle.registration_number ||
    vehicle.registration_no ||
    "";

  const code = vehicle.code || "";

  if (registration && code) {
    return `${registration} · ${code}`;
  }

  return (
    registration ||
    code ||
    vehicle.name ||
    vehicle.id ||
    "Vehicle"
  );
}

export default function FuelWorkspace() {
  const [vehicles, setVehicles] = useState([]);
  const [indents, setIndents] = useState([]);
  const [dashboard, setDashboard] = useState([]);

  const [showIndentForm, setShowIndentForm] =
    useState(false);

  const [showFuelForm, setShowFuelForm] =
    useState(false);

  const [indentForm, setIndentForm] = useState({
    vehicle_id: "",
    odometer_km: "",
    requested_quantity_litres: "",
    requested_amount_rupees: "",
    notes: "",
  });

  const [fuelForm, setFuelForm] = useState({
    indent_id: "",
    actual_quantity_litres: "",
    actual_amount_rupees: "",
    fuel_date: nowLocalInput(),
    fuel_station: "",
    bill_number: "",
    notes: "",
  });

  const [receiptFile, setReceiptFile] =
    useState(null);

  const [progress, setProgress] =
    useState(0);

  const [busy, setBusy] =
    useState(false);

  const [loading, setLoading] =
    useState(true);

  const [success, setSuccess] =
    useState("");

  const [error, setError] =
    useState("");

  const submitLock = useRef(false);

  const requestedIndents = useMemo(
    () =>
      indents.filter(
        (row) =>
          String(row.status || "").toUpperCase() ===
          "REQUESTED"
      ),
    [indents]
  );

  const vehicleMap = useMemo(
    () =>
      Object.fromEntries(
        vehicles.map((vehicle) => [
          vehicle.id,
          vehicle,
        ])
      ),
    [vehicles]
  );

  async function load() {
    setLoading(true);
    setError("");

    try {
      const [
        vehiclesResult,
        indentsResult,
        dashboardResult,
      ] = await Promise.allSettled([
        apiRequest("/assets/vehicles"),
        apiRequest("/fuel/indents"),
        apiRequest("/fuel/dashboard"),
      ]);

      setVehicles(
        vehiclesResult.status === "fulfilled" &&
          Array.isArray(vehiclesResult.value)
          ? vehiclesResult.value
          : []
      );

      setIndents(
        indentsResult.status === "fulfilled" &&
          Array.isArray(indentsResult.value)
          ? indentsResult.value
          : []
      );

      setDashboard(
        dashboardResult.status === "fulfilled" &&
          Array.isArray(dashboardResult.value)
          ? dashboardResult.value
          : []
      );

      if (indentsResult.status === "rejected") {
        throw indentsResult.reason;
      }
    } catch (err) {
      setError(readableError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function createIndent(event) {
    event.preventDefault();

    if (submitLock.current) {
      return;
    }

    if (!indentForm.vehicle_id) {
      setError("Please select a vehicle.");
      return;
    }

    if (!(Number(indentForm.odometer_km) > 0)) {
      setError(
        "Odometer reading must be greater than zero."
      );
      return;
    }

    if (
      indentForm.requested_quantity_litres === "" &&
      indentForm.requested_amount_rupees === ""
    ) {
      setError(
        "Enter requested fuel quantity or requested amount."
      );
      return;
    }

    submitLock.current = true;
    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest("/fuel/indents", {
        method: "POST",

        body: {
          vehicle_id:
            indentForm.vehicle_id,

          odometer_km:
            Number(indentForm.odometer_km),

          requested_quantity_litres:
            indentForm.requested_quantity_litres === ""
              ? null
              : Number(
                  indentForm.requested_quantity_litres
                ),

          requested_amount_rupees:
            indentForm.requested_amount_rupees === ""
              ? null
              : Number(
                  indentForm.requested_amount_rupees
                ),

          notes:
            indentForm.notes.trim() ||
            null,
        },
      });

      setSuccess(
        "Fuel indent created successfully."
      );

      setIndentForm({
        vehicle_id: "",
        odometer_km: "",
        requested_quantity_litres: "",
        requested_amount_rupees: "",
        notes: "",
      });

      setShowIndentForm(false);

      await load();
    } catch (err) {
      setError(readableError(err));
    } finally {
      submitLock.current = false;
      setBusy(false);
    }
  }

  async function uploadReceipt(indent) {
    if (!receiptFile) {
      return null;
    }

    const contentType =
      receiptFile.type ||
      "application/octet-stream";

    const title =
      fuelForm.bill_number.trim()
        ? `Fuel receipt ${fuelForm.bill_number.trim()}`
        : `Fuel receipt ${indent.indent_number}`;

    const issueDate =
      fuelForm.fuel_date
        ? fuelForm.fuel_date.slice(0, 10)
        : null;

    const prepared = await apiRequest(
      "/documents/presign-upload",
      {
        method: "POST",

        body: {
          owner_type: "VEHICLE",
          owner_id: indent.vehicle_id,

          category: "FUEL_RECEIPT",

          title,

          description:
            `Fuel receipt for indent ${indent.indent_number}`,

          issue_date: issueDate,
          expiry_date: null,

          alert_days_before: 30,

          is_confidential: true,

          file_name: receiptFile.name,
          content_type: contentType,
          file_size: receiptFile.size,

          extra_data: {
            purpose: "FUEL_RECEIPT",
            fuel_indent_id: indent.id,
            indent_number:
              indent.indent_number,
          },
        },
      }
    );

    const etag =
      await uploadWithProgress(
        prepared.upload_url,
        receiptFile,
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

  async function recordFueling(event) {
    event.preventDefault();

    if (submitLock.current) {
      return;
    }

    const indent =
      indents.find(
        (row) =>
          row.id === fuelForm.indent_id
      );

    if (!indent) {
      setError(
        "Please select a requested fuel indent."
      );
      return;
    }

    const quantity = Number(
      fuelForm.actual_quantity_litres
    );

    const amount = Number(
      fuelForm.actual_amount_rupees
    );

    if (!(quantity > 0)) {
      setError(
        "Actual fuel quantity must be greater than zero."
      );
      return;
    }

    if (!(amount > 0)) {
      setError(
        "Actual fuel amount must be greater than zero."
      );
      return;
    }

    if (!fuelForm.fuel_date) {
      setError(
        "Please select fueling date and time."
      );
      return;
    }

    const localDate =
      new Date(fuelForm.fuel_date);

    if (
      Number.isNaN(
        localDate.getTime()
      )
    ) {
      setError(
        "Fueling date and time is invalid."
      );
      return;
    }

    submitLock.current = true;

    setBusy(true);
    setError("");
    setSuccess("");
    setProgress(0);

    try {
      /*
       * receipt_document_id is never typed by the user.
       * The selected image/PDF is uploaded first, then the generated
       * UUID is sent internally to the fuel endpoint.
       */
      const receiptDocumentId =
        await uploadReceipt(indent);

      await apiRequest(
        `/fuel/indents/${indent.id}/fuel`,
        {
          method: "POST",

          body: {
            actual_quantity_litres:
              quantity,

            actual_amount_rupees:
              amount,

            fuel_date:
              localDate.toISOString(),

            fuel_station:
              fuelForm.fuel_station.trim() ||
              null,

            bill_number:
              fuelForm.bill_number.trim() ||
              null,

            receipt_document_id:
              receiptDocumentId,

            notes:
              fuelForm.notes.trim() ||
              null,
          },
        }
      );

      setSuccess(
        receiptDocumentId
          ? "Fueling recorded successfully and the receipt was uploaded."
          : "Fueling recorded successfully."
      );

      setFuelForm({
        indent_id: "",
        actual_quantity_litres: "",
        actual_amount_rupees: "",
        fuel_date: nowLocalInput(),
        fuel_station: "",
        bill_number: "",
        notes: "",
      });

      setReceiptFile(null);
      setProgress(0);
      setShowFuelForm(false);

      await load();
    } catch (err) {
      setError(readableError(err));
    } finally {
      submitLock.current = false;
      setBusy(false);
    }
  }

  async function cancelIndent(row) {
    if (
      busy ||
      String(
        row.status || ""
      ).toUpperCase() !== "REQUESTED"
    ) {
      return;
    }

    const ok = window.confirm(
      `Cancel fuel indent ${row.indent_number}?`
    );

    if (!ok) {
      return;
    }

    setBusy(true);
    setError("");
    setSuccess("");

    try {
      await apiRequest(
        `/fuel/indents/${row.id}/cancel`,
        {
          method: "POST",
        }
      );

      setSuccess(
        `Fuel indent ${row.indent_number} cancelled.`
      );

      await load();
    } catch (err) {
      setError(readableError(err));
    } finally {
      setBusy(false);
    }
  }

  function openFuelForm(row = null) {
    setError("");
    setSuccess("");
    setProgress(0);
    setReceiptFile(null);

    setFuelForm({
      indent_id: row?.id || "",
      actual_quantity_litres: "",
      actual_amount_rupees: "",
      fuel_date: nowLocalInput(),
      fuel_station: "",
      bill_number: "",
      notes: "",
    });

    setShowFuelForm(true);
    setShowIndentForm(false);
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <span className="eyebrow">
            Vehicle Operations
          </span>

          <h1>
            Fuel & Mileage
          </h1>

          <p>
            Create fuel indents, record actual fueling,
            upload receipts, and monitor vehicle mileage.
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
        <button
          type="button"
          className="primary-button"
          disabled={busy}
          onClick={() => {
            setShowIndentForm(
              !showIndentForm
            );

            setShowFuelForm(false);
            setError("");
            setSuccess("");
          }}
        >
          {showIndentForm
            ? "Close"
            : "Create Fuel Indent"}
        </button>

        <button
          type="button"
          className="secondary-button pending-leave-button"
          disabled={
            busy ||
            requestedIndents.length === 0
          }
          onClick={() =>
            openFuelForm()
          }
        >
          Record Fueling

          {requestedIndents.length > 0 && (
            <span className="pending-leave-badge">
              {requestedIndents.length > 99
                ? "99+"
                : requestedIndents.length}
            </span>
          )}
        </button>

        <button
          type="button"
          className="secondary-button"
          disabled={
            loading || busy
          }
          onClick={load}
        >
          {loading
            ? "Refreshing…"
            : "Refresh"}
        </button>
      </div>

      {showIndentForm && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>
                Create Fuel Indent
              </h2>

              <p>
                Select the vehicle instead of entering an internal UUID.
              </p>
            </div>
          </div>

          <form
            className="document-form"
            onSubmit={createIndent}
          >
            <div className="form-grid">
              <label>
                Vehicle *

                <select
                  required
                  disabled={busy}
                  value={
                    indentForm.vehicle_id
                  }
                  onChange={(event) =>
                    setIndentForm({
                      ...indentForm,
                      vehicle_id:
                        event.target.value,
                    })
                  }
                >
                  <option value="">
                    Select vehicle…
                  </option>

                  {vehicles.map(
                    (vehicle) => (
                      <option
                        key={vehicle.id}
                        value={vehicle.id}
                      >
                        {vehicleLabel(
                          vehicle
                        )}
                      </option>
                    )
                  )}
                </select>
              </label>

              <label>
                Odometer Reading (km) *

                <input
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  disabled={busy}
                  value={
                    indentForm.odometer_km
                  }
                  onChange={(event) =>
                    setIndentForm({
                      ...indentForm,
                      odometer_km:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Requested Fuel (litres)

                <input
                  type="number"
                  min="0.001"
                  step="0.001"
                  disabled={busy}
                  value={
                    indentForm.requested_quantity_litres
                  }
                  onChange={(event) =>
                    setIndentForm({
                      ...indentForm,
                      requested_quantity_litres:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Requested Amount (₹)

                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  disabled={busy}
                  value={
                    indentForm.requested_amount_rupees
                  }
                  onChange={(event) =>
                    setIndentForm({
                      ...indentForm,
                      requested_amount_rupees:
                        event.target.value,
                    })
                  }
                />
              </label>
            </div>

            <label>
              Notes

              <textarea
                rows="3"
                disabled={busy}
                value={indentForm.notes}
                onChange={(event) =>
                  setIndentForm({
                    ...indentForm,
                    notes:
                      event.target.value,
                  })
                }
              />
            </label>

            <button
              className="primary-button"
              disabled={busy}
            >
              {busy
                ? "Creating…"
                : "Create Fuel Indent"}
            </button>
          </form>
        </section>
      )}

      {showFuelForm && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>
                Record Fueling
              </h2>

              <p>
                Select a requested indent and optionally upload the
                fuel receipt image or PDF. Receipt Document ID is
                handled automatically.
              </p>
            </div>
          </div>

          <form
            className="document-form"
            onSubmit={recordFueling}
          >
            <div className="form-grid">
              <label>
                Requested Fuel Indent *

                <select
                  required
                  disabled={busy}
                  value={
                    fuelForm.indent_id
                  }
                  onChange={(event) =>
                    setFuelForm({
                      ...fuelForm,
                      indent_id:
                        event.target.value,
                    })
                  }
                >
                  <option value="">
                    Select requested indent…
                  </option>

                  {requestedIndents.map(
                    (row) => {
                      const vehicle =
                        vehicleMap[
                          row.vehicle_id
                        ];

                      return (
                        <option
                          key={row.id}
                          value={row.id}
                        >
                          {row.indent_number}
                          {" · "}
                          {vehicleLabel(
                            vehicle
                          )}
                          {" · "}
                          {row.odometer_km}
                          {" km"}
                        </option>
                      );
                    }
                  )}
                </select>
              </label>

              <label>
                Fuel Date & Time *

                <input
                  required
                  type="datetime-local"
                  disabled={busy}
                  value={
                    fuelForm.fuel_date
                  }
                  onChange={(event) =>
                    setFuelForm({
                      ...fuelForm,
                      fuel_date:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Actual Quantity (litres) *

                <input
                  required
                  type="number"
                  min="0.001"
                  step="0.001"
                  disabled={busy}
                  value={
                    fuelForm.actual_quantity_litres
                  }
                  onChange={(event) =>
                    setFuelForm({
                      ...fuelForm,
                      actual_quantity_litres:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Actual Amount (₹) *

                <input
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  disabled={busy}
                  value={
                    fuelForm.actual_amount_rupees
                  }
                  onChange={(event) =>
                    setFuelForm({
                      ...fuelForm,
                      actual_amount_rupees:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Fuel Station

                <input
                  disabled={busy}
                  value={
                    fuelForm.fuel_station
                  }
                  onChange={(event) =>
                    setFuelForm({
                      ...fuelForm,
                      fuel_station:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Bill Number

                <input
                  disabled={busy}
                  value={
                    fuelForm.bill_number
                  }
                  onChange={(event) =>
                    setFuelForm({
                      ...fuelForm,
                      bill_number:
                        event.target.value,
                    })
                  }
                />
              </label>
            </div>

            <label className="file-drop">
              Fuel Receipt / Bill

              <small className="muted">
                Optional image or PDF
              </small>

              <input
                type="file"
                accept=".pdf,image/*"
                disabled={busy}
                onChange={(event) => {
                  setReceiptFile(
                    event.target.files?.[0] ||
                      null
                  );

                  setProgress(0);
                }}
              />

              <span>
                {receiptFile
                  ? `${receiptFile.name} · ${Math.round(
                      receiptFile.size / 1024
                    )} KB`
                  : "Choose receipt image or PDF"}
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

            <label>
              Notes

              <textarea
                rows="3"
                disabled={busy}
                value={fuelForm.notes}
                onChange={(event) =>
                  setFuelForm({
                    ...fuelForm,
                    notes:
                      event.target.value,
                  })
                }
              />
            </label>

            <button
              className="primary-button"
              disabled={busy}
            >
              {busy
                ? receiptFile
                  ? "Uploading & Recording…"
                  : "Recording…"
                : "Record Fueling"}
            </button>
          </form>
        </section>
      )}

      <section className="panel">
        <div className="panel-header">
          <div>
            <span className="eyebrow">
              Mileage
            </span>

            <h2>
              Vehicle Fuel Summary
            </h2>
          </div>
        </div>

        {dashboard.length === 0 ? (
          <div className="empty-state">
            No vehicle mileage summary available yet.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vehicle</th>
                  <th>Expected</th>
                  <th>Latest Actual</th>
                  <th>Average Actual</th>
                  <th>Status</th>
                  <th>Month Fuel</th>
                  <th>Month Cost</th>
                  <th>Cost / km</th>
                </tr>
              </thead>

              <tbody>
                {dashboard.map(
                  (row) => (
                    <tr
                      key={
                        row.vehicle_id
                      }
                    >
                      <td>
                        <strong>
                          {row.registration_number}
                        </strong>

                        <div className="muted">
                          {row.vehicle_code}
                          {row.make
                            ? ` · ${row.make}`
                            : ""}
                          {row.model
                            ? ` ${row.model}`
                            : ""}
                        </div>
                      </td>

                      <td>
                        {row.expected_mileage_kmpl ??
                          "—"}
                        {row.expected_mileage_kmpl !=
                          null
                          ? " km/L"
                          : ""}
                      </td>

                      <td>
                        {row.latest_actual_mileage_kmpl ??
                          "—"}
                        {row.latest_actual_mileage_kmpl !=
                          null
                          ? " km/L"
                          : ""}
                      </td>

                      <td>
                        {row.average_actual_mileage_kmpl ??
                          "—"}
                        {row.average_actual_mileage_kmpl !=
                          null
                          ? " km/L"
                          : ""}
                      </td>

                      <td>
                        {String(
                          row.mileage_status ||
                            "—"
                        ).replaceAll(
                          "_",
                          " "
                        )}
                      </td>

                      <td>
                        {row.current_month_fuel_litres ??
                          0}
                        {" L"}
                      </td>

                      <td>
                        {money(
                          row.current_month_fuel_amount_rupees ??
                            0
                        )}
                      </td>

                      <td>
                        {row.average_cost_per_km !=
                        null
                          ? money(
                              row.average_cost_per_km
                            )
                          : "—"}
                      </td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>
              Fuel Indents & History
            </h2>

            <p>
              Requested, fueled and cancelled vehicle fuel records.
            </p>
          </div>

          <span className="muted">
            {indents.length} records
          </span>
        </div>

        {loading ? (
          <div className="skeleton-lines" />
        ) : indents.length === 0 ? (
          <div className="empty-state">
            No fuel indents found.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Indent</th>
                  <th>Vehicle</th>
                  <th>Status</th>
                  <th>Odometer</th>
                  <th>Fuel</th>
                  <th>Amount</th>
                  <th>Mileage</th>
                  <th>Bill</th>
                  <th>Action</th>
                </tr>
              </thead>

              <tbody>
                {indents.map(
                  (row) => {
                    const vehicle =
                      vehicleMap[
                        row.vehicle_id
                      ];

                    const requested =
                      String(
                        row.status || ""
                      ).toUpperCase() ===
                      "REQUESTED";

                    return (
                      <tr
                        key={row.id}
                      >
                        <td>
                          <strong>
                            {row.indent_number}
                          </strong>

                          <div className="muted">
                            {row.fuel_date
                              ? new Date(
                                  row.fuel_date
                                ).toLocaleString()
                              : "Not fueled"}
                          </div>
                        </td>

                        <td>
                          {vehicleLabel(
                            vehicle
                          )}
                        </td>

                        <td>
                          {String(
                            row.status ||
                              "—"
                          ).replaceAll(
                            "_",
                            " "
                          )}
                        </td>

                        <td>
                          {row.odometer_km ??
                            "—"}{" "}
                          km
                        </td>

                        <td>
                          {row.actual_quantity_litres ??
                            row.requested_quantity_litres ??
                            "—"}

                          {(row.actual_quantity_litres !=
                            null ||
                            row.requested_quantity_litres !=
                              null) &&
                            " L"}
                        </td>

                        <td>
                          {row.actual_amount_rupees !=
                          null
                            ? money(
                                row.actual_amount_rupees
                              )
                            : row.requested_amount_rupees !=
                                null
                              ? money(
                                  row.requested_amount_rupees
                                )
                              : "—"}
                        </td>

                        <td>
                          {row.actual_mileage_kmpl !=
                          null
                            ? `${row.actual_mileage_kmpl} km/L`
                            : "—"}

                          {row.mileage_status && (
                            <div className="muted">
                              {String(
                                row.mileage_status
                              ).replaceAll(
                                "_",
                                " "
                              )}
                            </div>
                          )}
                        </td>

                        <td>
                          {row.bill_number ||
                            "—"}
                        </td>

                        <td>
                          {requested ? (
                            <div className="action-strip">
                              <button
                                type="button"
                                className="primary-button"
                                disabled={busy}
                                onClick={() =>
                                  openFuelForm(
                                    row
                                  )
                                }
                              >
                                Record
                              </button>

                              <button
                                type="button"
                                className="secondary-button"
                                disabled={busy}
                                onClick={() =>
                                  cancelIndent(
                                    row
                                  )
                                }
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <span className="muted">
                              —
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  }
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
