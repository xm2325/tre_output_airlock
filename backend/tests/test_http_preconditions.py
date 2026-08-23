from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.api.review_routes as review_routes
from app.core.config import settings
from app.core.http_preconditions import submission_etag
from app.db import SessionLocal
from app.models import Submission
from app.services.review_decision import compare_and_swap_review_decision

REVIEWER = {"X-Demo-User": "xiaomei-reviewer", "X-Demo-Role": "reviewer"}


def upload_review_item(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/submissions",
        headers=REVIEWER,
        files={"file": ("small.csv", b"group,count\nA,2\nB,20\n", "text/csv")},
        data={
            "project_code": "HTTP-PRECONDITION-CI",
            "output_type": "TABLE",
            "output_description": "Synthetic small-cell output for HTTP precondition tests.",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "AWAITING_REVIEW"
    return payload


def claim(client: TestClient, submission_id: str):
    return client.post(f"/api/v1/submissions/{submission_id}/claim", headers=REVIEWER)


def review_payload(expected_version: int | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision": "ALLOW",
        "rationale": "The disclosure concern was resolved in the synthetic review evidence.",
    }
    if expected_version is not None:
        payload["expected_version"] = expected_version
    return payload


def test_detail_and_review_responses_publish_current_etag(client: TestClient) -> None:
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])

    detail = client.get(f"/api/v1/submissions/{submission_id}", headers=REVIEWER)
    assert detail.status_code == 200
    expected_initial = submission_etag(submission_id, int(detail.json()["row_version"]))
    assert detail.headers["etag"] == expected_initial

    claimed = claim(client, submission_id)
    assert claimed.status_code == 200
    claimed_version = int(claimed.json()["row_version"])
    claimed_etag = submission_etag(submission_id, claimed_version)
    assert claimed.headers["etag"] == claimed_etag
    assert claimed_etag != expected_initial

    reviewed = client.post(
        f"/api/v1/submissions/{submission_id}/review",
        headers={**REVIEWER, "If-Match": claimed_etag},
        json=review_payload(),
    )
    assert reviewed.status_code == 200
    final_version = int(reviewed.json()["row_version"])
    assert reviewed.headers["etag"] == submission_etag(submission_id, final_version)
    assert final_version == claimed_version + 1


def test_stale_if_match_returns_412(client: TestClient) -> None:
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])
    stale_etag = submission_etag(submission_id, int(submitted["row_version"]))
    assert claim(client, submission_id).status_code == 200

    response = client.post(
        f"/api/v1/submissions/{submission_id}/review",
        headers={**REVIEWER, "If-Match": stale_etag},
        json=review_payload(),
    )
    assert response.status_code == 412
    assert "precondition failed" in response.json()["detail"].lower()


def test_review_requires_http_or_legacy_precondition(client: TestClient) -> None:
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])
    assert claim(client, submission_id).status_code == 200

    response = client.post(
        f"/api/v1/submissions/{submission_id}/review",
        headers=REVIEWER,
        json=review_payload(),
    )
    assert response.status_code == 428
    assert "if-match" in response.json()["detail"].lower()


def test_if_match_and_body_version_must_agree(client: TestClient) -> None:
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])
    claimed = claim(client, submission_id)
    assert claimed.status_code == 200
    current_version = int(claimed.json()["row_version"])

    response = client.post(
        f"/api/v1/submissions/{submission_id}/review",
        headers={**REVIEWER, "If-Match": claimed.headers["etag"]},
        json=review_payload(current_version - 1),
    )
    assert response.status_code == 400
    assert "different submission versions" in response.json()["detail"].lower()


@pytest.mark.parametrize("if_match", ["*", 'W/"airlock-submission:weak:v1"'])
def test_review_rejects_weak_or_wildcard_if_match(
    client: TestClient,
    if_match: str,
) -> None:
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])
    assert claim(client, submission_id).status_code == 200

    response = client.post(
        f"/api/v1/submissions/{submission_id}/review",
        headers={**REVIEWER, "If-Match": if_match},
        json=review_payload(),
    )
    assert response.status_code == 400


def test_review_decision_service_is_compare_and_swap(client: TestClient) -> None:
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])
    claimed = claim(client, submission_id)
    assert claimed.status_code == 200
    expected_version = int(claimed.json()["row_version"])
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.review_claim_ttl_minutes)

    with SessionLocal() as db:
        first = compare_and_swap_review_decision(
            db,
            submission_id=submission_id,
            expected_version=expected_version,
            reviewer="xiaomei-reviewer",
            decision="ALLOW",
            rationale="First atomic compare-and-swap decision wins the synthetic race.",
            require_claim=True,
            claim_cutoff=cutoff,
        )
        second = compare_and_swap_review_decision(
            db,
            submission_id=submission_id,
            expected_version=expected_version,
            reviewer="xiaomei-reviewer",
            decision="BLOCK",
            rationale="A stale second compare-and-swap must not overwrite the first result.",
            require_claim=True,
            claim_cutoff=cutoff,
        )
        assert first is True
        assert second is False
        db.rollback()


def test_review_audit_failure_rolls_back_atomic_decision(
    client: TestClient,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    submitted = upload_review_item(client)
    submission_id = str(submitted["id"])
    claimed = claim(client, submission_id)
    assert claimed.status_code == 200
    claimed_payload = claimed.json()
    expected_version = int(claimed_payload["row_version"])

    def fail_audit(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated manual-review audit failure")

    monkeypatch.setattr(review_routes, "append_audit_event", fail_audit)
    response = client.post(
        f"/api/v1/submissions/{submission_id}/review",
        headers={**REVIEWER, "If-Match": claimed.headers["etag"]},
        json=review_payload(),
    )
    assert response.status_code == 500

    with SessionLocal() as db:
        persisted = db.scalar(select(Submission).where(Submission.id == submission_id))
        assert persisted is not None
        assert persisted.status == "AWAITING_REVIEW"
        assert persisted.final_decision is None
        assert persisted.reviewer is None
        assert persisted.review_rationale is None
        assert persisted.claimed_by == "xiaomei-reviewer"
        assert persisted.row_version == expected_version
        assert all(event.event_type != "MANUAL_REVIEW_COMPLETED" for event in persisted.audit_events)
