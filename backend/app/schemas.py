from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["ALLOW", "REVIEW", "BLOCK"]
ReviewDecision = Literal["ALLOW", "BLOCK"]
Role = Literal["researcher", "reviewer", "admin"]


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    title: str
    category: str
    severity: str
    message: str
    evidence: str | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_type: str
    actor: str
    detail: str
    request_id: str | None
    prev_hash: str
    event_hash: str
    created_at: datetime


class SubmissionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_code: str
    output_type: str
    output_description: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    automated_decision: Decision
    final_decision: ReviewDecision | None
    risk_score: float
    risk_band: str
    policy_version: str
    submitted_by: str
    reviewer: str | None
    claimed_by: str | None
    claimed_at: datetime | None
    row_version: int
    file_available: bool
    created_at: datetime
    updated_at: datetime


class SubmissionDetail(SubmissionSummary):
    sha256: str
    review_rationale: str | None
    findings: list[FindingOut]
    audit_events: list[AuditEventOut]


class SubmissionPage(BaseModel):
    items: list[SubmissionSummary]
    page: int
    page_size: int
    total: int
    pages: int


class ReviewRequest(BaseModel):
    decision: ReviewDecision
    rationale: str = Field(min_length=20, max_length=2000)
    expected_version: int = Field(ge=1)


class TopFindingOut(BaseModel):
    code: str
    count: int


class MetricsOut(BaseModel):
    total: int
    allow: int
    review: int
    block: int
    awaiting_review: int
    claimed_reviews: int
    automated_allow: int
    automated_review: int
    automated_block: int
    completed_reviews: int
    automation_rate: float
    review_completion_rate: float
    manual_block_rate: float
    average_risk: float
    average_queue_age_minutes: float
    oldest_queue_age_minutes: float
    deleted_files: int
    top_findings: list[TopFindingOut]
    policy_version: str


class RuleDefinitionOut(BaseModel):
    code: str
    category: str
    severity: str
    title: str
    description: str
    default_action: Decision


class PolicyOut(BaseModel):
    policy_version: str
    decision_logic: str
    small_cell_threshold: int
    max_rows_to_scan: int
    retention_days: int
    rules: list[RuleDefinitionOut]


class DecisionReportFinding(BaseModel):
    code: str
    title: str
    category: str
    severity: str
    message: str
    evidence: str | None


class DecisionReportOut(BaseModel):
    report_version: str
    generated_at: datetime
    submission_id: str
    project_code: str
    output_type: str
    filename: str
    sha256: str
    size_bytes: int
    submitted_by: str
    policy_version: str
    automated_decision: Decision
    final_decision: ReviewDecision | None
    status: str
    risk_score: float
    risk_band: str
    reviewer: str | None
    review_rationale: str | None
    file_available: bool
    findings: list[DecisionReportFinding]
    audit_chain_valid: bool
    signature_algorithm: str
    signature: str
    disclaimer: str


class ReportVerificationOut(BaseModel):
    submission_id: str
    signature_valid: bool
    audit_chain_valid: bool


class AuditVerificationOut(BaseModel):
    submission_id: str
    valid: bool
    checked_events: int
    first_invalid_event_id: int | None


class PolicySimulationRequest(BaseModel):
    critical_action: Decision = "BLOCK"
    high_action: Decision = "REVIEW"
    medium_action: Decision = "REVIEW"
    low_action: Decision = "ALLOW"


class PolicySimulationOut(BaseModel):
    total: int
    allow: int
    review: int
    block: int
    automation_rate: float
    changed_decisions: int
    note: str


class HealthOut(BaseModel):
    status: str
    service: str
    version: str
    policy_version: str


class ReadinessOut(BaseModel):
    status: str
    database: str
    quarantine: str


class CurrentActorOut(BaseModel):
    name: str
    role: Role
