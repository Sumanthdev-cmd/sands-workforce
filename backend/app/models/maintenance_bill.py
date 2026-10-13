from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class MaintenanceBill(TimestampMixin, Base):
    __tablename__ = "maintenance_bills"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "submission_id",
            name="uq_maintenance_bill_submission",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hidden frontend identifier used only to prevent
    # accidental duplicate submission / double click.
    submission_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="GENERAL",
        server_default="GENERAL",
        index=True,
    )

    related_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="GENERAL",
        server_default="GENERAL",
        index=True,
    )

    outlet_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("outlets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    vehicle_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    property_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("property_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    company_asset_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("company_assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    vendor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Snapshot so old bills still show vendor name
    # even if vendor information changes later.
    vendor_name: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    invoice_number: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )

    bill_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Image or PDF uploaded using the existing S3 document flow.
    bill_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    submitted_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    verified_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    verification_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    md_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    decision_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    paid_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    payment_reference: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    payment_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    outlet = relationship(
        "Outlet",
        foreign_keys=[outlet_id],
    )

    vehicle = relationship(
        "Vehicle",
        foreign_keys=[vehicle_id],
    )

    property = relationship(
        "PropertyAsset",
        foreign_keys=[property_id],
    )

    company_asset = relationship(
        "CompanyAsset",
        foreign_keys=[company_asset_id],
    )

    vendor = relationship(
        "Vendor",
        foreign_keys=[vendor_id],
    )

    bill_document = relationship(
        "DocumentRecord",
        foreign_keys=[bill_document_id],
    )

    created_by = relationship(
        "User",
        foreign_keys=[created_by_user_id],
    )

    submitted_by = relationship(
        "User",
        foreign_keys=[submitted_by_user_id],
    )

    verified_by = relationship(
        "User",
        foreign_keys=[verified_by_user_id],
    )

    md_user = relationship(
        "User",
        foreign_keys=[md_user_id],
    )

    paid_by = relationship(
        "User",
        foreign_keys=[paid_by_user_id],
    )


class MaintenanceBillAction(TimestampMixin, Base):
    __tablename__ = "maintenance_bill_actions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    bill_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("maintenance_bills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    actor_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    extra_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    bill = relationship("MaintenanceBill")

    actor = relationship(
        "User",
        foreign_keys=[actor_user_id],
    )