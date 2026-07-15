import type { Decision, Finding, Policy, RiskBand, SubmissionDetail } from '../types/api'

const MINUTE_MS = 60_000
export const DEMO_POLICY_VERSION = 'demo-policy-2026.4'
export const DEMO_SEED_COUNT = 18
export const currentIso = () => new Date().toISOString()
const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * MINUTE_MS).toISOString()
const hash = (value: string) => value.repeat(64).slice(0, 64)

export function demoFinding(
  code: string,
  title: string,
  severity: Finding['severity'],
  category: string,
  message: string,
  evidence: string,
): Finding {
  return { code, title, severity, category, message, evidence }
}

export function demoEvent(eventType: string, actor: string, detail: string, index: number, createdAt = currentIso()) {
  return {
    event_type: eventType,
    actor,
    detail,
    request_id: `demo-request-${index}`,
    prev_hash: index === 0 ? hash('0') : hash(String(index)),
    event_hash: hash(String(index + 1)),
    created_at: createdAt,
  }
}

export const demoHash = hash

interface SeedInput {
  id: string
  project: string
  type: SubmissionDetail['output_type']
  description: string
  filename: string
  size: number
  status: string
  automated: Decision
  final: SubmissionDetail['final_decision']
  score: number
  band: RiskBand
  owner: string
  age: number
  findings?: Finding[]
  contentType?: string
  reviewer?: string
  claimedBy?: string
  rationale?: string
  fileAvailable?: boolean
  policyVersion?: string
}

function build(input: SeedInput): SubmissionDetail {
  const createdAt = minutesAgo(input.age)
  const policyVersion = input.policyVersion ?? DEMO_POLICY_VERSION
  const auditEvents = [
    demoEvent('SUBMITTED', input.owner, 'Synthetic output registered.', 0, createdAt),
    demoEvent('QUARANTINED', 'system', 'File stored in the demonstration quarantine.', 1, createdAt),
    demoEvent('AUTOMATED_CHECK_COMPLETED', 'system', `Decision ${input.automated} under ${policyVersion}.`, 2, createdAt),
  ]
  if (input.claimedBy) auditEvents.push(demoEvent('REVIEW_CLAIMED', input.claimedBy, 'Review ownership recorded.', auditEvents.length, createdAt))
  if (input.reviewer) auditEvents.push(demoEvent('MANUAL_REVIEW_COMPLETED', input.reviewer, `Final decision ${input.final}.`, auditEvents.length, createdAt))
  if (input.fileAvailable === false) auditEvents.push(demoEvent('FILE_DELETED', 'xiaomei-admin', 'Quarantine object removed after retention review.', auditEvents.length, createdAt))

  return {
    id: input.id,
    project_code: input.project,
    output_type: input.type,
    output_description: input.description,
    filename: input.filename,
    content_type: input.contentType ?? 'text/csv',
    size_bytes: input.size,
    status: input.status,
    automated_decision: input.automated,
    final_decision: input.final,
    risk_score: input.score,
    risk_band: input.band,
    policy_version: policyVersion,
    submitted_by: input.owner,
    reviewer: input.reviewer ?? null,
    claimed_by: input.claimedBy ?? null,
    claimed_at: input.claimedBy ? createdAt : null,
    row_version: input.reviewer || input.claimedBy ? 3 : 2,
    file_available: input.fileAvailable ?? true,
    created_at: createdAt,
    updated_at: createdAt,
    sha256: hash(input.id),
    review_rationale: input.rationale ?? null,
    findings: input.findings ?? [],
    audit_events: auditEvents,
  }
}

export const findings = {
  smallCell: demoFinding('SMALL_CELL', 'Small aggregate cell', 'HIGH', 'statistical-disclosure',
    'An aggregate count is below the demonstration release threshold.', 'column=count; threshold=5; matched_values_redacted=true'),
  unique: demoFinding('HIGH_UNIQUENESS_COLUMN', 'Highly unique column', 'MEDIUM', 'statistical-disclosure',
    'High uniqueness may indicate participant-level rows rather than an aggregate output.', 'uniqueness_ratio=0.99; values_not_logged=true'),
  freeText: demoFinding('FREE_TEXT_COLUMN', 'Free-text column', 'HIGH', 'unstructured-content',
    'Free text can contain identifiers or sensitive narrative content and requires review.', 'columns=notes; values_not_logged=true'),
  formula: demoFinding('SPREADSHEET_FORMULA', 'Spreadsheet formula detected', 'HIGH', 'active-content',
    'Formula-like content should be flattened and reviewed before release.', 'formula_cells=3; formulas_redacted=true'),
  partial: demoFinding('PARTIAL_INSPECTION', 'Partial inspection only', 'MEDIUM', 'inspection-coverage',
    'The output exceeded the configured row inspection limit.', 'rows_scanned=10000; additional_rows_present=true'),
}

export function createDemoSeed(): SubmissionDetail[] {
  return [
    build({ id: 'demo-review-small-cell', project: 'UKB-DEMO-042', type: 'TABLE', description: 'Synthetic subgroup summary prepared for a controlled manuscript release.', filename: 'small_cell_table.csv', size: 4_120, status: 'AWAITING_REVIEW', automated: 'REVIEW', final: null, score: 0.55, band: 'HIGH', owner: 'xiaomei-researcher', age: 90, findings: [findings.smallCell] }),
    build({ id: 'demo-block-identifier', project: 'UKB-DEMO-017', type: 'TABLE', description: 'Synthetic participant-level export used to demonstrate a hard block.', filename: 'participant_level_export.csv', size: 12_380, status: 'COMPLETED', automated: 'BLOCK', final: 'BLOCK', score: 1, band: 'CRITICAL', owner: 'other-researcher', age: 170, findings: [demoFinding('DIRECT_IDENTIFIER_COLUMN', 'Direct identifier column', 'CRITICAL', 'direct-identifiers', 'A column name indicates participant-level identifying data.', 'columns=participant_id; values_not_logged=true')] }),
    build({ id: 'demo-allow-summary', project: 'UKB-DEMO-001', type: 'TABLE', description: 'Synthetic aggregate means with no configured release concern.', filename: 'safe_summary.csv', size: 2_080, status: 'COMPLETED', automated: 'ALLOW', final: 'ALLOW', score: 0, band: 'LOW', owner: 'xiaomei-researcher', age: 220 }),
    build({ id: 'demo-review-unique', project: 'UKB-DEMO-101', type: 'TABLE', description: 'Synthetic row-like export with a near-unique study key.', filename: 'cohort_extract.csv', size: 86_440, status: 'AWAITING_REVIEW', automated: 'REVIEW', final: null, score: 0.42, band: 'MODERATE', owner: 'alex-researcher', age: 55, claimedBy: 'xiaomei-reviewer', findings: [findings.unique] }),
    build({ id: 'demo-review-free-text', project: 'UKB-DEMO-042', type: 'TABLE', description: 'Synthetic results table containing a narrative notes field.', filename: 'phenotype_notes.csv', size: 18_740, status: 'AWAITING_REVIEW', automated: 'REVIEW', final: null, score: 0.55, band: 'HIGH', owner: 'xiaomei-researcher', age: 310, findings: [findings.freeText] }),
    build({ id: 'demo-block-email', project: 'UKB-DEMO-088', type: 'TABLE', description: 'Synthetic contact export containing an email address.', filename: 'contact_followup.csv', size: 6_420, status: 'COMPLETED', automated: 'BLOCK', final: 'BLOCK', score: 1, band: 'CRITICAL', owner: 'priya-researcher', age: 400, findings: [demoFinding('EMAIL_ADDRESS', 'Email address detected', 'CRITICAL', 'direct-identifiers', 'Email-like text is not permitted in an output release.', 'matched_values_redacted=true')] }),
    build({ id: 'demo-block-phone', project: 'UKB-DEMO-042', type: 'OTHER', description: 'Synthetic text export containing a UK telephone number.', filename: 'followup_notes.txt', contentType: 'text/plain', size: 3_812, status: 'COMPLETED', automated: 'BLOCK', final: 'BLOCK', score: 1, band: 'CRITICAL', owner: 'xiaomei-researcher', age: 760, findings: [demoFinding('PHONE_NUMBER', 'Telephone number detected', 'CRITICAL', 'direct-identifiers', 'Telephone-like text is not permitted in an output release.', 'matched_values_redacted=true')] }),
    build({ id: 'demo-block-nhs-number', project: 'UKB-DEMO-017', type: 'TABLE', description: 'Synthetic export containing a ten-digit health identifier pattern.', filename: 'linkage_ids.csv', size: 9_210, status: 'COMPLETED', automated: 'BLOCK', final: 'BLOCK', score: 1, band: 'CRITICAL', owner: 'ben-researcher', age: 1_380, findings: [demoFinding('NHS_NUMBER', 'Health identifier pattern detected', 'CRITICAL', 'direct-identifiers', 'A ten-digit health identifier pattern was detected.', 'matched_values_redacted=true')] }),
    build({ id: 'demo-block-quasi-identifiers', project: 'UKB-DEMO-033', type: 'TABLE', description: 'Synthetic row-level export containing postcode and date-of-birth fields.', filename: 'geography_linkage.csv', size: 43_200, status: 'COMPLETED', automated: 'BLOCK', final: 'BLOCK', score: 1, band: 'CRITICAL', owner: 'sarah-researcher', age: 1_860, findings: [demoFinding('SENSITIVE_COLUMN', 'Sensitive identifying columns', 'CRITICAL', 'quasi-identifiers', 'The combination of geography and birth-date fields presents a disclosure concern.', 'columns=postcode,date_of_birth; values_not_logged=true')] }),
    build({ id: 'demo-review-formula', project: 'UKB-DEMO-220', type: 'TABLE', description: 'Synthetic spreadsheet export containing formula-like cells.', filename: 'derived_metrics.csv', size: 7_980, status: 'AWAITING_REVIEW', automated: 'REVIEW', final: null, score: 0.55, band: 'HIGH', owner: 'other-researcher', age: 35, findings: [findings.formula] }),
    build({ id: 'demo-review-partial', project: 'UKB-DEMO-042', type: 'TABLE', description: 'Large synthetic table that exceeded the configured inspection window.', filename: 'large_summary.csv', size: 4_820_000, status: 'AWAITING_REVIEW', automated: 'REVIEW', final: null, score: 0.35, band: 'MODERATE', owner: 'xiaomei-researcher', age: 1_440, claimedBy: 'alex-reviewer', findings: [findings.partial] }),
    build({ id: 'demo-allow-figure', project: 'UKB-DEMO-101', type: 'FIGURE', description: 'Synthetic aggregate forest plot with non-identifying image metadata.', filename: 'forest_plot.png', contentType: 'image/png', size: 248_400, status: 'COMPLETED', automated: 'ALLOW', final: 'ALLOW', score: 0.05, band: 'LOW', owner: 'alex-researcher', age: 60, findings: [demoFinding('IMAGE_METADATA_PRESENT', 'Image metadata present', 'LOW', 'metadata', 'Non-location image metadata was found and recorded for transparency.', 'metadata_fields=software')] }),
    build({ id: 'demo-allow-report', project: 'UKB-DEMO-042', type: 'REPORT', description: 'Synthetic aggregate methods report with ordinary document metadata.', filename: 'analysis_report.pdf', contentType: 'application/pdf', size: 612_300, status: 'COMPLETED', automated: 'ALLOW', final: 'ALLOW', score: 0.05, band: 'LOW', owner: 'xiaomei-researcher', age: 900, findings: [demoFinding('PDF_METADATA_PRESENT', 'PDF metadata present', 'LOW', 'metadata', 'Document metadata was found and recorded for reviewer visibility.', 'metadata_fields=producer,creation_date')] }),
    build({ id: 'demo-manual-allow', project: 'UKB-DEMO-220', type: 'TABLE', description: 'Synthetic table manually allowed after a suppressed-cell revision.', filename: 'revised_subgroups.csv', size: 8_410, status: 'COMPLETED', automated: 'REVIEW', final: 'ALLOW', score: 0.55, band: 'HIGH', owner: 'other-researcher', age: 2_500, reviewer: 'xiaomei-reviewer', rationale: 'The revised output suppresses all counts below five.', findings: [findings.smallCell] }),
    build({ id: 'demo-manual-block', project: 'UKB-DEMO-088', type: 'TABLE', description: 'Synthetic free-text export manually blocked after reviewer inspection.', filename: 'narrative_export.csv', size: 26_600, status: 'COMPLETED', automated: 'REVIEW', final: 'BLOCK', score: 0.8, band: 'HIGH', owner: 'priya-researcher', age: 3_000, reviewer: 'xiaomei-reviewer', rationale: 'Narrative content remains row-level and cannot be safely released.', findings: [findings.freeText, findings.unique] }),
    build({ id: 'demo-allow-bom', project: 'UKB-DEMO-001', type: 'TABLE', description: 'Synthetic UTF-8 summary containing a byte-order mark and no release concern.', filename: 'unicode_summary.csv', size: 1_940, status: 'COMPLETED', automated: 'ALLOW', final: 'ALLOW', score: 0, band: 'LOW', owner: 'xiaomei-researcher', age: 15 }),
    build({ id: 'demo-block-signature', project: 'UKB-DEMO-101', type: 'REPORT', description: 'Synthetic file whose extension does not match its content signature.', filename: 'mislabelled_report.pdf', contentType: 'application/pdf', size: 5_220, status: 'COMPLETED', automated: 'BLOCK', final: 'BLOCK', score: 1, band: 'CRITICAL', owner: 'alex-researcher', age: 5_000, fileAvailable: false, findings: [demoFinding('CONTENT_SIGNATURE_MISMATCH', 'Content signature mismatch', 'CRITICAL', 'file-integrity', 'The declared file type does not match the detected content signature.', 'declared=pdf; detected=text')] }),
    build({ id: 'demo-review-multiple-unique', project: 'UKB-DEMO-042', type: 'TABLE', description: 'Synthetic table with multiple near-unique analytical columns.', filename: 'model_predictions.csv', size: 78_340, status: 'AWAITING_REVIEW', automated: 'REVIEW', final: null, score: 0.5, band: 'MODERATE', owner: 'xiaomei-researcher', age: 12, findings: [demoFinding('HIGH_UNIQUENESS_COLUMN', 'Multiple highly unique columns', 'MEDIUM', 'statistical-disclosure', 'Several columns are almost unique and may expose row-level records.', 'columns=prediction_id,score; uniqueness_ratio>=0.98')] }),
  ]
}

export const demoPolicy: Policy = {
  policy_version: DEMO_POLICY_VERSION,
  decision_logic: 'Highest configured action across all transparent findings.',
  small_cell_threshold: 5,
  max_rows_to_scan: 10_000,
  retention_days: 30,
  rules: [
    { code: 'DIRECT_IDENTIFIER_COLUMN', category: 'direct-identifiers', severity: 'CRITICAL', title: 'Direct identifier column', description: 'Participant-level identifier column.', default_action: 'BLOCK' },
    { code: 'CONTACT_INFORMATION', category: 'direct-identifiers', severity: 'CRITICAL', title: 'Contact information', description: 'Email, telephone or health-identifier pattern.', default_action: 'BLOCK' },
    { code: 'CONTENT_SIGNATURE_MISMATCH', category: 'file-integrity', severity: 'CRITICAL', title: 'Content signature mismatch', description: 'Declared file type differs from the detected signature.', default_action: 'BLOCK' },
    { code: 'SMALL_CELL', category: 'statistical-disclosure', severity: 'HIGH', title: 'Small aggregate cell', description: 'Aggregate count below the demonstration threshold.', default_action: 'REVIEW' },
    { code: 'FREE_TEXT_COLUMN', category: 'unstructured-content', severity: 'HIGH', title: 'Free-text column', description: 'Narrative content requires manual inspection.', default_action: 'REVIEW' },
    { code: 'SPREADSHEET_FORMULA', category: 'active-content', severity: 'HIGH', title: 'Spreadsheet formula', description: 'Formula-like content should be flattened before release.', default_action: 'REVIEW' },
    { code: 'HIGH_UNIQUENESS_COLUMN', category: 'statistical-disclosure', severity: 'MEDIUM', title: 'Highly unique column', description: 'High uniqueness may indicate row-level data.', default_action: 'REVIEW' },
    { code: 'PARTIAL_INSPECTION', category: 'inspection-coverage', severity: 'MEDIUM', title: 'Partial inspection', description: 'Only part of the output was inspected.', default_action: 'REVIEW' },
    { code: 'DOCUMENT_METADATA', category: 'metadata', severity: 'LOW', title: 'Document metadata', description: 'Non-critical metadata is recorded for transparency.', default_action: 'ALLOW' },
  ],
}
