from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.async_scan import AsyncScanSettings
from app.models import OutboxEvent
from app.services.sqs_transport import QueueTransport


@dataclass(frozen=True)
class PublishBatchResult:
    claimed: int
    published: int
    failed: int


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def claim_outbox_batch(
    db: Session,
    settings: AsyncScanSettings,
    *,
    now: datetime | None = None,
) -> list[OutboxEvent]:
    """Lease pending/recoverable events without holding DB locks during SQS I/O."""

    current = now or datetime.now(UTC)
    cutoff = current - timedelta(seconds=settings.outbox_claim_ttl_seconds)
    statement = (
        select(OutboxEvent)
        .where(
            or_(
                OutboxEvent.status == "PENDING",
                and_(
                    OutboxEvent.status == "PUBLISHING",
                    or_(OutboxEvent.claimed_at.is_(None), OutboxEvent.claimed_at <= cutoff),
                ),
            )
        )
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(settings.outbox_batch_size)
        .with_for_update(skip_locked=True)
    )
    events = list(db.scalars(statement))
    for event in events:
        event.status = "PUBLISHING"
        event.claimed_at = current
        event.attempt_count += 1
        event.last_error = None
    db.commit()
    return events


def publish_outbox_batch(
    db: Session,
    transport: QueueTransport,
    settings: AsyncScanSettings,
    *,
    now: datetime | None = None,
) -> PublishBatchResult:
    events = claim_outbox_batch(db, settings, now=now)
    published = 0
    failed = 0
    for event in events:
        try:
            transport.send(event.payload_json)
        except Exception as exc:
            db.rollback()
            current = db.get(OutboxEvent, event.id)
            if current is not None and current.status != "PUBLISHED":
                current.status = "PENDING"
                current.claimed_at = None
                current.last_error = str(exc)[:1000]
                db.commit()
            failed += 1
            continue

        current = db.get(OutboxEvent, event.id)
        if current is None:
            raise RuntimeError(f"Outbox event disappeared after publish: {event.id}")
        current.status = "PUBLISHED"
        current.published_at = datetime.now(UTC)
        current.claimed_at = None
        current.last_error = None
        db.commit()
        published += 1

    return PublishBatchResult(claimed=len(events), published=published, failed=failed)
