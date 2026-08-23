# ruff: noqa: F401
from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import PlainTextResponse
from sqlalchemy import and_, asc, desc, func, or_, select, text, update
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.api.common import _get_submission, _request_id
from app.core.auth import Actor, get_actor, require_roles
from app.core.config import settings
from app.core.http_preconditions import (
    resolve_review_precondition,
    stale_write_error,
    submission_etag,
)
from app.core.policy import API_VERSION, POLICY_VERSION, RULE_CATALOG
from app.core.telemetry import telemetry
from app.db import get_db
from app.models import Finding, Submission
from app.rules.base import FileContext, FindingResult
from app.rules.csv_rules import MAX_ROWS_TO_SCAN, SMALL_CELL_THRESHOLD
from app.schemas import (
    AuditVerificationOut,
    CurrentActorOut,
    DecisionReportOut,
    HealthOut,
    MetricsOut,
    PolicyOut,
    PolicySimulationOut,
    PolicySimulationRequest,
    ReadinessOut,
    ReportVerificationOut,
    ReviewRequest,
    RuleDefinitionOut,
    SubmissionDetail,
    SubmissionPage,
    SubmissionSummary,
    TopFindingOut,
)
from app.services.audit import append_audit_event, verify_audit_chain
from app.services.checker import ACTION_PRIORITY, OutputChecker, decision_from_findings
from app.services.reports import build_report, verify_report
from app.services.review_decision import compare_and_swap_review_decision
from app.services.storage import FileTooLargeError, quarantined_path, store_quarantined_file

logger = logging.getLogger(__name__)
router = APIRouter()


def _claim_cutoff(now: datetime | None = None) -> datetime:
    ttl_minutes = settings.review_claim_ttl_minutes
    if ttl_minutes <= 0:
        raise RuntimeError("AIRLOCK_REVIEW_CLAIM_TTL_MINUTES must be greater than zero.")
    reference = now or datetime.now(UTC)
    return reference - timedelta(minutes=ttl_minutes)


def _normalise_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _claim_is_expired(submission: Submission, now: datetime | None = None) -> bool:
    if submission.claimed_by is None:
        return False
    if submission.claimed_at is None:
        return True
    reference = now or datetime.now(UTC)
    return _normalise_utc(submission.claimed_at) <= _claim_cutoff(reference)


def _set_etag(response: Response, submission: Submission) -> None:
    response.headers["ETag"] = submission_etag(submission.id, submission.row_version)


@router.get(
    "/api/v1/review-queue",
    response_model=list[SubmissionSummary],
    tags=["review"],
)
def review_queue(
    unclaimed_only: bool = Query(default=False),
    _: Actor = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> list[Submission]:
    statement = select(Submission).where(Submission.status == "AWAITING_REVIEW")
    if unclaimed_only:
        cutoff = _claim_cutoff()
        statement = statement.where(
            or_(
                Submission.claimed_by.is_(None),
                Submission.claimed_at.is_(None),
                Submission.claimed_at <= cutoff,
            )
        )
    statement = statement.order_by(desc(Submission.risk_score), asc(Submission.created_at))
    return list(db.scalars(statement))


@router.post(
    "/api/v1/submissions/{submission_id}/claim",
    response_model=SubmissionDetail,
    tags=["review"],
)
def claim_submission(
    request: Request,
    response: Response,
    submission_id: str,
    actor: Actor = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> Submission:
    current = _get_submission(db, submission_id, actor)
    if current.status != "AWAITING_REVIEW":
        raise HTTPException(status_code=409, detail="Submission is not awaiting review.")

    now = datetime.now(UTC)
    expired = _claim_is_expired(current, now)
    previous_claimant = current.claimed_by
    if current.claimed_by == actor.name and not expired:
        _set_etag(response, current)
        return current
    if current.claimed_by is not None and not expired:
        raise HTTPException(
            status_code=409, detail=f"Submission is already claimed by {current.claimed_by}."
        )

    cutoff = _claim_cutoff(now)
    claim_update = (
        update(Submission)
        .where(
            Submission.id == submission_id,
            Submission.status == "AWAITING_REVIEW",
            Submission.row_version == current.row_version,
            or_(
                Submission.claimed_by.is_(None),
                Submission.claimed_at.is_(None),
                Submission.claimed_at <= cutoff,
            ),
        )
        .values(
            claimed_by=actor.name,
            claimed_at=now,
            row_version=current.row_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    result = db.execute(claim_update)
    if getattr(result, "rowcount", 0) != 1:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="The review item changed. Refresh and try again."
        )

    db.flush()
    db.refresh(current)
    if expired and previous_claimant is not None:
        event_type = "REVIEW_CLAIM_REASSIGNED"
        detail = (
            f"Expired claim held by {previous_claimant} was reassigned to {actor.name} "
            f"at row_version={current.row_version}."
        )
    else:
        event_type = "REVIEW_CLAIMED"
        detail = f"Reviewer claimed item at row_version={current.row_version}."
    append_audit_event(
        current,
        event_type,
        actor.name,
        detail,
        _request_id(request),
    )
    db.commit()
    latest = _get_submission(db, submission_id, actor)
    _set_etag(response, latest)
    return latest


@router.post(
    "/api/v1/submissions/{submission_id}/release-claim",
    response_model=SubmissionDetail,
    tags=["review"],
)
def release_claim(
    request: Request,
    response: Response,
    submission_id: str,
    actor: Actor = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> Submission:
    submission = _get_submission(db, submission_id, actor)
    if submission.claimed_by is None:
        _set_etag(response, submission)
        return submission
    if submission.claimed_by != actor.name and actor.role != "admin":
        raise HTTPException(
            status_code=403, detail="Only the claimant or an admin can release this item."
        )
    previous = submission.claimed_by
    submission.claimed_by = None
    submission.claimed_at = None
    submission.row_version += 1
    append_audit_event(
        submission,
        "REVIEW_CLAIM_RELEASED",
        actor.name,
        f"Review claim held by {previous} was released.",
        _request_id(request),
    )
    db.commit()
    latest = _get_submission(db, submission_id, actor)
    _set_etag(response, latest)
    return latest


@router.post(
    "/api/v1/submissions/{submission_id}/review",
    response_model=SubmissionDetail,
    tags=["review"],
)
def review_submission(
    request: Request,
    response: Response,
    submission_id: str,
    payload: ReviewRequest,
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
    actor: Actor = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> Submission:
    submission = _get_submission(db, submission_id, actor)
    precondition = resolve_review_precondition(
        if_match=if_match,
        expected_version=payload.expected_version,
        submission_id=submission.id,
        current_version=submission.row_version,
    )

    if submission.status != "AWAITING_REVIEW":
        raise HTTPException(status_code=409, detail="Submission is not awaiting review.")

    now = datetime.now(UTC)
    if actor.role != "admin" and _claim_is_expired(submission, now):
        raise HTTPException(
            status_code=409,
            detail=(
                "The review claim has expired. "
                "Claim the item again before recording a decision."
            ),
        )
    if actor.role != "admin" and submission.claimed_by != actor.name:
        raise HTTPException(
            status_code=409, detail="Claim the review item before recording a decision."
        )

    updated = compare_and_swap_review_decision(
        db,
        submission_id=submission.id,
        expected_version=precondition.expected_version,
        reviewer=actor.name,
        decision=payload.decision,
        rationale=payload.rationale,
        require_claim=actor.role != "admin",
        claim_cutoff=_claim_cutoff(now),
    )
    if not updated:
        db.rollback()
        latest = _get_submission(db, submission_id, actor)
        if latest.row_version != precondition.expected_version:
            raise stale_write_error(precondition.source)
        if latest.status != "AWAITING_REVIEW":
            raise HTTPException(status_code=409, detail="Submission is not awaiting review.")
        if actor.role != "admin" and _claim_is_expired(latest):
            raise HTTPException(
                status_code=409,
                detail=(
                    "The review claim has expired. "
                    "Claim the item again before recording a decision."
                ),
            )
        if actor.role != "admin" and latest.claimed_by != actor.name:
            raise HTTPException(
                status_code=409, detail="Claim the review item before recording a decision."
            )
        raise stale_write_error(precondition.source)

    db.flush()
    db.refresh(submission)
    append_audit_event(
        submission,
        "MANUAL_REVIEW_COMPLETED",
        actor.name,
        f"Final decision={payload.decision}; rationale recorded; automated evidence retained.",
        _request_id(request),
    )
    db.commit()
    latest = _get_submission(db, submission.id, actor)
    _set_etag(response, latest)
    logger.info(
        "Manual review completed", extra={"submission_id": submission.id, "status_code": 200}
    )
    return latest
