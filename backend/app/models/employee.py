from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    String,
    UniqueConstraint,
    false,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.designation import Designation
    from app.models.organization import Organization
    from app.models.user import User


class Employee(TimestampMixin, Base):
    """Employment profile connected to a login user."""

    __tablename__ = "employees"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            name="uq_employees_user_id",
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

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    department_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "departments.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    designation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "designations.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    manager_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "employees.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    phone: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    bank_name: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )

    bank_ifsc: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    bank_account_number: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    date_of_joining: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    employment_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="FULL_TIME",
        server_default="FULL_TIME",
    )

    employment_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
    )

    last_working_day: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    separation_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    separation_reason: Mapped[str | None] = mapped_column(
        String(5000),
        nullable=True,
    )

    is_field_employee: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    organization: Mapped[Organization] = relationship()

    user: Mapped[User] = relationship()

    department: Mapped[Department | None] = relationship()

    designation: Mapped[Designation | None] = relationship()

    manager: Mapped[Employee | None] = relationship(
        remote_side="Employee.id",
        back_populates="subordinates",
        foreign_keys=[manager_id],
    )

    subordinates: Mapped[list[Employee]] = relationship(
        back_populates="manager",
        foreign_keys=[manager_id],
    )

    @property
    def full_name(self) -> str:
        """Return the employee's combined display name."""

        if self.last_name:
            return f"{self.first_name} {self.last_name}"

        return self.first_name
