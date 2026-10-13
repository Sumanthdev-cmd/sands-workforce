from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, Request, status
from jwt import InvalidTokenError
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import (
    Organization,
    RefreshToken,
    Role,
    User,
)


settings = get_settings()


@dataclass(frozen=True, slots=True)
class TokenPair:
    """Access and refresh tokens returned by the service."""

    access_token: str
    refresh_token: str
    expires_in: int
    must_change_password: bool


def unauthorized_exception(
    detail: str = "Invalid authentication credentials.",
) -> HTTPException:
    """Create a standard authentication exception."""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_request_metadata(
    request: Request,
) -> tuple[str | None, str | None]:
    """Return the requesting IP address and user agent."""

    ip_address = (
        request.client.host
        if request.client is not None
        else None
    )

    user_agent = request.headers.get("user-agent")

    return ip_address, user_agent


def load_user_by_id(
    database: Session,
    user_id: UUID,
) -> User | None:
    """Load a user with organization, roles and permissions."""

    statement = (
        select(User)
        .options(
            selectinload(User.organization),
            selectinload(User.roles).selectinload(
                Role.permissions
            ),
        )
        .where(User.id == user_id)
    )

    return database.scalar(statement)


def authenticate_user(
    database: Session,
    *,
    organization_code: str,
    employee_code: str,
    password: str,
) -> User:
    """Validate organization code, employee code and password."""

    statement = (
        select(User)
        .join(
            Organization,
            User.organization_id == Organization.id,
        )
        .options(
            selectinload(User.organization),
            selectinload(User.roles).selectinload(
                Role.permissions
            ),
        )
        .where(
            Organization.code == organization_code,
            User.employee_code == employee_code,
        )
    )

    user = database.scalar(statement)

    if user is None:
        raise unauthorized_exception()

    if not user.organization.is_active:
        raise unauthorized_exception(
            "The organization is inactive."
        )

    if not user.is_active:
        raise unauthorized_exception(
            "The user account is disabled."
        )

    if not verify_password(
        password,
        user.password_hash,
    ):
        raise unauthorized_exception()

    return user


def issue_login_tokens(
    database: Session,
    *,
    user: User,
    request: Request,
) -> TokenPair:
    """Issue and store tokens after a successful login."""

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    ip_address, user_agent = get_request_metadata(request)

    token_record = RefreshToken(
        user_id=user.id,
        jti=refresh_token.jti,
        expires_at=refresh_token.expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    user.last_login_at = datetime.now(timezone.utc)

    database.add(token_record)
    database.commit()

    return TokenPair(
        access_token=access_token.token,
        refresh_token=refresh_token.token,
        expires_in=(
            settings.access_token_expire_minutes * 60
        ),
        must_change_password=user.must_change_password,
    )


def rotate_refresh_token(
    database: Session,
    *,
    encoded_refresh_token: str,
    request: Request,
) -> TokenPair:
    """Validate and replace an existing refresh token."""

    try:
        payload = decode_token(
            encoded_refresh_token,
            expected_type="refresh",
        )

        user_id = UUID(payload["sub"])
        token_jti = str(payload["jti"])
    except (
        InvalidTokenError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise unauthorized_exception(
            "Invalid refresh token."
        ) from error

    statement = (
        select(RefreshToken)
        .where(RefreshToken.jti == token_jti)
    )

    stored_token = database.scalar(statement)

    if stored_token is None:
        raise unauthorized_exception(
            "Refresh token was not found."
        )

    if stored_token.user_id != user_id:
        raise unauthorized_exception(
            "Refresh token user mismatch."
        )

    if stored_token.revoked_at is not None:
        raise unauthorized_exception(
            "Refresh token has been revoked."
        )

    now = datetime.now(timezone.utc)

    if stored_token.expires_at <= now:
        raise unauthorized_exception(
            "Refresh token has expired."
        )

    user = load_user_by_id(database, user_id)

    if user is None or not user.is_active:
        raise unauthorized_exception(
            "The user account is unavailable."
        )

    if not user.organization.is_active:
        raise unauthorized_exception(
            "The organization is inactive."
        )

    new_access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    ip_address, user_agent = get_request_metadata(request)

    replacement_record = RefreshToken(
        user_id=user.id,
        jti=new_refresh_token.jti,
        expires_at=new_refresh_token.expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    stored_token.revoked_at = now
    stored_token.replaced_by_jti = new_refresh_token.jti

    database.add(replacement_record)
    database.commit()

    return TokenPair(
        access_token=new_access_token.token,
        refresh_token=new_refresh_token.token,
        expires_in=(
            settings.access_token_expire_minutes * 60
        ),
        must_change_password=user.must_change_password,
    )


def revoke_refresh_token(
    database: Session,
    *,
    encoded_refresh_token: str,
) -> None:
    """Revoke one refresh token during logout."""

    try:
        payload = decode_token(
            encoded_refresh_token,
            expected_type="refresh",
        )

        token_jti = str(payload["jti"])
    except (
        InvalidTokenError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise unauthorized_exception(
            "Invalid refresh token."
        ) from error

    stored_token = database.scalar(
        select(RefreshToken).where(
            RefreshToken.jti == token_jti
        )
    )

    if stored_token is None:
        raise unauthorized_exception(
            "Refresh token was not found."
        )

    if stored_token.revoked_at is None:
        stored_token.revoked_at = datetime.now(timezone.utc)
        database.commit()


def change_user_password(
    database: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    """Change a user password and revoke active refresh tokens."""

    if not verify_password(
        current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current password is incorrect.",
        )

    if current_password == new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The new password must be different "
                "from the current password."
            ),
        )

    user.password_hash = hash_password(new_password)
    user.must_change_password = False

    now = datetime.now(timezone.utc)

    database.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    database.commit()