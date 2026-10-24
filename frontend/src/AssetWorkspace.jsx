import DateField from "./DateField";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, uploadWithProgress } from "./lib/api";

const VEHICLE_DOC_TYPES = [
  {
    key: "registration_certificate",
    category: "VEHICLE_RC",
    label: "Registration Certificate (RC)",
    expiryField: "registration_expiry_date",
  },
  {
    key: "insurance",
    category: "VEHICLE_INSURANCE",
    label: "Insurance",
    expiryField: "insurance_expiry_date",
  },
  {
    key: "pollution",
    category: "VEHICLE_PUC",
    label: "PUC / Emission Certificate",
    expiryField: "pollution_expiry_date",
  },
  {
    key: "fitness",
    category: "VEHICLE_FITNESS",
    label: "Fitness Certificate",
    extraExpiryKey: "fitness_expiry_date",
  },
  {
    key: "permit",
    category: "VEHICLE_PERMIT",
    label: "Permit",
    extraExpiryKey: "permit_expiry_date",
  },
  {
    key: "road_tax",
    category: "VEHICLE_ROAD_TAX",
    label: "Road Tax Receipt",
    extraExpiryKey: "road_tax_expiry_date",
  },
  {
    key: "purchase_invoice",
    category: "VEHICLE_PURCHASE_INVOICE",
    label: "Purchase Invoice",
  },
  {
    key: "other",
    category: "VEHICLE_OTHER",
    label: "Other Vehicle Document",
  },
];

const PROPERTY_DOC_TYPES = [
  {
    key: "title_deed",
    category: "PROPERTY_TITLE_DEED",
    label: "Title / Sale Deed",
  },
  {
    key: "tax_receipt",
    category: "PROPERTY_TAX_RECEIPT",
    label: "Property Tax Receipt",
    expiryField: "next_tax_due_date",
  },
  {
    key: "approved_plan",
    category: "PROPERTY_APPROVED_PLAN",
    label: "Approved Building / Property Plan",
  },
  {
    key: "insurance",
    category: "PROPERTY_INSURANCE",
    label: "Property Insurance",
    extraExpiryKey: "property_insurance_expiry_date",
  },
  {
    key: "agreement",
    category: "PROPERTY_AGREEMENT",
    label: "Lease / Rent / Property Agreement",
    extraExpiryKey: "property_agreement_expiry_date",
  },
  {
    key: "other",
    category: "PROPERTY_OTHER",
    label: "Other Property Document",
  },
];

function emptyVehicleForm() {
  return {
    code: "",
    registration_number: "",
    ownership_type: "COMPANY",
    employee_owner_id: "",
    vehicle_type: "",
    make: "",
    model: "",
    fuel_type: "",
    expected_mileage_kmpl: "",
    manufacture_year: "",
    insurance_expiry_date: "",
    registration_expiry_date: "",
    pollution_expiry_date: "",
    notes: "",
    fitness_expiry_date: "",
    permit_expiry_date: "",
    road_tax_expiry_date: "",
  };
}

function emptyPropertyForm() {
  return {
    code: "",
    name: "",
    property_type: "",
    address: "",
    tax_identifier: "",
    last_tax_paid_date: "",
    next_tax_due_date: "",
    notes: "",
    property_insurance_expiry_date: "",
    property_agreement_expiry_date: "",
  };
}

function blankFileMap(types) {
  return Object.fromEntries(
    types.map((item) => [item.key, null])
  );
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

function employeeLabel(employee) {
  if (!employee) return "Employee";

  const code =
    employee.employee_code ||
    employee.user?.employee_code ||
    "";

  const name =
    employee.full_name ||
    [employee.first_name, employee.last_name]
      .filter(Boolean)
      .join(" ");

  if (code && name) return `${code} · ${name}`;
  return code || name || employee.id;
}

function documentTitle(ownerLabel, label) {
  return `${ownerLabel} - ${label}`;
}

function formatDate(value) {
  if (!value) return "—";
  return String(value).slice(0, 10);
}

function daysClass(severity) {
  const value = String(severity || "").toUpperCase();
  if (value === "EXPIRED" || value === "CRITICAL") return "error-banner";
  if (value === "HIGH") return "warning-banner";
  return "success-banner";
}

function DocumentSelection({
  types,
  files,
  setFiles,
  form,
  setForm,
  busy,
  progress,
}) {
  return (
    <div className="asset-document-grid">
      {types.map((type) => {
        const expiryValue = type.expiryField
          ? form[type.expiryField] || ""
          : type.extraExpiryKey
            ? form[type.extraExpiryKey] || ""
            : "";

        return (
          <article className="asset-document-card" key={type.key}>
            <div>
              <strong>{type.label}</strong>
              <p className="muted">
                {type.expiryField || type.extraExpiryKey
                  ? "Upload image/PDF and record expiry when applicable."
                  : "Optional supporting document."}
              </p>
            </div>

            <label className="file-drop compact-file-drop">
              Choose file
              <input
                type="file"
                accept=".pdf,image/*"
                disabled={busy}
                onChange={(event) =>
                  setFiles({
                    ...files,
                    [type.key]:
                      event.target.files?.[0] || null,
                  })
                }
              />
              <span>
                {files[type.key]
                  ? `${files[type.key].name} · ${Math.round(
                      files[type.key].size / 1024
                    )} KB`
                  : "No file selected"}
              </span>
            </label>

            {(type.expiryField || type.extraExpiryKey) && (
              <label>
                Expiry / Due Date
                <DateField
                  type="date"
                  disabled={busy}
                  value={expiryValue}
                  onChange={(event) => {
                    const key =
                      type.expiryField ||
                      type.extraExpiryKey;

                    setForm({
                      ...form,
                      [key]: event.target.value,
                    });
                  }}
                />
              </label>
            )}

            {progress[type.key] > 0 && (
              <div className="progress-bar">
                <span
                  style={{
                    width: `${progress[type.key]}%`,
                  }}
                />
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

export default function AssetWorkspace() {
  const [vehicles, setVehicles] = useState([]);
  const [properties, setProperties] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [renewals, setRenewals] = useState([]);
  const [documents, setDocuments] = useState([]);

  const [vehicleForm, setVehicleForm] =
    useState(emptyVehicleForm);

  const [propertyForm, setPropertyForm] =
    useState(emptyPropertyForm);

  const [vehicleFiles, setVehicleFiles] =
    useState(() => blankFileMap(VEHICLE_DOC_TYPES));

  const [propertyFiles, setPropertyFiles] =
    useState(() => blankFileMap(PROPERTY_DOC_TYPES));

  const [vehicleProgress, setVehicleProgress] =
    useState({});

  const [propertyProgress, setPropertyProgress] =
    useState({});

  const [showVehicleForm, setShowVehicleForm] =
    useState(false);

  const [showPropertyForm, setShowPropertyForm] =
    useState(false);

  const [manageTarget, setManageTarget] =
    useState(null);

  const [manageForm, setManageForm] = useState({
    category: "",
    title: "",
    issue_date: "",
    expiry_date: "",
    description: "",
  });

  const [manageFile, setManageFile] =
    useState(null);

  const [manageProgress, setManageProgress] =
    useState(0);

  const [loading, setLoading] =
    useState(true);

  const [busy, setBusy] =
    useState(false);

  const [success, setSuccess] =
    useState("");

  const [error, setError] =
    useState("");

  const submitLock = useRef(false);

  async function load() {
    setLoading(true);
    setError("");

    const [
      vehicleResult,
      propertyResult,
      employeeResult,
      renewalResult,
      documentResult,
    ] = await Promise.allSettled([
      apiRequest("/assets/vehicles"),
      apiRequest("/assets/properties"),
      apiRequest("/employees"),
      apiRequest("/assets/renewals/upcoming?days=90"),
      apiRequest("/documents"),
    ]);

    setVehicles(
      vehicleResult.status === "fulfilled" &&
        Array.isArray(vehicleResult.value)
        ? vehicleResult.value
        : []
    );

    setProperties(
      propertyResult.status === "fulfilled" &&
        Array.isArray(propertyResult.value)
        ? propertyResult.value
        : []
    );

    setEmployees(
      employeeResult.status === "fulfilled" &&
        Array.isArray(employeeResult.value)
        ? employeeResult.value
        : []
    );

    setRenewals(
      renewalResult.status === "fulfilled" &&
        Array.isArray(renewalResult.value)
        ? renewalResult.value
        : []
    );

    setDocuments(
      documentResult.status === "fulfilled" &&
        Array.isArray(documentResult.value)
        ? documentResult.value
        : []
    );

    if (vehicleResult.status === "rejected") {
      setError(readableError(vehicleResult.reason));
    } else if (propertyResult.status === "rejected") {
      setError(readableError(propertyResult.reason));
    }

    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  async function uploadOneDocument({
    ownerType,
    ownerId,
    ownerLabel,
    type,
    file,
    issueDate = null,
    expiryDate = null,
    description = "",
    onProgress,
  }) {
    const contentType =
      file.type || "application/octet-stream";

    const prepared = await apiRequest(
      "/documents/presign-upload",
      {
        method: "POST",

        body: {
          owner_type: ownerType,
          owner_id: ownerId,
          category: type.category,
          title: documentTitle(
            ownerLabel,
            type.label
          ),
          description:
            description ||
            `${type.label} for ${ownerLabel}`,
          issue_date: issueDate || null,
          expiry_date: expiryDate || null,
          alert_days_before: 30,
          is_confidential: true,
          file_name: file.name,
          content_type: contentType,
          file_size: file.size,
          extra_data: {
            asset_document: true,
            document_label: type.label,
          },
        },
      }
    );

    const etag = await uploadWithProgress(
      prepared.upload_url,
      file,
      contentType,
      onProgress
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

    return prepared.document_id;
  }

  async function uploadVehicleDocuments(vehicle) {
    const selected =
      VEHICLE_DOC_TYPES.filter(
        (type) => vehicleFiles[type.key]
      );

    const failed = [];

    for (const type of selected) {
      try {
        const expiryDate = type.expiryField
          ? vehicleForm[type.expiryField] || null
          : type.extraExpiryKey
            ? vehicleForm[type.extraExpiryKey] || null
            : null;

        await uploadOneDocument({
          ownerType: "VEHICLE",
          ownerId: vehicle.id,
          ownerLabel: vehicle.registration_number,
          type,
          file: vehicleFiles[type.key],
          expiryDate,
          description:
            `${type.label} for vehicle ${vehicle.registration_number}`,
          onProgress: (value) =>
            setVehicleProgress((current) => ({
              ...current,
              [type.key]: value,
            })),
        });
      } catch (err) {
        failed.push(`${type.label}: ${readableError(err)}`);
      }
    }

    return failed;
  }

  async function uploadPropertyDocuments(property) {
    const selected =
      PROPERTY_DOC_TYPES.filter(
        (type) => propertyFiles[type.key]
      );

    const failed = [];

    for (const type of selected) {
      try {
        const expiryDate = type.expiryField
          ? propertyForm[type.expiryField] || null
          : type.extraExpiryKey
            ? propertyForm[type.extraExpiryKey] || null
            : null;

        await uploadOneDocument({
          ownerType: "PROPERTY",
          ownerId: property.id,
          ownerLabel: property.name,
          type,
          file: propertyFiles[type.key],
          expiryDate,
          description:
            `${type.label} for property ${property.name}`,
          onProgress: (value) =>
            setPropertyProgress((current) => ({
              ...current,
              [type.key]: value,
            })),
        });
      } catch (err) {
        failed.push(`${type.label}: ${readableError(err)}`);
      }
    }

    return failed;
  }

  async function createVehicle(event) {
    event.preventDefault();

    if (submitLock.current) return;

    if (
      vehicleForm.ownership_type === "EMPLOYEE" &&
      !vehicleForm.employee_owner_id
    ) {
      setError(
        "Please select the employee owner."
      );
      return;
    }

    submitLock.current = true;
    setBusy(true);
    setError("");
    setSuccess("");
    setVehicleProgress({});

    try {
      const vehicle = await apiRequest(
        "/assets/vehicles",
        {
          method: "POST",
          body: {
            code: vehicleForm.code
              .trim()
              .toUpperCase(),

            registration_number:
              vehicleForm.registration_number
                .trim()
                .toUpperCase(),

            ownership_type:
              vehicleForm.ownership_type,

            employee_owner_id:
              vehicleForm.ownership_type === "EMPLOYEE"
                ? vehicleForm.employee_owner_id
                : null,

            vehicle_type:
              vehicleForm.vehicle_type.trim(),

            make:
              vehicleForm.make.trim() ||
              null,

            model:
              vehicleForm.model.trim() ||
              null,

            fuel_type:
              vehicleForm.fuel_type.trim(),

            expected_mileage_kmpl:
              Number(
                vehicleForm.expected_mileage_kmpl
              ),

            manufacture_year:
              vehicleForm.manufacture_year === ""
                ? null
                : Number(
                    vehicleForm.manufacture_year
                  ),

            insurance_expiry_date:
              vehicleForm.insurance_expiry_date ||
              null,

            registration_expiry_date:
              vehicleForm.registration_expiry_date ||
              null,

            pollution_expiry_date:
              vehicleForm.pollution_expiry_date ||
              null,

            notes:
              vehicleForm.notes.trim() ||
              null,

            extra_data: null,
          },
        }
      );

      const failed =
        await uploadVehicleDocuments(vehicle);

      if (failed.length) {
        setSuccess(
          `Vehicle ${vehicle.registration_number} was created, but some documents need to be uploaded again.`
        );

        setError(failed.join(" | "));
      } else {
        const count =
          VEHICLE_DOC_TYPES.filter(
            (type) =>
              vehicleFiles[type.key]
          ).length;

        setSuccess(
          count
            ? `Vehicle ${vehicle.registration_number} created successfully with ${count} document${count === 1 ? "" : "s"}.`
            : `Vehicle ${vehicle.registration_number} created successfully.`
        );
      }

      setVehicleForm(emptyVehicleForm());
      setVehicleFiles(
        blankFileMap(VEHICLE_DOC_TYPES)
      );
      setVehicleProgress({});
      setShowVehicleForm(false);

      await load();
    } catch (err) {
      setError(readableError(err));
    } finally {
      submitLock.current = false;
      setBusy(false);
    }
  }

  async function createProperty(event) {
    event.preventDefault();

    if (submitLock.current) return;

    submitLock.current = true;
    setBusy(true);
    setError("");
    setSuccess("");
    setPropertyProgress({});

    try {
      const property = await apiRequest(
        "/assets/properties",
        {
          method: "POST",
          body: {
            code:
              propertyForm.code
                .trim()
                .toUpperCase(),

            name:
              propertyForm.name.trim(),

            property_type:
              propertyForm.property_type
                .trim()
                .toUpperCase(),

            address:
              propertyForm.address.trim(),

            tax_identifier:
              propertyForm.tax_identifier
                .trim() || null,

            last_tax_paid_date:
              propertyForm.last_tax_paid_date ||
              null,

            next_tax_due_date:
              propertyForm.next_tax_due_date ||
              null,

            notes:
              propertyForm.notes.trim() ||
              null,

            extra_data: null,
          },
        }
      );

      const failed =
        await uploadPropertyDocuments(property);

      if (failed.length) {
        setSuccess(
          `Property ${property.name} was created, but some documents need to be uploaded again.`
        );

        setError(failed.join(" | "));
      } else {
        const count =
          PROPERTY_DOC_TYPES.filter(
            (type) =>
              propertyFiles[type.key]
          ).length;

        setSuccess(
          count
            ? `Property ${property.name} created successfully with ${count} document${count === 1 ? "" : "s"}.`
            : `Property ${property.name} created successfully.`
        );
      }

      setPropertyForm(emptyPropertyForm());
      setPropertyFiles(
        blankFileMap(PROPERTY_DOC_TYPES)
      );
      setPropertyProgress({});
      setShowPropertyForm(false);

      await load();
    } catch (err) {
      setError(readableError(err));
    } finally {
      submitLock.current = false;
      setBusy(false);
    }
  }

  function openManageDocuments(
    ownerType,
    row
  ) {
    const label =
      ownerType === "VEHICLE"
        ? row.registration_number
        : row.name;

    setManageTarget({
      ownerType,
      ownerId: row.id,
      label,
    });

    setManageForm({
      category:
        ownerType === "VEHICLE"
          ? "VEHICLE_OTHER"
          : "PROPERTY_OTHER",

      title: "",
      issue_date: "",
      expiry_date: "",
      description: "",
    });

    setManageFile(null);
    setManageProgress(0);
    setError("");
    setSuccess("");
  }

  async function uploadManagedDocument(event) {
    event.preventDefault();

    if (!manageTarget || !manageFile) {
      setError(
        "Please select a document file."
      );
      return;
    }

    if (submitLock.current) return;

    submitLock.current = true;
    setBusy(true);
    setError("");
    setSuccess("");
    setManageProgress(0);

    try {
      const label =
        manageForm.title.trim() ||
        manageForm.category
          .replaceAll("_", " ");

      await uploadOneDocument({
        ownerType:
          manageTarget.ownerType,

        ownerId:
          manageTarget.ownerId,

        ownerLabel:
          manageTarget.label,

        type: {
          category:
            manageForm.category,
          label,
        },

        file:
          manageFile,

        issueDate:
          manageForm.issue_date ||
          null,

        expiryDate:
          manageForm.expiry_date ||
          null,

        description:
          manageForm.description.trim(),

        onProgress:
          setManageProgress,
      });

      setSuccess(
        `Document uploaded successfully for ${manageTarget.label}.`
      );

      setManageFile(null);
      setManageProgress(0);

      setManageForm({
        ...manageForm,
        title: "",
        issue_date: "",
        expiry_date: "",
        description: "",
      });

      await load();
    } catch (err) {
      setError(readableError(err));
    } finally {
      submitLock.current = false;
      setBusy(false);
    }
  }

  const managedDocuments = useMemo(() => {
    if (!manageTarget) return [];

    return documents.filter(
      (document) =>
        String(
          document.owner_type || ""
        ).toUpperCase() ===
          manageTarget.ownerType &&
        String(document.owner_id || "") ===
          String(manageTarget.ownerId)
    );
  }, [documents, manageTarget]);

  const manageCategories =
    manageTarget?.ownerType === "VEHICLE"
      ? VEHICLE_DOC_TYPES
      : PROPERTY_DOC_TYPES;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <span className="eyebrow">
            Assets & Compliance
          </span>

          <h1>
            Properties & Vehicles
          </h1>

          <p>
            Maintain company vehicles and properties,
            upload their supporting documents, and track
            expiry and renewal dates.
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
            setShowVehicleForm(
              !showVehicleForm
            );
            setShowPropertyForm(false);
            setManageTarget(null);
            setError("");
            setSuccess("");
          }}
        >
          {showVehicleForm
            ? "Close"
            : "Add Vehicle"}
        </button>

        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          onClick={() => {
            setShowPropertyForm(
              !showPropertyForm
            );
            setShowVehicleForm(false);
            setManageTarget(null);
            setError("");
            setSuccess("");
          }}
        >
          {showPropertyForm
            ? "Close"
            : "Add Property"}
        </button>

        <button
          type="button"
          className="secondary-button"
          disabled={loading || busy}
          onClick={load}
        >
          {loading
            ? "Refreshing…"
            : "Refresh"}
        </button>
      </div>

      {showVehicleForm && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">
                Vehicle
              </span>

              <h2>
                Add Vehicle & Documents
              </h2>

              <p>
                Save the vehicle first; selected files are
                then linked to the generated vehicle ID automatically.
              </p>
            </div>
          </div>

          <form
            className="document-form"
            onSubmit={createVehicle}
          >
            <div className="form-grid">
              <label>
                Vehicle Code *
                <input
                  required
                  minLength="2"
                  maxLength="40"
                  disabled={busy}
                  value={vehicleForm.code}
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      code:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Registration Number *
                <input
                  required
                  minLength="3"
                  maxLength="50"
                  disabled={busy}
                  value={
                    vehicleForm.registration_number
                  }
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      registration_number:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Ownership Type *
                <select
                  required
                  disabled={busy}
                  value={
                    vehicleForm.ownership_type
                  }
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      ownership_type:
                        event.target.value,
                      employee_owner_id:
                        event.target.value ===
                        "EMPLOYEE"
                          ? vehicleForm.employee_owner_id
                          : "",
                    })
                  }
                >
                  <option value="COMPANY">
                    Company
                  </option>
                  <option value="EMPLOYEE">
                    Employee Owned
                  </option>
                </select>
              </label>

              {vehicleForm.ownership_type ===
                "EMPLOYEE" && (
                <label>
                  Employee Owner *
                  <select
                    required
                    disabled={busy}
                    value={
                      vehicleForm.employee_owner_id
                    }
                    onChange={(event) =>
                      setVehicleForm({
                        ...vehicleForm,
                        employee_owner_id:
                          event.target.value,
                      })
                    }
                  >
                    <option value="">
                      Select employee…
                    </option>
                    {employees.map(
                      (employee) => (
                        <option
                          key={employee.id}
                          value={employee.id}
                        >
                          {employeeLabel(
                            employee
                          )}
                        </option>
                      )
                    )}
                  </select>
                </label>
              )}

              <label>
                Vehicle Type *
                <input
                  required
                  minLength="2"
                  maxLength="50"
                  disabled={busy}
                  placeholder="Car, Van, Bike, Truck..."
                  value={
                    vehicleForm.vehicle_type
                  }
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      vehicle_type:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Fuel Type *
                <input
                  required
                  minLength="2"
                  maxLength="30"
                  disabled={busy}
                  placeholder="Petrol, Diesel, EV..."
                  value={
                    vehicleForm.fuel_type
                  }
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      fuel_type:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Make
                <input
                  disabled={busy}
                  value={vehicleForm.make}
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      make:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Model
                <input
                  disabled={busy}
                  value={vehicleForm.model}
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      model:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Expected Mileage (km/L) *
                <input
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  disabled={busy}
                  value={
                    vehicleForm.expected_mileage_kmpl
                  }
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      expected_mileage_kmpl:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Manufacture Year
                <input
                  type="number"
                  min="1900"
                  max="2200"
                  disabled={busy}
                  value={
                    vehicleForm.manufacture_year
                  }
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      manufacture_year:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Registration Expiry
                <DateField
                  type="date"
                  disabled={busy}
                  value={
                    vehicleForm.registration_expiry_date
                  }
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      registration_expiry_date:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Insurance Expiry
                <DateField
                  type="date"
                  disabled={busy}
                  value={
                    vehicleForm.insurance_expiry_date
                  }
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      insurance_expiry_date:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                PUC / Emission Expiry
                <DateField
                  type="date"
                  disabled={busy}
                  value={
                    vehicleForm.pollution_expiry_date
                  }
                  onChange={(event) =>
                    setVehicleForm({
                      ...vehicleForm,
                      pollution_expiry_date:
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
                value={vehicleForm.notes}
                onChange={(event) =>
                  setVehicleForm({
                    ...vehicleForm,
                    notes:
                      event.target.value,
                  })
                }
              />
            </label>

            <div>
              <span className="eyebrow">
                Vehicle Documents
              </span>
              <h3>
                Upload related documents
              </h3>
              <p className="muted">
                All files are optional during creation.
                Expiring documents will automatically participate
                in the renewal alert system.
              </p>
            </div>

            <DocumentSelection
              types={VEHICLE_DOC_TYPES}
              files={vehicleFiles}
              setFiles={setVehicleFiles}
              form={vehicleForm}
              setForm={setVehicleForm}
              busy={busy}
              progress={vehicleProgress}
            />

            <button
              className="primary-button"
              disabled={busy}
            >
              {busy
                ? "Saving Vehicle & Documents…"
                : "Save Vehicle & Documents"}
            </button>
          </form>
        </section>
      )}

      {showPropertyForm && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">
                Property
              </span>

              <h2>
                Add Property & Documents
              </h2>

              <p>
                Store property details and link supporting
                documents to the new property automatically.
              </p>
            </div>
          </div>

          <form
            className="document-form"
            onSubmit={createProperty}
          >
            <div className="form-grid">
              <label>
                Property Code *
                <input
                  required
                  minLength="2"
                  maxLength="40"
                  disabled={busy}
                  value={propertyForm.code}
                  onChange={(event) =>
                    setPropertyForm({
                      ...propertyForm,
                      code:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Property Name *
                <input
                  required
                  minLength="2"
                  maxLength="180"
                  disabled={busy}
                  value={propertyForm.name}
                  onChange={(event) =>
                    setPropertyForm({
                      ...propertyForm,
                      name:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Property Type *
                <input
                  required
                  minLength="2"
                  maxLength="50"
                  disabled={busy}
                  placeholder="Office, Land, Building..."
                  value={
                    propertyForm.property_type
                  }
                  onChange={(event) =>
                    setPropertyForm({
                      ...propertyForm,
                      property_type:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Tax Identifier
                <input
                  disabled={busy}
                  value={
                    propertyForm.tax_identifier
                  }
                  onChange={(event) =>
                    setPropertyForm({
                      ...propertyForm,
                      tax_identifier:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Last Tax Paid Date
                <DateField
                  type="date"
                  disabled={busy}
                  value={
                    propertyForm.last_tax_paid_date
                  }
                  onChange={(event) =>
                    setPropertyForm({
                      ...propertyForm,
                      last_tax_paid_date:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Next Tax Due Date
                <DateField
                  type="date"
                  disabled={busy}
                  value={
                    propertyForm.next_tax_due_date
                  }
                  onChange={(event) =>
                    setPropertyForm({
                      ...propertyForm,
                      next_tax_due_date:
                        event.target.value,
                    })
                  }
                />
              </label>
            </div>

            <label>
              Address *
              <textarea
                required
                minLength="3"
                rows="4"
                disabled={busy}
                value={propertyForm.address}
                onChange={(event) =>
                  setPropertyForm({
                    ...propertyForm,
                    address:
                      event.target.value,
                  })
                }
              />
            </label>

            <label>
              Notes
              <textarea
                rows="3"
                disabled={busy}
                value={propertyForm.notes}
                onChange={(event) =>
                  setPropertyForm({
                    ...propertyForm,
                    notes:
                      event.target.value,
                  })
                }
              />
            </label>

            <div>
              <span className="eyebrow">
                Property Documents
              </span>
              <h3>
                Upload related documents
              </h3>
              <p className="muted">
                Tax, insurance and agreement expiry dates can
                automatically feed the document renewal alerts.
              </p>
            </div>

            <DocumentSelection
              types={PROPERTY_DOC_TYPES}
              files={propertyFiles}
              setFiles={setPropertyFiles}
              form={propertyForm}
              setForm={setPropertyForm}
              busy={busy}
              progress={propertyProgress}
            />

            <button
              className="primary-button"
              disabled={busy}
            >
              {busy
                ? "Saving Property & Documents…"
                : "Save Property & Documents"}
            </button>
          </form>
        </section>
      )}

      {manageTarget && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <span className="eyebrow">
                Document Manager
              </span>
              <h2>
                {manageTarget.label}
              </h2>
              <p>
                Upload additional documents without entering
                the asset UUID manually.
              </p>
            </div>

            <button
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() =>
                setManageTarget(null)
              }
            >
              Close
            </button>
          </div>

          <form
            className="document-form"
            onSubmit={uploadManagedDocument}
          >
            <div className="form-grid">
              <label>
                Document Type *
                <select
                  required
                  disabled={busy}
                  value={manageForm.category}
                  onChange={(event) =>
                    setManageForm({
                      ...manageForm,
                      category:
                        event.target.value,
                    })
                  }
                >
                  {manageCategories.map(
                    (type) => (
                      <option
                        key={type.category}
                        value={type.category}
                      >
                        {type.label}
                      </option>
                    )
                  )}
                </select>
              </label>

              <label>
                Custom Title
                <input
                  disabled={busy}
                  value={manageForm.title}
                  onChange={(event) =>
                    setManageForm({
                      ...manageForm,
                      title:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Issue Date
                <DateField
                  type="date"
                  disabled={busy}
                  value={
                    manageForm.issue_date
                  }
                  onChange={(event) =>
                    setManageForm({
                      ...manageForm,
                      issue_date:
                        event.target.value,
                    })
                  }
                />
              </label>

              <label>
                Expiry / Renewal Date
                <DateField
                  type="date"
                  disabled={busy}
                  value={
                    manageForm.expiry_date
                  }
                  onChange={(event) =>
                    setManageForm({
                      ...manageForm,
                      expiry_date:
                        event.target.value,
                    })
                  }
                />
              </label>
            </div>

            <label>
              Description
              <textarea
                rows="3"
                disabled={busy}
                value={
                  manageForm.description
                }
                onChange={(event) =>
                  setManageForm({
                    ...manageForm,
                    description:
                      event.target.value,
                  })
                }
              />
            </label>

            <label className="file-drop">
              Document File *
              <input
                required
                type="file"
                accept=".pdf,image/*"
                disabled={busy}
                onChange={(event) => {
                  setManageFile(
                    event.target.files?.[0] ||
                      null
                  );
                  setManageProgress(0);
                }}
              />
              <span>
                {manageFile
                  ? `${manageFile.name} · ${Math.round(
                      manageFile.size / 1024
                    )} KB`
                  : "Choose image or PDF"}
              </span>
            </label>

            {manageProgress > 0 && (
              <div className="progress-bar">
                <span
                  style={{
                    width: `${manageProgress}%`,
                  }}
                />
              </div>
            )}

            <button
              className="primary-button"
              disabled={busy}
            >
              {busy
                ? "Uploading…"
                : "Upload Document"}
            </button>
          </form>

          <div className="asset-document-list">
            <h3>
              Linked Documents
            </h3>

            {managedDocuments.length === 0 ? (
              <div className="empty-state">
                No linked documents found.
              </div>
            ) : (
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th>Title</th>
                      <th>Issue Date</th>
                      <th>Expiry Date</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {managedDocuments.map(
                      (document) => (
                        <tr key={document.id}>
                          <td>
                            {String(
                              document.category ||
                                "—"
                            ).replaceAll(
                              "_",
                              " "
                            )}
                          </td>
                          <td>
                            {document.title ||
                              "—"}
                          </td>
                          <td>
                            {formatDate(
                              document.issue_date
                            )}
                          </td>
                          <td>
                            {formatDate(
                              document.expiry_date
                            )}
                          </td>
                          <td>
                            {document.status ||
                              "—"}
                          </td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>
              Vehicles
            </h2>
            <p>
              Company and employee-owned vehicle register.
            </p>
          </div>
          <span className="muted">
            {vehicles.length} records
          </span>
        </div>

        {loading ? (
          <div className="skeleton-lines" />
        ) : vehicles.length === 0 ? (
          <div className="empty-state">
            No vehicles found.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Vehicle</th>
                  <th>Type</th>
                  <th>Ownership</th>
                  <th>Expected Mileage</th>
                  <th>Registration Expiry</th>
                  <th>Insurance Expiry</th>
                  <th>PUC Expiry</th>
                  <th>Documents</th>
                </tr>
              </thead>

              <tbody>
                {vehicles.map(
                  (vehicle) => (
                    <tr key={vehicle.id}>
                      <td>
                        <strong>
                          {vehicle.registration_number}
                        </strong>
                        <div className="muted">
                          {vehicle.code}
                          {vehicle.make
                            ? ` · ${vehicle.make}`
                            : ""}
                          {vehicle.model
                            ? ` ${vehicle.model}`
                            : ""}
                        </div>
                      </td>

                      <td>
                        {vehicle.vehicle_type}
                      </td>

                      <td>
                        {String(
                          vehicle.ownership_type ||
                            "—"
                        ).replaceAll(
                          "_",
                          " "
                        )}
                      </td>

                      <td>
                        {vehicle.expected_mileage_kmpl ??
                          "—"}
                        {vehicle.expected_mileage_kmpl !=
                          null
                          ? " km/L"
                          : ""}
                      </td>

                      <td>
                        {formatDate(
                          vehicle.registration_expiry_date
                        )}
                      </td>

                      <td>
                        {formatDate(
                          vehicle.insurance_expiry_date
                        )}
                      </td>

                      <td>
                        {formatDate(
                          vehicle.pollution_expiry_date
                        )}
                      </td>

                      <td>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() =>
                            openManageDocuments(
                              "VEHICLE",
                              vehicle
                            )
                          }
                        >
                          Manage Documents
                        </button>
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
              Properties
            </h2>
            <p>
              Property register, tax dates and linked documents.
            </p>
          </div>

          <span className="muted">
            {properties.length} records
          </span>
        </div>

        {loading ? (
          <div className="skeleton-lines" />
        ) : properties.length === 0 ? (
          <div className="empty-state">
            No properties found.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Property</th>
                  <th>Type</th>
                  <th>Tax ID</th>
                  <th>Last Tax Paid</th>
                  <th>Next Tax Due</th>
                  <th>Status</th>
                  <th>Documents</th>
                </tr>
              </thead>

              <tbody>
                {properties.map(
                  (property) => (
                    <tr key={property.id}>
                      <td>
                        <strong>
                          {property.name}
                        </strong>
                        <div className="muted">
                          {property.code}
                        </div>
                      </td>

                      <td>
                        {String(
                          property.property_type ||
                            "—"
                        ).replaceAll(
                          "_",
                          " "
                        )}
                      </td>

                      <td>
                        {property.tax_identifier ||
                          "—"}
                      </td>

                      <td>
                        {formatDate(
                          property.last_tax_paid_date
                        )}
                      </td>

                      <td>
                        {formatDate(
                          property.next_tax_due_date
                        )}
                      </td>

                      <td>
                        {property.status ||
                          "—"}
                      </td>

                      <td>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() =>
                            openManageDocuments(
                              "PROPERTY",
                              property
                            )
                          }
                        >
                          Manage Documents
                        </button>
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
            <span className="eyebrow">
              Compliance
            </span>
            <h2>
              Upcoming Renewals
            </h2>
            <p>
              Vehicle, property and uploaded-document renewals
              due within the next 90 days.
            </p>
          </div>

          <span className="muted">
            {renewals.length} items
          </span>
        </div>

        {renewals.length === 0 ? (
          <div className="empty-state">
            No renewals are due within 90 days.
          </div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Record</th>
                  <th>Renewal</th>
                  <th>Due Date</th>
                  <th>Days</th>
                  <th>Severity</th>
                </tr>
              </thead>

              <tbody>
                {renewals.map(
                  (item, index) => (
                    <tr
                      key={`${item.source_type}-${item.source_id}-${item.renewal_type}-${index}`}
                    >
                      <td>
                        {item.source_type}
                      </td>
                      <td>
                        <strong>
                          {item.title}
                        </strong>
                        <div className="muted">
                          {item.code}
                        </div>
                      </td>
                      <td>
                        {String(
                          item.renewal_type ||
                            "—"
                        ).replaceAll(
                          "_",
                          " "
                        )}
                      </td>
                      <td>
                        {formatDate(
                          item.due_date
                        )}
                      </td>
                      <td>
                        {item.days_remaining}
                      </td>
                      <td>
                        <span
                          className={`asset-severity ${daysClass(
                            item.severity
                          )}`}
                        >
                          {item.severity}
                        </span>
                      </td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
// date-display-ddmmyyyy-v1
