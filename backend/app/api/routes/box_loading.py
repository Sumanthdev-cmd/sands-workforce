from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.box_loading import CreateBoxLoading, DecisionRequest, DisbursementRequest, UpdateBoxLoading, VersionRequest
from app.services import box_loading_service as service

router = APIRouter(prefix="/box-loading", tags=["Box Loading"])
DB = Annotated[Session, Depends(get_db)]


@router.get("/version")
def version():
    return {"version": 1}


@router.get("/requests")
def list_requests(user: CurrentUser, database: DB, from_date: date | None = None, to_date: date | None = None,
                  status: str | None = None, search: str = Query("", max_length=100),
                  offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    return service.list_requests(database, user, from_date=from_date, to_date=to_date, status=status,
                                 search=search, offset=offset, limit=limit)


@router.post("/requests", status_code=201)
def create(payload: CreateBoxLoading, user: CurrentUser, database: DB):
    return service.create_request(database, user, payload)


@router.get("/requests/{request_id}")
def detail(request_id: UUID, user: CurrentUser, database: DB):
    return service.request_detail(database, user, request_id)


@router.put("/requests/{request_id}")
def update(request_id: UUID, payload: UpdateBoxLoading, user: CurrentUser, database: DB):
    return service.update_request(database, user, request_id, payload)


@router.post("/requests/{request_id}/submit")
def submit(request_id: UUID, payload: VersionRequest, user: CurrentUser, database: DB):
    return service.submit_request(database, user, request_id, payload)


@router.post("/requests/{request_id}/decision")
def decide(request_id: UUID, payload: DecisionRequest, user: CurrentUser, database: DB):
    return service.decide_request(database, user, request_id, payload)


@router.post("/requests/{request_id}/disbursement")
def disburse(request_id: UUID, payload: DisbursementRequest, user: CurrentUser, database: DB):
    return service.record_disbursement(database, user, request_id, payload)
