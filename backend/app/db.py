from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import build_database_engine_options, load_database_pool_settings, settings


class Base(DeclarativeBase):
    pass


@dataclass(frozen=True)
class DatabasePoolSnapshot:
    configured_size: int
    max_overflow: int
    capacity: int
    checked_out: int
    checked_in: int
    overflow_open: int
    available: int
    utilisation_ratio: float


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        raw_path = database_url.removeprefix(prefix)
        if raw_path and raw_path != ":memory:":
            Path(raw_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent(settings.database_url)
engine = create_engine(
    settings.database_url,
    **build_database_engine_options(settings.database_url),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def database_pool_snapshot() -> DatabasePoolSnapshot | None:
    """Return the live per-process QueuePool state for PostgreSQL deployments.

    SQLite remains the low-friction local/demo database and intentionally does not
    publish PostgreSQL/RDS capacity metrics.
    """

    if engine.dialect.name != "postgresql" or not isinstance(engine.pool, QueuePool):
        return None

    pool_settings = load_database_pool_settings()
    capacity = pool_settings.size + pool_settings.max_overflow
    checked_out = engine.pool.checkedout()
    return DatabasePoolSnapshot(
        configured_size=pool_settings.size,
        max_overflow=pool_settings.max_overflow,
        capacity=capacity,
        checked_out=checked_out,
        checked_in=engine.pool.checkedin(),
        overflow_open=max(0, engine.pool.overflow()),
        available=max(0, capacity - checked_out),
        utilisation_ratio=checked_out / capacity,
    )


def initialise_database() -> None:
    """Create tables for the self-contained demo.

    Production deployment should use reviewed database migrations. The repository includes
    an explicit production-readiness note rather than silently changing a live schema.
    """
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
