export type Decision = 'ALLOW' | 'REVIEW' | 'BLOCK'
export type ReviewDecision = 'ALLOW' | 'BLOCK'
export type RiskBand = 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL'
export type Role = 'researcher' | 'reviewer' | 'admin'
export type OutputType = 'TABLE' | 'FIGURE' | 'REPORT' | 'OTHER'

export interface Actor {
  name: string
  role: Role
}

export interface Finding {
  code: string
  title: string
  category: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  message: string
  evidence: string | null
}

export interface AuditEvent {
  event_type: string
  actor: string
  detail: string
  request_id: string | null
  prev_hash: string
  event_hash: string
  created_at: string
}

export interface SubmissionSummary {
  id: string
  project_code: string
  output_type: OutputType
  output_description: string
  filename: string
  content_type: string
  size_bytes: number
  status: string
  automated_decision: Decision
  final_decision: ReviewDecision | null
  risk_score: number
  risk_band: RiskBand
  policy_version: string
  submitted_by: string
  reviewer: string | null
  claimed_by: string | null
  claimed_at: string | null
  row_version: number
  file_available: boolean
  created_at: string
  updated_at: string
}

export interface SubmissionDetail extends SubmissionSummary {
  sha256: string
  review_rationale: string | null
  findings: Finding[]
  audit_events: AuditEvent[]
}

export interface SubmissionPage {
  items: SubmissionSummary[]
  page: number
  page_size: number
  total: number
  pages: number
}

export interface SubmissionFilters {
  page: number
  pageSize: number
  decision?: Decision
  workflowStatus?: string
  projectCode?: string
  search?: string
  sort: 'newest' | 'oldest' | 'risk_desc'
}

export interface UploadMetadata {
  projectCode: string
  outputType: OutputType
  outputDescription: string
}

export interface TopFinding {
  code: string
  count: number
}

export interface Metrics {
  total: number
  allow: number
  review: number
  block: number
  awaiting_review: number
  claimed_reviews: number
  automated_allow: number
  automated_review: number
  automated_block: number
  completed_reviews: number
  automation_rate: number
  review_completion_rate: number
  manual_block_rate: number
  average_risk: number
  average_queue_age_minutes: number
  oldest_queue_age_minutes: number
  deleted_files: number
  top_findings: TopFinding[]
  policy_version: string
}

export interface PolicyRule {
  code: string
  category: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  title: string
  description: string
  default_action: Decision
}

export interface Policy {
  policy_version: string
  decision_logic: string
  small_cell_threshold: number
  max_rows_to_scan: number
  retention_days: number
  rules: PolicyRule[]
}

export interface PolicySimulationInput {
  critical_action: Decision
  high_action: Decision
  medium_action: Decision
  low_action: Decision
}

export interface PolicySimulation {
  total: number
  allow: number
  review: number
  block: number
  automation_rate: number
  changed_decisions: number
  note: string
}

export interface DecisionReport {
  report_version: string
  generated_at: string
  submission_id: string
  project_code: string
  output_type: OutputType
  filename: string
  sha256: string
  size_bytes: number
  submitted_by: string
  policy_version: string
  automated_decision: Decision
  final_decision: ReviewDecision | null
  status: string
  risk_score: number
  risk_band: RiskBand
  reviewer: string | null
  review_rationale: string | null
  file_available: boolean
  findings: Finding[]
  audit_chain_valid: boolean
  signature_algorithm: string
  signature: string
  disclaimer: string
}

export interface VerificationResult {
  submission_id: string
  signature_valid: boolean
  audit_chain_valid: boolean
}

export interface AuditVerification {
  submission_id: string
  valid: boolean
  checked_events: number
  first_invalid_event_id: number | null
}
