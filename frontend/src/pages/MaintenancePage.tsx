import { useState, useEffect, useCallback } from 'react'
import {
  Wrench, Plus, CheckCircle, AlertTriangle,
  RefreshCw, Calendar, ClipboardList, X, ShieldCheck,
} from 'lucide-react'
import toast from 'react-hot-toast'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { api } from '../lib/api'
import { useSiteContext } from '../contexts/SiteContext'
import type { MaintenanceTaskEntry, MaintenanceDashboardStats, MaintenanceEventEntry } from '../lib/api'

type MainTab = 'tasks' | 'events'
type TaskTab = 'all' | 'scheduled' | 'in_progress' | 'completed' | 'overdue'

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'var(--danger)',
  high: 'var(--warning)',
  medium: 'var(--accent)',
  low: 'var(--text-secondary)',
}

const EVENT_TYPES = [
  'inspection', 'repair', 'replacement', 'calibration',
  'cleaning', 'lubrication', 'refrigerant_add', 'leak_repair',
  'electrical', 'defrost', 'other',
]

function formatLabel(s: string) {
  return s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function formatDt(iso: string) {
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', year: '2-digit', hour: 'numeric', minute: '2-digit' })
}

// ── Log Event Modal ───────────────────────────────────────────────────────────
interface LogEventModalProps {
  facilityId: string
  onClose: () => void
  onSuccess: () => void
}

function LogEventModal({ facilityId, onClose, onSuccess }: LogEventModalProps) {
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    event_type: 'inspection',
    description: '',
    technician_name: '',
    technician_company: '',
    occurred_at: new Date().toISOString().slice(0, 16),
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.description.trim() || !form.technician_name.trim()) {
      toast.error('Description and technician name are required')
      return
    }
    setSaving(true)
    try {
      await api.createMaintenanceEvent({
        facility_id: facilityId,
        event_type: form.event_type,
        description: form.description,
        technician_name: form.technician_name,
        technician_company: form.technician_company || undefined,
        occurred_at: new Date(form.occurred_at).toISOString(),
      })
      toast.success('Event logged')
      onSuccess()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to log event')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 500 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Log Maintenance Event</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Event Type</label>
            <select value={form.event_type} onChange={e => setForm({ ...form, event_type: e.target.value })}>
              {EVENT_TYPES.map(t => <option key={t} value={t}>{formatLabel(t)}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Description *</label>
            <textarea rows={3} value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="What was done? Include equipment, location, and findings." required autoFocus />
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Technician *</label>
              <input value={form.technician_name} onChange={e => setForm({ ...form, technician_name: e.target.value })}
                placeholder="Full name" required />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Company</label>
              <input value={form.technician_company} onChange={e => setForm({ ...form, technician_company: e.target.value })}
                placeholder="Optional" />
            </div>
          </div>
          <div className="field">
            <label>Date / Time</label>
            <input type="datetime-local" value={form.occurred_at}
              onChange={e => setForm({ ...form, occurred_at: e.target.value })} />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : <><ClipboardList size={14} /> Log Event</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Create Task Modal ─────────────────────────────────────────────────────────
interface CreateTaskModalProps {
  facilityId: string
  onClose: () => void
  onSuccess: () => void
}

function CreateTaskModal({ facilityId, onClose, onSuccess }: CreateTaskModalProps) {
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({
    title: '', description: '', category: 'preventive', priority: 'medium',
    is_recurring: false, recurrence_days: '', due_date: '',
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.title.trim()) { toast.error('Title is required'); return }
    setCreating(true)
    try {
      await api.createMaintenanceTask({
        facility_id: facilityId,
        title: form.title,
        description: form.description || undefined,
        category: form.category,
        priority: form.priority,
        is_recurring: form.is_recurring,
        recurrence_days: form.recurrence_days ? parseInt(form.recurrence_days) : undefined,
        due_date: form.due_date || undefined,
      })
      toast.success('Task created')
      onSuccess()
      onClose()
    } catch {
      toast.error('Failed to create task')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 500 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>New Work Order</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Title *</label>
            <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
              placeholder="e.g. Replace compressor oil filter" required autoFocus />
          </div>
          <div className="field">
            <label>Description</label>
            <textarea rows={2} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="Optional details..." />
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Category</label>
              <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
                <option value="preventive">Preventive</option>
                <option value="corrective">Corrective</option>
                <option value="inspection">Inspection</option>
                <option value="calibration">Calibration</option>
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Priority</label>
              <select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
          </div>
          <div className="field">
            <label>Due Date</label>
            <input type="date" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} />
          </div>
          <div className="field">
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input type="checkbox" checked={form.is_recurring}
                onChange={e => setForm({ ...form, is_recurring: e.target.checked })} />
              Recurring task
            </label>
            {form.is_recurring && (
              <div style={{ marginTop: 8 }}>
                <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>Repeat every N days</label>
                <input type="number" placeholder="30" value={form.recurrence_days}
                  onChange={e => setForm({ ...form, recurrence_days: e.target.value })} />
              </div>
            )}
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={creating}>
              {creating ? 'Creating...' : <><Plus size={14} /> Create Work Order</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function MaintenancePage() {
  const { site, facilities } = useSiteContext()
  const [mainTab, setMainTab] = useState<MainTab>('tasks')
  const [taskTab, setTaskTab] = useState<TaskTab>('all')
  const [tasks, setTasks] = useState<MaintenanceTaskEntry[]>([])
  const [stats, setStats] = useState<MaintenanceDashboardStats | null>(null)
  const [events, setEvents] = useState<MaintenanceEventEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [eventsLoading, setEventsLoading] = useState(false)
  const [eventsLoaded, setEventsLoaded] = useState(false)
  const [showCreateTask, setShowCreateTask] = useState(false)
  const [showLogEvent, setShowLogEvent] = useState(false)

  const facilityId = site?.id

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {}
      if (facilityId) params.facility_id = facilityId
      if (taskTab !== 'all') params.state = taskTab
      const [taskRes, statsRes] = await Promise.all([
        api.listMaintenanceTasks(params),
        api.getMaintenanceDashboard(facilityId),
      ])
      setTasks(taskRes.tasks)
      setStats(statsRes)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [facilityId, taskTab])

  const loadEvents = useCallback(async () => {
    if (eventsLoaded) return
    setEventsLoading(true)
    try {
      const res = await api.listMaintenanceEvents(facilityId ? { facility_id: facilityId, limit: 200 } : { limit: 200 })
      setEvents(res.events)
      setEventsLoaded(true)
    } catch {
      // silent
    } finally {
      setEventsLoading(false)
    }
  }, [facilityId, eventsLoaded])

  useEffect(() => { loadTasks() }, [loadTasks])
  useEffect(() => { if (mainTab === 'events') loadEvents() }, [mainTab, loadEvents])

  async function handleStateChange(taskId: string, newState: string) {
    try {
      await api.updateMaintenanceTask(taskId, { state: newState })
      toast.success(newState === 'completed' ? 'Task completed' : 'Task started')
      loadTasks()
    } catch {
      toast.error('Failed to update task')
    }
  }

  const TASK_TABS: { id: TaskTab; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'scheduled', label: 'Scheduled' },
    { id: 'in_progress', label: 'In Progress' },
    { id: 'overdue', label: 'Overdue' },
    { id: 'completed', label: 'Completed' },
  ]

  const effectiveFacilityId = facilityId ?? (facilities.length === 1 ? facilities[0].id : '')

  return (
    <div className="page-container">
      <PageHeader
        title="Maintenance & Audit"
        subtitle="Work orders, inspection records, and tamper-evident event log"
      >
        {mainTab === 'tasks' ? (
          <button className="btn-primary" onClick={() => setShowCreateTask(true)} disabled={!effectiveFacilityId}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Plus size={14} /> New Work Order
          </button>
        ) : (
          <>
            <button className="btn-secondary" style={{ fontSize: 12 }} onClick={() => {
              toast('Activity log export — PDF coming soon', { icon: '📋' })
            }}>
              <ShieldCheck size={14} /> Export My Record
            </button>
            <button className="btn-primary" onClick={() => setShowLogEvent(true)} disabled={!effectiveFacilityId}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <ClipboardList size={14} /> Log Event
            </button>
          </>
        )}
        <button className="btn-secondary" onClick={() => { setEventsLoaded(false); loadTasks() }}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <RefreshCw size={14} />
        </button>
      </PageHeader>

      {/* Stats — always visible */}
      {stats && (
        <div className="stat-grid stagger" style={{ marginBottom: 20 }}>
          <StatCard label="Due This Week" value={String(stats.due_this_week)} color="var(--accent)" icon={<Calendar size={16} />} />
          <StatCard label="Overdue" value={String(stats.overdue)}
            color={stats.overdue > 0 ? 'var(--danger)' : 'var(--success)'} icon={<AlertTriangle size={16} />} />
          <StatCard label="In Progress" value={String(stats.by_state?.in_progress || 0)}
            color="var(--warning)" icon={<Wrench size={16} />} />
          <StatCard label="Completed (30d)" value={String(stats.completed_30d)}
            color="var(--success)" icon={<CheckCircle size={16} />} />
        </div>
      )}

      {/* Main tab bar */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)', marginBottom: 16 }}>
        {([
          { id: 'tasks' as MainTab, label: 'Work Orders', icon: <Wrench size={13} /> },
          { id: 'events' as MainTab, label: 'Activity Log', icon: <ClipboardList size={13} /> },
        ]).map(t => (
          <button key={t.id} onClick={() => setMainTab(t.id)} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '8px 16px', fontSize: 13, fontWeight: mainTab === t.id ? 600 : 400,
            color: mainTab === t.id ? 'var(--accent)' : 'var(--text-secondary)',
            borderBottom: mainTab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
            background: 'none', border: 'none', cursor: 'pointer', marginBottom: -1,
          }}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ── WORK ORDERS TAB ── */}
      {mainTab === 'tasks' && (
        <>
          <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
            {TASK_TABS.map(t => (
              <button key={t.id} onClick={() => setTaskTab(t.id)} style={{
                padding: '5px 12px', fontSize: 12, borderRadius: 6, cursor: 'pointer',
                background: taskTab === t.id ? 'var(--accent-muted)' : 'var(--bg-secondary)',
                color: taskTab === t.id ? 'var(--accent)' : 'var(--text-secondary)',
                border: `1px solid ${taskTab === t.id ? 'var(--accent)' : 'var(--border)'}`,
                fontWeight: taskTab === t.id ? 600 : 400,
              }}>
                {t.label}
                {t.id === 'overdue' && stats && stats.overdue > 0 && (
                  <span style={{ marginLeft: 6, fontSize: 10, padding: '1px 5px', borderRadius: 8,
                    background: 'var(--danger)', color: '#fff', fontWeight: 700 }}>
                    {stats.overdue}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              {loading ? (
                <LoadingState label="Loading tasks..." />
              ) : tasks.length === 0 ? (
                <EmptyState icon={<Wrench size={24} />} title="No work orders"
                  description="Create a work order to track maintenance tasks."
                  action={effectiveFacilityId ? (
                    <button className="btn-primary" onClick={() => setShowCreateTask(true)}>
                      <Plus size={14} /> New Work Order
                    </button>
                  ) : undefined} />
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Category</th>
                      <th>Priority</th>
                      <th>Due</th>
                      <th>State</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.map(task => {
                      const overdue = task.state === 'scheduled' && task.due_date && new Date(task.due_date) < new Date()
                      return (
                        <tr key={task.id}>
                          <td>
                            <div style={{ fontWeight: 600, fontSize: 13 }}>{task.title}</div>
                            {task.description && (
                              <div style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {task.description}
                              </div>
                            )}
                          </td>
                          <td style={{ fontSize: 12 }}>{formatLabel(task.category)}</td>
                          <td>
                            <span style={{
                              fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                              textTransform: 'uppercase',
                              color: PRIORITY_COLORS[task.priority] || 'var(--text-secondary)',
                              background: `color-mix(in srgb, ${PRIORITY_COLORS[task.priority] || 'var(--text-secondary)'} 15%, transparent)`,
                            }}>
                              {task.priority}
                            </span>
                          </td>
                          <td style={{
                            fontSize: 12, whiteSpace: 'nowrap',
                            color: overdue ? 'var(--danger)' : 'var(--text-secondary)',
                            fontWeight: overdue ? 600 : 400,
                          }}>
                            {task.due_date ? new Date(task.due_date).toLocaleDateString() : '—'}
                            {overdue && ' (overdue)'}
                          </td>
                          <td>
                            <span style={{
                              fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                              textTransform: 'uppercase',
                              color: task.state === 'completed' ? 'var(--success)' : task.state === 'in_progress' ? 'var(--warning)' : 'var(--accent)',
                              background: task.state === 'completed'
                                ? 'color-mix(in srgb, var(--success) 15%, transparent)'
                                : task.state === 'in_progress'
                                  ? 'color-mix(in srgb, var(--warning) 15%, transparent)'
                                  : 'var(--bg-secondary)',
                            }}>
                              {task.state.replace('_', ' ')}
                            </span>
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: 6 }}>
                              {task.state === 'scheduled' && (
                                <button className="btn-secondary" onClick={() => handleStateChange(task.id, 'in_progress')}
                                  style={{ fontSize: 11, padding: '4px 10px' }}>
                                  Start
                                </button>
                              )}
                              {task.state === 'in_progress' && (
                                <button className="btn-primary" onClick={() => handleStateChange(task.id, 'completed')}
                                  style={{ fontSize: 11, padding: '4px 10px' }}>
                                  Complete
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}

      {/* ── ACTIVITY LOG TAB ── */}
      {mainTab === 'events' && (
        <>
          <div style={{
            padding: '10px 14px', background: 'var(--bg-secondary)',
            borderRadius: 8, border: '1px solid var(--border)', marginBottom: 16,
            fontSize: 12, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <ClipboardList size={13} style={{ flexShrink: 0 }} />
            Activity log entries are immutable once created. Each entry is timestamped and attributed to the logging user.
            <button className="btn-ghost" style={{ marginLeft: 'auto', fontSize: 12 }}
              onClick={() => toast('PDF export coming soon — will include all entries with timestamps and technician names', { icon: '📋' })}>
              <ShieldCheck size={12} /> Export My Record
            </button>
          </div>

          {eventsLoading ? (
            <LoadingState label="Loading activity log..." />
          ) : events.length === 0 ? (
            <EmptyState icon={<ClipboardList size={24} />} title="No events logged"
              description="Log an inspection, repair, or other activity to start building the tamper-evident record."
              action={effectiveFacilityId ? (
                <button className="btn-primary" onClick={() => setShowLogEvent(true)}>
                  <ClipboardList size={14} /> Log First Event
                </button>
              ) : undefined} />
          ) : (
            <div className="card">
              <div className="card-body" style={{ padding: 0 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date / Time</th>
                      <th>Event</th>
                      <th>Description</th>
                      <th>Technician</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map(ev => (
                      <tr key={ev.id}>
                        <td style={{ fontSize: 12, whiteSpace: 'nowrap', color: 'var(--text-muted)' }}>
                          {formatDt(ev.occurred_at)}
                        </td>
                        <td>
                          <span style={{
                            fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                            background: 'var(--accent-muted)', color: 'var(--accent)',
                          }}>
                            {formatLabel(ev.event_type)}
                          </span>
                        </td>
                        <td style={{ fontSize: 13, maxWidth: 340 }}>{ev.description}</td>
                        <td style={{ fontSize: 12 }}>
                          <div style={{ fontWeight: 500 }}>{ev.technician_name}</div>
                          {ev.technician_company && (
                            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{ev.technician_company}</div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Modals */}
      {showCreateTask && effectiveFacilityId && (
        <CreateTaskModal
          facilityId={effectiveFacilityId}
          onClose={() => setShowCreateTask(false)}
          onSuccess={() => loadTasks()}
        />
      )}
      {showLogEvent && effectiveFacilityId && (
        <LogEventModal
          facilityId={effectiveFacilityId}
          onClose={() => setShowLogEvent(false)}
          onSuccess={() => { setEventsLoaded(false); loadEvents() }}
        />
      )}
    </div>
  )
}
