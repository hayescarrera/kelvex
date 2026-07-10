/**
 * Site health score ring (0–100) — the category-standard rollup.
 * Green ≥85, amber ≥60, red below. Color never stands alone: the number
 * is always rendered inside the ring and exposed to screen readers.
 */
export default function HealthRing({ score, size = 44 }: { score: number; size?: number }) {
  const r = (size - 8) / 2
  const c = 2 * Math.PI * r
  const color = score >= 85 ? 'var(--success)' : score >= 60 ? 'var(--warning)' : 'var(--danger)'
  return (
    <span
      role="img"
      aria-label={`Health score ${score} out of 100`}
      style={{ position: 'relative', display: 'inline-grid', placeItems: 'center', width: size, height: size }}
    >
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border-subtle)" strokeWidth={4.5} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={color} strokeWidth={4.5} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - score / 100)}
          style={{ transition: 'stroke-dashoffset 320ms cubic-bezier(0.22, 1, 0.36, 1)' }}
        />
      </svg>
      <span
        className="num"
        style={{ position: 'absolute', fontWeight: 700, fontSize: size * 0.3, color }}
      >
        {score}
      </span>
    </span>
  )
}

/** Health formula shared by dashboard + facility views. Inputs are all
 * real API data; missing signals simply don't deduct. */
export function computeHealth(inputs: {
  criticalAlerts?: number
  highAlerts?: number
  zoneAlarms?: number
  openLeaks?: number
  leakRatePct?: number | null
}): number {
  let score = 100
  score -= (inputs.criticalAlerts ?? 0) * 25
  score -= (inputs.highAlerts ?? 0) * 10
  score -= (inputs.zoneAlarms ?? 0) * 8
  score -= (inputs.openLeaks ?? 0) * 12
  const rate = inputs.leakRatePct
  if (rate != null) score -= rate >= 20 ? 18 : rate >= 15 ? 8 : 0
  return Math.max(0, Math.round(score))
}
