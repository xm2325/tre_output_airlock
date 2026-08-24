from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.async_scan import AsyncScanSettings, load_async_scan_settings
from app.db import SessionLocal
from app.models import ScanJob, Submission
from app.services.audit import append_audit_event
from app.services.checker import OutputChecker
from app.services.scan_jobs import ScanMessage
from app.services.scanning import run_submission_scan
from app.services.sqs_transport import AwsSqsTransport, QueueTransport

ClaimDisposition = Literal["CLAIMED", "ALREADY_COMPLETED", "IN_PROGRESS"]
ProcessDisposition = Literal["PROCESSED", "ALREADY_COMPLETED", "IN_PROGRESS"]


@dataclass(frozen=True)
class WorkerBatchResult:
    received: int
    deleted: int
    failed: int


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def claim_scan_job(
    db: Session,
    message: ScanMessage,
    settings: AsyncScanSettings,
    *,
    now: datetime | None = None,
) -> ClaimDisposition:
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(seconds=settings.worker_claim_ttl_seconds)
    job = db.scalar(select(ScanJob).where(ScanJob.id == message.job_id).with_for_update())
    if job is None:
        raise ValueError(f"Unknown scan job: {message.job_id}")
    if job.submission_id != message.submission_id:
        raise ValueError("Scan message submission_id does not match the durable job")
    if job.status == "COMPLETED":
        db.rollback()
        return "ALREADY_COMPLETED"
    if (
        job.status == "PROCESSING"
        and job.claimed_at is not None
        and _as_utc(job.claimed_at) > cutoff
    ):
        db.rollback()
        return "IN_PROGRESS"
    if job.status not in {"QUEUED", "PROCESSING"}:
        raise ValueError(f"Unsupported scan job state: {job.status}")

    submission = db.get(Submission, job.submission_id)
    if submission is None:
        raise ValueError(f"Submission for scan job no longer exists: {job.submission_id}")

    job.status = "PROCESSING"
    job.claimed_at = current
    job.attempt_count += 1
    job.last_error = None
    submission.status = "SCANNING"
    db.commit()
    return "CLAIMED"


def process_scan_message(
    db: Session,
    payload: str,
    settings: AsyncScanSettings,
    *,
    checker: OutputChecker | None = None,
) -> ProcessDisposition:
    message = ScanMessage.from_json(payload)
    claim = claim_scan_job(db, message, settings)
    if claim == "ALREADY_COMPLETED":
        return "ALREADY_COMPLETED"
    if claim == "IN_PROGRESS":
        return "IN_PROGRESS"

    job = db.get(ScanJob, message.job_id)
    submission = db.get(Submission, message.submission_id)
    if job is None or submission is None:
        raise RuntimeError("Claimed scan job or submission disappeared before processing")

    try:
        run_submission_scan(
            db,
            submission,
            checker=checker or OutputChecker(),
            request_id=None,
        )
        job.status = "COMPLETED"
        job.completed_at = datetime.now(UTC)
        job.claimed_at = None
        job.last_error = None
        db.commit()
        return "PROCESSED"
    except Exception as exc:
        db.rollback()
        failed_job = db.get(ScanJob, message.job_id)
        failed_submission = db.get(Submission, message.submission_id)
        if failed_job is not None and failed_job.status != "COMPLETED":
            failed_job.status = "QUEUED"
            failed_job.claimed_at = None
            failed_job.last_error = str(exc)[:1000]
        if failed_submission is not None and failed_submission.status == "SCANNING":
            failed_submission.status = "QUEUED"
            append_audit_event(
                failed_submission,
                "SCAN_ATTEMPT_FAILED",
                "scan-worker",
                f"error_type={type(exc).__name__}; retryable=true.",
                None,
            )
        db.commit()
        raise


def run_worker_once(
    transport: QueueTransport,
    settings: AsyncScanSettings,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    checker: OutputChecker | None = None,
) -> WorkerBatchResult:
    messages = transport.receive(
        max_messages=1,
        wait_seconds=settings.receive_wait_seconds,
        visibility_timeout_seconds=settings.visibility_timeout_seconds,
    )
    deleted = 0
    failed = 0
    for message in messages:
        with session_factory() as db:
            try:
                process_scan_message(db, message.body, settings, checker=checker)
            except Exception:
                failed += 1
                continue
        transport.delete(message.receipt_handle)
        deleted += 1
    return WorkerBatchResult(received=len(messages), deleted=deleted, failed=failed)


def main() -> None:
    settings = load_async_scan_settings()
    transport = AwsSqsTransport(
        queue_url=settings.queue_url,
        region_name=settings.aws_region,
        endpoint_url=settings.endpoint_url,
    )
    while True:
        run_worker_once(transport, settings)


if __name__ == "__main__":
    main()
