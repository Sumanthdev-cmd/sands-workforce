from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InspectionCreateRequest(BaseModel):
    outlet_id: UUID
    visit_assignment_id: UUID | None = None
    vendor_id: UUID | None = None
    task_assignment_id: UUID | None = None
    cluster_name: str | None = Field(default=None, max_length=180)


class InspectionRotationAssignRequest(BaseModel):
    outlet_id: UUID
    scheduled_for: date


class InspectionRotationManualOverrideRequest(BaseModel):
    outlet_id: UUID
    scheduled_for: date
    employee_id: UUID
    reason: str = Field(min_length=5, max_length=2000)


class InspectionVisitCancelRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class InspectionDraftUpdateRequest(BaseModel):
    answers: dict = Field(default_factory=dict)
    section_remarks: dict = Field(default_factory=dict)


class InspectionSubmitRequest(BaseModel):
    answers: dict
    section_remarks: dict = Field(default_factory=dict)
    inspector_signature_data_uri: str | None = None

    @field_validator("inspector_signature_data_uri")
    @classmethod
    def validate_signature(cls, value):
        if value is None or value == "":
            return None
        if not value.startswith(("data:image/png;base64,", "data:image/jpeg;base64,")):
            raise ValueError("Signature must be a PNG/JPEG data URL.")
        if len(value) > 600_000:
            raise ValueError("Signature image is too large.")
        return value


class VendorInspectionResponseRequest(BaseModel):
    response: str
    vendor_name: str = Field(min_length=2, max_length=180)
    remarks: str | None = Field(default=None, max_length=5000)
    signature_data_uri: str | None = None

    @field_validator("response")
    @classmethod
    def normalize_response(cls, value):
        value = value.strip().upper()
        if value not in {"ACCEPT", "DISPUTE"}:
            raise ValueError("response must be ACCEPT or DISPUTE")
        return value

    @field_validator("signature_data_uri")
    @classmethod
    def validate_signature(cls, value):
        if value is None or value == "":
            return None
        if not value.startswith(("data:image/png;base64,", "data:image/jpeg;base64,")):
            raise ValueError("Signature must be a PNG/JPEG data URL.")
        if len(value) > 600_000:
            raise ValueError("Signature image is too large.")
        return value

    @model_validator(mode="after")
    def dispute_requires_remarks(self):
        if self.response == "DISPUTE" and not (self.remarks or "").strip():
            raise ValueError("Remarks are required when disputing the report.")
        return self


class HoAcknowledgeRequest(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class InspectionTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    title: str
    version: int
    schema_data: dict


class InspectionReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_number: str
    version: int
    previous_report_id: UUID | None
    outlet_id: UUID
    outlet_name: str | None
    outlet_code: str | None
    outlet_address: str | None
    vendor_id: UUID | None
    task_assignment_id: UUID | None
    inspector_employee_id: UUID
    inspector_user_id: UUID
    cluster_name: str | None
    inspection_started_at: datetime
    start_latitude: float | None
    start_longitude: float | None
    start_accuracy_meters: float | None
    start_distance_meters: float | None
    location_verified_at: datetime | None
    submitted_at: datetime | None
    ho_received_at: datetime | None
    ho_acknowledged_at: datetime | None
    ho_acknowledgement_note: str | None
    template_snapshot: dict
    answers: dict
    section_remarks: dict
    attention_flags: list
    status: str
    inspector_signature_data_uri: str | None
    vendor_name_snapshot: str | None
    vendor_contact_name: str | None
    vendor_contact_email: str | None
    vendor_contact_phone: str | None
    vendor_opened_at: datetime | None
    vendor_response: str | None
    vendor_response_name: str | None
    vendor_remarks: str | None
    vendor_signature_data_uri: str | None
    vendor_responded_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class InspectionSubmitResponse(BaseModel):
    report: InspectionReportResponse
    vendor_review_url: str
    vendor_notification_status: str


class VendorPublicReportResponse(BaseModel):
    report_number: str
    version: int
    outlet_name: str
    outlet_address: str
    cluster_name: str | None
    inspector_name: str
    inspection_started_at: datetime
    submitted_at: datetime | None
    template_snapshot: dict
    answers: dict
    section_remarks: dict
    attention_flags: list
    status: str
    vendor_name: str | None
    vendor_response: str | None
    vendor_response_name: str | None
    vendor_remarks: str | None
    vendor_responded_at: datetime | None
    inspector_signature_data_uri: str | None
    vendor_signature_data_uri: str | None


class InspectionDashboardResponse(BaseModel):
    counts: dict[str, int]
    attention_reports: list[InspectionReportResponse]
