from app.api.routes.outlets import router as outlets_router
from app.api.routes.account_sheet_verifications import (
    router as account_sheet_verifications_router,
)
from app.api.routes.inspections import router as inspections_router
from app.api.routes.fuel import router as fuel_router
from app.api.routes.management_dashboard import router as management_dashboard_router
from app.api.routes.recruitment import router as recruitment_router
from app.api.routes.inventory_assets import router as inventory_assets_router
from app.api.routes.operations import router as operations_router
from app.api.routes.approvals import router as approvals_router
from app.api.routes.appointments import router as appointments_router
from app.api.routes.background import router as background_router
from app.api.routes.maintenance_bills import (
    router as maintenance_bills_router,
)
from fastapi import APIRouter

from app.api.routes.vendor_portal import router as vendor_portal_router

from app.api.routes.assets import router as assets_router
from app.api.routes.attendance import router as attendance_router
from app.api.routes.auth import router as auth_router
from app.api.routes.devices import router as devices_router
from app.api.routes.documents import router as documents_router
from app.api.routes.employees import router as employees_router
from app.api.routes.expenses import router as expenses_router
from app.api.routes.geofences import router as geofences_router
from app.api.routes.health import router as health_router
from app.api.routes.leave import router as leave_router
from app.api.routes.locations import router as locations_router
from app.api.routes.master_data import router as master_data_router
from app.api.routes.payroll import router as payroll_router
from app.api.routes.salary_advances import router as salary_advances_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.workforce_policy import router as workforce_policy_router
from app.api.routes.security_controls import router as security_controls_router
from app.api.routes.overtime import router as overtime_router


api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(master_data_router)
api_router.include_router(employees_router)
api_router.include_router(devices_router)
api_router.include_router(locations_router)
api_router.include_router(geofences_router)
api_router.include_router(attendance_router)
api_router.include_router(workforce_policy_router)
api_router.include_router(security_controls_router)
api_router.include_router(overtime_router)
api_router.include_router(tasks_router)
api_router.include_router(leave_router)
api_router.include_router(payroll_router)
api_router.include_router(salary_advances_router)
api_router.include_router(expenses_router)
api_router.include_router(account_sheet_verifications_router)
api_router.include_router(documents_router)
api_router.include_router(assets_router)
api_router.include_router(background_router)
api_router.include_router(appointments_router)
api_router.include_router(approvals_router)
api_router.include_router(operations_router)
api_router.include_router(inventory_assets_router)
api_router.include_router(recruitment_router)
api_router.include_router(management_dashboard_router)
api_router.include_router(fuel_router)
api_router.include_router(inspections_router)
api_router.include_router(outlets_router)
api_router.include_router(
    maintenance_bills_router
)
api_router.include_router(vendor_portal_router)

# Android work-session location support
from app.api.routes.mobile_tracking import router as mobile_tracking_router
api_router.include_router(mobile_tracking_router)

# Native Android notifications
from app.api.routes.mobile_push import router as mobile_push_router
api_router.include_router(mobile_push_router)

# Task oversight and Android workday diagnostics
from app.api.routes.task_workday_support import router as task_workday_support_router
api_router.include_router(task_workday_support_router)

from app.api.routes.box_loading import router as box_loading_router
api_router.include_router(box_loading_router)

from app.api.routes.catalogue import router as catalogue_router
api_router.include_router(catalogue_router)

from app.api.routes.cashbook import router as cashbook_router
api_router.include_router(cashbook_router)

# attendance-grid-update-v1
from app.api.routes.workforce_improvements import router as workforce_improvements_router
api_router.include_router(workforce_improvements_router)

from app.api.routes.financial_records import router as financial_records_router
api_router.include_router(financial_records_router)

# financial-records-update-v1
