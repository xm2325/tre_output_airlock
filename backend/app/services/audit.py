from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from app.models import AuditEvent, Submission

GENESIS_HASH = "0" * 64


def _event_digest(
    submission_id: str,
    event_type: str,
    actor: str,
    detail: str,
    request_id: str | None,
    created_at: datetime,
    prev_hash: str,
) -> str:
    normalised_time = (
        created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=UTC)
    )
    value = "|".join(
        [
            submission_id,
            event_type,
            actor,
            detail,
            request_id or "",
            normalised_time.astimezone(UTC).isoformat(),
            prev_hash,
        ]
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def append_audit_event(
    submission: Submission,
    event_type: str,
    actor: str,
    detail: str,
    request_id: str | None = None,
) -> AuditEvent:
    previous = submission.audit_events[-1].event_hash if submission.audit_events else GENESIS_HASH
    created_at = datetime.now(UTC)
    event = AuditEvent(
        event_type=event_type,
        actor=actor,
        detail=detail,
        request_id=request_id,
        prev_hash=previous,
        event_hash=_event_digest(
            submission.id, event_type, actor, detail, request_id, created_at, previous
        ),
        created_at=created_at,
    )
    submission.audit_events.append(event)
    return event


def verify_audit_chain(submission: Submission) -> tuple[bool, int | None]:
    previous = GENESIS_HASH
    for event in sorted(submission.audit_events, key=lambda item: item.id or 0):
        expected = _event_digest(
            submission.id,
            event.event_type,
            event.actor,
            event.detail,
            event.request_id,
            event.created_at,
            previous,
        )
        if event.prev_hash != previous or event.event_hash != expected:
            return False, event.id
        previous = event.event_hash
    return True, None
