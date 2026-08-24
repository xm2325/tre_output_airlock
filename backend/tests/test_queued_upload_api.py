from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import IdempotencyRecord, OutboxEvent, ScanJob, Submission

RESEARCHER = {"X-Demo-User": "queued-researcher", "X-Demo-Role": "researcher"}
KEY = "queued-request-0001"
CONTENT = b"group,count\nA,20\nB,25\n"


def upload(
    client: TestClient,
    *,
    key: str = KEY,
    content: bytes = CONTENT,
):
    return client.post(
        "/api/v1/submissions",
        headers={**RESEARCHER, "Idempotency-Key": key},
        files={"file": ("queued.csv", content, "text/csv")},
        data={
            "project_code": "ASYNC-API",
            "output_type": "TABLE",
            "output_description": "Synthetic queued output for asynchronous API contract testing.",
        },
    )


def test_queued_upload_returns_before_checker_and_persists_one_job(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AIRLOCK_SCAN_MODE", "queued")

    response = upload(client)

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "QUEUED"
    assert payload["findings"] == []
    assert payload["risk_score"] == 0.0
    assert response.headers["idempotency-replayed"] == "false"
    assert [event["event_type"] for event in payload["audit_events"]] == [
        "SUBMITTED",
        "QUARANTINED",
        "SCAN_QUEUED",
    ]

    with SessionLocal() as db:
        submission = db.get(Submission, payload["id"])
        jobs = list(db.scalars(select(ScanJob)))
        events = list(db.scalars(select(OutboxEvent)))
        assert submission is not None and submission.status == "QUEUED"
        assert len(jobs) == 1
        assert len(events) == 1
        assert jobs[0].submission_id == submission.id
        assert jobs[0].status == "QUEUED"
        assert events[0].job_id == jobs[0].id
        assert events[0].aggregate_id == submission.id
        assert events[0].status == "PENDING"


def test_queued_idempotent_replay_does_not_create_another_job(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AIRLOCK_SCAN_MODE", "queued")

    first = upload(client)
    second = upload(client)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.headers["idempotency-replayed"] == "false"
    assert second.headers["idempotency-replayed"] == "true"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 1
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        assert db.scalar(select(func.count()).select_from(ScanJob)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_queued_idempotency_conflict_rolls_back_loser_job_and_outbox(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AIRLOCK_SCAN_MODE", "queued")

    first = upload(client)
    conflict = upload(client, content=b"group,count\nA,99\nB,98\n")

    assert first.status_code == 202
    assert conflict.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 1
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1
        assert db.scalar(select(func.count()).select_from(ScanJob)) == 1
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1
