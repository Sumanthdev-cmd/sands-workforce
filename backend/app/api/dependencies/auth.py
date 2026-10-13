from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import User
from app.services.auth_service import load_user_by_id

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AccessToken",
    bearerFormat="JWT",
    description=(
        "Paste only the access_token returned by /auth/login. "
        "Do not include 'Bearer' and do not use the refresh_token."
    ),
)


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    database: Annotated[
        Session,
        Depends(get_db),
    ],
) -> User:
    """Return the user represented by an access token."""

    authentication_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise authentication_error

    if credentials.scheme.lower() != "bearer":
        raise authentication_error

    try:
        payload = decode_token(
            credentials.credentials,
            expected_type="access",
        )

        user_id = UUID(payload["sub"])
    except (
        InvalidTokenError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise authentication_error from error

    user = load_user_by_id(database, user_id)

    if user is None:
        raise authentication_error

    if not user.is_active:
        raise authentication_error

    if not user.organization.is_active:
        raise authentication_error

    return user


CurrentUser = Annotated[
    User,
    Depends(get_current_user),
]
