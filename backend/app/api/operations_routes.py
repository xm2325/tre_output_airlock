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

from app.api.common import _as_utc

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/health", response_model=HealthOut, tags=["operations"])
def health() -> HealthOut:
    return HealthOut(
        status="ok",
        service="tre-output-airlock-api",
        version=API_VERSION,
        policy_version=POLICY_VERSION,
    )

@router.get("/ready", response_model=ReadinessOut, tags=["operations"])
def readiness(db: Session = Depends(get_db)) -> ReadinessOut:
    try:
        db.execute(text("SELECT 1"))
        settings.quarantine_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.quarantine_dir / ".readiness-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        logger.exception("Readiness check failed")
        raise HTTPException(status_code=503, detail="Service dependencies are not ready.") from exc
    return ReadinessOut(status="ready", database="ok", quarantine="ok")

@router.get("/metrics", response_class=PlainTextResponse, tags=["operations"])
def prometheus_metrics() -> str:
    return telemetry.prometheus()

@router.get("/api/v1/me", response_model=CurrentActorOut, tags=["identity"])
def current_actor(actor: Actor = Depends(get_actor)) -> CurrentActorOut:
    return CurrentActorOut(name=actor.name, role=actor.role)

@router.get("/api/v1/metrics", response_model=MetricsOut, tags=["operations"])
def metrics(db: Session = Depends(get_db)) -> MetricsOut:
    total = int(db.scalar(select(func.count()).select_from(Submission)) or 0)

    def count_where(condition: ColumnElement[bool]) -> int:
        return int(db.scalar(select(func.count()).select_from(Submission).where(condition)) or 0)

    allow = count_where(Submission.final_decision == "ALLOW")
    block = count_where(Submission.final_decision == "BLOCK")
    automated_allow = count_where(Submission.automated_decision == "ALLOW")
    automated_review = count_where(Submission.automated_decision == "REVIEW")
    automated_block = count_where(Submission.automated_decision == "BLOCK")
    awaiting_review = count_where(Submission.status == "AWAITING_REVIEW")
    claimed_reviews = count_where(
        and_(Submission.status == "AWAITING_REVIEW", Submission.claimed_by.is_not(None))
    )
    completed_reviews = count_where(
        and_(Submission.automated_decision == "REVIEW", Submission.status == "COMPLETED")
    )
    manual_blocks = count_where(
        and_(Submission.automated_decision == "REVIEW", Submission.final_decision == "BLOCK")
    )
    deleted_files = count_where(Submission.file_deleted_at.is_not(None))
    average_risk = float(
        db.scalar(select(func.avg(Submission.risk_score)).select_from(Submission)) or 0.0
    )

    queue_times = list(
        db.scalars(select(Submission.created_at).where(Submission.status == "AWAITING_REVIEW"))
    )
    now = datetime.now(UTC)
    queue_ages = [max(0.0, (now - _as_utc(item)).total_seconds() / 60) for item in queue_times]

    top_rows = db.execute(
        select(Finding.code, func.count(Finding.id).label("count"))
        .group_by(Finding.code)
        .order_by(func.count(Finding.id).desc(), Finding.code)
        .limit(5)
    ).all()
    automation_rate = (automated_allow + automated_block) / total if total else 0.0
    review_completion_rate = completed_reviews / automated_review if automated_review else 0.0
    manual_block_rate = manual_blocks / completed_reviews if completed_reviews else 0.0
    return MetricsOut(
        total=total,
        allow=allow,
        review=automated_review,
        block=block,
        awaiting_review=awaiting_review,
        claimed_reviews=claimed_reviews,
        automated_allow=automated_allow,
        automated_review=automated_review,
        automated_block=automated_block,
        completed_reviews=completed_reviews,
        automation_rate=round(automation_rate, 3),
        review_completion_rate=round(review_completion_rate, 3),
        manual_block_rate=round(manual_block_rate, 3),
        average_risk=round(average_risk, 3),
        average_queue_age_minutes=round(sum(queue_ages) / len(queue_ages), 2)
        if queue_ages
        else 0.0,
        oldest_queue_age_minutes=round(max(queue_ages), 2) if queue_ages else 0.0,
        deleted_files=deleted_files,
        top_findings=[TopFindingOut(code=code, count=count) for code, count in top_rows],
        policy_version=POLICY_VERSION,
    )

