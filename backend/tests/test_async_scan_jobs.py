from __future__ import annotations

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import OutboxEvent, ScanJob, Submission
from app.services.scan_jobs import ScanMessage, enqueue_scan


def make_submission(submission_id: str = "async-submission-0001") -> Submission:
    return Submission(
        id=submission_id,
        project_code="ASYNC-CI",
        output_type="TABLE",
        output_description="Synthetic aggregate output for async scan contract testing.",
        filename="safe.csv",
        content_type="text/csv",
        size_bytes=24,
        sha256="a" * 64,
        idempotency_key=None,
        status="QUARANTINED",
        automated_decision="ALLOW",
        final_decision=None,
        risk_score=0.0,
        policy_version="test-policy",
        submitted_by="xiaomei-researcher",
        row_version=1,
    )


def test_scan_message_round_trip_is_versioned_and_correlated() -> None:
    message = ScanMessage(
        event_id="event-001",
        job_id="job-001",
        submission_id="submission-001",
        request_id="request-001",
    )

    encoded = message.to_json()

    assert ScanMessage.from_json(encoded) == message
    assert '"schema_version":2' in encoded
    assert '"request_id":"request-001"' in encoded


def test_scan_message_accepts_legacy_v1_without_request_id() -> None:
    payload = '{"event_id":"e","job_id":"j","schema_version":1,"submission_id":"s"}'

    message = ScanMessage.from_json(payload)

    assert message == ScanMessage(
        event_id="e",
        job_id="j",
        submission_id="s",
        request_id=None,
        schema_version=1,
    )
    assert message.to_json() == payload


def test_scan_message_rejects_invalid_contract() -> None:
    for payload in (
        "not-json",
        "[]",
        '{"schema_version":3,"event_id":"e","job_id":"j","submission_id":"s","request_id":"r"}',
        '{"schema_version":2,"event_id":"e","job_id":"j","submission_id":"s"}',
        '{"schema_version":2,"event_id":"e","job_id":"j","submission_id":"s","request_id":""}',
        '{"schema_version":1,"event_id":"","job_id":"j","submission_id":"s"}',
    ):
        try:
            ScanMessage.from_json(payload)
        except ValueError:
            continue
        raise AssertionError(f"Expected invalid scan message to fail: {payload}")


def test_scan_message_v2_encoder_requires_request_id() -> None:
    message = ScanMessage(event_id="e", job_id="j", submission_id="s")

    try:
        message.to_json()
    except ValueError as exc:
        assert str(exc) == "Scan message request_id must be a non-empty string"
    else:
        raise AssertionError("Expected v2 message without request_id to fail")


def test_enqueue_scan_commit_persists_submission_job_outbox_and_audit() -> None:
    submission = make_submission()
    with SessionLocal() as db:
        db.add(submission)
        job, outbox = enqueue_scan(db, submission, request_id="request-001")
        db.commit()
        job_id = job.id
        event_id = outbox.id

    with SessionLocal() as db:
        stored_submission = db.get(Submission, submission.id)
        stored_job = db.get(ScanJob, job_id)
        stored_outbox = db.get(OutboxEvent, event_id)

        assert stored_submission is not None
        assert stored_submission.status == "QUEUED"
        assert [event.event_type for event in stored_submission.audit_events] == ["SCAN_QUEUED"]
        assert stored_submission.audit_events[0].request_id == "request-001"
        assert stored_job is not None
        assert stored_job.submission_id == submission.id
        assert stored_job.status == "QUEUED"
        assert stored_job.attempt_count == 0
        assert stored_outbox is not None
        assert stored_outbox.job_id == job_id
        assert stored_outbox.aggregate_id == submission.id
        assert stored_outbox.status == "PENDING"
        assert stored_outbox.attempt_count == 0
        assert ScanMessage.from_json(stored_outbox.payload_json) == ScanMessage(
            event_id=event_id,
            job_id=job_id,
            submission_id=submission.id,
            request_id="request-001",
        )


def test_enqueue_scan_generates_correlation_when_no_http_request_id_exists() -> None:
    submission = make_submission("async-submission-generated-correlation")
    with SessionLocal() as db:
        db.add(submission)
        _, outbox = enqueue_scan(db, submission, request_id=None)
        db.commit()
        event_id = outbox.id

    with SessionLocal() as db:
        stored_submission = db.get(Submission, submission.id)
        stored_outbox = db.get(OutboxEvent, event_id)
        assert stored_submission is not None
        assert stored_outbox is not None
        message = ScanMessage.from_json(stored_outbox.payload_json)
        assert message.request_id
        assert stored_submission.audit_events[0].request_id == message.request_id


def test_enqueue_scan_rollback_leaves_no_partial_job_or_outbox() -> None:
    submission = make_submission()
    with SessionLocal() as db:
        db.add(submission)
        enqueue_scan(db, submission, request_id="request-rollback")
        assert db.scalar(select(func.count()).select_from(ScanJob)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        db.rollback()

    with SessionLocal() as db:
        assert db.get(Submission, submission.id) is None
        assert db.scalar(select(func.count()).select_from(ScanJob)) == 0
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 0
