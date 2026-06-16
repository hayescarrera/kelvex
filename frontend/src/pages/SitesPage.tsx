import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapPin, ChevronRight, Bell, Plug, Wrench } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { useSiteContext } from '../contexts/SiteContext'
import { useAuth } from '../contexts/AuthContext'
import { useAlertSummary } from '../hooks/useAlerts'

export default function SitesPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { facilities, isLoading } = useSiteContext()
  const { data: alertSummary } = useAlertSummary()

  // Technicians with exactly one site: redirect straight to it
  useEffect(() => {
    if (user?.role === 'technician' && facilities.length === 1 && !isLoading) {
      navigate(`/sites/${facilities[0].id}`, { replace: true })
    }
  }, [user, facilities, isLoading, navigate])

  const totalAlerts = alertSummary?.total_active ?? 0
  const criticalAlerts = alertSummary?.by_severity?.critical ?? 0

  if (isLoading) return <LoadingState />

  if (facilities.length === 0) {
    return (
      <div className="page-container">
        <PageHeader title="Sites" subtitle="Your assigned sites" />
        <EmptyState
          icon={<MapPin size={28} />}
          title="No sites assigned"
          description="Contact your account admin to get site access."
        />
      </div>
    )
  }

  return (
    <div className="page-container">
      <PageHeader
        title="Sites"
        subtitle={`${facilities.length} site${facilities.length !== 1 ? 's' : ''} — ${totalAlerts} active alert${totalAlerts !== 1 ? 's' : ''}`}
      />

      {criticalAlerts > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
          background: 'var(--danger-bg)', border: '1px solid var(--danger-border)',
          borderRadius: 6, marginTop: 12, fontSize: 13,
        }}>
          <Bell size={14} style={{ color: 'var(--danger)', flexShrink: 0 }} />
          <span style={{ color: 'var(--danger)', fontWeight: 600 }}>
            {criticalAlerts} critical alert{criticalAlerts !== 1 ? 's' : ''} need attention
          </span>
          <button
            className="btn-ghost"
            style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--danger)', fontWeight: 600 }}
            onClick={() => navigate('/alerts')}
          >
            View alerts →
          </button>
        </div>
      )}

      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <h3>Your Sites</h3>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Site</th>
              <th>Location</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {facilities.map(f => (
              <tr
                key={f.id}
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/sites/${f.id}`)}
              >
                <td>
                  <div className="cell-with-icon">
                    <div className="table-icon"><MapPin size={13} /></div>
                    <span className="cell-primary">{f.name}</span>
                  </div>
                </td>
                <td className="text-muted" style={{ fontSize: 12 }}>
                  {[f.city, f.state].filter(Boolean).join(', ') || '—'}
                </td>
                <td>
                  <span className="badge badge-success"><span className="badge-dot" /> Online</span>
                </td>
                <td>
                  <div style={{ display: 'flex', gap: 4, justifyContent: 'flex-end' }}>
                    <button
                      className="icon-btn-sm"
                      title="Alerts"
                      onClick={e => { e.stopPropagation(); navigate('/alerts') }}
                    >
                      <Bell size={13} />
                    </button>
                    <button
                      className="icon-btn-sm"
                      title="Maintenance"
                      onClick={e => { e.stopPropagation(); navigate('/maintenance') }}
                    >
                      <Wrench size={13} />
                    </button>
                    <button
                      className="icon-btn-sm"
                      title="Controller access"
                      onClick={e => { e.stopPropagation(); navigate('/tunnel') }}
                    >
                      <Plug size={13} />
                    </button>
                    <ChevronRight size={15} style={{ opacity: 0.3 }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
