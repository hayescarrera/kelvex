import { useState, useEffect, useCallback } from 'react'
import {
  Loader2, ShieldCheck, Thermometer, AlertTriangle, FileCheck,
  Plus, CheckCircle, Clock, RefreshCw,
  FileSignature,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import { api } from '../lib/api'
import { useSiteContext } from '../contexts/SiteContext'
import toast from 'react-hot-toast'
import type {
  CCP, ComplianceLogEntry, TempExcursionEntry,
  ComplianceReportEntry, ComplianceDashboard,
} from '../lib/api'

type Tab = 'dashboard' | 'ccps' | 'logs' | 'excursions' | 'reports'

export default function CompliancePage() {
  const { site } = useSiteContext()
  const [tab, setTab] = useState<Tab>('dashboard')
  const [dashboard, setDashboard] = useState<ComplianceDashboard | null>(null)
  const [ccps, setCCPs] = useState<CCP[]>([])
  const [logs, setLogs] = useState<ComplianceLogEntry[]>([])
  const [excursions, setExcursions] = useState<TempExcursionEntry[]>([])
  const [reports, setReports] = useState<ComplianceReportEntry[]>([])
  const [loading, setLoading] = useState(true)

  // CCP create modal
  const [showCreate, setShowCreate] = useState(false)
  const [ccpForm, setCCPForm] = useState({
    name: '', temp_min: '', temp_max: '', temp_unit: 'degF',
    hazard_type: 'biological', corrective_action: '',
    check_interval_min: '15', excursion_threshold_min: '30', warning_offset: '2',
  })

  const facilityId = site?.id

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [dashRes, ccpRes, logRes, excRes, rptRes] = await Promise.all([
        api.getComplianceDashboard(facilityId),
        api.listCCPs(facilityId),
        api.listComplianceLogs(facilityId ? { facility_id: facilityId } : undefined),
        api.listExcursions(facilityId ? { facility_id: facilityId } : undefined),
        api.listComplianceReports(facilityId ? { facility_id: facilityId } : undefined),
      ])
      setDashboard(dashRes)
      setCCPs(ccpRes.ccps)
      setLogs(logRes.logs)
      setExcursions(excRes.excursions)
      setReports(rptRes.reports)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [facilityId])

  useEffect(() => { load() }, [load])

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
      setShowCreate(false)
      setCCPForm({ name: '', temp_min: '', temp_max: '', temp_unit: 'degF', hazard_type: 'biological', corrective_action: '', check_interval_min: '15', excursion_threshold_min: '30', warning_offset: '2' })
      load()
    } catch { toast.error('Failed to create CCP') }
  }

  async function handleGenerateReport(type: string) {
    if (!facilityId) { toast.error('Select a facility first'); return }
    try {
      await api.generateComplianceReport({ facility_id: facilityId, report_type: type })
      toast.success(`${type} report generated`)
      load()
    } catch { toast.error('Failed to generate report') }
  }

  async function handleSignOff(reportId: string) {
    try {
      await api.signOffReport(reportId)
      toast.success('Report signed off')
      load()
    } catch { toast.error('Failed to sign off') }
  }

  async function handleResolveExcursion(excId: string) {
    try {
      await api.resolveExcursion(excId, { state: 'resolved' })
      toast.success('Excursion resolved')
      load()
    } catch { toast.error('Failed to resolve') }
  }

  const statusColor = (s: string) => {
    switch (s) {
      case 'pass': return 'var(--success)'
      case 'warning': return 'var(--warning)'
      case 'critical': return 'var(--danger)'
      default: return 'var(--text-secondary)'
    }
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: 'dashboard', label: 'Overview' },
    { id: 'ccps', label: 'Control Points' },
    { id: 'logs', label: 'Check Log' },
    { id: 'excursions', label: 'Excursions' },
    { id: 'reports', label: 'Reports' },
  ]

  return (
    <div className="page-container">
      <PageHeader
        title="HACCP Compliance"
        subtitle="FDA/HACCP temperature monitoring, excursions, and audit reports"
      >
        <button className="btn-secondary" onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </PageHeader>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: tab === t.id ? 600 : 400,
              color: tab === t.id ? 'var(--accent)' : 'var(--text-secondary)',
              borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
              background: 'none', border: 'none', borderBottomStyle: 'solid', cursor: 'pointer',
              marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <Loader2 size={24} className="spin" />
        </div>
      ) : (
        <>
          {/* Dashboard Tab */}
          {tab === 'dashboard' && dashboard && (
            <div>
              <div className="stat-grid" style={{ marginBottom: 20 }}>
                <StatCard label="Active CCPs" value={String(dashboard.active_ccps)} color="var(--accent)" icon={<ShieldCheck size={16} />} />
                <StatCard label="Checks (24h)" value={String(dashboard.checks_24h)} color="var(--info)" icon={<Thermometer size={16} />} />
                <StatCard label="Pass Rate (24h)" value={`${dashboard.pass_rate_24h}%`} color={dashboard.pass_rate_24h >= 95 ? 'var(--success)' : 'var(--warning)'} icon={<CheckCircle size={16} />} />
                <StatCard label="Active Excursions" value={String(dashboard.active_excursions)} color={dashboard.active_excursions > 0 ? 'var(--danger)' : 'var(--success)'} icon={<AlertTriangle size={16} />} />
                <StatCard label="Excursions (7d)" value={String(dashboard.excursions_this_week)} color="var(--warning)" icon={<Clock size={16} />} />
                <StatCard label="Pending Reports" value={String(dashboard.pending_reports)} color="var(--info)" icon={<FileCheck size={16} />} />
              </div>

              {/* Quick actions */}
              <div className="card">
                <div className="card-header">Quick Actions</div>
                <div className="card-body" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  <button className="btn-primary" onClick={() => setTab('ccps')} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ShieldCheck size={14} /> Manage CCPs
                  </button>
                  <button className="btn-secondary" onClick={() => handleGenerateReport('daily')} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <FileCheck size={14} /> Generate Daily Report
                  </button>
                  <button className="btn-secondary" onClick={() => handleGenerateReport('weekly')} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <FileCheck size={14} /> Generate Weekly Report
                  </button>
                </div>
              </div>

              {/* Recent excursions */}
              {excursions.filter(e => e.state === 'active').length > 0 && (
                <div className="card" style={{ marginTop: 16 }}>
                  <div className="card-header" style={{ color: 'var(--danger)' }}>
                    <AlertTriangle size={14} style={{ marginRight: 6 }} /> Active Excursions
                  </div>
                  <div className="card-body" style={{ padding: 0 }}>
                    {excursions.filter(e => e.state === 'active').map(exc => (
                      <div key={exc.id} style={{
                        padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)',
                        display: 'flex', alignItems: 'center', gap: 12,
                      }}>
                        <div style={{
                          width: 8, height: 8, borderRadius: '50%',
                          background: exc.severity === 'critical' ? 'var(--danger)' : 'var(--warning)',
                        }} />
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
            </div>
          )}

          {/* CCPs Tab */}
          {tab === 'ccps' && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                <button className="btn-primary" onClick={() => setShowCreate(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Plus size={14} /> Add Control Point
                </button>
              </div>

              {ccps.length === 0 ? (
                <div className="card">
                  <div className="card-body empty-state" style={{ padding: 40 }}>
                    <div className="empty-icon"><ShieldCheck size={24} /></div>
                    <h3>No Critical Control Points</h3>
                    <p>Create your first CCP to start HACCP monitoring.</p>
                  </div>
                </div>
              ) : (
                <div className="card">
                  <div className="card-body" style={{ padding: 0 }}>
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
                              <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                                Warning: ±{ccp.warning_offset}°
                              </div>
                            </td>
                            <td>{ccp.check_interval_min} min</td>
                            <td>
                              {ccp.hazard_type && (
                                <span style={{
                                  fontSize: 11, padding: '2px 8px', borderRadius: 10,
                                  background: 'var(--bg-secondary)', textTransform: 'capitalize',
                                }}>
                                  {ccp.hazard_type}
                                </span>
                              )}
                            </td>
                            <td>
                              <span style={{
                                fontSize: 11, padding: '2px 8px', borderRadius: 10,
                                background: ccp.is_active ? 'color-mix(in srgb, var(--success) 15%, transparent)' : 'var(--bg-secondary)',
                                color: ccp.is_active ? 'var(--success)' : 'var(--text-secondary)',
                                fontWeight: 600,
                              }}>
                                {ccp.is_active ? 'Active' : 'Inactive'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Create CCP Modal */}
              {showCreate && (
                <div className="modal-overlay" onClick={() => setShowCreate(false)}>
                  <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
                    <div className="modal-header">
                      <h3 style={{ margin: 0, fontSize: 16 }}>New Critical Control Point</h3>
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
                    <div className="modal-footer" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                      <button className="btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
                      <button className="btn-primary" onClick={handleCreateCCP}>Create CCP</button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Compliance Logs Tab */}
          {tab === 'logs' && (
            <div className="card">
              <div className="card-header">Temperature Check Log (24h)</div>
              <div className="card-body" style={{ padding: 0 }}>
                {logs.length === 0 ? (
                  <div className="empty-state" style={{ padding: 40 }}>
                    <div className="empty-icon"><Thermometer size={24} /></div>
                    <h3>No compliance checks</h3>
                    <p>Checks will appear here as they are recorded.</p>
                  </div>
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
                      {logs.map(log => (
                        <tr key={log.id}>
                          <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                            {new Date(log.checked_at).toLocaleString()}
                          </td>
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
                              color: statusColor(log.status),
                              background: `color-mix(in srgb, ${statusColor(log.status)} 15%, transparent)`,
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
          )}

          {/* Excursions Tab */}
          {tab === 'excursions' && (
            <div className="card">
              <div className="card-header">Temperature Excursions</div>
              <div className="card-body" style={{ padding: 0 }}>
                {excursions.length === 0 ? (
                  <div className="empty-state" style={{ padding: 40 }}>
                    <div className="empty-icon"><CheckCircle size={24} /></div>
                    <h3>No excursions</h3>
                    <p>No temperature excursions in the selected period.</p>
                  </div>
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
                          <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                            {new Date(exc.started_at).toLocaleString()}
                          </td>
                          <td>
                            <span style={{
                              fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                              textTransform: 'uppercase',
                              color: exc.severity === 'critical' ? 'var(--danger)' : 'var(--warning)',
                              background: exc.severity === 'critical'
                                ? 'color-mix(in srgb, var(--danger) 15%, transparent)'
                                : 'color-mix(in srgb, var(--warning) 15%, transparent)',
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
                              background: exc.state === 'active'
                                ? 'color-mix(in srgb, var(--danger) 15%, transparent)'
                                : exc.state === 'resolved'
                                  ? 'color-mix(in srgb, var(--success) 15%, transparent)'
                                  : 'color-mix(in srgb, var(--warning) 15%, transparent)',
                            }}>
                              {exc.state}
                            </span>
                          </td>
                          <td>
                            {exc.state === 'active' && (
                              <button className="btn-secondary" onClick={() => handleResolveExcursion(exc.id)}
                                style={{ fontSize: 11, padding: '4px 10px' }}>
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
          )}

          {/* Reports Tab */}
          {tab === 'reports' && (
            <div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
                <button className="btn-primary" onClick={() => handleGenerateReport('daily')} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                  <FileCheck size={14} /> Daily Report
                </button>
                <button className="btn-primary" onClick={() => handleGenerateReport('weekly')} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                  <FileCheck size={14} /> Weekly Report
                </button>
                <button className="btn-primary" onClick={() => handleGenerateReport('monthly')} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                  <FileCheck size={14} /> Monthly Report
                </button>
              </div>

              {reports.length === 0 ? (
                <div className="card">
                  <div className="card-body empty-state" style={{ padding: 40 }}>
                    <div className="empty-icon"><FileCheck size={24} /></div>
                    <h3>No reports</h3>
                    <p>Generate a compliance report to get started.</p>
                  </div>
                </div>
              ) : (
                <div className="card">
                  <div className="card-body" style={{ padding: 0 }}>
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
                        {reports.map(rpt => (
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
                              {rpt.failed_checks > 0 && (
                                <span style={{ color: 'var(--danger)', marginLeft: 4 }}>({rpt.failed_checks} failed)</span>
                              )}
                            </td>
                            <td>
                              <span style={{ color: rpt.excursion_count > 0 ? 'var(--danger)' : 'var(--success)' }}>
                                {rpt.excursion_count}
                              </span>
                            </td>
                            <td>
                              <span style={{
                                fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                                textTransform: 'uppercase',
                                color: rpt.state === 'signed_off' ? 'var(--success)' : rpt.state === 'pending_review' ? 'var(--warning)' : 'var(--text-secondary)',
                                background: rpt.state === 'signed_off'
                                  ? 'color-mix(in srgb, var(--success) 15%, transparent)'
                                  : 'var(--bg-secondary)',
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
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
