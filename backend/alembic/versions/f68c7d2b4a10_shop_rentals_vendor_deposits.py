"""Shop rentals, vendor deposits and GM late inspection approval.

Revision ID: f68c7d2b4a10
Revises: e21d4f87a9b2
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f68c7d2b4a10"
down_revision: Union[str, Sequence[str], None] = "e21d4f87a9b2"
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
    op.add_column("vendors", sa.Column("deposit_amount", sa.Float(), nullable=True))
    op.add_column("vendors", sa.Column("deposit_payment_mode", sa.String(length=30), nullable=True))
    op.add_column("vendors", sa.Column("deposit_reference", sa.String(length=180), nullable=True))
    op.add_column("vendors", sa.Column("deposit_received_on", sa.Date(), nullable=True))
    op.add_column("vendors", sa.Column("deposit_document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_vendors_deposit_document_id_document_records",
        "vendors",
        "document_records",
        ["deposit_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_vendors_deposit_document_id", "vendors", ["deposit_document_id"])

    op.create_table(
        "vendor_deposit_refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("payment_mode", sa.String(length=30), nullable=False),
        sa.Column("refund_date", sa.Date(), nullable=False),
        sa.Column("payment_reference", sa.String(length=180), nullable=True),
        sa.Column("supporting_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING_MD"),
        sa.Column("md_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supporting_document_id"], ["document_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["md_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendor_deposit_refunds_organization_id", "vendor_deposit_refunds", ["organization_id"])
    op.create_index("ix_vendor_deposit_refunds_vendor_id", "vendor_deposit_refunds", ["vendor_id"])
    op.create_index("ix_vendor_deposit_refunds_status", "vendor_deposit_refunds", ["status"])
    op.create_index("ix_vendor_deposit_refunds_refund_date", "vendor_deposit_refunds", ["refund_date"])

    op.create_table(
        "shop_rentals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rental_type", sa.String(length=30), nullable=False),
        sa.Column("building_name", sa.String(length=180), nullable=False),
        sa.Column("building_code", sa.String(length=80), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("counterparty_name", sa.String(length=180), nullable=False),
        sa.Column("counterparty_contact", sa.String(length=80), nullable=True),
        sa.Column("agreement_start_date", sa.Date(), nullable=False),
        sa.Column("agreement_end_date", sa.Date(), nullable=True),
        sa.Column("monthly_rent_amount", sa.Float(), nullable=False),
        sa.Column("advance_amount", sa.Float(), nullable=True),
        sa.Column("advance_payment_mode", sa.String(length=30), nullable=True),
        sa.Column("advance_paid_on", sa.Date(), nullable=True),
        sa.Column("advance_reference", sa.String(length=180), nullable=True),
        sa.Column("agreement_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("advance_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="ACTIVE"),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agreement_document_id"], ["document_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["advance_document_id"], ["document_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shop_rentals_organization_id", "shop_rentals", ["organization_id"])
    op.create_index("ix_shop_rentals_rental_type", "shop_rentals", ["rental_type"])
    op.create_index("ix_shop_rentals_building_code", "shop_rentals", ["building_code"])
    op.create_index("ix_shop_rentals_agreement_end_date", "shop_rentals", ["agreement_end_date"])
    op.create_index("ix_shop_rentals_status", "shop_rentals", ["status"])
    op.create_index("ix_shop_rentals_agreement_document_id", "shop_rentals", ["agreement_document_id"])
    op.create_index("ix_shop_rentals_advance_document_id", "shop_rentals", ["advance_document_id"])

    op.create_table(
        "shop_rental_advance_refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rental_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("payment_mode", sa.String(length=30), nullable=False),
        sa.Column("refund_date", sa.Date(), nullable=False),
        sa.Column("payment_reference", sa.String(length=180), nullable=True),
        sa.Column("supporting_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING_MD"),
        sa.Column("md_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rental_id"], ["shop_rentals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supporting_document_id"], ["document_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["md_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shop_rental_advance_refunds_organization_id", "shop_rental_advance_refunds", ["organization_id"])
    op.create_index("ix_shop_rental_advance_refunds_rental_id", "shop_rental_advance_refunds", ["rental_id"])
    op.create_index("ix_shop_rental_advance_refunds_status", "shop_rental_advance_refunds", ["status"])
    op.create_index("ix_shop_rental_advance_refunds_refund_date", "shop_rental_advance_refunds", ["refund_date"])


def downgrade() -> None:
    op.drop_index("ix_shop_rental_advance_refunds_refund_date", table_name="shop_rental_advance_refunds")
    op.drop_index("ix_shop_rental_advance_refunds_status", table_name="shop_rental_advance_refunds")
    op.drop_index("ix_shop_rental_advance_refunds_rental_id", table_name="shop_rental_advance_refunds")
    op.drop_index("ix_shop_rental_advance_refunds_organization_id", table_name="shop_rental_advance_refunds")
    op.drop_table("shop_rental_advance_refunds")

    op.drop_index("ix_shop_rentals_advance_document_id", table_name="shop_rentals")
    op.drop_index("ix_shop_rentals_agreement_document_id", table_name="shop_rentals")
    op.drop_index("ix_shop_rentals_status", table_name="shop_rentals")
    op.drop_index("ix_shop_rentals_agreement_end_date", table_name="shop_rentals")
    op.drop_index("ix_shop_rentals_building_code", table_name="shop_rentals")
    op.drop_index("ix_shop_rentals_rental_type", table_name="shop_rentals")
    op.drop_index("ix_shop_rentals_organization_id", table_name="shop_rentals")
    op.drop_table("shop_rentals")

    op.drop_index("ix_vendor_deposit_refunds_refund_date", table_name="vendor_deposit_refunds")
    op.drop_index("ix_vendor_deposit_refunds_status", table_name="vendor_deposit_refunds")
    op.drop_index("ix_vendor_deposit_refunds_vendor_id", table_name="vendor_deposit_refunds")
    op.drop_index("ix_vendor_deposit_refunds_organization_id", table_name="vendor_deposit_refunds")
    op.drop_table("vendor_deposit_refunds")

    op.drop_index("ix_vendors_deposit_document_id", table_name="vendors")
    op.drop_constraint("fk_vendors_deposit_document_id_document_records", "vendors", type_="foreignkey")
    op.drop_column("vendors", "deposit_document_id")
    op.drop_column("vendors", "deposit_received_on")
    op.drop_column("vendors", "deposit_reference")
    op.drop_column("vendors", "deposit_payment_mode")
    op.drop_column("vendors", "deposit_amount")
