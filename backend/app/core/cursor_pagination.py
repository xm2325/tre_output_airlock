from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.core.config import settings

CursorSort = Literal["newest", "oldest", "risk_desc"]


@dataclass(frozen=True)
class SubmissionCursor:
    sort: CursorSort
    contract: str
    created_at: datetime
    submission_id: str
    risk_score: float | None = None


def cursor_contract(
    *,
    actor_role: str,
    actor_name: str,
    decision: str | None,
    workflow_status: str | None,
    project_code: str | None,
    search: str | None,
    sort: CursorSort,
) -> str:
    canonical = json.dumps(
        {
            "actor_name": actor_name,
            "actor_role": actor_role,
            "decision": decision,
            "project_code": project_code.strip() if project_code else None,
            "search": search.strip() if search else None,
            "sort": sort,
            "workflow_status": workflow_status,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _signing_key() -> bytes:
    return hmac.new(
        settings.report_signing_secret.encode(),
        b"tre-output-airlock:submission-cursor:v1",
        hashlib.sha256,
    ).digest()


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _b64decode(payload: str) -> bytes:
    return base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))


def encode_submission_cursor(cursor: SubmissionCursor) -> str:
    payload = json.dumps(
        {
            "v": 1,
            "sort": cursor.sort,
            "contract": cursor.contract,
            "created_at": cursor.created_at.isoformat(),
            "submission_id": cursor.submission_id,
            "risk_score": cursor.risk_score,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    encoded = _b64encode(payload)
    signature = hmac.new(_signing_key(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def decode_submission_cursor(
    token: str,
    *,
    expected_contract: str,
    expected_sort: CursorSort,
) -> SubmissionCursor:
    try:
        encoded, signature = token.split(".", maxsplit=1)
        expected_signature = hmac.new(
            _signing_key(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("cursor signature mismatch")
        payload = json.loads(_b64decode(encoded))
        if payload.get("v") != 1:
            raise ValueError("unsupported cursor version")
        if payload.get("contract") != expected_contract or payload.get("sort") != expected_sort:
            raise ValueError("cursor query contract mismatch")
        created_at = datetime.fromisoformat(payload["created_at"])
        submission_id = str(payload["submission_id"])
        if not submission_id:
            raise ValueError("empty cursor submission id")
        risk_score_raw = payload.get("risk_score")
        risk_score = None if risk_score_raw is None else float(risk_score_raw)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or incompatible submission cursor.") from exc

    if expected_sort == "risk_desc" and risk_score is None:
        raise ValueError("Invalid or incompatible submission cursor.")

    return SubmissionCursor(
        sort=expected_sort,
        contract=expected_contract,
        created_at=created_at,
        submission_id=submission_id,
        risk_score=risk_score,
    )
