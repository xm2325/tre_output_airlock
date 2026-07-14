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

from app.api.common import (
    _apply_automated_result,
    _duplicate_finding,
    _get_submission,
    _request_id,
)

logger = logging.getLogger(__name__)
router = APIRouter()
checker = OutputChecker()

@router.post(
    "/api/v1/submissions",
    response_model=SubmissionDetail,
    status_code=status.HTTP_201_CREATED,
    tags=["submissions"],
)
async def create_submission(
    request: Request,
    file: UploadFile = File(...),
    project_code: str = Form(default="DEMO-001", min_length=2, max_length=80),
    output_type: str = Form(default="TABLE", min_length=2, max_length=40),
    output_description: str = Form(
        default="Synthetic aggregate research output for portfolio demonstration.",
        min_length=10,
        max_length=1000,
    ),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> Submission:
    if idempotency_key:
        key = idempotency_key.strip()
        if not 8 <= len(key) <= 120:
            raise HTTPException(status_code=400, detail="Idempotency-Key must be 8-120 characters.")
        existing = db.scalar(select(Submission).where(Submission.idempotency_key == key))
        if existing is not None:
            return _get_submission(db, existing.id, actor)
    else:
        key = None

    normalised_output_type = output_type.strip().upper()
    if normalised_output_type not in {"TABLE", "FIGURE", "REPORT", "OTHER"}:
        raise HTTPException(
            status_code=422, detail="output_type must be TABLE, FIGURE, REPORT or OTHER."
        )

    submission_id = str(uuid4())
    safe_filename = Path(file.filename or "upload.bin").name
    try:
        stored = await store_quarantined_file(file, submission_id)
    except FileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    submission = Submission(
        id=submission_id,
        project_code=project_code.strip(),
        output_type=normalised_output_type,
        output_description=output_description.strip(),
        filename=safe_filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        idempotency_key=key,
        status="QUARANTINED",
        automated_decision="ALLOW",
        final_decision=None,
        risk_score=0.0,
        policy_version=POLICY_VERSION,
        submitted_by=actor.name,
        row_version=1,
    )
    append_audit_event(
        submission,
        "SUBMITTED",
        actor.name,
        (
            f"Project={submission.project_code}; output_type={submission.output_type}; "
            f"filename={safe_filename}."
        ),
        _request_id(request),
    )
    append_audit_event(
        submission,
        "QUARANTINED",
        "airlock-service",
        f"File stored in quarantine; size_bytes={stored.size_bytes}; sha256_recorded=true.",
        _request_id(request),
    )
    submission.status = "SCANNING"
    append_audit_event(
        submission,
        "SCAN_STARTED",
        "rule-engine",
        f"Policy={POLICY_VERSION}; deterministic checks started.",
        _request_id(request),
    )

    context = FileContext(
        path=stored.path,
        filename=safe_filename,
        content_type=submission.content_type,
        size_bytes=stored.size_bytes,
    )
    result = checker.check(context)
    findings = list(result.findings)
    duplicate = _duplicate_finding(db, submission_id, stored.sha256)
    if duplicate is not None:
        findings.append(duplicate)
    _apply_automated_result(submission, findings, result.policy_version)
    append_audit_event(
        submission,
        "AUTOMATED_CHECK_COMPLETED",
        "rule-engine",
        (
            f"Policy={submission.policy_version}; decision={submission.automated_decision}; "
            f"risk_score={submission.risk_score:.3f}; findings={len(findings)}."
        ),
        _request_id(request),
    )
    db.add(submission)
    try:
        db.commit()
    except Exception:
        quarantined_path(submission.id, submission.filename).unlink(missing_ok=True)
        raise
    logger.info("Submission checked", extra={"submission_id": submission.id, "status_code": 201})
    return _get_submission(db, submission.id, actor)

@router.get(
    "/api/v1/submissions",
    response_model=SubmissionPage,
    tags=["submissions"],
)
def list_submissions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    decision: Literal["ALLOW", "REVIEW", "BLOCK"] | None = Query(default=None),
    workflow_status: Literal["AWAITING_REVIEW", "COMPLETED", "QUARANTINED", "SCANNING"]
    | None = Query(default=None),
    project_code: str | None = Query(default=None, max_length=80),
    search: str | None = Query(default=None, max_length=120),
    sort: Literal["newest", "oldest", "risk_desc"] = Query(default="newest"),
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> SubmissionPage:
    conditions: list[ColumnElement[bool]] = []
    if actor.role == "researcher":
        conditions.append(Submission.submitted_by == actor.name)
    if decision is not None:
        conditions.append(Submission.automated_decision == decision)
    if workflow_status is not None:
        conditions.append(Submission.status == workflow_status)
    if project_code and project_code.strip():
        conditions.append(Submission.project_code == project_code.strip())
    if search and search.strip():
        term = f"%{search.strip()}%"
        conditions.append(
            or_(
                Submission.filename.ilike(term),
                Submission.submitted_by.ilike(term),
                Submission.project_code.ilike(term),
                Submission.output_description.ilike(term),
            )
        )

    statement = select(Submission)
    count_statement = select(func.count()).select_from(Submission)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)
    if sort == "oldest":
        statement = statement.order_by(asc(Submission.created_at))
    elif sort == "risk_desc":
        statement = statement.order_by(desc(Submission.risk_score), asc(Submission.created_at))
    else:
        statement = statement.order_by(desc(Submission.created_at))

    total = int(db.scalar(count_statement) or 0)
    rows = list(db.scalars(statement.offset((page - 1) * page_size).limit(page_size)))
    return SubmissionPage(
        items=[SubmissionSummary.model_validate(item) for item in rows],
        page=page,
        page_size=page_size,
        total=total,
        pages=max(1, math.ceil(total / page_size)),
    )

@router.get(
    "/api/v1/submissions/{submission_id}",
    response_model=SubmissionDetail,
    tags=["submissions"],
)
def get_submission(
    submission_id: str,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> Submission:
    return _get_submission(db, submission_id, actor)

@router.post(
    "/api/v1/submissions/{submission_id}/recheck",
    response_model=SubmissionDetail,
    tags=["submissions"],
)
def recheck_submission(
    request: Request,
    submission_id: str,
    actor: Actor = Depends(require_roles("reviewer", "admin")),
    db: Session = Depends(get_db),
) -> Submission:
    submission = _get_submission(db, submission_id, actor)
    path = quarantined_path(submission.id, submission.filename)
    if submission.file_deleted_at is not None or not path.exists():
        raise HTTPException(status_code=409, detail="Quarantined file is no longer available.")

    submission.status = "SCANNING"
    submission.claimed_by = None
    submission.claimed_at = None
    append_audit_event(
        submission, "RECHECK_STARTED", actor.name, f"Policy={POLICY_VERSION}.", _request_id(request)
    )
    result = checker.check(
        FileContext(
            path=path,
            filename=submission.filename,
            content_type=submission.content_type,
            size_bytes=submission.size_bytes,
        )
    )
    findings = list(result.findings)
    duplicate = _duplicate_finding(db, submission.id, submission.sha256)
    if duplicate is not None:
        findings.append(duplicate)
    _apply_automated_result(submission, findings, result.policy_version)
    append_audit_event(
        submission,
        "AUTOMATED_RECHECK_COMPLETED",
        "rule-engine",
        (
            f"Policy={submission.policy_version}; "
            f"decision={submission.automated_decision}; "
            f"risk_score={submission.risk_score:.3f}; "
            f"findings={len(findings)}."
        ),
        _request_id(request),
    )
    db.commit()
    return _get_submission(db, submission.id, actor)

@router.get(
    "/api/v1/submissions/{submission_id}/report",
    tags=["submissions"],
)
def decision_report(
    submission_id: str,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> DecisionReportOut:
    return build_report(_get_submission(db, submission_id, actor))

@router.get(
    "/api/v1/submissions/{submission_id}/report/verify",
    response_model=ReportVerificationOut,
    tags=["submissions"],
)
def verify_decision_report(
    submission_id: str,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> ReportVerificationOut:
    submission = _get_submission(db, submission_id, actor)
    report = build_report(submission)
    audit_valid, _ = verify_audit_chain(submission)
    return ReportVerificationOut(
        submission_id=submission.id,
        signature_valid=verify_report(report),
        audit_chain_valid=audit_valid,
    )

@router.get(
    "/api/v1/submissions/{submission_id}/audit/verify",
    response_model=AuditVerificationOut,
    tags=["audit"],
)
def verify_submission_audit(
    submission_id: str,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
) -> AuditVerificationOut:
    submission = _get_submission(db, submission_id, actor)
    valid, invalid_id = verify_audit_chain(submission)
    return AuditVerificationOut(
        submission_id=submission.id,
        valid=valid,
        checked_events=len(submission.audit_events),
        first_invalid_event_id=invalid_id,
    )

@router.delete(
    "/api/v1/submissions/{submission_id}/file",
    response_model=SubmissionDetail,
    tags=["submissions"],
)
def delete_quarantined_file(
    request: Request,
    submission_id: str,
    actor: Actor = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
) -> Submission:
    submission = _get_submission(db, submission_id, actor)
    if submission.file_deleted_at is None:
        quarantined_path(submission.id, submission.filename).unlink(missing_ok=True)
        submission.file_deleted_at = datetime.now(UTC)
        submission.row_version += 1
        append_audit_event(
            submission,
            "QUARANTINED_FILE_DELETED",
            actor.name,
            "File content deleted under the demonstration retention workflow; metadata retained.",
            _request_id(request),
        )
        db.commit()
    return _get_submission(db, submission.id, actor)

