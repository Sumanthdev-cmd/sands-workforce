from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class AccountSheetItemCreate(BaseModel):
    sheet_name: str = Field(min_length=2, max_length=250)
    sheet_generated_on: date
    has_discrepancy: bool = False
    discrepancy_reason: str | None = Field(default=None, max_length=5000)
    discrepancy_document_id: UUID | None = None

    @field_validator("sheet_name")
    @classmethod
    def normalize_sheet_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 2:
            raise ValueError("Sheet name must contain at least two characters.")
        return normalized

    @field_validator("discrepancy_reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_discrepancy_evidence(self):
        if self.has_discrepancy:
            if not self.discrepancy_reason:
                raise ValueError(
                    "A discrepancy reason is required for every discrepant sheet."
                )
            if self.discrepancy_document_id is None:
                raise ValueError(
                    "Upload the discrepant sheet before submitting the report."
                )
        else:
            self.discrepancy_reason = None
            self.discrepancy_document_id = None
        return self


class AccountSheetVerificationCreate(BaseModel):
    submission_id: UUID
    verification_date: date
    declared_sheet_count: int = Field(ge=1, le=500)
    notes: str | None = Field(default=None, max_length=5000)
    items: list[AccountSheetItemCreate] = Field(min_length=1, max_length=500)

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_declared_count(self):
        if self.declared_sheet_count != len(self.items):
            raise ValueError(
                "Declared sheet count must exactly match the sheet entries."
            )

        identities = {
            (item.sheet_name.casefold(), item.sheet_generated_on)
            for item in self.items
        }
        if len(identities) != len(self.items):
            raise ValueError(
                "The same sheet name and generated date cannot be entered twice."
            )
        return self


class AccountSheetSecretaryReviewRequest(BaseModel):
    decision: Literal["VERIFIED", "CONFIRMED", "NOT_FOUND"]
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AccountSheetResolveRequest(BaseModel):
    resolution_note: str = Field(min_length=3, max_length=5000)

    @field_validator("resolution_note")
    @classmethod
    def normalize_resolution_note(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Resolution note must contain at least three characters.")
        return normalized


class AccountSheetItemResponse(BaseModel):
    id: UUID
    report_id: UUID
    verification_date: date
    declared_sheet_count: int
    accounts_manager_employee_id: UUID
    accounts_manager_employee_code: str
    accounts_manager_name: str

    sheet_name: str
    sheet_generated_on: date
    has_discrepancy: bool
    discrepancy_reason: str | None
    discrepancy_document_id: UUID | None
    discrepancy_document_name: str | None
    discrepancy_document_content_type: str | None

    secretary_status: str
    secretary_reviewed_by_user_id: UUID | None
    secretary_reviewed_at: datetime | None
    secretary_note: str | None

    issue_status: str
    issue_raised_at: datetime | None
    admin_escalated_at: datetime | None
    md_escalated_at: datetime | None
    resolved_by_user_id: UUID | None
    resolved_at: datetime | None
    resolution_note: str | None
    resolution_role: str | None

    can_secretary_review: bool
    can_resolve: bool
    created_at: datetime
    updated_at: datetime


class AccountSheetVerificationResponse(BaseModel):
    id: UUID
    submission_id: UUID
    verification_date: date
    declared_sheet_count: int
    actual_sheet_count: int
    discrepancy_count: int
    open_issue_count: int
    notes: str | None
    status: str
    accounts_manager_employee_id: UUID
    accounts_manager_employee_code: str
    accounts_manager_name: str
    submitted_by_user_id: UUID
    submitted_at: datetime
    items: list[AccountSheetItemResponse]
    created_at: datetime
    updated_at: datetime


class AccountSheetEscalationResult(BaseModel):
    scanned: int
    admin_escalations: int
    md_escalations: int
