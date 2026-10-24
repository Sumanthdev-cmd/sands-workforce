from datetime import date
from typing import Annotated
from fastapi import APIRouter,Depends
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import User
from app.api.dependencies.permissions import require_permissions
from app.services.attendance_grid import grid
from app.services.employee_numbering import reserve

router=APIRouter(prefix='/workforce-improvements',tags=['Attendance and employee setup'])
DB=Annotated[Session,Depends(get_db)]
Viewer=Annotated[User,Depends(require_permissions('attendance.view_all'))]
Creator=Annotated[User,Depends(require_permissions('employee.create'))]
class ReservationRequest(BaseModel):
    role_codes:list[str]=Field(min_length=1,max_length=30)

@router.get('/attendance-grid')
def attendance_grid(start_date:date,end_date:date,user:Viewer,db:DB):
    return grid(db,user,start_date,end_date)

@router.post('/employee-code',status_code=201)
def employee_code(payload:ReservationRequest,user:Creator,db:DB):
    return reserve(db,user.organization_id,payload.role_codes)
