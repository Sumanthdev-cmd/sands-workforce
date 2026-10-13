from __future__ import annotations

import argparse
from typing import Iterable

from pwdlib import PasswordHash
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Employee, User


DEFAULT_CODES = [
    "ADMIN001",
    "MD001",
    "GM001",
    "MANAGER001",
    "EMP002",
]


def password_field_name() -> str:
    for field in ("password_hash", "hashed_password"):
        if hasattr(User, field):
            return field
    raise RuntimeError(
        "User model does not expose password_hash or hashed_password."
    )


def users_for_codes(database, codes: Iterable[str]) -> tuple[list[tuple[str, User]], list[str]]:
    wanted = {code.strip().upper() for code in codes if code.strip()}
    found: list[tuple[str, User]] = []

    if hasattr(User, "employee_code"):
        rows = list(
            database.scalars(
                select(User).where(User.employee_code.in_(wanted))
            ).all()
        )
        found = [(str(row.employee_code).upper(), row) for row in rows]
    elif hasattr(Employee, "employee_code"):
        employees = list(
            database.scalars(
                select(Employee).where(Employee.employee_code.in_(wanted))
            ).all()
        )
        for employee in employees:
            user = database.get(User, employee.user_id)
            if user is not None:
                found.append((str(employee.employee_code).upper(), user))
    else:
        raise RuntimeError(
            "Neither User nor Employee has an employee_code field."
        )

    found_codes = {code for code, _ in found}
    missing = sorted(wanted - found_codes)
    return found, missing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--password",
        required=True,
        help="Temporary local-development password.",
    )
    parser.add_argument(
        "--codes",
        default=",".join(DEFAULT_CODES),
        help="Comma-separated employee codes.",
    )
    parser.add_argument(
        "--confirm-local-development",
        action="store_true",
        help="Required safety confirmation.",
    )
    args = parser.parse_args()

    if not args.confirm_local_development:
        raise SystemExit(
            "Add --confirm-local-development. Do not run this in production."
        )

    codes = [item.strip() for item in args.codes.split(",") if item.strip()]
    password_hash = PasswordHash.recommended().hash(args.password)
    field_name = password_field_name()

    database = SessionLocal()
    try:
        rows, missing = users_for_codes(database, codes)
        for code, user in rows:
            setattr(user, field_name, password_hash)
            print(f"Reset password for {code}")
        database.commit()

        if missing:
            print("Missing employee codes:", ", ".join(missing))

        print()
        print("Password reset completed.")
        print("Change these passwords after testing.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
