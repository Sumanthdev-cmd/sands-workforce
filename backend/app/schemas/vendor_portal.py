from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class VendorPortalLoginRequest(BaseModel):
    organization_code: str = Field(min_length=2, max_length=50)
    vendor_code: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("organization_code", "vendor_code")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class VendorPortalTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    force_password_change: bool
    organization_code: str
    vendor_code: str
    vendor_name: str


class VendorPortalChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_must_differ(self):
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from the current password.")
        return self


class VendorPortalAdminCreateRequest(BaseModel):
    vendor_id: UUID
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)


class VendorPortalAdminResetPasswordRequest(BaseModel):
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)


class VendorPortalAccountResponse(BaseModel):
    id: UUID
    vendor_id: UUID
    organization_code: str
    vendor_code: str
    vendor_name: str
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str
    force_password_change: bool
    last_login_at: datetime | None = None
    created_at: datetime
    temporary_password: str | None = None


class VendorPortalMeResponse(BaseModel):
    organization_code: str
    vendor_code: str
    vendor_name: str
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str
    force_password_change: bool
    last_login_at: datetime | None = None


class VendorPortalDashboardResponse(BaseModel):
    outlet_count: int
    document_count: int
    pending_inspection_count: int
    unread_notification_count: int


class VendorPortalOutletResponse(BaseModel):
    id: UUID
    code: str
    name: str
    outlet_type: str | None = None
    cluster_name: str | None = None
    address: str
    latitude: float | None = None
    longitude: float | None = None
    attendance_radius_meters: float = 150
    vendor_contact_person: str | None = None
    vendor_phone: str | None = None
    vendor_email: str | None = None
    licence_number: str | None = None
    licence_expiry_date: date | None = None
    excise_licence_number: str | None = None
    excise_expiry_date: date | None = None
    rent_agreement_expiry_date: date | None = None
    status: str | None = None
    is_active: bool


class VendorAttendanceActionRequest(BaseModel):
    outlet_id: UUID
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, ge=0, le=10000)


class VendorAttendanceResponse(BaseModel):
    id: UUID
    vendor_id: UUID
    vendor_code: str
    vendor_name: str
    outlet_id: UUID
    outlet_code: str
    outlet_name: str
    attendance_date: date
    status: str
    check_in_at: datetime
    check_out_at: datetime | None = None
    check_in_latitude: float
    check_in_longitude: float
    check_in_accuracy_meters: float | None = None
    check_in_distance_meters: float
    check_out_latitude: float | None = None
    check_out_longitude: float | None = None
    check_out_accuracy_meters: float | None = None
    check_out_distance_meters: float | None = None
    worked_minutes: int
    late_minutes: int = 0


class VendorPortalDocumentResponse(BaseModel):
    id: UUID
    outlet_id: UUID
    outlet_code: str
    outlet_name: str
    category: str
    title: str
    description: str | None = None
    file_name: str
    content_type: str
    file_size: int | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    status: str
    created_at: datetime


class VendorPortalDownloadResponse(BaseModel):
    document_id: UUID
    download_url: str
    expires_in_seconds: int


class VendorPortalInspectionSummary(BaseModel):
    id: UUID
    report_number: str
    version: int
    outlet_code: str
    outlet_name: str
    outlet_address: str
    inspector_code: str | None = None
    inspector_name: str | None = None
    inspection_started_at: datetime
    submitted_at: datetime | None = None
    status: str
    attention_flag_count: int
    vendor_response: str | None = None
    vendor_remarks: str | None = None
    vendor_responded_at: datetime | None = None


class VendorPortalInspectionDetail(VendorPortalInspectionSummary):
    cluster_name: str | None = None
    template_snapshot: dict
    answers: dict
    section_remarks: dict
    attention_flags: list
    inspector_signature_data_uri: str | None = None
    vendor_signature_data_uri: str | None = None


class VendorPortalInspectionResponseRequest(BaseModel):
    response: str
    remarks: str | None = Field(default=None, max_length=5000)
    signature_data_uri: str | None = None

    @field_validator("response")
    @classmethod
    def normalize_response(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"ACCEPT", "DISPUTE"}:
            raise ValueError("response must be ACCEPT or DISPUTE")
        return value

    @field_validator("signature_data_uri")
    @classmethod
    def validate_signature(cls, value: str | None):
        if value in {None, ""}:
            return None
        if not value.startswith(("data:image/png;base64,", "data:image/jpeg;base64,")):
            raise ValueError("Signature must be a PNG/JPEG data URL.")
        if len(value) > 600_000:
            raise ValueError("Signature image is too large.")
        return value

    @model_validator(mode="after")
    def dispute_requires_remarks(self):
        if self.response == "DISPUTE" and len((self.remarks or "").strip()) < 3:
            raise ValueError("Remarks are required when disputing the inspection report.")
        return self


class VendorPortalNotificationResponse(BaseModel):
    id: UUID
    title: str
    body: str
    payload: dict | None = None
    read_at: datetime | None = None
    created_at: datetime
