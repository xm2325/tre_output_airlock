from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.async_scan import AsyncScanSettings
from app.db import SessionLocal
from app.models import OutboxEvent, ScanJob, Submission
from app.services.outbox_publisher import claim_outbox_batch, publish_outbox_batch
from app.services.scan_jobs import enqueue_scan
from app.services.sqs_transport import QueueTransport, ReceivedQueueMessage
from app.services.storage import quarantined_path
from app.workers.scan_worker import run_worker_once


class FakeQueue(QueueTransport):
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.incoming: list[ReceivedQueueMessage] = []
        self.deleted: list[str] = []
        self.fail_send = False

    def send(self, body: str) -> str:
        if self.fail_send:
            raise RuntimeError("synthetic SQS outage")
        self.sent.append(body)
        return f"message-{len(self.sent)}"

    def receive(
        self,
        *,
        max_messages: int,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> list[ReceivedQueueMessage]:
        del wait_seconds, visibility_timeout_seconds
        messages = self.incoming[:max_messages]
        self.incoming = self.incoming[max_messages:]
        return messages

    def delete(self, receipt_handle: str) -> None:
        self.deleted.append(receipt_handle)


def queue_settings() -> AsyncScanSettings:
    return AsyncScanSettings(
        mode="queued",
        queue_url="https://example.invalid/queue",
        aws_region="eu-west-2",
        endpoint_url=None,
        outbox_batch_size=10,
        outbox_claim_ttl_seconds=30,
        worker_claim_ttl_seconds=60,
        receive_wait_seconds=0,
        visibility_timeout_seconds=60,
    )


def create_queued_submission(content: bytes = b"metric,count\nalpha,20\nbeta,25\n") -> tuple[str, str]:
    submission_id = str(uuid4())
    filename = "safe.csv"
    path = quarantined_path(submission_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    submission = Submission(
        id=submission_id,
        project_code="ASYNC-001",
        output_type="TABLE",
        output_description="Synthetic asynchronous scan pipeline test output.",
        filename=filename,
        content_type="text/csv",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        idempotency_key=None,
        status="QUARANTINED",
        automated_decision="ALLOW",
        final_decision=None,
        risk_score=0.0,
        policy_version="test-policy",
        submitted_by="async-test-researcher",
        row_version=1,
    )
    with SessionLocal() as db:
        db.add(submission)
        db.flush()
        _, outbox = enqueue_scan(db, submission, request_id="async-test-request")
        db.commit()
        return submission_id, outbox.id


def test_outbox_publish_marks_event_published() -> None:
    _, event_id = create_queued_submission()
    transport = FakeQueue()
    with SessionLocal() as db:
        result = publish_outbox_batch(db, transport, queue_settings())
        event = db.get(OutboxEvent, event_id)
        assert result.claimed == 1
        assert result.published == 1
        assert result.failed == 0
        assert len(transport.sent) == 1
        assert event is not None
        assert event.status == "PUBLISHED"
        assert event.attempt_count == 1
        assert event.published_at is not None
        assert event.claimed_at is None


def test_outbox_reclaims_after_send_before_published_commit() -> None:
    _, event_id = create_queued_submission()
    settings = queue_settings()
    transport = FakeQueue()
    first_claim_time = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    with SessionLocal() as db:
        claimed = claim_outbox_batch(db, settings, now=first_claim_time)
        assert len(claimed) == 1
        transport.send(claimed[0].payload_json)
        # Simulate a crash after SQS accepted the message but before PUBLISHED was persisted.

    retry_time = first_claim_time + timedelta(seconds=settings.outbox_claim_ttl_seconds + 1)
    with SessionLocal() as db:
        result = publish_outbox_batch(db, transport, settings, now=retry_time)
        event = db.get(OutboxEvent, event_id)
        assert result.published == 1
        assert len(transport.sent) == 2
        assert event is not None
        assert event.status == "PUBLISHED"
        assert event.attempt_count == 2


def test_outbox_send_failure_returns_event_to_pending() -> None:
    _, event_id = create_queued_submission()
    transport = FakeQueue()
    transport.fail_send = True
    with SessionLocal() as db:
        result = publish_outbox_batch(db, transport, queue_settings())
        event = db.get(OutboxEvent, event_id)
        assert result.failed == 1
        assert event is not None
        assert event.status == "PENDING"
        assert event.claimed_at is None
        assert event.last_error == "synthetic SQS outage"


def test_worker_duplicate_delivery_does_not_repeat_scan() -> None:
    submission_id, _ = create_queued_submission()
    transport = FakeQueue()
    with SessionLocal() as db:
        publish_outbox_batch(db, transport, queue_settings())
    payload = transport.sent[0]

    transport.incoming.append(
        ReceivedQueueMessage(message_id="m1", receipt_handle="r1", body=payload)
    )
    first = run_worker_once(transport, queue_settings())
    assert first.received == 1
    assert first.deleted == 1
    assert first.failed == 0

    with SessionLocal() as db:
        job = db.scalar(select(ScanJob).where(ScanJob.submission_id == submission_id))
        submission = db.get(Submission, submission_id)
        assert job is not None and job.status == "COMPLETED"
        assert submission is not None
        completed_events = [
            item.event_type
            for item in submission.audit_events
            if item.event_type == "AUTOMATED_CHECK_COMPLETED"
        ]
        assert len(completed_events) == 1
        version_after_first = submission.row_version

    transport.incoming.append(
        ReceivedQueueMessage(message_id="m2", receipt_handle="r2", body=payload)
    )
    second = run_worker_once(transport, queue_settings())
    assert second.received == 1
    assert second.deleted == 1
    assert second.failed == 0
    assert transport.deleted == ["r1", "r2"]

    with SessionLocal() as db:
        submission = db.get(Submission, submission_id)
        assert submission is not None
        assert submission.row_version == version_after_first
        assert (
            sum(
                item.event_type == "AUTOMATED_CHECK_COMPLETED"
                for item in submission.audit_events
            )
            == 1
        )


def test_worker_failure_keeps_message_for_retry() -> None:
    submission_id, _ = create_queued_submission()
    quarantined_path(submission_id, "safe.csv").unlink()
    transport = FakeQueue()
    with SessionLocal() as db:
        publish_outbox_batch(db, transport, queue_settings())
    transport.incoming.append(
        ReceivedQueueMessage(message_id="m-fail", receipt_handle="r-fail", body=transport.sent[0])
    )

    result = run_worker_once(transport, queue_settings())
    assert result.received == 1
    assert result.deleted == 0
    assert result.failed == 1
    assert transport.deleted == []
    with SessionLocal() as db:
        job = db.scalar(select(ScanJob).where(ScanJob.submission_id == submission_id))
        submission = db.get(Submission, submission_id)
        assert job is not None
        assert job.status == "QUEUED"
        assert job.attempt_count == 1
        assert job.last_error == "Quarantined file is no longer available."
        assert submission is not None and submission.status == "QUEUED"
        assert any(item.event_type == "SCAN_ATTEMPT_FAILED" for item in submission.audit_events)
