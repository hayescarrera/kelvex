export default function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div style={{ color: 'var(--text-tertiary)', marginBottom: 6, fontSize: 11, fontWeight: 600 }}>
        {label}
      </div>
      {payload.map((p: any, i: number) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: p.color, flexShrink: 0 }} />
          <span style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>{p.name}:</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: 12 }}>
            {typeof p.value === 'number' && p.value > 100 ? p.value.toLocaleString() : p.value}
          </span>
        </div>
      ))}
    </div>
  )
}
