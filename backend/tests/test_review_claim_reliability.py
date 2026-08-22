from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.api.review_routes as review_routes
from app.core.config import settings
from app.db import SessionLocal
from app.models import Submission

REVIEWER = {"X-Demo-User": "xiaomei-reviewer", "X-Demo-Role": "reviewer"}
SECOND_REVIEWER = {"X-Demo-User": "second-reviewer", "X-Demo-Role": "reviewer"}


def upload_review_item(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/submissions",
        headers=REVIEWER,
        files={"file": ("small.csv", b"group,count\nA,2\nB,20\n", "text/csv")},
        data={
            "project_code": "UKB-DEMO-42",
            "output_type": "TABLE",
            "output_description": "Synthetic small-cell table for review-claim reliability tests.",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "AWAITING_REVIEW"
    return payload


def claim(client: TestClient, submission_id: str, headers: dict[str, str]):
    return client.post(f"/api/v1/submissions/{submission_id}/claim", headers=headers)


def expire_claim(submission_id: str) -> int:
    with SessionLocal() as db:
        submission = db.scalar(select(Submission).where(Submission.id == submission_id))
        assert submission is not None
        submission.claimed_at = datetime.now(UTC) - timedelta(
            minutes=settings.review_claim_ttl_minutes + 1
        )
        version = submission.row_version
        db.commit()
        return version


def test_claim_and_audit_event_commit_atomically(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])
    initial_version = int(submitted["row_version"])

    def fail_audit(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated audit persistence failure")

    monkeypatch.setattr(review_routes, "append_audit_event", fail_audit)
    response = claim(client, submission_id, REVIEWER)
    assert response.status_code == 500

    with SessionLocal() as db:
        persisted = db.scalar(select(Submission).where(Submission.id == submission_id))
        assert persisted is not None
        assert persisted.claimed_by is None
        assert persisted.claimed_at is None
        assert persisted.row_version == initial_version
        assert all(event.event_type != "REVIEW_CLAIMED" for event in persisted.audit_events)


def test_expired_claim_is_visible_as_claimable_and_can_be_reassigned(
    client: TestClient,
) -> None:
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])

    first = claim(client, submission_id, REVIEWER)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["claimed_by"] == "xiaomei-reviewer"

    expired_version = expire_claim(submission_id)

    queue = client.get("/api/v1/review-queue?unclaimed_only=true", headers=SECOND_REVIEWER)
    assert queue.status_code == 200
    assert submission_id in {item["id"] for item in queue.json()}

    reassigned = claim(client, submission_id, SECOND_REVIEWER)
    assert reassigned.status_code == 200
    payload = reassigned.json()
    assert payload["claimed_by"] == "second-reviewer"
    assert payload["row_version"] == expired_version + 1
    assert payload["audit_events"][-1]["event_type"] == "REVIEW_CLAIM_REASSIGNED"
    assert "xiaomei-reviewer" in payload["audit_events"][-1]["detail"]


def test_expired_claim_cannot_be_used_to_record_decision(client: TestClient) -> None:
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])

    claimed = claim(client, submission_id, REVIEWER)
    assert claimed.status_code == 200
    current_version = expire_claim(submission_id)

    response = client.post(
        f"/api/v1/submissions/{submission_id}/review",
        headers=REVIEWER,
        json={
            "decision": "ALLOW",
            "rationale": "This decision must not be accepted after the claim lease expires.",
            "expected_version": current_version,
        },
    )
    assert response.status_code == 409
    assert "claim has expired" in response.json()["detail"].lower()


def test_active_claim_still_conflicts_for_second_reviewer(client: TestClient) -> None:
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])

    assert claim(client, submission_id, REVIEWER).status_code == 200
    conflict = claim(client, submission_id, SECOND_REVIEWER)
    assert conflict.status_code == 409
    assert "already claimed" in conflict.json()["detail"].lower()
