import type { RiskBand } from '../types/api'

export function RiskBadge({ band, score }: { band: RiskBand; score: number }) {
  return (
    <span className={`risk-badge risk-badge--${band.toLowerCase()}`}>
      {band} · {Math.round(score * 100)}%
    </span>
  )
}
