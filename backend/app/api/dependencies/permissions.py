from collections.abc import Callable

from fastapi import HTTPException, status

from app.api.dependencies.auth import CurrentUser
from app.models import User


def require_permissions(
    *required_permissions: str,
) -> Callable[..., User]:
    """
    Require every specified permission.

    Superusers bypass normal permission checks.
    """

    def permission_dependency(
        current_user: CurrentUser,
    ) -> User:
        if current_user.is_superuser:
            return current_user

        granted_permissions = {
            permission.code
            for role in current_user.roles
            for permission in role.permissions
        }

        missing_permissions = set(
            required_permissions
        ) - granted_permissions

        if missing_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Permission denied.",
                    "missing_permissions": sorted(
                        missing_permissions
                    ),
                },
            )

        return current_user

    return permission_dependency