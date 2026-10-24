import csv
import io
from html import escape
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.db.session import get_db
from app.schemas.payroll import (
    AdminPayrollItemResponse,
    MyPayslipResponse,
    PayrollRunApprovalRequest,
    PayrollRunCreateRequest,
    PayrollRunResponse,
    PayrollRunReturnRequest,
    PayrollRunSubmitRequest,
    SalaryHoldCreateRequest,
    SalaryHoldReleaseRequest,
    SalaryHoldResponse,
    SalaryRevisionRequest,
    SalaryStructureCreateRequest,
    SalaryStructureResponse,
    VendorClosureCreateRequest,
    VendorClosureResponse,
    VendorPayrollItemResponse,
    VendorSalaryStructureRequest,
    VendorSalaryStructureResponse,
)
from app.services.payroll_service import (
    approve_payroll_run,
    calculate_payroll_run,
    create_payroll_run,
    create_salary_hold,
    create_salary_structure,
    create_vendor_closure,
    deactivate_vendor_closure,
    delete_payroll_run,
    finalize_payroll_run,
    get_finalized_payroll_export,
    get_payroll_working_calendar,
    get_printable_payslip,
    list_my_payslips,
    list_payroll_items,
    list_payroll_runs,
    list_salary_holds,
    list_salary_structures,
    list_payroll_vendors,
    list_vendor_closures,
    list_vendor_payroll_items,
    list_vendor_salary_structures,
    release_salary_hold,
    return_payroll_run,
    revise_salary,
    save_vendor_salary_structure,
    submit_payroll_run,
)


router = APIRouter(prefix="/payroll", tags=["Payroll"])

DatabaseSession = Annotated[Session, Depends(get_db)]


def _safe_csv_cell(value) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def _amount(value) -> str:
    return f"{float(value or 0):.2f}"


from app.services.payroll_print_layout import render_register, render_payslip

@router.post(
    "/structures/{employee_id}",
    response_model=SalaryStructureResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_structure(
    employee_id: UUID,
    payload: SalaryStructureCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_salary_structure(
        database,
        current_user,
        employee_id,
        payload,
    )


@router.get(
    "/structures/{employee_id}",
    response_model=list[SalaryStructureResponse],
)
def read_structures(
    employee_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_salary_structures(
        database,
        current_user,
        employee_id,
    )


@router.post(
    "/structures/{employee_id}/revise",
    response_model=SalaryStructureResponse,
    status_code=status.HTTP_201_CREATED,
)
def revise_structure(
    employee_id: UUID,
    payload: SalaryRevisionRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return revise_salary(
        database,
        current_user,
        employee_id,
        payload,
    )


@router.get("/vendors")
def read_payroll_vendors(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_payroll_vendors(database, current_user)


@router.get(
    "/vendor-structures/{vendor_id}",
    response_model=list[VendorSalaryStructureResponse],
)
def read_vendor_structures(
    vendor_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_vendor_salary_structures(database, current_user, vendor_id)


@router.post(
    "/vendor-structures/{vendor_id}",
    response_model=VendorSalaryStructureResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_vendor_structure(
    vendor_id: UUID,
    payload: VendorSalaryStructureRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return save_vendor_salary_structure(database, current_user, vendor_id, payload)


@router.get("/vendor-closures", response_model=list[VendorClosureResponse])
def read_vendor_closures(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_vendor_closures(database, current_user)


@router.post(
    "/vendor-closures",
    response_model=VendorClosureResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_vendor_closure(
    payload: VendorClosureCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_vendor_closure(database, current_user, payload)


@router.delete("/vendor-closures/{closure_id}", response_model=VendorClosureResponse)
def remove_vendor_closure(
    closure_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return deactivate_vendor_closure(database, current_user, closure_id)


@router.get("/holds", response_model=list[SalaryHoldResponse])
def read_holds(
    current_user: CurrentUser,
    database: DatabaseSession,
    active_only: bool = Query(default=True),
):
    return list_salary_holds(
        database,
        current_user,
        active_only,
    )


@router.post(
    "/holds/{employee_id}",
    response_model=SalaryHoldResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_hold(
    employee_id: UUID,
    payload: SalaryHoldCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_salary_hold(
        database,
        current_user,
        employee_id,
        payload,
    )


@router.post(
    "/holds/{hold_id}/release",
    response_model=SalaryHoldResponse,
)
def release_hold(
    hold_id: UUID,
    payload: SalaryHoldReleaseRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return release_salary_hold(
        database,
        current_user,
        hold_id,
        payload,
    )


@router.post(
    "/runs",
    response_model=PayrollRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_run(
    payload: PayrollRunCreateRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return create_payroll_run(
        database,
        current_user,
        payload,
    )


@router.get("/runs", response_model=list[PayrollRunResponse])
def read_runs(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_payroll_runs(database, current_user)


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_run(
    run_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    delete_payroll_run(database, current_user, run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/runs/{run_id}/calculate",
    response_model=PayrollRunResponse,
)
def calculate_run(
    run_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return calculate_payroll_run(
        database,
        current_user,
        run_id,
    )


@router.post(
    "/runs/{run_id}/submit-approval",
    response_model=PayrollRunResponse,
)
def submit_run_for_md_approval(
    run_id: UUID,
    payload: PayrollRunSubmitRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return submit_payroll_run(database, current_user, run_id, payload)


@router.post(
    "/runs/{run_id}/approve",
    response_model=PayrollRunResponse,
)
def approve_run(
    run_id: UUID,
    payload: PayrollRunApprovalRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return approve_payroll_run(database, current_user, run_id, payload)


@router.post(
    "/runs/{run_id}/return",
    response_model=PayrollRunResponse,
)
def return_run_for_correction(
    run_id: UUID,
    payload: PayrollRunReturnRequest,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return return_payroll_run(database, current_user, run_id, payload)


@router.post(
    "/runs/{run_id}/finalize",
    response_model=PayrollRunResponse,
)
def finalize_run(
    run_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return finalize_payroll_run(
        database,
        current_user,
        run_id,
    )


@router.get(
    "/runs/{run_id}/items",
    response_model=list[AdminPayrollItemResponse],
)
def read_run_items(
    run_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_payroll_items(
        database,
        current_user,
        run_id,
    )


@router.get(
    "/runs/{run_id}/vendor-items",
    response_model=list[VendorPayrollItemResponse],
)
def read_run_vendor_items(
    run_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_vendor_payroll_items(database, current_user, run_id)


@router.get("/runs/{run_id}/working-calendar")
def read_run_working_calendar(
    run_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return get_payroll_working_calendar(
        database,
        current_user,
        run_id,
    )


@router.get("/runs/{run_id}/export.csv")
def download_finalized_payroll(
    run_id: UUID,
    current_user: CurrentUser,
    database: DatabaseSession,
):
    payroll_run, items = get_finalized_payroll_export(
        database,
        current_user,
        run_id,
    )
    vendor_items = list_vendor_payroll_items(database, current_user, run_id)
    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Period Start", "Period End", "Payroll Status", "Approved At",
        "Approval Note", "Payee Type", "Code", "Name", "Bank Name",
        "IFSC", "Account Number", "Payslip Number",
        "Working Days", "Payable Days", "Absent Days", "Basic Earned",
        "HRA Earned", "Conveyance Earned", "Other Allowance Earned",
        "Daily Allowance", "OT Benefit", "Gross Earned",
        "Loss of Pay (Reference)", "Fixed Deduction", "Late Deduction",
        "Advance Recovery", "Payroll Deductions", "Net Salary", "Currency",
        "Salary Held", "Hold Reason",
    ])
    for item in items:
        payroll_deductions = (
            float(item.get("fixed_deduction") or 0)
            + float(item.get("other_deductions") or 0)
            + float(item.get("salary_advance_deduction") or 0)
        )
        writer.writerow([
            payroll_run.period_start,
            payroll_run.period_end,
            payroll_run.status,
            payroll_run.approved_at or "",
            _safe_csv_cell(payroll_run.approval_note),
            "EMPLOYEE",
            _safe_csv_cell(item.get("employee_code")),
            _safe_csv_cell(item.get("employee_name")),
            _safe_csv_cell(item.get("bank_name")),
            _safe_csv_cell(item.get("bank_ifsc")),
            _safe_csv_cell(item.get("bank_account_number")),
            _safe_csv_cell(item.get("payslip_number")),
            _amount(item.get("working_days")),
            _amount(item.get("payable_days")),
            _amount(item.get("absent_days")),
            _amount(item.get("basic_earned")),
            _amount(item.get("hra_earned")),
            _amount(item.get("conveyance_earned")),
            _amount(item.get("other_allowance_earned")),
            _amount(item.get("daily_allowance_earned")),
            _amount(item.get("overtime_benefit")),
            _amount(item.get("gross_earned")),
            _amount(item.get("loss_of_pay_deduction")),
            _amount(item.get("fixed_deduction")),
            _amount(item.get("other_deductions")),
            _amount(item.get("salary_advance_deduction")),
            _amount(payroll_deductions),
            _amount(item.get("net_salary")),
            _safe_csv_cell(item.get("currency")),
            "YES" if item.get("is_held") else "NO",
            _safe_csv_cell(item.get("hold_reason")),
        ])
    for item in vendor_items:
        vendor_deductions = (
            float(item.get("fixed_deduction") or 0)
            + float(item.get("other_deductions") or 0)
            + float(item.get("salary_advance_deduction") or 0)
        )
        writer.writerow([
            payroll_run.period_start,
            payroll_run.period_end,
            payroll_run.status,
            payroll_run.approved_at or "",
            _safe_csv_cell(payroll_run.approval_note),
            "VENDOR",
            _safe_csv_cell(item.get("vendor_code")),
            _safe_csv_cell(item.get("vendor_name")),
            "",
            "",
            "",
            _safe_csv_cell(item.get("payslip_number")),
            _amount(item.get("working_days")),
            _amount(item.get("payable_days")),
            _amount(item.get("absent_days")),
            _amount(item.get("basic_earned")),
            _amount(item.get("hra_earned")),
            _amount(item.get("conveyance_earned")),
            _amount(item.get("other_allowance_earned")),
            _amount(item.get("daily_allowance_earned")),
            "",
            _amount(item.get("gross_earned")),
            "",
            _amount(item.get("fixed_deduction")),
            _amount(item.get("other_deductions")),
            _amount(item.get("salary_advance_deduction")),
            _amount(vendor_deductions),
            _amount(item.get("net_salary")),
            _safe_csv_cell(item.get("currency")),
            "NO",
            "",
        ])

    filename = (
        f"payroll_{payroll_run.period_start}_to_"
        f"{payroll_run.period_end}_finalized.csv"
    )
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/print", response_class=HTMLResponse)
def print_finalized_payroll(run_id: UUID, current_user: CurrentUser, database: DatabaseSession):
    payroll_run, items = get_finalized_payroll_export(database, current_user, run_id)
    vendor_items = list_vendor_payroll_items(database, current_user, run_id)
    from app.models.organization import Organization
    org = database.get(Organization, current_user.organization_id)
    return HTMLResponse(content=render_register(payroll_run, items, vendor_items, org.timezone if org else "Asia/Kolkata"))


@router.get(
    "/me/payslips",
    response_model=list[MyPayslipResponse],
)
def read_my_slips(
    current_user: CurrentUser,
    database: DatabaseSession,
):
    return list_my_payslips(database, current_user)


@router.get(
    "/payslips/{item_id}/print",
    response_class=HTMLResponse,
)
def print_payslip(item_id: UUID, current_user: CurrentUser, database: DatabaseSession):
    item, payroll_run, structure, employee = get_printable_payslip(database, current_user, item_id)
    return HTMLResponse(content=render_payslip(item, payroll_run, structure, employee))

# date-display-ddmmyyyy-v1

# payroll-reference-layout-v1
