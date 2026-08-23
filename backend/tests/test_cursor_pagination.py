from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Submission

ADMIN_HEADERS = {"X-Demo-User": "pagination-admin", "X-Demo-Role": "admin"}


def _submission(
    submission_id: str,
    *,
    created_at: datetime,
    risk_score: float,
    submitted_by: str,
    project_code: str,
    decision: str = "ALLOW",
) -> Submission:
    return Submission(
        id=submission_id,
        project_code=project_code,
        output_type="TABLE",
        output_description="Synthetic pagination contract fixture.",
        filename=f"{submission_id}.csv",
        content_type="text/csv",
        size_bytes=100,
        sha256=submission_id.replace("-", "").ljust(64, "0")[:64],
        status="COMPLETED",
        automated_decision=decision,
        final_decision=None,
        risk_score=risk_score,
        policy_version="pagination-test",
        submitted_by=submitted_by,
        row_version=1,
        created_at=created_at,
        updated_at=created_at,
    )


def _seed_submissions() -> list[str]:
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    rows = [
        _submission(
            "00000000-0000-0000-0000-000000000001",
            created_at=base,
            risk_score=0.8,
            submitted_by="alice",
            project_code="ALPHA",
        ),
        _submission(
            "00000000-0000-0000-0000-000000000002",
            created_at=base,
            risk_score=0.8,
            submitted_by="alice",
            project_code="ALPHA",
        ),
        _submission(
            "00000000-0000-0000-0000-000000000003",
            created_at=base + timedelta(minutes=1),
            risk_score=0.9,
            submitted_by="alice",
            project_code="ALPHA",
        ),
        _submission(
            "00000000-0000-0000-0000-000000000004",
            created_at=base + timedelta(minutes=1),
            risk_score=0.9,
            submitted_by="bob",
            project_code="BETA",
        ),
        _submission(
            "00000000-0000-0000-0000-000000000005",
            created_at=base + timedelta(minutes=2),
            risk_score=0.5,
            submitted_by="alice",
            project_code="ALPHA",
            decision="BLOCK",
        ),
        _submission(
            "00000000-0000-0000-0000-000000000006",
            created_at=base + timedelta(minutes=2),
            risk_score=0.8,
            submitted_by="bob",
            project_code="BETA",
        ),
    ]
    with SessionLocal() as db:
        db.add_all(rows)
        db.commit()
    return [row.id for row in rows]


def _walk_cursor(client: TestClient, sort: str, limit: int = 2) -> list[str]:
    cursor = None
    ids: list[str] = []
    while True:
        params: dict[str, str | int] = {"sort": sort, "limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get(
            "/api/v1/submissions/cursor",
            params=params,
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["limit"] == limit
        assert "total" not in payload
        ids.extend(item["id"] for item in payload["items"])
        if not payload["has_more"]:
            assert payload["next_cursor"] is None
            return ids
        cursor = payload["next_cursor"]
        assert isinstance(cursor, str) and len(cursor) >= 16


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        (
            "newest",
            [
                "00000000-0000-0000-0000-000000000006",
                "00000000-0000-0000-0000-000000000005",
                "00000000-0000-0000-0000-000000000004",
                "00000000-0000-0000-0000-000000000003",
                "00000000-0000-0000-0000-000000000002",
                "00000000-0000-0000-0000-000000000001",
            ],
        ),
        (
            "oldest",
            [
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "00000000-0000-0000-0000-000000000003",
                "00000000-0000-0000-0000-000000000004",
                "00000000-0000-0000-0000-000000000005",
                "00000000-0000-0000-0000-000000000006",
            ],
        ),
        (
            "risk_desc",
            [
                "00000000-0000-0000-0000-000000000003",
                "00000000-0000-0000-0000-000000000004",
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
                "00000000-0000-0000-0000-000000000006",
                "00000000-0000-0000-0000-000000000005",
            ],
        ),
    ],
)
def test_cursor_walk_is_stable_without_duplicates_or_gaps(
    client: TestClient, sort: str, expected: list[str]
) -> None:
    _seed_submissions()
    ids = _walk_cursor(client, sort)
    assert ids == expected
    assert len(ids) == len(set(ids))


def test_cursor_is_bound_to_filter_contract(client: TestClient) -> None:
    _seed_submissions()
    first = client.get(
        "/api/v1/submissions/cursor",
        params={"limit": 1, "project_code": "ALPHA"},
        headers=ADMIN_HEADERS,
    )
    assert first.status_code == 200
    cursor = first.json()["next_cursor"]
    assert cursor

    incompatible = client.get(
        "/api/v1/submissions/cursor",
        params={"limit": 1, "project_code": "BETA", "cursor": cursor},
        headers=ADMIN_HEADERS,
    )
    assert incompatible.status_code == 400
    assert incompatible.json()["detail"] == "Invalid or incompatible submission cursor."


def test_cursor_is_bound_to_actor_and_researcher_visibility(client: TestClient) -> None:
    _seed_submissions()
    alice_headers = {"X-Demo-User": "alice", "X-Demo-Role": "researcher"}
    first = client.get(
        "/api/v1/submissions/cursor",
        params={"limit": 1},
        headers=alice_headers,
    )
    assert first.status_code == 200
    assert first.json()["items"][0]["submitted_by"] == "alice"
    cursor = first.json()["next_cursor"]
    assert cursor

    bob_headers = {"X-Demo-User": "bob", "X-Demo-Role": "researcher"}
    reused = client.get(
        "/api/v1/submissions/cursor",
        params={"limit": 1, "cursor": cursor},
        headers=bob_headers,
    )
    assert reused.status_code == 400


def test_tampered_cursor_is_rejected(client: TestClient) -> None:
    _seed_submissions()
    first = client.get(
        "/api/v1/submissions/cursor",
        params={"limit": 1},
        headers=ADMIN_HEADERS,
    )
    cursor = first.json()["next_cursor"]
    assert cursor
    replacement = "0" if cursor[-1] != "0" else "1"
    tampered = cursor[:-1] + replacement

    response = client.get(
        "/api/v1/submissions/cursor",
        params={"limit": 1, "cursor": tampered},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or incompatible submission cursor."


def test_cursor_limit_is_bounded(client: TestClient) -> None:
    response = client.get(
        "/api/v1/submissions/cursor",
        params={"limit": 101},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 422
