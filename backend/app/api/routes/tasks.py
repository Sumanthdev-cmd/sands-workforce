from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.tasks import AdminAssignmentResponse, AssignmentCompleteRequest, AssignmentProgressRequest, MyTaskResponse, QuestionnaireSubmissionResponse, QuestionnaireSubmitRequest, TaskAssignmentCreateRequest, TaskAssignmentResponse, TaskCreateRequest, TaskProgressLogResponse, TaskResponse, TaskUpdateRequest
from app.services.task_service import add_progress, assign_task, assignment_activity, complete_assignment, create_task, employee_assignment_availability, list_my_tasks, list_progress, list_task_assignments, list_task_submissions, list_tasks, start_assignment, submit_questionnaire, update_task

router = APIRouter(prefix="/tasks", tags=["Tasks"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/me/assignments", response_model=list[MyTaskResponse])
def my_tasks(current_user: CurrentUser, database: Database, assignment_status: str | None = Query(default=None)):
    return list_my_tasks(database, current_user, assignment_status)


@router.get("/assignment-availability")
def assignment_availability(
    current_user: CurrentUser,
    database: Database,
    scheduled_for: date = Query(...),
    due_at: datetime | None = Query(default=None),
):
    return employee_assignment_availability(
        database,
        current_user,
        scheduled_for=scheduled_for,
        due_at=due_at,
    )


@router.get("/assignments/{assignment_id}/activity")
def activity(
    assignment_id: UUID,
    current_user: CurrentUser,
    database: Database,
):
    return assignment_activity(
        database,
        current_user,
        assignment_id,
    )


@router.post("/assignments/{assignment_id}/start", response_model=TaskAssignmentResponse)
def start(assignment_id: UUID, payload: AssignmentProgressRequest, current_user: CurrentUser, database: Database):
    return start_assignment(database, current_user, assignment_id, payload)


@router.post("/assignments/{assignment_id}/progress", response_model=TaskProgressLogResponse)
def progress(assignment_id: UUID, payload: AssignmentProgressRequest, current_user: CurrentUser, database: Database):
    return add_progress(database, current_user, assignment_id, payload)


@router.post("/assignments/{assignment_id}/questionnaire", response_model=QuestionnaireSubmissionResponse)
def questionnaire(assignment_id: UUID, payload: QuestionnaireSubmitRequest, current_user: CurrentUser, database: Database):
    return submit_questionnaire(database, current_user, assignment_id, payload)


@router.post("/assignments/{assignment_id}/complete", response_model=TaskAssignmentResponse)
def complete(assignment_id: UUID, payload: AssignmentCompleteRequest, current_user: CurrentUser, database: Database):
    return complete_assignment(database, current_user, assignment_id, payload)


@router.get("/assignments/{assignment_id}/progress", response_model=list[TaskProgressLogResponse])
def progress_history(assignment_id: UUID, current_user: CurrentUser, database: Database):
    return list_progress(database, current_user, assignment_id)


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create(payload: TaskCreateRequest, current_user: CurrentUser, database: Database):
    return create_task(database, current_user, payload)


@router.get("", response_model=list[TaskResponse])
def read(current_user: CurrentUser, database: Database, task_type: str | None = Query(default=None), active_only: bool = Query(default=True)):
    return list_tasks(database, current_user, task_type, active_only)


@router.patch("/{task_id}", response_model=TaskResponse)
def edit(task_id: UUID, payload: TaskUpdateRequest, current_user: CurrentUser, database: Database):
    return update_task(database, current_user, task_id, payload)


@router.post("/{task_id}/assignments", response_model=list[TaskAssignmentResponse])
def assign(task_id: UUID, payload: TaskAssignmentCreateRequest, current_user: CurrentUser, database: Database):
    return assign_task(database, current_user, task_id, payload)


@router.get("/{task_id}/assignments", response_model=list[AdminAssignmentResponse])
def assignments(task_id: UUID, current_user: CurrentUser, database: Database):
    return list_task_assignments(database, current_user, task_id)


@router.get("/{task_id}/submissions", response_model=list[QuestionnaireSubmissionResponse])
def submissions(task_id: UUID, current_user: CurrentUser, database: Database):
    return list_task_submissions(database, current_user, task_id)
