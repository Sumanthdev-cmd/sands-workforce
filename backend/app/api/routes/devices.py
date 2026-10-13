from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.devices import DeviceRegisterRequest, DeviceResponse, FcmTokenUpdateRequest
from app.services.device_service import list_own_devices, register_device, update_fcm_token


router = APIRouter(prefix="/devices", tags=["Devices"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/register",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_employee_device(
    payload: DeviceRegisterRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> DeviceResponse:
    return register_device(database, user=current_user, payload=payload)


@router.get("/me", response_model=list[DeviceResponse])
def read_own_devices(
    current_user: CurrentUser,
    database: DatabaseSession,
) -> list[DeviceResponse]:
    return list_own_devices(database, user=current_user)


@router.patch("/{device_id}/fcm-token", response_model=DeviceResponse)
def replace_fcm_token(
    device_id: UUID,
    payload: FcmTokenUpdateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
) -> DeviceResponse:
    return update_fcm_token(
        database,
        user=current_user,
        device_id=device_id,
        fcm_token=payload.fcm_token,
    )
