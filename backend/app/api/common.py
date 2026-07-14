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
    submission.findings.clear()
    submission.findings.extend(
        Finding(
            code=item.code,
            severity=item.severity,
            message=item.message,
            evidence=item.evidence,
        )
        for item in findings
    )

def _apply_automated_result(
    submission: Submission,
    findings: list[FindingResult],
    policy_version: str,
) -> None:
    decision, score = decision_from_findings(findings)
    submission.automated_decision = decision
    submission.risk_score = score
    submission.policy_version = policy_version
    _store_findings(submission, findings)
    submission.claimed_by = None
    submission.claimed_at = None
    submission.row_version += 1
    if decision == "REVIEW":
        submission.status = "AWAITING_REVIEW"
        submission.final_decision = None
        submission.reviewer = None
        submission.review_rationale = None
    else:
        submission.status = "COMPLETED"
        submission.final_decision = decision
        submission.reviewer = None
        submission.review_rationale = None

def _duplicate_finding(db: Session, submission_id: str, sha256: str) -> FindingResult | None:
    previous = db.scalar(
        select(Submission).where(
            Submission.sha256 == sha256,
            Submission.id != submission_id,
        )
    )
    if previous is None:
        return None
    return FindingResult(
        code="DUPLICATE_FILE_HASH",
        severity="LOW",
        message="The same file fingerprint has been submitted previously.",
        evidence=f"previous_submission_id={previous.id}; content_not_compared=true",
    )

