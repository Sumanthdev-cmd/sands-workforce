from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class VehicleFuelIndent(TimestampMixin, Base):
    __tablename__ = "vehicle_fuel_indents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "indent_number",
            name="uq_vehicle_fuel_indent_org_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    indent_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="REQUESTED", server_default="REQUESTED", index=True
    )

    odometer_km: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    requested_quantity_litres: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    requested_amount_rupees: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    fuel_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    actual_quantity_litres: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    actual_amount_rupees: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    price_per_litre: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    fuel_station: Mapped[str | None] = mapped_column(String(180))
    bill_number: Mapped[str | None] = mapped_column(String(120))
    receipt_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_records.id", ondelete="SET NULL"),
        index=True,
    )

    previous_fuel_indent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vehicle_fuel_indents.id", ondelete="SET NULL"),
        index=True,
    )
    previous_odometer_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    distance_since_previous_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    interval_fuel_quantity_litres: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    interval_fuel_amount_rupees: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    actual_mileage_kmpl: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    expected_mileage_kmpl_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    mileage_difference_kmpl: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    mileage_variance_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    mileage_status: Mapped[str | None] = mapped_column(String(30), index=True)
    interval_cost_per_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))

    notes: Mapped[str | None] = mapped_column(Text)

    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    fueled_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    canceled_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    fueled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    vehicle = relationship("Vehicle")
    receipt_document = relationship("DocumentRecord")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    fueled_by = relationship("User", foreign_keys=[fueled_by_user_id])
    canceled_by = relationship("User", foreign_keys=[canceled_by_user_id])
    previous_fuel_indent = relationship(
        "VehicleFuelIndent",
        remote_side=[id],
        foreign_keys=[previous_fuel_indent_id],
    )
