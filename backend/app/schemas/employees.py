from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


EMPLOYMENT_TYPES = {
    "FULL_TIME",
    "PART_TIME",
    "CONTRACT",
    "TEMPORARY",
    "INTERN",
}

SEPARATION_TYPES = {
    "RESIGNED",
    "REMOVED",
    "DISABLED",
}


def validate_strong_password(value: str) -> str:
    """Validate a temporary password before it reaches the service layer."""

    if not any(character.isupper() for character in value):
        raise ValueError("Password must contain an uppercase letter.")

    if not any(character.islower() for character in value):
        raise ValueError("Password must contain a lowercase letter.")

    if not any(character.isdigit() for character in value):
        raise ValueError("Password must contain a number.")

    if value.isalnum():
        raise ValueError("Password must contain a special character.")

    return value


class EmployeeCreate(BaseModel):
    """Data required to create a login user and employee profile."""

    employee_code: str = Field(min_length=2, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    temporary_password: str = Field(min_length=10, max_length=128)

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    bank_name: str | None = Field(default=None, max_length=180)
    bank_ifsc: str | None = Field(default=None, max_length=20)
    bank_account_number: str | None = Field(default=None, max_length=40)
    date_of_joining: date
    employment_type: str = "FULL_TIME"
    is_field_employee: bool = False

    department_id: UUID | None = None
    designation_id: UUID | None = None
    manager_id: UUID | None = None
    role_codes: list[str] = Field(
        default_factory=lambda: ["EMPLOYEE"],
        min_length=1,
    )

    @field_validator("employee_code")
    @classmethod
    def normalize_employee_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().lower()
        return normalized or None

    @field_validator("first_name")
    @classmethod
    def normalize_first_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("last_name", "phone", "bank_name", "bank_account_number")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("bank_ifsc")
    @classmethod
    def normalize_ifsc(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("employment_type")
    @classmethod
    def validate_employment_type(cls, value: str) -> str:
        normalized = value.strip().upper()

        if normalized not in EMPLOYMENT_TYPES:
            raise ValueError(
                f"Employment type must be one of: "
                f"{', '.join(sorted(EMPLOYMENT_TYPES))}."
            )

        return normalized

    @field_validator("role_codes")
    @classmethod
    def normalize_role_codes(cls, values: list[str]) -> list[str]:
        normalized = sorted(
            {
                value.strip().upper()
                for value in values
                if value.strip()
            }
        )

        if not normalized:
            raise ValueError("At least one role is required.")

        return normalized

    @field_validator("temporary_password")
    @classmethod
    def validate_temporary_password(cls, value: str) -> str:
        return validate_strong_password(value)


class EmployeeUpdate(BaseModel):
    """Editable employee and login fields."""

    employee_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=50,
    )
    email: str | None = Field(default=None, max_length=255)

    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    last_name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    bank_name: str | None = Field(default=None, max_length=180)
    bank_ifsc: str | None = Field(default=None, max_length=20)
    bank_account_number: str | None = Field(default=None, max_length=40)
    date_of_joining: date | None = None
    employment_type: str | None = None
    is_field_employee: bool | None = None

    department_id: UUID | None = None
    designation_id: UUID | None = None
    manager_id: UUID | None = None

    @field_validator("employee_code")
    @classmethod
    def normalize_employee_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().lower()
        return normalized or None

    @field_validator("first_name")
    @classmethod
    def normalize_first_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("last_name", "phone", "bank_name", "bank_account_number")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("bank_ifsc")
    @classmethod
    def normalize_ifsc(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("employment_type")
    @classmethod
    def validate_employment_type(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().upper()

        if normalized not in EMPLOYMENT_TYPES:
            raise ValueError(
                f"Employment type must be one of: "
                f"{', '.join(sorted(EMPLOYMENT_TYPES))}."
            )

        return normalized


class EmployeeRoleUpdate(BaseModel):
    """Replacement role list for an employee."""

    role_codes: list[str] = Field(min_length=1)

    @field_validator("role_codes")
    @classmethod
    def normalize_role_codes(cls, values: list[str]) -> list[str]:
        normalized = sorted(
            {
                value.strip().upper()
                for value in values
                if value.strip()
            }
        )

        if not normalized:
            raise ValueError("At least one role is required.")

        return normalized


class EmployeePasswordReset(BaseModel):
    """New temporary password assigned by an administrator."""

    temporary_password: str = Field(min_length=10, max_length=128)

    @field_validator("temporary_password")
    @classmethod
    def validate_temporary_password(cls, value: str) -> str:
        return validate_strong_password(value)


class EmployeeDisableRequest(BaseModel):
    """Separation information required before disabling an employee."""

    last_working_day: date
    separation_type: str = Field(default="RESIGNED", max_length=30)
    reason: str | None = Field(default=None, max_length=5000)

    @field_validator("separation_type")
    @classmethod
    def validate_separation_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in SEPARATION_TYPES:
            raise ValueError(
                "Separation type must be RESIGNED, REMOVED or DISABLED."
            )
        return normalized

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class NamedEntitySummary(BaseModel):
    """Compact department or designation information."""

    id: UUID
    code: str
    name: str


class EmployeeResponse(BaseModel):
    """Employee information returned by the API."""

    id: UUID
    user_id: UUID
    organization_id: UUID

    employee_code: str
    email: str | None
    user_is_active: bool
    must_change_password: bool

    first_name: str
    last_name: str | None
    full_name: str
    phone: str | None
    bank_name: str | None
    bank_ifsc: str | None
    bank_account_number: str | None
    date_of_joining: date
    employment_type: str
    employment_status: str
    last_working_day: date | None
    separation_type: str | None
    separation_reason: str | None
    is_field_employee: bool

    department: NamedEntitySummary | None
    designation: NamedEntitySummary | None
    manager_id: UUID | None
    role_codes: list[str]
