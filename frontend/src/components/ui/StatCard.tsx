import type { ReactNode } from 'react'

interface StatCardProps {
  icon: ReactNode
  color: string
  value: string
  label: string
}

export default function StatCard({ icon, color, value, label }: StatCardProps) {
  return (
    <div className="stat-card">
      <div
        className="stat-icon"
        style={{ color, background: `color-mix(in srgb, ${color} 10%, transparent)` }}
      >
        {icon}
      </div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  )
}
