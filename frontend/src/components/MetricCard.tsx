import type { ReactNode } from 'react'

interface MetricCardProps {
  label: string
  value: number | string
  helper: string
  icon: ReactNode
}

export function MetricCard({ label, value, helper, icon }: MetricCardProps) {
  return (
    <article className="metric-card">
      <div className="metric-card__icon">{icon}</div>
      <div>
        <p className="metric-card__label">{label}</p>
        <strong className="metric-card__value">{value}</strong>
        <p className="metric-card__helper">{helper}</p>
      </div>
    </article>
  )
}
