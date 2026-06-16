import { useState, useEffect, useCallback } from 'react'
import {
  Loader2, Activity, FileText, CheckCircle, XCircle, Clock,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import { useSiteContext } from '../contexts/SiteContext'
import { api } from '../lib/api'
import type { AuditLogReport, AuditCommand } from '../lib/api'

const CMD_STATE_COLORS: Record<string, string> = {
  completed: 'var(--success)',
  pending: 'var(--warning)',
  sent: 'var(--info)',
  failed: 'var(--danger)',
  expired: 'var(--text-secondary)',
  acknowledged: 'var(--accent)',
}

export default function ReportsPage() {
  const { site } = useSiteContext()
  const facilityId = site?.id

  const [report, setReport] = useState<AuditLogReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)
  const [filterType, setFilterType] = useState('')
  const [filterState, setFilterState] = useState('')

  const load = useCallback(async () => {
    if (!facilityId) { setLoading(false); return }
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
    <div className="page-container">
      <PageHeader
        title="Audit Log"
        subtitle={site ? `${site.name} — Control command history` : 'Control command history'}
      />

      {!facilityId ? (
        <div className="card" style={{ marginTop: 20 }}>
          <div className="card-body">
            <div className="empty-state">
              <div className="empty-icon"><FileText size={24} /></div>
              <h3>No facility selected</h3>
              <p>Choose a facility from the site selector to view the audit log.</p>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 20 }}>
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

          {/* Type breakdown */}
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
                        : ''
                      return (
                        <tr key={cmd.id}>
                          <td className="cell-secondary" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                            {cmd.issued_at ? new Date(cmd.issued_at).toLocaleString() : ''}
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
                            {cmd.error_message || ''}
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
      )}
    </div>
  )
}
