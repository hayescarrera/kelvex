import { useState, useEffect, useCallback } from 'react'
import {
  Loader2, Clock, User, Filter, ChevronRight, RefreshCw,
  PlusCircle, Edit3, Trash2, LogIn, Shield, Settings, Zap,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import { api } from '../lib/api'
import type { ActivityLogEntry, ActivityStats } from '../lib/api'

const ACTION_ICONS: Record<string, typeof PlusCircle> = {
  create: PlusCircle,
  update: Edit3,
  delete: Trash2,
  login: LogIn,
  invite: User,
  rule_change: Shield,
  setting_change: Settings,
  command: Zap,
}

const ACTION_COLORS: Record<string, string> = {
  create: 'var(--success)',
  update: 'var(--accent)',
  delete: 'var(--danger)',
  login: 'var(--info)',
  invite: 'var(--warning)',
}

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function ChangesDisplay({ changes }: { changes: Record<string, { old: unknown; new: unknown }> }) {
  const entries = Object.entries(changes)
  if (entries.length === 0) return null

  return (
    <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
      {entries.map(([field, { old: oldVal, new: newVal }]) => (
        <div key={field} style={{ marginBottom: 2 }}>
          <span style={{ fontWeight: 600 }}>{field}:</span>{' '}
          <span style={{ textDecoration: 'line-through', opacity: 0.6 }}>{String(oldVal ?? '')}</span>
          {' → '}
          <span style={{ fontWeight: 500 }}>{String(newVal ?? '')}</span>
        </div>
      ))}
    </div>
  )
}

export default function ActivityLogPage() {
  const [entries, setEntries] = useState<ActivityLogEntry[]>([])
  const [stats, setStats] = useState<ActivityStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [days, setDays] = useState(30)
  const [filterType, setFilterType] = useState('')
  const [filterAction, setFilterAction] = useState('')
  const [resourceTypes, setResourceTypes] = useState<string[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { days, limit: 50, offset }
      if (filterType) params.resource_type = filterType
      if (filterAction) params.action = filterAction

      const [logRes, statsRes, typesRes] = await Promise.all([
        api.getActivityLog(params as Record<string, string>),
        api.getActivityStats(days),
        api.getActivityResourceTypes(),
      ])
      setEntries(logRes.items)
      setTotal(logRes.total)
      setStats(statsRes)
      setResourceTypes(typesRes.resource_types)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [days, offset, filterType, filterAction])

  useEffect(() => { load() }, [load])

  return (
    <div className="page-container">
      <PageHeader
        title="Activity Log"
        subtitle="Audit trail of all changes across your organization"
      >
        <button className="btn-secondary" onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </PageHeader>

      {/* Stats */}
      {stats && (
        <div className="stat-grid" style={{ marginBottom: 20 }}>
          <StatCard label="Total Events" value={String(stats.total)} color="var(--accent)" icon={<Clock size={16} />} />
          <StatCard label="Unique Users" value={String(stats.unique_actors)} color="var(--info)" icon={<User size={16} />} />
          <StatCard label="Creates" value={String(stats.by_action.create || 0)} color="var(--success)" icon={<PlusCircle size={16} />} />
          <StatCard label="Updates" value={String(stats.by_action.update || 0)} color="var(--accent)" icon={<Edit3 size={16} />} />
          <StatCard label="Deletes" value={String(stats.by_action.delete || 0)} color="var(--danger)" icon={<Trash2 size={16} />} />
          <StatCard label="Logins" value={String(stats.by_action.login || 0)} color="var(--info)" icon={<LogIn size={16} />} />
        </div>
      )}

      {/* Filters */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <Filter size={14} style={{ color: 'var(--text-secondary)' }} />

          <select
            value={days}
            onChange={e => { setDays(Number(e.target.value)); setOffset(0) }}
            className="form-select"
            style={{ width: 'auto', fontSize: 13 }}
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>

          <select
            value={filterAction}
            onChange={e => { setFilterAction(e.target.value); setOffset(0) }}
            className="form-select"
            style={{ width: 'auto', fontSize: 13 }}
          >
            <option value="">All actions</option>
            <option value="create">Create</option>
            <option value="update">Update</option>
            <option value="delete">Delete</option>
            <option value="login">Login</option>
            <option value="invite">Invite</option>
          </select>

          <select
            value={filterType}
            onChange={e => { setFilterType(e.target.value); setOffset(0) }}
            className="form-select"
            style={{ width: 'auto', fontSize: 13 }}
          >
            <option value="">All resources</option>
            {resourceTypes.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          <span style={{ fontSize: 12, color: 'var(--text-secondary)', marginLeft: 'auto' }}>
            {total} events
          </span>
        </div>
      </div>

      {/* Activity feed */}
      <div className="card">
        <div className="card-body" style={{ padding: 0 }}>
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <Loader2 size={20} className="spin" />
            </div>
          ) : entries.length === 0 ? (
            <div className="empty-state" style={{ padding: 40 }}>
              <div className="empty-icon"><Clock size={24} /></div>
              <h3>No activity found</h3>
              <p>Activity will appear here as changes are made.</p>
            </div>
          ) : (
            <div style={{ position: 'relative' }}>
              {/* Timeline line */}
              <div style={{
                position: 'absolute', left: 28, top: 0, bottom: 0,
                width: 2, background: 'var(--border)',
              }} />

              {entries.map((entry) => {
                const Icon = ACTION_ICONS[entry.action] || ChevronRight
                const color = ACTION_COLORS[entry.action] || 'var(--text-secondary)'

                return (
                  <div
                    key={entry.id}
                    style={{
                      display: 'flex', gap: 16, padding: '14px 20px',
                      borderBottom: '1px solid var(--border-subtle)',
                      position: 'relative',
                    }}
                  >
                    {/* Timeline dot */}
                    <div style={{
                      width: 20, height: 20, borderRadius: '50%',
                      background: 'var(--bg-primary)', border: `2px solid ${color}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0, zIndex: 1, marginTop: 2,
                    }}>
                      <Icon size={10} style={{ color }} />
                    </div>

                    {/* Content */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 600, fontSize: 13 }}>
                          {entry.actor_email || 'System'}
                        </span>
                        <span style={{
                          fontSize: 11, padding: '1px 8px', borderRadius: 10,
                          background: color + '18', color,
                          fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px',
                        }}>
                          {entry.action}
                        </span>
                        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                          {entry.resource_type}
                          {entry.resource_name && ` "${entry.resource_name}"`}
                        </span>
                      </div>

                      {entry.summary && (
                        <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
                          {entry.summary}
                        </div>
                      )}

                      {entry.changes && <ChangesDisplay changes={entry.changes} />}

                      <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 11, color: 'var(--text-tertiary)' }}>
                        <span>{formatTimeAgo(entry.created_at)}</span>
                        {entry.ip_address && <span>{entry.ip_address}</span>}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Pagination */}
        {total > 50 && (
          <div style={{
            display: 'flex', justifyContent: 'center', gap: 8, padding: 16,
            borderTop: '1px solid var(--border)',
          }}>
            <button
              className="btn-secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 50))}
              style={{ fontSize: 12 }}
            >
              Previous
            </button>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '6px 12px' }}>
              {offset + 1}–{Math.min(offset + 50, total)} of {total}
            </span>
            <button
              className="btn-secondary"
              disabled={offset + 50 >= total}
              onClick={() => setOffset(offset + 50)}
              style={{ fontSize: 12 }}
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
