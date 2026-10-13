import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Candidate,
    Department,
    DocumentRecord,
    JobApplication,
    JobVacancy,
    Role,
    User,
    user_roles,
)
from app.schemas.recruitment import (
    ApplicationCreateRequest,
    CandidateCreateRequest,
    VacancyCreateRequest,
    VacancyUpdateRequest,
)


RECRUITMENT_ROLES = {"ADMIN", "MD", "GM", "MANAGER", "HR_RECRUITER"}


def role_codes(database: Session, user: User) -> set[str]:
    return set(
        database.scalars(
            select(Role.code)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
        ).all()
    )


def require_recruiter(database: Session, user: User) -> None:
    if not role_codes(database, user).intersection(RECRUITMENT_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruitment access is required.",
        )


def create_vacancy(
    database: Session,
    *,
    user: User,
    payload: VacancyCreateRequest,
) -> JobVacancy:
    require_recruiter(database, user)

    if payload.department_id:
        department = database.scalar(
            select(Department).where(
                Department.id == payload.department_id,
                Department.organization_id == user.organization_id,
            )
        )
        if department is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department was not found.",
            )

    row = JobVacancy(
        organization_id=user.organization_id,
        created_by_user_id=user.id,
        status="OPEN",
        **payload.model_dump(),
    )
    database.add(row)
    database.commit()
    database.refresh(row)
    return row


def list_vacancies(database: Session, *, user: User) -> list[JobVacancy]:
    require_recruiter(database, user)
    return list(
        database.scalars(
            select(JobVacancy)
            .where(JobVacancy.organization_id == user.organization_id)
            .order_by(JobVacancy.created_at.desc())
        ).all()
    )


def update_vacancy(
    database: Session,
    *,
    user: User,
    vacancy_id: UUID,
    payload: VacancyUpdateRequest,
) -> JobVacancy:
    require_recruiter(database, user)
    row = database.scalar(
        select(JobVacancy).where(
            JobVacancy.id == vacancy_id,
            JobVacancy.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vacancy was not found.",
        )
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    database.commit()
    database.refresh(row)
    return row


def parse_resume_profile(text: str) -> dict:
    lower = text.lower()
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", text)
    phone_match = re.search(r"(?:\+?\d[\d\s-]{8,}\d)", text)
    years = [
        float(value)
        for value in re.findall(
            r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?years?",
            lower,
        )
    ]
    return {
        "email_detected": email_match.group(0) if email_match else None,
        "phone_detected": phone_match.group(0) if phone_match else None,
        "maximum_experience_years_detected": max(years) if years else 0,
        "character_count": len(text),
        "word_count": len(re.findall(r"\b\w+\b", text)),
    }


def create_candidate(
    database: Session,
    *,
    user: User,
    payload: CandidateCreateRequest,
) -> Candidate:
    require_recruiter(database, user)

    if payload.resume_document_id:
        document = database.scalar(
            select(DocumentRecord).where(
                DocumentRecord.id == payload.resume_document_id,
                DocumentRecord.organization_id == user.organization_id,
            )
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Resume document was not found.",
            )

    row = Candidate(
        organization_id=user.organization_id,
        full_name=payload.full_name.strip(),
        email=payload.email.strip().lower(),
        phone=payload.phone,
        resume_document_id=payload.resume_document_id,
        resume_text=payload.resume_text,
        parsed_profile=parse_resume_profile(payload.resume_text),
        status="ACTIVE",
    )
    database.add(row)
    database.commit()
    database.refresh(row)
    return row


def list_candidates(database: Session, *, user: User) -> list[Candidate]:
    require_recruiter(database, user)
    return list(
        database.scalars(
            select(Candidate)
            .where(Candidate.organization_id == user.organization_id)
            .order_by(Candidate.created_at.desc())
        ).all()
    )


def create_application(
    database: Session,
    *,
    user: User,
    payload: ApplicationCreateRequest,
) -> JobApplication:
    require_recruiter(database, user)

    vacancy = database.scalar(
        select(JobVacancy).where(
            JobVacancy.id == payload.vacancy_id,
            JobVacancy.organization_id == user.organization_id,
        )
    )
    candidate = database.scalar(
        select(Candidate).where(
            Candidate.id == payload.candidate_id,
            Candidate.organization_id == user.organization_id,
        )
    )
    if vacancy is None or candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vacancy or candidate was not found.",
        )

    existing = database.scalar(
        select(JobApplication).where(
            JobApplication.vacancy_id == vacancy.id,
            JobApplication.candidate_id == candidate.id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This candidate already applied for the vacancy.",
        )

    row = JobApplication(
        organization_id=user.organization_id,
        vacancy_id=vacancy.id,
        candidate_id=candidate.id,
        created_by_user_id=user.id,
        status="PENDING_SCREENING",
        human_review_required=False,
    )
    database.add(row)
    database.commit()
    database.refresh(row)
    return row


def list_applications(database: Session, *, user: User) -> list[JobApplication]:
    require_recruiter(database, user)
    return list(
        database.scalars(
            select(JobApplication)
            .where(JobApplication.organization_id == user.organization_id)
            .order_by(JobApplication.created_at.desc())
        ).all()
    )


def skill_present(skill: str, resume_text: str) -> bool:
    normalized_skill = re.sub(r"\s+", " ", skill.strip().lower())
    normalized_resume = re.sub(r"\s+", " ", resume_text.lower())
    return normalized_skill in normalized_resume


def screen_application(
    database: Session,
    *,
    user: User,
    application_id: UUID,
) -> JobApplication:
    require_recruiter(database, user)
    row = database.scalar(
        select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application was not found.",
        )

    vacancy = database.get(JobVacancy, row.vacancy_id)
    candidate = database.get(Candidate, row.candidate_id)
    if vacancy is None or candidate is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application references are incomplete.",
        )

    required = vacancy.required_skills or []
    preferred = vacancy.preferred_skills or []
    matched = [skill for skill in required if skill_present(skill, candidate.resume_text)]
    missing = [skill for skill in required if skill not in matched]
    preferred_matches = [
        skill for skill in preferred if skill_present(skill, candidate.resume_text)
    ]

    required_score = (
        (len(matched) / len(required)) * 80 if required else 80
    )
    preferred_score = (
        (len(preferred_matches) / len(preferred)) * 20 if preferred else 20
    )
    score = round(required_score + preferred_score, 2)

    experience = float(
        (candidate.parsed_profile or {}).get(
            "maximum_experience_years_detected",
            0,
        )
    )
    experience_ok = experience >= vacancy.minimum_experience_years
    if not experience_ok:
        score = round(max(0, score - 15), 2)

    if score >= 70 and experience_ok:
        decision = "AUTO_SHORTLISTED"
        review_required = False
    elif score < 40:
        decision = "AUTO_REJECTED"
        review_required = False
    else:
        decision = "NEEDS_REVIEW"
        review_required = True

    row.screening_score = score
    row.matched_skills = matched
    row.missing_skills = missing
    row.preferred_matches = preferred_matches
    row.status = decision
    row.human_review_required = review_required
    row.screened_at = datetime.now(timezone.utc)
    row.screening_summary = (
        f"Matched {len(matched)}/{len(required)} required skills and "
        f"{len(preferred_matches)}/{len(preferred)} preferred skills. "
        f"Detected experience: {experience} years. Decision: {decision}."
    )

    database.commit()
    database.refresh(row)
    return row


def screen_all_for_vacancy(
    database: Session,
    *,
    user: User,
    vacancy_id: UUID,
) -> dict:
    require_recruiter(database, user)
    rows = list(
        database.scalars(
            select(JobApplication).where(
                JobApplication.organization_id == user.organization_id,
                JobApplication.vacancy_id == vacancy_id,
            )
        ).all()
    )
    results = []
    for row in rows:
        screened = screen_application(
            database,
            user=user,
            application_id=row.id,
        )
        results.append(
            {
                "application_id": str(screened.id),
                "score": screened.screening_score,
                "status": screened.status,
            }
        )
    return {
        "vacancy_id": str(vacancy_id),
        "screened_count": len(results),
        "results": results,
    }


def update_application_status(
    database: Session,
    *,
    user: User,
    application_id: UUID,
    new_status: str,
) -> JobApplication:
    require_recruiter(database, user)
    row = database.scalar(
        select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.organization_id == user.organization_id,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application was not found.",
        )
    row.status = new_status.strip().upper()
    database.commit()
    database.refresh(row)
    return row
