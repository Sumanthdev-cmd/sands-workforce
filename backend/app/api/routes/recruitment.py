from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.recruitment import (
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationStatusRequest,
    CandidateCreateRequest,
    CandidateResponse,
    VacancyCreateRequest,
    VacancyResponse,
    VacancyUpdateRequest,
)
from app.services.recruitment_service import (
    create_application,
    create_candidate,
    create_vacancy,
    list_applications,
    list_candidates,
    list_vacancies,
    screen_all_for_vacancy,
    screen_application,
    update_application_status,
    update_vacancy,
)


router = APIRouter(
    prefix="/recruitment",
    tags=["Recruitment and Resume Screening"],
)
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/vacancies",
    response_model=VacancyResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_vacancy(
    payload: VacancyCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_vacancy(database, user=current_user, payload=payload)


@router.get("/vacancies", response_model=list[VacancyResponse])
def read_vacancies(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_vacancies(database, user=current_user)


@router.patch(
    "/vacancies/{vacancy_id}",
    response_model=VacancyResponse,
)
def edit_vacancy(
    vacancy_id: UUID,
    payload: VacancyUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return update_vacancy(
        database,
        user=current_user,
        vacancy_id=vacancy_id,
        payload=payload,
    )


@router.post(
    "/candidates",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_candidate(
    payload: CandidateCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_candidate(database, user=current_user, payload=payload)


@router.get("/candidates", response_model=list[CandidateResponse])
def read_candidates(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_candidates(database, user=current_user)


@router.post(
    "/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_application(
    payload: ApplicationCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_application(database, user=current_user, payload=payload)


@router.get(
    "/applications",
    response_model=list[ApplicationResponse],
)
def read_applications(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_applications(database, user=current_user)


@router.post(
    "/applications/{application_id}/screen",
    response_model=ApplicationResponse,
)
def screen_one_application(
    application_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return screen_application(
        database,
        user=current_user,
        application_id=application_id,
    )


@router.post("/vacancies/{vacancy_id}/screen-all")
def screen_vacancy_applications(
    vacancy_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return screen_all_for_vacancy(
        database,
        user=current_user,
        vacancy_id=vacancy_id,
    )


@router.patch(
    "/applications/{application_id}/status",
    response_model=ApplicationResponse,
)
def change_application_status(
    application_id: UUID,
    payload: ApplicationStatusRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return update_application_status(
        database,
        user=current_user,
        application_id=application_id,
        new_status=payload.status,
    )
