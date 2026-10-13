"""Add employee-equivalent allowance components to vendor payroll.

Revision ID: c62e8a41bd30
Revises: b51d7f93ac20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c62e8a41bd30"
down_revision: Union[str, Sequence[str], None] = "b51d7f93ac20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column_name in (
        "basic_salary",
        "hra",
        "conveyance_allowance",
        "other_allowance",
        "daily_allowance",
    ):
        op.add_column(
            "vendor_salary_structures",
            sa.Column(column_name, sa.Float(), nullable=False, server_default="0"),
        )

    # Preserve every salary already fixed before this upgrade as Basic Salary.
    op.execute(
        "UPDATE vendor_salary_structures "
        "SET basic_salary = monthly_salary "
        "WHERE basic_salary = 0"
    )

    for column_name in (
        "basic_earned",
        "hra_earned",
        "conveyance_earned",
        "other_allowance_earned",
        "daily_allowance_earned",
    ):
        op.add_column(
            "vendor_payroll_items",
            sa.Column(column_name, sa.Float(), nullable=False, server_default="0"),
        )

    # Existing calculated vendor payroll remains auditable after the schema split.
    op.execute(
        "UPDATE vendor_payroll_items "
        "SET basic_earned = gross_earned "
        "WHERE basic_earned = 0"
    )


def downgrade() -> None:
    for column_name in (
        "daily_allowance_earned",
        "other_allowance_earned",
        "conveyance_earned",
        "hra_earned",
        "basic_earned",
    ):
        op.drop_column("vendor_payroll_items", column_name)

    for column_name in (
        "daily_allowance",
        "other_allowance",
        "conveyance_allowance",
        "hra",
        "basic_salary",
    ):
        op.drop_column("vendor_salary_structures", column_name)
