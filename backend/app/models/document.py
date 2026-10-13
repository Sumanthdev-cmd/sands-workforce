from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class DocumentRecord(TimestampMixin, Base):
    """Metadata for a file stored in the organisation's document bucket."""

    __tablename__ = "document_records"

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
    owner_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    file_size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    s3_bucket: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    s3_key: Mapped[str] = mapped_column(
        String(700),
        nullable=False,
        unique=True,
        index=True,
    )
    etag: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    issue_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    expiry_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    alert_days_before: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default="30",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="UPLOAD_PENDING",
        server_default="UPLOAD_PENDING",
        index=True,
    )
    is_confidential: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
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
    extra_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    uploaded_by = relationship(
        "User",
        foreign_keys=[uploaded_by_user_id],
    )
    verified_by = relationship(
        "User",
        foreign_keys=[verified_by_user_id],
    )
