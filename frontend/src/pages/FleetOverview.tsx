import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import {
  Building2, Cpu, Thermometer, Plus, MapPin,
  ChevronRight, X, Trash2, AlertTriangle, DollarSign, Droplets, Wrench, ShieldCheck, CheckCircle,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSiteContext } from '../contexts/SiteContext'
import { useAlertSummary } from '../hooks/useAlerts'
import { useCreateFacility, useDeleteFacility } from '../hooks/useFacilities'
import { api } from '../lib/api'
import type { Zone, Bill, RefrigerantDashboard } from '../lib/api'

interface PortfolioData {
  equipmentCounts: Record<string, number>
  zones: (Zone & { facilityId: string })[]
  bills: Bill[]
  loaded: boolean
  refrigerantDashboard: RefrigerantDashboard | null
}

export default function FleetOverview() {
  const navigate = useNavigate()
  const { facilities, isLoading } = useSiteContext()
  const { data: alertSummary } = useAlertSummary()
  const [showAddModal, setShowAddModal] = useState(false)
  const deleteFacility = useDeleteFacility()

  const [portfolio, setPortfolio] = useState<PortfolioData>({
    equipmentCounts: {}, zones: [], bills: [], loaded: false, refrigerantDashboard: null,
  })

  useEffect(() => {
    if (!facilities.length) return
    Promise.all([
      Promise.all(facilities.map(f => api.listEquipment(f.id).then(r => ({ id: f.id, count: r.total })).catch(() => ({ id: f.id, count: 0 })))),
      Promise.all(facilities.map(f => api.listZones(f.id).then(r => r.zones.map(z => ({ ...z, facilityId: f.id }))).catch(() => []))),
      Promise.all(facilities.map(f => api.listBills(f.id).then(r => r.bills).catch(() => []))),
      api.getRefrigerantDashboard().catch(() => null),
    ]).then(([eqResults, zoneResults, billResults, refrigerantDashboard]) => {
      const counts: Record<string, number> = {}
      ;(eqResults as { id: string; count: number }[]).forEach(({ id, count }) => { counts[id] = count })
      setPortfolio({
        equipmentCounts: counts,
        zones: (zoneResults as (Zone & { facilityId: string })[][]).flat(),
        bills: (billResults as Bill[][]).flat(),
        loaded: true,
        refrigerantDashboard: refrigerantDashboard as RefrigerantDashboard | null,
      })
    }).catch(err => {
      console.error('FleetOverview portfolio load error:', err)
      setPortfolio(p => ({ ...p, loaded: true }))
    })
  }, [facilities])


  const totalAlerts = alertSummary?.total_active ?? 0
  const criticalAlerts = alertSummary?.by_severity?.critical ?? 0
  const highAlerts = alertSummary?.by_severity?.high ?? 0
  const openLeaks = portfolio.refrigerantDashboard?.open_leak_events ?? 0
  const sitesAboveThreshold = portfolio.refrigerantDashboard?.sites_above_threshold ?? 0

  // Per-facility zone alarm lookup
  const facilityZoneAlarms: Record<string, number> = {}
  portfolio.zones.forEach(z => {
    const inAlarm = z.current_temp != null && (
      (z.temp_alarm_high != null && z.current_temp > z.temp_alarm_high) ||
      (z.temp_alarm_low != null && z.current_temp < z.temp_alarm_low)
    )
    if (inAlarm) facilityZoneAlarms[z.facilityId] = (facilityZoneAlarms[z.facilityId] || 0) + 1
  })

  // Zone temperature stats
  const zonesWithTemp = portfolio.zones.filter(z => z.current_temp != null)
  const zonesInAlarm = portfolio.zones.filter(z => {
    if (z.current_temp == null) return false
    if (z.temp_alarm_high != null && z.current_temp > z.temp_alarm_high) return true
    if (z.temp_alarm_low != null && z.current_temp < z.temp_alarm_low) return true
    return false
  })
  const avgTemp = zonesWithTemp.length > 0
    ? (zonesWithTemp.reduce((s, z) => s + (z.current_temp ?? 0), 0) / zonesWithTemp.length).toFixed(1)
    : null

  // Cost data — monthly from bills
  const monthlyCosts: Record<string, { month: string; demand: number; energy: number; total: number }> = {}
  for (const bill of portfolio.bills) {
    const start = new Date(bill.period_start)
    const key = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}`
    const label = start.toLocaleString('default', { month: 'short', year: '2-digit' })
    if (!monthlyCosts[key]) monthlyCosts[key] = { month: label, demand: 0, energy: 0, total: 0 }
    monthlyCosts[key].demand += Number(bill.demand_charge || 0)
    monthlyCosts[key].energy += Number(bill.energy_charge || 0)
    monthlyCosts[key].total += Number(bill.total_cost || 0)
  }
  const costChart = Object.entries(monthlyCosts)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-8)
    .map(([, v]) => v)

  const annualCost = portfolio.bills.reduce((s, b) => s + Number(b.total_cost || 0), 0)
  const annualDemand = portfolio.bills.reduce((s, b) => s + Number(b.demand_charge || 0), 0)
  const peakDemand = portfolio.bills.reduce((max, b) => Math.max(max, Number(b.peak_demand_kw || 0)), 0)

  // Alert severity pie
  const alertPie = alertSummary ? [
    { name: 'Critical', value: alertSummary.by_severity.critical, color: '#ef4444' },
    { name: 'High', value: alertSummary.by_severity.high, color: '#f97316' },
    { name: 'Medium', value: alertSummary.by_severity.medium, color: '#eab308' },
    { name: 'Low', value: alertSummary.by_severity.low, color: '#3b82f6' },
    { name: 'Info', value: alertSummary.by_severity.info, color: '#6b7280' },
  ].filter(d => d.value > 0) : []

  if (isLoading) return <LoadingState />

  return (
    <div className="page-container">
      <PageHeader title="Fleet Overview" subtitle={`${facilities.length} facilit${facilities.length !== 1 ? 'ies' : 'y'} across your portfolio`}>
        <button className="btn-primary" onClick={() => setShowAddModal(true)}><Plus size={15} /> Add Facility</button>
      </PageHeader>

      {/* ── Critical alert banner ───────────────── */}
      {criticalAlerts > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
          background: 'var(--danger-bg)', border: '1px solid var(--danger-border)',
          borderRadius: 8, marginTop: 12, fontSize: 13,
        }}>
          <AlertTriangle size={16} style={{ color: 'var(--danger)', flexShrink: 0 }} />
          <span style={{ color: 'var(--danger)', fontWeight: 600 }}>
            {criticalAlerts} critical alert{criticalAlerts !== 1 ? 's' : ''} require attention
          </span>
          <button className="btn-ghost" style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--danger)', fontWeight: 600 }} onClick={() => navigate('/alerts')}>
            View alerts →
          </button>
        </div>
      )}

      {/* ── Top Stats ──────────────────────────── */}
      <div className="stat-grid stagger">
        <StatCard
          icon={<AlertTriangle size={18} />}
          color={totalAlerts > 0 ? 'var(--danger)' : 'var(--success)'}
          value={String(totalAlerts)}
          label={totalAlerts === 1 ? 'Active Alert' : 'Active Alerts'}
        />
        <StatCard
          icon={<Droplets size={18} />}
          color={openLeaks > 0 ? 'var(--danger)' : portfolio.loaded ? 'var(--success)' : 'var(--text-muted)'}
          value={portfolio.loaded ? String(openLeaks) : '—'}
          label="Open Leaks"
        />
        <StatCard
          icon={<ShieldCheck size={18} />}
          color={sitesAboveThreshold > 0 ? 'var(--warning)' : portfolio.loaded ? 'var(--success)' : 'var(--text-muted)'}
          value={portfolio.loaded ? String(sitesAboveThreshold) : '—'}
          label="Above AIM-Act Threshold"
        />
        <StatCard icon={<Building2 size={18} />} color="var(--accent)" value={String(facilities.length)} label="Facilities" />
      </div>

      {/* ── Dashboard Grid ─────────────────────── */}
      {facilities.length > 0 && portfolio.loaded && (
        <div className="dashboard-grid">

          {/* Refrigerant Overview — first, highest operational priority */}
          <div className="card" style={{ cursor: 'pointer' }} onClick={() => navigate('/leak-tracking')}>
            <div className="card-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Droplets size={16} /> Refrigerant Overview</h3>
              <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
            </div>
            <div className="card-body">
              {!portfolio.refrigerantDashboard ? (
                <div className="empty-state" style={{ padding: '1.5rem 0' }}>
                  <p className="text-muted">No refrigerant tracking data yet. Connect an edge agent to start detecting leaks.</p>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div style={{ textAlign: 'center', padding: 16, background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
                    <AlertTriangle size={24} style={{ color: portfolio.refrigerantDashboard.open_leak_events > 0 ? 'var(--danger)' : 'var(--success)', marginBottom: 4 }} />
                    <div style={{ fontSize: 24, fontWeight: 700, color: portfolio.refrigerantDashboard.open_leak_events > 0 ? 'var(--danger)' : undefined }}>
                      {portfolio.refrigerantDashboard.open_leak_events}
                    </div>
                    <div className="text-muted" style={{ fontSize: 11 }}>Open Leaks</div>
                  </div>
                  <div style={{ textAlign: 'center', padding: 16, background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
                    <Droplets size={24} style={{ color: 'var(--warning)', marginBottom: 4 }} />
                    <div style={{ fontSize: 24, fontWeight: 700 }}>
                      {portfolio.refrigerantDashboard.refrigerant_added_30d_lbs.toFixed(1)}
                    </div>
                    <div className="text-muted" style={{ fontSize: 11 }}>Lbs Added (30d)</div>
                  </div>
                  <div style={{ textAlign: 'center', padding: 16, background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
                    <Wrench size={24} style={{ color: 'var(--info)', marginBottom: 4 }} />
                    <div style={{ fontSize: 24, fontWeight: 700 }}>{portfolio.refrigerantDashboard.repairs_30d}</div>
                    <div className="text-muted" style={{ fontSize: 11 }}>Repairs (30d)</div>
                  </div>
                  <div style={{ textAlign: 'center', padding: 16, background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
                    <ShieldCheck size={24} style={{ color: portfolio.refrigerantDashboard.sites_above_threshold > 0 ? 'var(--danger)' : 'var(--success)', marginBottom: 4 }} />
                    <div style={{ fontSize: 24, fontWeight: 700, color: portfolio.refrigerantDashboard.sites_above_threshold > 0 ? 'var(--danger)' : undefined }}>
                      {portfolio.refrigerantDashboard.sites_above_threshold}
                    </div>
                    <div className="text-muted" style={{ fontSize: 11 }}>Above AIM-Act Threshold</div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Alert Summary */}
          <div className="card">
            <div className="card-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}><AlertTriangle size={16} /> Alert Summary</h3>
            </div>
            <div className="card-body">
              {totalAlerts === 0 ? (
                <div className="empty-state" style={{ padding: '1.5rem 0' }}>
                  <div className="empty-icon"><CheckCircle size={22} style={{ color: 'var(--success)' }} /></div>
                  <h3 style={{ color: 'var(--success)' }}>All clear</h3>
                  <p className="text-muted">No active alerts across the portfolio.</p>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                  <ResponsiveContainer width={120} height={120}>
                    <PieChart>
                      <Pie data={alertPie} dataKey="value" cx="50%" cy="50%" innerRadius={30} outerRadius={50} paddingAngle={2}>
                        {alertPie.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={{ flex: 1 }}>
                    {criticalAlerts > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                        <span className="badge badge-danger" style={{ fontSize: 11 }}>Critical</span>
                        <span style={{ fontWeight: 700 }}>{criticalAlerts}</span>
                      </div>
                    )}
                    {highAlerts > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                        <span className="badge badge-warning" style={{ fontSize: 11 }}>High</span>
                        <span style={{ fontWeight: 700 }}>{highAlerts}</span>
                      </div>
                    )}
                    {(alertSummary?.by_severity.medium ?? 0) > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                        <span className="badge badge-info" style={{ fontSize: 11 }}>Medium</span>
                        <span style={{ fontWeight: 700 }}>{alertSummary!.by_severity.medium}</span>
                      </div>
                    )}
                    {(alertSummary?.by_severity.low ?? 0) + (alertSummary?.by_severity.info ?? 0) > 0 && (
                      <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
                        <span className="badge badge-neutral" style={{ fontSize: 11 }}>Low/Info</span>
                        <span style={{ fontWeight: 700 }}>{(alertSummary!.by_severity.low ?? 0) + (alertSummary!.by_severity.info ?? 0)}</span>
                      </div>
                    )}
                    <button className="btn-ghost" style={{ marginTop: 8, fontSize: 12 }} onClick={() => navigate('/alerts')}>
                      View all alerts <ChevronRight size={12} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Zone Temperatures */}
          <div className="card">
            <div className="card-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}><Thermometer size={16} /> Zone Temperatures</h3>
            </div>
            <div className="card-body">
              {portfolio.zones.length === 0 ? (
                <div className="empty-state" style={{ padding: '1.5rem 0' }}>
                  <p className="text-muted">No zones configured yet.</p>
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', gap: 20, marginBottom: 16, fontSize: 12 }}>
                    <div>
                      <span className="text-muted">Avg Temp</span>
                      <div style={{ fontSize: 18, fontWeight: 700 }}>{avgTemp ? `${avgTemp}°F` : ''}</div>
                    </div>
                    <div>
                      <span className="text-muted">Reporting</span>
                      <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--success)' }}>{zonesWithTemp.length}</div>
                    </div>
                    <div>
                      <span className="text-muted">In Alarm</span>
                      <div style={{ fontSize: 18, fontWeight: 700, color: zonesInAlarm.length > 0 ? 'var(--danger)' : 'var(--success)' }}>
                        {zonesInAlarm.length}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {portfolio.zones.slice(0, 12).map(z => {
                      const inAlarm = z.current_temp != null && (
                        (z.temp_alarm_high != null && z.current_temp > z.temp_alarm_high) ||
                        (z.temp_alarm_low != null && z.current_temp < z.temp_alarm_low)
                      )
                      return (
                        <div key={z.id} style={{
                          padding: '8px 12px', borderRadius: 'var(--radius-md)',
                          border: `1px solid ${inAlarm ? 'var(--danger)' : 'var(--border-subtle)'}`,
                          background: inAlarm ? 'color-mix(in srgb, var(--danger) 8%, transparent)' : 'var(--bg-tertiary)',
                          minWidth: 90, fontSize: 12,
                        }}>
                          <div style={{ fontWeight: 600, marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 100 }}>{z.name}</div>
                          <div style={{ fontSize: 16, fontWeight: 700, color: inAlarm ? 'var(--danger)' : 'var(--text-primary)' }}>
                            {z.current_temp != null ? `${z.current_temp.toFixed(1)}°` : ''}
                          </div>
                          {z.temp_setpoint != null && (
                            <div className="text-muted" style={{ fontSize: 10 }}>
                              Set: {z.temp_setpoint}°
                            </div>
                          )}
                        </div>
                      )
                    })}
                    {portfolio.zones.length > 12 && (
                      <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center', fontSize: 12, color: 'var(--text-muted)' }}>
                        +{portfolio.zones.length - 12} more
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Portfolio Costs — last, least urgent */}
          <div className="card">
            <div className="card-header">
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}><DollarSign size={16} /> Portfolio Costs</h3>
            </div>
            <div className="card-body">
              {costChart.length === 0 ? (
                <div className="empty-state" style={{ padding: '1.5rem 0' }}>
                  <p className="text-muted">No bill data — upload utility bills to see cost trends.</p>
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', gap: 20, marginBottom: 12, fontSize: 12 }}>
                    <div>
                      <span className="text-muted">Annual Total</span>
                      <div style={{ fontSize: 18, fontWeight: 700 }}>${annualCost.toLocaleString()}</div>
                    </div>
                    <div>
                      <span className="text-muted">Utility Charges</span>
                      <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--danger)' }}>${annualDemand.toLocaleString()}</div>
                    </div>
                    <div>
                      <span className="text-muted">Peak kW</span>
                      <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--warning)' }}>{peakDemand > 0 ? `${peakDemand}` : ''}</div>
                    </div>
                  </div>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={costChart} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
                      <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)} width={40} />
                      <Tooltip content={<ChartTooltip />} />
                      <Bar dataKey="demand" name="Demand $" stackId="cost" fill="#ef4444" radius={[0, 0, 0, 0]} />
                      <Bar dataKey="energy" name="Energy $" stackId="cost" fill="var(--color-accent, #3b82f6)" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </>
              )}
            </div>
          </div>

        </div>
      )}

      {/* ── Facility Table ─────────────────────── */}
      <div className="content-area">
        {facilities.length === 0 ? (
          <EmptyState
            icon={<Building2 size={28} />}
            title="No facilities yet"
            description="Add your first cold storage facility to start monitoring operations."
            action={
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
                <button className="btn-primary" onClick={() => navigate('/onboarding')} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <ChevronRight size={15} /> Start setup wizard
                </button>
                <button className="btn-ghost" onClick={() => setShowAddModal(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Plus size={15} /> Add manually
                </button>
              </div>
            }
          />
        ) : (
          <div className="card">
            <div className="card-header"><h3>Facilities</h3></div>
            <table className="data-table">
              <thead><tr><th>Facility</th><th>Location</th><th>Size</th><th>Equipment</th><th>Status</th><th style={{ width: 80 }}></th></tr></thead>
              <tbody>
                {facilities.map(f => (
                  <tr key={f.id} onClick={() => navigate(`/sites/${f.id}`)} style={{ cursor: 'pointer' }}>
                    <td>
                      <div className="cell-with-icon">
                        <div className="table-icon"><Building2 size={14} /></div>
                        <div>
                          <span className="cell-primary">{f.name}</span>
                          {(f.zone_types?.length ?? 0) > 0 && <span className="cell-secondary">{f.zone_types!.join(', ')}</span>}
                        </div>
                      </div>
                    </td>
                    <td><span className="cell-with-icon-inline"><MapPin size={13} />{[f.city, f.state].filter(Boolean).join(', ') || '\u2014'}</span></td>
                    <td>{f.sqft ? `${f.sqft.toLocaleString()} sqft` : '\u2014'}</td>
                    <td><span className="cell-with-icon-inline"><Cpu size={13} />{portfolio.equipmentCounts[f.id] ?? 0} units</span></td>
                    <td>
                      {(portfolio.equipmentCounts[f.id] ?? 0) === 0
                        ? <span className="badge badge-neutral"><span className="badge-dot" /> No agent</span>
                        : (facilityZoneAlarms[f.id] ?? 0) > 0
                          ? (
                            <span
                              className="badge badge-danger"
                              style={{ cursor: 'pointer' }}
                              onClick={e => { e.stopPropagation(); navigate('/alerts') }}
                            >
                              <span className="badge-dot" /> {facilityZoneAlarms[f.id]} zone alarm{facilityZoneAlarms[f.id] !== 1 ? 's' : ''}
                            </span>
                          )
                          : <span className="badge badge-success"><span className="badge-dot" /> Online</span>}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <button className="icon-btn-sm" title="Delete facility" onClick={e => {
                          e.stopPropagation()
                          if (confirm(`Delete "${f.name}"? This cannot be undone.`)) deleteFacility.mutate(f.id)
                        }}>
                          <Trash2 size={14} />
                        </button>
                        <ChevronRight size={16} style={{ opacity: 0.3 }} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showAddModal && <AddFacilityModal onClose={() => setShowAddModal(false)} />}
    </div>
  )
}

function AddFacilityModal({ onClose }: { onClose: () => void }) {
  const createFacility = useCreateFacility()
  const [form, setForm] = useState({ name: '', city: '', state: '', sqft: '' })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    createFacility.mutate(
      { name: form.name, city: form.city || undefined, state: form.state || undefined, sqft: form.sqft ? parseInt(form.sqft) : undefined },
      {
        onSuccess: () => { toast.success('Facility created'); onClose() },
        onError: () => toast.error('Failed to create facility'),
      }
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Facility</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Facility name</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Main Distribution Center" required autoFocus />
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 2 }}><label>City</label><input value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} placeholder="Dallas" /></div>
            <div className="field" style={{ flex: 1 }}><label>State</label><input value={form.state} onChange={e => setForm({ ...form, state: e.target.value.toUpperCase() })} placeholder="TX" maxLength={2} /></div>
          </div>
          <div className="field">
            <label>Square footage</label>
            <input type="number" value={form.sqft} onChange={e => setForm({ ...form, sqft: e.target.value })} placeholder="250000" />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createFacility.isPending}>{createFacility.isPending ? 'Adding...' : <><Plus size={15} /> Add Facility</>}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
