"""Password reset approval, late payroll controls and overtime claims.

Revision ID: 9c40b77e31ad
Revises: 4e2ac9f71b90
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9c40b77e31ad"
down_revision: Union[str, Sequence[str], None] = "4e2ac9f71b90"
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
            "overtime_benefit",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "password_reset_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING_MD"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('PENDING_MD','APPROVED','REJECTED','COMPLETED','EXPIRED')",
            name="ck_password_reset_approval_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "organization_id",
        "target_employee_id",
        "requested_by_user_id",
        "status",
        "requested_at",
        "approval_expires_at",
    ):
        op.create_index(
            f"ix_password_reset_approvals_{column}",
            "password_reset_approvals",
            [column],
        )

    op.create_table(
        "late_attendance_monthly_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("month_start", sa.Date(), nullable=False),
        sa.Column("qualifying_late_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("half_day_deduction_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("half_day_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("salary_hold_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("salary_hold_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hold_released_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("hold_released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hold_release_note", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hold_released_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "employee_id",
            "month_start",
            name="uq_late_attendance_month_employee",
        ),
    )
    for column in ("organization_id", "employee_id", "month_start"):
        op.create_index(
            f"ix_late_attendance_monthly_actions_{column}",
            "late_attendance_monthly_actions",
            [column],
        )

    op.create_table(
        "overtime_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attendance_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worked_minutes", sa.Integer(), nullable=False),
        sa.Column("scheduled_minutes", sa.Integer(), nullable=False),
        sa.Column("overtime_minutes", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="DRAFT"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_verified_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("admin_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("admin_proposed_amount", sa.Float(), nullable=True),
        sa.Column("md_decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("md_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("md_note", sa.Text(), nullable=True),
        sa.Column("approved_amount", sa.Float(), nullable=True),
        sa.Column("payroll_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('DRAFT','PENDING_ADMIN','PENDING_MD','APPROVED','REJECTED','PAID')",
            name="ck_overtime_claim_status",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attendance_record_id"], ["attendance_records.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evidence_document_id"], ["document_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["admin_verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["md_decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payroll_run_id"], ["payroll_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "work_date", name="uq_overtime_claim_employee_date"),
    )
    for column in (
        "organization_id",
        "employee_id",
        "attendance_record_id",
        "work_date",
        "status",
        "submitted_at",
        "payroll_run_id",
    ):
        op.create_index(f"ix_overtime_claims_{column}", "overtime_claims", [column])


def downgrade() -> None:
    op.drop_table("overtime_claims")
    op.drop_table("late_attendance_monthly_actions")
    op.drop_table("password_reset_approvals")
    op.drop_column("payroll_items", "overtime_benefit")
