from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.policy import POLICY_VERSION
from app.models import Finding, Submission
from app.rules.base import FileContext, FindingResult
from app.services.audit import append_audit_event
from app.services.checker import OutputChecker, decision_from_findings
from app.services.storage import quarantined_path


class ScanInputUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ScanAuditContract:
    started_event: str = "SCAN_STARTED"
    started_actor: str = "rule-engine"
    completed_event: str = "AUTOMATED_CHECK_COMPLETED"


def store_findings(submission: Submission, findings: list[FindingResult]) -> None:
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


def apply_automated_result(
    submission: Submission,
    findings: list[FindingResult],
    policy_version: str,
) -> None:
    decision, score = decision_from_findings(findings)
    submission.automated_decision = decision
    submission.risk_score = score
    submission.policy_version = policy_version
    store_findings(submission, findings)
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


def duplicate_finding(db: Session, submission_id: str, sha256: str) -> FindingResult | None:
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


def run_submission_scan(
    db: Session,
    submission: Submission,
    *,
    checker: OutputChecker,
    request_id: str | None,
    audit: ScanAuditContract = ScanAuditContract(),
    path: Path | None = None,
) -> None:
    input_path = path or quarantined_path(submission.id, submission.filename)
    if submission.file_deleted_at is not None or not input_path.exists():
        raise ScanInputUnavailable("Quarantined file is no longer available.")

    submission.status = "SCANNING"
    submission.claimed_by = None
    submission.claimed_at = None
    append_audit_event(
        submission,
        audit.started_event,
        audit.started_actor,
        f"Policy={POLICY_VERSION}.",
        request_id,
    )

    result = checker.check(
        FileContext(
            path=input_path,
            filename=submission.filename,
            content_type=submission.content_type,
            size_bytes=submission.size_bytes,
        )
    )
    findings = list(result.findings)
    duplicate = duplicate_finding(db, submission.id, submission.sha256)
    if duplicate is not None:
        findings.append(duplicate)
    apply_automated_result(submission, findings, result.policy_version)
    append_audit_event(
        submission,
        audit.completed_event,
        "rule-engine",
        (
            f"Policy={submission.policy_version}; decision={submission.automated_decision}; "
            f"risk_score={submission.risk_score:.3f}; findings={len(findings)}."
        ),
        request_id,
    )
