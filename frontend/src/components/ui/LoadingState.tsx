import { Loader2 } from 'lucide-react'

interface LoadingStateProps {
  label?: string
  fullScreen?: boolean
  rows?: number
}

function SkeletonRows({ rows }: { rows: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-row">
          <div className="skeleton" style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0 }} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div className="skeleton skeleton-text" style={{ width: `${55 + (i % 3) * 15}%` }} />
            <div className="skeleton skeleton-text" style={{ width: `${30 + (i % 4) * 10}%`, opacity: 0.6 }} />
          </div>
          <div className="skeleton skeleton-text" style={{ width: 72 }} />
          <div className="skeleton skeleton-text" style={{ width: 56 }} />
        </div>
      ))}
    </>
  )
}

export default function LoadingState({ label, fullScreen, rows }: LoadingStateProps) {
  if (rows != null) {
    return <SkeletonRows rows={rows} />
  }

  if (fullScreen) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 10 }}>
        <Loader2 size={20} className="spin" style={{ color: 'var(--accent)' }} />
        {label && <span style={{ color: 'var(--text-secondary)', fontSize: 14 }}>{label}</span>}
      </div>
    )
  }

  return (
    <div className="loading-state">
      <Loader2 size={20} className="spin" style={{ color: 'var(--accent)' }} />
      {label && <span style={{ color: 'var(--text-secondary)', marginLeft: 8, fontSize: 13 }}>{label}</span>}
    </div>
  )
}
