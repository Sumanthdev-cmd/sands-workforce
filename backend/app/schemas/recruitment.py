from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VacancyCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    department_id: UUID | None = None
    description: str = Field(min_length=10, max_length=10000)
    required_skills: list[str] = Field(min_length=1, max_length=100)
    preferred_skills: list[str] = Field(default_factory=list, max_length=100)
    minimum_experience_years: float = Field(default=0, ge=0, le=80)

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def normalize_skills(cls, values: list[str]) -> list[str]:
        cleaned = []
        seen = set()
        for value in values:
            item = value.strip()
            if item and item.lower() not in seen:
                cleaned.append(item)
                seen.add(item.lower())
        return cleaned


class VacancyUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=180)
    description: str | None = Field(default=None, max_length=10000)
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    minimum_experience_years: float | None = Field(default=None, ge=0, le=80)
    status: str | None = Field(default=None, max_length=30)


class VacancyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    department_id: UUID | None
    description: str
    required_skills: list[str]
    preferred_skills: list[str] | None
    minimum_experience_years: float
    status: str
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class CandidateCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=180)
    email: str = Field(min_length=5, max_length=180)
    phone: str | None = Field(default=None, max_length=40)
    resume_document_id: UUID | None = None
    resume_text: str = Field(min_length=20, max_length=200000)


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str
    phone: str | None
    resume_document_id: UUID | None
    resume_text: str
    parsed_profile: dict | None
    status: str
    created_at: datetime
    updated_at: datetime


class ApplicationCreateRequest(BaseModel):
    vacancy_id: UUID
    candidate_id: UUID


class ApplicationStatusRequest(BaseModel):
    status: str = Field(min_length=2, max_length=40)


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vacancy_id: UUID
    candidate_id: UUID
    screening_score: float | None
    matched_skills: list[str] | None
    missing_skills: list[str] | None
    preferred_matches: list[str] | None
    screening_summary: str | None
    status: str
    screened_at: datetime | None
    human_review_required: bool
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
