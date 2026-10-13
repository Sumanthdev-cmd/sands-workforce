from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import get_settings


settings = get_settings()

password_hasher = PasswordHash.recommended()

TokenType = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """A newly issued JWT with tracking information."""

    token: str
    jti: str
    expires_at: datetime


def hash_password(password: str) -> str:
    """Hash a plain-text password."""

    if not password:
        raise ValueError("Password cannot be empty.")

    return password_hasher.hash(password)


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """Verify a plain password against a stored password hash."""

    if not plain_password or not password_hash:
        return False

    try:
        return password_hasher.verify(
            plain_password,
            password_hash,
        )
    except Exception:
        return False


def _create_token(
    *,
    subject: UUID | str,
    token_type: TokenType,
    expires_delta: timedelta,
) -> IssuedToken:
    """Create a signed JSON Web Token."""

    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + expires_delta
    token_jti = str(uuid4())

    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "jti": token_jti,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }

    encoded_token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return IssuedToken(
        token=encoded_token,
        jti=token_jti,
        expires_at=expires_at,
    )


def create_access_token(
    subject: UUID | str,
) -> IssuedToken:
    """Create a short-lived access token."""

    return _create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(
            minutes=settings.access_token_expire_minutes,
        ),
    )


def create_refresh_token(
    subject: UUID | str,
) -> IssuedToken:
    """Create a longer-lived refresh token."""

    return _create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(
            days=settings.refresh_token_expire_days,
        ),
    )


def decode_token(
    token: str,
    expected_type: TokenType | None = None,
) -> dict[str, Any]:
    """Validate and decode a JSON Web Token."""

    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )

    if expected_type is not None:
        actual_type = payload.get("type")

        if actual_type != expected_type:
            raise InvalidTokenError(
                f"Expected {expected_type} token."
            )

    return payload