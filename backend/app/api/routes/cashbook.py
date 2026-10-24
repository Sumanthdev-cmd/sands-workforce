"""Organisation-isolated credit/debit register. Recording does not transfer money."""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.models import Role, user_roles, DocumentRecord
from app.models.cashbook import CashbookEntry
from app.services.document_service import prepare_preview

router = APIRouter(prefix='/cashbook', tags=['Credit/Debit Record'])
DB = Annotated[Session, Depends(get_db)]

class EntryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid', allow_inf_nan=False)
    client_request_id: UUID
    transaction_date: date
    direction: Literal['CREDIT','DEBIT']
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    organization_account: str = Field(min_length=1, max_length=160)
    payment_mode: Literal['CASH','UPI','BANK_TRANSFER','CHEQUE','CARD','OTHER']
    counterparty: str = Field(min_length=1, max_length=160)
    counterparty_account: str | None = Field(None, max_length=64)
    payment_reference: str | None = Field(None, max_length=160)
    notes: str | None = Field(None, max_length=2000)
    document_id: UUID | None = None

    @field_validator('counterparty_account','payment_reference','notes')
    @classmethod
    def blanks(cls, value):
        return value or None

class VoidRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    reason: str = Field(min_length=3, max_length=2000)


def access(db, user):
    roles = set(db.scalars(select(Role.code).join(user_roles, Role.id == user_roles.c.role_id).where(
        user_roles.c.user_id == user.id, Role.organization_id == user.organization_id, Role.is_active.is_(True))))
    if not user.is_active or not roles.intersection({'CASHIER','ADMIN','MD'}):
        raise HTTPException(403, 'Cashier, Admin or MD access is required.')
    return bool(roles.intersection({'ADMIN','MD'}))


def scope(user, management):
    conditions = [CashbookEntry.organization_id == user.organization_id]
    if not management: conditions.append(CashbookEntry.created_by_user_id == user.id)
    return conditions


def output(row):
    data = {c.name: getattr(row,c.name) for c in row.__table__.columns if c.name not in {'fingerprint','client_request_id','organization_id'}}
    data['amount'] = format(row.amount, '.2f')
    data['reference'] = 'CB-' + str(row.id).replace('-','')[:12].upper()
    return data


def get_entry(db, user, entry_id, management, lock=False):
    stmt=select(CashbookEntry).where(*scope(user,management),CashbookEntry.id==entry_id)
    if lock: stmt=stmt.with_for_update()
    row=db.scalar(stmt)
    if row is None: raise HTTPException(404,'Record not found.')
    return row


@router.get('/entries')
def entries(user: CurrentUser, db: DB, from_date: date | None=None, to_date: date | None=None,
            direction: Literal['CREDIT','DEBIT'] | None=None, offset: int=Query(0,ge=0), limit: int=Query(25,ge=1,le=100)):
    management=access(db,user)
    if from_date and to_date and from_date>to_date: raise HTTPException(422,'From date must be on or before To date.')
    conditions=scope(user,management)
    if from_date:conditions.append(CashbookEntry.transaction_date>=from_date)
    if to_date:conditions.append(CashbookEntry.transaction_date<=to_date)
    if direction:conditions.append(CashbookEntry.direction==direction)
    count=db.scalar(select(func.count()).select_from(CashbookEntry).where(*conditions))
    rows=db.scalars(select(CashbookEntry).where(*conditions).order_by(CashbookEntry.transaction_date.desc(),CashbookEntry.created_at.desc(),CashbookEntry.id).offset(offset).limit(limit)).all()
    totals={}
    for kind in ['CREDIT','DEBIT']:
        total=db.scalar(select(func.coalesce(func.sum(CashbookEntry.amount),0)).where(*conditions,CashbookEntry.direction==kind,CashbookEntry.voided_at.is_(None)))
        totals[kind.lower()]=format(Decimal(total),'.2f')
    return {'items':[output(r) for r in rows],'total':count,'totals':totals,'management':management}


@router.post('/entries',status_code=201)
def create(payload: EntryCreate, user: CurrentUser, db: DB):
    access(db,user)
    today=datetime.now(ZoneInfo(user.organization.timezone or 'Asia/Kolkata')).date()
    if payload.transaction_date>today:raise HTTPException(422,'Transaction date cannot be in the future.')
    fingerprint=hashlib.sha256(payload.model_dump_json(exclude={'client_request_id'}).encode()).hexdigest()
    def previous():
        row=db.scalar(select(CashbookEntry).where(CashbookEntry.organization_id==user.organization_id,CashbookEntry.created_by_user_id==user.id,CashbookEntry.client_request_id==payload.client_request_id))
        if row and row.fingerprint!=fingerprint:raise HTTPException(409,'This save was already used for different details. Refresh the register before making another entry.')
        return row
    old=previous()
    if old:return output(old)
    if payload.document_id:
        doc=db.scalar(select(DocumentRecord).where(DocumentRecord.id==payload.document_id,DocumentRecord.organization_id==user.organization_id))
        if not doc or doc.uploaded_by_user_id!=user.id or doc.category!='CASHBOOK' or doc.status not in {'ACTIVE','VERIFIED'}:
            raise HTTPException(422,'Choose a completed supporting-document upload for this record.')
    row=CashbookEntry(**payload.model_dump(),organization_id=user.organization_id,created_by_user_id=user.id,created_by_code=user.employee_code,fingerprint=fingerprint)
    db.add(row)
    try:db.commit()
    except IntegrityError:
        db.rollback()
        old=previous()
        if old:return output(old)
        raise HTTPException(409,'Unable to save this record. Refresh and try again.')
    db.refresh(row)
    return output(row)


@router.post('/entries/{entry_id}/void')
def void(entry_id: UUID, payload: VoidRequest, user: CurrentUser, db: DB):
    management=access(db,user)
    row=get_entry(db,user,entry_id,management,lock=True)
    if row.voided_at:raise HTTPException(409,'This record is already voided.')
    row.voided_at=datetime.now(timezone.utc);row.voided_by_user_id=user.id;row.void_reason=payload.reason
    db.commit();db.refresh(row)
    return output(row)


@router.get('/entries/{entry_id}/document')
def document(entry_id: UUID, user: CurrentUser, db: DB):
    row=get_entry(db,user,entry_id,access(db,user))
    if not row.document_id:raise HTTPException(404,'No supporting document attached.')
    return prepare_preview(db,user=user,document_id=row.document_id)
