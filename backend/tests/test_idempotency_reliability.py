from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import app.api.submission_routes as submission_routes
from app.core.config import settings
from app.core.idempotency import idempotency_scope_key
from app.db import SessionLocal, engine
from app.models import IdempotencyRecord, Submission

RESEARCHER = {"X-Demo-User": "xiaomei-researcher", "X-Demo-Role": "researcher"}
OTHER_RESEARCHER = {"X-Demo-User": "other-researcher", "X-Demo-Role": "researcher"}
KEY = "reliable-request-0001"


def upload(
    client: TestClient,
    *,
    headers: dict[str, str] = RESEARCHER,
    key: str = KEY,
    content: bytes = b"group,mean\nA,1.2\nB,1.5\n",
    project_code: str = "IDEMPOTENCY-CI",
    description: str = "Synthetic aggregate output for idempotency reliability testing.",
):
    return client.post(
        "/api/v1/submissions",
        headers={**headers, "Idempotency-Key": key},
        files={"file": ("safe.csv", content, "text/csv")},
        data={
            "project_code": project_code,
            "output_type": "TABLE",
            "output_description": description,
        },
    )


def test_same_actor_same_key_same_payload_replays(client: TestClient) -> None:
    first = upload(client)
    second = upload(client)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.headers["idempotency-replayed"] == "false"
    assert second.headers["idempotency-replayed"] == "true"
    assert first.headers["etag"] == second.headers["etag"]

    with SessionLocal() as db:
        submissions = list(db.scalars(select(Submission)))
        records = list(db.scalars(select(IdempotencyRecord)))
        assert len(submissions) == 1
        assert len(records) == 1
        assert submissions[0].idempotency_key is None
        assert records[0].submitted_by == "xiaomei-researcher"
        assert records[0].scope_key == idempotency_scope_key("xiaomei-researcher", KEY)
        assert records[0].submission_id == submissions[0].id


def test_same_actor_same_key_different_payload_conflicts(client: TestClient) -> None:
    first = upload(client)
    assert first.status_code == 201
    before = set(settings.quarantine_dir.iterdir())

    conflict = upload(client, content=b"group,mean\nA,9.9\nB,8.8\n")

    assert conflict.status_code == 409
    assert "different request payload" in conflict.json()["detail"].lower()
    assert set(settings.quarantine_dir.iterdir()) == before
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 1
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1


def test_same_actor_same_key_different_metadata_conflicts(client: TestClient) -> None:
    first = upload(client)
    assert first.status_code == 201

    conflict = upload(
        client,
        description="A different synthetic description must not silently replay the first request.",
    )

    assert conflict.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Submission)) == 1
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 1


def test_different_actors_can_reuse_same_raw_key(client: TestClient) -> None:
    first = upload(client, headers=RESEARCHER)
    second = upload(client, headers=OTHER_RESEARCHER)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.headers["idempotency-replayed"] == "false"
    assert second.headers["idempotency-replayed"] == "false"

    with SessionLocal() as db:
        records = list(
            db.scalars(select(IdempotencyRecord).order_by(IdempotencyRecord.submitted_by))
        )
        submissions = list(db.scalars(select(Submission)))
        assert len(records) == 2
        assert len({record.scope_key for record in records}) == 2
        assert all(submission.idempotency_key is None for submission in submissions)
        assert {record.submitted_by for record in records} == {
            "other-researcher",
            "xiaomei-researcher",
        }


def test_scope_digest_is_actor_bound_without_storing_raw_key() -> None:
    first = idempotency_scope_key("xiaomei-researcher", KEY)
    repeated = idempotency_scope_key("xiaomei-researcher", KEY)
    other_actor = idempotency_scope_key("other-researcher", KEY)

    assert first == repeated
    assert first != other_actor
    assert len(first) == 64
    assert KEY not in first


@pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Concurrent first-request race contract requires PostgreSQL transaction semantics.",
)
def test_concurrent_first_requests_collapse_to_one_submission(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    barrier = Barrier(2)
    original_check = submission_routes.checker.check

    def synchronised_check(context):  # type: ignore[no-untyped-def]
        barrier.wait(timeout=10)
        return original_check(context)

    monkeypatch.setattr(submission_routes.checker, "check", synchronised_check)
    before = set(settings.quarantine_dir.iterdir())

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(upload, client) for _ in range(2)]
        responses = [future.result(timeout=20) for future in futures]

    assert [response.status_code for response in responses] == [201, 201]
    submission_ids = {response.json()["id"] for response in responses}
    assert len(submission_ids) == 1
    assert sorted(response.headers["idempotency-replayed"] for response in responses) == [
        "false",
        "true",
    ]

    with SessionLocal() as db:
        submissions = list(db.scalars(select(Submission)))
        records = list(db.scalars(select(IdempotencyRecord)))
        assert len(submissions) == 1
        assert len(records) == 1
        assert records[0].submission_id == submissions[0].id
        assert [event.event_type for event in submissions[0].audit_events] == [
            "SUBMITTED",
            "QUARANTINED",
            "SCAN_STARTED",
            "AUTOMATED_CHECK_COMPLETED",
        ]

    created_files = set(settings.quarantine_dir.iterdir()) - before
    assert len(created_files) == 1
