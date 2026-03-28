from __future__ import annotations

import time
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.settings import get_settings


Base = declarative_base()
_ENGINE = None
_SESSION_FACTORY = None


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        settings = get_settings()
        connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
        _ENGINE = create_engine(
            settings.normalized_database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _ENGINE


def get_session_factory():
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)
    return _SESSION_FACTORY


def reset_db_state() -> None:
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SESSION_FACTORY = None


def wait_for_database(timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Database is not ready after {timeout_seconds} seconds") from last_error


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _migrate_existing_schema()


def _migrate_existing_schema() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    if "nesting_jobs" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("nesting_jobs")}
    statements: list[str] = []

    if engine.dialect.name == "postgresql":
        statements.extend(
            [
                "ALTER TYPE job_state ADD VALUE IF NOT EXISTS 'QUEUED'",
                "ALTER TYPE job_state ADD VALUE IF NOT EXISTS 'PARTIAL'",
                "ALTER TYPE job_state ADD VALUE IF NOT EXISTS 'CANCELLED'",
            ]
        )
        if "artifact_path" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN artifact_path VARCHAR(512)")
        if "status_message" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN status_message TEXT")
        if "progress" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN progress DOUBLE PRECISION NOT NULL DEFAULT 0")
        if "queue_attempts" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN queue_attempts INTEGER NOT NULL DEFAULT 0")
        if "queued_at" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN queued_at TIMESTAMPTZ")
        if "started_at" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN started_at TIMESTAMPTZ")
        if "heartbeat_at" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN heartbeat_at TIMESTAMPTZ")
        if "finished_at" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN finished_at TIMESTAMPTZ")
    else:
        if "artifact_path" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN artifact_path VARCHAR(512)")
        if "status_message" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN status_message TEXT")
        if "progress" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN progress FLOAT NOT NULL DEFAULT 0")
        if "queue_attempts" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN queue_attempts INTEGER NOT NULL DEFAULT 0")
        if "queued_at" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN queued_at DATETIME")
        if "started_at" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN started_at DATETIME")
        if "heartbeat_at" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN heartbeat_at DATETIME")
        if "finished_at" not in columns:
            statements.append("ALTER TABLE nesting_jobs ADD COLUMN finished_at DATETIME")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
