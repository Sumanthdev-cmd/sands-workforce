from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class InspectionTemplate(TimestampMixin, Base):
    __tablename__ = "inspection_templates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "code",
            "version",
            name="uq_inspection_template_org_code_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schema_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true(), index=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class InspectionReport(TimestampMixin, Base):
    __tablename__ = "inspection_reports"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "report_number",
            name="uq_inspection_report_org_number",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inspection_templates.id", ondelete="RESTRICT"), nullable=False
    )
    report_number: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    previous_report_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inspection_reports.id", ondelete="SET NULL"), index=True
    )

    outlet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("outlets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), index=True
    )
    task_assignment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("task_assignments.id", ondelete="SET NULL"), index=True
    )
    inspector_employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inspector_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    cluster_name: Mapped[str | None] = mapped_column(String(180))
    inspection_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    start_latitude: Mapped[float | None] = mapped_column(Float)
    start_longitude: Mapped[float | None] = mapped_column(Float)
    start_accuracy_meters: Mapped[float | None] = mapped_column(Float)
    start_distance_meters: Mapped[float | None] = mapped_column(Float)
    location_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    ho_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ho_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ho_acknowledged_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    ho_acknowledgement_note: Mapped[str | None] = mapped_column(Text)

    template_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    section_remarks: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    attention_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="DRAFT", server_default="DRAFT", index=True
    )

    inspector_signature_data_uri: Mapped[str | None] = mapped_column(Text)

    vendor_name_snapshot: Mapped[str | None] = mapped_column(String(180))
    vendor_contact_name: Mapped[str | None] = mapped_column(String(180))
    vendor_contact_email: Mapped[str | None] = mapped_column(String(180))
    vendor_contact_phone: Mapped[str | None] = mapped_column(String(40))
    vendor_access_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    vendor_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    vendor_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vendor_response: Mapped[str | None] = mapped_column(String(20), index=True)
    vendor_response_name: Mapped[str | None] = mapped_column(String(180))
    vendor_remarks: Mapped[str | None] = mapped_column(Text)
    vendor_signature_data_uri: Mapped[str | None] = mapped_column(Text)
    vendor_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vendor_response_ip: Mapped[str | None] = mapped_column(String(80))
    vendor_response_user_agent: Mapped[str | None] = mapped_column(String(500))

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    template = relationship("InspectionTemplate")
    outlet = relationship("Outlet")
    vendor = relationship("Vendor")
    inspector_employee = relationship("Employee")
    inspector_user = relationship("User", foreign_keys=[inspector_user_id])
    previous_report = relationship("InspectionReport", remote_side=[id], foreign_keys=[previous_report_id])

    @property
    def outlet_name(self) -> str | None:
        """Expose the related shop identity to authenticated report responses."""
        return getattr(self.outlet, "name", None)

    @property
    def outlet_code(self) -> str | None:
        return getattr(self.outlet, "code", None)

    @property
    def outlet_address(self) -> str | None:
        return getattr(self.outlet, "address", None)


class InspectionAuditEvent(TimestampMixin, Base):
    __tablename__ = "inspection_audit_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inspection_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(80))
    user_agent: Mapped[str | None] = mapped_column(String(500))
