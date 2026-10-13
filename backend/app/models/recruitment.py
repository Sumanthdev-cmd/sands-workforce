from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class JobVacancy(TimestampMixin, Base):
    __tablename__ = "job_vacancies"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    department_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_skills: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    preferred_skills: Mapped[list[str] | None] = mapped_column(JSONB)
    minimum_experience_years: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
        server_default="OPEN",
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    department = relationship("Department")
    created_by = relationship("User")


class Candidate(TimestampMixin, Base):
    __tablename__ = "candidates"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    resume_document_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("document_records.id", ondelete="SET NULL"),
        index=True,
    )
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_profile: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
        server_default="ACTIVE",
        index=True,
    )

    resume_document = relationship("DocumentRecord")


class JobApplication(TimestampMixin, Base):
    __tablename__ = "job_applications"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vacancy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("job_vacancies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    screening_score: Mapped[float | None] = mapped_column(Float)
    matched_skills: Mapped[list[str] | None] = mapped_column(JSONB)
    missing_skills: Mapped[list[str] | None] = mapped_column(JSONB)
    preferred_matches: Mapped[list[str] | None] = mapped_column(JSONB)
    screening_summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="PENDING_SCREENING",
        server_default="PENDING_SCREENING",
        index=True,
    )
    screened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    human_review_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    vacancy = relationship("JobVacancy")
    candidate = relationship("Candidate")
    created_by = relationship("User")
