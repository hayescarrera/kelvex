import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  ShieldCheck, AlertTriangle, RefreshCw, TrendingUp, Wrench,
  Droplets, ArrowRight, Download, Thermometer, CheckCircle,
  Clock, Plus, FileCheck, FileSignature, X,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { useSiteContext } from '../contexts/SiteContext'
import { api } from '../lib/api'
import type {
  AIMActSummary, RefrigerantDashboard, RepairRecord,
  CircuitForecast, DetectionSettings, DetectionInsights,
  CCP, ComplianceLogEntry, TempExcursionEntry, ComplianceReportEntry, ComplianceDashboard,
} from '../lib/api'

type Tab = 'overview' | 'leak-rates' | 'haccp'

function aimActStatusBadge(status: string) {
  const map: Record<string, string> = {
    compliant: 'badge-success',
    warning: 'badge-warning',
    exceeds_threshold: 'badge-danger',
    no_charge_data: 'badge-neutral',
  }
  return map[status] ?? 'badge-neutral'
}

function aimActStatusLabel(status: string) {
  const map: Record<string, string> = {
    compliant: 'Compliant',
    warning: 'Warning',
    exceeds_threshold: 'Exceeds Threshold',
    no_charge_data: 'No Charge Data',
  }
  return map[status] ?? status
}

function haccpStatusColor(s: string) {
  switch (s) {
    case 'pass': return 'var(--success)'
    case 'warning': return 'var(--warning)'
    case 'critical': return 'var(--danger)'
    default: return 'var(--text-secondary)'
  }
}

function TabBar({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'leak-rates', label: 'Leak Rates (AIM Act)' },
    { id: 'haccp', label: 'HACCP' },
  ]
  return (
    <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)', marginBottom: 24 }}>
      {tabs.map(t => (
        <button
          key={t.id}
          onClick={() => setTab(t.id)}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: tab === t.id ? 600 : 400,
            color: tab === t.id ? 'var(--accent)' : 'var(--text-secondary)',
            borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
            background: 'none', border: 'none', cursor: 'pointer', marginBottom: -1,
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export default function CompliancePage() {
  const { site } = useSiteContext()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)

  // Refrigerant / AIM Act state
  const [dashboard, setDashboard] = useState<RefrigerantDashboard | null>(null)
  const [aimAct, setAimAct] = useState<AIMActSummary | null>(null)
  const [repairs, setRepairs] = useState<RepairRecord[]>([])
  const [forecasts, setForecasts] = useState<CircuitForecast[]>([])
  const [insights, setInsights] = useState<DetectionInsights | null>(null)
  const [detectionSettings, setDetectionSettings] = useState<DetectionSettings | null>(null)

  // HACCP state (lazy-loaded on first tab open)
  const [haccpLoading, setHaccpLoading] = useState(false)
  const [haccpLoaded, setHaccpLoaded] = useState(false)
  const [compDashboard, setCompDashboard] = useState<ComplianceDashboard | null>(null)
  const [ccps, setCCPs] = useState<CCP[]>([])
  const [compLogs, setCompLogs] = useState<ComplianceLogEntry[]>([])
  const [excursions, setExcursions] = useState<TempExcursionEntry[]>([])
  const [compReports, setCompReports] = useState<ComplianceReportEntry[]>([])
  const [showCreateCCP, setShowCreateCCP] = useState(false)
  const [ccpForm, setCCPForm] = useState({
    name: '', temp_min: '', temp_max: '', temp_unit: 'degF',
    hazard_type: 'biological', corrective_action: '',
    check_interval_min: '15', excursion_threshold_min: '30', warning_offset: '2',
  })

  const facilityId = site?.id

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [dashRes, aimRes, repairRes, settingsRes] = await Promise.all([
        api.getRefrigerantDashboard(facilityId).catch(() => null),
        api.getAIMActSummary(facilityId).catch(() => null),
        api.listRepairs(facilityId ? { facility_id: facilityId, limit: 30 } : { limit: 30 }).catch(() => ({ repairs: [], total: 0 })),
        api.getDetectionSettings().catch(() => null),
      ])
      setDashboard(dashRes)
      setAimAct(aimRes)
      setRepairs(repairRes.repairs)
      setDetectionSettings(settingsRes)
      if (settingsRes?.forecasting || settingsRes?.auto_detection) {
        const [forecastRes, insightRes] = await Promise.all([
          settingsRes.forecasting
            ? api.getDetectionForecasts(facilityId).catch(() => [])
            : Promise.resolve([]),
          api.getDetectionInsights(facilityId).catch(() => null),
        ])
        setForecasts(forecastRes ?? [])
        setInsights(insightRes)
      } else {
        setForecasts([])
        setInsights(null)
      }
    } catch (err) {
      console.error('CompliancePage load error:', err)
    } finally {
      setLoading(false)
    }
  }, [facilityId])

  const loadHaccp = useCallback(async () => {
    setHaccpLoading(true)
    try {
      const [cDashRes, ccpRes, logRes, excRes, rptRes] = await Promise.all([
        api.getComplianceDashboard(facilityId).catch(() => null),
        api.listCCPs(facilityId).catch(() => ({ ccps: [], total: 0 })),
        api.listComplianceLogs(facilityId ? { facility_id: facilityId } : undefined).catch(() => ({ logs: [], total: 0 })),
        api.listExcursions(facilityId ? { facility_id: facilityId } : undefined).catch(() => ({ excursions: [], total: 0 })),
        api.listComplianceReports(facilityId ? { facility_id: facilityId } : undefined).catch(() => ({ reports: [], total: 0 })),
      ])
      setCompDashboard(cDashRes)
      setCCPs(ccpRes.ccps)
      setCompLogs(logRes.logs)
      setExcursions(excRes.excursions)
      setCompReports(rptRes.reports)
      setHaccpLoaded(true)
    } catch (err) {
      console.error('HACCP load error:', err)
    } finally {
      setHaccpLoading(false)
    }
  }, [facilityId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (tab === 'haccp' && !haccpLoaded) loadHaccp()
  }, [tab, haccpLoaded, loadHaccp])

  // Reset HACCP cache when facility changes
  useEffect(() => { setHaccpLoaded(false) }, [facilityId])

  async function handleCreateCCP() {
    if (!facilityId) { toast.error('Select a facility first'); return }
    if (!ccpForm.name || !ccpForm.temp_min || !ccpForm.temp_max) {
      toast.error('Name and temperature limits are required'); return
    }
    try {
      await api.createCCP({
        facility_id: facilityId,
        name: ccpForm.name,
        temp_min: parseFloat(ccpForm.temp_min),
        temp_max: parseFloat(ccpForm.temp_max),
        temp_unit: ccpForm.temp_unit,
        warning_offset: parseFloat(ccpForm.warning_offset),
        check_interval_min: parseInt(ccpForm.check_interval_min),
        excursion_threshold_min: parseInt(ccpForm.excursion_threshold_min),
        hazard_type: ccpForm.hazard_type,
        corrective_action: ccpForm.corrective_action || undefined,
      })
      toast.success('CCP created')
      setShowCreateCCP(false)
      setCCPForm({ name: '', temp_min: '', temp_max: '', temp_unit: 'degF', hazard_type: 'biological', corrective_action: '', check_interval_min: '15', excursion_threshold_min: '30', warning_offset: '2' })
      loadHaccp()
    } catch { toast.error('Failed to create CCP') }
  }

  async function handleGenerateReport(type: string) {
    if (!facilityId) { toast.error('Select a facility first'); return }
    try {
      await api.generateComplianceReport({ facility_id: facilityId, report_type: type })
      toast.success(`${type} report generated`)
      loadHaccp()
    } catch { toast.error('Failed to generate report') }
  }

  async function handleSignOff(reportId: string) {
    try {
      await api.signOffReport(reportId)
      toast.success('Report signed off')
      loadHaccp()
    } catch { toast.error('Failed to sign off') }
  }

  async function handleResolveExcursion(excId: string) {
    try {
      await api.resolveExcursion(excId, { state: 'resolved' })
      toast.success('Excursion resolved')
      loadHaccp()
    } catch { toast.error('Failed to resolve') }
  }

  const forecastByCircuit = Object.fromEntries((forecasts ?? []).map(f => [f.circuit_id, f]))
  const hasForecast = detectionSettings?.forecasting === true && forecasts.length > 0

  if (loading) {
    return (
      <div className="page-container">
        <PageHeader title="Compliance" subtitle="AIM-Act refrigerant tracking, leak rates, and HACCP records" />
        <LoadingState label="Loading compliance data..." />
      </div>
    )
  }

  const currentYear = new Date().getFullYear()
  const repairsThisYear = repairs.filter(r => new Date(r.repaired_at).getFullYear() === currentYear).length

  return (
    <div className="page-container">
      <PageHeader
        title="Compliance"
        subtitle="AIM-Act refrigerant tracking, leak rates, and HACCP records"
      >
        <button className="btn-secondary" onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </PageHeader>

      <TabBar tab={tab} setTab={setTab} />

      {/* ── OVERVIEW TAB ──────────────────────────────────────────────────────── */}
      {tab === 'overview' && (
        <div>
          <div className="stat-grid stagger" style={{ marginBottom: 24 }}>
            <StatCard
              icon={<Droplets size={18} />}
              color="var(--warning)"
              value={`${(aimAct?.facility_summary.total_added_lbs ?? 0).toFixed(1)} lbs`}
              label="Total Refrigerant Added (12mo)"
            />
            <StatCard
              icon={<AlertTriangle size={18} />}
              color={(aimAct?.facility_summary.circuits_above_threshold ?? 0) > 0 ? 'var(--danger)' : 'var(--success)'}
              value={String(aimAct?.facility_summary.circuits_above_threshold ?? 0)}
              label="Circuits Above Warning"
            />
            <StatCard
              icon={<AlertTriangle size={18} />}
              color={(dashboard?.open_leak_events ?? 0) > 0 ? 'var(--danger)' : 'var(--success)'}
              value={String(dashboard?.open_leak_events ?? 0)}
              label="Open Leak Events"
            />
            <StatCard
              icon={<Wrench size={18} />}
              color="var(--info)"
              value={String(repairsThisYear)}
              label="Repairs This Year"
            />
          </div>

          {aimAct && aimAct.circuits.length > 0 && (
            <div className="card" style={{ marginBottom: 20 }}>
              <div className="card-header">
                <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <ShieldCheck size={15} /> AIM Act Circuit Status
                </h3>
                <button className="btn-ghost" style={{ fontSize: 12 }} onClick={() => setTab('leak-rates')}>
                  Full report <ArrowRight size={12} />
                </button>
              </div>
              <div className="card-body" style={{ padding: 0 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Circuit</th>
                      <th>Leak Rate (15% threshold)</th>
                      <th>Status</th>
                      <th>Open Leaks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...aimAct.circuits].sort((a, b) => (b.leak_rate_pct ?? 0) - (a.leak_rate_pct ?? 0)).slice(0, 8).map((c, i) => {
                      const pct = c.leak_rate_pct ?? 0
                      const barColor = pct >= 15 ? 'var(--danger)' : pct >= 10 ? 'var(--warning)' : 'var(--success)'
                      const remaining = Math.max(0, 15 - pct)
                      return (
                        <tr key={c.circuit_id ?? i}>
                          <td>
                            <span className="cell-primary">{c.circuit_name}</span>
                            <span className="cell-secondary">{c.rack_name} · {c.refrigerant_type}</span>
                          </td>
                          <td style={{ minWidth: 160 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <div style={{ flex: 1, height: 6, background: 'var(--bg-tertiary)', borderRadius: 3, overflow: 'hidden' }}>
                                <div style={{
                                  height: '100%', width: `${Math.min(100, (pct / 20) * 100)}%`,
                                  background: barColor, borderRadius: 3, transition: 'width 0.3s ease',
                                }} />
                              </div>
                              <span style={{ fontSize: 12, fontWeight: 700, fontFamily: 'monospace', color: barColor, minWidth: 36 }}>
                                {pct > 0 ? `${pct.toFixed(1)}%` : '—'}
                              </span>
                            </div>
                            {pct > 0 && pct < 15 && (
                              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                                {remaining.toFixed(1)}% remaining before threshold
                              </div>
                            )}
                          </td>
                          <td>
                            <span className={`badge ${aimActStatusBadge(c.status)}`}>{aimActStatusLabel(c.status)}</span>
                          </td>
                          <td style={{ textAlign: 'center', fontSize: 13, fontWeight: c.open_leak_events > 0 ? 700 : 400,
                            color: c.open_leak_events > 0 ? 'var(--danger)' : 'var(--text-secondary)' }}>
                            {c.open_leak_events > 0 ? `⚠ ${c.open_leak_events}` : c.open_leak_events}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="card">
            <div className="card-header"><h3>Quick Actions</h3></div>
            <div className="card-body" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <button
                className="btn-primary"
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                onClick={() => { toast.loading('Generating compliance report...', { duration: 2500 }) }}
              >
                <Download size={14} /> Export Compliance Report
              </button>
              <button
                className="btn-secondary"
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                onClick={() => navigate('/leak-tracking')}
              >
                <Droplets size={14} /> Log Refrigerant Add
              </button>
              <button
                className="btn-secondary"
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                onClick={() => setTab('leak-rates')}
              >
                <TrendingUp size={14} /> View Leak Rates
              </button>
              <button
                className="btn-secondary"
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                onClick={() => setTab('haccp')}
              >
                <ShieldCheck size={14} /> HACCP Records
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── LEAK RATES TAB ──────────────────────────────────────────────────── */}
      {tab === 'leak-rates' && (
        <div>
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card-body">
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                <ShieldCheck size={20} style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 2 }} />
                <div>
                  <div style={{ fontWeight: 600, marginBottom: 6 }}>AIM Act Leak Rate Requirements</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    AIM Act requires leak rate tracking for systems with 50+ lbs of refrigerant. Threshold for commercial refrigeration: <strong>15% annual leak rate</strong>.
                    Leak rate is calculated as total refrigerant added over 12 months divided by the full circuit charge. Warning threshold begins at 10%.
                    Facilities exceeding the threshold may be subject to reporting requirements and corrective action mandates.
                  </div>
                </div>
              </div>
            </div>
          </div>

          {aimAct && (
            <div className="stat-grid stagger" style={{ marginBottom: 20 }}>
              <StatCard icon={<ShieldCheck size={18} />} color="var(--accent)"
                value={String(aimAct.circuits.length)} label="Circuits Monitored" />
              <StatCard
                icon={<AlertTriangle size={18} />}
                color="var(--warning)"
                value={String(aimAct.circuits.filter(c => c.status === 'warning').length)}
                label="Above Warning (>10%)"
              />
              <StatCard
                icon={<AlertTriangle size={18} />}
                color="var(--danger)"
                value={String(aimAct.facility_summary.circuits_above_threshold)}
                label="Above Threshold (>15%)"
              />
              {hasForecast ? (
                <StatCard
                  icon={<TrendingUp size={18} />}
                  color="var(--info)"
                  value={String(insights?.circuits_approaching_threshold ?? 0)}
                  label="Approaching Threshold (forecast)"
                />
              ) : (
                <StatCard
                  icon={<Droplets size={18} />}
                  color="var(--info)"
                  value={`${aimAct.facility_summary.total_added_lbs.toFixed(1)} lbs`}
                  label={`Total Added (${aimAct.period_days}d)`}
                />
              )}
            </div>
          )}

          {detectionSettings?.auto_detection && insights && insights.auto_detected_events > 0 && (
            <div style={{ marginBottom: 16, padding: '10px 16px', background: 'color-mix(in srgb, var(--accent) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--accent) 20%, transparent)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
              <TrendingUp size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              <span>
                <strong>{insights.auto_detected_events}</strong> leak event{insights.auto_detected_events !== 1 ? 's' : ''} auto-detected this period
                {insights.detection_breakdown.multi_signal > 0 && ` — ${insights.detection_breakdown.multi_signal} multi-signal confirmed`}
                {insights.detection_breakdown.pressure_trend > 0 && `, ${insights.detection_breakdown.pressure_trend} pressure trend`}
              </span>
            </div>
          )}

          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              {!aimAct || aimAct.circuits.length === 0 ? (
                <EmptyState
                  icon={<ShieldCheck size={24} />}
                  title="No circuit data"
                  description="Add refrigerant circuits in the Leak Tracking page and log refrigerant adds to enable AIM Act compliance monitoring."
                />
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Circuit</th>
                      <th>Refrigerant Type</th>
                      <th>Full Charge (lbs)</th>
                      <th>Added (12mo lbs)</th>
                      <th>Leak Rate</th>
                      <th>Status</th>
                      <th>Open Leaks</th>
                      {hasForecast && <th>Forecast (365d)</th>}
                      {hasForecast && <th>Days to Warning</th>}
                      {hasForecast && <th>Days to Threshold</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {aimAct.circuits.map((c, i) => {
                      const fc = c.circuit_id ? forecastByCircuit[c.circuit_id] : undefined
                      return (
                        <tr key={c.circuit_id ?? i}>
                          <td>
                            <span className="cell-primary">{c.circuit_name}</span>
                            <span className="cell-secondary">{c.rack_name}</span>
                          </td>
                          <td style={{ fontSize: 12 }}>{c.refrigerant_type}</td>
                          <td style={{ fontFamily: 'monospace', fontSize: 13 }}>
                            {c.full_charge_lbs != null ? c.full_charge_lbs.toFixed(1) : ''}
                          </td>
                          <td style={{ fontFamily: 'monospace', fontSize: 13, fontWeight: 600 }}>
                            {c.total_added_lbs.toFixed(1)}
                          </td>
                          <td style={{
                            fontFamily: 'monospace', fontSize: 14, fontWeight: 700,
                            color: c.leak_rate_pct != null && c.leak_rate_pct >= 15 ? 'var(--danger)' :
                              c.leak_rate_pct != null && c.leak_rate_pct >= 10 ? 'var(--warning)' : 'var(--text-primary)',
                          }}>
                            {c.leak_rate_pct != null ? `${c.leak_rate_pct.toFixed(1)}%` : ''}
                          </td>
                          <td>
                            <span className={`badge ${aimActStatusBadge(c.status)}`}>
                              {aimActStatusLabel(c.status)}
                            </span>
                          </td>
                          <td style={{ textAlign: 'center', fontSize: 13, fontWeight: c.open_leak_events > 0 ? 700 : 400,
                            color: c.open_leak_events > 0 ? 'var(--danger)' : 'var(--text-secondary)' }}>
                            {c.open_leak_events}
                          </td>
                          {hasForecast && (
                            <td style={{ fontFamily: 'monospace', fontSize: 13 }}>
                              {fc?.projected_adds_lbs != null
                                ? <>{fc.projected_adds_lbs.toFixed(1)} lbs{fc.confidence && <span style={{ marginLeft: 4, fontSize: 10, color: 'var(--text-muted)' }}>({fc.confidence})</span>}</>
                                : ''}
                            </td>
                          )}
                          {hasForecast && (
                            <td style={{ fontSize: 13, fontWeight: fc?.days_to_aim_warning != null && fc.days_to_aim_warning < 60 ? 700 : 400,
                              color: fc?.days_to_aim_warning != null && fc.days_to_aim_warning < 60 ? 'var(--warning)' : 'var(--text-secondary)' }}>
                              {fc?.days_to_aim_warning != null ? `${fc.days_to_aim_warning}d` : ''}
                            </td>
                          )}
                          {hasForecast && (
                            <td style={{ fontSize: 13, fontWeight: fc?.days_to_aim_threshold != null && fc.days_to_aim_threshold < 30 ? 700 : 400,
                              color: fc?.days_to_aim_threshold != null && fc.days_to_aim_threshold < 30 ? 'var(--danger)' : 'var(--text-secondary)' }}>
                              {fc?.days_to_aim_threshold != null ? `${fc.days_to_aim_threshold}d` : ''}
                            </td>
                          )}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div style={{ marginTop: 16, padding: '12px 16px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Leak rate is calculated as total refrigerant added over 12 months divided by the full circuit charge. Set circuit charge in the Leak Tracking &gt; Circuits tab to enable leak rate tracking.
          </div>
        </div>
      )}

      {/* ── HACCP TAB ───────────────────────────────────────────────────────── */}
      {tab === 'haccp' && (
        <div>
          {haccpLoading ? (
            <LoadingState label="Loading HACCP data..." />
          ) : (
            <>
              {compDashboard && (
                <div className="stat-grid stagger" style={{ marginBottom: 20 }}>
                  <StatCard label="Active CCPs" value={String(compDashboard.active_ccps)} color="var(--accent)" icon={<ShieldCheck size={16} />} />
                  <StatCard label="Checks (24h)" value={String(compDashboard.checks_24h)} color="var(--info)" icon={<Thermometer size={16} />} />
                  <StatCard label="Pass Rate (24h)" value={`${compDashboard.pass_rate_24h}%`} color={compDashboard.pass_rate_24h >= 95 ? 'var(--success)' : 'var(--warning)'} icon={<CheckCircle size={16} />} />
                  <StatCard label="Active Excursions" value={String(compDashboard.active_excursions)} color={compDashboard.active_excursions > 0 ? 'var(--danger)' : 'var(--success)'} icon={<AlertTriangle size={16} />} />
                  <StatCard label="Excursions (7d)" value={String(compDashboard.excursions_this_week)} color="var(--warning)" icon={<Clock size={16} />} />
                  <StatCard label="Pending Reports" value={String(compDashboard.pending_reports)} color="var(--info)" icon={<FileCheck size={16} />} />
                </div>
              )}

              <div className="card" style={{ marginBottom: 20 }}>
                <div className="card-header">Quick Actions</div>
                <div className="card-body" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  <button className="btn-primary" onClick={() => setShowCreateCCP(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ShieldCheck size={14} /> Add Control Point
                  </button>
                  <button className="btn-secondary" onClick={() => handleGenerateReport('daily')} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <FileCheck size={14} /> Generate Daily Report
                  </button>
                  <button className="btn-secondary" onClick={() => handleGenerateReport('weekly')} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <FileCheck size={14} /> Generate Weekly Report
                  </button>
                </div>
              </div>

              {excursions.filter(e => e.state === 'active').length > 0 && (
                <div className="card" style={{ marginBottom: 20 }}>
                  <div className="card-header" style={{ color: 'var(--danger)' }}>
                    <AlertTriangle size={14} style={{ marginRight: 6 }} /> Active Temperature Excursions
                  </div>
                  <div className="card-body" style={{ padding: 0 }}>
                    {excursions.filter(e => e.state === 'active').map(exc => (
                      <div key={exc.id} style={{
                        padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)',
                        display: 'flex', alignItems: 'center', gap: 12,
                      }}>
                        <div style={{ width: 8, height: 8, borderRadius: '50%', background: exc.severity === 'critical' ? 'var(--danger)' : 'var(--warning)' }} />
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 13, fontWeight: 600 }}>
                            {exc.severity.toUpperCase()} — Peak: {exc.peak_temp}°
                          </div>
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            {exc.limit_breached === 'high' ? 'Over max limit' : 'Under min limit'} · Started {new Date(exc.started_at).toLocaleString()}
                          </div>
                        </div>
                        <button className="btn-secondary" onClick={() => handleResolveExcursion(exc.id)} style={{ fontSize: 12 }}>
                          Resolve
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="card" style={{ marginBottom: 20 }}>
                <div className="card-header">
                  <h3>Critical Control Points (HACCP)</h3>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {ccps.length === 0 ? (
                    <EmptyState
                      icon={<ShieldCheck size={24} />}
                      title="No Critical Control Points"
                      description="Create your first CCP to start HACCP temperature monitoring."
                    />
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Limits</th>
                          <th>Check Interval</th>
                          <th>Hazard</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ccps.map(ccp => (
                          <tr key={ccp.id}>
                            <td>
                              <div style={{ fontWeight: 600 }}>{ccp.name}</div>
                              {ccp.description && <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{ccp.description}</div>}
                            </td>
                            <td>
                              <span style={{ fontFamily: 'monospace', fontSize: 13 }}>
                                {ccp.temp_min}° – {ccp.temp_max}° {ccp.temp_unit === 'degF' ? 'F' : 'C'}
                              </span>
                              <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Warning: ±{ccp.warning_offset}°</div>
                            </td>
                            <td>{ccp.check_interval_min} min</td>
                            <td>
                              {ccp.hazard_type && (
                                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 10, background: 'var(--bg-secondary)', textTransform: 'capitalize' }}>
                                  {ccp.hazard_type}
                                </span>
                              )}
                            </td>
                            <td>
                              {ccp.is_active
                                ? <span className="badge badge-success"><span className="badge-dot" /> Active</span>
                                : <span className="badge badge-neutral">Inactive</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              <div className="card" style={{ marginBottom: 20 }}>
                <div className="card-header">
                  <h3>Temperature Check Log (24h)</h3>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {compLogs.length === 0 ? (
                    <EmptyState
                      icon={<Thermometer size={24} />}
                      title="No compliance checks"
                      description="Checks will appear here as they are recorded."
                    />
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Time</th>
                          <th>Temperature</th>
                          <th>Limits</th>
                          <th>Status</th>
                          <th>Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {compLogs.map(log => (
                          <tr key={log.id}>
                            <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{new Date(log.checked_at).toLocaleString()}</td>
                            <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                              {log.temperature}° {log.temp_unit === 'degF' ? 'F' : 'C'}
                            </td>
                            <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                              {log.limit_min}° – {log.limit_max}°
                            </td>
                            <td>
                              <span style={{
                                fontSize: 11, padding: '2px 8px', borderRadius: 10,
                                fontWeight: 600, textTransform: 'uppercase',
                                color: haccpStatusColor(log.status),
                                background: `color-mix(in srgb, ${haccpStatusColor(log.status)} 15%, transparent)`,
                              }}>
                                {log.status}
                              </span>
                            </td>
                            <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{log.source}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              <div className="card" style={{ marginBottom: 20 }}>
                <div className="card-header">
                  <h3>Temperature Excursions</h3>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {excursions.length === 0 ? (
                    <EmptyState
                      icon={<CheckCircle size={24} />}
                      title="No excursions"
                      description="No temperature excursions in the selected period."
                    />
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Started</th>
                          <th>Severity</th>
                          <th>Peak Temp</th>
                          <th>Duration</th>
                          <th>Breach</th>
                          <th>State</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {excursions.map(exc => (
                          <tr key={exc.id}>
                            <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{new Date(exc.started_at).toLocaleString()}</td>
                            <td>
                              <span style={{
                                fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600, textTransform: 'uppercase',
                                color: exc.severity === 'critical' ? 'var(--danger)' : 'var(--warning)',
                                background: exc.severity === 'critical' ? 'color-mix(in srgb, var(--danger) 15%, transparent)' : 'color-mix(in srgb, var(--warning) 15%, transparent)',
                              }}>
                                {exc.severity}
                              </span>
                            </td>
                            <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>{exc.peak_temp}°</td>
                            <td>{exc.duration_minutes ? `${exc.duration_minutes} min` : 'Ongoing'}</td>
                            <td style={{ fontSize: 12 }}>{exc.limit_breached === 'high' ? 'Over max' : 'Under min'}</td>
                            <td>
                              <span style={{
                                fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                                color: exc.state === 'active' ? 'var(--danger)' : exc.state === 'resolved' ? 'var(--success)' : 'var(--warning)',
                                background: exc.state === 'active' ? 'color-mix(in srgb, var(--danger) 15%, transparent)' : exc.state === 'resolved' ? 'color-mix(in srgb, var(--success) 15%, transparent)' : 'color-mix(in srgb, var(--warning) 15%, transparent)',
                              }}>
                                {exc.state}
                              </span>
                            </td>
                            <td>
                              {exc.state === 'active' && (
                                <button className="btn-secondary" onClick={() => handleResolveExcursion(exc.id)} style={{ fontSize: 11, padding: '4px 10px' }}>
                                  Resolve
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              <div className="card">
                <div className="card-header">
                  <h3>Compliance Reports</h3>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn-secondary" onClick={() => handleGenerateReport('daily')} style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
                      <FileCheck size={13} /> Daily
                    </button>
                    <button className="btn-secondary" onClick={() => handleGenerateReport('weekly')} style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
                      <FileCheck size={13} /> Weekly
                    </button>
                    <button className="btn-secondary" onClick={() => handleGenerateReport('monthly')} style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
                      <FileCheck size={13} /> Monthly
                    </button>
                  </div>
                </div>
                <div className="card-body" style={{ padding: 0 }}>
                  {compReports.length === 0 ? (
                    <EmptyState
                      icon={<FileCheck size={24} />}
                      title="No reports"
                      description="Generate a compliance report to get started."
                    />
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Title</th>
                          <th>Period</th>
                          <th>Compliance</th>
                          <th>Checks</th>
                          <th>Excursions</th>
                          <th>State</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {compReports.map(rpt => (
                          <tr key={rpt.id}>
                            <td>
                              <div style={{ fontWeight: 600, fontSize: 13 }}>{rpt.title}</div>
                              <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{rpt.report_type}</div>
                            </td>
                            <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                              {new Date(rpt.period_start).toLocaleDateString()} — {new Date(rpt.period_end).toLocaleDateString()}
                            </td>
                            <td>
                              <span style={{
                                fontWeight: 700, fontSize: 14,
                                color: rpt.compliance_pct >= 95 ? 'var(--success)' : rpt.compliance_pct >= 80 ? 'var(--warning)' : 'var(--danger)',
                              }}>
                                {rpt.compliance_pct}%
                              </span>
                            </td>
                            <td>
                              <span style={{ color: 'var(--success)' }}>{rpt.passed_checks}</span>
                              {' / '}
                              <span>{rpt.total_checks}</span>
                              {rpt.failed_checks > 0 && <span style={{ color: 'var(--danger)', marginLeft: 4 }}>({rpt.failed_checks} failed)</span>}
                            </td>
                            <td>
                              <span style={{ color: rpt.excursion_count > 0 ? 'var(--danger)' : 'var(--success)' }}>
                                {rpt.excursion_count}
                              </span>
                            </td>
                            <td>
                              <span style={{
                                fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600, textTransform: 'uppercase',
                                color: rpt.state === 'signed_off' ? 'var(--success)' : rpt.state === 'pending_review' ? 'var(--warning)' : 'var(--text-secondary)',
                                background: rpt.state === 'signed_off' ? 'color-mix(in srgb, var(--success) 15%, transparent)' : 'var(--bg-secondary)',
                              }}>
                                {rpt.state.replace('_', ' ')}
                              </span>
                            </td>
                            <td>
                              {rpt.state !== 'signed_off' && (
                                <button className="btn-secondary" onClick={() => handleSignOff(rpt.id)}
                                  style={{ fontSize: 11, padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 4 }}>
                                  <FileSignature size={12} /> Sign Off
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Create CCP Modal */}
      {showCreateCCP && (
        <div className="modal-overlay" onClick={() => setShowCreateCCP(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
            <div className="modal-header">
              <h3>New Critical Control Point</h3>
              <button className="icon-btn" onClick={() => setShowCreateCCP(false)}><X size={18} /></button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label className="form-label">Name *</label>
                <input type="text" className="form-input" placeholder="e.g. Freezer A Zone 1"
                  value={ccpForm.name} onChange={e => setCCPForm({ ...ccpForm, name: e.target.value })} />
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Min Temp *</label>
                  <input type="number" className="form-input" placeholder="-10"
                    value={ccpForm.temp_min} onChange={e => setCCPForm({ ...ccpForm, temp_min: e.target.value })} />
                </div>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Max Temp *</label>
                  <input type="number" className="form-input" placeholder="0"
                    value={ccpForm.temp_max} onChange={e => setCCPForm({ ...ccpForm, temp_max: e.target.value })} />
                </div>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Unit</label>
                  <select className="form-select" value={ccpForm.temp_unit} onChange={e => setCCPForm({ ...ccpForm, temp_unit: e.target.value })}>
                    <option value="degF">°F</option>
                    <option value="degC">°C</option>
                  </select>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Warning Offset</label>
                  <input type="number" className="form-input" value={ccpForm.warning_offset}
                    onChange={e => setCCPForm({ ...ccpForm, warning_offset: e.target.value })} />
                </div>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Check Interval (min)</label>
                  <input type="number" className="form-input" value={ccpForm.check_interval_min}
                    onChange={e => setCCPForm({ ...ccpForm, check_interval_min: e.target.value })} />
                </div>
              </div>
              <div>
                <label className="form-label">Hazard Type</label>
                <select className="form-select" value={ccpForm.hazard_type} onChange={e => setCCPForm({ ...ccpForm, hazard_type: e.target.value })}>
                  <option value="biological">Biological</option>
                  <option value="chemical">Chemical</option>
                  <option value="physical">Physical</option>
                </select>
              </div>
              <div>
                <label className="form-label">Corrective Action</label>
                <textarea className="form-input" rows={2} placeholder="Describe corrective action on excursion..."
                  value={ccpForm.corrective_action} onChange={e => setCCPForm({ ...ccpForm, corrective_action: e.target.value })} />
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowCreateCCP(false)}>Cancel</button>
              <button className="btn-primary" onClick={handleCreateCCP} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Plus size={14} /> Create CCP
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
