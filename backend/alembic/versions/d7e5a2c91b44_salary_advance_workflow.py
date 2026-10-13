"""Salary advance request, approval, disbursement and payroll recovery.

Revision ID: d7e5a2c91b44
Revises: f31a9c4d72b8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d7e5a2c91b44"
down_revision: Union[str, Sequence[str], None] = "f31a9c4d72b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def timestamps():
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def upgrade() -> None:
    op.add_column(
        "payroll_items",
        sa.Column(
            "salary_advance_deduction",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "salary_advance_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("requested_amount", sa.Float(), nullable=False),
        sa.Column("installment_amount", sa.Float(), nullable=False),
        sa.Column("recovery_months", sa.Integer(), nullable=False),
        sa.Column(
            "recovered_amount",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "currency",
            sa.String(length=10),
            nullable=False,
            server_default="INR",
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "decided_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "disbursed_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("disbursed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "disbursement_reference",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column("disbursement_note", sa.Text(), nullable=True),
        sa.Column("recovery_start_date", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_note", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "requested_amount > 0",
            name="ck_salary_advance_requested_amount_positive",
        ),
        sa.CheckConstraint(
            "installment_amount > 0 AND installment_amount <= requested_amount",
            name="ck_salary_advance_installment_amount",
        ),
        sa.CheckConstraint(
            "recovery_months BETWEEN 1 AND 120",
            name="ck_salary_advance_recovery_months",
        ),
        sa.CheckConstraint(
            "recovered_amount >= 0 AND recovered_amount <= requested_amount",
            name="ck_salary_advance_recovered_amount",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','DISBURSED','RECOVERING','RECOVERED','CANCELLED')",
            name="ck_salary_advance_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["disbursed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_salary_advance_requests_organization_id",
        "salary_advance_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_salary_advance_requests_employee_id",
        "salary_advance_requests",
        ["employee_id"],
    )
    op.create_index(
        "ix_salary_advance_requests_status",
        "salary_advance_requests",
        ["status"],
    )
    op.create_index(
        "ix_salary_advance_requests_requested_at",
        "salary_advance_requests",
        ["requested_at"],
    )
    op.create_index(
        "ix_salary_advance_requests_recovery_start_date",
        "salary_advance_requests",
        ["recovery_start_date"],
    )

    op.create_table(
        "salary_advance_recoveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "salary_advance_request_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "payroll_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column(
            "recovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "recorded_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        *timestamps(),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_salary_advance_recovery_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["salary_advance_request_id"],
            ["salary_advance_requests.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payroll_run_id"],
            ["payroll_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "salary_advance_request_id",
            "payroll_run_id",
            name="uq_salary_advance_recovery_request_run",
        ),
    )
    op.create_index(
        "ix_salary_advance_recoveries_organization_id",
        "salary_advance_recoveries",
        ["organization_id"],
    )
    op.create_index(
        "ix_salary_advance_recoveries_salary_advance_request_id",
        "salary_advance_recoveries",
        ["salary_advance_request_id"],
    )
    op.create_index(
        "ix_salary_advance_recoveries_payroll_run_id",
        "salary_advance_recoveries",
        ["payroll_run_id"],
    )
    op.create_index(
        "ix_salary_advance_recoveries_employee_id",
        "salary_advance_recoveries",
        ["employee_id"],
    )
    op.create_index(
        "ix_salary_advance_recoveries_recovered_at",
        "salary_advance_recoveries",
        ["recovered_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_salary_advance_recoveries_recovered_at",
        table_name="salary_advance_recoveries",
    )
    op.drop_index(
        "ix_salary_advance_recoveries_employee_id",
        table_name="salary_advance_recoveries",
    )
    op.drop_index(
        "ix_salary_advance_recoveries_payroll_run_id",
        table_name="salary_advance_recoveries",
    )
    op.drop_index(
        "ix_salary_advance_recoveries_salary_advance_request_id",
        table_name="salary_advance_recoveries",
    )
    op.drop_index(
        "ix_salary_advance_recoveries_organization_id",
        table_name="salary_advance_recoveries",
    )
    op.drop_table("salary_advance_recoveries")

    op.drop_index(
        "ix_salary_advance_requests_recovery_start_date",
        table_name="salary_advance_requests",
    )
    op.drop_index(
        "ix_salary_advance_requests_requested_at",
        table_name="salary_advance_requests",
    )
    op.drop_index(
        "ix_salary_advance_requests_status",
        table_name="salary_advance_requests",
    )
    op.drop_index(
        "ix_salary_advance_requests_employee_id",
        table_name="salary_advance_requests",
    )
    op.drop_index(
        "ix_salary_advance_requests_organization_id",
        table_name="salary_advance_requests",
    )
    op.drop_table("salary_advance_requests")
    op.drop_column("payroll_items", "salary_advance_deduction")
