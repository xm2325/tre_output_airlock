from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _int_setting(name: str, default: str, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, default).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _float_setting(name: str, default: str, *, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, default).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return value


def build_database_url() -> str:
    explicit_url = os.getenv("AIRLOCK_DATABASE_URL", "").strip()
    if explicit_url:
        return explicit_url

    host = os.getenv("AIRLOCK_DATABASE_HOST", "").strip()
    if not host:
        return "sqlite:///./data/airlock.db"

    user = os.getenv("AIRLOCK_DATABASE_USER", "").strip()
    password = os.getenv("AIRLOCK_DATABASE_PASSWORD", "")
    database = os.getenv("AIRLOCK_DATABASE_NAME", "airlock").strip()
    port = os.getenv("AIRLOCK_DATABASE_PORT", "5432").strip()
    if not user or not password or not database:
        raise ValueError(
            "RDS-style database configuration requires AIRLOCK_DATABASE_USER, "
            "AIRLOCK_DATABASE_PASSWORD and AIRLOCK_DATABASE_NAME"
        )
    try:
        parsed_port = int(port)
    except ValueError as exc:
        raise ValueError("AIRLOCK_DATABASE_PORT must be an integer") from exc
    if parsed_port < 1 or parsed_port > 65535:
        raise ValueError("AIRLOCK_DATABASE_PORT must be between 1 and 65535")

    return (
        "postgresql+psycopg://"
        f"{quote(user, safe='')}:{quote(password, safe='')}@{host}:{parsed_port}/"
        f"{quote(database, safe='')}"
    )


@dataclass(frozen=True)
class DatabasePoolSettings:
    size: int
    max_overflow: int
    timeout_seconds: float
    recycle_seconds: int


def load_database_pool_settings() -> DatabasePoolSettings:
    return DatabasePoolSettings(
        size=_int_setting(
            "AIRLOCK_DATABASE_POOL_SIZE",
            "5",
            minimum=1,
            maximum=20,
        ),
        max_overflow=_int_setting(
            "AIRLOCK_DATABASE_MAX_OVERFLOW",
            "5",
            minimum=0,
            maximum=20,
        ),
        timeout_seconds=_float_setting(
            "AIRLOCK_DATABASE_POOL_TIMEOUT_SECONDS",
            "5.0",
            minimum=0.1,
            maximum=30.0,
        ),
        recycle_seconds=_int_setting(
            "AIRLOCK_DATABASE_POOL_RECYCLE_SECONDS",
            "900",
            minimum=30,
            maximum=3600,
        ),
    )


def build_database_engine_options(database_url: str) -> dict[str, object]:
    options: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        return options

    pool = load_database_pool_settings()
    options.update(
        {
            "pool_size": pool.size,
            "max_overflow": pool.max_overflow,
            "pool_timeout": pool.timeout_seconds,
            "pool_recycle": pool.recycle_seconds,
        }
    )
    return options


@dataclass(frozen=True)
class Settings:
    database_url: str = build_database_url()
    quarantine_dir: Path = Path(os.getenv("AIRLOCK_QUARANTINE_DIR", "./quarantine"))
    max_file_size_mb: int = int(os.getenv("AIRLOCK_MAX_FILE_SIZE_MB", "5"))
    retention_days: int = int(os.getenv("AIRLOCK_RETENTION_DAYS", "30"))
    review_claim_ttl_minutes: int = int(os.getenv("AIRLOCK_REVIEW_CLAIM_TTL_MINUTES", "30"))
    report_signing_secret: str = os.getenv("AIRLOCK_REPORT_SIGNING_SECRET", "demo-only-change-me")
    auto_create_schema: bool = _as_bool(os.getenv("AIRLOCK_AUTO_CREATE_SCHEMA", "true"))
    cors_origins: tuple[str, ...] = _split_csv(
        os.getenv("AIRLOCK_CORS_ORIGINS", "http://localhost:5173")
    )

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


settings = Settings()
