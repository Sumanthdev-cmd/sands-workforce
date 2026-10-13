from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Vendor(TimestampMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_vendor_org_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(180))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(180))
    address: Mapped[str | None] = mapped_column(Text)
    service_category: Mapped[str | None] = mapped_column(String(100))
    deposit_amount: Mapped[float | None] = mapped_column(Float)
    deposit_payment_mode: Mapped[str | None] = mapped_column(String(30))
    deposit_reference: Mapped[str | None] = mapped_column(String(180))
    deposit_received_on: Mapped[date | None] = mapped_column(Date)
    deposit_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_records.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)


class VendorDepositRefund(TimestampMixin, Base):
    __tablename__ = "vendor_deposit_refunds"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    refund_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_reference: Mapped[str | None] = mapped_column(String(180))
    supporting_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_records.id", ondelete="SET NULL"),
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING_MD",
        server_default="PENDING_MD",
        index=True,
    )
    md_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)

    vendor = relationship("Vendor")
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    md_user = relationship("User", foreign_keys=[md_user_id])


class ShopRental(TimestampMixin, Base):
    __tablename__ = "shop_rentals"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rental_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    building_name: Mapped[str] = mapped_column(String(180), nullable=False)
    building_code: Mapped[str | None] = mapped_column(String(80), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    counterparty_name: Mapped[str] = mapped_column(String(180), nullable=False)
    counterparty_contact: Mapped[str | None] = mapped_column(String(80))
    agreement_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    agreement_end_date: Mapped[date | None] = mapped_column(Date, index=True)
    monthly_rent_amount: Mapped[float] = mapped_column(Float, nullable=False)
    advance_amount: Mapped[float | None] = mapped_column(Float)
    advance_payment_mode: Mapped[str | None] = mapped_column(String(30))
    advance_paid_on: Mapped[date | None] = mapped_column(Date)
    advance_reference: Mapped[str | None] = mapped_column(String(180))
    agreement_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_records.id", ondelete="SET NULL"),
        index=True,
    )
    advance_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_records.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text)


class ShopRentalAdvanceRefund(TimestampMixin, Base):
    __tablename__ = "shop_rental_advance_refunds"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rental_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("shop_rentals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    refund_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_reference: Mapped[str | None] = mapped_column(String(180))
    supporting_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_records.id", ondelete="SET NULL"),
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING_MD",
        server_default="PENDING_MD",
        index=True,
    )
    md_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)

    rental = relationship("ShopRental")
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    md_user = relationship("User", foreign_keys=[md_user_id])


class VendorIssue(TimestampMixin, Base):
    __tablename__ = "vendor_issues"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="SET NULL"),
        index=True,
    )
    outlet_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("outlets.id", ondelete="SET NULL"),
        index=True,
    )
    raised_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_to_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        default="GENERAL",
        server_default="GENERAL",
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MEDIUM",
        server_default="MEDIUM",
        index=True,
    )
    evidence_urls: Mapped[list[str] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
        server_default="OPEN",
        index=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    vendor = relationship("Vendor")
    outlet = relationship("Outlet")
    raised_by = relationship("User", foreign_keys=[raised_by_user_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_user_id])


class VendorIssueAction(TimestampMixin, Base):
    __tablename__ = "vendor_issue_actions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    issue_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vendor_issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)

    issue = relationship("VendorIssue")
    actor = relationship("User")


class ExternalLabourPayment(TimestampMixin, Base):
    __tablename__ = "external_labour_payments"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    labour_name: Mapped[str] = mapped_column(String(180), nullable=False)
    labour_phone: Mapped[str | None] = mapped_column(String(40))
    work_description: Mapped[str] = mapped_column(Text, nullable=False)
    work_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    work_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(10), nullable=False, default="INR", server_default="INR"
    )
    evidence_urls: Mapped[list[str] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING_MD",
        server_default="PENDING_MD",
        index=True,
    )
    md_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    decision_note: Mapped[str | None] = mapped_column(Text)
    paid_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(180))

    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
    md_user = relationship("User", foreign_keys=[md_user_id])
    paid_by = relationship("User", foreign_keys=[paid_by_user_id])


class ExternalLabourPaymentAction(TimestampMixin, Base):
    __tablename__ = "external_labour_payment_actions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("external_labour_payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)

    payment = relationship("ExternalLabourPayment")
    actor = relationship("User")


class Wing(TimestampMixin, Base):
    __tablename__ = "wings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_wing_org_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
        index=True,
    )


class WingContact(TimestampMixin, Base):
    __tablename__ = "wing_contacts"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wing_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("wings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_name: Mapped[str] = mapped_column(String(180), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(180), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(180))
    address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    wing = relationship("Wing")
