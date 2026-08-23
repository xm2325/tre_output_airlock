from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import Actor
from app.models import Submission
from app.rules.base import FindingResult
from app.services.scanning import apply_automated_result, duplicate_finding, store_findings


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _get_submission(
    db: Session,
    submission_id: str,
    actor: Actor | None = None,
) -> Submission:
    statement = (
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.findings), selectinload(Submission.audit_events))
    )
    submission = db.scalar(statement)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    if actor is not None and actor.role == "researcher" and submission.submitted_by != actor.name:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return submission


def _store_findings(submission: Submission, findings: list[FindingResult]) -> None:
    store_findings(submission, findings)


def _apply_automated_result(
    submission: Submission,
    findings: list[FindingResult],
    policy_version: str,
) -> None:
    apply_automated_result(submission, findings, policy_version)


def _duplicate_finding(db: Session, submission_id: str, sha256: str) -> FindingResult | None:
    return duplicate_finding(db, submission_id, sha256)
