from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.models import Submission
from app.schemas import DecisionReportFinding, DecisionReportOut
from app.services.audit import verify_audit_chain


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sign_payload(payload: dict[str, Any]) -> str:
    return hmac.new(
        settings.report_signing_secret.encode("utf-8"), _canonical(payload), hashlib.sha256
    ).hexdigest()


def build_report(submission: Submission) -> DecisionReportOut:
    audit_valid, _ = verify_audit_chain(submission)
    unsigned: dict[str, Any] = {
        "report_version": "2.0",
        "generated_at": datetime.now(UTC),
        "submission_id": submission.id,
        "project_code": submission.project_code,
        "output_type": submission.output_type,
        "filename": submission.filename,
        "sha256": submission.sha256,
        "size_bytes": submission.size_bytes,
        "submitted_by": submission.submitted_by,
        "policy_version": submission.policy_version,
        "automated_decision": submission.automated_decision,
        "final_decision": submission.final_decision,
        "status": submission.status,
        "risk_score": submission.risk_score,
        "risk_band": submission.risk_band,
        "reviewer": submission.reviewer,
        "review_rationale": submission.review_rationale,
        "file_available": submission.file_available,
        "findings": [
            DecisionReportFinding(
                code=item.code,
                title=item.title,
                category=item.category,
                severity=item.severity,
                message=item.message,
                evidence=item.evidence,
            )
            for item in submission.findings
        ],
        "audit_chain_valid": audit_valid,
        "signature_algorithm": "HMAC-SHA256",
        "disclaimer": (
            "Synthetic portfolio demonstration only. This report is not a production "
            "disclosure-control certificate and is not affiliated with UK Biobank."
        ),
    }
    signature_payload = {
        key: (value.model_dump(mode="json") if isinstance(value, DecisionReportFinding) else value)
        for key, value in unsigned.items()
        if key != "generated_at"
    }
    signature_payload["findings"] = [item.model_dump(mode="json") for item in unsigned["findings"]]
    signature = sign_payload(signature_payload)
    return DecisionReportOut(**unsigned, signature=signature)


def verify_report(report: DecisionReportOut) -> bool:
    payload = report.model_dump(mode="json")
    signature = payload.pop("signature")
    payload.pop("generated_at", None)
    return hmac.compare_digest(signature, sign_payload(payload))
