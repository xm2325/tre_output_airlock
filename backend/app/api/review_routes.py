# ruff: noqa: F401
from __future__ import annotations

import logging
import math
from datetime import UTC, datetime
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
from app.services.storage import FileTooLargeError, quarantined_path, store_quarantined_file

logger = logging.getLogger(__name__)
router = APIRouter()

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
        statement = statement.where(Submission.claimed_by.is_(None))
    statement = statement.order_by(desc(Submission.risk_score), asc(Submission.created_at))
    return list(db.scalars(statement))

@router.post(
    "/api/v1/submissions/{submission_id}/claim",
    response_model=SubmissionDetail,
    tags=["review"],
)
def claim_submission(
    request: Request,
    submission_id: str,
    actor: Actor = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> Submission:
    current = _get_submission(db, submission_id, actor)
    if current.status != "AWAITING_REVIEW":
        raise HTTPException(status_code=409, detail="Submission is not awaiting review.")
    if current.claimed_by == actor.name:
        return current
    if current.claimed_by is not None:
        raise HTTPException(
            status_code=409, detail=f"Submission is already claimed by {current.claimed_by}."
        )

    result = db.execute(
        update(Submission)
        .where(
            Submission.id == submission_id,
            Submission.status == "AWAITING_REVIEW",
            Submission.claimed_by.is_(None),
            Submission.row_version == current.row_version,
        )
        .values(
            claimed_by=actor.name,
            claimed_at=datetime.now(UTC),
            row_version=current.row_version + 1,
        )
    )
    if getattr(result, "rowcount", 0) != 1:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="The review item changed. Refresh and try again."
        )
    db.commit()
    submission = _get_submission(db, submission_id, actor)
    append_audit_event(
        submission,
        "REVIEW_CLAIMED",
        actor.name,
        f"Reviewer claimed item at row_version={submission.row_version}.",
        _request_id(request),
    )
    db.commit()
    return _get_submission(db, submission_id, actor)

@router.post(
    "/api/v1/submissions/{submission_id}/release-claim",
    response_model=SubmissionDetail,
    tags=["review"],
)
def release_claim(
    request: Request,
    submission_id: str,
    actor: Actor = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> Submission:
    submission = _get_submission(db, submission_id, actor)
    if submission.claimed_by is None:
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
    return _get_submission(db, submission_id, actor)

@router.post(
    "/api/v1/submissions/{submission_id}/review",
    response_model=SubmissionDetail,
    tags=["review"],
)
def review_submission(
    request: Request,
    submission_id: str,
    payload: ReviewRequest,
    actor: Actor = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> Submission:
    submission = _get_submission(db, submission_id, actor)
    if submission.status != "AWAITING_REVIEW":
        raise HTTPException(status_code=409, detail="Submission is not awaiting review.")
    if payload.expected_version != submission.row_version:
        raise HTTPException(
            status_code=409, detail="The review item changed. Refresh and try again."
        )
    if actor.role != "admin" and submission.claimed_by != actor.name:
        raise HTTPException(
            status_code=409, detail="Claim the review item before recording a decision."
        )

    submission.final_decision = payload.decision
    submission.status = "COMPLETED"
    submission.reviewer = actor.name
    submission.review_rationale = payload.rationale
    submission.claimed_by = None
    submission.claimed_at = None
    submission.row_version += 1
    append_audit_event(
        submission,
        "MANUAL_REVIEW_COMPLETED",
        actor.name,
        f"Final decision={payload.decision}; rationale recorded; automated evidence retained.",
        _request_id(request),
    )
    db.commit()
    logger.info(
        "Manual review completed", extra={"submission_id": submission.id, "status_code": 200}
    )
    return _get_submission(db, submission.id, actor)

