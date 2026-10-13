"""Workforce policy controls and escalation rules.

Revision ID: f31a9c4d72b8
Revises: a84d9c7e31f2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f31a9c4d72b8"
down_revision: Union[str, Sequence[str], None] = "a84d9c7e31f2"
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
        "salary_structures",
        sa.Column(
            "daily_allowance",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "payroll_items",
        sa.Column(
            "daily_allowance_earned",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "organization_work_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "lunch_break_minutes",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column(
            "lunch_is_paid",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "inspection_start_cutoff",
            sa.String(length=5),
            nullable=False,
            server_default="09:30",
        ),
        sa.Column(
            "updated_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            name="uq_organization_work_policy_organization",
        ),
    )
    op.create_index(
        "ix_organization_work_policies_organization_id",
        "organization_work_policies",
        ["organization_id"],
    )

    op.create_table(
        "duty_exit_requests",
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
            "attendance_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
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
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_latitude", sa.Float(), nullable=True),
        sa.Column("exit_longitude", sa.Float(), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("return_latitude", sa.Float(), nullable=True),
        sa.Column("return_longitude", sa.Float(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','OUTSIDE','RETURNED','CANCELLED')",
            name="ck_duty_exit_request_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["attendance_record_id"],
            ["attendance_records.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_duty_exit_requests_organization_id",
        "duty_exit_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_duty_exit_requests_employee_id",
        "duty_exit_requests",
        ["employee_id"],
    )
    op.create_index(
        "ix_duty_exit_requests_attendance_record_id",
        "duty_exit_requests",
        ["attendance_record_id"],
    )
    op.create_index(
        "ix_duty_exit_requests_status",
        "duty_exit_requests",
        ["status"],
    )
    op.create_index(
        "ix_duty_exit_requests_requested_at",
        "duty_exit_requests",
        ["requested_at"],
    )

    op.create_table(
        "lunch_breaks",
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
            "attendance_record_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allowed_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "exceeded_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "overrun_notified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('ACTIVE','COMPLETED')",
            name="ck_lunch_break_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["attendance_record_id"],
            ["attendance_records.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lunch_breaks_organization_id",
        "lunch_breaks",
        ["organization_id"],
    )
    op.create_index(
        "ix_lunch_breaks_employee_id",
        "lunch_breaks",
        ["employee_id"],
    )
    op.create_index(
        "ix_lunch_breaks_attendance_record_id",
        "lunch_breaks",
        ["attendance_record_id"],
    )
    op.create_index(
        "ix_lunch_breaks_started_at",
        "lunch_breaks",
        ["started_at"],
    )
    op.create_index(
        "ix_lunch_breaks_status",
        "lunch_breaks",
        ["status"],
    )

    op.create_table(
        "employee_notice_periods",
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
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "salary_hold_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "ended_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_note", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('ACTIVE','COMPLETED','CANCELLED')",
            name="ck_employee_notice_period_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["salary_hold_id"], ["salary_holds.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ended_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "salary_hold_id",
            name="uq_employee_notice_period_salary_hold",
        ),
    )
    op.create_index(
        "ix_employee_notice_periods_organization_id",
        "employee_notice_periods",
        ["organization_id"],
    )
    op.create_index(
        "ix_employee_notice_periods_employee_id",
        "employee_notice_periods",
        ["employee_id"],
    )
    op.create_index(
        "ix_employee_notice_periods_start_date",
        "employee_notice_periods",
        ["start_date"],
    )
    op.create_index(
        "ix_employee_notice_periods_end_date",
        "employee_notice_periods",
        ["end_date"],
    )
    op.create_index(
        "ix_employee_notice_periods_status",
        "employee_notice_periods",
        ["status"],
    )

    op.create_table(
        "inspection_late_start_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "visit_assignment_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
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
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED')",
            name="ck_inspection_late_start_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inspection_late_start_requests_organization_id",
        "inspection_late_start_requests",
        ["organization_id"],
    )
    op.create_index(
        "ix_inspection_late_start_requests_visit_assignment_id",
        "inspection_late_start_requests",
        ["visit_assignment_id"],
    )
    op.create_index(
        "ix_inspection_late_start_requests_employee_id",
        "inspection_late_start_requests",
        ["employee_id"],
    )
    op.create_index(
        "ix_inspection_late_start_requests_scheduled_for",
        "inspection_late_start_requests",
        ["scheduled_for"],
    )
    op.create_index(
        "ix_inspection_late_start_requests_status",
        "inspection_late_start_requests",
        ["status"],
    )
    op.create_index(
        "ix_inspection_late_start_requests_requested_at",
        "inspection_late_start_requests",
        ["requested_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inspection_late_start_requests_requested_at",
        table_name="inspection_late_start_requests",
    )
    op.drop_index(
        "ix_inspection_late_start_requests_status",
        table_name="inspection_late_start_requests",
    )
    op.drop_index(
        "ix_inspection_late_start_requests_scheduled_for",
        table_name="inspection_late_start_requests",
    )
    op.drop_index(
        "ix_inspection_late_start_requests_employee_id",
        table_name="inspection_late_start_requests",
    )
    op.drop_index(
        "ix_inspection_late_start_requests_visit_assignment_id",
        table_name="inspection_late_start_requests",
    )
    op.drop_index(
        "ix_inspection_late_start_requests_organization_id",
        table_name="inspection_late_start_requests",
    )
    op.drop_table("inspection_late_start_requests")

    op.drop_index(
        "ix_employee_notice_periods_status",
        table_name="employee_notice_periods",
    )
    op.drop_index(
        "ix_employee_notice_periods_end_date",
        table_name="employee_notice_periods",
    )
    op.drop_index(
        "ix_employee_notice_periods_start_date",
        table_name="employee_notice_periods",
    )
    op.drop_index(
        "ix_employee_notice_periods_employee_id",
        table_name="employee_notice_periods",
    )
    op.drop_index(
        "ix_employee_notice_periods_organization_id",
        table_name="employee_notice_periods",
    )
    op.drop_table("employee_notice_periods")

    op.drop_index("ix_lunch_breaks_status", table_name="lunch_breaks")
    op.drop_index("ix_lunch_breaks_started_at", table_name="lunch_breaks")
    op.drop_index(
        "ix_lunch_breaks_attendance_record_id",
        table_name="lunch_breaks",
    )
    op.drop_index("ix_lunch_breaks_employee_id", table_name="lunch_breaks")
    op.drop_index(
        "ix_lunch_breaks_organization_id",
        table_name="lunch_breaks",
    )
    op.drop_table("lunch_breaks")

    op.drop_index(
        "ix_duty_exit_requests_requested_at",
        table_name="duty_exit_requests",
    )
    op.drop_index(
        "ix_duty_exit_requests_status",
        table_name="duty_exit_requests",
    )
    op.drop_index(
        "ix_duty_exit_requests_attendance_record_id",
        table_name="duty_exit_requests",
    )
    op.drop_index(
        "ix_duty_exit_requests_employee_id",
        table_name="duty_exit_requests",
    )
    op.drop_index(
        "ix_duty_exit_requests_organization_id",
        table_name="duty_exit_requests",
    )
    op.drop_table("duty_exit_requests")

    op.drop_index(
        "ix_organization_work_policies_organization_id",
        table_name="organization_work_policies",
    )
    op.drop_table("organization_work_policies")
    op.drop_column("payroll_items", "daily_allowance_earned")
    op.drop_column("salary_structures", "daily_allowance")
