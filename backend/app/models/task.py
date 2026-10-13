from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, false, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    geofence_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("geofences.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False, default="TASK", server_default="TASK", index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM", server_default="MEDIUM", index=True)
    recurrence_type: Mapped[str] = mapped_column(String(20), nullable=False, default="NONE", server_default="NONE")
    recurrence_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    recurrence_days: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    location_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    questionnaire_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())

    geofence = relationship("Geofence")
    created_by = relationship("User")


class TaskAssignment(TimestampMixin, Base):
    __tablename__ = "task_assignments"
    __table_args__ = (
        UniqueConstraint("task_id", "employee_id", "scheduled_for", name="uq_task_assignment_employee_date"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ASSIGNED", server_default="ASSIGNED", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    completion_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    task = relationship("Task")
    employee = relationship("Employee")
    assigned_by = relationship("User")


class TaskProgressLog(TimestampMixin, Base):
    __tablename__ = "task_progress_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("task_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    assignment = relationship("TaskAssignment")
    actor = relationship("User")


class QuestionnaireSubmission(TimestampMixin, Base):
    __tablename__ = "questionnaire_submissions"
    __table_args__ = (UniqueConstraint("assignment_id", name="uq_questionnaire_submission_assignment"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("task_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())

    assignment = relationship("TaskAssignment")
    employee = relationship("Employee")
