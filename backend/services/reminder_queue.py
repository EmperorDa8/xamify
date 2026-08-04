"""Durable reminder delivery.

A reminder is a row with a `send_at`, not a job inside a running process. That
distinction is the whole point: the previous APScheduler setup tied delivery to
a process Render's free tier is allowed to stop, and a reminder that came due
while the service slept was permanently discarded once it aged past the
one-hour misfire grace — after the user had been told it was scheduled.

Here nothing is lost. A due row stays `pending` until it is actually delivered,
so a missed window costs latency instead of the reminder. An external heartbeat
(pg_cron -> pg_net -> POST /tasks/dispatch-reminders) drives the sending.
"""
import json
from datetime import datetime, timedelta, timezone as dt_timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    func,
    select,
    text as sql_text,
    update,
)

from models import ExamEntry
from services.datetime_utils import parse_exam_datetime_in_timezone
from services.db import IS_POSTGRES, PRIVATE_SCHEMA, engine, ensure_schema

# How many reminders one dispatch run will send. Keeps a single invocation well
# inside any request timeout; the next tick picks up whatever is left.
BATCH_SIZE = 50

# A row claimed but not resolved within this long belonged to a process that
# died mid-send. It goes back on the queue rather than being stranded.
STALLED_AFTER = timedelta(minutes=15)

_metadata = MetaData(schema=PRIVATE_SCHEMA)

reminder_queue = Table(
    "reminder_queue",
    _metadata,
    # SQLite only auto-assigns rowids for INTEGER PRIMARY KEY, not BIGINT, so
    # the local-dev mirror uses Integer while Postgres keeps bigint.
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column("channel", String(16), nullable=False, default="email"),
    Column("destination", Text, nullable=False),
    Column("payload", Text, nullable=False, default="{}"),
    Column("send_at", DateTime(timezone=True), nullable=False),
    Column("status", String(16), nullable=False, default="pending"),
    Column("attempts", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False, default=5),
    Column("last_error", Text),
    Column("dedupe_key", Text, nullable=False, unique=True),
    Column("user_id", String(36)),
    Column("schedule_id", String(36)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("claimed_at", DateTime(timezone=True)),
    Column("sent_at", DateTime(timezone=True)),
)


def init() -> None:
    """Create the schema and table if missing. On Postgres the migration has
    already made them, so this is a no-op there; it is what lets local SQLite
    dev work without running migrations."""
    ensure_schema()
    _metadata.create_all(engine, checkfirst=True)


def _now() -> datetime:
    return datetime.now(dt_timezone.utc)


# jsonb on Postgres wants a dict; the SQLite mirror stores TEXT. Normalising on
# the way in and out keeps callers from caring which backend they are on.
def _dump(payload: dict) -> str:
    return json.dumps(payload)


def _load(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}


def enqueue(
    *,
    destination: str,
    payload: dict,
    send_at: datetime,
    dedupe_key: str,
    channel: str = "email",
    user_id: str | None = None,
    schedule_id: str | None = None,
) -> bool:
    """Queue one reminder. Returns True if a row was created or rescheduled.

    Re-running the alerts endpoint must not produce duplicate sends, so the
    dedupe key is unique and a conflict reschedules the existing row — but only
    while it is still pending, so an already-delivered reminder is never
    resurrected.
    """
    now = _now()
    values = {
        "channel": channel,
        "destination": destination,
        "payload": _dump(payload),
        "send_at": send_at,
        "status": "pending",
        "attempts": 0,
        "max_attempts": 5,
        "dedupe_key": dedupe_key,
        "user_id": user_id,
        "schedule_id": schedule_id,
        "created_at": now,
    }

    with engine.begin() as conn:
        if IS_POSTGRES:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(reminder_queue).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["dedupe_key"],
                set_={"send_at": stmt.excluded.send_at},
                where=reminder_queue.c.status == "pending",
            )
        else:
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            stmt = sqlite_insert(reminder_queue).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["dedupe_key"],
                set_={"send_at": stmt.excluded.send_at},
                where=reminder_queue.c.status == "pending",
            )
        result = conn.execute(stmt)
        return bool(result.rowcount)


def schedule_exam_reminders(
    to: str,
    exams: list[ExamEntry],
    reminder_minutes: list[int],
    timezone: str = "UTC",
    channel: str = "email",
    user_id: str | None = None,
    schedule_id: str | None = None,
) -> int:
    """Queue a reminder for each (exam, lead-time) whose send time is still in
    the future. Returns how many are now queued.

    Unlike the scheduler this replaced, this cannot silently return 0 because a
    background process isn't running — it only skips lead times that have
    genuinely already passed.
    """
    now = _now()
    queued = 0

    for exam in exams:
        start = parse_exam_datetime_in_timezone(exam.date, exam.time, timezone)
        if start is None:
            continue  # unusable date/time; the review table is where that's fixed
        payload = exam.model_dump()
        for minutes in reminder_minutes:
            send_at = start - timedelta(minutes=minutes)
            if send_at <= now:
                continue  # lead time already passed
            key = f"{channel}:{to}:{exam.course_code}:{exam.date}:{exam.time}:{minutes}"
            if enqueue(
                destination=to,
                payload=payload,
                send_at=send_at,
                dedupe_key=key,
                channel=channel,
                user_id=user_id,
                schedule_id=schedule_id,
            ):
                queued += 1

    return queued


def reclaim_stalled() -> int:
    """Return rows stuck in 'sending' (process died mid-send) to the queue."""
    cutoff = _now() - STALLED_AFTER
    with engine.begin() as conn:
        result = conn.execute(
            update(reminder_queue)
            .where(
                and_(
                    reminder_queue.c.status == "sending",
                    reminder_queue.c.claimed_at < cutoff,
                )
            )
            .values(status="pending", claimed_at=None)
        )
    return result.rowcount or 0


def claim_due(limit: int = BATCH_SIZE) -> list[dict]:
    """Atomically take up to `limit` due reminders and mark them 'sending'.

    On Postgres the claim uses FOR UPDATE SKIP LOCKED, so two overlapping
    dispatch runs take disjoint sets and a reminder can never be sent twice.
    """
    now = _now()

    with engine.begin() as conn:
        if IS_POSTGRES:
            rows = conn.execute(
                sql_text(
                    """
                    update xamio.reminder_queue q
                       set status = 'sending',
                           attempts = q.attempts + 1,
                           claimed_at = :now
                     where q.id in (
                           select id from xamio.reminder_queue
                            where status = 'pending' and send_at <= :now
                            order by send_at
                            limit :limit
                              for update skip locked
                     )
                 returning q.id, q.channel, q.destination, q.payload,
                           q.attempts, q.max_attempts
                    """
                ),
                {"now": now, "limit": limit},
            ).mappings().all()
        else:
            # SQLite is single-writer, so a plain select-then-update inside one
            # transaction is already exclusive.
            ids = [
                r[0]
                for r in conn.execute(
                    select(reminder_queue.c.id)
                    .where(
                        and_(
                            reminder_queue.c.status == "pending",
                            reminder_queue.c.send_at <= now,
                        )
                    )
                    .order_by(reminder_queue.c.send_at)
                    .limit(limit)
                ).all()
            ]
            if not ids:
                return []
            conn.execute(
                update(reminder_queue)
                .where(reminder_queue.c.id.in_(ids))
                .values(
                    status="sending",
                    attempts=reminder_queue.c.attempts + 1,
                    claimed_at=now,
                )
            )
            rows = conn.execute(
                select(
                    reminder_queue.c.id,
                    reminder_queue.c.channel,
                    reminder_queue.c.destination,
                    reminder_queue.c.payload,
                    reminder_queue.c.attempts,
                    reminder_queue.c.max_attempts,
                ).where(reminder_queue.c.id.in_(ids))
            ).mappings().all()

    return [{**dict(row), "payload": _load(row["payload"])} for row in rows]


def mark_sent(reminder_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(reminder_queue)
            .where(reminder_queue.c.id == reminder_id)
            .values(status="sent", sent_at=_now(), last_error=None)
        )


def mark_failed(reminder_id: int, error: str, attempts: int, max_attempts: int) -> None:
    """Put a failed send back on the queue, or give up once it has burned
    through its attempts — so one permanently bad address can't be retried
    forever."""
    exhausted = attempts >= max_attempts
    with engine.begin() as conn:
        conn.execute(
            update(reminder_queue)
            .where(reminder_queue.c.id == reminder_id)
            .values(
                status="failed" if exhausted else "pending",
                last_error=error[:2000],
                claimed_at=None,
            )
        )


def cancel_for_schedule(schedule_id: str) -> int:
    """Drop the pending reminders for a schedule. Used when a re-uploaded
    timetable moves or removes exams, so nobody is reminded about a sitting
    that no longer exists."""
    with engine.begin() as conn:
        result = conn.execute(
            update(reminder_queue)
            .where(
                and_(
                    reminder_queue.c.schedule_id == schedule_id,
                    reminder_queue.c.status == "pending",
                )
            )
            .values(status="cancelled")
        )
    return result.rowcount or 0


def stats() -> dict:
    """Queue health — what the old scheduler could never tell you."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(reminder_queue.c.status, func.count().label("n")).group_by(
                reminder_queue.c.status
            )
        ).all()
    return {status: count for status, count in rows}
