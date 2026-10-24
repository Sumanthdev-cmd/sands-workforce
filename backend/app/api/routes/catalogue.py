from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.services.operations_service import require_roles
from app.services.catalogue_service import ensure_not_archived, load_person, settlement_blockers, audit, organization_date

router = APIRouter(prefix="/catalogue", tags=["Catalogue settlement"])
DB = Annotated[Session, Depends(get_db)]
Kind = Literal["employee", "vendor"]

class Settlement(BaseModel):
    settled_on: date
    reference: str = Field(min_length=3, max_length=200)
    note: str = Field(min_length=5, max_length=2000)
    all_dues_paid: Literal[True]

class Separation(BaseModel):
    last_working_day: date
    reason: str = Field(min_length=5,max_length=2000)
    separation_type: Literal["DISABLED","RESIGNED","REMOVED"]


def access(db, user):
    require_roles(db,user,{"ADMIN","MD"},"Only ADMIN or MD can manage final settlement and catalogue removal.")

@router.get("/vendors")
def vendors(user: CurrentUser, database: DB):
    require_roles(database,user,{"ADMIN","MD","GM","MANAGER"},"Vendor catalogue access is required.")
    return database.execute(text("""SELECT v.id, v.code, v.name, CASE WHEN v.status='ACTIVE' AND EXISTS (SELECT 1 FROM vendor_portal_accounts va WHERE va.vendor_id=v.id AND va.organization_id=v.organization_id AND va.status<>'ACTIVE') THEN 'DISABLED' ELSE v.status END AS status, cs.last_working_day,
        cs.separation_reason, cs.settled_on, cs.settlement_reference, cs.archived_at
        FROM vendors v LEFT JOIN workforce_catalogue_state cs ON cs.organization_id=v.organization_id AND cs.person_id=v.id AND cs.kind='vendor'
        WHERE v.organization_id=:org AND cs.archived_at IS NULL ORDER BY v.name"""),dict(org=user.organization_id)).mappings().all()

@router.post("/vendor/{person_id}/separate")
def separate(person_id: UUID, payload: Separation, user: CurrentUser, database: DB):
    access(database,user)
    load_person(database,user.organization_id,person_id,"vendor")
    ensure_not_archived(database,user.organization_id,person_id,"vendor")
    params=dict(org=user.organization_id,id=person_id,actor=user.id,**payload.model_dump())
    database.execute(text("UPDATE vendors SET status=:separation_type WHERE organization_id=:org AND id=:id"),params)
    database.execute(text("""INSERT INTO workforce_catalogue_state (organization_id,kind,person_id,last_working_day,separation_reason)
        VALUES (:org,'vendor',:id,:last_working_day,:reason) ON CONFLICT (organization_id,kind,person_id)
        DO UPDATE SET last_working_day=EXCLUDED.last_working_day,separation_reason=EXCLUDED.separation_reason,
        settled_on=NULL,settled_by=NULL,settlement_reference=NULL,settlement_note=NULL"""),params)
    database.execute(text("UPDATE vendor_portal_accounts SET status='DISABLED',updated_at=now() WHERE organization_id=:org AND vendor_id=:id"),params)
    database.execute(text("UPDATE vendor_portal_sessions SET revoked_at=now(),updated_at=now() WHERE account_id IN (SELECT id FROM vendor_portal_accounts WHERE organization_id=:org AND vendor_id=:id) AND revoked_at IS NULL"),params)
    audit(database,user,"vendor",person_id,"SEPARATED",payload.model_dump())
    database.commit()
    return {"message":"Vendor moved to Disabled / Resigned. Login and tracking are no longer available."}

@router.get("/{kind}/{person_id}/settlement")
def settlement_status(kind: Kind, person_id: UUID, user: CurrentUser, database: DB):
    access(database,user)
    reasons,state,last=settlement_blockers(database,user.organization_id,person_id,kind)
    return {"blockers":reasons,"settlement":state,"last_working_day":last,"can_delete":not reasons and bool(state.get("settled_on")) and not state.get("archived_at")}

@router.post("/{kind}/{person_id}/settlement")
def settle(kind: Kind, person_id: UUID, payload: Settlement, user: CurrentUser, database: DB):
    access(database,user)
    reasons,state,last=settlement_blockers(database,user.organization_id,person_id,kind)
    ensure_not_archived(database,user.organization_id,person_id,kind)
    if reasons:
        raise HTTPException(409," ".join(reasons))
    if payload.settled_on>organization_date(database,user.organization_id) or payload.settled_on<last:
        raise HTTPException(422,"Settlement date must be on or after the last working day and no later than today.")
    if not payload.reference.strip() or len(payload.note.strip())<5:
        raise HTTPException(422,"Enter the payment reference and settlement remarks.")
    database.execute(text("""INSERT INTO workforce_catalogue_state
        (organization_id,kind,person_id,last_working_day,settled_on,settled_by,settlement_reference,settlement_note)
        VALUES (:org,:kind,:id,:last,:settled_on,:actor,:reference,:note)
        ON CONFLICT (organization_id,kind,person_id) DO UPDATE SET last_working_day=EXCLUDED.last_working_day,
        settled_on=EXCLUDED.settled_on,settled_by=EXCLUDED.settled_by,settlement_reference=EXCLUDED.settlement_reference,
        settlement_note=EXCLUDED.settlement_note"""),dict(org=user.organization_id,kind=kind,id=person_id,last=last,actor=user.id,**payload.model_dump()))
    audit(database,user,kind,person_id,"SETTLED",payload.model_dump())
    database.commit()
    return {"message":"Final settlement recorded. You may now delete this person from the catalogue."}

@router.delete("/{kind}/{person_id}")
def remove(kind: Kind, person_id: UUID, user: CurrentUser, database: DB):
    access(database,user)
    reasons,state,last=settlement_blockers(database,user.organization_id,person_id,kind)
    if reasons or not state.get("settled_on"):
        raise HTTPException(409," ".join(reasons) or "Record completed final settlement first.")
    database.execute(text("UPDATE workforce_catalogue_state SET archived_at=now(),archived_by=:actor WHERE organization_id=:org AND kind=:kind AND person_id=:id AND archived_at IS NULL"),dict(org=user.organization_id,kind=kind,id=person_id,actor=user.id))
    audit(database,user,kind,person_id,"CATALOGUE_REMOVED",state)
    database.commit()
    return {"message":"Removed from catalogue. Payroll, attendance and settlement history are retained."}
