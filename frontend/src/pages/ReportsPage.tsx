import { useState, useEffect, useCallback } from 'react'
import {
  Loader2, Zap, Activity, FileText, Clock, AlertTriangle, CheckCircle,
  XCircle, Mail, BarChart3, Shield,
} from 'lucide-react'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import { useSiteContext } from '../contexts/SiteContext'
import { api } from '../lib/api'
import type {
  PowerReport, PowerSummary, AuditLogReport, AuditCommand,
  DigestPreview, EquipmentPowerBreakdown,
} from '../lib/api'

// ── Constants ───────────────────────────────────
const RANGES = [
  { value: '1d', label: 'Last 24h', days: 1, interval: '1h' },
  { value: '7d', label: 'Last 7 days', days: 7, interval: '1h' },
  { value: '30d', label: 'Last 30 days', days: 30, interval: '1d' },
  { value: '90d', label: 'Last 90 days', days: 90, interval: '1d' },
]
const CMD_STATE_COLORS: Record<string, string> = {
  completed: 'var(--success)',
  pending: 'var(--warning)',
  sent: 'var(--info)',
  failed: 'var(--danger)',
  expired: 'var(--text-secondary)',
  acknowledged: 'var(--accent)',
}

// ── Power Tab ───────────────────────────────────
function PowerTab({ facilityId }: { facilityId: string }) {
  const [range, setRange] = useState('7d')
  const [report, setReport] = useState<PowerReport | null>(null)
  const [summary, setSummary] = useState<PowerSummary | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    const r = RANGES.find(r => r.value === range) || RANGES[1]
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
      {/* Controls */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {RANGES.map(r => (
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

      {/* Stats */}
      <div className="stat-grid stagger">
        <StatCard icon={<Zap size={18} />} color="var(--accent)" value={`${report?.total_kwh?.toLocaleString() || 0} kWh`} label="Total Energy" />
        <StatCard icon={<Activity size={18} />} color="var(--danger)" value={`${report?.peak_demand_kw || 0} kW`} label="Peak Demand" />
        <StatCard icon={<BarChart3 size={18} />} color="var(--success)" value={`${summary?.avg_kw || 0} kW`} label="Avg Demand" />
        <StatCard icon={<Zap size={18} />} color="var(--warning)" value={`${report?.count || 0}`} label="Data Points" />
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div className="card">
          <div className="card-header"><h3>Power Consumption</h3></div>
          <div className="card-body" style={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="time" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                />
                <Area type="monotone" dataKey="avg_kw" name="Avg kW" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.15} />
                <Area type="monotone" dataKey="peak_kw" name="Peak kW" stroke="var(--danger)" fill="var(--danger)" fillOpacity={0.08} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Equipment breakdown */}
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
                  <th style={{ textAlign: 'right' }}>Readings</th>
                </tr>
              </thead>
              <tbody>
                {summary.equipment_breakdown.map((eq: EquipmentPowerBreakdown) => (
                  <tr key={eq.equipment_id}>
                    <td className="cell-primary">{eq.name}</td>
                    <td className="cell-secondary">{eq.equipment_type}</td>
                    <td style={{ textAlign: 'right' }}>{eq.avg_kw}</td>
                    <td style={{ textAlign: 'right', fontWeight: 600 }}>{eq.peak_kw}</td>
                    <td style={{ textAlign: 'right' }} className="cell-secondary">{eq.readings.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!chartData.length && !loading && (
        <div className="card">
          <div className="card-body">
            <div className="empty-state">
              <div className="empty-icon"><Zap size={24} /></div>
              <h3>No power data</h3>
              <p>No telemetry readings with kw_demand metric found for this time range.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Audit Log Tab ───────────────────────────────
function AuditLogTab({ facilityId }: { facilityId: string }) {
  const [report, setReport] = useState<AuditLogReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const [filterType, setFilterType] = useState('')
  const [filterState, setFilterState] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    const end = new Date().toISOString()
    const start = new Date(Date.now() - days * 86400000).toISOString()
    try {
      const data = await api.getAuditLog(facilityId, {
        start, end,
        action_type: filterType || undefined,
        state: filterState || undefined,
        limit: 200,
      })
      setReport(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [facilityId, days, filterType, filterState])

  useEffect(() => { load() }, [load])

  const totalByState = report?.by_state || {}
  const totalByType = report?.by_type || {}

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        {[7, 30, 90].map(d => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={days === d ? 'btn-primary' : 'btn-secondary'}
            style={{ padding: '5px 12px', fontSize: 12 }}
          >
            {d}d
          </button>
        ))}
        <select
          value={filterType}
          onChange={e => setFilterType(e.target.value)}
          style={{ padding: '5px 8px', fontSize: 12, borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
        >
          <option value="">All types</option>
          {Object.keys(totalByType).map(t => (
            <option key={t} value={t}>{t} ({totalByType[t]})</option>
          ))}
        </select>
        <select
          value={filterState}
          onChange={e => setFilterState(e.target.value)}
          style={{ padding: '5px 8px', fontSize: 12, borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
        >
          <option value="">All states</option>
          {Object.keys(totalByState).map(s => (
            <option key={s} value={s}>{s} ({totalByState[s]})</option>
          ))}
        </select>
      </div>

      {/* Stats */}
      <div className="stat-grid stagger">
        <StatCard icon={<Activity size={18} />} color="var(--accent)" value={String(report?.total || 0)} label="Total Commands" />
        <StatCard icon={<CheckCircle size={18} />} color="var(--success)" value={String(totalByState['completed'] || 0)} label="Completed" />
        <StatCard icon={<XCircle size={18} />} color="var(--danger)" value={String(totalByState['failed'] || 0)} label="Failed" />
        <StatCard icon={<Clock size={18} />} color="var(--warning)" value={String(totalByState['pending'] || 0)} label="Pending" />
      </div>

      {/* Type breakdown chart */}
      {Object.keys(totalByType).length > 0 && (
        <div className="card">
          <div className="card-header"><h3>Commands by Type</h3></div>
          <div className="card-body" style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={Object.entries(totalByType).map(([name, count]) => ({ name, count }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-primary)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                />
                <Bar dataKey="count" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Command list */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Loader2 size={24} className="spin" /></div>
      ) : (report?.commands?.length || 0) > 0 ? (
        <div className="card">
          <div className="card-header"><h3>Command History ({report?.total})</h3></div>
          <div className="card-body" style={{ padding: 0, overflow: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Type</th>
                  <th>State</th>
                  <th>Priority</th>
                  <th>Duration</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {report?.commands.map((cmd: AuditCommand) => {
                  const duration = cmd.issued_at && cmd.completed_at
                    ? `${((new Date(cmd.completed_at).getTime() - new Date(cmd.issued_at).getTime()) / 1000).toFixed(1)}s`
                    : '—'
                  return (
                    <tr key={cmd.id}>
                      <td className="cell-secondary" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                        {cmd.issued_at ? new Date(cmd.issued_at).toLocaleString() : '—'}
                      </td>
                      <td className="cell-primary">{cmd.command_type}</td>
                      <td>
                        <span
                          className="badge"
                          style={{
                            background: (CMD_STATE_COLORS[cmd.state] || 'var(--border)') + '22',
                            color: CMD_STATE_COLORS[cmd.state] || 'var(--text-secondary)',
                          }}
                        >
                          {cmd.state}
                        </span>
                      </td>
                      <td className="cell-secondary">{cmd.priority}</td>
                      <td className="cell-secondary">{duration}</td>
                      <td style={{ fontSize: 11, color: 'var(--danger)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {cmd.error_message || '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card">
          <div className="card-body">
            <div className="empty-state">
              <div className="empty-icon"><FileText size={24} /></div>
              <h3>No commands found</h3>
              <p>No control commands have been issued in this time range.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Digest Tab ──────────────────────────────────
function DigestTab() {
  const [preview, setPreview] = useState<DigestPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [hours, setHours] = useState(24)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getDigestPreview(hours)
      setPreview(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [hours])

  useEffect(() => { load() }, [load])

  if (loading) return <div style={{ textAlign: 'center', padding: 40 }}><Loader2 size={24} className="spin" /></div>
  if (!preview) return null

  const sevColors: Record<string, string> = {
    critical: 'var(--danger)', high: '#e67700', medium: 'var(--warning)',
    low: 'var(--info)', info: 'var(--text-secondary)',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        {[12, 24, 48, 168].map(h => (
          <button
            key={h}
            onClick={() => setHours(h)}
            className={hours === h ? 'btn-primary' : 'btn-secondary'}
            style={{ padding: '5px 12px', fontSize: 12 }}
          >
            {h < 48 ? `${h}h` : `${h / 24}d`}
          </button>
        ))}
      </div>

      <div className="card" style={{ border: '1px solid var(--accent)' }}>
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3><Mail size={15} style={{ marginRight: 6, verticalAlign: -2 }} /> Email Digest Preview</h3>
          <span className="text-muted" style={{ fontSize: 11 }}>
            Sent daily at 7:00 UTC to all notification channels
          </span>
        </div>
        <div className="card-body">
          {/* Digest content */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            {/* Alerts section */}
            <div style={{ padding: 16, background: 'var(--bg-secondary)', borderRadius: 8 }}>
              <h4 style={{ margin: '0 0 10px', fontSize: 14 }}>
                <AlertTriangle size={14} style={{ marginRight: 4, verticalAlign: -2 }} /> Alerts
              </h4>
              <div style={{ fontSize: 28, fontWeight: 700, color: preview.alerts.new_total > 0 ? 'var(--danger)' : 'var(--success)' }}>
                {preview.alerts.new_total}
              </div>
              <div className="text-muted" style={{ fontSize: 11, marginBottom: 8 }}>new active alerts</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {Object.entries(preview.alerts.active_by_severity).map(([sev, count]) => (
                  count > 0 && (
                    <div key={sev} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: sevColors[sev] || '#888' }} />
                        {sev}
                      </span>
                      <span style={{ fontWeight: 600 }}>{count}</span>
                    </div>
                  )
                ))}
              </div>
            </div>

            {/* Commands section */}
            <div style={{ padding: 16, background: 'var(--bg-secondary)', borderRadius: 8 }}>
              <h4 style={{ margin: '0 0 10px', fontSize: 14 }}>
                <Activity size={14} style={{ marginRight: 4, verticalAlign: -2 }} /> Control Actions
              </h4>
              <div style={{ fontSize: 28, fontWeight: 700 }}>{preview.commands.total}</div>
              <div className="text-muted" style={{ fontSize: 11, marginBottom: 8 }}>commands issued</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Completed</span>
                  <span style={{ fontWeight: 600, color: 'var(--success)' }}>{preview.commands.completed}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Failed</span>
                  <span style={{ fontWeight: 600, color: 'var(--danger)' }}>{preview.commands.failed}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Automation fires</span>
                  <span style={{ fontWeight: 600 }}>{preview.automation.rule_fires_today}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Facilities */}
          <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
            Covering {preview.facilities_count} facilit{preview.facilities_count === 1 ? 'y' : 'ies'}:{' '}
            {preview.facilities.map(f => f.name).join(', ')}
          </div>

          {/* Notifications */}
          {Object.keys(preview.notifications).length > 0 && (
            <div style={{ marginTop: 12, fontSize: 12 }}>
              <span className="text-muted">Recent notifications: </span>
              {Object.entries(preview.notifications).map(([status, count]) => (
                <span key={status} className="badge badge-neutral" style={{ fontSize: 10, marginRight: 4 }}>
                  {status}: {count}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-body" style={{ padding: 14 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            <Shield size={15} style={{ color: 'var(--accent)' }} />
            The daily digest is automatically sent to all enabled notification channels every day at 7:00 UTC.
            Configure channels in Settings to control who receives it.
          </div>
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════
export default function ReportsPage() {
  const { site } = useSiteContext()
  const facilityId = site?.id
  const [tab, setTab] = useState<'power' | 'audit' | 'digest'>('power')

  const needsFacility = !facilityId && tab !== 'digest'

  return (
    <div className="page-container">
      <PageHeader title="Reports" subtitle={`${site?.name || 'All'} — Power consumption, audit logs, and digests`} />

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 0, marginTop: 20, borderBottom: '1px solid var(--border)' }}>
        {(['power', 'audit', 'digest'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '8px 20px', border: 'none', background: 'none', cursor: 'pointer',
              fontWeight: tab === t ? 600 : 400, fontSize: 13,
              color: tab === t ? 'var(--accent)' : 'var(--text-secondary)',
              borderBottom: tab === t ? '2px solid var(--accent)' : '2px solid transparent',
            }}
          >
            {t === 'power' && <><Zap size={14} style={{ marginRight: 6, verticalAlign: -2 }} />Power</>}
            {t === 'audit' && <><FileText size={14} style={{ marginRight: 6, verticalAlign: -2 }} />Audit Log</>}
            {t === 'digest' && <><Mail size={14} style={{ marginRight: 6, verticalAlign: -2 }} />Digest</>}
          </button>
        ))}
      </div>

      <div className="content-area" style={{ marginTop: 16 }}>
        {needsFacility ? (
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <div className="empty-icon"><BarChart3 size={24} /></div>
                <h3>No facility selected</h3>
                <p>Choose a facility from the site selector to view {tab === 'power' ? 'power consumption' : 'audit log'} reports.</p>
              </div>
            </div>
          </div>
        ) : (
          <>
            {tab === 'power' && facilityId && <PowerTab facilityId={facilityId} />}
            {tab === 'audit' && facilityId && <AuditLogTab facilityId={facilityId} />}
            {tab === 'digest' && <DigestTab />}
          </>
        )}
      </div>
    </div>
  )
}
