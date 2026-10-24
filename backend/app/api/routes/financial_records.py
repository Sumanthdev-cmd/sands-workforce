from datetime import date,datetime,timedelta,timezone
from uuid import UUID
from typing import Annotated
import jwt
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.core.config import get_settings
from app.services.auth_service import load_user_by_id
from app.services import financial_records as service
from app.services.financial_pdf import render_pdf

router=APIRouter(prefix='/financial-records',tags=['Financial record downloads'])
DB=Annotated[Session,Depends(get_db)]
AUD='sands-financial-download-v1'

@router.get('/categories')
def categories(user:CurrentUser,db:DB):
    service.access(db,user)
    installed=set(inspect(db.get_bind()).get_table_names())
    return [{'id':k,'label':v[0]} for k,v in service.CATEGORIES.items() if v[1] in installed]

@router.get('/download')
def download(db:DB, ticket:str=Query(min_length=1,max_length=4096)):
    settings=get_settings()
    try:
        claims=jwt.decode(ticket,settings.jwt_secret_key,algorithms=[settings.jwt_algorithm],audience=AUD,issuer=settings.jwt_issuer,options={'require':['exp','iat','sub','org','kind','record','purpose']})
        if claims['purpose']!='financial-download':raise ValueError('wrong purpose')
        uid,org,rid=UUID(claims['sub']),UUID(claims['org']),UUID(claims['record'])
    except (jwt.InvalidTokenError,ValueError,KeyError,TypeError):raise HTTPException(401,'Download link expired or invalid. Click Download PDF again.')
    user=load_user_by_id(db,uid);service.access(db,user)
    if user.organization_id!=org:raise HTTPException(403,'Download organisation does not match.')
    data=service.export_data(db,user,claims['kind'],rid)
    return Response(render_pdf(data),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{claims["kind"]}-{rid}.pdf"','Cache-Control':'private, no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})

@router.get('/{kind}')
def listing(kind:str,user:CurrentUser,db:DB,from_date:date|None=None,to_date:date|None=None,offset:int=Query(0,ge=0)):
    service.access(db,user)
    return service.listing(db,user.organization_id,kind,from_date,to_date,offset)

@router.post('/{kind}/{record_id}/download-link')
def link(kind:str,record_id:UUID,user:CurrentUser,db:DB):
    service.access(db,user);service.record(db,user.organization_id,kind,record_id)
    settings=get_settings();now=datetime.now(timezone.utc)
    token=jwt.encode({'iss':settings.jwt_issuer,'aud':AUD,'sub':str(user.id),'org':str(user.organization_id),'kind':kind,'record':str(record_id),'purpose':'financial-download','iat':now,'exp':now+timedelta(seconds=120)},settings.jwt_secret_key,algorithm=settings.jwt_algorithm)
    # Scoped ticket, not a login token. Works with the Android HTTPS download handler.
    return {'url':settings.api_v1_prefix+'/financial-records/download?ticket='+token,'expires_in':120}
