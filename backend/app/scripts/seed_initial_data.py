from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Organization, Permission, Role, User


settings = get_settings()


PERMISSION_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    (
        "organization.view",
        "View organization",
        "View organization profile and configuration.",
    ),
    (
        "employee.create",
        "Create employees",
        "Create new employee and user accounts.",
    ),
    (
        "employee.read",
        "View employees",
        "View employee information.",
    ),
    (
        "employee.update",
        "Update employees",
        "Update employee information.",
    ),
    (
        "employee.disable",
        "Disable employees",
        "Disable or enable employee accounts.",
    ),
    (
        "role.manage",
        "Manage roles",
        "Create roles and assign permissions.",
    ),
    (
        "user.assign_roles",
        "Assign user roles",
        "Assign or remove roles from users.",
    ),
    (
        "permission.view",
        "View permissions",
        "View available system permissions.",
    ),
    (
        "attendance.view_all",
        "View all attendance",
        "View attendance records for all employees.",
    ),
    (
        "location.view_all",
        "View all locations",
        "View live and historical employee locations.",
    ),
    (
        "salary.prepare",
        "Prepare salary",
        "Prepare salary calculations and deductions.",
    ),
    (
        "salary.approve",
        "Approve salary",
        "Approve salary for disbursement.",
    ),
    (
        "salary.hike",
        "Change salary",
        "Increase or modify an employee salary.",
    ),
    (
        "salary.hold",
        "Hold salary",
        "Hold or release an employee salary.",
    ),
    (
        "salary.advance",
        "Approve salary advance",
        "Approve advance salary payments.",
    ),
    (
        "finance.manage",
        "Manage financial entries",
        "Create and maintain financial transactions.",
    ),
    (
        "finance.approve",
        "Approve financial entries",
        "Approve expenses and financial requests.",
    ),
    (
        "task.assign",
        "Assign tasks",
        "Assign tasks and routine work to employees.",
    ),
    (
        "leave.approve",
        "Approve leave",
        "Review and approve employee leave requests.",
    ),
    (
        "audit.view",
        "View audit logs",
        "View system and business audit history.",
    ),
)


ROLE_DEFINITIONS: tuple[tuple[str, str, str], ...] = (
    (
        "MD",
        "Managing Director",
        "Managing Director with business-wide visibility and approvals.",
    ),
    (
        "ADMIN",
        "Administrator",
        "Organization administrator responsible for workforce operations.",
    ),
    (
        "GM",
        "General Manager",
        "General Manager with management reporting access.",
    ),
    (
        "MANAGER",
        "Manager",
        "Department or team manager.",
    ),
    (
        "ACCOUNTS_MANAGER",
        "Accounts Manager",
        "Manager responsible for accounts operations.",
    ),
    (
        "ACCOUNTS_SECRETARY",
        "Accounts Secretary",
        "Accounts employee responsible for approved payment processing.",
    ),
    (
        "HR_RECRUITER",
        "HR Recruiter",
        "Human-resources and recruitment employee.",
    ),
    (
        "FIELD_VISITOR",
        "Field Visitor",
        "Employee assigned to field visits and field reporting.",
    ),
    (
        "OFFICE_EMPLOYEE",
        "Office Employee",
        "Employee working primarily from an office.",
    ),
    (
        "EMPLOYEE",
        "Employee",
        "Standard employee role.",
    ),
)


ROLE_PERMISSION_CODES: dict[str, set[str]] = {
    "MD": {
        permission_code
        for permission_code, _, _ in PERMISSION_DEFINITIONS
    },
    "ADMIN": {
        "organization.view",
        "employee.create",
        "employee.read",
        "employee.update",
        "employee.disable",
        "role.manage",
        "user.assign_roles",
        "permission.view",
        "attendance.view_all",
        "location.view_all",
        "salary.prepare",
        "finance.manage",
        "task.assign",
        "leave.approve",
        "audit.view",
    },
    "GM": {
        "organization.view",
        "employee.read",
        "attendance.view_all",
        "location.view_all",
        "task.assign",
    },
    "MANAGER": {
        "employee.read",
        "attendance.view_all",
        "task.assign",
    },
    "ACCOUNTS_MANAGER": {
        "employee.read",
        "salary.prepare",
        "finance.manage",
    },
    "ACCOUNTS_SECRETARY": {
        "employee.read",
        "finance.manage",
    },
    "HR_RECRUITER": {
        "employee.create",
        "employee.read",
        "employee.update",
    },
    "FIELD_VISITOR": set(),
    "OFFICE_EMPLOYEE": set(),
    "EMPLOYEE": set(),
}


def get_or_create_organization(
    database: Session,
) -> Organization:
    """Create the initial organization when it does not exist."""

    organization = database.scalar(
        select(Organization).where(
            Organization.code
            == settings.initial_organization_code.upper()
        )
    )

    if organization is not None:
        return organization

    organization = Organization(
        name=settings.initial_organization_name.strip(),
        code=settings.initial_organization_code.strip().upper(),
        timezone="Asia/Kolkata",
        is_active=True,
    )

    database.add(organization)
    database.flush()

    print(
        f"Created organization: "
        f"{organization.name} ({organization.code})"
    )

    return organization


def seed_permissions(
    database: Session,
) -> dict[str, Permission]:
    """Create or update system permissions."""

    permissions: dict[str, Permission] = {}

    for code, name, description in PERMISSION_DEFINITIONS:
        permission = database.scalar(
            select(Permission).where(
                Permission.code == code
            )
        )

        if permission is None:
            permission = Permission(
                code=code,
                name=name,
                description=description,
            )
            database.add(permission)
            print(f"Created permission: {code}")
        else:
            permission.name = name
            permission.description = description

        permissions[code] = permission

    database.flush()

    return permissions


def seed_roles(
    database: Session,
    organization: Organization,
    permissions: dict[str, Permission],
) -> dict[str, Role]:
    """Create organization roles and assign their permissions."""

    roles: dict[str, Role] = {}

    for code, name, description in ROLE_DEFINITIONS:
        role = database.scalar(
            select(Role).where(
                Role.organization_id == organization.id,
                Role.code == code,
            )
        )

        if role is None:
            role = Role(
                organization_id=organization.id,
                code=code,
                name=name,
                description=description,
                is_system_role=True,
                is_active=True,
            )
            database.add(role)
            database.flush()
            print(f"Created role: {code}")
        else:
            role.name = name
            role.description = description
            role.is_system_role = True
            role.is_active = True

        required_permission_codes = ROLE_PERMISSION_CODES.get(
            code,
            set(),
        )

        role.permissions = [
            permissions[permission_code]
            for permission_code in sorted(
                required_permission_codes
            )
        ]

        roles[code] = role

    database.flush()

    return roles


def create_initial_admin(
    database: Session,
    organization: Organization,
    roles: dict[str, Role],
) -> User:
    """Create the first administrator account."""

    if not settings.initial_admin_password:
        raise RuntimeError(
            "INITIAL_ADMIN_PASSWORD is required in backend/.env."
        )

    employee_code = (
        settings.initial_admin_employee_code.strip().upper()
    )

    user = database.scalar(
        select(User).where(
            User.organization_id == organization.id,
            User.employee_code == employee_code,
        )
    )

    if user is not None:
        if roles["ADMIN"] not in user.roles:
            user.roles.append(roles["ADMIN"])

        print(
            f"Initial administrator already exists: "
            f"{employee_code}"
        )

        return user

    email = (
        settings.initial_admin_email.strip().lower()
        if settings.initial_admin_email
        else None
    )

    user = User(
        organization_id=organization.id,
        employee_code=employee_code,
        email=email,
        password_hash=hash_password(
            settings.initial_admin_password
        ),
        is_active=True,
        is_superuser=True,
        must_change_password=True,
        roles=[roles["ADMIN"]],
    )

    database.add(user)
    database.flush()

    print(
        f"Created initial administrator: "
        f"{user.employee_code}"
    )

    return user


def print_summary(
    organization: Organization,
    roles: Iterable[Role],
    permissions: Iterable[Permission],
    administrator: User,
) -> None:
    """Print a safe summary without displaying passwords."""

    print("")
    print("Initial data seed completed.")
    print(f"Organization: {organization.code}")
    print(f"Roles: {len(list(roles))}")
    print(f"Permissions: {len(list(permissions))}")
    print(
        f"Administrator employee code: "
        f"{administrator.employee_code}"
    )
    print(
        "Administrator must change password: "
        f"{administrator.must_change_password}"
    )


def seed_initial_data() -> None:
    """Create all required bootstrap records."""

    with SessionLocal() as database:
        try:
            organization = get_or_create_organization(
                database
            )

            permissions = seed_permissions(database)

            roles = seed_roles(
                database,
                organization,
                permissions,
            )

            administrator = create_initial_admin(
                database,
                organization,
                roles,
            )

            database.commit()

            print_summary(
                organization,
                roles.values(),
                permissions.values(),
                administrator,
            )
        except Exception:
            database.rollback()
            raise


if __name__ == "__main__":
    seed_initial_data()