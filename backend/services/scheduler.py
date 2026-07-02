import os
from datetime import datetime, timezone as dt_timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from models import ExamEntry
from services.datetime_utils import parse_exam_datetime_in_timezone

# Persistent job store so scheduled reminders survive a backend restart.
# Prefers DATABASE_URL (one env var upgrades this AND token_store to Postgres —
# Render's free-tier disk is ephemeral, so SQLite there is wiped per deploy).
_JOBSTORE_URL = (
    os.getenv("SCHEDULER_DB_URL")
    or os.getenv("DATABASE_URL")
    or "sqlite:///reminders.sqlite"
)
if _JOBSTORE_URL.startswith("postgres://"):
    _JOBSTORE_URL = _JOBSTORE_URL.replace("postgres://", "postgresql://", 1)

# Same private schema as token_store: on Supabase, `public` is exposed via
# PostgREST, so app tables live in a schema the REST API can't see.
_PG_SCHEMA = "xamio" if _JOBSTORE_URL.startswith("postgresql") else None

scheduler = BackgroundScheduler(
    jobstores={
        "default": SQLAlchemyJobStore(url=_JOBSTORE_URL, tableschema=_PG_SCHEMA)
    },
    job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 5},
)


def _ensure_schema() -> None:
    """Create the private schema before APScheduler creates its table in it
    (SQLAlchemyJobStore creates the table but not the schema)."""
    if not _PG_SCHEMA:
        return
    from sqlalchemy import create_engine, text

    engine = create_engine(_JOBSTORE_URL, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{_PG_SCHEMA}"'))
    finally:
        engine.dispose()


def start() -> None:
    try:
        if not scheduler.running:
            _ensure_schema()
            scheduler.start()
    except Exception as e:
        print(f"[scheduler] Could not start (serverless env?): {e}")


def shutdown() -> None:
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass


def _reminder_job(to: str, exam: dict) -> None:
    # Imported lazily so the job store doesn't pin a heavy import graph.
    from services.email_service import send_reminder_email

    send_reminder_email(to, exam)


def schedule_exam_reminders(
    to: str, exams: list[ExamEntry], reminder_minutes: list[int], timezone: str = "UTC"
) -> int:
    """Schedule a reminder email for each (exam, lead-time) pair whose fire time
    is still in the future. Returns the number of reminders scheduled."""
    # On a serverless host the background scheduler never started (start()
    # swallows that), and each request runs in a throwaway process — a job added
    # here would never fire. Don't queue reminders we can't deliver; the caller
    # reports 0 honestly instead of promising emails that never arrive.
    if not scheduler.running:
        print("[scheduler] not running (serverless host?) — skipping timed reminders.")
        return 0

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
            try:
                scheduler.add_job(
                    _reminder_job,
                    trigger="date",
                    run_date=run_dt,
                    args=[to, exam_dict],
                    id=job_id,
                    replace_existing=True,
                )
                scheduled += 1
            except Exception as e:
                print(f"[scheduler] Could not schedule job {job_id}: {e}")

    return scheduled
