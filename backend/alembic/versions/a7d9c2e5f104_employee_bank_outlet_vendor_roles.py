"""Employee bank details and shop vendor roles.

Revision ID: a7d9c2e5f104
Revises: f68c7d2b4a10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a7d9c2e5f104"
down_revision: Union[str, Sequence[str], None] = "f68c7d2b4a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("bank_name", sa.String(length=180), nullable=True))
    op.add_column("employees", sa.Column("bank_ifsc", sa.String(length=20), nullable=True))
    op.add_column("employees", sa.Column("bank_account_number", sa.String(length=40), nullable=True))
    op.add_column("employees", sa.Column("last_working_day", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("separation_type", sa.String(length=30), nullable=True))
    op.add_column("employees", sa.Column("separation_reason", sa.String(length=5000), nullable=True))

    op.add_column("outlets", sa.Column("assistant_vendor_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("outlets", sa.Column("assistant_vendor_name", sa.String(length=180), nullable=True))
    op.add_column("outlets", sa.Column("assistant_vendor_contact_person", sa.String(length=180), nullable=True))
    op.add_column("outlets", sa.Column("assistant_vendor_phone", sa.String(length=40), nullable=True))
    op.add_column("outlets", sa.Column("assistant_vendor_email", sa.String(length=180), nullable=True))
    op.add_column("outlets", sa.Column("parcel_vendor_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("outlets", sa.Column("parcel_vendor_name", sa.String(length=180), nullable=True))
    op.add_column("outlets", sa.Column("parcel_vendor_contact_person", sa.String(length=180), nullable=True))
    op.add_column("outlets", sa.Column("parcel_vendor_phone", sa.String(length=40), nullable=True))
    op.add_column("outlets", sa.Column("parcel_vendor_email", sa.String(length=180), nullable=True))
    op.create_index("ix_outlets_assistant_vendor_id", "outlets", ["assistant_vendor_id"])
    op.create_index("ix_outlets_parcel_vendor_id", "outlets", ["parcel_vendor_id"])
    op.create_foreign_key(
        "fk_outlets_assistant_vendor_id_vendors",
        "outlets",
        "vendors",
        ["assistant_vendor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_outlets_parcel_vendor_id_vendors",
        "outlets",
        "vendors",
        ["parcel_vendor_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_outlets_parcel_vendor_id_vendors", "outlets", type_="foreignkey")
    op.drop_constraint("fk_outlets_assistant_vendor_id_vendors", "outlets", type_="foreignkey")
    op.drop_index("ix_outlets_parcel_vendor_id", table_name="outlets")
    op.drop_index("ix_outlets_assistant_vendor_id", table_name="outlets")
    op.drop_column("outlets", "parcel_vendor_email")
    op.drop_column("outlets", "parcel_vendor_phone")
    op.drop_column("outlets", "parcel_vendor_contact_person")
    op.drop_column("outlets", "parcel_vendor_name")
    op.drop_column("outlets", "parcel_vendor_id")
    op.drop_column("outlets", "assistant_vendor_email")
    op.drop_column("outlets", "assistant_vendor_phone")
    op.drop_column("outlets", "assistant_vendor_contact_person")
    op.drop_column("outlets", "assistant_vendor_name")
    op.drop_column("outlets", "assistant_vendor_id")

    op.drop_column("employees", "separation_reason")
    op.drop_column("employees", "separation_type")
    op.drop_column("employees", "last_working_day")
    op.drop_column("employees", "bank_account_number")
    op.drop_column("employees", "bank_ifsc")
    op.drop_column("employees", "bank_name")
