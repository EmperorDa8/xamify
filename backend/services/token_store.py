"""Persistent store for per-session Google OAuth credentials.

Replaces the previous in-memory dict so authenticated Google sessions survive a
backend restart. Uses the shared engine in services.db, so one DATABASE_URL
moves this and the reminder queue to Postgres together.
"""
import json
from datetime import datetime, timezone as dt_timezone

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Text,
    delete,
    select,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from services.db import PRIVATE_SCHEMA, engine as _engine, ensure_schema

_metadata = MetaData(schema=PRIVATE_SCHEMA)

_google_tokens = Table(
    "google_oauth_tokens",
    _metadata,
    Column("session_key", String(64), primary_key=True),
    Column("credentials", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ensure_schema()
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
