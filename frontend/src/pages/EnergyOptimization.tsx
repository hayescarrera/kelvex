import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Zap, DollarSign, TrendingDown, Clock, Sun, Moon, AlertTriangle, Gauge,
  Thermometer, Target, Activity, BarChart3, Loader2, Brain, CheckCircle2,
  XCircle, ChevronDown, ChevronUp, Wrench, Droplets, Wind, BarChart2, Settings2,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Cell, AreaChart, Area,
} from 'recharts'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSiteContext } from '../contexts/SiteContext'
import { usePrecoolSchedule, useDemandForecast, useSavingsProjection, useOpportunitiesSummary, useOpportunities, usePatchOpportunity } from '../hooks/useEnergy'
import { api } from '../lib/api'
import type { PowerReport, PowerSummary, EquipmentPowerBreakdown, EnergyOpportunity } from '../lib/api'

const OPP_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  excess_lift:              { label: 'Excess Lift',             icon: <Wind size={15} />,     color: '#3b82f6' },
  defrost_overrun:          { label: 'Defrost Overrun',         icon: <Thermometer size={15} />, color: '#f97316' },
  defrost_underrun:         { label: 'Defrost Underrun',        icon: <Thermometer size={15} />, color: '#f97316' },
  compressor_degradation:   { label: 'Compressor Degradation',  icon: <Activity size={15} />, color: '#ef4444' },
  condenser_fouling:        { label: 'Condenser Fouling',       icon: <Droplets size={15} />, color: '#8b5cf6' },
  charge_anomaly:           { label: 'Charge Anomaly',          icon: <BarChart2 size={15} />, color: '#ec4899' },
  setpoint_drift:           { label: 'Setpoint Drift',          icon: <Settings2 size={15} />, color: '#14b8a6' },
}

function confidenceLabel(c: number): string {
  if (c >= 0.85) return 'High'
  if (c >= 0.65) return 'Medium'
  return 'Low'
}
function confidenceColor(c: number): string {
  if (c >= 0.85) return 'var(--success)'
  if (c >= 0.65) return 'var(--warning)'
  return 'var(--text-secondary)'
}

function OpportunityCard({ opp, onDismiss, onCreateWorkOrder }: {
  opp: EnergyOpportunity
  onDismiss: (id: string) => void
  onCreateWorkOrder: (opp: EnergyOpportunity) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const meta = OPP_META[opp.opp_type] || { label: opp.opp_type, icon: <Zap size={15} />, color: 'var(--accent)' }

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      background: 'var(--bg-primary)',
      overflow: 'hidden',
    }}>
      <div
        style={{ padding: '14px 16px', cursor: 'pointer', display: 'flex', alignItems: 'flex-start', gap: 12 }}
        onClick={() => setExpanded(e => !e)}
      >
        {/* Type icon */}
        <div style={{
          width: 32, height: 32, borderRadius: 8, flexShrink: 0, marginTop: 2,
          background: meta.color + '18', color: meta.color,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {meta.icon}
        </div>

        {/* Main content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{meta.label}</span>
            {opp.confidence != null && (
              <span style={{ fontSize: 11, color: confidenceColor(opp.confidence), fontWeight: 500 }}>
                {confidenceLabel(opp.confidence)} confidence
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            {opp.recommended_action}
          </div>
        </div>

        {/* Dollar value */}
        <div style={{ textAlign: 'right', flexShrink: 0, marginLeft: 8 }}>
          {opp.estimated_usd_year != null && opp.estimated_usd_year > 0 && (
            <>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--success)' }}>
                ${Math.round(opp.estimated_usd_year).toLocaleString()}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>/yr</div>
            </>
          )}
        </div>

        <div style={{ color: 'var(--text-secondary)', flexShrink: 0, marginTop: 6 }}>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>

      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '12px 16px', background: 'var(--bg-secondary)' }}>
          {/* Evidence grid */}
          {opp.evidence && Object.keys(opp.evidence).length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 24px', marginBottom: 12 }}>
              {Object.entries(opp.evidence)
                .filter(([, v]) => v !== null && typeof v !== 'object')
                .map(([k, v]) => (
                  <div key={k} style={{ fontSize: 11 }}>
                    <span style={{ color: 'var(--text-secondary)' }}>{k.replace(/_/g, ' ')}: </span>
                    <span style={{ fontWeight: 600 }}>{String(v)}</span>
                  </div>
                ))}
            </div>
          )}

          {/* kWh/yr */}
          {opp.estimated_kwh_year != null && opp.estimated_kwh_year > 0 && (
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 12 }}>
              {Math.round(opp.estimated_kwh_year).toLocaleString()} kWh/yr estimated waste
            </div>
          )}

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn-primary"
              style={{ fontSize: 11, padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 4 }}
              onClick={e => { e.stopPropagation(); onCreateWorkOrder(opp) }}
            >
              <Wrench size={11} /> Create Work Order
            </button>
            <button
              className="btn-secondary"
              style={{ fontSize: 11, padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-secondary)' }}
              onClick={e => { e.stopPropagation(); onDismiss(opp.id) }}
            >
              <XCircle size={11} /> Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function oppToPriority(confidence: number | null): string {
  if (!confidence) return 'medium'
  if (confidence >= 0.85) return 'high'
  if (confidence >= 0.65) return 'medium'
  return 'low'
}

function IntelligenceTab({ facilityId }: { facilityId: string }) {
  const [statusFilter, setStatusFilter] = useState<'open' | 'dismissed' | 'work_order_created'>('open')
  const { data: summary } = useOpportunitiesSummary(facilityId)
  const { data: oppsData, isLoading } = useOpportunities(facilityId, statusFilter)
  const patch = usePatchOpportunity(facilityId)
  const navigate = useNavigate()

  function handleCreateWorkOrder(opp: EnergyOpportunity) {
    const meta = OPP_META[opp.opp_type]
    const title = meta ? `${meta.label} — ${opp.recommended_action?.split('.')[0] ?? 'Investigate'}` : opp.opp_type
    const qs = new URLSearchParams({
      prefill:     '1',
      title:       title.slice(0, 120),
      description: opp.recommended_action ?? '',
      category:    'corrective',
      priority:    oppToPriority(opp.confidence),
    })
    patch.mutate({ oppId: opp.id, status: 'work_order_created' })
    navigate(`/maintenance?${qs.toString()}`)
  }

  const opps = oppsData?.opportunities ?? []

  if (isLoading) return (
    <div style={{ textAlign: 'center', padding: 60 }}>
      <Loader2 size={24} className="spin" />
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Summary strip */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
          <div className="card" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.4px', fontWeight: 600 }}>
              Total Savings Potential
            </div>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--success)' }}>
              ${Math.round(summary.total_estimated_usd_year).toLocaleString()}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>per year</div>
          </div>
          <div className="card" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.4px', fontWeight: 600 }}>
              Energy Waste
            </div>
            <div style={{ fontSize: 28, fontWeight: 800 }}>
              {Math.round(summary.total_estimated_kwh_year / 1000).toLocaleString()}k
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>kWh/yr identified</div>
          </div>
          <div className="card" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.4px', fontWeight: 600 }}>
              Open Findings
            </div>
            <div style={{ fontSize: 28, fontWeight: 800 }}>
              {summary.by_type.reduce((s, r) => s + r.count, 0)}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>across {summary.by_type.length} categories</div>
          </div>
        </div>
      )}

      {/* Type breakdown pills */}
      {summary && summary.by_type.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {summary.by_type.map(r => {
            const meta = OPP_META[r.opp_type]
            return (
              <div key={r.opp_type} style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '4px 10px', borderRadius: 20,
                background: (meta?.color ?? '#6b7280') + '15',
                border: `1px solid ${(meta?.color ?? '#6b7280')}30`,
                fontSize: 12, color: meta?.color ?? 'var(--text-primary)',
              }}>
                {meta?.icon}
                <span style={{ fontWeight: 600 }}>{meta?.label ?? r.opp_type}</span>
                <span style={{ opacity: 0.7 }}>{r.count} · ${Math.round(r.estimated_usd_year / 1000)}k/yr</span>
              </div>
            )
          })}
        </div>
      )}

      {/* Status filter */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {(['open', 'work_order_created', 'dismissed'] as const).map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            style={{
              padding: '6px 14px', fontSize: 12, fontWeight: statusFilter === s ? 600 : 400,
              color: statusFilter === s ? 'var(--accent)' : 'var(--text-secondary)',
              borderBottom: statusFilter === s ? '2px solid var(--accent)' : '2px solid transparent',
              background: 'none', border: 'none', cursor: 'pointer', marginBottom: -1,
            }}
          >
            {s === 'open' ? 'Open' : s === 'work_order_created' ? 'Work Orders' : 'Dismissed'}
          </button>
        ))}
      </div>

      {/* Opportunity list */}
      {opps.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-secondary)' }}>
          <CheckCircle2 size={32} style={{ opacity: 0.3, marginBottom: 8 }} />
          <div style={{ fontSize: 14 }}>
            {statusFilter === 'open' ? 'No open findings — system looks good.' : 'Nothing here yet.'}
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {opps.map(opp => (
            <OpportunityCard
              key={opp.id}
              opp={opp}
              onDismiss={id => patch.mutate({ oppId: id, status: 'dismissed' })}
              onCreateWorkOrder={handleCreateWorkOrder}
            />
          ))}
        </div>
      )}
    </div>
  )
}

const POWER_RANGES = [
  { value: '1d', label: 'Last 24h', days: 1, interval: '1h' },
  { value: '7d', label: 'Last 7 days', days: 7, interval: '1h' },
  { value: '30d', label: 'Last 30 days', days: 30, interval: '1d' },
  { value: '90d', label: 'Last 90 days', days: 90, interval: '1d' },
]

function PowerHistoryTab({ facilityId }: { facilityId: string }) {
  const [range, setRange] = useState('7d')
  const [report, setReport] = useState<PowerReport | null>(null)
  const [summary, setSummary] = useState<PowerSummary | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const r = POWER_RANGES.find(r => r.value === range) || POWER_RANGES[1]
    const end = new Date().toISOString()
    const start = new Date(Date.now() - r.days * 86400000).toISOString()
    try {
      const [pwr, sum] = await Promise.all([
        api.getPowerReport(facilityId, { start, end, interval: r.interval }),
        api.getPowerSummary(facilityId, r.days),
      ])
      setReport(pwr)
      setSummary(sum)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [facilityId, range])

  useEffect(() => { load() }, [load])

  if (loading) return <div style={{ textAlign: 'center', padding: 40 }}><Loader2 size={24} className="spin" /></div>

  const chartData = (report?.data_points || []).map(d => ({
    ...d,
    time: new Date(d.time).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 8 }}>
        {POWER_RANGES.map(r => (
          <button
            key={r.value}
            onClick={() => setRange(r.value)}
            className={range === r.value ? 'btn-primary' : 'btn-secondary'}
            style={{ padding: '5px 12px', fontSize: 12 }}
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="stat-grid stagger">
        <StatCard icon={<Zap size={18} />} color="var(--accent)" value={`${report?.total_kwh?.toLocaleString() || 0} kWh`} label="Total Energy" />
        <StatCard icon={<Activity size={18} />} color="var(--danger)" value={`${report?.peak_demand_kw || 0} kW`} label="Peak Demand" />
        <StatCard icon={<BarChart3 size={18} />} color="var(--success)" value={`${summary?.avg_kw || 0} kW`} label="Avg Demand" />
      </div>

      {chartData.length > 0 ? (
        <div className="card">
          <div className="card-header"><h3>Power Consumption</h3></div>
          <div className="card-body" style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="time" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }} />
                <Area type="monotone" dataKey="avg_kw" name="Avg kW" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.15} />
                <Area type="monotone" dataKey="peak_kw" name="Peak kW" stroke="var(--danger)" fill="var(--danger)" fillOpacity={0.08} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <EmptyState icon={<Zap size={24} />} title="No power data" description="No telemetry readings with kw_demand metric found for this time range." />
      )}

      {summary?.equipment_breakdown && summary.equipment_breakdown.length > 0 && (
        <div className="card">
          <div className="card-header"><h3>Equipment Breakdown</h3></div>
          <div className="card-body" style={{ padding: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Equipment</th>
                  <th>Type</th>
                  <th style={{ textAlign: 'right' }}>Avg kW</th>
                  <th style={{ textAlign: 'right' }}>Peak kW</th>
                </tr>
              </thead>
              <tbody>
                {summary.equipment_breakdown.map((eq: EquipmentPowerBreakdown) => (
                  <tr key={eq.equipment_id}>
                    <td className="cell-primary">{eq.name}</td>
                    <td className="cell-secondary">{eq.equipment_type}</td>
                    <td style={{ textAlign: 'right' }}>{eq.avg_kw}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>{eq.peak_kw}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

const PERIOD_COLORS: Record<string, string> = {
  on_peak: '#ef4444',
  mid_peak: '#f97316',
  off_peak: '#22c55e',
  flat: '#3b82f6',
  unknown: '#6b7280',
}

export default function EnergyOptimization() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const { facilities } = useSiteContext()
  const facility = facilities.find(f => f.id === facilityId)
  const [tab, setTab] = useState<'intelligence' | 'optimization' | 'history'>('intelligence')

  const { data: precool, isLoading: precoolLoading } = usePrecoolSchedule(facilityId)
  const { data: forecast, isLoading: forecastLoading } = useDemandForecast(facilityId)
  const { data: savings, isLoading: savingsLoading } = useSavingsProjection(facilityId)

  const isLoading = tab === 'optimization' && (precoolLoading || forecastLoading || savingsLoading)

  if (isLoading) return <LoadingState />

  return (
    <div>
      <PageHeader
        title="Energy"
        subtitle={facility ? `${facility.name} — Load Shifting & Demand Management` : 'Load Shifting & Demand Management'}
      />

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)', marginBottom: 20, marginTop: 4 }}>
        {([
          { key: 'intelligence', label: 'Intelligence', icon: <Brain size={13} /> },
          { key: 'optimization', label: 'Load Shifting', icon: <Zap size={13} /> },
          { key: 'history',      label: 'Power History', icon: <BarChart3 size={13} /> },
        ] as const).map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '8px 14px', fontSize: 13, fontWeight: tab === t.key ? 600 : 400,
              color: tab === t.key ? 'var(--accent)' : 'var(--text-secondary)',
              borderBottom: tab === t.key ? '2px solid var(--accent)' : '2px solid transparent',
              background: 'none', border: 'none', cursor: 'pointer', marginBottom: -1,
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {tab === 'intelligence' && facilityId && <IntelligenceTab facilityId={facilityId} />}
      {tab === 'history' && facilityId && <PowerHistoryTab facilityId={facilityId} />}
      {tab === 'optimization' && (
      <>

      {/* Top stats */}
      {savings && !('error' in savings) && (
        <div className="stat-grid stagger">
          <StatCard
            icon={<DollarSign size={18} />}
            color="var(--success)"
            value={`$${Math.round(savings.projected_savings.annual_total).toLocaleString()}`}
            label="Projected Annual Savings"
          />
          <StatCard
            icon={<TrendingDown size={18} />}
            color="var(--danger)"
            value={`$${Math.round(savings.current_costs.annual_demand).toLocaleString()}`}
            label="Annual Demand Charges"
          />
          <StatCard
            icon={<Gauge size={18} />}
            color="var(--warning)"
            value={savings.current_costs.avg_peak_kw ? `${Math.round(savings.current_costs.avg_peak_kw)} kW` : ''}
            label="Avg Peak Demand"
          />
          <StatCard
            icon={<Zap size={18} />}
            color="var(--accent)"
            value={savings.plant_capacity.total_hp ? `${savings.plant_capacity.total_hp} HP` : ''}
            label="Plant Capacity"
          />
        </div>
      )}

      <div className="dashboard-grid" style={{ marginTop: 16 }}>
        {/* Rate Windows Chart */}
        {precool && !('error' in precool) && (
          <div className="card">
            <div className="card-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Clock size={16} /> Today's Rate Windows</h3>
              <span className="card-subtitle">{precool.rate_schedule}</span>
            </div>
            <div className="card-body">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={precool.rate_windows} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis
                    dataKey="hour"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(h: number) => h % 4 === 0 ? `${h}:00` : ''}
                  />
                  <YAxis
                    tick={{ fontSize: 10 }}
                    width={50}
                    tickFormatter={(v: number) => `$${v.toFixed(2)}`}
                    label={{ value: '$/kWh', angle: -90, position: 'insideLeft', style: { fontSize: 10 } }}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="energy_rate" name="Energy Rate">
                    {precool.rate_windows.map((w, i) => (
                      <Cell key={i} fill={PERIOD_COLORS[w.energy_period] || '#6b7280'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 8, fontSize: 11 }}>
                <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: '#22c55e', marginRight: 4 }} />Off-Peak</span>
                <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: '#f97316', marginRight: 4 }} />Mid-Peak</span>
                <span><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: '#ef4444', marginRight: 4 }} />On-Peak</span>
              </div>
            </div>
          </div>
        )}

        {/* Pre-Cool Schedule */}
        {precool && !('error' in precool) && (
          <div className="card">
            <div className="card-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Thermometer size={16} /> Pre-Cool Schedule</h3>
            </div>
            <div className="card-body">
              {precool.precool_window.hours.length === 0 ? (
                <div className="empty-state" style={{ padding: '1.5rem 0' }}>
                  <p className="text-muted">No TOU rate differential — pre-cooling not applicable.</p>
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', gap: 16, marginBottom: 16, fontSize: 12 }}>
                    <div>
                      <span className="text-muted">Pre-Cool Window</span>
                      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--accent)' }}>
                        <Moon size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
                        {precool.precool_window.start_hour}:00 — {precool.precool_window.end_hour}:00
                      </div>
                    </div>
                    <div>
                      <span className="text-muted">Coast Window</span>
                      <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--danger)' }}>
                        <Sun size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
                        {precool.coast_window.hours.length > 0
                          ? `${Math.min(...precool.coast_window.hours)}:00 — ${Math.max(...precool.coast_window.hours) + 1}:00`
                          : ''}
                      </div>
                    </div>
                  </div>

                  {/* Zone strategies */}
                  {precool.zone_strategies.length > 0 && (
                    <div style={{ fontSize: 12 }}>
                      <div className="text-muted" style={{ marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', fontSize: 10, letterSpacing: '0.5px' }}>
                        Zone Strategies
                      </div>
                      {precool.zone_strategies.map(z => (
                        <div key={z.zone_id} style={{
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          padding: '6px 0', borderBottom: '1px solid var(--border-subtle)',
                        }}>
                          <div>
                            <span style={{ fontWeight: 600 }}>{z.zone_name}</span>
                            <span className="text-muted" style={{ marginLeft: 6, fontSize: 11 }}>{z.zone_type}</span>
                          </div>
                          <div style={{ textAlign: 'right' }}>
                            <span style={{ color: 'var(--accent)' }}>{z.current_setpoint}°</span>
                            <span className="text-muted" style={{ margin: '0 4px' }}>→</span>
                            <span style={{ color: 'var(--success)', fontWeight: 600 }}>{z.precool_target}°</span>
                            <span className="text-muted" style={{ marginLeft: 4, fontSize: 10 }}>({z.temp_delta}° pull-down)</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Estimated savings */}
                  <div style={{ marginTop: 16, padding: 12, background: 'var(--success-bg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--success-border)' }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--success)', marginBottom: 4 }}>
                      Estimated Daily Savings
                    </div>
                    <div style={{ fontSize: 20, fontWeight: 700 }}>
                      ${precool.estimated_savings.energy_savings_daily.toFixed(2)}
                    </div>
                    <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>
                      ${precool.estimated_savings.energy_savings_monthly.toFixed(0)}/mo · {precool.estimated_savings.shifted_kwh_daily.toFixed(0)} kWh shifted daily
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* Demand Charge Tracker */}
        {forecast && !('error' in forecast) && (
          <div className="card">
            <div className="card-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Target size={16} /> Demand Charge Tracker</h3>
              <span className="card-subtitle">Billing cycle: {forecast.billing_cycle.start} → {forecast.billing_cycle.end}</span>
            </div>
            <div className="card-body">
              {/* Gauge visualization */}
              <div style={{ textAlign: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: 32, fontWeight: 700 }}>
                  {forecast.demand.current_peak_kw.toFixed(0)} kW
                </div>
                <div className="text-muted" style={{ fontSize: 12 }}>Current Peak This Cycle</div>
              </div>

              {/* Progress bar — % of historical peak */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
                  <span className="text-muted">% of Historical Peak</span>
                  <span style={{
                    fontWeight: 600,
                    color: forecast.risk.level === 'critical' ? 'var(--danger)'
                      : forecast.risk.level === 'high' ? 'var(--warning)'
                      : 'var(--success)',
                  }}>
                    {forecast.risk.pct_of_historical_peak.toFixed(0)}%
                  </span>
                </div>
                <div style={{ height: 8, background: 'var(--bg-tertiary)', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{
                    width: `${Math.min(100, forecast.risk.pct_of_historical_peak)}%`,
                    height: '100%',
                    borderRadius: 4,
                    background: forecast.risk.level === 'critical' ? 'var(--danger)'
                      : forecast.risk.level === 'high' ? 'var(--warning)'
                      : 'var(--success)',
                    transition: 'width 0.5s ease',
                  }} />
                </div>
              </div>

              {/* Risk alert */}
              <div style={{
                padding: '8px 12px', borderRadius: 'var(--radius-sm)', fontSize: 12,
                background: forecast.risk.level === 'critical' ? 'var(--danger-bg)'
                  : forecast.risk.level === 'high' ? 'var(--warning-bg)'
                  : 'var(--success-bg)',
                color: forecast.risk.level === 'critical' ? 'var(--danger)'
                  : forecast.risk.level === 'high' ? 'var(--warning)'
                  : 'var(--success)',
                marginBottom: 16,
              }}>
                <AlertTriangle size={12} style={{ marginRight: 4, verticalAlign: -2 }} />
                {forecast.risk.message}
              </div>

              {/* Billing details */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12 }}>
                <div>
                  <div className="text-muted">Billed Demand</div>
                  <div style={{ fontWeight: 700 }}>{forecast.demand.billed_demand_kw.toFixed(0)} kW</div>
                </div>
                <div>
                  <div className="text-muted">Projected Charge</div>
                  <div style={{ fontWeight: 700, color: 'var(--danger)' }}>
                    ${forecast.demand.projected_charge.toLocaleString()}
                  </div>
                </div>
                <div>
                  <div className="text-muted">Ratchet Demand</div>
                  <div style={{ fontWeight: 700 }}>{forecast.demand.ratchet_demand_kw.toFixed(0)} kW</div>
                </div>
                <div>
                  <div className="text-muted">Days Remaining</div>
                  <div style={{ fontWeight: 700 }}>
                    {forecast.billing_cycle.days_total - forecast.billing_cycle.days_elapsed}
                  </div>
                </div>
              </div>

              {/* Historical peaks chart */}
              {forecast.historical_peaks.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="text-muted" style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>
                    Historical Peak Demand
                  </div>
                  <ResponsiveContainer width="100%" height={120}>
                    <BarChart data={forecast.historical_peaks.slice(-8).reverse()} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                      <XAxis dataKey="period" tick={{ fontSize: 9 }} tickFormatter={(v: string) => v.substring(5)} />
                      <YAxis tick={{ fontSize: 9 }} width={35} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="peak_kw" fill="var(--accent)" radius={[2, 2, 0, 0]} name="Peak kW" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Savings Projection */}
        {savings && !('error' in savings) && (
          <div className="card">
            <div className="card-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}><DollarSign size={16} /> Savings Projection</h3>
            </div>
            <div className="card-body">
              <div style={{ textAlign: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--success)', marginBottom: 4 }}>
                  Annual Savings Potential
                </div>
                <div style={{ fontSize: 36, fontWeight: 800, color: 'var(--success)' }}>
                  ${Math.round(savings.projected_savings.annual_total).toLocaleString()}
                </div>
                <div className="text-muted" style={{ fontSize: 12 }}>
                  ${Math.round(savings.projected_savings.monthly_avg).toLocaleString()}/month average
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div style={{ textAlign: 'center', padding: 12, background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
                  <TrendingDown size={20} style={{ color: 'var(--danger)', marginBottom: 4 }} />
                  <div style={{ fontSize: 18, fontWeight: 700 }}>
                    ${Math.round(savings.projected_savings.demand_savings).toLocaleString()}
                  </div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Demand Savings</div>
                  <div style={{ fontSize: 10, color: 'var(--success)', marginTop: 2 }}>
                    {savings.projected_savings.demand_reduction_pct}% reduction
                  </div>
                </div>
                <div style={{ textAlign: 'center', padding: 12, background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
                  <Zap size={20} style={{ color: 'var(--accent)', marginBottom: 4 }} />
                  <div style={{ fontSize: 18, fontWeight: 700 }}>
                    ${Math.round(savings.projected_savings.energy_savings).toLocaleString()}
                  </div>
                  <div className="text-muted" style={{ fontSize: 11 }}>Energy Savings</div>
                  <div style={{ fontSize: 10, color: 'var(--success)', marginTop: 2 }}>
                    {savings.projected_savings.energy_reduction_pct}% reduction
                  </div>
                </div>
              </div>

              <div style={{ padding: 12, background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', fontSize: 12 }}>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>Current Annual Costs</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                  <span className="text-muted">Total</span>
                  <span style={{ fontWeight: 600 }}>${Math.round(savings.current_costs.annual_total).toLocaleString()}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                  <span className="text-muted">Demand charges</span>
                  <span style={{ fontWeight: 600, color: 'var(--danger)' }}>${Math.round(savings.current_costs.annual_demand).toLocaleString()}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                  <span className="text-muted">Energy charges</span>
                  <span style={{ fontWeight: 600 }}>${Math.round(savings.current_costs.annual_energy).toLocaleString()}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                  <span className="text-muted">Bills analyzed</span>
                  <span style={{ fontWeight: 600 }}>{savings.current_costs.bills_analyzed}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* No data states */}
      {!isLoading && (!savings || 'error' in savings) && (!forecast || 'error' in forecast) && (
        <EmptyState
          icon={<Zap size={28} />}
          title="Energy optimization requires data"
          description="Upload utility bills and assign a rate schedule to this facility to see load shifting recommendations, demand forecasts, and savings projections."
        />
      )}
      </>
      )}
    </div>
  )
}
