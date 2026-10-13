from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.db.session import SessionLocal
from app.services.background_service import (
    dispatch_notifications,
    enqueue_renewal_notifications,
    generate_recurring_assignments,
    run_logged_job,
)
from app.services.storage_service import load_backend_env
from app.services.workforce_policy_service import enqueue_policy_escalations
from app.services.account_sheet_verification_service import (
    enqueue_account_sheet_escalations,
)


def recurring_tasks_job():
    database = SessionLocal()
    try:
        run_logged_job(
            database,
            "generate_recurring_tasks",
            "SCHEDULED",
            lambda: generate_recurring_assignments(database),
        )
    finally:
        database.close()


def renewal_job():
    database = SessionLocal()
    try:
        run_logged_job(
            database,
            "enqueue_renewal_reminders",
            "SCHEDULED",
            lambda: enqueue_renewal_notifications(database, 60),
        )
    finally:
        database.close()


def dispatch_job():
    database = SessionLocal()
    try:
        run_logged_job(
            database,
            "dispatch_notifications",
            "SCHEDULED",
            lambda: dispatch_notifications(database, 100),
        )
    finally:
        database.close()


def workforce_policy_job():
    database = SessionLocal()
    try:
        run_logged_job(
            database,
            "workforce_policy_escalations",
            "SCHEDULED",
            lambda: enqueue_policy_escalations(database),
        )
    finally:
        database.close()


def account_sheet_escalation_job():
    database = SessionLocal()
    try:
        run_logged_job(
            database,
            "account_sheet_discrepancy_escalations",
            "SCHEDULED",
            lambda: enqueue_account_sheet_escalations(database),
        )
    finally:
        database.close()


def main():
    load_backend_env()

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        recurring_tasks_job,
        CronTrigger(hour=0, minute=5, timezone="Asia/Kolkata"),
        id="generate_recurring_tasks",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        renewal_job,
        CronTrigger(hour=8, minute=0, timezone="Asia/Kolkata"),
        id="enqueue_renewal_reminders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        dispatch_job,
        IntervalTrigger(minutes=1),
        id="dispatch_notifications",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        workforce_policy_job,
        IntervalTrigger(minutes=5),
        id="workforce_policy_escalations",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        account_sheet_escalation_job,
        IntervalTrigger(minutes=5),
        id="account_sheet_discrepancy_escalations",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    print("Background worker started.")
    print("Recurring tasks: 12:05 AM IST")
    print("Renewal reminders: 8:00 AM IST")
    print("Notification delivery: every minute")
    print("Lunch, task and notice escalations: every 5 minutes")
    print("Accounts discrepancy escalations: every 5 minutes")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
