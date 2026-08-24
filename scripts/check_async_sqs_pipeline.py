from __future__ import annotations

import hashlib
from uuid import uuid4

from sqlalchemy import select

from app.core.async_scan import load_async_scan_settings
from app.core.config import settings as app_settings
from app.core.policy import POLICY_VERSION
from app.db import SessionLocal
from app.models import OutboxEvent, ScanJob, Submission
from app.services.audit import append_audit_event
from app.services.outbox_publisher import publish_outbox_batch
from app.services.scan_jobs import ScanMessage, enqueue_scan
from app.services.sqs_transport import AwsSqsTransport
from app.services.storage import quarantined_path
from app.workers.scan_worker import run_worker_once


def main() -> None:
    async_settings = load_async_scan_settings()
    if async_settings.mode != "queued":
        raise SystemExit("AIRLOCK_SCAN_MODE=queued is required")
    transport = AwsSqsTransport(
        queue_url=async_settings.queue_url,
        region_name=async_settings.aws_region,
        endpoint_url=async_settings.endpoint_url,
    )

    correlation_id = "async-sqs-ci-correlation"
    content = b"metric,count\nalpha,20\nbeta,25\n"
    submission_id = str(uuid4())
    filename = "async-pipeline.csv"
    path = quarantined_path(submission_id, filename)
    app_settings.quarantine_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    submission = Submission(
        id=submission_id,
        project_code="ASYNC-SQS-CI",
        output_type="TABLE",
        output_description="Synthetic PostgreSQL and SQS asynchronous integration evidence.",
        filename=filename,
        content_type="text/csv",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        idempotency_key=None,
        status="QUARANTINED",
        automated_decision="ALLOW",
        final_decision=None,
        risk_score=0.0,
        policy_version=POLICY_VERSION,
        submitted_by="async-sqs-ci",
        row_version=1,
    )
    with SessionLocal() as db:
        append_audit_event(
            submission,
            "SUBMITTED",
            "async-sqs-ci",
            "Synthetic SQS-compatible integration submission.",
            correlation_id,
        )
        append_audit_event(
            submission,
            "QUARANTINED",
            "airlock-service",
            "Synthetic file stored for asynchronous integration validation.",
            correlation_id,
        )
        db.add(submission)
        db.flush()
        job, outbox = enqueue_scan(db, submission, request_id=correlation_id)
        job_id = job.id
        event_id = outbox.id
        payload = outbox.payload_json
        assert ScanMessage.from_json(payload).request_id == correlation_id
        db.commit()

    with SessionLocal() as db:
        publish_result = publish_outbox_batch(db, transport, async_settings)
        assert publish_result.claimed == 1, publish_result
        assert publish_result.published == 1, publish_result
        assert publish_result.failed == 0, publish_result
        outbox = db.get(OutboxEvent, event_id)
        assert outbox is not None and outbox.status == "PUBLISHED"

    first = run_worker_once(transport, async_settings)
    assert first.received == 1, first
    assert first.deleted == 1, first
    assert first.failed == 0, first

    with SessionLocal() as db:
        job = db.get(ScanJob, job_id)
        finished = db.get(Submission, submission_id)
        assert job is not None and job.status == "COMPLETED"
        assert job.attempt_count == 1
        assert job.completed_at is not None
        assert finished is not None
        assert finished.status in {"COMPLETED", "AWAITING_REVIEW"}
        assert finished.status not in {"QUEUED", "SCANNING"}
        completed_events = [
            item for item in finished.audit_events if item.event_type == "AUTOMATED_CHECK_COMPLETED"
        ]
        assert len(completed_events) == 1
        assert completed_events[0].request_id == correlation_id
        version_after_first = finished.row_version

    # Re-deliver the exact message after the durable scan transaction committed.
    # The worker must recognise the completed job and delete the duplicate without rescanning.
    transport.send(payload)
    duplicate = run_worker_once(transport, async_settings)
    assert duplicate.received == 1, duplicate
    assert duplicate.deleted == 1, duplicate
    assert duplicate.failed == 0, duplicate

    with SessionLocal() as db:
        job = db.get(ScanJob, job_id)
        finished = db.get(Submission, submission_id)
        assert job is not None and job.attempt_count == 1
        assert finished is not None and finished.row_version == version_after_first
        completed_events = [
            event
            for event in finished.audit_events
            if event.event_type == "AUTOMATED_CHECK_COMPLETED"
        ]
        assert len(completed_events) == 1
        assert completed_events[0].request_id == correlation_id
        assert db.scalar(select(OutboxEvent).where(OutboxEvent.id == event_id)) is not None

    print(
        "async SQS pipeline verified: committed outbox -> SQS -> correlated worker audit -> "
        "durable result -> duplicate-safe replay"
    )


if __name__ == "__main__":
    main()
