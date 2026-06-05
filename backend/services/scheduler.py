import os
from datetime import datetime, timezone as dt_timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from models import ExamEntry
from services.datetime_utils import parse_exam_datetime_in_timezone

# Persistent job store so scheduled reminders survive a backend restart.
_JOBSTORE_URL = os.getenv("SCHEDULER_DB_URL", "sqlite:///reminders.sqlite")

scheduler = BackgroundScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=_JOBSTORE_URL)},
    job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 5},
)


def start() -> None:
    if not scheduler.running:
        scheduler.start()


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _reminder_job(to: str, exam: dict) -> None:
    # Imported lazily so the job store doesn't pin a heavy import graph.
    from services.email_service import send_reminder_email

    send_reminder_email(to, exam)


def schedule_exam_reminders(
    to: str, exams: list[ExamEntry], reminder_minutes: list[int], timezone: str = "UTC"
) -> int:
    """Schedule a reminder email for each (exam, lead-time) pair whose fire time
    is still in the future. Returns the number of reminders scheduled."""
    now = datetime.now(dt_timezone.utc)
    scheduled = 0

    for exam in exams:
        start_dt = parse_exam_datetime_in_timezone(exam.date, exam.time, timezone)
        if start_dt is None:
            continue
        exam_dict = exam.model_dump()
        for minutes in reminder_minutes:
            run_at = start_dt.timestamp() - minutes * 60
            run_dt = datetime.fromtimestamp(run_at, tz=dt_timezone.utc)
            if run_dt <= now:
                continue  # lead time already passed
            job_id = f"reminder:{to}:{exam.course_code}:{exam.date}:{exam.time}:{minutes}"
            scheduler.add_job(
                _reminder_job,
                trigger="date",
                run_date=run_dt,
                args=[to, exam_dict],
                id=job_id,
                replace_existing=True,
            )
            scheduled += 1

    return scheduled
