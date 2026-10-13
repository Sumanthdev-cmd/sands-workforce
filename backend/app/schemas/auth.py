from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    """Credentials used to authenticate a user."""

    organization_code: str = Field(
        min_length=2,
        max_length=40,
        examples=["SANDS"],
    )
    employee_code: str = Field(
        min_length=2,
        max_length=50,
        examples=["ADMIN001"],
    )
    password: str = Field(
        min_length=1,
        max_length=128,
    )

    @field_validator(
        "organization_code",
        "employee_code",
    )
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return value.strip().upper()


class RefreshRequest(BaseModel):
    """Refresh token submitted for token rotation."""

    refresh_token: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    """Refresh token that should be revoked."""

    refresh_token: str = Field(min_length=20)


class ChangePasswordRequest(BaseModel):
    """Current and replacement passwords."""

    current_password: str = Field(
        min_length=1,
        max_length=128,
    )
    new_password: str = Field(
        min_length=10,
        max_length=128,
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not any(character.isupper() for character in value):
            raise ValueError(
                "Password must contain an uppercase letter."
            )

        if not any(character.islower() for character in value):
            raise ValueError(
                "Password must contain a lowercase letter."
            )

        if not any(character.isdigit() for character in value):
            raise ValueError(
                "Password must contain a number."
            )

        if value.isalnum():
            raise ValueError(
                "Password must contain a special character."
            )

        return value


class TokenResponse(BaseModel):
    """Access and refresh tokens returned after authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    must_change_password: bool


class CurrentUserResponse(BaseModel):
    """Information about the authenticated user."""

    id: UUID
    organization_id: UUID
    organization_code: str
    employee_code: str
    email: str | None
    is_superuser: bool
    must_change_password: bool
    roles: list[str]
    permissions: list[str]


class MessageResponse(BaseModel):
    """Standard message response."""

    message: str