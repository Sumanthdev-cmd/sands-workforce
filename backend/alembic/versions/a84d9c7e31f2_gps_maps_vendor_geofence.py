"""GPS maps, vendor attendance and inspection location proof.

Revision ID: a84d9c7e31f2
Revises: 63f88d0768fa
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a84d9c7e31f2"
down_revision: Union[str, Sequence[str], None] = "63f88d0768fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "outlets",
        sa.Column(
            "attendance_radius_meters",
            sa.Float(),
            nullable=False,
            server_default="150",
        ),
    )
    op.add_column("inspection_reports", sa.Column("start_latitude", sa.Float(), nullable=True))
    op.add_column("inspection_reports", sa.Column("start_longitude", sa.Float(), nullable=True))
    op.add_column("inspection_reports", sa.Column("start_accuracy_meters", sa.Float(), nullable=True))
    op.add_column("inspection_reports", sa.Column("start_distance_meters", sa.Float(), nullable=True))
    op.add_column(
        "inspection_reports",
        sa.Column("location_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "vendor_attendance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outlet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PRESENT"),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_in_latitude", sa.Float(), nullable=False),
        sa.Column("check_in_longitude", sa.Float(), nullable=False),
        sa.Column("check_in_accuracy_meters", sa.Float(), nullable=True),
        sa.Column("check_in_distance_meters", sa.Float(), nullable=False),
        sa.Column("check_out_latitude", sa.Float(), nullable=True),
        sa.Column("check_out_longitude", sa.Float(), nullable=True),
        sa.Column("check_out_accuracy_meters", sa.Float(), nullable=True),
        sa.Column("check_out_distance_meters", sa.Float(), nullable=True),
        sa.Column("worked_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('PRESENT','CHECKED_OUT')", name="ck_vendor_attendance_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_account_id"], ["vendor_portal_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["outlet_id"], ["outlets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_vendor_attendance_records"),
        sa.UniqueConstraint("vendor_account_id", "outlet_id", "attendance_date", name="uq_vendor_attendance_account_outlet_date"),
    )
    op.create_index("ix_vendor_attendance_org_date", "vendor_attendance_records", ["organization_id", "attendance_date"])
    op.create_index("ix_vendor_attendance_vendor", "vendor_attendance_records", ["vendor_id"])
    op.create_index("ix_vendor_attendance_outlet", "vendor_attendance_records", ["outlet_id"])


def downgrade() -> None:
    op.drop_index("ix_vendor_attendance_outlet", table_name="vendor_attendance_records")
    op.drop_index("ix_vendor_attendance_vendor", table_name="vendor_attendance_records")
    op.drop_index("ix_vendor_attendance_org_date", table_name="vendor_attendance_records")
    op.drop_table("vendor_attendance_records")
    op.drop_column("inspection_reports", "location_verified_at")
    op.drop_column("inspection_reports", "start_distance_meters")
    op.drop_column("inspection_reports", "start_accuracy_meters")
    op.drop_column("inspection_reports", "start_longitude")
    op.drop_column("inspection_reports", "start_latitude")
    op.drop_column("outlets", "attendance_radius_meters")
