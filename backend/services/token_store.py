"""Persistent store for per-session Google OAuth credentials.

Replaces the previous in-memory dict so authenticated Google sessions survive a
backend restart. Backed by SQLAlchemy, so it works on SQLite today (Render free
tier) and can move to Postgres later by setting DATABASE_URL / SCHEDULER_DB_URL —
no code change required.
"""
import json
import os
from datetime import datetime, timezone as dt_timezone

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    select,
    text,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

# Share the scheduler's DB so a single Postgres URL upgrades both later.
_DB_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("SCHEDULER_DB_URL")
    or "sqlite:///reminders.sqlite"
)

# SQLAlchemy needs the postgres:// scheme spelled postgresql://
if _DB_URL.startswith("postgres://"):
    _DB_URL = _DB_URL.replace("postgres://", "postgresql://", 1)

# pool_pre_ping revalidates pooled connections (Supabase's pooler recycles
# idle ones), so a stale connection becomes a reconnect, not a 500.
_engine = create_engine(_DB_URL, future=True, pool_pre_ping=True)

# On Postgres (e.g. Supabase) keep our tables OUT of the `public` schema:
# Supabase exposes `public` through its PostgREST API, and OAuth tokens must
# never be reachable that way. A dedicated schema is invisible to PostgREST.
PRIVATE_SCHEMA = "xamio" if _engine.dialect.name == "postgresql" else None

_metadata = MetaData(schema=PRIVATE_SCHEMA)

_google_tokens = Table(
    "google_oauth_tokens",
    _metadata,
    Column("session_key", String(64), primary_key=True),
    Column("credentials", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

if PRIVATE_SCHEMA:
    with _engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{PRIVATE_SCHEMA}"'))
_metadata.create_all(_engine)


def save_credentials(session_key: str, credentials: dict) -> None:
    payload = json.dumps(credentials)
    now = datetime.now(dt_timezone.utc)
    with _engine.begin() as conn:
        if conn.dialect.name == "sqlite":
            stmt = sqlite_insert(_google_tokens).values(
                session_key=session_key, credentials=payload, updated_at=now
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["session_key"],
                set_={"credentials": payload, "updated_at": now},
            )
            conn.execute(stmt)
        else:
            # Portable upsert: delete-then-insert inside the same transaction.
            conn.execute(
                delete(_google_tokens).where(
                    _google_tokens.c.session_key == session_key
                )
            )
            conn.execute(
                _google_tokens.insert().values(
                    session_key=session_key, credentials=payload, updated_at=now
                )
            )


def get_credentials(session_key: str | None) -> dict | None:
    if not session_key:
        return None
    with _engine.connect() as conn:
        row = conn.execute(
            select(_google_tokens.c.credentials).where(
                _google_tokens.c.session_key == session_key
            )
        ).first()
    if not row:
        return None
    return json.loads(row[0])


def has_credentials(session_key: str | None) -> bool:
    return get_credentials(session_key) is not None


def delete_credentials(session_key: str) -> None:
    with _engine.begin() as conn:
        conn.execute(
            delete(_google_tokens).where(_google_tokens.c.session_key == session_key)
        )
