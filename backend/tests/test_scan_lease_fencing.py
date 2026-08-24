from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.async_scan import AsyncScanSettings
from app.core.policy import POLICY_VERSION
from app.db import SessionLocal, engine
from app.models import ScanJob, Submission
from app.services.checker import CheckResult, OutputChecker
from app.services.scan_jobs import ScanMessage, enqueue_scan
from app.services.sqs_transport import ReceivedQueueMessage
from app.services.storage import quarantined_path
from app.workers.scan_worker import (
    ScanLeaseHeartbeat,
    claim_scan_job,
    process_claimed_scan_message,
    renew_scan_job_lease,
    run_worker_once,
)


class FakeQueue:
    def __init__(self) -> None:
        self.incoming: list[ReceivedQueueMessage] = []
        self.deleted: list[str] = []
        self.visibility_changes: list[tuple[str, int]] = []

    def send(self, body: str) -> str:
        del body
        return "message-1"

    def receive(
        self,
        *,
        max_messages: int,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> list[ReceivedQueueMessage]:
        del wait_seconds, visibility_timeout_seconds
        result = self.incoming[:max_messages]
        self.incoming = self.incoming[max_messages:]
        return result

    def change_visibility(self, receipt_handle: str, visibility_timeout_seconds: int) -> None:
        self.visibility_changes.append((receipt_handle, visibility_timeout_seconds))

    def delete(self, receipt_handle: str) -> None:
        self.deleted.append(receipt_handle)


def _settings() -> AsyncScanSettings:
    return AsyncScanSettings(
        mode="queued",
        queue_url="https://sqs.example.test/scan",
        aws_region="eu-west-2",
        endpoint_url=None,
        outbox_batch_size=10,
        outbox_claim_ttl_seconds=60,
        worker_claim_ttl_seconds=120,
        receive_wait_seconds=0,
        visibility_timeout_seconds=120,
    )


def _create_job() -> tuple[str, ScanMessage]:
    content = b"metric,count\nalpha,20\n"
    submission_id = str(uuid4())
    filename = "lease.csv"
    path = quarantined_path(submission_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    submission = Submission(
        id=submission_id,
        project_code="LEASE-CI",
        output_type="TABLE",
        output_description="Synthetic scan lease fencing contract.",
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
        submitted_by="lease-test",
        row_version=1,
    )
    with SessionLocal() as db:
        db.add(submission)
        db.flush()
        job, outbox = enqueue_scan(db, submission, request_id="lease-request")
        message = ScanMessage.from_json(outbox.payload_json)
        job_id = job.id
        db.commit()
    return job_id, message


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def test_claim_token_renews_and_stale_owner_cannot_renew() -> None:
    settings = _settings()
    job_id, message = _create_job()
    started = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)

    with SessionLocal() as db:
        assert claim_scan_job(db, message, settings, now=started) == "CLAIMED"
        first = db.get(ScanJob, job_id)
        assert first is not None and first.claim_token
        first_token = first.claim_token

    renewed_at = started + timedelta(seconds=30)
    with SessionLocal() as db:
        assert renew_scan_job_lease(db, job_id, first_token, now=renewed_at)
        renewed = db.get(ScanJob, job_id)
        assert renewed is not None and renewed.claimed_at is not None
        assert _as_utc(renewed.claimed_at) == renewed_at

    reclaimed_at = renewed_at + timedelta(seconds=settings.worker_claim_ttl_seconds + 1)
    with SessionLocal() as db:
        assert claim_scan_job(db, message, settings, now=reclaimed_at) == "CLAIMED"
        second = db.get(ScanJob, job_id)
        assert second is not None and second.claim_token
        assert second.claim_token != first_token
        assert second.attempt_count == 2

    with SessionLocal() as db:
        assert not renew_scan_job_lease(
            db,
            job_id,
            first_token,
            now=reclaimed_at + timedelta(seconds=1),
        )


def test_heartbeat_renews_database_lease_and_sqs_visibility() -> None:
    settings = _settings()
    job_id, message = _create_job()
    with SessionLocal() as db:
        assert claim_scan_job(db, message, settings) == "CLAIMED"
        job = db.get(ScanJob, job_id)
        assert job is not None and job.claim_token
        token = job.claim_token
        previous_claimed_at = job.claimed_at

    transport = FakeQueue()
    heartbeat = ScanLeaseHeartbeat(
        transport=transport,
        receipt_handle="receipt-1",
        job_id=job_id,
        claim_token=token,
        settings=settings,
    )
    assert heartbeat.renew_once()
    assert not heartbeat.lost_lease
    assert transport.visibility_changes == [("receipt-1", settings.visibility_timeout_seconds)]

    with SessionLocal() as db:
        renewed = db.get(ScanJob, job_id)
        assert renewed is not None and renewed.claimed_at is not None
        assert previous_claimed_at is not None
        assert _as_utc(renewed.claimed_at) >= _as_utc(previous_claimed_at)


def test_active_duplicate_delivery_is_not_acknowledged() -> None:
    settings = _settings()
    _, message = _create_job()
    with SessionLocal() as db:
        assert claim_scan_job(db, message, settings) == "CLAIMED"

    transport = FakeQueue()
    transport.incoming.append(
        ReceivedQueueMessage(
            message_id="duplicate-active",
            receipt_handle="duplicate-receipt",
            body=message.to_json(),
        )
    )

    result = run_worker_once(transport, settings)

    assert result.received == 1
    assert result.deleted == 0
    assert result.failed == 0
    assert transport.deleted == []


class LeaseStealingChecker(OutputChecker):
    def __init__(self, job_id: str, replacement_token: str) -> None:
        super().__init__(rules=[])
        self.job_id = job_id
        self.replacement_token = replacement_token

    def check(self, context) -> CheckResult:  # type: ignore[no-untyped-def]
        del context
        with SessionLocal() as other:
            job = other.get(ScanJob, self.job_id)
            assert job is not None
            job.claim_token = self.replacement_token
            job.claimed_at = datetime.now(UTC)
            job.attempt_count += 1
            other.commit()
        return CheckResult(
            decision="ALLOW",
            risk_score=0.0,
            risk_band="LOW",
            policy_version=POLICY_VERSION,
            findings=[],
        )


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="requires concurrent PG transactions")
def test_postgres_stale_worker_is_fenced_after_scan_before_commit() -> None:
    settings = _settings()
    job_id, message = _create_job()
    with SessionLocal() as db:
        assert claim_scan_job(db, message, settings) == "CLAIMED"
        job = db.get(ScanJob, job_id)
        submission = db.get(Submission, message.submission_id)
        assert job is not None and job.claim_token
        assert submission is not None
        stale_token = job.claim_token
        version_before = submission.row_version

    replacement_token = str(uuid4())
    with SessionLocal() as db:
        disposition = process_claimed_scan_message(
            db,
            message,
            stale_token,
            checker=LeaseStealingChecker(job_id, replacement_token),
        )

    assert disposition == "LEASE_LOST"
    with SessionLocal() as db:
        job = db.get(ScanJob, job_id)
        submission = db.get(Submission, message.submission_id)
        assert job is not None
        assert job.status == "PROCESSING"
        assert job.claim_token == replacement_token
        assert job.attempt_count == 2
        assert submission is not None
        assert submission.row_version == version_before
        event_types = [event.event_type for event in submission.audit_events]
        assert "SCAN_STARTED" not in event_types
        assert "AUTOMATED_CHECK_COMPLETED" not in event_types
        assert db.scalar(select(ScanJob.claim_token).where(ScanJob.id == job_id)) == replacement_token
