from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DepartmentCreate(BaseModel):
    """Data required to create a department."""

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class DepartmentUpdate(BaseModel):
    """Fields that can be changed on a department."""

    code: str | None = Field(default=None, min_length=2, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class DepartmentResponse(BaseModel):
    """Department data returned by the API."""

    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool


class DesignationCreate(BaseModel):
    """Data required to create a designation."""

    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class DesignationUpdate(BaseModel):
    """Fields that can be changed on a designation."""

    code: str | None = Field(default=None, min_length=2, max_length=40)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class DesignationResponse(BaseModel):
    """Designation data returned by the API."""

    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool


class RoleSummary(BaseModel):
    """Role option returned for employee assignment."""

    id: UUID
    code: str
    name: str
    description: str | None
    is_active: bool
