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

router = APIRouter()

@router.get("/api/v1/policy", response_model=PolicyOut, tags=["policy"])
def policy() -> PolicyOut:
    return PolicyOut(
        policy_version=POLICY_VERSION,
        decision_logic=(
            "The rule catalogue maps each finding to ALLOW, REVIEW or BLOCK. The most "
            "restrictive action wins. Human review can resolve REVIEW cases but cannot "
            "silently remove the automated evidence."
        ),
        small_cell_threshold=SMALL_CELL_THRESHOLD,
        max_rows_to_scan=MAX_ROWS_TO_SCAN,
        retention_days=settings.retention_days,
        rules=[RuleDefinitionOut(**item.__dict__) for item in RULE_CATALOG],
    )

@router.post(
    "/api/v1/policy/simulate",
    response_model=PolicySimulationOut,
    tags=["policy"],
)
def simulate_policy(
    payload: PolicySimulationRequest,
    _: Actor = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> PolicySimulationOut:
    action_by_severity = {
        "CRITICAL": payload.critical_action,
        "HIGH": payload.high_action,
        "MEDIUM": payload.medium_action,
        "LOW": payload.low_action,
    }
    rows = list(db.scalars(select(Submission).options(selectinload(Submission.findings))))
    counts = {"ALLOW": 0, "REVIEW": 0, "BLOCK": 0}
    changed = 0
    for row in rows:
        actions = [action_by_severity.get(item.severity, "REVIEW") for item in row.findings]
        simulated = max(actions, key=lambda item: ACTION_PRIORITY[item], default="ALLOW")
        counts[simulated] += 1
        changed += int(simulated != row.automated_decision)
    total = len(rows)
    automation_rate = (counts["ALLOW"] + counts["BLOCK"]) / total if total else 0.0
    return PolicySimulationOut(
        total=total,
        allow=counts["ALLOW"],
        review=counts["REVIEW"],
        block=counts["BLOCK"],
        automation_rate=round(automation_rate, 3),
        changed_decisions=changed,
        note=(
            "This is a retrospective workflow simulation over stored findings. It does not "
            "re-run file checks and does not estimate clinical or disclosure-control accuracy."
        ),
    )

