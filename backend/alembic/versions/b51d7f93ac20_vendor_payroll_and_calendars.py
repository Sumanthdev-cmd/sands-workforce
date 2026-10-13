"""Vendor payroll and separate employee/vendor working calendars.

Revision ID: b51d7f93ac20
Revises: 9c40b77e31ad
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b51d7f93ac20"
down_revision: Union[str, Sequence[str], None] = "9c40b77e31ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    op.add_column("payroll_runs", sa.Column("total_vendors", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("payroll_runs", sa.Column("vendor_total_gross", sa.Float(), nullable=False, server_default="0"))
    op.add_column("payroll_runs", sa.Column("vendor_total_deductions", sa.Float(), nullable=False, server_default="0"))
    op.add_column("payroll_runs", sa.Column("vendor_total_net", sa.Float(), nullable=False, server_default="0"))

    op.create_table(
        "vendor_salary_structures",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("monthly_salary", sa.Float(), nullable=False),
        sa.Column("fixed_deduction", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="INR"),
        sa.Column("revision_reason", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vendor_id", "effective_from", name="uq_vendor_salary_structure_vendor_date"),
    )
    op.create_index("ix_vendor_salary_structures_organization_id", "vendor_salary_structures", ["organization_id"])
    op.create_index("ix_vendor_salary_structures_vendor_id", "vendor_salary_structures", ["vendor_id"])
    op.create_index("ix_vendor_salary_structures_effective_from", "vendor_salary_structures", ["effective_from"])

    op.create_table(
        "vendor_closure_days",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("closure_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "closure_date", name="uq_vendor_closure_org_date"),
    )
    op.create_index("ix_vendor_closure_days_organization_id", "vendor_closure_days", ["organization_id"])
    op.create_index("ix_vendor_closure_days_closure_date", "vendor_closure_days", ["closure_date"])

    op.create_table(
        "vendor_payroll_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payroll_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_salary_structure_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("working_days", sa.Float(), nullable=False),
        sa.Column("payable_days", sa.Float(), nullable=False),
        sa.Column("absent_days", sa.Float(), nullable=False),
        sa.Column("gross_earned", sa.Float(), nullable=False),
        sa.Column("fixed_deduction", sa.Float(), nullable=False, server_default="0"),
        sa.Column("net_salary", sa.Float(), nullable=False),
        sa.Column("calculation_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("payslip_number", sa.String(length=100), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payroll_run_id"], ["payroll_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_salary_structure_id"], ["vendor_salary_structures.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payroll_run_id", "vendor_id", name="uq_vendor_payroll_item_run_vendor"),
        sa.UniqueConstraint("payslip_number", name="uq_vendor_payroll_items_payslip_number"),
    )
    for column in ("organization_id", "payroll_run_id", "vendor_id", "payslip_number"):
        op.create_index(f"ix_vendor_payroll_items_{column}", "vendor_payroll_items", [column])


def downgrade() -> None:
    op.drop_table("vendor_payroll_items")
    op.drop_table("vendor_closure_days")
    op.drop_table("vendor_salary_structures")
    op.drop_column("payroll_runs", "vendor_total_net")
    op.drop_column("payroll_runs", "vendor_total_deductions")
    op.drop_column("payroll_runs", "vendor_total_gross")
    op.drop_column("payroll_runs", "total_vendors")
