"""Accounts daily sheet verification and timed discrepancy escalation.

Revision ID: 4e2ac9f71b90
Revises: d7e5a2c91b44
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4e2ac9f71b90"
down_revision: Union[str, Sequence[str], None] = "d7e5a2c91b44"
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


def ensure_accounts_roles() -> None:
    connection = op.get_bind()
    organization_ids = list(
        connection.execute(sa.text("SELECT id FROM organizations")).scalars()
    )
    definitions = (
        (
            "ACCOUNTS_MANAGER",
            "Accounts Manager",
            "Manager responsible for accounts operations and daily sheet verification.",
        ),
        (
            "ACCOUNTS_SECRETARY",
            "Accounts Secretary",
            "Accounts employee responsible for verifying daily accounts sheets.",
        ),
    )

    for organization_id in organization_ids:
        for code, name, description in definitions:
            exists = connection.execute(
                sa.text(
                    "SELECT 1 FROM roles "
                    "WHERE organization_id = :organization_id AND code = :code"
                ),
                {"organization_id": organization_id, "code": code},
            ).scalar()
            if exists:
                continue
            connection.execute(
                sa.text(
                    "INSERT INTO roles "
                    "(id, organization_id, name, code, description, "
                    "is_system_role, is_active, created_at, updated_at) "
                    "VALUES (CAST(:id AS UUID), CAST(:organization_id AS UUID), "
                    ":name, :code, :description, "
                    "true, true, now(), now())"
                ),
                {
                    "id": str(uuid4()),
                    "organization_id": str(organization_id),
                    "name": name,
                    "code": code,
                    "description": description,
                },
            )


def upgrade() -> None:
    ensure_accounts_roles()

    op.create_table(
        "account_sheet_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "submission_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "accounts_manager_employee_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("verification_date", sa.Date(), nullable=False),
        sa.Column("declared_sheet_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="PENDING_SECRETARY",
        ),
        sa.Column(
            "submitted_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        *timestamps(),
        sa.CheckConstraint(
            "declared_sheet_count > 0",
            name="ck_account_sheet_verification_positive_count",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_SECRETARY','ISSUES_OPEN','COMPLETED')",
            name="ck_account_sheet_verification_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["accounts_manager_employee_id"],
            ["employees.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "submission_id",
            name="uq_account_sheet_verification_submission",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "accounts_manager_employee_id",
            "verification_date",
            name="uq_account_sheet_verification_manager_day",
        ),
    )
    op.create_index(
        "ix_account_sheet_verifications_organization_id",
        "account_sheet_verifications",
        ["organization_id"],
    )
    op.create_index(
        "ix_account_sheet_verifications_submission_id",
        "account_sheet_verifications",
        ["submission_id"],
    )
    op.create_index(
        "ix_account_sheet_verifications_accounts_manager_employee_id",
        "account_sheet_verifications",
        ["accounts_manager_employee_id"],
    )
    op.create_index(
        "ix_account_sheet_verifications_verification_date",
        "account_sheet_verifications",
        ["verification_date"],
    )
    op.create_index(
        "ix_account_sheet_verifications_status",
        "account_sheet_verifications",
        ["status"],
    )
    op.create_index(
        "ix_account_sheet_verifications_submitted_by_user_id",
        "account_sheet_verifications",
        ["submitted_by_user_id"],
    )
    op.create_index(
        "ix_account_sheet_verifications_submitted_at",
        "account_sheet_verifications",
        ["submitted_at"],
    )

    op.create_table(
        "account_sheet_verification_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "verification_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("sheet_name", sa.String(length=250), nullable=False),
        sa.Column("sheet_generated_on", sa.Date(), nullable=False),
        sa.Column(
            "has_discrepancy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("discrepancy_reason", sa.Text(), nullable=True),
        sa.Column(
            "discrepancy_document_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "secretary_status",
            sa.String(length=20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "secretary_reviewed_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "secretary_reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("secretary_note", sa.Text(), nullable=True),
        sa.Column(
            "issue_status",
            sa.String(length=20),
            nullable=False,
            server_default="NONE",
        ),
        sa.Column(
            "issue_raised_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "admin_escalated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "md_escalated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolution_role", sa.String(length=40), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "secretary_status IN ('PENDING','VERIFIED','CONFIRMED','NOT_FOUND')",
            name="ck_account_sheet_item_secretary_status",
        ),
        sa.CheckConstraint(
            "issue_status IN ('NONE','OPEN','RESOLVED')",
            name="ck_account_sheet_item_issue_status",
        ),
        sa.CheckConstraint(
            "((has_discrepancy = false AND discrepancy_reason IS NULL "
            "AND discrepancy_document_id IS NULL AND issue_status = 'NONE' "
            "AND issue_raised_at IS NULL) OR "
            "(has_discrepancy = true AND discrepancy_reason IS NOT NULL "
            "AND discrepancy_document_id IS NOT NULL "
            "AND issue_status IN ('OPEN','RESOLVED') "
            "AND issue_raised_at IS NOT NULL))",
            name="ck_account_sheet_item_discrepancy_fields",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["verification_id"],
            ["account_sheet_verifications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["discrepancy_document_id"],
            ["document_records.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["secretary_reviewed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "verification_id",
            "sheet_name",
            "sheet_generated_on",
            name="uq_account_sheet_item_name_date",
        ),
    )
    index_columns = (
        "organization_id",
        "verification_id",
        "sheet_generated_on",
        "has_discrepancy",
        "discrepancy_document_id",
        "secretary_status",
        "issue_status",
        "issue_raised_at",
        "admin_escalated_at",
        "md_escalated_at",
    )
    for column_name in index_columns:
        op.create_index(
            f"ix_account_sheet_verification_items_{column_name}",
            "account_sheet_verification_items",
            [column_name],
        )


def downgrade() -> None:
    index_columns = (
        "md_escalated_at",
        "admin_escalated_at",
        "issue_raised_at",
        "issue_status",
        "secretary_status",
        "discrepancy_document_id",
        "has_discrepancy",
        "sheet_generated_on",
        "verification_id",
        "organization_id",
    )
    for column_name in index_columns:
        op.drop_index(
            f"ix_account_sheet_verification_items_{column_name}",
            table_name="account_sheet_verification_items",
        )
    op.drop_table("account_sheet_verification_items")

    report_index_columns = (
        "submitted_at",
        "submitted_by_user_id",
        "status",
        "verification_date",
        "accounts_manager_employee_id",
        "submission_id",
        "organization_id",
    )
    for column_name in report_index_columns:
        op.drop_index(
            f"ix_account_sheet_verifications_{column_name}",
            table_name="account_sheet_verifications",
        )
    op.drop_table("account_sheet_verifications")
