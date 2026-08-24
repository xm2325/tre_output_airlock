from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.async_scan import AsyncScanSettings
from app.db import SessionLocal
from app.models import OutboxEvent, ScanJob, Submission
from app.services.async_operations import collect_async_operations_snapshot
from app.workers.scan_worker import claim_scan_job
from app.services.scan_jobs import ScanMessage


def _settings() -> AsyncScanSettings:
    return AsyncScanSettings(
        mode="queued",
        queue_url="https://sqs.example.test/scan",
        aws_region="eu-west-2",
        endpoint_url=None,
        outbox_batch_size=10,
        outbox_claim_ttl_seconds=60,
        worker_claim_ttl_seconds=120,
        receive_wait_seconds=20,
        visibility_timeout_seconds=120,
    )


def _submission(submission_id: str) -> Submission:
    return Submission(
        id=submission_id,
        project_code="OPS",
        output_type="table",
        output_description="async operations test",
        filename="ops.csv",
        content_type="text/csv",
        size_bytes=10,
        sha256="a" * 64,
        status="QUEUED",
        automated_decision="PENDING",
        final_decision=None,
        risk_score=0.0,
        policy_version="test",
        submitted_by="alice",
        row_version=1,
    )


def test_async_operations_snapshot_tracks_backlog_retries_and_stale_leases() -> None:
    now = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)
    submission_id = str(uuid4())
    queued_job_id = str(uuid4())
    processing_job_id = str(uuid4())
    with SessionLocal() as db:
        db.add(_submission(submission_id))
        db.add_all(
            [
                ScanJob(
                    id=queued_job_id,
                    submission_id=submission_id,
                    status="QUEUED",
                    attempt_count=2,
                    last_error="retryable parser failure",
                    created_at=now - timedelta(seconds=80),
                    updated_at=now - timedelta(seconds=10),
                ),
                ScanJob(
                    id=processing_job_id,
                    submission_id=submission_id,
                    status="PROCESSING",
                    attempt_count=1,
                    claimed_at=now - timedelta(seconds=180),
                    created_at=now - timedelta(seconds=200),
                    updated_at=now - timedelta(seconds=180),
                ),
            ]
        )
        db.add_all(
            [
                OutboxEvent(
                    id=str(uuid4()),
                    event_type="SCAN_REQUESTED",
                    aggregate_id=submission_id,
                    job_id=queued_job_id,
                    payload_json="{}",
                    status="PENDING",
                    attempt_count=1,
                    created_at=now - timedelta(seconds=100),
                    updated_at=now - timedelta(seconds=100),
                ),
                OutboxEvent(
                    id=str(uuid4()),
                    event_type="SCAN_REQUESTED",
                    aggregate_id=submission_id,
                    job_id=processing_job_id,
                    payload_json="{}",
                    status="PUBLISHING",
                    attempt_count=2,
                    claimed_at=now - timedelta(seconds=120),
                    created_at=now - timedelta(seconds=200),
                    updated_at=now - timedelta(seconds=120),
                ),
            ]
        )
        db.commit()

        snapshot = collect_async_operations_snapshot(db, _settings(), now=now)

    assert snapshot.outbox_pending == 1
    assert snapshot.outbox_publishing == 1
    assert snapshot.outbox_stale_publishing == 1
    assert snapshot.outbox_retry_events == 1
    assert snapshot.outbox_oldest_unpublished_age_seconds == 200.0
    assert snapshot.scan_queued == 1
    assert snapshot.scan_processing == 1
    assert snapshot.scan_stale_processing == 1
    assert snapshot.scan_retry_jobs == 1
    assert snapshot.scan_retryable_failures == 1
    assert snapshot.scan_oldest_queued_age_seconds == 80.0


def test_metrics_async_exposes_durable_state_without_changing_core_metrics(client) -> None:  # type: ignore[no-untyped-def]
    submission_id = str(uuid4())
    job_id = str(uuid4())
    with SessionLocal() as db:
        db.add(_submission(submission_id))
        db.add(
            ScanJob(
                id=job_id,
                submission_id=submission_id,
                status="QUEUED",
                attempt_count=0,
            )
        )
        db.add(
            OutboxEvent(
                id=str(uuid4()),
                event_type="SCAN_REQUESTED",
                aggregate_id=submission_id,
                job_id=job_id,
                payload_json="{}",
                status="PENDING",
                attempt_count=0,
            )
        )
        db.commit()

    core = client.get("/metrics")
    async_metrics = client.get("/metrics/async")

    assert core.status_code == 200
    assert "airlock_database_pool_" not in core.text or "airlock_http_requests_total" in core.text
    assert "airlock_async_scan_queued" not in core.text
    assert async_metrics.status_code == 200
    assert "airlock_async_outbox_pending 1" in async_metrics.text
    assert "airlock_async_scan_queued 1" in async_metrics.text
    assert "airlock_async_scan_retryable_failures 0" in async_metrics.text


def test_stale_processing_job_is_reclaimed() -> None:
    settings = _settings()
    now = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)
    submission_id = str(uuid4())
    job_id = str(uuid4())
    with SessionLocal() as db:
        db.add(_submission(submission_id))
        db.add(
            ScanJob(
                id=job_id,
                submission_id=submission_id,
                status="PROCESSING",
                attempt_count=1,
                claimed_at=now - timedelta(seconds=settings.worker_claim_ttl_seconds + 1),
            )
        )
        db.commit()

        disposition = claim_scan_job(
            db,
            ScanMessage(version=1, job_id=job_id, submission_id=submission_id),
            settings,
            now=now,
        )
        job = db.get(ScanJob, job_id)
        submission = db.get(Submission, submission_id)

    assert disposition == "CLAIMED"
    assert job is not None
    assert job.status == "PROCESSING"
    assert job.attempt_count == 2
    assert job.claimed_at == now
    assert submission is not None
    assert submission.status == "SCANNING"
