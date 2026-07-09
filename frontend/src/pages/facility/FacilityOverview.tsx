import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  AreaChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  Cpu, Thermometer, Activity, AlertTriangle, DollarSign,
  WifiOff, ChevronDown, ChevronRight, Settings2, Eye, EyeOff, TrendingUp, TrendingDown,
} from 'lucide-react'
import StatCard from '../../components/ui/StatCard'
import LoadingState from '../../components/ui/LoadingState'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { useFacility } from '../../hooks/useFacilities'
import { useEquipment } from '../../hooks/useEquipment'
import { useBills } from '../../hooks/useBills'
import { useZones } from '../../hooks/useZones'
import { useAlerts } from '../../hooks/useAlerts'
import { api } from '../../lib/api'
import type { Zone, LiveMonitorResponse, LiveFacility, LiveCompressor } from '../../lib/api'

// ── Stat card definitions ─────────────────────────────────────────────────────

interface CardDef {
  id: string
  label: string
  icon: React.ReactNode
  color: string
  getValue: (data: OverviewData) => string
  getSubtitle?: (data: OverviewData) => string | null
}

interface OverviewData {
  equipmentCount: number
  zoneCount: number
  activeAlerts: number
  lastBillAmt: number | null
  billChange: number | null   // % change vs prior month
  runningCompressors: number | null
  totalKw: number | null
}

const ALL_CARDS: CardDef[] = [
  {
    id: 'equipment',
    label: 'Equipment',
    icon: <Cpu size={18} />,
    color: 'var(--accent)',
    getValue: d => String(d.equipmentCount),
  },
  {
    id: 'zones',
    label: 'Zones',
    icon: <Thermometer size={18} />,
    color: 'var(--success)',
    getValue: d => String(d.zoneCount),
  },
  {
    id: 'alerts',
    label: 'Active Alerts',
    icon: <AlertTriangle size={18} />,
    color: 'var(--danger)',
    getValue: d => String(d.activeAlerts),
  },
  {
    id: 'last_bill',
    label: 'Last Bill',
    icon: <DollarSign size={18} />,
    color: '#7c3aed',
    getValue: d => d.lastBillAmt != null ? `$${d.lastBillAmt.toLocaleString()}` : '—',
    getSubtitle: d => {
      if (d.billChange == null) return null
      const sign = d.billChange >= 0 ? '+' : ''
      return `${sign}${d.billChange.toFixed(0)}% vs prior month`
    },
  },
  {
    id: 'compressors',
    label: 'Compressors',
    icon: <Activity size={18} />,
    color: 'var(--warning)',
    getValue: d => d.runningCompressors != null ? `${d.runningCompressors} running` : '—',
  },
  {
    id: 'total_kw',
    label: 'Live kW',
    icon: <TrendingUp size={18} />,
    color: 'var(--info, #3b82f6)',
    getValue: d => d.totalKw != null ? `${d.totalKw} kW` : '—',
  },
]

const DEFAULT_VISIBLE = ['equipment', 'zones', 'alerts', 'last_bill']

function useCardPrefs(facilityId: string) {
  const key = `kelvex_overview_cards_${facilityId}`
  const [visible, setVisible] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem(key)
      if (saved) return JSON.parse(saved)
    } catch { /* ignore */ }
    return DEFAULT_VISIBLE
  })

  const save = (ids: string[]) => {
    setVisible(ids)
    localStorage.setItem(key, JSON.stringify(ids))
  }

  const toggle = (id: string) => {
    save(visible.includes(id) ? visible.filter(v => v !== id) : [...visible, id])
  }

  return { visible, toggle }
}

// ── Live monitor ───────────────────────────────────────────────────────────────

const POLL_MS = 5000

const LIVE_METRICS: { key: keyof LiveCompressor['readings']; label: string; unit: string; warn?: number; danger?: number; warnLow?: number }[] = [
  { key: 'discharge_pressure_psi', label: 'Discharge', unit: 'psi', warn: 200, danger: 250 },
  { key: 'suction_pressure_psi',  label: 'Suction',   unit: 'psi', warnLow: 15 },
  { key: 'oil_temp_f',            label: 'Oil Temp',  unit: '°F',  warn: 160, danger: 180 },
  { key: 'kw',                    label: 'kW',        unit: 'kW'  },
  { key: 'slide_valve_pct',       label: 'Load',      unit: '%'   },
  { key: 'amp_draw',              label: 'Amps',      unit: 'A'   },
]

function metricLevel(m: typeof LIVE_METRICS[0], val: number): 'normal' | 'warn' | 'danger' {
  if (m.danger != null && val >= m.danger) return 'danger'
  if (m.warn   != null && val >= m.warn)   return 'warn'
  if (m.warnLow != null && val <= m.warnLow) return 'warn'
  return 'normal'
}

function timeAgo(iso: string | null) {
  if (!iso) return 'never'
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  return `${Math.round(s / 3600)}h ago`
}

function LiveDot({ state }: { state: string }) {
  const color = state === 'connected' ? 'var(--success)' : state === 'stale' ? 'var(--warning)' : 'var(--danger)'
  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%', background: color, flexShrink: 0,
        animation: state === 'connected' ? 'pulse 2s ease-in-out infinite' : undefined,
      }} />
      <span style={{ fontSize: 12, color, fontWeight: 600 }}>
        {state === 'connected' ? 'Online' : state === 'stale' ? 'Stale' : 'Offline'}
      </span>
    </span>
  )
}

function CompressorRow({ c }: { c: LiveCompressor }) {
  const [open, setOpen] = useState(false)
  const isAlarm   = c.state === 'alarm' || c.anomalies.length > 0
  const isRunning = c.state === 'running' || c.readings.running === true
  const isAtRisk  = !isAlarm && c.health_score != null && c.health_score < 70
  const accentColor = isAlarm ? 'var(--danger)' : isAtRisk ? 'var(--warning)' : c.data_stale ? 'var(--border)' : 'var(--success)'
  const statusColor = isAlarm ? 'var(--danger)' : isRunning ? 'var(--success)' : 'var(--text-secondary)'

  return (
    <div style={{
      border: '1px solid var(--border)', borderLeft: `3px solid ${accentColor}`,
      borderRadius: 8, overflow: 'hidden', background: 'var(--bg-primary)',
      boxShadow: isAlarm ? '0 0 14px rgba(201,49,49,0.1)' : undefined,
    }}>
      <div onClick={() => setOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', cursor: 'pointer' }}>
        <div style={{ color: 'var(--text-secondary)', flexShrink: 0 }}>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
        <div style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, background: accentColor,
          animation: isRunning && !isAlarm ? 'pulse 2s infinite' : undefined }} />
        <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{c.name}</span>
        {c.tag && <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{c.tag}</span>}
        {c.health_score != null && (
          <span style={{ fontSize: 12, fontWeight: 700,
            color: c.health_score >= 70 ? 'var(--success)' : c.health_score >= 40 ? 'var(--warning)' : 'var(--danger)' }}>
            {c.health_score}%
          </span>
        )}
        <span style={{ fontSize: 11, fontWeight: 600, color: statusColor }}>
          {isAlarm ? 'Alarm' : isRunning ? 'Running' : 'Standby'}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{timeAgo(c.readings.recorded_at)}</span>
      </div>
      {isAlarm && c.anomalies.length > 0 && (
        <div style={{ padding: '6px 14px 6px 38px', background: 'var(--danger-bg)', borderTop: '1px solid var(--danger-border)' }}>
          {c.anomalies.map((a, i) => (
            <div key={i} style={{ fontSize: 12, color: 'var(--danger)', fontWeight: 600 }}>
              ⚠ {a.type.replace(/_/g, ' ')} — {a.value.toFixed(1)} / {a.threshold} limit
            </div>
          ))}
        </div>
      )}
      {open && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(90px, 1fr))', gap: 1, background: 'var(--border)', borderTop: '1px solid var(--border)' }}>
          {LIVE_METRICS.map(m => {
            const raw = c.readings[m.key]
            if (raw == null) return null
            const val = typeof raw === 'boolean' ? (raw ? 1 : 0) : raw as number
            const level = metricLevel(m, val)
            return (
              <div key={m.key} style={{ background: 'var(--bg-primary)', padding: '8px 10px' }}>
                <div style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: 0.3 }}>{m.label}</div>
                <div style={{ fontSize: 14, fontWeight: 600, marginTop: 2, fontVariantNumeric: 'tabular-nums',
                  color: level === 'danger' ? 'var(--danger)' : level === 'warn' ? 'var(--warning)' : 'var(--text-primary)' }}>
                  {val.toFixed(1)}<span style={{ fontSize: 10, color: 'var(--text-secondary)', marginLeft: 2 }}>{m.unit}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function LiveSection({ facilityId, onLiveData }: { facilityId: string; onLiveData: (d: LiveFacility | null) => void }) {
  const [liveData, setLiveData] = useState<LiveFacility | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [liveErr, setLiveErr] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    async function fetch() {
      try {
        const res: LiveMonitorResponse = await api.getLiveMonitor()
        const fac = res.facilities.find(f => String(f.facility_id) === facilityId) ?? null
        setLiveData(fac)
        onLiveData(fac)
        setLastUpdate(new Date())
        setLiveErr(false)
      } catch {
        setLiveErr(true)
      }
    }
    fetch()
    timer.current = setInterval(fetch, POLL_MS)
    return () => { if (timer.current) clearInterval(timer.current) }
  }, [facilityId]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!liveData && !liveErr) return null

  if (liveErr || !liveData) return (
    <div className="card">
      <div className="card-body" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: 13 }}>
        <WifiOff size={15} /> Live telemetry unavailable
      </div>
    </div>
  )

  const sorted = [...liveData.compressors].sort((a, b) => {
    const score = (c: LiveCompressor) => c.state === 'alarm' || c.anomalies.length > 0 ? 0 : c.health_score != null && c.health_score < 40 ? 1 : c.health_score != null && c.health_score < 70 ? 2 : 3
    return score(a) - score(b)
  })

  return (
    <div className="card">
      <div className="card-header">
        <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--success)', display: 'inline-block', animation: 'pulse 2s ease-in-out infinite' }} />
          Live
        </h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12 }}>
          <LiveDot state={liveData.agent_status} />
          <span style={{ color: 'var(--text-secondary)' }}>{liveData.running}/{liveData.total_compressors} running</span>
          {liveData.total_kw != null && <span style={{ color: 'var(--warning)', fontWeight: 600 }}>{liveData.total_kw} kW</span>}
          {liveData.in_alarm > 0 && (
            <span style={{ color: 'var(--danger)', fontWeight: 700 }}>
              <AlertTriangle size={12} style={{ verticalAlign: -2, marginRight: 3 }} />
              {liveData.in_alarm} alarm{liveData.in_alarm > 1 ? 's' : ''}
            </span>
          )}
          {lastUpdate && <span style={{ color: 'var(--text-secondary)' }}>Updated {timeAgo(lastUpdate.toISOString())}</span>}
        </div>
      </div>
      {liveData.in_alarm > 0 && (
        <div style={{ margin: '0 16px 12px', padding: '9px 14px', background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 8, fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertTriangle size={14} style={{ color: 'var(--danger)', flexShrink: 0 }} />
          <span style={{ fontWeight: 600, color: 'var(--danger)' }}>{liveData.in_alarm} unit{liveData.in_alarm > 1 ? 's' : ''} require attention — sorted to top</span>
        </div>
      )}
      <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {sorted.length === 0
          ? <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-secondary)', fontSize: 13 }}>No compressors connected. Add one under Equipment.</div>
          : sorted.map(c => <CompressorRow key={c.id} c={c} />)
        }
      </div>
    </div>
  )
}

// ── Zone colors ───────────────────────────────────────────────────────────────

const ZONE_COLORS: Record<string, string> = {
  freezer: 'var(--freezer)', cooler: 'var(--cooler)', dock: 'var(--dock)',
  machine_room: 'var(--machine)', blast_freezer: 'var(--freezer)', staging: 'var(--accent)',
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FacilityOverview() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const { isLoading: fl } = useFacility(facilityId!)
  const { data: eqData, isLoading: el } = useEquipment(facilityId!)
  const { data: billData, isLoading: bl } = useBills(facilityId!)
  const { data: zoneData, isLoading: zl } = useZones(facilityId!)
  const { data: alertData } = useAlerts(facilityId!, { state: 'active' })

  const [liveData, setLiveData] = useState<LiveFacility | null>(null)
  const [customizing, setCustomizing] = useState(false)
  const { visible, toggle } = useCardPrefs(facilityId!)

  if (fl || el || bl || zl) return <LoadingState />

  const equipment    = eqData?.equipment ?? []
  const bills        = billData?.bills ?? []
  const zones        = zoneData?.zones ?? []
  const activeAlerts = alertData?.total ?? 0

  // Bill totals
  const lastBill  = bills[0] ?? null
  const priorBill = bills[1] ?? null
  const lastBillAmt  = lastBill  ? Math.round(Number(lastBill.total_cost  || (Number(lastBill.demand_charge  || 0) + Number(lastBill.energy_charge  || 0)))) : null
  const priorBillAmt = priorBill ? Math.round(Number(priorBill.total_cost || (Number(priorBill.demand_charge || 0) + Number(priorBill.energy_charge || 0)))) : null
  const billChange = (lastBillAmt && priorBillAmt && priorBillAmt > 0)
    ? ((lastBillAmt - priorBillAmt) / priorBillAmt) * 100
    : null

  // Sparkline: total cost per month (last 7)
  const sparkData = bills.slice(0, 7).reverse().map(b => ({
    month: new Date(b.period_start).toLocaleString('default', { month: 'short', year: '2-digit' }),
    total: Math.round(Number(b.total_cost || (Number(b.demand_charge || 0) + Number(b.energy_charge || 0)))),
    kwh: b.total_kwh != null ? Math.round(b.total_kwh) : null,
  }))
  const hasKwh = sparkData.some(d => d.kwh != null)

  const eqByType: Record<string, typeof equipment> = {}
  equipment.forEach(eq => {
    if (!eqByType[eq.equipment_type]) eqByType[eq.equipment_type] = []
    eqByType[eq.equipment_type].push(eq)
  })

  const overviewData: OverviewData = {
    equipmentCount:     equipment.length,
    zoneCount:          zones.length,
    activeAlerts,
    lastBillAmt,
    billChange,
    runningCompressors: liveData ? liveData.running : null,
    totalKw:            liveData?.total_kw ?? null,
  }

  const visibleCards = ALL_CARDS.filter(c => visible.includes(c.id))
  const hiddenCards  = ALL_CARDS.filter(c => !visible.includes(c.id))

  return (
    <div className="stack-lg">

      {/* ── Stat cards ──────────────────────────────────────────── */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <button
            onClick={() => setCustomizing(c => !c)}
            style={{
              display: 'flex', alignItems: 'center', gap: 5, fontSize: 12,
              color: customizing ? 'var(--accent)' : 'var(--text-secondary)',
              background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px',
            }}
          >
            <Settings2 size={13} /> {customizing ? 'Done' : 'Customize'}
          </button>
        </div>

        {/* Visible cards */}
        {visibleCards.length > 0 && (
          <div className="stat-grid-5 stagger">
            {visibleCards.map(card => (
              <div key={card.id} style={{ position: 'relative' }}>
                <StatCard
                  icon={card.icon}
                  color={card.color}
                  value={card.getValue(overviewData)}
                  label={card.label}
                  subtitle={card.getSubtitle?.(overviewData) ?? undefined}
                />
                {customizing && (
                  <button
                    onClick={() => toggle(card.id)}
                    title="Hide this card"
                    style={{
                      position: 'absolute', top: 6, right: 6,
                      background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                      borderRadius: '50%', width: 22, height: 22, cursor: 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    <EyeOff size={11} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Hidden cards — show in customize mode */}
        {customizing && hiddenCards.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
            {hiddenCards.map(card => (
              <button
                key={card.id}
                onClick={() => toggle(card.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '5px 12px', borderRadius: 20, fontSize: 12,
                  border: '1px dashed var(--border)',
                  background: 'var(--bg-secondary)', color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                <Eye size={12} /> {card.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Live compressors ────────────────────────────────────── */}
      <LiveSection facilityId={facilityId!} onLiveData={setLiveData} />

      {/* ── Zones ───────────────────────────────────────────────── */}
      {zones.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3>Zone Status</h3>
            <span className="card-subtitle">{zones.length} zones</span>
          </div>
          <div className="card-body">
            <div className="zone-grid">
              {zones.map((zone: Zone) => {
                const color = ZONE_COLORS[zone.zone_type] ?? 'var(--text-muted)'
                return (
                  <div key={zone.id} className="zone-card" style={{ '--zone-color': color } as React.CSSProperties}>
                    <div className="zone-card-header">
                      <span className="zone-card-name">{zone.name}</span>
                      <span className="zone-card-badge">{zone.state || 'normal'}</span>
                    </div>
                    <div className="zone-card-temp">
                      {zone.current_temp != null ? `${zone.current_temp}°${zone.temp_unit || 'F'}` : ''}
                    </div>
                    <div className="zone-card-meta">
                      Setpoint: {zone.temp_setpoint != null ? `${zone.temp_setpoint}°${zone.temp_unit || 'F'}` : '—'}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* ── Equipment + monthly cost ─────────────────────────────── */}
      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <h3>Equipment by Type</h3>
            <span className="card-subtitle">{equipment.length} units</span>
          </div>
          <div className="card-body">
            {Object.keys(eqByType).length === 0 ? (
              <p className="text-muted" style={{ padding: 20, textAlign: 'center' }}>No equipment registered yet</p>
            ) : Object.entries(eqByType).map(([type, items]) => (
              <div key={type} className="eq-type-row">
                <div className="eq-type-header">
                  <span className="eq-type-name">{type}</span>
                  <span className="eq-type-count">{items.length}</span>
                </div>
                <div className="eq-type-chips">
                  {items.slice(0, 4).map(eq => <span key={eq.id} className="chip">{eq.name}</span>)}
                  {items.length > 4 && <span className="chip chip-muted">+{items.length - 4} more</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <h3>Monthly Bill</h3>
            <span className="card-subtitle" style={{
              display: 'flex', alignItems: 'center', gap: 4,
              color: billChange == null ? undefined : billChange > 0 ? 'var(--danger)' : 'var(--success)',
            }}>
              {billChange != null && (billChange > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />)}
              {billChange != null ? `${billChange > 0 ? '+' : ''}${billChange.toFixed(0)}% vs prior month` : 'Total spend'}
            </span>
          </div>
          <div className="card-body" style={{ padding: '0 12px 12px' }}>
            {sparkData.length === 0 ? (
              <p className="text-muted" style={{ padding: 40, textAlign: 'center' }}>Upload bills to see cost trend</p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={sparkData} margin={{ top: 10, right: hasKwh ? 44 : 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#7c3aed" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#7c3aed" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis dataKey="month" stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="cost" stroke="var(--chart-text)" tick={{ fontSize: 11 }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
                  {hasKwh && (
                    <YAxis yAxisId="kwh" orientation="right" stroke="var(--chart-text)" tick={{ fontSize: 11 }}
                      tickFormatter={v => v >= 1000 ? `${(v/1000).toFixed(0)}M` : `${v}k`} />
                  )}
                  <Tooltip content={<ChartTooltip />} formatter={(v: number, name: string) =>
                    name === 'kWh Usage'
                      ? [v >= 1000 ? `${(v/1000).toFixed(1)} MWh` : `${v.toLocaleString()} kWh`, name]
                      : [`$${v.toLocaleString()}`, name]
                  } />
                  <Area yAxisId="cost" type="monotone" dataKey="total" name="Total Bill" stroke="#7c3aed" fill="url(#costGrad)" strokeWidth={2} dot={{ r: 3, fill: '#7c3aed' }} />
                  {hasKwh && (
                    <Line yAxisId="kwh" type="monotone" dataKey="kwh" name="kWh Usage" stroke="#0ea5e9" strokeWidth={2} dot={{ r: 3, fill: '#0ea5e9' }} strokeDasharray="4 3" connectNulls />
                  )}
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
