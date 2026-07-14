import { Activity, AlertTriangle, Gauge, ListChecks, TimerReset } from 'lucide-react'
import type { Metrics } from '../types/api'

const percent = (value: number) => `${Math.round(value * 100)}%`
const minutes = (value: number) => value < 60 ? `${Math.round(value)}m` : `${(value / 60).toFixed(1)}h`

export function OperationsPanel({ metrics }: { metrics: Metrics }) {
  const total = Math.max(metrics.total, 1)
  const rows = [
    { label: 'Automated allow', value: metrics.automated_allow, className: 'allow' },
    { label: 'Manual review', value: metrics.automated_review, className: 'review' },
    { label: 'Automated block', value: metrics.automated_block, className: 'block' },
  ]
  return (
    <section className="panel operations-panel">
      <div className="panel__header"><div><p className="eyebrow">Operations</p><h2>Workload and service risk</h2></div><Gauge /></div>
      <div className="operations-summary operations-summary--five">
        <div><Activity /><span>Automation</span><strong>{percent(metrics.automation_rate)}</strong></div>
        <div><ListChecks /><span>Review complete</span><strong>{percent(metrics.review_completion_rate)}</strong></div>
        <div><AlertTriangle /><span>Manual blocks</span><strong>{percent(metrics.manual_block_rate)}</strong></div>
        <div><TimerReset /><span>Oldest queue</span><strong>{minutes(metrics.oldest_queue_age_minutes)}</strong></div>
        <div><Gauge /><span>Average risk</span><strong>{percent(metrics.average_risk)}</strong></div>
      </div>
      <div className="decision-bars">
        {rows.map((row) => <div className="decision-bar" key={row.label}>
          <div className="decision-bar__label"><span>{row.label}</span><strong>{row.value}</strong></div>
          <div className="decision-bar__track"><span className={`decision-bar__fill decision-bar__fill--${row.className}`}
            style={{ width: `${Math.max((row.value / total) * 100, row.value ? 4 : 0)}%` }} /></div>
        </div>)}
      </div>
      <div className="top-findings"><div className="subheading-row"><h3>Most frequent findings</h3>
        <span>{metrics.claimed_reviews} claimed · {metrics.deleted_files} files retired</span></div>
        {metrics.top_findings.length === 0 ? <p className="empty-copy">Run the sample benchmark to populate rule frequencies.</p> :
          <ol>{metrics.top_findings.map((finding) => <li key={finding.code}><code>{finding.code}</code><strong>{finding.count}</strong></li>)}</ol>}
      </div>
    </section>
  )
}
