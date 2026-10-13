from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    String,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Department(TimestampMixin, Base):
    """An organizational department."""

    __tablename__ = "departments"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_departments_organization_code",
        ),
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_departments_organization_name",
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
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )