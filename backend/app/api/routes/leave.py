from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.leave import DecisionIn, HolidayCreate, HolidayOut, LeaveBalanceOut, LeaveRequestCreate, LeaveRequestOut, LeaveTypeCreate, LeaveTypeOut, PendingLeaveOut, PendingRegularizationOut, RegularizationCreate, RegularizationOut
from app.services.leave_service import cancel_request, create_holiday, create_type, decide_regularization, decide_request, list_holidays, list_types, my_balances, my_regularizations, my_requests, pending_regularizations, pending_requests, submit_regularization, submit_request

router = APIRouter(prefix="/leave", tags=["Leave and Holidays"])
DB = Annotated[Session, Depends(get_db)]

@router.post("/types", response_model=LeaveTypeOut, status_code=status.HTTP_201_CREATED)
def add_type(data: LeaveTypeCreate, user: CurrentUser, db: DB):
    return create_type(db, user, data)

@router.get("/types", response_model=list[LeaveTypeOut])
def get_types(user: CurrentUser, db: DB):
    return list_types(db, user)

@router.post("/holidays", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def add_holiday(data: HolidayCreate, user: CurrentUser, db: DB):
    return create_holiday(db, user, data)

@router.get("/holidays", response_model=list[HolidayOut])
def get_holidays(user: CurrentUser, db: DB, start_date: date = Query(default_factory=lambda: date(date.today().year, 1, 1)), end_date: date = Query(default_factory=lambda: date(date.today().year, 12, 31))):
    return list_holidays(db, user, start_date, end_date)

@router.get("/balances/me", response_model=list[LeaveBalanceOut])
def get_balances(user: CurrentUser, db: DB, year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2200)):
    return my_balances(db, user, year)

@router.post("/requests", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED)
def add_request(data: LeaveRequestCreate, user: CurrentUser, db: DB):
    return submit_request(db, user, data)

@router.get("/requests/me", response_model=list[LeaveRequestOut])
def get_my_requests(user: CurrentUser, db: DB):
    return my_requests(db, user)

@router.get("/requests/pending", response_model=list[PendingLeaveOut])
def get_pending_requests(user: CurrentUser, db: DB):
    return pending_requests(db, user)

@router.post("/requests/{request_id}/approve", response_model=LeaveRequestOut)
def approve_request(request_id: UUID, data: DecisionIn, user: CurrentUser, db: DB):
    return decide_request(db, user, request_id, True, data)

@router.post("/requests/{request_id}/reject", response_model=LeaveRequestOut)
def reject_request(request_id: UUID, data: DecisionIn, user: CurrentUser, db: DB):
    return decide_request(db, user, request_id, False, data)

@router.post("/requests/{request_id}/cancel", response_model=LeaveRequestOut)
def cancel_my_request(request_id: UUID, user: CurrentUser, db: DB):
    return cancel_request(db, user, request_id)

@router.post("/regularizations", response_model=RegularizationOut, status_code=status.HTTP_201_CREATED)
def add_regularization(data: RegularizationCreate, user: CurrentUser, db: DB):
    return submit_regularization(db, user, data)

@router.get("/regularizations/me", response_model=list[RegularizationOut])
def get_my_regularizations(user: CurrentUser, db: DB):
    return my_regularizations(db, user)

@router.get("/regularizations/pending", response_model=list[PendingRegularizationOut])
def get_pending_regularizations(user: CurrentUser, db: DB):
    return pending_regularizations(db, user)

@router.post("/regularizations/{item_id}/approve", response_model=RegularizationOut)
def approve_regularization(item_id: UUID, data: DecisionIn, user: CurrentUser, db: DB):
    return decide_regularization(db, user, item_id, True, data)

@router.post("/regularizations/{item_id}/reject", response_model=RegularizationOut)
def reject_regularization(item_id: UUID, data: DecisionIn, user: CurrentUser, db: DB):
    return decide_regularization(db, user, item_id, False, data)
