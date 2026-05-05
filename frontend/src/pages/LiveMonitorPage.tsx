import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Activity, WifiOff, AlertTriangle, Zap,
  Gauge, Radio, Building2, ChevronDown, ChevronRight, Wifi,
  Sliders, Power, Cpu, X, Thermometer, ToggleLeft, ToggleRight,
  ChevronUp, Send,
} from 'lucide-react'
import toast from 'react-hot-toast'
import PageHeader from '../components/ui/PageHeader'
import { api } from '../lib/api'
import type {
  LiveMonitorResponse, LiveCompressor, LiveFacility, ControlCapabilities,
  ControlActionSchema, ControlParamDef,
} from '../lib/api'

const POLL_INTERVAL = 5000 // 5 seconds

// ── Metric definitions ──────────────────────────────
const METRICS: {
  key: keyof LiveCompressor['readings']
  label: string
  unit: string
  warn?: number
  danger?: number
  warnLow?: number
  precision?: number
}[] = [
  { key: 'discharge_pressure_psi', label: 'Discharge', unit: 'psi', warn: 200, danger: 250 },
  { key: 'suction_pressure_psi', label: 'Suction', unit: 'psi', warnLow: 15 },
  { key: 'oil_temp_f', label: 'Oil Temp', unit: '°F', warn: 160, danger: 180 },
  { key: 'bearing_temp_f', label: 'Bearing', unit: '°F', warn: 180, danger: 200 },
  { key: 'vibration_ips', label: 'Vibration', unit: 'in/s', warn: 0.2, danger: 0.35, precision: 3 },
  { key: 'amp_draw', label: 'Amps', unit: 'A' },
  { key: 'kw', label: 'Power', unit: 'kW' },
  { key: 'slide_valve_pct', label: 'Load', unit: '%' },
  { key: 'rpm', label: 'Speed', unit: 'RPM', precision: 0 },
]

function metricLevel(m: typeof METRICS[0], val: number): 'normal' | 'warn' | 'danger' {
  if (m.danger != null && val >= m.danger) return 'danger'
  if (m.warn != null && val >= m.warn) return 'warn'
  if (m.warnLow != null && val <= m.warnLow) return 'warn'
  return 'normal'
}

function timeAgo(isoStr: string | null): string {
  if (!isoStr) return 'never'
  const secs = Math.round((Date.now() - new Date(isoStr).getTime()) / 1000)
  if (secs < 60) return `${secs}s ago`
  if (secs < 3600) return `${Math.round(secs / 60)}m ago`
  return `${Math.round(secs / 3600)}h ago`
}

// ── Main page ────────────────────────────────────────
export default function LiveMonitorPage() {
  const [data, setData] = useState<LiveMonitorResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = async () => {
    try {
      const res = await api.getLiveMonitor()
      setData(res)
      setLastUpdate(new Date())
      setError(null)
    } catch (e) {
      setError('Failed to fetch live data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    intervalRef.current = setInterval(fetchData, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  if (loading && !data) {
    return (
      <div>
        <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-muted)' }}>
          <Activity size={32} style={{ animation: 'spin 1s linear infinite', marginBottom: 12 }} />
          <div>Connecting to live telemetry...</div>
        </div>
      </div>
    )
  }

  const summary = data?.org_summary

  return (
    <div>
      <PageHeader
        title="Live Monitor"
        subtitle="Real-time compressor telemetry across all sites"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <LivePulse />
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {lastUpdate ? `Updated ${timeAgo(lastUpdate.toISOString())}` : ''}
          </span>
          {error && <span style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</span>}
        </div>
      </PageHeader>

      {/* Org-wide stats */}
      {summary && (
        <div className="stat-grid stagger">
          <OrgStat icon={<Building2 size={18} />} color="var(--accent)" value={summary.total_facilities} label="Sites" />
          <OrgStat icon={<Activity size={18} />} color="var(--text)" value={summary.total_compressors} label="Compressors" />
          <OrgStat icon={<Zap size={18} />} color="var(--success)" value={summary.running} label="Running" />
          <OrgStat
            icon={<AlertTriangle size={18} />}
            color={summary.in_alarm > 0 ? 'var(--danger)' : 'var(--success)'}
            value={summary.in_alarm}
            label="In Alarm"
          />
          <OrgStat icon={<Gauge size={18} />} color="var(--warning)" value={summary.total_kw ? `${summary.total_kw}` : '—'} label="Total kW" />
          <OrgStat
            icon={summary.offline_agents > 0 ? <WifiOff size={18} /> : <Wifi size={18} />}
            color={summary.offline_agents > 0 ? 'var(--danger)' : 'var(--success)'}
            value={summary.offline_agents}
            label="Offline Agents"
          />
        </div>
      )}

      {/* Facility sections */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginTop: 16 }}>
        {data?.facilities.map(fac => (
          <FacilitySection key={fac.facility_id} facility={fac} />
        ))}
      </div>

      {data && data.facilities.length === 0 && (
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <Radio size={28} style={{ color: 'var(--text-muted)', marginBottom: 8 }} />
          <div style={{ fontWeight: 600, marginBottom: 4 }}>No compressors connected yet</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            Register an edge agent and run a network scan to discover compressors.
          </div>
        </div>
      )}
    </div>
  )
}

// ── Org stat card ─────────────────────────────────────
function OrgStat({ icon, color, value, label }: { icon: React.ReactNode; color: string; value: string | number; label: string }) {
  return (
    <div className="stat-card">
      <div className="stat-icon" style={{ color, background: `color-mix(in srgb, ${color} 10%, transparent)` }}>
        {icon}
      </div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  )
}

// ── Live pulse indicator ──────────────────────────────
function LivePulse() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 8, height: 8, borderRadius: '50%', background: 'var(--success)',
        animation: 'pulse 2s ease-in-out infinite',
      }} />
      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--success)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
        Live
      </span>
    </div>
  )
}

// ── Facility section ──────────────────────────────────
function FacilitySection({ facility }: { facility: LiveFacility }) {
  const [expanded, setExpanded] = useState(true)

  const agentColor = facility.agent_status === 'connected'
    ? 'var(--success)'
    : facility.agent_status === 'stale'
    ? 'var(--warning)'
    : 'var(--danger)'

  const agentLabel = facility.agent_status === 'connected'
    ? 'Agent Online'
    : facility.agent_status === 'stale'
    ? 'Agent Stale'
    : 'Agent Offline'

  return (
    <div className="card" style={{ overflow: 'visible' }}>
      {/* Facility header */}
      <div
        className="card-body"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', padding: '14px 18px' }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          <Building2 size={16} style={{ color: 'var(--accent)' }} />
          <span style={{ fontWeight: 600, fontSize: 14 }}>{facility.facility_name}</span>
          {facility.location && (
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{facility.location}</span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: agentColor, display: 'inline-block' }} />
            <span style={{ color: agentColor }}>{agentLabel}</span>
          </span>
          <span style={{ color: 'var(--text-muted)' }}>
            {facility.running}/{facility.total_compressors} running
          </span>
          {facility.total_kw != null && (
            <span style={{ color: 'var(--warning)', fontWeight: 600 }}>{facility.total_kw} kW</span>
          )}
          {facility.in_alarm > 0 && (
            <span style={{ color: 'var(--danger)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 3 }}>
              <AlertTriangle size={12} /> {facility.in_alarm} alarm{facility.in_alarm > 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      {/* Compressor grid */}
      {expanded && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))',
          gap: 12,
          padding: '0 18px 18px',
        }}>
          {facility.compressors.map(comp => (
            <CompressorCard key={comp.id} compressor={comp} facilityId={String(facility.facility_id)} />
          ))}
          {facility.compressors.length === 0 && (
            <div style={{ padding: 20, color: 'var(--text-muted)', fontSize: 13, gridColumn: '1 / -1', textAlign: 'center' }}>
              No compressors linked to this site yet. Run a network scan from Edge Agents.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Compressor card ───────────────────────────────────
function CompressorCard({ compressor: c, facilityId }: { compressor: LiveCompressor; facilityId: string }) {
  const [showControl, setShowControl] = useState(false)
  const isRunning = c.state === 'running' || c.readings.running === true
  const isAlarm = c.state === 'alarm' || c.anomalies.length > 0
  const borderColor = isAlarm ? 'var(--danger)' : c.data_stale ? 'var(--border)' : 'var(--border)'

  return (
    <div style={{
      background: 'var(--card-bg)',
      border: `1px solid ${borderColor}`,
      borderRadius: 10,
      overflow: 'hidden',
      opacity: c.data_stale && !isRunning ? 0.7 : 1,
      boxShadow: isAlarm ? '0 0 12px rgba(239,68,68,0.15)' : undefined,
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderBottom: '1px solid var(--border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: isAlarm ? 'var(--danger)' : isRunning ? 'var(--success)' : 'var(--text-muted)',
            animation: isRunning && !isAlarm ? 'pulse 2s infinite' : undefined,
          }} />
          <span style={{ fontWeight: 600, fontSize: 13 }}>{c.name}</span>
          {c.tag && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{c.tag}</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {c.health_score != null && (
            <HealthBadge score={c.health_score} />
          )}
          <StatusBadge state={isAlarm ? 'alarm' : isRunning ? 'running' : c.state} />
        </div>
      </div>

      {/* Metrics grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 1,
        background: 'var(--border)',
      }}>
        {METRICS.map(m => {
          const val = c.readings[m.key]
          if (val == null) return null
          const numVal = typeof val === 'boolean' ? (val ? 1 : 0) : val as number
          const level = metricLevel(m, numVal)
          return (
            <div key={m.key} style={{ background: 'var(--card-bg)', padding: '8px 10px' }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.3 }}>
                {m.label}
              </div>
              <div style={{
                fontSize: 15, fontWeight: 600, marginTop: 2,
                fontVariantNumeric: 'tabular-nums',
                color: level === 'danger' ? 'var(--danger)' : level === 'warn' ? 'var(--warning)' : 'var(--text)',
              }}>
                {numVal.toFixed(m.precision ?? 1)}
                <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 2 }}>{m.unit}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Anomaly bar */}
      {c.anomalies.length > 0 && (
        <div style={{ padding: '6px 14px', background: 'color-mix(in srgb, var(--danger) 8%, transparent)', fontSize: 11, color: 'var(--danger)' }}>
          {c.anomalies.map((a, i) => (
            <span key={i}>
              {i > 0 && ' · '}
              {a.type.replace(/_/g, ' ')}: {a.value.toFixed(1)} (limit: {a.threshold})
            </span>
          ))}
        </div>
      )}

      {/* Footer with control button */}
      <div style={{
        padding: '8px 14px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: 11,
        color: 'var(--text-muted)',
      }}>
        <span>
          {c.manufacturer && `${c.manufacturer} `}
          {c.model && c.model}
          {c.hp && ` · ${c.hp} HP`}
          {c.refrigerant && ` · ${c.refrigerant}`}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ color: c.data_stale ? 'var(--warning)' : 'var(--text-muted)' }}>
            {c.data_stale ? '⚠ ' : ''}{timeAgo(c.readings.recorded_at)}
          </span>
          <button
            onClick={() => setShowControl(!showControl)}
            style={{
              background: 'var(--bg-secondary)', border: '1px solid var(--border)',
              borderRadius: 6, padding: '3px 8px', fontSize: 11, cursor: 'pointer',
              color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 4,
            }}
          >
            <Sliders size={11} /> Control
          </button>
        </div>
      </div>

      {/* Inline control panel */}
      {showControl && (
        <CompressorControlPanel compressorId={c.id} compressorName={c.name} facilityId={facilityId} onClose={() => setShowControl(false)} />
      )}
    </div>
  )
}

// ── Helper components ─────────────────────────────────
function StatusBadge({ state }: { state: string }) {
  const colors: Record<string, { bg: string; fg: string }> = {
    running: { bg: 'color-mix(in srgb, var(--success) 12%, transparent)', fg: 'var(--success)' },
    alarm: { bg: 'color-mix(in srgb, var(--danger) 12%, transparent)', fg: 'var(--danger)' },
    standby: { bg: 'color-mix(in srgb, var(--text-muted) 12%, transparent)', fg: 'var(--text-muted)' },
    maintenance: { bg: 'color-mix(in srgb, var(--warning) 12%, transparent)', fg: 'var(--warning)' },
  }
  const c = colors[state] || colors.standby
  return (
    <span style={{
      padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
      background: c.bg, color: c.fg, textTransform: 'capitalize',
    }}>
      {state}
    </span>
  )
}

// ── Schema-driven parameter input ────────────────
function ParamInput({
  name,
  def,
  value,
  onChange,
}: {
  name: string
  def: ControlParamDef
  value: unknown
  onChange: (name: string, val: unknown) => void
}) {
  const labelStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)' }
  const valStyle: React.CSSProperties = { fontSize: 13, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }

  if (def.type === 'slider') {
    const numVal = (value as number) ?? def.default ?? def.min ?? 0
    return (
      <div style={{ marginBottom: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <label style={labelStyle}>{def.label}</label>
          <span style={valStyle}>{numVal}{def.unit ? ` ${def.unit}` : ''}</span>
        </div>
        <input
          type="range"
          min={def.min ?? 0} max={def.max ?? 100} step={def.step ?? 1}
          value={numVal}
          onChange={e => onChange(name, Number(e.target.value))}
          style={{ width: '100%', accentColor: 'var(--accent)' }}
        />
      </div>
    )
  }

  if (def.type === 'number') {
    const numVal = (value as number) ?? def.default ?? def.min ?? 0
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={{ ...labelStyle, display: 'block', marginBottom: 4 }}>
          {def.label}
          {def.description && <span style={{ fontWeight: 400, marginLeft: 6, opacity: 0.7 }}>{def.description}</span>}
        </label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="number"
            min={def.min} max={def.max} step={def.step ?? 1}
            value={numVal}
            onChange={e => onChange(name, Number(e.target.value))}
            style={{
              width: 80, padding: '4px 8px', fontSize: 13, fontWeight: 600,
              border: '1px solid var(--border)', borderRadius: 6,
              background: 'var(--bg-secondary)', color: 'var(--text)',
              fontVariantNumeric: 'tabular-nums',
            }}
          />
          {def.unit && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{def.unit}</span>}
          {def.min != null && def.max != null && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 'auto' }}>
              {def.min}–{def.max}
            </span>
          )}
        </div>
      </div>
    )
  }

  if (def.type === 'select') {
    const strVal = (value as string) ?? (def.default as string) ?? ''
    return (
      <div style={{ marginBottom: 10 }}>
        <label style={{ ...labelStyle, display: 'block', marginBottom: 4 }}>{def.label}</label>
        <select
          value={strVal}
          onChange={e => onChange(name, e.target.value)}
          style={{
            padding: '5px 10px', fontSize: 12, fontWeight: 600,
            border: '1px solid var(--border)', borderRadius: 6,
            background: 'var(--bg-secondary)', color: 'var(--text)',
            width: '100%', cursor: 'pointer',
          }}
        >
          {def.options?.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
    )
  }

  if (def.type === 'toggle') {
    const boolVal = (value as boolean) ?? (def.default as boolean) ?? false
    return (
      <div
        style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
        onClick={() => onChange(name, !boolVal)}
      >
        {boolVal ? <ToggleRight size={22} style={{ color: 'var(--accent)' }} /> : <ToggleLeft size={22} style={{ color: 'var(--text-muted)' }} />}
        <span style={{ fontSize: 12, color: boolVal ? 'var(--text)' : 'var(--text-muted)', fontWeight: 600 }}>{def.label}</span>
        {def.description && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{def.description}</span>}
      </div>
    )
  }

  return null
}

// ── Action section (one schema block) ────────────
const ACTION_ICONS: Record<string, React.ReactNode> = {
  sliders: <Sliders size={13} />,
  gauge: <Gauge size={13} />,
  power: <Power size={13} />,
  snowflake: <Cpu size={13} />,
  zap: <Zap size={13} />,
  thermometer: <Thermometer size={13} />,
}

function ActionSection({
  actionKey,
  schema,
  onSend,
  sending,
}: {
  actionKey: string
  schema: ControlActionSchema
  onSend: (actionKey: string, params: Record<string, unknown>) => Promise<void>
  sending: string | null
}) {
  const [expanded, setExpanded] = useState(false)
  const [params, setParams] = useState<Record<string, unknown>>(() => {
    const defaults: Record<string, unknown> = {}
    for (const [k, def] of Object.entries(schema.params)) {
      defaults[k] = def.default
    }
    return defaults
  })

  const handleChange = useCallback((name: string, val: unknown) => {
    setParams(prev => ({ ...prev, [name]: val }))
  }, [])

  const handleSend = async () => {
    await onSend(actionKey, params)
  }

  // Filter visible params based on visible_when conditions
  const visibleParams = Object.entries(schema.params).filter(([, def]) => {
    if (!def.visible_when) return true
    return Object.entries(def.visible_when).every(([field, expected]) => params[field] === expected)
  })

  const icon = schema.icon ? ACTION_ICONS[schema.icon] || <Sliders size={13} /> : <Sliders size={13} />
  const isSending = sending === actionKey

  const sectionColors: Record<string, { bg: string; fg: string }> = {
    capacity: { bg: 'color-mix(in srgb, var(--accent) 8%, transparent)', fg: 'var(--accent)' },
    suction_setpoint: { bg: 'color-mix(in srgb, var(--accent) 8%, transparent)', fg: 'var(--accent)' },
    start_stop: { bg: 'color-mix(in srgb, var(--warning) 8%, transparent)', fg: 'var(--warning)' },
    defrost: { bg: 'color-mix(in srgb, var(--info, #3b82f6) 8%, transparent)', fg: 'var(--info, #3b82f6)' },
    demand_response: { bg: 'color-mix(in srgb, var(--danger) 8%, transparent)', fg: 'var(--danger)' },
    zone_setpoint: { bg: 'color-mix(in srgb, var(--success) 8%, transparent)', fg: 'var(--success)' },
  }
  const colors = sectionColors[actionKey] || { bg: 'color-mix(in srgb, var(--accent) 8%, transparent)', fg: 'var(--accent)' }

  return (
    <div style={{ borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', marginBottom: 8 }}>
      {/* Section header — click to expand */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '8px 12px', border: 'none', cursor: 'pointer',
          background: expanded ? colors.bg : 'var(--bg-secondary)',
          color: expanded ? colors.fg : 'var(--text)',
          fontSize: 12, fontWeight: 700,
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {icon}
          {schema.label}
        </span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {/* Expanded params form */}
      {expanded && (
        <div style={{ padding: '12px', background: 'var(--card-bg)' }}>
          {schema.description && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10 }}>
              {schema.description}
            </div>
          )}

          {visibleParams.map(([name, def]) => (
            <ParamInput key={name} name={name} def={def} value={params[name]} onChange={handleChange} />
          ))}

          {/* Check for required toggle (confirm) */}
          {(() => {
            const confirmDef = schema.params['confirm']
            if (confirmDef?.required && !params['confirm']) {
              return (
                <div style={{ fontSize: 11, color: 'var(--warning)', marginBottom: 8 }}>
                  Toggle "Confirm" above to enable this action.
                </div>
              )
            }
            return null
          })()}

          <button
            onClick={handleSend}
            disabled={isSending || (schema.params['confirm']?.required === true && !params['confirm'])}
            style={{
              width: '100%', padding: '8px', border: 'none', borderRadius: 6,
              background: colors.fg, color: '#fff', fontSize: 12, fontWeight: 700,
              cursor: isSending ? 'wait' : 'pointer', opacity: isSending ? 0.7 : 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            <Send size={12} />
            {isSending ? 'Sending...' : `Execute ${schema.label}`}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Compressor control panel (schema-driven) ─────
function CompressorControlPanel({
  compressorId,
  compressorName,
  facilityId,
  onClose,
}: {
  compressorId: string
  compressorName: string
  facilityId: string
  onClose: () => void
}) {
  const [caps, setCaps] = useState<ControlCapabilities | null>(null)
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState<string | null>(null)

  useEffect(() => {
    api.getControlCapabilities(facilityId).then(res => {
      setCaps(res)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [facilityId, compressorId])

  const compCaps = caps?.compressors.find(c => c.compressor_id === compressorId)
  const schemas = compCaps?.control_schemas || {}

  // Map action key → API call
  const handleSend = async (actionKey: string, params: Record<string, unknown>) => {
    setSending(actionKey)
    try {
      if (actionKey === 'capacity') {
        const res = await api.controlCompressor(facilityId, {
          compressor_id: compressorId,
          action: 'set_capacity',
          value: params.value,
          ramp_rate: params.ramp_rate,
        })
        toast.success(`${res.action}: ${res.message}`)
      } else if (actionKey === 'suction_setpoint') {
        const res = await api.controlCompressor(facilityId, {
          compressor_id: compressorId,
          action: 'set_suction',
          value: params.value,
        })
        toast.success(`${res.action}: ${res.message}`)
      } else if (actionKey === 'start_stop') {
        const action = (params.action as string) || 'start'
        const res = await api.controlCompressor(facilityId, {
          compressor_id: compressorId,
          action,
        })
        toast.success(`${res.action}: ${res.message}`)
      } else if (actionKey === 'defrost') {
        await api.triggerDefrost(facilityId, {
          compressor_id: compressorId,
          action: 'trigger',
          ...params,
        })
        toast.success(`Defrost initiated: ${params.method || 'hot_gas'}, ${params.duration_min || 30} min`)
      } else {
        // Generic — attempt compressor control
        const res = await api.controlCompressor(facilityId, {
          compressor_id: compressorId,
          action: actionKey,
          ...params,
        })
        toast.success(res.message)
      }
    } catch (e: unknown) {
      toast.error(`Command failed: ${e instanceof Error ? e.message : 'Unknown error'}`)
    } finally {
      setSending(null)
    }
  }

  const panelStyle: React.CSSProperties = {
    padding: '14px',
    borderTop: '1px solid var(--border)',
    background: 'color-mix(in srgb, var(--accent) 3%, var(--card-bg))',
  }

  if (loading) {
    return (
      <div style={panelStyle}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: 8 }}>
          Loading control capabilities...
        </div>
      </div>
    )
  }

  const schemaEntries = Object.entries(schemas)

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--accent)' }}>
          <Sliders size={12} style={{ marginRight: 4, verticalAlign: -1 }} />
          Control — {compressorName}
        </span>
        <button
          onClick={onClose}
          style={{
            border: 'none', background: 'transparent', cursor: 'pointer',
            color: 'var(--text-muted)', padding: '2px 4px', borderRadius: 4,
          }}
        >
          <X size={14} />
        </button>
      </div>

      {/* Agent status warning */}
      {caps && !caps.agent_connected && (
        <div style={{
          padding: '6px 10px', marginBottom: 10, borderRadius: 6, fontSize: 11,
          background: 'color-mix(in srgb, var(--warning) 10%, transparent)',
          color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <WifiOff size={12} /> Edge agent offline — commands will queue until reconnect
        </div>
      )}

      {/* Dynamic action sections from schema */}
      {schemaEntries.map(([key, schema]) => (
        <ActionSection key={key} actionKey={key} schema={schema} onSend={handleSend} sending={sending} />
      ))}

      {/* Fallback for profiles with no schema but legacy boolean caps */}
      {schemaEntries.length === 0 && compCaps && (compCaps.can_set_capacity || compCaps.can_start_stop || compCaps.can_set_suction || compCaps.has_defrost_config) && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
          This device profile has writable registers but no parameter schemas configured. Basic controls available via API.
        </div>
      )}

      {/* No capabilities at all */}
      {schemaEntries.length === 0 && compCaps && !compCaps.can_set_capacity && !compCaps.can_start_stop && !compCaps.can_set_suction && !compCaps.has_defrost_config && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
          No writable registers configured for this compressor's device profile.
        </div>
      )}

      {!compCaps && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
          Compressor not found in control capabilities. Check device profile configuration.
        </div>
      )}
    </div>
  )
}

function HealthBadge({ score }: { score: number }) {
  const color = score >= 70 ? 'var(--success)' : score >= 40 ? 'var(--warning)' : 'var(--danger)'
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, color,
      display: 'flex', alignItems: 'center', gap: 3,
    }}>
      <svg width="12" height="12" viewBox="0 0 12 12">
        <circle cx="6" cy="6" r="5" fill="none" stroke="var(--border)" strokeWidth="2" />
        <circle cx="6" cy="6" r="5" fill="none" stroke={color} strokeWidth="2"
          strokeDasharray={`${(score / 100) * 31.4} 31.4`}
          transform="rotate(-90 6 6)"
        />
      </svg>
      {score}
    </span>
  )
}
