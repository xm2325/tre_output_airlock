from __future__ import annotations

import os
from dataclasses import dataclass


def _int_setting(name: str, default: str, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, default).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _mode_setting() -> str:
    value = os.getenv("AIRLOCK_SCAN_MODE", "synchronous").strip().lower()
    if value not in {"synchronous", "queued"}:
        raise ValueError("AIRLOCK_SCAN_MODE must be synchronous or queued")
    return value


@dataclass(frozen=True)
class AsyncScanSettings:
    mode: str
    queue_url: str
    aws_region: str
    endpoint_url: str | None
    outbox_batch_size: int
    outbox_claim_ttl_seconds: int
    worker_claim_ttl_seconds: int
    receive_wait_seconds: int
    visibility_timeout_seconds: int


def load_async_scan_settings() -> AsyncScanSettings:
    endpoint = os.getenv("AIRLOCK_SQS_ENDPOINT_URL", "").strip()
    return AsyncScanSettings(
        mode=_mode_setting(),
        queue_url=os.getenv("AIRLOCK_SCAN_QUEUE_URL", "").strip(),
        aws_region=os.getenv("AIRLOCK_AWS_REGION", "eu-west-2").strip() or "eu-west-2",
        endpoint_url=endpoint or None,
        outbox_batch_size=_int_setting(
            "AIRLOCK_OUTBOX_BATCH_SIZE", "10", minimum=1, maximum=100
        ),
        outbox_claim_ttl_seconds=_int_setting(
            "AIRLOCK_OUTBOX_CLAIM_TTL_SECONDS", "60", minimum=5, maximum=900
        ),
        worker_claim_ttl_seconds=_int_setting(
            "AIRLOCK_SCAN_WORKER_CLAIM_TTL_SECONDS", "120", minimum=10, maximum=3600
        ),
        receive_wait_seconds=_int_setting(
            "AIRLOCK_SQS_WAIT_TIME_SECONDS", "20", minimum=0, maximum=20
        ),
        visibility_timeout_seconds=_int_setting(
            "AIRLOCK_SQS_VISIBILITY_TIMEOUT_SECONDS", "120", minimum=10, maximum=43200
        ),
    )
