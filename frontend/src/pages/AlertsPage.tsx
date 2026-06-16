import { useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { AlertTriangle, Bell, CheckCircle, Filter, Shield, Clock, Wrench } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { useSiteContext } from '../contexts/SiteContext'
import { useAlerts, useAlertSummary, useUpdateAlert } from '../hooks/useAlerts'
import { api } from '../lib/api'
import type { Alert } from '../lib/api'

function formatCategory(cat: string) {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low', 'info']

const severityBadge = (severity: string) => {
  const map: Record<string, string> = {
    critical: 'badge-danger',
    high: 'badge-warning',
    medium: 'badge-info',
    low: 'badge-neutral',
    info: 'badge-neutral',
  }
  return map[severity] ?? 'badge-neutral'
}

const stateBadge = (state: string) => {
  if (state === 'active') return 'badge-danger'
  if (state === 'acknowledged') return 'badge-warning'
  if (state === 'resolved') return 'badge-success'
  return 'badge-neutral'
}

export default function AlertsPage() {
  const { site, facilities } = useSiteContext()
  const [severityFilter, setSeverityFilter] = useState<string>('')
  const [stateFilter, setStateFilter] = useState<string>('')

  const facilityId = site?.id
  const { data, isLoading } = useAlerts(facilityId, {
    severity: severityFilter || undefined,
    state: stateFilter || undefined,
  })
  const { data: summary } = useAlertSummary()
  const updateAlert = useUpdateAlert(facilityId ?? '')

  const alerts = data?.alerts ?? []

  const handleAcknowledge = (alertId: string) => {
    if (!facilityId) return
    updateAlert.mutate({ alertId, data: { state: 'acknowledged' } }, {
      onSuccess: () => toast.success('Alert acknowledged'),
      onError: () => toast.error('Failed to acknowledge alert'),
    })
  }

  const handleResolve = (alertId: string) => {
    if (!facilityId) return
    updateAlert.mutate({ alertId, data: { state: 'resolved', resolution_note: 'Resolved from dashboard' } }, {
      onSuccess: () => toast.success('Alert resolved'),
      onError: () => toast.error('Failed to resolve alert'),
    })
  }

  const handleCreateWorkOrder = async (alertId: string) => {
    try {
      const task = await api.createWorkOrderFromAlert(alertId)
      toast.success(`Work order created: ${task.title}`)
    } catch {
      toast.error('Failed to create work order')
    }
  }

  const formatTime = (val: string) => {
    const d = new Date(val)
    const now = Date.now()
    const diff = now - d.getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'Just now'
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    return d.toLocaleDateString()
  }

  if (!site) {
    return (
      <div className="page-container">
        <PageHeader title="Alerts & Events" subtitle="Monitor facility health across your fleet" />
        <div className="content-area">
          <div className="stat-grid stagger">
            <StatCard icon={<AlertTriangle size={18} />} color="var(--danger)" value={String(summary?.total_active ?? 0)} label="Active Alerts" />
            <StatCard icon={<Shield size={18} />} color="var(--warning)" value={String(summary?.by_severity?.critical ?? 0)} label="Critical" />
            <StatCard icon={<Bell size={18} />} color="var(--info)" value={String(summary?.by_severity?.high ?? 0)} label="High" />
            <StatCard icon={<CheckCircle size={18} />} color="var(--success)" value={String((summary?.by_severity?.medium ?? 0) + (summary?.by_severity?.low ?? 0))} label="Medium/Low" />
          </div>
          <div className="card" style={{ marginTop: 20 }}>
            <div className="card-header">
              <h3>Showing fleet-wide counts</h3>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                Use the site selector in the sidebar to filter alerts by facility
              </span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              <table className="data-table">
                <thead>
                  <tr><th>Facility</th><th>Location</th></tr>
                </thead>
                <tbody>
                  {facilities.map(f => (
                    <tr key={f.id}>
                      <td><span className="cell-primary">{f.name}</span></td>
                      <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                        {[f.city, f.state].filter(Boolean).join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-container">
      <PageHeader title="Alerts & Events" subtitle={`${site.name} — ${alerts.length} alert${alerts.length !== 1 ? 's' : ''}`}>
        <Link to="/settings" className="btn-secondary"
          style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, textDecoration: 'none' }}>
          <Bell size={14} /> Configure Notifications
        </Link>
      </PageHeader>

      <div className="stat-grid stagger" style={{ marginTop: 20 }}>
        <StatCard icon={<AlertTriangle size={18} />} color="var(--danger)" value={String(summary?.total_active ?? alerts.length)} label="Active" />
        <StatCard icon={<Shield size={18} />} color="var(--warning)" value={String(summary?.by_severity?.critical ?? 0)} label="Critical" />
        <StatCard icon={<Bell size={18} />} color="var(--info)" value={String(summary?.by_severity?.high ?? 0)} label="High" />
        <StatCard icon={<CheckCircle size={18} />} color="var(--success)" value={String((summary?.by_severity?.medium ?? 0) + (summary?.by_severity?.low ?? 0))} label="Medium / Low" />
      </div>

      <div className="content-area">
        <div className="card">
          <div className="card-header">
            <h3>Alert Feed</h3>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Filter size={14} style={{ color: 'var(--text-muted)' }} />
              <select
                value={severityFilter}
                onChange={e => setSeverityFilter(e.target.value)}
                style={{
                  padding: '5px 10px', fontSize: '12px', border: '1px solid var(--input-border)',
                  borderRadius: 'var(--radius-sm)', background: 'var(--input-bg)', color: 'var(--text-primary)',
                  fontFamily: 'inherit',
                }}
              >
                <option value="">All severities</option>
                {SEVERITY_ORDER.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
              </select>
              <select
                value={stateFilter}
                onChange={e => setStateFilter(e.target.value)}
                style={{
                  padding: '5px 10px', fontSize: '12px', border: '1px solid var(--input-border)',
                  borderRadius: 'var(--radius-sm)', background: 'var(--input-bg)', color: 'var(--text-primary)',
                  fontFamily: 'inherit',
                }}
              >
                <option value="">All states</option>
                <option value="active">Active</option>
                <option value="acknowledged">Acknowledged</option>
                <option value="resolved">Resolved</option>
              </select>
            </div>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {isLoading ? (
              <LoadingState label="Loading alerts..." />
            ) : alerts.length === 0 ? (
              <EmptyState
                icon={<CheckCircle size={24} />}
                title="All clear"
                description="No alerts matching your filters. All systems operating normally."
              />
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Alert</th>
                    <th>Category</th>
                    <th>State</th>
                    <th>Triggered</th>
                    <th style={{ width: 120 }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((alert: Alert) => (
                    <tr key={alert.id}>
                      <td>
                        <span className={`badge ${severityBadge(alert.severity)}`}>
                          {alert.severity}
                        </span>
                      </td>
                      <td>
                        <span className="cell-primary">{alert.title}</span>
                        {alert.message && <span className="cell-secondary">{alert.message}</span>}
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>{formatCategory(alert.category)}</td>
                      <td>
                        <span className={`badge ${stateBadge(alert.state)}`}>
                          <span className="badge-dot" /> {alert.state}
                        </span>
                      </td>
                      <td>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '12px', color: 'var(--text-tertiary)' }}>
                          <Clock size={12} /> {formatTime(alert.triggered_at)}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 4 }}>
                          {alert.state === 'active' && (
                            <button
                              className="btn-secondary"
                              style={{ padding: '4px 8px', fontSize: '11px' }}
                              onClick={() => handleAcknowledge(alert.id)}
                              disabled={updateAlert.isPending}
                            >
                              Ack
                            </button>
                          )}
                          {alert.state !== 'resolved' && (
                            <button
                              className="btn-secondary"
                              style={{ padding: '4px 8px', fontSize: '11px' }}
                              onClick={() => handleResolve(alert.id)}
                              disabled={updateAlert.isPending}
                            >
                              Resolve
                            </button>
                          )}
                          {alert.state !== 'resolved' && (alert.severity === 'critical' || alert.severity === 'high') && (
                            <button
                              className="btn-secondary"
                              style={{ padding: '4px 8px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: 3 }}
                              onClick={() => handleCreateWorkOrder(alert.id)}
                              title="Auto-generate maintenance work order from this alert"
                            >
                              <Wrench size={10} /> WO
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
