import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileLock2,
  Fingerprint,
  Lock,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Unlock,
  X,
} from 'lucide-react'
import { useState } from 'react'
import type {
  Actor,
  AuditVerification,
  SubmissionDetail,
  VerificationResult,
} from '../types/api'
import { DecisionBadge } from './DecisionBadge'
import { RiskBadge } from './RiskBadge'

interface DetailPanelProps {
  actor: Actor
  submission: SubmissionDetail
  busy: boolean
  onClose: () => void
  onReview: (id: string, decision: 'ALLOW' | 'BLOCK', rationale: string, version: number) => Promise<void>
  onRecheck: (id: string) => Promise<void>
  onDownload: (id: string, filename: string) => Promise<void>
  onClaim: (id: string) => Promise<void>
  onReleaseClaim: (id: string) => Promise<void>
  onDeleteFile: (id: string) => Promise<void>
  onVerify: (id: string) => Promise<{ report: VerificationResult; audit: AuditVerification }>
}

const rationaleTemplates = [
  'The flagged small cell has been suppressed in the revised release output, and the remaining table contains aggregate statistics only.',
  'The disclosure concern remains unresolved, so release is blocked until the researcher submits a revised output.',
]

export function DetailPanel({
  actor, submission, busy, onClose, onReview, onRecheck, onDownload,
  onClaim, onReleaseClaim, onDeleteFile, onVerify,
}: DetailPanelProps) {
  const [rationale, setRationale] = useState('')
  const [verification, setVerification] = useState<{
    report: VerificationResult
    audit: AuditVerification
  } | null>(null)
  const canReview = actor.role === 'reviewer' || actor.role === 'admin'
  const ownsClaim = submission.claimed_by === actor.name
  const mayRecordDecision = actor.role === 'admin' || ownsClaim

  async function verify() {
    try {
      setVerification(await onVerify(submission.id))
    } catch {
      setVerification(null)
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true"
        aria-label={`Submission detail for ${submission.filename}`}
        onMouseDown={(event) => event.stopPropagation()}>
        <div className="drawer__header">
          <div><p className="eyebrow">Submission detail</p><h2>{submission.filename}</h2>
            <span className="drawer-subtitle">{submission.project_code} · {submission.output_type} · v{submission.row_version}</span></div>
          <div className="drawer-actions">
            <button className="icon-button" onClick={() => void onDownload(submission.id, submission.filename)} title="Download signed report" disabled={busy}><Download /></button>
            {canReview && <button className="icon-button" onClick={() => void onRecheck(submission.id)} title="Run checks again" disabled={busy || !submission.file_available}><RefreshCw className={busy ? 'spin' : ''} /></button>}
            <button className="icon-button" onClick={onClose} aria-label="Close detail panel"><X /></button>
          </div>
        </div>

        <div className="workflow-strip">
          <div className="workflow-step workflow-step--done"><span>1</span><strong>Submitted</strong></div><i />
          <div className="workflow-step workflow-step--done"><span>2</span><strong>Scanned</strong></div><i />
          <div className={`workflow-step ${submission.status === 'AWAITING_REVIEW' ? 'workflow-step--active' : 'workflow-step--done'}`}>
            <span>3</span><strong>{submission.status === 'AWAITING_REVIEW' ? 'Review' : 'Decided'}</strong></div>
        </div>

        <div className="decision-summary decision-summary--four">
          <div><span>Automated</span><DecisionBadge decision={submission.automated_decision} /></div>
          <div><span>Final</span><DecisionBadge decision={submission.final_decision} /></div>
          <div><span>Risk</span><RiskBadge band={submission.risk_band} score={submission.risk_score} /></div>
          <div><span>File</span><strong>{submission.file_available ? 'IN QUARANTINE' : 'RETIRED'}</strong></div>
        </div>

        <section className="drawer-section context-card">
          <div><span>Purpose</span><p>{submission.output_description}</p></div>
          <div><span>Submitted by</span><strong>{submission.submitted_by}</strong></div>
          <div><span>Current claim</span><strong>{submission.claimed_by ?? 'Unclaimed'}</strong></div>
          <div><span>Policy</span><code>{submission.policy_version}</code></div>
        </section>

        {submission.status === 'AWAITING_REVIEW' && canReview && (
          <section className="drawer-section claim-card">
            <div><Lock aria-hidden="true" /><div><h3>Review ownership</h3>
              <p>Claiming prevents two reviewers from recording conflicting decisions.</p></div></div>
            {submission.claimed_by === null ?
              <button className="secondary-button" disabled={busy} onClick={() => void onClaim(submission.id)}><Lock size={16} /> Claim review</button> :
              <div className="claim-card__status"><span>Claimed by <strong>{submission.claimed_by}</strong></span>
                {(ownsClaim || actor.role === 'admin') && <button disabled={busy} onClick={() => void onReleaseClaim(submission.id)}><Unlock size={15} /> Release</button>}</div>}
          </section>
        )}

        <section className="drawer-section">
          <div className="section-heading-row"><h3>Policy findings</h3><span>{submission.findings.length} detected</span></div>
          {submission.findings.length === 0 ? (
            <div className="finding finding--safe"><CheckCircle2 /><div><strong>No configured finding</strong>
              <p>The current deterministic checks found no configured release concern.</p></div></div>
          ) : submission.findings.map((finding, index) => (
            <div className={`finding finding--${finding.severity.toLowerCase()}`} key={`${finding.code}-${index}`}>
              {finding.severity === 'CRITICAL' ? <ShieldAlert /> : <AlertTriangle />}
              <div><div className="finding-heading"><strong>{finding.title}</strong><span>{finding.category}</span></div>
                <code className="finding-code">{finding.code}</code><p>{finding.message}</p>
                {finding.evidence && <code>{finding.evidence}</code>}</div>
            </div>
          ))}
        </section>

        {submission.status === 'AWAITING_REVIEW' && canReview && (
          <section className="drawer-section review-form">
            <div className="section-heading-row"><h3>Record manual decision</h3>
              <span>{mayRecordDecision ? 'Rationale required' : 'Claim this item first'}</span></div>
            <textarea className="text-input" rows={5} value={rationale}
              disabled={!mayRecordDecision}
              placeholder="Explain the evidence, mitigation and final release decision."
              onChange={(event) => setRationale(event.target.value)} />
            <div className="template-buttons">{rationaleTemplates.map((template) =>
              <button key={template} disabled={!mayRecordDecision} onClick={() => setRationale(template)}>
                {template.includes('suppressed') ? 'Use mitigation example' : 'Use block example'}
              </button>)}</div>
            <div className="review-actions">
              <button disabled={busy || !mayRecordDecision || rationale.length < 20} className="danger-button"
                onClick={() => void onReview(submission.id, 'BLOCK', rationale, submission.row_version)}>Block release</button>
              <button disabled={busy || !mayRecordDecision || rationale.length < 20} className="primary-button"
                onClick={() => void onReview(submission.id, 'ALLOW', rationale, submission.row_version)}>Allow release</button>
            </div>
          </section>
        )}

        {submission.review_rationale && (
          <section className="drawer-section final-review"><div className="section-heading-row"><h3>Recorded review</h3>
            <DecisionBadge decision={submission.final_decision} /></div><p>{submission.review_rationale}</p><span>{submission.reviewer}</span></section>
        )}

        <section className="drawer-section verification-card">
          <div className="section-heading-row"><h3>Integrity verification</h3>
            <button className="text-button" disabled={busy} onClick={() => void verify()}><Fingerprint size={15} /> Verify now</button></div>
          <p>Decision reports use HMAC signatures. Audit events are linked through SHA-256 hashes.</p>
          {verification && <div className="verification-grid">
            <div className={verification.report.signature_valid ? 'verification-ok' : 'verification-fail'}>
              <ShieldCheck /><span>Report signature</span><strong>{verification.report.signature_valid ? 'VALID' : 'INVALID'}</strong></div>
            <div className={verification.audit.valid ? 'verification-ok' : 'verification-fail'}>
              <FileLock2 /><span>Audit chain</span><strong>{verification.audit.valid ? 'VALID' : 'INVALID'}</strong></div>
          </div>}
        </section>

        <section className="drawer-section"><h3>Audit history</h3><div className="timeline">
          {submission.audit_events.map((event, index) => <div className="timeline__item" key={`${event.event_type}-${index}`}>
            <ShieldCheck size={16} /><div><strong>{event.event_type.replaceAll('_', ' ')}</strong><p>{event.detail}</p>
              <span>{event.actor} · {new Date(event.created_at).toLocaleString()}</span>
              <code className="audit-hash">{event.event_hash.slice(0, 18)}…</code></div></div>)}
        </div></section>

        {actor.role === 'admin' && submission.file_available && (
          <section className="drawer-section retention-card"><div><Trash2 /><div><h3>Retention operation</h3>
            <p>Delete quarantined bytes while retaining metadata, decisions and audit evidence.</p></div></div>
            <button className="danger-button" disabled={busy} onClick={() => void onDeleteFile(submission.id)}><Trash2 size={15} /> Retire file content</button>
          </section>
        )}

        <section className="drawer-section metadata-grid">
          <div><span>SHA-256</span><code>{submission.sha256}</code></div>
          <div><span>Content type</span><strong>{submission.content_type}</strong></div>
          <div><span>Submission ID</span><code>{submission.id}</code></div>
          <div><span>Row version</span><code>{submission.row_version}</code></div>
        </section>
      </aside>
    </div>
  )
}
