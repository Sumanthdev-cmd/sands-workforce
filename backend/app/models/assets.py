from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Vehicle(TimestampMixin, Base):
    """Company or employee-linked vehicle record."""

    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "registration_number",
            name="uq_vehicle_org_registration",
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
    code: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )
    registration_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    ownership_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="COMPANY",
        server_default="COMPANY",
    )
    employee_owner_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vehicle_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    make: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    fuel_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    expected_mileage_kmpl: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2),
        nullable=True,
    )
    manufacture_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    insurance_expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    registration_expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    pollution_expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    extra_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    employee_owner = relationship("Employee")


class PropertyAsset(TimestampMixin, Base):
    """Organisation property and tax-renewal record."""

    __tablename__ = "property_assets"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_property_org_code",
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
    code: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )
    property_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    cluster_name: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
        index=True,
    )
    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    vendor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tax_identifier: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    last_tax_paid_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    next_tax_due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    extra_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )


class Outlet(TimestampMixin, Base):
    """Outlet, vendor, licence, blueprint, and location information."""

    __tablename__ = "outlets"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_outlet_org_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    outlet_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    address: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # -------------------------------------------------
    # CLUSTER / LOCATION
    # -------------------------------------------------

    cluster_name: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
        index=True,
    )

    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7),
        nullable=True,
    )

    attendance_radius_meters: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=150.0,
        server_default="150",
    )

    # -------------------------------------------------
    # VENDOR
    # -------------------------------------------------

    vendor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "vendors.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    vendor_name: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    vendor_contact_person: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    vendor_phone: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    vendor_email: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    assistant_vendor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "vendors.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    assistant_vendor_name: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    assistant_vendor_contact_person: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    assistant_vendor_phone: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    assistant_vendor_email: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    parcel_vendor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "vendors.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    parcel_vendor_name: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    parcel_vendor_contact_person: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    parcel_vendor_phone: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    parcel_vendor_email: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    # -------------------------------------------------
    # OUTLET DETAILS
    # -------------------------------------------------

    opening_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    # -------------------------------------------------
    # LICENCE
    # -------------------------------------------------

    licence_number: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    licence_expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    # -------------------------------------------------
    # EXCISE
    # -------------------------------------------------

    excise_licence_number: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    excise_expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    # -------------------------------------------------
    # RENT AGREEMENT
    # -------------------------------------------------

    rent_agreement_expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    # -------------------------------------------------
    # BLUEPRINT / DOCUMENT
    # -------------------------------------------------

    blueprint_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "document_records.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # -------------------------------------------------
    # STATUS
    # -------------------------------------------------

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    extra_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
        index=True,
    )

    # -------------------------------------------------
    # RELATIONSHIPS
    # -------------------------------------------------

    blueprint_document = relationship(
        "DocumentRecord",
        foreign_keys=[blueprint_document_id],
    )

    vendor = relationship(
        "Vendor",
        foreign_keys=[vendor_id],
    )

    assistant_vendor = relationship(
        "Vendor",
        foreign_keys=[assistant_vendor_id],
    )

    parcel_vendor = relationship(
        "Vendor",
        foreign_keys=[parcel_vendor_id],
    )
