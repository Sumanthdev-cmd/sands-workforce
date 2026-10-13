from datetime import date, datetime
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


OWNER_TYPES = {
    "ACCOUNT_SHEET",
    "EMPLOYEE",
    "VEHICLE",
    "PROPERTY",
    "OUTLET",
    "EXPENSE",
    "MD_REFERENCE",
    "GENERAL",
    "SHOP_RENTAL",
    "VENDOR",
}


class DocumentUploadRequest(BaseModel):
    owner_type: str
    owner_id: UUID | None = None
    category: str = Field(min_length=2, max_length=60)
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=150)
    file_size: int | None = Field(default=None, ge=1, le=50_000_000)
    issue_date: date | None = None
    expiry_date: date | None = None
    alert_days_before: int = Field(default=30, ge=0, le=3650)
    is_confidential: bool = False
    extra_data: dict | None = None

    @field_validator("owner_type", "category")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("owner_type")
    @classmethod
    def validate_owner_type(cls, value: str) -> str:
        if value not in OWNER_TYPES:
            raise ValueError(
                f"owner_type must be one of {sorted(OWNER_TYPES)}"
            )
        return value

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.issue_date is not None
            and self.expiry_date is not None
            and self.expiry_date < self.issue_date
        ):
            raise ValueError("expiry_date cannot be earlier than issue_date.")
        return self


class PresignedUploadResponse(BaseModel):
    document_id: UUID
    upload_url: str
    upload_headers: dict[str, str]
    expires_in_seconds: int
    s3_key: str


class DocumentCompleteRequest(BaseModel):
    etag: str | None = Field(default=None, max_length=200)


class DocumentVerifyRequest(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class DocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: str | None = Field(default=None, min_length=2, max_length=60)
    issue_date: date | None = None
    expiry_date: date | None = None
    alert_days_before: int | None = Field(default=None, ge=0, le=3650)
    is_confidential: bool | None = None
    status: str | None = Field(default=None, max_length=30)
    extra_data: dict | None = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_type: str
    owner_id: UUID | None
    category: str
    title: str
    description: str | None
    file_name: str
    content_type: str
    file_size: int | None
    s3_bucket: str
    s3_key: str
    etag: str | None
    issue_date: date | None
    expiry_date: date | None
    alert_days_before: int
    status: str
    is_confidential: bool
    uploaded_by_user_id: UUID
    verified_by_user_id: UUID | None
    verified_at: datetime | None
    verification_note: str | None
    extra_data: dict | None
    created_at: datetime
    updated_at: datetime


class PresignedDownloadResponse(BaseModel):
    document_id: UUID
    download_url: str
    expires_in_seconds: int
