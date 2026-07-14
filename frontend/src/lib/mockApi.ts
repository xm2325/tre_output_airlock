import type {
  Actor,
  AuditVerification,
  Decision,
  DecisionReport,
  Finding,
  Metrics,
  Policy,
  PolicySimulation,
  PolicySimulationInput,
  SubmissionDetail,
  SubmissionFilters,
  SubmissionPage,
  SubmissionSummary,
  UploadMetadata,
  VerificationResult,
} from '../types/api'

const now = '2026-07-14T18:00:00Z'
const earlier = '2026-07-14T16:30:00Z'
const hash = (value: string) => value.repeat(64).slice(0, 64)

function finding(
  code: string,
  title: string,
  severity: Finding['severity'],
  category: string,
  message: string,
  evidence: string,
): Finding {
  return { code, title, severity, category, message, evidence }
}

function event(event_type: string, actor: string, detail: string, index: number) {
  return {
    event_type,
    actor,
    detail,
    request_id: `demo-request-${index}`,
    prev_hash: index === 0 ? hash('0') : hash(String(index)),
    event_hash: hash(String(index + 1)),
    created_at: now,
  }
}

const seed: SubmissionDetail[] = [
  {
    id: 'demo-review-small-cell',
    project_code: 'UKB-DEMO-042',
    output_type: 'TABLE',
    output_description: 'Synthetic subgroup summary prepared for a controlled manuscript release.',
    filename: 'small_cell_table.csv',
    content_type: 'text/csv',
    size_bytes: 4120,
    status: 'AWAITING_REVIEW',
    automated_decision: 'REVIEW',
    final_decision: null,
    risk_score: 0.55,
    risk_band: 'MODERATE',
    policy_version: 'demo-policy-2026.2',
    submitted_by: 'xiaomei-researcher',
    reviewer: null,
    claimed_by: null,
    claimed_at: null,
    row_version: 2,
    file_available: true,
    created_at: earlier,
    updated_at: earlier,
    sha256: hash('a'),
    review_rationale: null,
    findings: [finding(
      'SMALL_CELL',
      'Small aggregate cell',
      'HIGH',
      'statistical-disclosure',
      'Small aggregate cells may increase disclosure risk.',
      'column=count; small_cells=2; threshold=5',
    )],
    audit_events: [
      event('SUBMITTED', 'xiaomei-researcher', 'Synthetic output registered.', 0),
      event('QUARANTINED', 'system', 'File stored in the demonstration quarantine.', 1),
      event('AUTOMATED_CHECK_COMPLETED', 'system', 'Decision REVIEW under demo-policy-2026.2.', 2),
    ],
  },
  {
    id: 'demo-block-identifier',
    project_code: 'UKB-DEMO-017',
    output_type: 'TABLE',
    output_description: 'Synthetic participant-level export used to demonstrate a hard block.',
    filename: 'participant_level_export.csv',
    content_type: 'text/csv',
    size_bytes: 12380,
    status: 'COMPLETED',
    automated_decision: 'BLOCK',
    final_decision: 'BLOCK',
    risk_score: 1,
    risk_band: 'CRITICAL',
    policy_version: 'demo-policy-2026.2',
    submitted_by: 'other-researcher',
    reviewer: null,
    claimed_by: null,
    claimed_at: null,
    row_version: 2,
    file_available: true,
    created_at: '2026-07-14T15:10:00Z',
    updated_at: '2026-07-14T15:10:00Z',
    sha256: hash('b'),
    review_rationale: null,
    findings: [finding(
      'DIRECT_IDENTIFIER_COLUMN',
      'Direct identifier column',
      'CRITICAL',
      'direct-identifiers',
      'A column name indicates participant-level identifying data.',
      'columns=participant_id; values_not_logged=true',
    )],
    audit_events: [
      event('SUBMITTED', 'other-researcher', 'Synthetic output registered.', 0),
      event('AUTOMATED_CHECK_COMPLETED', 'system', 'Decision BLOCK under demo-policy-2026.2.', 1),
    ],
  },
  {
    id: 'demo-allow-summary',
    project_code: 'UKB-DEMO-001',
    output_type: 'TABLE',
    output_description: 'Synthetic aggregate means with no configured release concern.',
    filename: 'safe_summary.csv',
    content_type: 'text/csv',
    size_bytes: 2080,
    status: 'COMPLETED',
    automated_decision: 'ALLOW',
    final_decision: 'ALLOW',
    risk_score: 0,
    risk_band: 'LOW',
    policy_version: 'demo-policy-2026.2',
    submitted_by: 'xiaomei-researcher',
    reviewer: null,
    claimed_by: null,
    claimed_at: null,
    row_version: 2,
    file_available: true,
    created_at: '2026-07-14T14:00:00Z',
    updated_at: '2026-07-14T14:00:00Z',
    sha256: hash('c'),
    review_rationale: null,
    findings: [],
    audit_events: [
      event('SUBMITTED', 'xiaomei-researcher', 'Synthetic output registered.', 0),
      event('AUTOMATED_CHECK_COMPLETED', 'system', 'Decision ALLOW under demo-policy-2026.2.', 1),
    ],
  },
]

const policy: Policy = {
  policy_version: 'demo-policy-2026.2',
  decision_logic: 'Highest configured action across transparent findings.',
  small_cell_threshold: 5,
  max_rows_to_scan: 10_000,
  retention_days: 30,
  rules: [
    {
      code: 'DIRECT_IDENTIFIER_COLUMN', category: 'direct-identifiers', severity: 'CRITICAL',
      title: 'Direct identifier column', description: 'Participant-level identifier column.', default_action: 'BLOCK',
    },
    {
      code: 'SMALL_CELL', category: 'statistical-disclosure', severity: 'HIGH',
      title: 'Small aggregate cell', description: 'Aggregate count below the demonstration threshold.', default_action: 'REVIEW',
    },
    {
      code: 'HIGH_UNIQUENESS_COLUMN', category: 'statistical-disclosure', severity: 'MEDIUM',
      title: 'Highly unique column', description: 'High uniqueness may indicate row-level data.', default_action: 'REVIEW',
    },
    {
      code: 'PDF_METADATA_PRESENT', category: 'metadata', severity: 'LOW',
      title: 'PDF metadata present', description: 'Document metadata should be checked.', default_action: 'ALLOW',
    },
  ],
}

function copy<T>(value: T): T {
  return structuredClone(value)
}

function calculateMetrics(rows: SubmissionDetail[]): Metrics {
  const final = (decision: Decision) => rows.filter((row) => row.final_decision === decision).length
  const automated = (decision: Decision) => rows.filter((row) => row.automated_decision === decision).length
  const awaiting = rows.filter((row) => row.status === 'AWAITING_REVIEW')
  const frequencies = new Map<string, number>()
  rows.flatMap((row) => row.findings).forEach((item) => frequencies.set(item.code, (frequencies.get(item.code) ?? 0) + 1))
  return {
    total: rows.length,
    allow: final('ALLOW'), review: awaiting.length, block: final('BLOCK'),
    awaiting_review: awaiting.length,
    claimed_reviews: awaiting.filter((row) => row.claimed_by).length,
    automated_allow: automated('ALLOW'), automated_review: automated('REVIEW'), automated_block: automated('BLOCK'),
    completed_reviews: rows.filter((row) => row.reviewer).length,
    automation_rate: rows.length ? (automated('ALLOW') + automated('BLOCK')) / rows.length : 0,
    review_completion_rate: 0,
    manual_block_rate: 0,
    average_risk: rows.length ? rows.reduce((sum, row) => sum + row.risk_score, 0) / rows.length : 0,
    average_queue_age_minutes: 90,
    oldest_queue_age_minutes: 90,
    deleted_files: rows.filter((row) => !row.file_available).length,
    top_findings: [...frequencies.entries()].map(([code, count]) => ({ code, count })),
    policy_version: policy.policy_version,
  }
}

function classifyUpload(file: File, text: string): { decision: Decision; findings: Finding[]; score: number } {
  const lower = `${file.name}\n${text}`.toLowerCase()
  if (lower.includes('participant_id') || lower.includes('@example.')) {
    return {
      decision: 'BLOCK', score: 1,
      findings: [finding('DIRECT_IDENTIFIER_COLUMN', 'Direct identifier column', 'CRITICAL', 'direct-identifiers',
        'Synthetic identifier evidence detected.', 'matched_values_redacted=true')],
    }
  }
  if (/\b(?:count|n),[1-4]\b/.test(lower) || lower.includes('small_cell')) {
    return {
      decision: 'REVIEW', score: 0.55,
      findings: [finding('SMALL_CELL', 'Small aggregate cell', 'HIGH', 'statistical-disclosure',
        'A synthetic aggregate count is below the demonstration threshold.', 'threshold=5; values_redacted=true')],
    }
  }
  return { decision: 'ALLOW', score: 0, findings: [] }
}

export function createMockApi(getActor: () => Actor) {
  const rows = copy(seed)
  const find = (id: string) => {
    const row = rows.find((item) => item.id === id)
    if (!row) throw new Error('Submission was not found in the static demonstration.')
    return row
  }
  const canSee = (row: SubmissionDetail) => getActor().role !== 'researcher' || row.submitted_by === getActor().name

  return {
    me: async () => copy(getActor()),
    metrics: async () => calculateMetrics(rows.filter(canSee)),
    policy: async () => copy(policy),
    simulatePolicy: async (payload: PolicySimulationInput): Promise<PolicySimulation> => {
      const decisions = rows.map((row) => {
        const severity = row.findings[0]?.severity ?? 'LOW'
        const key = `${severity.toLowerCase()}_action` as keyof PolicySimulationInput
        return payload[key]
      })
      return {
        total: decisions.length,
        allow: decisions.filter((item) => item === 'ALLOW').length,
        review: decisions.filter((item) => item === 'REVIEW').length,
        block: decisions.filter((item) => item === 'BLOCK').length,
        automation_rate: decisions.length ? decisions.filter((item) => item !== 'REVIEW').length / decisions.length : 0,
        changed_decisions: decisions.filter((item, index) => item !== rows[index].automated_decision).length,
        note: 'Static in-memory simulation over synthetic submissions.',
      }
    },
    submissions: async (filters: SubmissionFilters): Promise<SubmissionPage> => {
      let visible = rows.filter(canSee)
      if (filters.decision) visible = visible.filter((row) => row.automated_decision === filters.decision)
      if (filters.search?.trim()) {
        const query = filters.search.trim().toLowerCase()
        visible = visible.filter((row) => `${row.filename} ${row.project_code} ${row.output_description}`.toLowerCase().includes(query))
      }
      visible = [...visible].sort((a, b) => filters.sort === 'risk_desc'
        ? b.risk_score - a.risk_score
        : filters.sort === 'oldest'
          ? a.created_at.localeCompare(b.created_at)
          : b.created_at.localeCompare(a.created_at))
      const start = (filters.page - 1) * filters.pageSize
      return {
        items: copy(visible.slice(start, start + filters.pageSize)),
        total: visible.length,
        page: filters.page,
        page_size: filters.pageSize,
        pages: Math.max(1, Math.ceil(visible.length / filters.pageSize)),
      }
    },
    reviewQueue: async () => copy(rows.filter((row) => row.status === 'AWAITING_REVIEW').sort((a, b) => b.risk_score - a.risk_score)),
    submission: async (id: string) => copy(find(id)),
    report: async (id: string): Promise<DecisionReport> => {
      const row = find(id)
      return {
        report_version: '1.0', generated_at: now, submission_id: row.id, project_code: row.project_code,
        output_type: row.output_type, filename: row.filename, sha256: row.sha256, size_bytes: row.size_bytes,
        submitted_by: row.submitted_by, policy_version: row.policy_version,
        automated_decision: row.automated_decision, final_decision: row.final_decision, status: row.status,
        risk_score: row.risk_score, risk_band: row.risk_band, reviewer: row.reviewer,
        review_rationale: row.review_rationale, file_available: row.file_available, findings: copy(row.findings),
        audit_chain_valid: true, signature_algorithm: 'HMAC-SHA256-DEMO', signature: hash('d'),
        disclaimer: 'Static synthetic demonstration. No real participant data.',
      }
    },
    verifyReport: async (id: string): Promise<VerificationResult> => ({ submission_id: id, signature_valid: true, audit_chain_valid: true }),
    verifyAudit: async (id: string): Promise<AuditVerification> => ({ submission_id: id, valid: true, checked_events: find(id).audit_events.length, first_invalid_event_id: null }),
    recheck: async (id: string) => {
      const row = find(id)
      row.row_version += 1
      row.updated_at = now
      row.audit_events.push(event('AUTOMATED_RECHECK_COMPLETED', getActor().name, 'Static demonstration recheck completed.', row.audit_events.length))
      return copy(row)
    },
    claim: async (id: string) => {
      const row = find(id)
      if (row.claimed_by && row.claimed_by !== getActor().name) throw new Error(`Review is already claimed by ${row.claimed_by}.`)
      row.claimed_by = getActor().name
      row.claimed_at = now
      row.row_version += 1
      return copy(row)
    },
    releaseClaim: async (id: string) => {
      const row = find(id)
      row.claimed_by = null
      row.claimed_at = null
      row.row_version += 1
      return copy(row)
    },
    deleteFile: async (id: string) => {
      if (getActor().role !== 'admin') throw new Error('Administrator role is required.')
      const row = find(id)
      row.file_available = false
      row.row_version += 1
      return copy(row)
    },
    upload: async (file: File, metadata: UploadMetadata) => {
      const classification = classifyUpload(file, await file.text())
      const id = crypto.randomUUID()
      const row: SubmissionDetail = {
        id, project_code: metadata.projectCode, output_type: metadata.outputType,
        output_description: metadata.outputDescription, filename: file.name,
        content_type: file.type || 'application/octet-stream', size_bytes: file.size,
        status: classification.decision === 'REVIEW' ? 'AWAITING_REVIEW' : 'COMPLETED',
        automated_decision: classification.decision,
        final_decision: classification.decision === 'REVIEW' ? null : classification.decision,
        risk_score: classification.score,
        risk_band: classification.score >= 1 ? 'CRITICAL' : classification.score >= 0.25 ? 'MODERATE' : 'LOW',
        policy_version: policy.policy_version, submitted_by: getActor().name, reviewer: null,
        claimed_by: null, claimed_at: null, row_version: 2, file_available: true,
        created_at: now, updated_at: now, sha256: hash(id[0] ?? 'e'), review_rationale: null,
        findings: classification.findings,
        audit_events: [event('SUBMITTED', getActor().name, 'Synthetic browser-only upload.', 0),
          event('AUTOMATED_CHECK_COMPLETED', 'static-demo', `Decision ${classification.decision}.`, 1)],
      }
      rows.unshift(row)
      return copy(row)
    },
    review: async (id: string, decision: 'ALLOW' | 'BLOCK', rationale: string, expectedVersion: number) => {
      const row = find(id)
      if (row.row_version !== expectedVersion) throw new Error('The submission changed. Reload before saving the review.')
      if (row.claimed_by !== getActor().name && getActor().role !== 'admin') throw new Error('Claim the review before recording a decision.')
      row.final_decision = decision
      row.status = 'COMPLETED'
      row.reviewer = getActor().name
      row.review_rationale = rationale
      row.claimed_by = null
      row.claimed_at = null
      row.row_version += 1
      row.audit_events.push(event('MANUAL_REVIEW_COMPLETED', getActor().name, `Final decision ${decision}.`, row.audit_events.length))
      return copy(row)
    },
  }
}
