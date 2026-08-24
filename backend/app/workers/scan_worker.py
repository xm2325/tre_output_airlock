from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from typing import Literal
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.async_scan import AsyncScanSettings, load_async_scan_settings
from app.db import SessionLocal
from app.models import ScanJob, Submission
from app.services.audit import append_audit_event
from app.services.checker import OutputChecker
from app.services.scan_jobs import ScanMessage
from app.services.scanning import run_submission_scan
from app.services.sqs_transport import AwsSqsTransport, QueueTransport

logger = logging.getLogger(__name__)

ClaimDisposition = Literal["CLAIMED", "ALREADY_COMPLETED", "IN_PROGRESS"]
ProcessDisposition = Literal[
    "PROCESSED",
    "ALREADY_COMPLETED",
    "IN_PROGRESS",
    "LEASE_LOST",
]


@dataclass(frozen=True)
class WorkerBatchResult:
    received: int
    deleted: int
    failed: int


@dataclass(frozen=True)
class _ClaimResult:
    disposition: ClaimDisposition
    claim_token: str | None


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _log_context(message: ScanMessage, disposition: str) -> dict[str, str | None]:
    return {
        "request_id": message.request_id,
        "submission_id": message.submission_id,
        "job_id": message.job_id,
        "event_id": message.event_id,
        "disposition": disposition,
    }


def _claim_scan_job_ownership(
    db: Session,
    message: ScanMessage,
    settings: AsyncScanSettings,
    *,
    now: datetime | None = None,
) -> _ClaimResult:
    current = now or datetime.now(UTC)
    cutoff = current - timedelta(seconds=settings.worker_claim_ttl_seconds)
    job = db.scalar(select(ScanJob).where(ScanJob.id == message.job_id).with_for_update())
    if job is None:
        raise ValueError(f"Unknown scan job: {message.job_id}")
    if job.submission_id != message.submission_id:
        raise ValueError("Scan message submission_id does not match the durable job")
    if job.status == "COMPLETED":
        db.rollback()
        return _ClaimResult("ALREADY_COMPLETED", None)
    if (
        job.status == "PROCESSING"
        and job.claimed_at is not None
        and _as_utc(job.claimed_at) > cutoff
    ):
        db.rollback()
        return _ClaimResult("IN_PROGRESS", None)
    if job.status not in {"QUEUED", "PROCESSING"}:
        raise ValueError(f"Unsupported scan job state: {job.status}")

    submission = db.get(Submission, job.submission_id)
    if submission is None:
        raise ValueError(f"Submission for scan job no longer exists: {job.submission_id}")

    claim_token = str(uuid4())
    job.status = "PROCESSING"
    job.claimed_at = current
    job.claim_token = claim_token
    job.attempt_count += 1
    job.last_error = None
    submission.status = "SCANNING"
    db.commit()
    return _ClaimResult("CLAIMED", claim_token)


def claim_scan_job(
    db: Session,
    message: ScanMessage,
    settings: AsyncScanSettings,
    *,
    now: datetime | None = None,
) -> ClaimDisposition:
    """Claim a scan job while preserving the pre-v0.18 disposition-only API."""

    return _claim_scan_job_ownership(db, message, settings, now=now).disposition


def renew_scan_job_lease(
    db: Session,
    job_id: str,
    claim_token: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Renew a lease only while the caller still owns the durable claim token."""

    current = now or datetime.now(UTC)
    result = db.execute(
        update(ScanJob)
        .where(
            ScanJob.id == job_id,
            ScanJob.status == "PROCESSING",
            ScanJob.claim_token == claim_token,
        )
        .values(claimed_at=current)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        return False
    db.commit()
    return True


class ScanLeaseHeartbeat:
    """Renew database ownership and SQS invisibility while one scan is running."""

    def __init__(
        self,
        *,
        transport: QueueTransport,
        receipt_handle: str,
        job_id: str,
        claim_token: str,
        settings: AsyncScanSettings,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self.transport = transport
        self.receipt_handle = receipt_handle
        self.job_id = job_id
        self.claim_token = claim_token
        self.settings = settings
        self.session_factory = session_factory
        self._stop = Event()
        self._lost_lease = Event()
        self._thread = Thread(target=self._run, name=f"scan-heartbeat-{job_id}", daemon=True)

    @property
    def lost_lease(self) -> bool:
        return self._lost_lease.is_set()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self.settings.worker_heartbeat_interval_seconds + 1)

    def renew_once(self) -> bool:
        """Renew durable ownership first; SQS renewal is best-effort transport protection."""

        try:
            with self.session_factory() as db:
                renewed = renew_scan_job_lease(db, self.job_id, self.claim_token)
        except Exception:
            logger.exception(
                "Scan database lease heartbeat failed",
                extra={"job_id": self.job_id, "disposition": "HEARTBEAT_ERROR"},
            )
            return True
        if not renewed:
            self._lost_lease.set()
            logger.warning(
                "Scan worker lost durable claim ownership",
                extra={"job_id": self.job_id, "disposition": "LEASE_LOST"},
            )
            return False
        try:
            self.transport.change_visibility(
                self.receipt_handle,
                self.settings.visibility_timeout_seconds,
            )
        except Exception:
            # The durable claim token still protects writes if SQS visibility renewal fails.
            logger.exception(
                "SQS visibility heartbeat failed",
                extra={"job_id": self.job_id, "disposition": "VISIBILITY_RENEWAL_FAILED"},
            )
        return True

    def _run(self) -> None:
        interval = self.settings.worker_heartbeat_interval_seconds
        while not self._stop.wait(interval):
            if not self.renew_once():
                return


def process_claimed_scan_message(
    db: Session,
    message: ScanMessage,
    claim_token: str,
    *,
    checker: OutputChecker | None = None,
) -> ProcessDisposition:
    owned_job = db.scalar(
        select(ScanJob).where(
            ScanJob.id == message.job_id,
            ScanJob.status == "PROCESSING",
            ScanJob.claim_token == claim_token,
        )
    )
    submission = db.get(Submission, message.submission_id)
    if owned_job is None:
        db.rollback()
        return "LEASE_LOST"
    if submission is None:
        raise RuntimeError("Claimed scan job or submission disappeared before processing")

    try:
        run_submission_scan(
            db,
            submission,
            checker=checker or OutputChecker(),
            request_id=message.request_id,
        )
        completed_at = datetime.now(UTC)
        completion = db.execute(
            update(ScanJob)
            .where(
                ScanJob.id == message.job_id,
                ScanJob.status == "PROCESSING",
                ScanJob.claim_token == claim_token,
            )
            .values(
                status="COMPLETED",
                completed_at=completed_at,
                claimed_at=None,
                claim_token=None,
                last_error=None,
            )
            .execution_options(synchronize_session=False)
        )
        if completion.rowcount != 1:
            db.rollback()
            logger.warning(
                "Stale scan worker was fenced before commit",
                extra=_log_context(message, "LEASE_LOST"),
            )
            return "LEASE_LOST"
        db.commit()
        logger.info(
            "Async scan message processed",
            extra=_log_context(message, "PROCESSED"),
        )
        return "PROCESSED"
    except Exception as exc:
        db.rollback()
        failure = db.execute(
            update(ScanJob)
            .where(
                ScanJob.id == message.job_id,
                ScanJob.status == "PROCESSING",
                ScanJob.claim_token == claim_token,
            )
            .values(
                status="QUEUED",
                claimed_at=None,
                claim_token=None,
                last_error=str(exc)[:1000],
            )
            .execution_options(synchronize_session=False)
        )
        if failure.rowcount == 1:
            failed_submission = db.get(Submission, message.submission_id)
            if failed_submission is not None and failed_submission.status == "SCANNING":
                failed_submission.status = "QUEUED"
                append_audit_event(
                    failed_submission,
                    "SCAN_ATTEMPT_FAILED",
                    "scan-worker",
                    f"error_type={type(exc).__name__}; retryable=true.",
                    message.request_id,
                )
            db.commit()
        else:
            db.rollback()
        logger.exception(
            "Async scan message processing failed",
            extra=_log_context(message, "FAILED"),
        )
        raise


def process_scan_message(
    db: Session,
    payload: str,
    settings: AsyncScanSettings,
    *,
    checker: OutputChecker | None = None,
) -> ProcessDisposition:
    message = ScanMessage.from_json(payload)
    claim = _claim_scan_job_ownership(db, message, settings)
    if claim.disposition == "ALREADY_COMPLETED":
        logger.info(
            "Async scan message already completed",
            extra=_log_context(message, "ALREADY_COMPLETED"),
        )
        return "ALREADY_COMPLETED"
    if claim.disposition == "IN_PROGRESS":
        logger.info(
            "Async scan message already has an active lease",
            extra=_log_context(message, "IN_PROGRESS"),
        )
        return "IN_PROGRESS"
    if claim.claim_token is None:
        raise RuntimeError("Claimed scan job did not produce an ownership token")
    return process_claimed_scan_message(db, message, claim.claim_token, checker=checker)


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
    for queue_message in messages:
        try:
            message = ScanMessage.from_json(queue_message.body)
            with session_factory() as db:
                claim = _claim_scan_job_ownership(db, message, settings)
        except Exception:
            failed += 1
            logger.exception("Failed to claim asynchronous scan message")
            continue

        if claim.disposition == "ALREADY_COMPLETED":
            transport.delete(queue_message.receipt_handle)
            deleted += 1
            continue
        if claim.disposition == "IN_PROGRESS":
            # Do not acknowledge an active duplicate. If the owner later fails, this delivery
            # remains eligible for retry/redrive instead of being lost prematurely.
            continue
        if claim.claim_token is None:
            failed += 1
            continue

        heartbeat = ScanLeaseHeartbeat(
            transport=transport,
            receipt_handle=queue_message.receipt_handle,
            job_id=message.job_id,
            claim_token=claim.claim_token,
            settings=settings,
            session_factory=session_factory,
        )
        heartbeat.start()
        try:
            with session_factory() as db:
                disposition = process_claimed_scan_message(
                    db,
                    message,
                    claim.claim_token,
                    checker=checker,
                )
        except Exception:
            failed += 1
            continue
        finally:
            heartbeat.stop()

        if disposition == "PROCESSED":
            transport.delete(queue_message.receipt_handle)
            deleted += 1
        elif disposition == "LEASE_LOST":
            failed += 1

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
