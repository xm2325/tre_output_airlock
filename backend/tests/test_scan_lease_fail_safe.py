from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.core.async_scan import AsyncScanSettings
from app.db import SessionLocal
from app.models import ScanJob, Submission
from app.services.scan_jobs import ScanMessage
from app.workers.scan_worker import ScanLeaseHeartbeat, process_claimed_scan_message


class VisibilityTransport:
    def __init__(self, *, fail_visibility: bool = False) -> None:
        self.fail_visibility = fail_visibility
        self.visibility_calls = 0

    def send(self, body: str) -> str:
        del body
        return "message-1"

    def receive(
        self,
        *,
        max_messages: int,
        wait_seconds: int,
        visibility_timeout_seconds: int,
    ) -> list[object]:
        del max_messages, wait_seconds, visibility_timeout_seconds
        return []

    def change_visibility(self, receipt_handle: str, visibility_timeout_seconds: int) -> None:
        del receipt_handle, visibility_timeout_seconds
        self.visibility_calls += 1
        if self.fail_visibility:
            raise RuntimeError("synthetic visibility outage")

    def delete(self, receipt_handle: str) -> None:
        del receipt_handle


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


def _processing_job(claim_token: str) -> tuple[str, str]:
    submission_id = str(uuid4())
    job_id = str(uuid4())
    with SessionLocal() as db:
        db.add(
            Submission(
                id=submission_id,
                project_code="LEASE-FAIL-SAFE",
                output_type="TABLE",
                output_description="Synthetic lost-lease test.",
                filename="lease.csv",
                content_type="text/csv",
                size_bytes=10,
                sha256="a" * 64,
                idempotency_key=None,
                status="SCANNING",
                automated_decision="ALLOW",
                final_decision=None,
                risk_score=0.0,
                policy_version="test-policy",
                submitted_by="lease-test",
                row_version=1,
            )
        )
        db.flush()
        db.add(
            ScanJob(
                id=job_id,
                submission_id=submission_id,
                status="PROCESSING",
                attempt_count=1,
                claimed_at=datetime.now(UTC),
                claim_token=claim_token,
            )
        )
        db.commit()
    return submission_id, job_id


def test_heartbeat_marks_lost_lease_without_touching_sqs() -> None:
    _, job_id = _processing_job("new-owner")
    transport = VisibilityTransport()
    heartbeat = ScanLeaseHeartbeat(
        transport=transport,
        receipt_handle="receipt-1",
        job_id=job_id,
        claim_token="stale-owner",
        settings=_settings(),
    )

    assert not heartbeat.renew_once()
    assert heartbeat.lost_lease
    assert transport.visibility_calls == 0


def test_visibility_failure_does_not_invalidate_durable_ownership() -> None:
    _, job_id = _processing_job("owner-token")
    transport = VisibilityTransport(fail_visibility=True)
    heartbeat = ScanLeaseHeartbeat(
        transport=transport,
        receipt_handle="receipt-2",
        job_id=job_id,
        claim_token="owner-token",
        settings=_settings(),
    )

    assert heartbeat.renew_once()
    assert not heartbeat.lost_lease
    assert transport.visibility_calls == 1


def test_stale_worker_is_rejected_before_scanning() -> None:
    submission_id, job_id = _processing_job("new-owner")
    message = ScanMessage(
        event_id=str(uuid4()),
        job_id=job_id,
        submission_id=submission_id,
        request_id="lease-fail-safe",
    )

    with SessionLocal() as db:
        disposition = process_claimed_scan_message(db, message, "stale-owner")

    assert disposition == "LEASE_LOST"
