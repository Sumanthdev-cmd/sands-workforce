from datetime import date, time
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Geofence(TimestampMixin, Base):
    """A circular work-location boundary."""

    __tablename__ = "geofences"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            name="uq_geofences_organization_code",
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
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    geofence_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OFFICE",
        server_default="OFFICE",
    )

    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    radius_meters: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=150.0,
        server_default="150",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )


class EmployeeGeofenceAssignment(TimestampMixin, Base):
    """An employee's assigned work location and shift timing."""

    __tablename__ = "employee_geofence_assignments"

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "geofence_id",
            name="uq_employee_geofence_assignment",
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

    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    geofence_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("geofences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    valid_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    shift_start_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
        default=time(9, 0),
        server_default="09:00:00",
    )

    shift_end_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
        default=time(18, 0),
        server_default="18:00:00",
    )

    grace_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=15,
        server_default="15",
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )

    employee = relationship("Employee")
    geofence = relationship("Geofence")
