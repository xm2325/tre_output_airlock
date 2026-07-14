from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent

REVIEWER = {"X-Demo-User": "xiaomei-reviewer", "X-Demo-Role": "reviewer"}
ADMIN = {"X-Demo-User": "xiaomei-admin", "X-Demo-Role": "admin"}
RESEARCHER = {"X-Demo-User": "xiaomei-researcher", "X-Demo-Role": "researcher"}
OTHER_RESEARCHER = {"X-Demo-User": "other-researcher", "X-Demo-Role": "researcher"}


def upload_file(
    client: TestClient,
    name: str,
    content: bytes,
    content_type: str = "text/csv",
    headers: dict[str, str] | None = None,
    idempotency_key: str | None = None,
):
    request_headers = dict(headers or REVIEWER)
    if idempotency_key:
        request_headers["Idempotency-Key"] = idempotency_key
    return client.post(
        "/api/v1/submissions",
        headers=request_headers,
        files={"file": (name, content, content_type)},
        data={
            "project_code": "UKB-DEMO-42",
            "output_type": "TABLE",
            "output_description": (
                "Synthetic aggregate output created for automated airlock testing."
            ),
        },
    )


def upload_csv(
    client: TestClient,
    name: str,
    content: str,
    headers: dict[str, str] | None = None,
    idempotency_key: str | None = None,
):
    return upload_file(
        client,
        name,
        content.encode("utf-8"),
        headers=headers,
        idempotency_key=idempotency_key,
    )


def claim(client: TestClient, submission_id: str, headers: dict[str, str] | None = None):
    return client.post(
        f"/api/v1/submissions/{submission_id}/claim",
        headers=headers or REVIEWER,
    )


def test_health_readiness_identity_and_security_headers(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["version"] == "0.3.1"
    assert response.json()["policy_version"] == "demo-policy-2026.2"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "geolocation=()" in response.headers["permissions-policy"]

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    actor = client.get("/api/v1/me", headers=RESEARCHER).json()
    assert actor == {"name": "xiaomei-researcher", "role": "researcher"}


def test_invalid_demo_role_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/me",
        headers={"X-Demo-User": "test-user", "X-Demo-Role": "superuser"},
    )
    assert response.status_code == 400


def test_policy_catalogue_includes_retention_and_new_rules(client: TestClient) -> None:
    response = client.get("/api/v1/policy")
    assert response.status_code == 200
    payload = response.json()
    assert payload["policy_version"] == "demo-policy-2026.2"
    assert payload["small_cell_threshold"] == 5
    assert payload["retention_days"] == 30
    codes = {rule["code"] for rule in payload["rules"]}
    assert {"FREE_TEXT_COLUMN", "UK_POSTCODE_LIKE", "DATE_OF_BIRTH_LIKE"} <= codes


def test_upload_safe_submission_and_paginated_list(client: TestClient) -> None:
    response = upload_csv(client, "safe.csv", "group,mean\nA,1.2\nB,1.5\n")
    assert response.status_code == 201
    payload = response.json()
    assert payload["project_code"] == "UKB-DEMO-42"
    assert payload["automated_decision"] == "ALLOW"
    assert payload["final_decision"] == "ALLOW"
    assert payload["status"] == "COMPLETED"
    assert payload["row_version"] == 2
    assert payload["file_available"] is True
    assert [event["event_type"] for event in payload["audit_events"]] == [
        "SUBMITTED",
        "QUARANTINED",
        "SCAN_STARTED",
        "AUTOMATED_CHECK_COMPLETED",
    ]

    listed = client.get("/api/v1/submissions?page=1&page_size=10", headers=REVIEWER)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["filename"] == "safe.csv"


def test_researcher_only_sees_own_submissions(client: TestClient) -> None:
    own = upload_csv(
        client,
        "own.csv",
        "group,mean\nA,1.2\n",
        headers=RESEARCHER,
    ).json()
    upload_csv(
        client,
        "other.csv",
        "group,mean\nA,1.3\n",
        headers=OTHER_RESEARCHER,
    )

    own_list = client.get("/api/v1/submissions", headers=RESEARCHER).json()
    assert [item["filename"] for item in own_list["items"]] == ["own.csv"]
    hidden = client.get(f"/api/v1/submissions/{own['id']}", headers=OTHER_RESEARCHER)
    assert hidden.status_code == 404


def test_idempotency_key_returns_same_submission(client: TestClient) -> None:
    first = upload_csv(
        client,
        "safe.csv",
        "group,mean\nA,1.2\n",
        idempotency_key="request-00000001",
    )
    second = upload_csv(
        client,
        "safe.csv",
        "group,mean\nA,1.2\n",
        idempotency_key="request-00000001",
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert client.get("/api/v1/submissions", headers=REVIEWER).json()["total"] == 1


def test_list_filters_search_and_risk_sort(client: TestClient) -> None:
    upload_csv(client, "alpha-safe.csv", "group,mean\nA,1.2\n")
    upload_csv(client, "beta-review.csv", "group,count\nA,2\n")
    upload_csv(client, "gamma-block.csv", "participant_id,value\nP1,1\n")

    review = client.get("/api/v1/submissions?decision=REVIEW", headers=REVIEWER).json()
    assert [item["filename"] for item in review["items"]] == ["beta-review.csv"]

    searched = client.get("/api/v1/submissions?search=gamma", headers=REVIEWER).json()
    assert [item["filename"] for item in searched["items"]] == ["gamma-block.csv"]

    sorted_rows = client.get("/api/v1/submissions?sort=risk_desc", headers=REVIEWER).json()["items"]
    assert sorted_rows[0]["automated_decision"] == "BLOCK"


def test_reviewer_role_is_required_for_queue(client: TestClient) -> None:
    response = client.get("/api/v1/review-queue", headers=RESEARCHER)
    assert response.status_code == 403


def test_claim_review_and_optimistic_version_flow(client: TestClient) -> None:
    submission = upload_csv(client, "small.csv", "group,count\nA,2\nB,20\n").json()
    assert submission["status"] == "AWAITING_REVIEW"

    claimed = claim(client, submission["id"])
    assert claimed.status_code == 200
    claimed_payload = claimed.json()
    assert claimed_payload["claimed_by"] == "xiaomei-reviewer"
    assert claimed_payload["row_version"] == submission["row_version"] + 1

    stale = client.post(
        f"/api/v1/submissions/{submission['id']}/review",
        headers=REVIEWER,
        json={
            "decision": "ALLOW",
            "rationale": "The small count was suppressed in the revised synthetic output.",
            "expected_version": submission["row_version"],
        },
    )
    assert stale.status_code == 409

    reviewed = client.post(
        f"/api/v1/submissions/{submission['id']}/review",
        headers=REVIEWER,
        json={
            "decision": "ALLOW",
            "rationale": "The small count was suppressed in the revised synthetic output.",
            "expected_version": claimed_payload["row_version"],
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["final_decision"] == "ALLOW"
    assert reviewed.json()["status"] == "COMPLETED"
    assert reviewed.json()["claimed_by"] is None


def test_review_requires_claim_for_non_admin(client: TestClient) -> None:
    submission = upload_csv(client, "small.csv", "group,count\nA,2\nB,20\n").json()
    response = client.post(
        f"/api/v1/submissions/{submission['id']}/review",
        headers=REVIEWER,
        json={
            "decision": "BLOCK",
            "rationale": "The disclosure concern remains unresolved in the submitted file.",
            "expected_version": submission["row_version"],
        },
    )
    assert response.status_code == 409


def test_claim_conflict_and_admin_release(client: TestClient) -> None:
    submission = upload_csv(client, "small.csv", "group,count\nA,2\nB,20\n").json()
    assert claim(client, submission["id"]).status_code == 200
    conflict = claim(
        client,
        submission["id"],
        {"X-Demo-User": "second-reviewer", "X-Demo-Role": "reviewer"},
    )
    assert conflict.status_code == 409

    released = client.post(
        f"/api/v1/submissions/{submission['id']}/release-claim",
        headers=ADMIN,
    )
    assert released.status_code == 200
    assert released.json()["claimed_by"] is None


def test_recheck_resets_manual_review_state(client: TestClient) -> None:
    submission = upload_csv(client, "small.csv", "group,count\nA,2\nB,20\n").json()
    claimed = claim(client, submission["id"]).json()
    reviewed = client.post(
        f"/api/v1/submissions/{submission['id']}/review",
        headers=REVIEWER,
        json={
            "decision": "ALLOW",
            "rationale": "The small count was suppressed in the revised synthetic output.",
            "expected_version": claimed["row_version"],
        },
    )
    assert reviewed.json()["status"] == "COMPLETED"

    rechecked = client.post(f"/api/v1/submissions/{submission['id']}/recheck", headers=REVIEWER)
    assert rechecked.status_code == 200
    payload = rechecked.json()
    assert payload["status"] == "AWAITING_REVIEW"
    assert payload["final_decision"] is None
    assert payload["reviewer"] is None
    assert any(
        event["event_type"] == "AUTOMATED_RECHECK_COMPLETED" for event in payload["audit_events"]
    )


def test_signed_report_and_audit_verification(client: TestClient) -> None:
    submission = upload_csv(client, "safe.csv", "group,mean\nA,1.2\n").json()
    report = client.get(f"/api/v1/submissions/{submission['id']}/report", headers=REVIEWER)
    assert report.status_code == 200
    payload = report.json()
    assert payload["report_version"] == "2.0"
    assert payload["signature_algorithm"] == "HMAC-SHA256"
    assert len(payload["signature"]) == 64
    assert payload["audit_chain_valid"] is True

    verified = client.get(
        f"/api/v1/submissions/{submission['id']}/report/verify", headers=REVIEWER
    ).json()
    assert verified["signature_valid"] is True
    assert verified["audit_chain_valid"] is True

    audit = client.get(
        f"/api/v1/submissions/{submission['id']}/audit/verify", headers=REVIEWER
    ).json()
    assert audit["valid"] is True
    assert audit["checked_events"] == 4


def test_audit_tampering_is_detected(client: TestClient) -> None:
    submission = upload_csv(client, "safe.csv", "group,mean\nA,1.2\n").json()
    with SessionLocal() as db:
        event = db.scalar(
            select(AuditEvent)
            .where(AuditEvent.submission_id == submission["id"])
            .order_by(AuditEvent.id)
        )
        assert event is not None
        event.detail = "tampered detail"
        db.commit()

    audit = client.get(f"/api/v1/submissions/{submission['id']}/audit/verify", headers=ADMIN).json()
    assert audit["valid"] is False
    assert audit["first_invalid_event_id"] is not None


def test_admin_can_delete_file_but_metadata_is_retained(client: TestClient) -> None:
    submission = upload_csv(client, "safe.csv", "group,mean\nA,1.2\n").json()
    forbidden = client.delete(f"/api/v1/submissions/{submission['id']}/file", headers=REVIEWER)
    assert forbidden.status_code == 403

    deleted = client.delete(f"/api/v1/submissions/{submission['id']}/file", headers=ADMIN)
    assert deleted.status_code == 200
    assert deleted.json()["file_available"] is False
    assert any(
        item["event_type"] == "QUARANTINED_FILE_DELETED" for item in deleted.json()["audit_events"]
    )

    recheck = client.post(f"/api/v1/submissions/{submission['id']}/recheck", headers=ADMIN)
    assert recheck.status_code == 409


def test_policy_simulation(client: TestClient) -> None:
    upload_csv(client, "safe.csv", "group,mean\nA,1.2\n")
    upload_csv(client, "review.csv", "group,count\nA,2\n")
    upload_csv(client, "block.csv", "participant_id,value\nP1,1\n")

    simulated = client.post(
        "/api/v1/policy/simulate",
        headers=REVIEWER,
        json={
            "critical_action": "BLOCK",
            "high_action": "BLOCK",
            "medium_action": "REVIEW",
            "low_action": "ALLOW",
        },
    )
    assert simulated.status_code == 200
    payload = simulated.json()
    assert payload["total"] == 3
    assert payload["allow"] == 1
    assert payload["block"] == 2
    assert payload["changed_decisions"] == 1
    assert payload["automation_rate"] == 1.0


def test_metrics_include_queue_claim_and_retention_fields(client: TestClient) -> None:
    upload_csv(client, "safe.csv", "group,mean\nA,1.2\n")
    upload_csv(client, "blocked.csv", "participant_id,value\nP1,1\n")
    review = upload_csv(client, "review.csv", "group,count\nA,2\n").json()
    claim(client, review["id"])

    payload = client.get("/api/v1/metrics").json()
    assert payload["total"] == 3
    assert payload["allow"] == 1
    assert payload["review"] == 1
    assert payload["block"] == 1
    assert payload["awaiting_review"] == 1
    assert payload["claimed_reviews"] == 1
    assert payload["automation_rate"] == 0.667
    assert payload["deleted_files"] == 0
    assert payload["policy_version"] == "demo-policy-2026.2"


def test_prometheus_endpoint_records_requests(client: TestClient) -> None:
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "airlock_http_requests_total" in response.text
    assert 'path="/health"' in response.text
