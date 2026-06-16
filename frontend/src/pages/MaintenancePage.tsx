import { useState, useEffect, useCallback } from 'react'
import {
  Wrench, Plus, CheckCircle, AlertTriangle,
  RefreshCw, Calendar,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { api } from '../lib/api'
import { useSiteContext } from '../contexts/SiteContext'
import toast from 'react-hot-toast'
import type { MaintenanceTaskEntry, MaintenanceDashboardStats } from '../lib/api'

type Tab = 'all' | 'scheduled' | 'in_progress' | 'completed' | 'overdue'

const PRIORITY_COLORS: Record<string, string> = {
  critical: 'var(--danger)',
  high: 'var(--warning)',
  medium: 'var(--accent)',
  low: 'var(--text-secondary)',
}

const CATEGORY_LABELS: Record<string, string> = {
  preventive: 'Preventive',
  corrective: 'Corrective',
  inspection: 'Inspection',
  calibration: 'Calibration',
}

export default function MaintenancePage() {
  const { site } = useSiteContext()
  const [tab, setTab] = useState<Tab>('all')
  const [tasks, setTasks] = useState<MaintenanceTaskEntry[]>([])
  const [stats, setStats] = useState<MaintenanceDashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({
    title: '', description: '', category: 'preventive', priority: 'medium',
    is_recurring: false, recurrence_days: '', due_date: '',
  })
  const [creating, setCreating] = useState(false)

  const facilityId = site?.id

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {}
      if (facilityId) params.facility_id = facilityId
      if (tab !== 'all') params.state = tab

      const [taskRes, statsRes] = await Promise.all([
        api.listMaintenanceTasks(params),
        api.getMaintenanceDashboard(facilityId),
      ])
      setTasks(taskRes.tasks)
      setStats(statsRes)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [facilityId, tab])

  useEffect(() => { load() }, [load])

  async function handleCreate() {
    if (!facilityId) { toast.error('Select a facility first'); return }
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
      setShowCreate(false)
      setForm({ title: '', description: '', category: 'preventive', priority: 'medium', is_recurring: false, recurrence_days: '', due_date: '' })
      load()
    } catch { toast.error('Failed to create task') } finally { setCreating(false) }
  }

  async function handleStateChange(taskId: string, newState: string) {
    try {
      await api.updateMaintenanceTask(taskId, { state: newState })
      toast.success(`Task ${newState === 'completed' ? 'completed' : 'started'}`)
      load()
    } catch { toast.error('Failed to update task') }
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'scheduled', label: 'Scheduled' },
    { id: 'in_progress', label: 'In Progress' },
    { id: 'overdue', label: 'Overdue' },
    { id: 'completed', label: 'Completed' },
  ]

  return (
    <div className="page-container">
      <PageHeader
        title="Maintenance"
        subtitle="Preventive maintenance tasks, work orders, and scheduling"
      >
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-secondary" onClick={load} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <RefreshCw size={14} /> Refresh
          </button>
          <button className="btn-primary" onClick={() => setShowCreate(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Plus size={14} /> New Task
          </button>
        </div>
      </PageHeader>

      {/* Stats */}
      {stats && (
        <div className="stat-grid" style={{ marginBottom: 20 }}>
          <StatCard label="Due This Week" value={String(stats.due_this_week)} color="var(--accent)" icon={<Calendar size={16} />} />
          <StatCard label="Overdue" value={String(stats.overdue)} color={stats.overdue > 0 ? 'var(--danger)' : 'var(--success)'} icon={<AlertTriangle size={16} />} />
          <StatCard label="In Progress" value={String(stats.by_state.in_progress || 0)} color="var(--warning)" icon={<Wrench size={16} />} />
          <StatCard label="Completed (30d)" value={String(stats.completed_30d)} color="var(--success)" icon={<CheckCircle size={16} />} />
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16, borderBottom: '1px solid var(--border)' }}>
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
            {t.id === 'overdue' && stats && stats.overdue > 0 && (
              <span style={{
                marginLeft: 6, fontSize: 10, padding: '1px 6px', borderRadius: 8,
                background: 'var(--danger)', color: '#fff', fontWeight: 700,
              }}>
                {stats.overdue}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Task List */}
      <div className="card">
        <div className="card-body" style={{ padding: 0 }}>
          {loading ? (
            <LoadingState label="Loading tasks..." />
          ) : tasks.length === 0 ? (
            <EmptyState
              icon={<Wrench size={24} />}
              title="No maintenance tasks"
              description="Create a task to get started."
            />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Category</th>
                  <th>Priority</th>
                  <th>Due Date</th>
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
                        {task.description && <div style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{task.description}</div>}
                        {task.is_recurring && (
                          <div style={{ fontSize: 11, color: 'var(--accent)' }}>
                            Recurring every {task.recurrence_days} days
                          </div>
                        )}
                      </td>
                      <td>
                        <span style={{ fontSize: 12 }}>{CATEGORY_LABELS[task.category] || task.category}</span>
                      </td>
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
                        {task.due_date ? new Date(task.due_date).toLocaleDateString() : ''}
                        {overdue && ' (overdue)'}
                      </td>
                      <td>
                        <span style={{
                          fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                          textTransform: 'uppercase',
                          color: task.state === 'completed' ? 'var(--success)' : task.state === 'in_progress' ? 'var(--warning)' : task.state === 'cancelled' ? 'var(--text-tertiary)' : 'var(--accent)',
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

      {/* Create Modal */}
      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
            <div className="modal-header">
              <h3 style={{ margin: 0, fontSize: 16 }}>New Maintenance Task</h3>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label className="form-label">Title *</label>
                <input type="text" className="form-input" placeholder="e.g. Replace compressor oil filter"
                  value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
              </div>
              <div>
                <label className="form-label">Description</label>
                <textarea className="form-input" rows={2} placeholder="Optional details..."
                  value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Category</label>
                  <select className="form-select" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}>
                    <option value="preventive">Preventive</option>
                    <option value="corrective">Corrective</option>
                    <option value="inspection">Inspection</option>
                    <option value="calibration">Calibration</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label className="form-label">Priority</label>
                  <select className="form-select" value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="form-label">Due Date</label>
                <input type="date" className="form-input" value={form.due_date}
                  onChange={e => setForm({ ...form, due_date: e.target.value })} />
              </div>
              <div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                  <input type="checkbox" checked={form.is_recurring}
                    onChange={e => setForm({ ...form, is_recurring: e.target.checked })} />
                  Recurring task
                </label>
                {form.is_recurring && (
                  <div style={{ marginTop: 8 }}>
                    <label className="form-label">Repeat every N days</label>
                    <input type="number" className="form-input" placeholder="30" value={form.recurrence_days}
                      onChange={e => setForm({ ...form, recurrence_days: e.target.value })} />
                  </div>
                )}
              </div>
            </div>
            <div className="modal-actions" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
              <button className="btn-primary" onClick={handleCreate} disabled={creating}>
                {creating ? 'Creating...' : 'Create Task'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
