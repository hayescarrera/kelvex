import { Loader2 } from 'lucide-react'

interface LoadingStateProps {
  label?: string
  fullScreen?: boolean
}

export default function LoadingState({ label, fullScreen }: LoadingStateProps) {
  if (fullScreen) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 10 }}>
        <Loader2 size={20} className="spin" style={{ color: 'var(--accent)' }} />
        {label && <span style={{ color: 'var(--text-secondary)' }}>{label}</span>}
      </div>
    )
  }
  return (
    <div className="loading-state">
      <Loader2 size={20} className="spin" style={{ color: 'var(--accent)' }} />
      {label && <span>{label}</span>}
    </div>
  )
}
