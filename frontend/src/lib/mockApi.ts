import type {
  Actor,
  AuditVerification,
  Decision,
  DecisionReport,
  Finding,
  Metrics,
  PolicySimulation,
  PolicySimulationInput,
  SubmissionDetail,
  SubmissionFilters,
  SubmissionPage,
  SubmissionSummary,
  UploadMetadata,
  VerificationResult,
} from '../types/api'
import {
  currentIso,
  createDemoSeed,
  demoEvent,
  demoFinding,
  demoHash,
  demoPolicy,
  DEMO_SEED_COUNT,
  findings,
} from './mockDataset'

export { DEMO_SEED_COUNT }

const MINUTE_MS = 60_000
const severityRank: Record<Finding['severity'], number> = { LOW: 0, MEDIUM: 1, HIGH: 2, CRITICAL: 3 }
const actionRank: Record<Decision, number> = { ALLOW: 0, REVIEW: 1, BLOCK: 2 }

function copy<T>(value: T): T {
  return structuredClone(value)
}

function queueAgeMinutes(row: SubmissionDetail): number {
  return Math.max(0, Math.round((Date.now() - Date.parse(row.created_at)) / MINUTE_MS))
}

function calculateMetrics(rows: SubmissionDetail[]): Metrics {
  const final = (decision: Decision) => rows.filter((row) => row.final_decision === decision).length
  const automated = (decision: Decision) => rows.filter((row) => row.automated_decision === decision).length
  const awaiting = rows.filter((row) => row.status === 'AWAITING_REVIEW')
  const automatedReviews = rows.filter((row) => row.automated_decision === 'REVIEW')
  const completedReviews = automatedReviews.filter((row) => row.status === 'COMPLETED' && row.reviewer)
  const queueAges = awaiting.map(queueAgeMinutes)
  const frequencies = new Map<string, number>()
  rows.flatMap((row) => row.findings).forEach((item) => frequencies.set(item.code, (frequencies.get(item.code) ?? 0) + 1))

  return {
    total: rows.length,
    allow: final('ALLOW'),
    review: awaiting.length,
    block: final('BLOCK'),
    awaiting_review: awaiting.length,
    claimed_reviews: awaiting.filter((row) => row.claimed_by).length,
    automated_allow: automated('ALLOW'),
    automated_review: automated('REVIEW'),
    automated_block: automated('BLOCK'),
    completed_reviews: completedReviews.length,
    automation_rate: rows.length ? (automated('ALLOW') + automated('BLOCK')) / rows.length : 0,
    review_completion_rate: automatedReviews.length ? completedReviews.length / automatedReviews.length : 0,
    manual_block_rate: completedReviews.length
      ? completedReviews.filter((row) => row.final_decision === 'BLOCK').length / completedReviews.length
      : 0,
    average_risk: rows.length ? rows.reduce((sum, row) => sum + row.risk_score, 0) / rows.length : 0,
    average_queue_age_minutes: queueAges.length ? queueAges.reduce((sum, age) => sum + age, 0) / queueAges.length : 0,
    oldest_queue_age_minutes: queueAges.length ? Math.max(...queueAges) : 0,
    deleted_files: rows.filter((row) => !row.file_available).length,
    top_findings: [...frequencies.entries()]
      .map(([code, count]) => ({ code, count }))
      .sort((a, b) => b.count - a.count || a.code.localeCompare(b.code)),
    policy_version: demoPolicy.policy_version,
  }
}

function actionForSeverity(payload: PolicySimulationInput, severity: Finding['severity']): Decision {
  return payload[`${severity.toLowerCase()}_action` as keyof PolicySimulationInput]
}

function highestAction(actions: Decision[]): Decision {
  return actions.reduce<Decision>((highest, action) => (actionRank[action] > actionRank[highest] ? action : highest), 'ALLOW')
}

function classifyUpload(file: File, text: string): { decision: Decision; findings: Finding[]; score: number } {
  const lower = text.toLowerCase()
  const lowerName = file.name.toLowerCase()
  const detected: Finding[] = []

  if (!['.csv', '.txt', '.pdf', '.png', '.jpg', '.jpeg'].some((extension) => lowerName.endsWith(extension))) {
    detected.push(demoFinding('UNSUPPORTED_FILE_TYPE', 'Unsupported file type', 'CRITICAL', 'file-integrity',
      'The file extension is outside the demonstration allow-list.', `filename=${lowerName}`))
  }
  if (/(^|,)(participant_id|patient_id|subject_id|record_id|nhs_number|date_of_birth|postcode)(,|$)/m.test(lower)) {
    detected.push(demoFinding('DIRECT_IDENTIFIER_COLUMN', 'Direct identifier column', 'CRITICAL', 'direct-identifiers',
      'A direct or sensitive identifier column was detected.', 'values_not_logged=true'))
  }
  if (/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i.test(text)) {
    detected.push(demoFinding('EMAIL_ADDRESS', 'Email address detected', 'CRITICAL', 'direct-identifiers',
      'Email-like text is not permitted in an output release.', 'matched_values_redacted=true'))
  }
  if (/\b(?:0|\+44)[1-9](?:[\s()-]*\d){8,10}\b/.test(text)) {
    detected.push(demoFinding('PHONE_NUMBER', 'Telephone number detected', 'CRITICAL', 'direct-identifiers',
      'Telephone-like text is not permitted in an output release.', 'matched_values_redacted=true'))
  }
  if (/(^|,)(notes?|comment|free_text)(,|$)/m.test(lower)) detected.push(findings.freeText)
  if (/(^|,)\s*[=+@][^,\n]*/m.test(text)) detected.push(findings.formula)
  if (/(^|,)(?:count|n)\s*,\s*[1-4](?:\s*,|\s*$)/im.test(text)) detected.push(findings.smallCell)
  if (text.split(/\r?\n/).length > demoPolicy.max_rows_to_scan) detected.push(findings.partial)

  const highestSeverity = detected.reduce<Finding['severity'] | null>(
    (highest, item) => (!highest || severityRank[item.severity] > severityRank[highest] ? item.severity : highest),
    null,
  )
  if (!highestSeverity) return { decision: 'ALLOW', score: 0, findings: detected }
  if (highestSeverity === 'CRITICAL') return { decision: 'BLOCK', score: 1, findings: detected }
  if (highestSeverity === 'HIGH') return { decision: 'REVIEW', score: 0.55, findings: detected }
  if (highestSeverity === 'MEDIUM') return { decision: 'REVIEW', score: 0.35, findings: detected }
  return { decision: 'ALLOW', score: 0.05, findings: detected }
}

export function createMockApi(getActor: () => Actor) {
  const rows = createDemoSeed()
  const find = (id: string) => {
    const row = rows.find((item) => item.id === id)
    if (!row) throw new Error('Submission was not found in the static demonstration.')
    return row
  }
  const canSee = (row: SubmissionDetail) => getActor().role !== 'researcher' || row.submitted_by === getActor().name

  return {
    me: async () => copy(getActor()),
    metrics: async () => calculateMetrics(rows.filter(canSee)),
    policy: async () => copy(demoPolicy),
    simulatePolicy: async (payload: PolicySimulationInput): Promise<PolicySimulation> => {
      const decisions = rows.map((row) => row.findings.length
        ? highestAction(row.findings.map((item) => actionForSeverity(payload, item.severity)))
        : 'ALLOW')
      return {
        total: decisions.length,
        allow: decisions.filter((item) => item === 'ALLOW').length,
        review: decisions.filter((item) => item === 'REVIEW').length,
        block: decisions.filter((item) => item === 'BLOCK').length,
        automation_rate: decisions.length ? decisions.filter((item) => item !== 'REVIEW').length / decisions.length : 0,
        changed_decisions: decisions.filter((item, index) => item !== rows[index].automated_decision).length,
        note: `Static in-memory simulation over ${DEMO_SEED_COUNT} synthetic submissions.`,
      }
    },
    submissions: async (filters: SubmissionFilters): Promise<SubmissionPage> => {
      let visible = rows.filter(canSee)
      if (filters.decision) visible = visible.filter((row) => row.automated_decision === filters.decision)
      if (filters.workflowStatus) visible = visible.filter((row) => row.status === filters.workflowStatus)
      if (filters.projectCode?.trim()) visible = visible.filter((row) => row.project_code === filters.projectCode?.trim())
      if (filters.search?.trim()) {
        const query = filters.search.trim().toLowerCase()
        visible = visible.filter((row) => `${row.filename} ${row.project_code} ${row.output_description} ${row.submitted_by}`.toLowerCase().includes(query))
      }
      visible = [...visible].sort((a, b) => filters.sort === 'risk_desc'
        ? b.risk_score - a.risk_score || a.created_at.localeCompare(b.created_at)
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
    reviewQueue: async () => copy(rows.filter(canSee)
      .filter((row) => row.status === 'AWAITING_REVIEW')
      .sort((a, b) => b.risk_score - a.risk_score || a.created_at.localeCompare(b.created_at))),
    submission: async (id: string) => copy(find(id)),
    report: async (id: string): Promise<DecisionReport> => {
      const row = find(id)
      return {
        report_version: '1.0', generated_at: currentIso(), submission_id: row.id,
        project_code: row.project_code, output_type: row.output_type, filename: row.filename,
        sha256: row.sha256, size_bytes: row.size_bytes, submitted_by: row.submitted_by,
        policy_version: row.policy_version, automated_decision: row.automated_decision,
        final_decision: row.final_decision, status: row.status, risk_score: row.risk_score,
        risk_band: row.risk_band, reviewer: row.reviewer, review_rationale: row.review_rationale,
        file_available: row.file_available, findings: copy(row.findings), audit_chain_valid: true,
        signature_algorithm: 'HMAC-SHA256-DEMO', signature: demoHash('d'),
        disclaimer: 'Static synthetic demonstration. No real participant data.',
      }
    },
    verifyReport: async (id: string): Promise<VerificationResult> => ({ submission_id: id, signature_valid: true, audit_chain_valid: true }),
    verifyAudit: async (id: string): Promise<AuditVerification> => ({ submission_id: id, valid: true, checked_events: find(id).audit_events.length, first_invalid_event_id: null }),
    recheck: async (id: string) => {
      const row = find(id)
      row.row_version += 1
      row.updated_at = currentIso()
      row.audit_events.push(demoEvent('AUTOMATED_RECHECK_COMPLETED', getActor().name, 'Static demonstration recheck completed.', row.audit_events.length))
      return copy(row)
    },
    claim: async (id: string) => {
      if (getActor().role === 'researcher') throw new Error('Reviewer or administrator role is required.')
      const row = find(id)
      if (row.claimed_by && row.claimed_by !== getActor().name) throw new Error(`Review is already claimed by ${row.claimed_by}.`)
      row.claimed_by = getActor().name
      row.claimed_at = currentIso()
      row.row_version += 1
      row.audit_events.push(demoEvent('REVIEW_CLAIMED', getActor().name, 'Review ownership recorded.', row.audit_events.length))
      return copy(row)
    },
    releaseClaim: async (id: string) => {
      if (getActor().role === 'researcher') throw new Error('Reviewer or administrator role is required.')
      const row = find(id)
      row.claimed_by = null
      row.claimed_at = null
      row.row_version += 1
      row.audit_events.push(demoEvent('REVIEW_CLAIM_RELEASED', getActor().name, 'Review ownership released.', row.audit_events.length))
      return copy(row)
    },
    deleteFile: async (id: string) => {
      if (getActor().role !== 'admin') throw new Error('Administrator role is required.')
      const row = find(id)
      row.file_available = false
      row.row_version += 1
      row.updated_at = currentIso()
      row.audit_events.push(demoEvent('FILE_DELETED', getActor().name, 'Quarantine object removed in the static demonstration.', row.audit_events.length))
      return copy(row)
    },
    upload: async (file: File, metadata: UploadMetadata) => {
      let text = ''
      try { text = await file.text() } catch { text = '' }
      const classification = classifyUpload(file, text)
      const id = crypto.randomUUID()
      const createdAt = currentIso()
      const row: SubmissionDetail = {
        id, project_code: metadata.projectCode, output_type: metadata.outputType,
        output_description: metadata.outputDescription, filename: file.name,
        content_type: file.type || 'application/octet-stream', size_bytes: file.size,
        status: classification.decision === 'REVIEW' ? 'AWAITING_REVIEW' : 'COMPLETED',
        automated_decision: classification.decision,
        final_decision: classification.decision === 'REVIEW' ? null : classification.decision,
        risk_score: classification.score,
        risk_band: classification.score >= 1 ? 'CRITICAL' : classification.score >= 0.5 ? 'HIGH' : classification.score >= 0.25 ? 'MODERATE' : 'LOW',
        policy_version: demoPolicy.policy_version, submitted_by: getActor().name, reviewer: null,
        claimed_by: null, claimed_at: null, row_version: 2, file_available: true,
        created_at: createdAt, updated_at: createdAt, sha256: demoHash(id), review_rationale: null,
        findings: classification.findings,
        audit_events: [demoEvent('SUBMITTED', getActor().name, 'Synthetic browser-only upload.', 0, createdAt),
          demoEvent('AUTOMATED_CHECK_COMPLETED', 'static-demo', `Decision ${classification.decision}.`, 1, createdAt)],
      }
      rows.unshift(row)
      return copy(row)
    },
    review: async (id: string, decision: 'ALLOW' | 'BLOCK', rationale: string, expectedVersion: number) => {
      if (getActor().role === 'researcher') throw new Error('Reviewer or administrator role is required.')
      const row = find(id)
      if (row.row_version !== expectedVersion) throw new Error('The submission changed. Reload before saving the review.')
      if (row.claimed_by !== getActor().name && getActor().role !== 'admin') throw new Error('Claim the review before recording a decision.')
      row.final_decision = decision
      row.status = 'COMPLETED'
      row.reviewer = getActor().name
      row.review_rationale = rationale
      row.claimed_by = null
      row.claimed_at = null
      row.updated_at = currentIso()
      row.row_version += 1
      row.audit_events.push(demoEvent('MANUAL_REVIEW_COMPLETED', getActor().name, `Final decision ${decision}.`, row.audit_events.length))
      return copy(row)
    },
  }
}
