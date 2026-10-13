"""Add vendor attendance visibility and salary advance recovery.

Revision ID: e21d4f87a9b2
Revises: c62e8a41bd30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e21d4f87a9b2"
down_revision: Union[str, Sequence[str], None] = "c62e8a41bd30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vendor_payroll_items",
        sa.Column("other_deductions", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "vendor_payroll_items",
        sa.Column("salary_advance_deduction", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "vendor_attendance_records",
        sa.Column("late_minutes", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "vendor_salary_advance_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_vendor_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_amount", sa.Float(), nullable=False),
        sa.Column("installment_amount", sa.Float(), nullable=False),
        sa.Column("recovery_months", sa.Integer(), nullable=False),
        sa.Column("recovered_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="INR"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("disbursed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("disbursed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disbursement_reference", sa.String(length=200), nullable=True),
        sa.Column("disbursement_note", sa.Text(), nullable=True),
        sa.Column("recovery_start_date", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_vendor_account_id"], ["vendor_portal_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["disbursed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_salary_advance_requests_org_status", "vendor_salary_advance_requests", ["organization_id", "status"])
    op.create_index("ix_vendor_salary_advance_requests_vendor", "vendor_salary_advance_requests", ["vendor_id"])
    op.create_index("ix_vendor_salary_advance_requests_recovery_start", "vendor_salary_advance_requests", ["recovery_start_date"])

    op.create_table(
        "vendor_salary_advance_recoveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_salary_advance_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payroll_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_salary_advance_request_id"], ["vendor_salary_advance_requests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payroll_run_id"], ["payroll_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vendor_salary_advance_request_id", "payroll_run_id", name="uq_vendor_salary_advance_recovery_request_run"),
    )
    op.create_index("ix_vendor_salary_advance_recoveries_request", "vendor_salary_advance_recoveries", ["vendor_salary_advance_request_id"])
    op.create_index("ix_vendor_salary_advance_recoveries_run", "vendor_salary_advance_recoveries", ["payroll_run_id"])
    op.create_index("ix_vendor_salary_advance_recoveries_vendor", "vendor_salary_advance_recoveries", ["vendor_id"])


def downgrade() -> None:
    op.drop_index("ix_vendor_salary_advance_recoveries_vendor", table_name="vendor_salary_advance_recoveries")
    op.drop_index("ix_vendor_salary_advance_recoveries_run", table_name="vendor_salary_advance_recoveries")
    op.drop_index("ix_vendor_salary_advance_recoveries_request", table_name="vendor_salary_advance_recoveries")
    op.drop_table("vendor_salary_advance_recoveries")
    op.drop_index("ix_vendor_salary_advance_requests_recovery_start", table_name="vendor_salary_advance_requests")
    op.drop_index("ix_vendor_salary_advance_requests_vendor", table_name="vendor_salary_advance_requests")
    op.drop_index("ix_vendor_salary_advance_requests_org_status", table_name="vendor_salary_advance_requests")
    op.drop_table("vendor_salary_advance_requests")
    op.drop_column("vendor_attendance_records", "late_minutes")
    op.drop_column("vendor_payroll_items", "salary_advance_deduction")
    op.drop_column("vendor_payroll_items", "other_deductions")
