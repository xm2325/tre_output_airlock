from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


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
