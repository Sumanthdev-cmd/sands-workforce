from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class WorkPolicyUpdateRequest(BaseModel):
    lunch_break_minutes: int = Field(ge=1, le=240)


class DutyExitCreateRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=5000)


class DecisionRequest(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=5000)


class NoticePeriodCreateRequest(BaseModel):
    employee_id: UUID
    start_date: date
    end_date: date
    reason: str = Field(min_length=5, max_length=5000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be earlier than start_date.")
        return self


class NoticePeriodEndRequest(BaseModel):
    note: str = Field(min_length=3, max_length=5000)


class InspectionLateStartCreateRequest(BaseModel):
    visit_assignment_id: UUID
    reason: str = Field(min_length=5, max_length=5000)
