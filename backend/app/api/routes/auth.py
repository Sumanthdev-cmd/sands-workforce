from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    TokenResponse,
)
from app.services.auth_service import (
    authenticate_user,
    change_user_password,
    issue_login_tokens,
    revoke_refresh_token,
    rotate_refresh_token,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]


def create_token_response(token_pair) -> TokenResponse:
    """Convert service token data into an API response."""

    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        expires_in=token_pair.expires_in,
        must_change_password=(
            token_pair.must_change_password
        ),
    )


def create_current_user_response(
    user: User,
) -> CurrentUserResponse:
    """Convert a user model into a safe API response."""

    role_codes = sorted(
        role.code
        for role in user.roles
    )

    permission_codes = sorted(
        {
            permission.code
            for role in user.roles
            for permission in role.permissions
        }
    )

    return CurrentUserResponse(
        id=user.id,
        organization_id=user.organization_id,
        organization_code=user.organization.code,
        employee_code=user.employee_code,
        email=user.email,
        is_superuser=user.is_superuser,
        must_change_password=user.must_change_password,
        roles=role_codes,
        permissions=permission_codes,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    payload: LoginRequest,
    request: Request,
    database: DatabaseSession,
) -> TokenResponse:
    """Authenticate a user and issue tokens."""

    user = authenticate_user(
        database,
        organization_code=payload.organization_code,
        employee_code=payload.employee_code,
        password=payload.password,
    )

    token_pair = issue_login_tokens(
        database,
        user=user,
        request=request,
    )

    return create_token_response(token_pair)


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh(
    payload: RefreshRequest,
    request: Request,
    database: DatabaseSession,
) -> TokenResponse:
    """Rotate a refresh token and issue a new token pair."""

    token_pair = rotate_refresh_token(
        database,
        encoded_refresh_token=payload.refresh_token,
        request=request,
    )

    return create_token_response(token_pair)


@router.post(
    "/logout",
    response_model=MessageResponse,
)
def logout(
    payload: LogoutRequest,
    database: DatabaseSession,
) -> MessageResponse:
    """Revoke the submitted refresh token."""

    revoke_refresh_token(
        database,
        encoded_refresh_token=payload.refresh_token,
    )

    return MessageResponse(
        message="Logout completed successfully."
    )


@router.get(
    "/me",
    response_model=CurrentUserResponse,
)
def read_current_user(
    current_user: CurrentUser,
) -> CurrentUserResponse:
    """Return the authenticated user's profile and access."""

    return create_current_user_response(current_user)


@router.post(
    "/change-password",
    response_model=MessageResponse,
)
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> MessageResponse:
    """Replace the authenticated user's password."""

    change_user_password(
        database,
        user=current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )

    return MessageResponse(
        message=(
            "Password changed successfully. "
            "Existing refresh tokens were revoked."
        )
    )