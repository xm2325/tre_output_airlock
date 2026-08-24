from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import OutboxEvent, ScanJob, Submission
from app.services.audit import append_audit_event

SCAN_MESSAGE_SCHEMA_VERSION = 2
SUPPORTED_SCAN_MESSAGE_SCHEMA_VERSIONS = {1, SCAN_MESSAGE_SCHEMA_VERSION}
SCAN_REQUESTED_EVENT = "SCAN_REQUESTED"


@dataclass(frozen=True)
class ScanMessage:
    event_id: str
    job_id: str
    submission_id: str
    request_id: str | None = None
    schema_version: int = SCAN_MESSAGE_SCHEMA_VERSION

    def to_json(self) -> str:
        payload: dict[str, object] = {
            "event_id": self.event_id,
            "job_id": self.job_id,
            "schema_version": self.schema_version,
            "submission_id": self.submission_id,
        }
        if self.schema_version >= 2:
            if not isinstance(self.request_id, str) or not self.request_id.strip():
                raise ValueError("Scan message request_id must be a non-empty string")
            payload["request_id"] = self.request_id
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> ScanMessage:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Scan message must be valid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("Scan message must be a JSON object")
        schema_version = data.get("schema_version")
        if schema_version not in SUPPORTED_SCAN_MESSAGE_SCHEMA_VERSIONS:
            raise ValueError("Unsupported scan message schema version")
        required = ("event_id", "job_id", "submission_id")
        values: dict[str, str] = {}
        for field in required:
            value = data.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Scan message {field} must be a non-empty string")
            values[field] = value

        request_id: str | None = None
        if schema_version >= 2:
            value = data.get("request_id")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Scan message request_id must be a non-empty string")
            request_id = value

        return cls(
            event_id=values["event_id"],
            job_id=values["job_id"],
            submission_id=values["submission_id"],
            request_id=request_id,
            schema_version=schema_version,
        )


def enqueue_scan(
    db: Session,
    submission: Submission,
    *,
    request_id: str | None,
) -> tuple[ScanJob, OutboxEvent]:
    """Persist a scan job and its transport intent without committing the transaction."""

    job_id = str(uuid4())
    event_id = str(uuid4())
    correlation_id = request_id.strip() if request_id and request_id.strip() else str(uuid4())
    job = ScanJob(
        id=job_id,
        submission_id=submission.id,
        status="QUEUED",
        attempt_count=0,
    )
    message = ScanMessage(
        event_id=event_id,
        job_id=job_id,
        submission_id=submission.id,
        request_id=correlation_id,
    )
    outbox = OutboxEvent(
        id=event_id,
        event_type=SCAN_REQUESTED_EVENT,
        aggregate_id=submission.id,
        job_id=job_id,
        payload_json=message.to_json(),
        status="PENDING",
        attempt_count=0,
    )

    submission.status = "QUEUED"
    append_audit_event(
        submission,
        "SCAN_QUEUED",
        "airlock-service",
        f"scan_job_id={job_id}; outbox_event_id={event_id}.",
        correlation_id,
    )

    db.add(submission)
    db.flush()
    db.add(job)
    db.flush()
    db.add(outbox)
    db.flush()
    return job, outbox
