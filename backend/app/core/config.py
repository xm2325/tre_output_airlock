from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("AIRLOCK_DATABASE_URL", "sqlite:///./data/airlock.db")
    quarantine_dir: Path = Path(os.getenv("AIRLOCK_QUARANTINE_DIR", "./quarantine"))
    max_file_size_mb: int = int(os.getenv("AIRLOCK_MAX_FILE_SIZE_MB", "5"))
    retention_days: int = int(os.getenv("AIRLOCK_RETENTION_DAYS", "30"))
    report_signing_secret: str = os.getenv("AIRLOCK_REPORT_SIGNING_SECRET", "demo-only-change-me")
    auto_create_schema: bool = _as_bool(os.getenv("AIRLOCK_AUTO_CREATE_SCHEMA", "true"))
    cors_origins: tuple[str, ...] = _split_csv(
        os.getenv("AIRLOCK_CORS_ORIGINS", "http://localhost:5173")
    )

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


settings = Settings()
