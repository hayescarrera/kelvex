import { useNavigate } from 'react-router-dom'
import {
  Bell, Wrench, MapPin, ChevronRight, CheckCircle,
  AlertTriangle, Thermometer, ShieldCheck,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import { useSiteContext } from '../contexts/SiteContext'
import { useAlertSummary } from '../hooks/useAlerts'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

export default function OpsHome() {
  const navigate = useNavigate()
  const { facilities, isLoading } = useSiteContext()
  const { data: alertSummary } = useAlertSummary()

  // Pull active alerts from the first facility to populate the feed;
  // fleet-wide alert listing is on the dedicated /alerts page.
  const firstFacilityId = facilities[0]?.id
  const { data: alertsData } = useQuery({
    queryKey: ['alerts', 'list', firstFacilityId, 'active'],
    queryFn: () => api.listAlerts(firstFacilityId!, { state: 'active', limit: 8 }),
    enabled: !!firstFacilityId,
    refetchInterval: 30_000,
  })

  const totalAlerts = alertSummary?.total_active ?? 0
  const criticalAlerts = alertSummary?.by_severity?.critical ?? 0
  const highAlerts = alertSummary?.by_severity?.high ?? 0

  if (isLoading) return <LoadingState />

  const activeAlerts = alertsData?.alerts ?? []

  return (
    <div className="page-container">
      <PageHeader
        title="Fleet Health"
        subtitle={`${facilities.length} site${facilities.length !== 1 ? 's' : ''} — ${totalAlerts} active alert${totalAlerts !== 1 ? 's' : ''}`}
      />

      {/* Critical banner */}
      {criticalAlerts > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
          background: 'var(--danger-bg)', border: '1px solid var(--danger-border)',
          borderRadius: 6, marginTop: 12, fontSize: 13,
        }}>
          <AlertTriangle size={15} style={{ color: 'var(--danger)', flexShrink: 0 }} />
          <span style={{ color: 'var(--danger)', fontWeight: 600 }}>
            {criticalAlerts} critical alert{criticalAlerts !== 1 ? 's' : ''} require immediate attention
          </span>
          <button
            className="btn-ghost"
            style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--danger)', fontWeight: 600 }}
            onClick={() => navigate('/alerts')}
          >
            View all alerts →
          </button>
        </div>
      )}

      {/* KPI row */}
      <div className="stat-grid stagger">
        <StatCard
          icon={<Bell size={18} />}
          color={totalAlerts > 0 ? (criticalAlerts > 0 ? 'var(--danger)' : 'var(--warning)') : 'var(--ok)'}
          value={String(totalAlerts)}
          label={totalAlerts === 1 ? 'Active Alert' : 'Active Alerts'}
        />
        <StatCard
          icon={<AlertTriangle size={18} />}
          color={criticalAlerts > 0 ? 'var(--danger)' : 'var(--ok)'}
          value={String(criticalAlerts + highAlerts)}
          label="Critical + High"
        />
        <StatCard
          icon={<MapPin size={18} />}
          color="var(--accent)"
          value={String(facilities.length)}
          label="Sites online"
        />
        <StatCard
          icon={<ShieldCheck size={18} />}
          color="var(--ok)"
          value={String(facilities.length - 0)}
          label="Temp-compliant sites"
        />
      </div>

      <div className="dashboard-grid">

        {/* Active alerts feed */}
        <div className="card" style={{ gridColumn: 'span 2' }}>
          <div className="card-header">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Bell size={15} /> Active Alerts
            </h3>
            <button className="btn-ghost" style={{ fontSize: 12 }} onClick={() => navigate('/alerts')}>
              All alerts <ChevronRight size={12} />
            </button>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {activeAlerts.length === 0 ? (
              <div style={{ padding: '2rem', textAlign: 'center' }}>
                <CheckCircle size={24} style={{ color: 'var(--ok)', marginBottom: 8 }} />
                <p style={{ color: 'var(--ok)', fontWeight: 600, margin: 0 }}>All clear</p>
                <p className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>No active alerts across the fleet.</p>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Alert</th>
                    <th>Site</th>
                    <th>Since</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {activeAlerts.map(alert => {
                    const facility = facilities.find(f => f.id === alert.facility_id)
                    const since = new Date(alert.triggered_at).toLocaleString('default', {
                      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                    })
                    const severityClass = {
                      critical: 'badge-danger',
                      high: 'badge-warning',
                      medium: 'badge-info',
                      low: 'badge-neutral',
                      info: 'badge-neutral',
                    }[alert.severity as string] ?? 'badge-neutral'

                    return (
                      <tr
                        key={alert.id}
                        style={{ cursor: 'pointer' }}
                        onClick={() => navigate('/alerts')}
                      >
                        <td>
                          <span className={`badge ${severityClass}`} style={{ fontSize: 11, textTransform: 'capitalize' }}>
                            {alert.severity}
                          </span>
                        </td>
                        <td>
                          <span className="cell-primary" style={{ fontSize: 13 }}>{alert.alert_type?.replace(/_/g, ' ')}</span>
                          {alert.message && (
                            <span className="cell-secondary" style={{ fontSize: 11, display: 'block' }}>{alert.message}</span>
                          )}
                        </td>
                        <td className="text-muted" style={{ fontSize: 12 }}>{facility?.name ?? '—'}</td>
                        <td className="text-muted" style={{ fontSize: 11, fontVariantNumeric: 'tabular-nums' }}>{since}</td>
                        <td><ChevronRight size={14} style={{ opacity: 0.3 }} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Site health tiles */}
        <div className="card">
          <div className="card-header">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <MapPin size={15} /> Sites
            </h3>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {facilities.length === 0 ? (
              <p className="text-muted" style={{ fontSize: 13 }}>No sites configured.</p>
            ) : (
              facilities.map(f => (
                <button
                  key={f.id}
                  className="btn-ghost"
                  style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-start', padding: '8px 10px', fontSize: 13 }}
                  onClick={() => navigate(`/sites/${f.id}`)}
                >
                  <span className="badge-dot" style={{ background: 'var(--ok)', width: 7, height: 7, borderRadius: '50%', flexShrink: 0 }} />
                  <span style={{ flex: 1, textAlign: 'left' }}>{f.name}</span>
                  {f.city && <span className="text-muted" style={{ fontSize: 11 }}>{f.city}, {f.state}</span>}
                  <ChevronRight size={12} style={{ opacity: 0.3 }} />
                </button>
              ))
            )}
          </div>
        </div>

        {/* Quick links */}
        <div className="card">
          <div className="card-header">
            <h3>Quick Access</h3>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { label: 'Alert rules', icon: <Bell size={14} />, to: '/alert-rules' },
              { label: 'Maintenance log', icon: <Wrench size={14} />, to: '/maintenance' },
              { label: 'Refrigerant & compliance', icon: <Thermometer size={14} />, to: '/refrigerant' },
              { label: 'Reports & exports', icon: <ShieldCheck size={14} />, to: '/reports' },
            ].map(link => (
              <button
                key={link.to}
                className="btn-ghost"
                style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-start', fontSize: 13 }}
                onClick={() => navigate(link.to)}
              >
                {link.icon} {link.label} <ChevronRight size={12} style={{ marginLeft: 'auto' }} />
              </button>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}
