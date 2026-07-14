import type { Decision } from '../types/api'

export function DecisionBadge({ decision }: { decision: Decision | null }) {
  const value = decision ?? 'PENDING'
  return <span className={`decision decision--${value.toLowerCase()}`}>{value}</span>
}
