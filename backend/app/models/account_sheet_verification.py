from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class AccountSheetVerification(TimestampMixin, Base):
    """One Accounts Manager's declared sheet-verification total for a day."""

    __tablename__ = "account_sheet_verifications"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "submission_id",
            name="uq_account_sheet_verification_submission",
        ),
        UniqueConstraint(
            "organization_id",
            "accounts_manager_employee_id",
            "verification_date",
            name="uq_account_sheet_verification_manager_day",
        ),
        CheckConstraint(
            "declared_sheet_count > 0",
            name="ck_account_sheet_verification_positive_count",
        ),
        CheckConstraint(
            "status IN ('PENDING_SECRETARY','ISSUES_OPEN','COMPLETED')",
            name="ck_account_sheet_verification_status",
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
    submission_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    accounts_manager_employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verification_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    declared_sheet_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING_SECRETARY",
        server_default="PENDING_SECRETARY",
        index=True,
    )
    submitted_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    accounts_manager = relationship(
        "Employee",
        foreign_keys=[accounts_manager_employee_id],
    )
    submitted_by = relationship(
        "User",
        foreign_keys=[submitted_by_user_id],
    )
    items = relationship(
        "AccountSheetVerificationItem",
        back_populates="verification",
        cascade="all, delete-orphan",
        order_by="AccountSheetVerificationItem.created_at",
    )


class AccountSheetVerificationItem(TimestampMixin, Base):
    """A named sheet and its Accounts Secretary/discrepancy workflow."""

    __tablename__ = "account_sheet_verification_items"

    __table_args__ = (
        UniqueConstraint(
            "verification_id",
            "sheet_name",
            "sheet_generated_on",
            name="uq_account_sheet_item_name_date",
        ),
        CheckConstraint(
            "secretary_status IN ('PENDING','VERIFIED','CONFIRMED','NOT_FOUND')",
            name="ck_account_sheet_item_secretary_status",
        ),
        CheckConstraint(
            "issue_status IN ('NONE','OPEN','RESOLVED')",
            name="ck_account_sheet_item_issue_status",
        ),
        CheckConstraint(
            "((has_discrepancy = false AND discrepancy_reason IS NULL "
            "AND discrepancy_document_id IS NULL AND issue_status = 'NONE' "
            "AND issue_raised_at IS NULL) OR "
            "(has_discrepancy = true AND discrepancy_reason IS NOT NULL "
            "AND discrepancy_document_id IS NOT NULL "
            "AND issue_status IN ('OPEN','RESOLVED') "
            "AND issue_raised_at IS NOT NULL))",
            name="ck_account_sheet_item_discrepancy_fields",
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
    verification_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("account_sheet_verifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sheet_name: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )
    sheet_generated_on: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    has_discrepancy: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    discrepancy_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    discrepancy_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_records.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    secretary_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
        index=True,
    )
    secretary_reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    secretary_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    secretary_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    issue_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="NONE",
        server_default="NONE",
        index=True,
    )
    issue_raised_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    admin_escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    md_escalated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    resolution_role: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    verification = relationship(
        "AccountSheetVerification",
        back_populates="items",
    )
    discrepancy_document = relationship(
        "DocumentRecord",
        foreign_keys=[discrepancy_document_id],
    )
    secretary_reviewed_by = relationship(
        "User",
        foreign_keys=[secretary_reviewed_by_user_id],
    )
    resolved_by = relationship(
        "User",
        foreign_keys=[resolved_by_user_id],
    )
