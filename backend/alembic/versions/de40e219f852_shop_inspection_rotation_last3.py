"""shop inspection rotating field visitor assignments

Revision ID: de40e219f852
Revises: 9ab4c6d8e0f2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "de40e219f852"
down_revision: Union[str, Sequence[str], None] = '9ab4c6d8e0f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inspection_visit_assignments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "outlet_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "field_visitor_employee_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "scheduled_for",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="ASSIGNED",
        ),
        sa.Column(
            "assignment_method",
            sa.String(length=30),
            nullable=False,
            server_default="AUTO_ROTATION",
        ),
        sa.Column(
            "override_reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "inspection_report_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "cancel_reason",
            sa.Text(),
            nullable=True,
        ),
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
        sa.CheckConstraint(
            "status IN ('ASSIGNED','STARTED','SUBMITTED','COMPLETED','CANCELLED')",
            name="ck_insp_visit_status",
        ),
        sa.CheckConstraint(
            "assignment_method IN ('AUTO_ROTATION','MANUAL_OVERRIDE')",
            name="ck_insp_visit_assignment_method",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["outlet_id"],
            ["outlets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["field_visitor_employee_id"],
            ["employees.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inspection_report_id"],
            ["inspection_reports.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_inspection_visit_assignments",
        ),
        sa.UniqueConstraint(
            "inspection_report_id",
            name="uq_insp_visit_report",
        ),
    )

    op.create_index(
        "ix_insp_visit_org_outlet",
        "inspection_visit_assignments",
        ["organization_id", "outlet_id"],
        unique=False,
    )

    op.create_index(
        "ix_insp_visit_visitor_date",
        "inspection_visit_assignments",
        [
            "organization_id",
            "field_visitor_employee_id",
            "scheduled_for",
        ],
        unique=False,
    )

    op.create_index(
        "ix_insp_visit_status",
        "inspection_visit_assignments",
        ["organization_id", "status"],
        unique=False,
    )

    op.create_index(
        "ux_insp_visit_active_outlet",
        "inspection_visit_assignments",
        ["organization_id", "outlet_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('ASSIGNED','STARTED')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_insp_visit_active_outlet",
        table_name="inspection_visit_assignments",
    )
    op.drop_index(
        "ix_insp_visit_status",
        table_name="inspection_visit_assignments",
    )
    op.drop_index(
        "ix_insp_visit_visitor_date",
        table_name="inspection_visit_assignments",
    )
    op.drop_index(
        "ix_insp_visit_org_outlet",
        table_name="inspection_visit_assignments",
    )
    op.drop_table("inspection_visit_assignments")
