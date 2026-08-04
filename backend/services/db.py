"""Shared SQLAlchemy engine for Xamio's own tables.

Both the reminder queue and the Google OAuth token store live here, so they
share one connection pool and one place that decides where the database is.

Defaults to a local SQLite file, which is fine on a developer machine. In
production DATABASE_URL must point at real Postgres (the Supabase session
pooler): Render's free-tier disk is EPHEMERAL, so SQLite there is wiped on every
deploy — silently taking queued reminders and Google connections with it.
"""
import os

from sqlalchemy import create_engine, text

_DB_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("SCHEDULER_DB_URL")
    or "sqlite:///reminders.sqlite"
)

# SQLAlchemy needs the postgres:// scheme spelled postgresql://
if _DB_URL.startswith("postgres://"):
    _DB_URL = _DB_URL.replace("postgres://", "postgresql://", 1)

DB_URL = _DB_URL

# pool_pre_ping revalidates pooled connections (Supabase's pooler recycles idle
# ones), so a stale connection becomes a reconnect rather than a 500.
engine = create_engine(_DB_URL, future=True, pool_pre_ping=True)

IS_POSTGRES = engine.dialect.name == "postgresql"

# On Postgres keep our tables OUT of `public`: Supabase exposes that schema
# through PostgREST, and neither OAuth tokens nor recipient addresses should
# ever be reachable that way. SQLite has no schemas, hence None.
PRIVATE_SCHEMA = "xamio" if IS_POSTGRES else None


def ensure_schema() -> None:
    """Create the private schema if it doesn't exist. SQLAlchemy's create_all
    makes tables but not the schema that holds them."""
    if not PRIVATE_SCHEMA:
        return
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{PRIVATE_SCHEMA}"'))


_prepared: set[int] = set()


def prepare(metadata) -> None:
    """Create the private schema and this metadata's tables, once per process.

    Deliberately lazy. Doing this at import time meant a wrong DATABASE_URL took
    the entire service down at startup — uvicorn exited before binding a port,
    so /health and /parse died too even though neither touches Postgres. A
    database misconfiguration should fail the requests that need the database,
    not the whole API.
    """
    key = id(metadata)
    if key in _prepared:
        return
    ensure_schema()
    metadata.create_all(engine, checkfirst=True)
    _prepared.add(key)
