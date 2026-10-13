from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviceRegisterRequest(BaseModel):
    """Device details submitted by the authenticated employee."""

    device_identifier: str = Field(min_length=3, max_length=255)
    platform: str = Field(default="ANDROID", min_length=2, max_length=20)
    device_name: str | None = Field(default=None, max_length=150)
    manufacturer: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    os_version: str | None = Field(default=None, max_length=50)
    app_version: str | None = Field(default=None, max_length=50)
    fcm_token: str | None = None

    @field_validator("device_identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip()

    @field_validator("platform")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        return value.strip().upper()


class FcmTokenUpdateRequest(BaseModel):
    """A replacement Firebase Cloud Messaging token."""

    fcm_token: str = Field(min_length=10)


class DeviceResponse(BaseModel):
    """Safe registered-device response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employee_id: UUID
    device_identifier: str
    platform: str
    device_name: str | None
    manufacturer: str | None
    model: str | None
    os_version: str | None
    app_version: str | None
    is_active: bool
    is_primary: bool
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
