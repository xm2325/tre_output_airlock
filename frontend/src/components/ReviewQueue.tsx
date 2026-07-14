import { ChevronRight, Clock3, Inbox, LockKeyhole } from 'lucide-react'
import { formatAge } from '../lib/query'
import type { Actor, SubmissionSummary } from '../types/api'
import { RiskBadge } from './RiskBadge'

interface ReviewQueueProps {
  actor: Actor
  rows: SubmissionSummary[]
  onSelect: (id: string) => void
}

export function ReviewQueue({ actor, rows, onSelect }: ReviewQueueProps) {
  if (actor.role === 'researcher') {
    return (
      <section className="panel queue-panel restricted-panel">
        <LockKeyhole aria-hidden="true" />
        <div><p className="eyebrow">Separation of duties</p><h2>Reviewer queue restricted</h2>
          <p>Researchers can view their own submissions but cannot inspect or resolve the shared review queue.</p></div>
      </section>
    )
  }

  return (
    <section className="panel queue-panel">
      <div className="panel__header">
        <div><p className="eyebrow">Human control</p><h2>Risk-prioritised review queue</h2></div>
        <span className="record-count">{rows.length} waiting</span>
      </div>
      {rows.length === 0 ? (
        <div className="queue-empty"><Inbox /><div><strong>No outputs are waiting</strong>
          <p>REVIEW items appear here, ordered by risk and age.</p></div></div>
      ) : (
        <div className="queue-list">
          {rows.slice(0, 7).map((row) => (
            <button className="queue-row" key={row.id} onClick={() => onSelect(row.id)}>
              <div><strong>{row.filename}</strong><span>{row.project_code} · {row.submitted_by}</span></div>
              <RiskBadge band={row.risk_band} score={row.risk_score} />
              <span className="claim-state">{row.claimed_by ?? 'Unclaimed'}</span>
              <span className="queue-age"><Clock3 size={14} /> {formatAge(row.created_at)}</span>
              <ChevronRight size={18} />
            </button>
          ))}
        </div>
      )}
    </section>
  )
}
