import { TrendingUp, TrendingDown } from 'lucide-react'
import type { ReactNode } from 'react'

interface StatCardProps {
  icon: ReactNode
  color: string
  value: string
  label: string
  delta?: string
  deltaLabel?: string
  deltaPositive?: boolean
}

export default function StatCard({ icon, color, value, label, delta, deltaLabel, deltaPositive }: StatCardProps) {
  return (
    <div className="stat-card">
      <div
        className="stat-icon"
        style={{ color, background: `color-mix(in srgb, ${color} 12%, transparent)` }}
      >
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
        {delta && (
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 3,
            marginTop: 6,
            fontSize: 11,
            fontWeight: 600,
            color: deltaPositive ? 'var(--success)' : 'var(--danger)',
          }}>
            {deltaPositive
              ? <TrendingUp size={11} />
              : <TrendingDown size={11} />}
            {delta}
            {deltaLabel && <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>&nbsp;{deltaLabel}</span>}
          </div>
        )}
      </div>
    </div>
  )
}
