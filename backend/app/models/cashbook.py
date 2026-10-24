"""Immutable cashbook entries; corrections retain the original record."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import String, Text, Numeric, Date, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class CashbookEntry(Base):
    __tablename__ = 'cashbook_entries'
    __table_args__ = (
        UniqueConstraint('organization_id', 'created_by_user_id', 'client_request_id', name='uq_cashbook_request'),
        CheckConstraint('amount > 0', name='ck_cashbook_positive'),
        CheckConstraint("direction IN ('CREDIT','DEBIT')", name='ck_cashbook_direction'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey('organizations.id'), index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    created_by_code: Mapped[str] = mapped_column(String(100))
    client_request_id: Mapped[UUID] = mapped_column(Uuid)
    fingerprint: Mapped[str] = mapped_column(String(64))
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    direction: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(16,2))
    organization_account: Mapped[str] = mapped_column(String(160))
    payment_mode: Mapped[str] = mapped_column(String(30))
    counterparty: Mapped[str] = mapped_column(String(160))
    counterparty_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey('document_records.id', ondelete='RESTRICT'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
