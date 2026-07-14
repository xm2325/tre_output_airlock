import { BookOpenCheck, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Policy } from '../types/api'
import { DecisionBadge } from './DecisionBadge'

export function PolicyCatalogue({ policy }: { policy: Policy | null }) {
  const [expanded, setExpanded] = useState(false)
  const categories = useMemo(() => {
    if (!policy) return []
    return [...new Set(policy.rules.map((rule) => rule.category))]
  }, [policy])

  return (
    <section className="panel policy-panel">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Policy as code</p>
          <h2>Versioned rule catalogue</h2>
        </div>
        <BookOpenCheck aria-hidden="true" />
      </div>

      {!policy ? (
        <p className="empty-copy">Policy metadata is unavailable.</p>
      ) : (
        <>
          <div className="policy-version-card">
            <ShieldCheck aria-hidden="true" />
            <div>
              <span>Active policy</span>
              <strong>{policy.policy_version}</strong>
            </div>
          </div>
          <p className="policy-logic">{policy.decision_logic}</p>
          <div className="policy-facts">
            <div><span>Rules</span><strong>{policy.rules.length}</strong></div>
            <div><span>Categories</span><strong>{categories.length}</strong></div>
            <div><span>Small-cell threshold</span><strong>&lt; {policy.small_cell_threshold}</strong></div>
            <div><span>CSV scan cap</span><strong>{policy.max_rows_to_scan.toLocaleString()}</strong></div>
          </div>
          <button className="text-button" onClick={() => setExpanded((value) => !value)}>
            {expanded ? 'Hide rule catalogue' : 'Inspect rule catalogue'}
          </button>
          {expanded && (
            <div className="rule-catalogue">
              {policy.rules.map((rule) => (
                <article key={rule.code}>
                  <div>
                    <code>{rule.code}</code>
                    <span>{rule.category}</span>
                  </div>
                  <strong>{rule.title}</strong>
                  <p>{rule.description}</p>
                  <div className="rule-meta">
                    <span className={`severity severity--${rule.severity.toLowerCase()}`}>{rule.severity}</span>
                    <DecisionBadge decision={rule.default_action} />
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}
