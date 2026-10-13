"""Box loading requests and their append-only workflow history."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class BoxLoadingRequest(TimestampMixin, Base):
    __tablename__ = "box_loading_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "created_by_user_id", "client_request_id", name="uq_box_loading_create_retry"),
        CheckConstraint("status IN ('DRAFT','PENDING_MD','APPROVED','REJECTED','PAID')", name="ck_box_loading_status"),
        CheckConstraint("vehicle_type IN ('OWN','RENTED')", name="ck_box_loading_vehicle_type"),
        CheckConstraint("version >= 1", name="ck_box_loading_version"),
        CheckConstraint("loading_box_count BETWEEN 1 AND 1000000 AND loading_rate BETWEEN 0 AND 1000000", name="ck_box_loading_loading_inputs"),
        CheckConstraint("transport_box_count BETWEEN 0 AND 1000000 AND transport_rate BETWEEN 0 AND 1000000", name="ck_box_loading_transport_inputs"),
        CheckConstraint("(vehicle_type = 'OWN' AND transport_box_count = 0 AND transport_rate = 0) OR (vehicle_type = 'RENTED' AND transport_box_count > 0)", name="ck_box_loading_transport_vehicle"),
        CheckConstraint("loading_cost = round(loading_rate * loading_box_count, 2) AND transport_cost = round(transport_rate * transport_box_count, 2) AND total_amount = round(loading_cost + transport_cost, 2)", name="ck_box_loading_totals"),
        CheckConstraint("status = 'DRAFT' OR (submitted_at IS NOT NULL AND submitted_by_user_id IS NOT NULL AND total_amount > 0)", name="ck_box_loading_submitted"),
        CheckConstraint("status NOT IN ('APPROVED','PAID') OR (md_user_id IS NOT NULL AND decided_at IS NOT NULL)", name="ck_box_loading_md_approval"),
        CheckConstraint("status != 'PAID' OR (paid_at IS NOT NULL AND paid_by_user_id IS NOT NULL AND payment_date IS NOT NULL AND payment_mode IS NOT NULL AND payment_reference IS NOT NULL AND paid_to IS NOT NULL AND paid_amount IS NOT NULL AND paid_amount = total_amount)", name="ck_box_loading_disbursement"),
        CheckConstraint("payment_mode IS NULL OR payment_mode IN ('CASH','UPI','BANK_TRANSFER','CHEQUE')", name="ck_box_loading_payment_mode"),
        Index("ix_box_loading_org_date", "organization_id", "loading_date"),
        Index("ix_box_loading_org_status", "organization_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"))
    client_request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True))
    creation_fingerprint: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_by_code: Mapped[str] = mapped_column(String(50))
    loading_date: Mapped[date] = mapped_column(Date)
    vehicle_type: Mapped[str] = mapped_column(String(10))
    vehicle_number: Mapped[str] = mapped_column(String(32))
    loading_rate: Mapped[Decimal] = mapped_column(Numeric(9, 2))
    loading_box_count: Mapped[int] = mapped_column(Integer)
    transport_rate: Mapped[Decimal] = mapped_column(Numeric(9, 2), default=0)
    transport_box_count: Mapped[int] = mapped_column(Integer, default=0)
    loading_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    transport_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    submitted_by_code: Mapped[str | None] = mapped_column(String(50))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    md_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    md_code: Mapped[str | None] = mapped_column(String(50))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    paid_by_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    paid_by_code: Mapped[str | None] = mapped_column(String(50))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_date: Mapped[date | None] = mapped_column(Date)
    payment_mode: Mapped[str | None] = mapped_column(String(20))
    payment_reference: Mapped[str | None] = mapped_column(String(160))
    paid_to: Mapped[str | None] = mapped_column(String(160))
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))


class BoxLoadingAction(Base):
    __tablename__ = "box_loading_actions"
    __table_args__ = (
        UniqueConstraint("request_id", "version", name="uq_box_loading_action_version"),
        Index("ix_box_loading_actions_org_request", "organization_id", "request_id"),
    )
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"))
    request_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("box_loading_requests.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    actor_code: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
