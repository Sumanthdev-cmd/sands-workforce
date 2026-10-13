from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: str
    title: str
    body: str
    payload: dict | None
    status: str
    attempts: int
    available_at: datetime
    sent_at: datetime | None
    read_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class BackgroundJobExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_name: str
    trigger_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    result_summary: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class BackgroundJobResult(BaseModel):
    job_name: str
    status: str
    result: dict
