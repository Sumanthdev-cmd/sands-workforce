from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class SalaryStructure(TimestampMixin, Base):
    """Salary components effective from a particular date."""

    __tablename__ = "salary_structures"
    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "effective_from",
            name="uq_salary_structure_employee_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    effective_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    basic_salary: Mapped[float] = mapped_column(Float, nullable=False)
    hra: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    conveyance_allowance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    other_allowance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    daily_allowance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    fixed_deduction: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="INR",
        server_default="INR",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    employee = relationship("Employee")
    created_by = relationship("User")

    @property
    def gross_monthly_salary(self) -> float:
        return round(
            self.basic_salary
            + self.hra
            + self.conveyance_allowance
            + self.other_allowance,
            2,
        )

    @property
    def net_monthly_after_fixed_deduction(self) -> float:
        """Structure-level net; payroll-period adjustments are applied later."""
        return max(
            0,
            round(
                self.gross_monthly_salary
                - self.fixed_deduction,
                2,
            ),
        )


class VendorSalaryStructure(TimestampMixin, Base):
    """Effective-dated monthly salary for a shop vendor."""

    __tablename__ = "vendor_salary_structures"
    __table_args__ = (
        UniqueConstraint(
            "vendor_id",
            "effective_from",
            name="uq_vendor_salary_structure_vendor_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # ``monthly_salary`` is retained for compatibility with records created before
    # vendor salary components were introduced. New records store the calculated
    # monthly gross here as well as the individual components below.
    monthly_salary: Mapped[float] = mapped_column(Float, nullable=False)
    basic_salary: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    hra: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    conveyance_allowance: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    other_allowance: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    daily_allowance: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    fixed_deduction: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR", server_default="INR")
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    vendor = relationship("Vendor")
    created_by = relationship("User")

    @property
    def gross_monthly_salary(self) -> float:
        return round(
            self.basic_salary
            + self.hra
            + self.conveyance_allowance
            + self.other_allowance,
            2,
        )

    @property
    def net_monthly_salary(self) -> float:
        return max(0, round(self.gross_monthly_salary - self.fixed_deduction, 2))


class VendorClosureDay(TimestampMixin, Base):
    """Government-ordered closure excluded from vendor payroll working days."""

    __tablename__ = "vendor_closure_days"
    __table_args__ = (
        UniqueConstraint("organization_id", "closure_date", name="uq_vendor_closure_org_date"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    closure_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    created_by = relationship("User")


class SalaryRevision(TimestampMixin, Base):
    """Audit history for MD-approved salary changes."""

    __tablename__ = "salary_revisions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_structure_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("salary_structures.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_structure_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("salary_structures.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revised_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    previous_gross: Mapped[float] = mapped_column(Float, nullable=False)
    new_gross: Mapped[float] = mapped_column(Float, nullable=False)
    increase_amount: Mapped[float] = mapped_column(Float, nullable=False)
    increase_percentage: Mapped[float] = mapped_column(Float, nullable=False)


class SalaryHold(TimestampMixin, Base):
    """MD-controlled salary hold."""

    __tablename__ = "salary_holds"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hold_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hold_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
        index=True,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    released_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    release_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SalaryAdvanceRequest(TimestampMixin, Base):
    """Employee-raised salary advance with MD approval and payroll recovery."""

    __tablename__ = "salary_advance_requests"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_amount: Mapped[float] = mapped_column(Float, nullable=False)
    installment_amount: Mapped[float] = mapped_column(Float, nullable=False)
    recovery_months: Mapped[int] = mapped_column(Integer, nullable=False)
    recovered_amount: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="INR",
        server_default="INR",
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
        index=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    disbursed_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    disbursed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disbursement_reference: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    disbursement_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancellation_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class VendorSalaryAdvanceRequest(TimestampMixin, Base):
    """Vendor-raised salary advance with MD approval and payroll recovery."""

    __tablename__ = "vendor_salary_advance_requests"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_vendor_account_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vendor_portal_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_amount: Mapped[float] = mapped_column(Float, nullable=False)
    installment_amount: Mapped[float] = mapped_column(Float, nullable=False)
    recovery_months: Mapped[int] = mapped_column(Integer, nullable=False)
    recovered_amount: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="INR",
        server_default="INR",
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
        server_default="PENDING",
        index=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    disbursed_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    disbursed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disbursement_reference: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    disbursement_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancellation_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class PayrollRun(TimestampMixin, Base):
    """Payroll processing period."""

    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "period_start",
            "period_end",
            name="uq_payroll_run_organization_period",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        index=True,
    )
    total_employees: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    total_vendors: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    vendor_total_gross: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    vendor_total_deductions: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    vendor_total_net: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    total_gross: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    total_deductions: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    total_net: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    finalized_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submission_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    return_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SalaryAdvanceRecovery(TimestampMixin, Base):
    """Finalized payroll installment recovered against a salary advance."""

    __tablename__ = "salary_advance_recoveries"
    __table_args__ = (
        UniqueConstraint(
            "salary_advance_request_id",
            "payroll_run_id",
            name="uq_salary_advance_recovery_request_run",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    salary_advance_request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("salary_advance_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payroll_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    recovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class VendorSalaryAdvanceRecovery(TimestampMixin, Base):
    """Finalized vendor payroll installment recovered against a salary advance."""

    __tablename__ = "vendor_salary_advance_recoveries"
    __table_args__ = (
        UniqueConstraint(
            "vendor_salary_advance_request_id",
            "payroll_run_id",
            name="uq_vendor_salary_advance_recovery_request_run",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vendor_salary_advance_request_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vendor_salary_advance_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payroll_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    vendor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    recovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class PayrollItem(TimestampMixin, Base):
    """Calculated salary and payslip for one employee."""

    __tablename__ = "payroll_items"
    __table_args__ = (
        UniqueConstraint(
            "payroll_run_id",
            "employee_id",
            name="uq_payroll_item_run_employee",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payroll_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    salary_structure_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("salary_structures.id", ondelete="RESTRICT"),
        nullable=False,
    )
    working_days: Mapped[float] = mapped_column(Float, nullable=False)
    payable_days: Mapped[float] = mapped_column(Float, nullable=False)
    absent_days: Mapped[float] = mapped_column(Float, nullable=False)
    basic_earned: Mapped[float] = mapped_column(Float, nullable=False)
    hra_earned: Mapped[float] = mapped_column(Float, nullable=False)
    conveyance_earned: Mapped[float] = mapped_column(Float, nullable=False)
    other_allowance_earned: Mapped[float] = mapped_column(Float, nullable=False)
    daily_allowance_earned: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    gross_earned: Mapped[float] = mapped_column(Float, nullable=False)
    loss_of_pay_deduction: Mapped[float] = mapped_column(Float, nullable=False)
    fixed_deduction: Mapped[float] = mapped_column(Float, nullable=False)
    other_deductions: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    salary_advance_deduction: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    overtime_benefit: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0,
        server_default="0",
    )
    net_salary: Mapped[float] = mapped_column(Float, nullable=False)
    is_held: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    hold_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculation_details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    payslip_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )


class VendorPayrollItem(TimestampMixin, Base):
    """Attendance-based monthly payment calculated for a shop vendor."""

    __tablename__ = "vendor_payroll_items"
    __table_args__ = (
        UniqueConstraint(
            "payroll_run_id",
            "vendor_id",
            name="uq_vendor_payroll_item_run_vendor",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payroll_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_salary_structure_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("vendor_salary_structures.id", ondelete="RESTRICT"), nullable=False
    )
    working_days: Mapped[float] = mapped_column(Float, nullable=False)
    payable_days: Mapped[float] = mapped_column(Float, nullable=False)
    absent_days: Mapped[float] = mapped_column(Float, nullable=False)
    basic_earned: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    hra_earned: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    conveyance_earned: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    other_allowance_earned: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    daily_allowance_earned: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    gross_earned: Mapped[float] = mapped_column(Float, nullable=False)
    fixed_deduction: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    other_deductions: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    salary_advance_deduction: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default="0")
    net_salary: Mapped[float] = mapped_column(Float, nullable=False)
    calculation_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    payslip_number: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    vendor = relationship("Vendor")
    salary_structure = relationship("VendorSalaryStructure")
