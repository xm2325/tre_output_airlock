from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.async_scan import AsyncScanSettings
from app.models import OutboxEvent, ScanJob


@dataclass(frozen=True)
class AsyncOperationsSnapshot:
    outbox_pending: int
    outbox_publishing: int
    outbox_stale_publishing: int
    outbox_retry_events: int
    outbox_oldest_unpublished_age_seconds: float
    scan_queued: int
    scan_processing: int
    scan_stale_processing: int
    scan_retry_jobs: int
    scan_retryable_failures: int
    scan_oldest_queued_age_seconds: float


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _count(db: Session, model: type[OutboxEvent] | type[ScanJob], *conditions: object) -> int:
    statement = select(func.count()).select_from(model)
    for condition in conditions:
        statement = statement.where(condition)  # type: ignore[arg-type]
    return int(db.scalar(statement) or 0)


def _age_seconds(value: datetime | None, now: datetime) -> float:
    if value is None:
        return 0.0
    return max(0.0, (now - _as_utc(value)).total_seconds())


def collect_async_operations_snapshot(
    db: Session,
    settings: AsyncScanSettings,
    *,
    now: datetime | None = None,
) -> AsyncOperationsSnapshot:
    current = now or datetime.now(UTC)
    outbox_cutoff = current - timedelta(seconds=settings.outbox_claim_ttl_seconds)
    worker_cutoff = current - timedelta(seconds=settings.worker_claim_ttl_seconds)

    oldest_unpublished = db.scalar(
        select(func.min(OutboxEvent.created_at)).where(
            OutboxEvent.status.in_(("PENDING", "PUBLISHING"))
        )
    )
    oldest_queued = db.scalar(
        select(func.min(ScanJob.created_at)).where(ScanJob.status == "QUEUED")
    )

    return AsyncOperationsSnapshot(
        outbox_pending=_count(db, OutboxEvent, OutboxEvent.status == "PENDING"),
        outbox_publishing=_count(db, OutboxEvent, OutboxEvent.status == "PUBLISHING"),
        outbox_stale_publishing=_count(
            db,
            OutboxEvent,
            OutboxEvent.status == "PUBLISHING",
            or_(OutboxEvent.claimed_at.is_(None), OutboxEvent.claimed_at <= outbox_cutoff),
        ),
        outbox_retry_events=_count(db, OutboxEvent, OutboxEvent.attempt_count > 1),
        outbox_oldest_unpublished_age_seconds=_age_seconds(oldest_unpublished, current),
        scan_queued=_count(db, ScanJob, ScanJob.status == "QUEUED"),
        scan_processing=_count(db, ScanJob, ScanJob.status == "PROCESSING"),
        scan_stale_processing=_count(
            db,
            ScanJob,
            ScanJob.status == "PROCESSING",
            or_(ScanJob.claimed_at.is_(None), ScanJob.claimed_at <= worker_cutoff),
        ),
        scan_retry_jobs=_count(db, ScanJob, ScanJob.attempt_count > 1),
        scan_retryable_failures=_count(
            db,
            ScanJob,
            ScanJob.status == "QUEUED",
            ScanJob.last_error.is_not(None),
        ),
        scan_oldest_queued_age_seconds=_age_seconds(oldest_queued, current),
    )


def prometheus_async_operations(snapshot: AsyncOperationsSnapshot) -> str:
    metrics = (
        (
            "airlock_async_outbox_pending",
            "Transactional outbox events waiting to be published.",
            snapshot.outbox_pending,
        ),
        (
            "airlock_async_outbox_publishing",
            "Transactional outbox events currently leased by publishers.",
            snapshot.outbox_publishing,
        ),
        (
            "airlock_async_outbox_stale_publishing",
            "Publisher leases old enough to be reclaimed.",
            snapshot.outbox_stale_publishing,
        ),
        (
            "airlock_async_outbox_retry_events",
            "Outbox events that have been claimed more than once.",
            snapshot.outbox_retry_events,
        ),
        (
            "airlock_async_outbox_oldest_unpublished_age_seconds",
            "Age of the oldest unpublished outbox event.",
            snapshot.outbox_oldest_unpublished_age_seconds,
        ),
        (
            "airlock_async_scan_queued",
            "Durable scan jobs waiting for a worker.",
            snapshot.scan_queued,
        ),
        (
            "airlock_async_scan_processing",
            "Durable scan jobs currently leased by workers.",
            snapshot.scan_processing,
        ),
        (
            "airlock_async_scan_stale_processing",
            "Worker leases old enough to be reclaimed.",
            snapshot.scan_stale_processing,
        ),
        (
            "airlock_async_scan_retry_jobs",
            "Scan jobs that have been claimed more than once.",
            snapshot.scan_retry_jobs,
        ),
        (
            "airlock_async_scan_retryable_failures",
            "Queued scan jobs carrying a retryable failure reason.",
            snapshot.scan_retryable_failures,
        ),
        (
            "airlock_async_scan_oldest_queued_age_seconds",
            "Age of the oldest queued durable scan job.",
            snapshot.scan_oldest_queued_age_seconds,
        ),
    )
    lines: list[str] = []
    for name, help_text, value in metrics:
        lines.extend((f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"))
    return "\n".join(lines) + "\n"
