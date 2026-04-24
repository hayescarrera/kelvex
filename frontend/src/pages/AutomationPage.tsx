import { useState } from 'react'
import toast from 'react-hot-toast'
import { useLocation } from 'react-router-dom'
import { Loader2, Play, Plus, X, Power, PowerOff, Clock, Zap, Trash2, AlertTriangle } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import { useSiteContext } from '../contexts/SiteContext'
import {
  useSequences, useCreateSequence, useRunSequence,
  useAutomationRules, useCreateAutomationRule, useUpdateAutomationRule,
  useSchedules, useCreateSchedule, useDeleteSchedule,
} from '../hooks/useControls'
import type { ControlSequence, AutomationRule, ScheduleRecord } from '../lib/api'

const SEQUENCE_TYPES = ['pre_cool', 'load_shed', 'night_setback', 'demand_response', 'defrost', 'custom']
const TRIGGER_METRICS = ['zone_temp', 'demand_kw', 'energy_price', 'outdoor_temp', 'schedule']
const TRIGGER_OPERATORS = ['gt', 'lt', 'gte', 'lte', 'eq']
const ACTION_TYPES = ['set_setpoint', 'disable_equipment', 'enable_equipment', 'run_sequence', 'send_alert']
const SCHEDULE_TYPES = ['daily', 'weekly', 'cron', 'one_time']
const DAYS_OF_WEEK = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export default function AutomationPage() {
  const { site } = useSiteContext()
  const facilityId = site?.id
  const location = useLocation()
  const isSchedulesRoute = location.pathname.startsWith('/schedules')

  const [showSeqModal, setShowSeqModal] = useState(false)
  const [showRuleModal, setShowRuleModal] = useState(false)
  const [showSchedModal, setShowSchedModal] = useState(false)

  const { data: seqData, isLoading: seqLoading } = useSequences(facilityId)
  const { data: ruleData, isLoading: rulesLoading } = useAutomationRules(facilityId)
  const { data: schedData, isLoading: schedLoading } = useSchedules(facilityId)

  const sequences = seqData?.sequences ?? []
  const rules = ruleData?.rules ?? []
  const schedules = schedData?.schedules ?? []

  const runSequence = useRunSequence(facilityId ?? '')
  const updateRule = useUpdateAutomationRule(facilityId ?? '')
  const deleteSchedule = useDeleteSchedule(facilityId ?? '')

  const formatDateTime = (val: string | null | undefined) =>
    val ? new Date(val).toLocaleString() : '\u2014'

  if (!facilityId) {
    return (
      <div className="page-container">
        <PageHeader title={isSchedulesRoute ? 'Schedules' : 'Automation'} subtitle="Select a facility to manage automation" />
        <div className="content-area">
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <div className="empty-icon"><Zap size={24} /></div>
                <h3>No facility selected</h3>
                <p>Choose a facility from the site selector to manage automation.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── Schedules page (/schedules) ──────────────────
  if (isSchedulesRoute) {
    return (
      <div className="page-container">
        <PageHeader title="Schedules" subtitle={`${site?.name} — Recurring automation schedules`}>
          <button className="btn-primary" onClick={() => setShowSchedModal(true)}>
            <Plus size={14} /> New Schedule
          </button>
        </PageHeader>

        <div className="stat-grid stagger" style={{ marginTop: 20 }}>
          <StatCard icon={<Clock size={18} />} color="var(--accent)" value={String(schedules.length)} label="Total Schedules" />
          <StatCard icon={<Play size={18} />} color="var(--success)" value={String(schedules.filter((s: ScheduleRecord) => s.enabled).length)} label="Active" />
          <StatCard icon={<Zap size={18} />} color="var(--warning)" value={String(sequences.length)} label="Linked Sequences" />
        </div>

        <div className="content-area">
          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              {schedLoading ? (
                <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Loader2 size={24} className="spin" /></div>
              ) : schedules.length === 0 ? (
                <div className="empty-state">
                  <h3>No schedules</h3>
                  <p>Schedules run automation sequences at specific times or on recurring intervals.</p>
                  <button className="btn-ghost" style={{ marginTop: 12 }} onClick={() => setShowSchedModal(true)}>
                    <Plus size={14} /> Create your first schedule
                  </button>
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr><th>Name</th><th>Type</th><th>Status</th><th>Cron</th><th>Timezone</th><th>Next Run</th><th>Last Run</th><th style={{ width: 60 }}></th></tr>
                  </thead>
                  <tbody>
                    {schedules.map((sched: ScheduleRecord) => (
                      <tr key={sched.id}>
                        <td className="cell-primary">{sched.name}</td>
                        <td><span className="badge badge-info">{sched.schedule_type}</span></td>
                        <td>
                          <span className={`badge ${sched.enabled ? 'badge-success' : 'badge-neutral'}`}>
                            <span className="badge-dot" /> {sched.enabled ? 'Active' : 'Paused'}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{sched.cron_expression ?? '\u2014'}</td>
                        <td style={{ fontSize: 12 }}>{sched.timezone}</td>
                        <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{formatDateTime(sched.next_run_at)}</td>
                        <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{formatDateTime(sched.last_run_at)}</td>
                        <td>
                          <button className="icon-btn-sm" title="Delete schedule"
                            onClick={() => { if (confirm('Delete this schedule?')) deleteSchedule.mutate(sched.id) }}
                            disabled={deleteSchedule.isPending}
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>

        {showSchedModal && <CreateScheduleModal facilityId={facilityId} sequences={sequences} onClose={() => setShowSchedModal(false)} />}
      </div>
    )
  }

  // ── Automation page (/automation) — sequences + rules together ──
  return (
    <div className="page-container">
      <PageHeader title="Automation" subtitle={`${site?.name} — Sequences & trigger rules`}>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary" onClick={() => setShowSeqModal(true)}>
            <Plus size={14} /> New Sequence
          </button>
          <button className="btn-secondary" onClick={() => setShowRuleModal(true)}>
            <Plus size={14} /> New Rule
          </button>
        </div>
      </PageHeader>

      <div className="stat-grid stagger" style={{ marginTop: 20 }}>
        <StatCard icon={<Play size={18} />} color="var(--accent)" value={String(sequences.length)} label="Sequences" />
        <StatCard icon={<AlertTriangle size={18} />} color="var(--success)" value={String(rules.filter((r: AutomationRule) => r.enabled).length)} label="Active Rules" />
        <StatCard icon={<Clock size={18} />} color="var(--warning)" value={String(schedules.length)} label="Schedules" />
      </div>

      <div className="content-area" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Sequences section */}
        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 600 }}>Sequences</span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Pre-cool, load shed, defrost, demand response — the actions your plant can take
            </span>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {seqLoading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Loader2 size={24} className="spin" /></div>
            ) : sequences.length === 0 ? (
              <div className="empty-state">
                <h3>No sequences configured</h3>
                <p>Sequences automate refrigeration operations like pre-cooling, load shedding, and demand response.</p>
                <button className="btn-ghost" style={{ marginTop: 12 }} onClick={() => setShowSeqModal(true)}>
                  <Plus size={14} /> Create your first sequence
                </button>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr><th>Name</th><th>Type</th><th>Priority</th><th>Status</th><th>Last Run</th><th>Runs</th><th style={{ width: 80 }}>Actions</th></tr>
                </thead>
                <tbody>
                  {sequences.map((seq: ControlSequence) => (
                    <tr key={seq.id}>
                      <td>
                        <span className="cell-primary">{seq.name}</span>
                        {seq.description && <span className="cell-secondary">{seq.description}</span>}
                      </td>
                      <td><span className="badge badge-info">{seq.sequence_type?.replace(/_/g, ' ')}</span></td>
                      <td>{seq.priority}</td>
                      <td>
                        <span className={`badge ${seq.enabled ? 'badge-success' : 'badge-neutral'}`}>
                          <span className="badge-dot" /> {seq.enabled ? 'Enabled' : 'Disabled'}
                        </span>
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{formatDateTime(seq.last_run_at)}</td>
                      <td>{seq.run_count}</td>
                      <td>
                        <button className="icon-btn-sm" title="Run now" onClick={() => runSequence.mutate(seq.id)} disabled={runSequence.isPending}>
                          <Play size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Rules section */}
        <div className="card">
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontWeight: 600 }}>Trigger Rules</span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Automatically fire sequences when conditions are met (demand &gt; threshold, zone temp, etc.)
            </span>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {rulesLoading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Loader2 size={24} className="spin" /></div>
            ) : rules.length === 0 ? (
              <div className="empty-state">
                <h3>No trigger rules</h3>
                <p>Rules automatically fire sequences when conditions like demand spikes or zone temperature thresholds are met.</p>
                <button className="btn-ghost" style={{ marginTop: 12 }} onClick={() => setShowRuleModal(true)}>
                  <Plus size={14} /> Create your first rule
                </button>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr><th>Name</th><th>Status</th><th>Cooldown</th><th>Max/Day</th><th>Last Triggered</th><th>Today</th><th style={{ width: 60 }}></th></tr>
                </thead>
                <tbody>
                  {rules.map((rule: AutomationRule) => (
                    <tr key={rule.id}>
                      <td>
                        <span className="cell-primary">{rule.name}</span>
                        {rule.description && <span className="cell-secondary">{rule.description}</span>}
                      </td>
                      <td>
                        <span className={`badge ${rule.enabled ? 'badge-success' : 'badge-neutral'}`}>
                          <span className="badge-dot" /> {rule.enabled ? 'Active' : 'Paused'}
                        </span>
                      </td>
                      <td>{rule.cooldown_minutes}m</td>
                      <td>{rule.max_executions_per_day}</td>
                      <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{formatDateTime(rule.last_triggered_at)}</td>
                      <td>{rule.execution_count_today}</td>
                      <td>
                        <button className="icon-btn-sm" title={rule.enabled ? 'Disable' : 'Enable'}
                          onClick={() => updateRule.mutate({ ruleId: rule.id, data: { enabled: !rule.enabled } as any }, {
                            onSuccess: () => toast.success('Rule updated'),
                            onError: () => toast.error('Failed to update rule'),
                          })}
                        >
                          {rule.enabled ? <PowerOff size={14} /> : <Power size={14} />}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {showSeqModal && <CreateSequenceModal facilityId={facilityId} onClose={() => setShowSeqModal(false)} />}
      {showRuleModal && <CreateRuleModal facilityId={facilityId} onClose={() => setShowRuleModal(false)} />}
    </div>
  )
}

/* ── Modals ──────────────────────────────────────── */
function CreateSequenceModal({ facilityId, onClose }: { facilityId: string; onClose: () => void }) {
  const createSeq = useCreateSequence(facilityId)
  const [form, setForm] = useState({ name: '', description: '', sequence_type: 'pre_cool', priority: '5' })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createSeq.mutate({
      name: form.name, description: form.description || undefined,
      sequence_type: form.sequence_type, priority: parseInt(form.priority) || 5,
      steps: [{ action: 'set_setpoint', target: 'all_zones', params: {} }],
    }, {
      onSuccess: () => { toast.success('Sequence created'); onClose() },
      onError: () => toast.error('Failed to create sequence'),
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header"><h3>New Sequence</h3><button className="icon-btn" onClick={onClose}><X size={18} /></button></div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field"><label>Name</label><input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Evening Pre-Cool" required autoFocus /></div>
          <div className="field"><label>Description</label><textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} rows={2} /></div>
          <div className="field-row">
            <div className="field" style={{ flex: 2 }}><label>Type</label><select value={form.sequence_type} onChange={e => setForm({ ...form, sequence_type: e.target.value })}>{SEQUENCE_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}</select></div>
            <div className="field" style={{ flex: 1 }}><label>Priority</label><input type="number" value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })} min="1" max="10" /></div>
          </div>
          {createSeq.isError && <p className="text-danger" style={{ fontSize: 12 }}>Failed to create sequence.</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createSeq.isPending}>{createSeq.isPending ? 'Creating...' : <><Plus size={14} /> Create</>}</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function CreateScheduleModal({ facilityId, sequences, onClose }: { facilityId: string; sequences: ControlSequence[]; onClose: () => void }) {
  const createSchedule = useCreateSchedule(facilityId)
  const [form, setForm] = useState({
    name: '', control_sequence_id: sequences[0]?.id ?? '', schedule_type: 'daily',
    cron_expression: '', start_time: '06:00', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    days_of_week: [] as number[],
  })

  const toggleDay = (day: number) => {
    setForm(f => ({
      ...f,
      days_of_week: f.days_of_week.includes(day) ? f.days_of_week.filter(d => d !== day) : [...f.days_of_week, day],
    }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createSchedule.mutate({
      name: form.name,
      control_sequence_id: form.control_sequence_id,
      schedule_type: form.schedule_type,
      cron_expression: form.schedule_type === 'cron' ? form.cron_expression : undefined,
      days_of_week: form.schedule_type === 'weekly' ? form.days_of_week : undefined,
      start_time: form.start_time || undefined,
      timezone: form.timezone,
    }, {
      onSuccess: () => { toast.success('Schedule saved'); onClose() },
      onError: () => toast.error('Failed to save schedule'),
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header"><h3>New Schedule</h3><button className="icon-btn" onClick={onClose}><X size={18} /></button></div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field"><label>Name</label><input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Nightly Pre-Cool" required autoFocus /></div>
          <div className="field">
            <label>Linked Sequence</label>
            <select value={form.control_sequence_id} onChange={e => setForm({ ...form, control_sequence_id: e.target.value })} required>
              {sequences.length === 0 && <option value="">No sequences available</option>}
              {sequences.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Type</label>
              <select value={form.schedule_type} onChange={e => setForm({ ...form, schedule_type: e.target.value })}>
                {SCHEDULE_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Start Time</label>
              <input type="time" value={form.start_time} onChange={e => setForm({ ...form, start_time: e.target.value })} />
            </div>
          </div>
          {form.schedule_type === 'cron' && (
            <div className="field">
              <label>Cron Expression</label>
              <input value={form.cron_expression} onChange={e => setForm({ ...form, cron_expression: e.target.value })} placeholder="0 2 * * *" style={{ fontFamily: 'monospace' }} required />
              <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Standard 5-field cron (min hour dom mon dow)</span>
            </div>
          )}
          {form.schedule_type === 'weekly' && (
            <div className="field">
              <label>Days of Week</label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {DAYS_OF_WEEK.map((d, i) => (
                  <button type="button" key={d} onClick={() => toggleDay(i)}
                    style={{
                      padding: '4px 10px', fontSize: 12, borderRadius: 'var(--radius-md)',
                      border: `1px solid ${form.days_of_week.includes(i) ? 'var(--accent)' : 'var(--input-border)'}`,
                      background: form.days_of_week.includes(i) ? 'var(--accent)' : 'var(--input-bg)',
                      color: form.days_of_week.includes(i) ? '#fff' : 'var(--text-primary)',
                      cursor: 'pointer',
                    }}
                  >{d}</button>
                ))}
              </div>
            </div>
          )}
          <div className="field">
            <label>Timezone</label>
            <input value={form.timezone} onChange={e => setForm({ ...form, timezone: e.target.value })} />
          </div>
          {createSchedule.isError && <p className="text-danger" style={{ fontSize: 12 }}>Failed to create schedule.</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createSchedule.isPending || !form.control_sequence_id}>
              {createSchedule.isPending ? 'Creating...' : <><Plus size={14} /> Create</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function CreateRuleModal({ facilityId, onClose }: { facilityId: string; onClose: () => void }) {
  const createRule = useCreateAutomationRule(facilityId)
  const [form, setForm] = useState({ name: '', description: '', trigger_metric: 'demand_kw', trigger_operator: 'gt', trigger_value: '', action_type: 'run_sequence', cooldown: '15', maxPerDay: '10' })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createRule.mutate({
      name: form.name, description: form.description || undefined,
      trigger_conditions: { metric: form.trigger_metric, operator: form.trigger_operator, value: parseFloat(form.trigger_value) },
      actions: [{ type: form.action_type, params: {} }],
      cooldown_minutes: parseInt(form.cooldown) || 15, max_executions_per_day: parseInt(form.maxPerDay) || 10,
    }, {
      onSuccess: () => { toast.success('Rule created'); onClose() },
      onError: () => toast.error('Failed to create rule'),
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header"><h3>New Trigger Rule</h3><button className="icon-btn" onClick={onClose}><X size={18} /></button></div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field"><label>Name</label><input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Peak Demand Load Shed" required autoFocus /></div>
          <div className="field"><label>Description</label><input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></div>
          <div style={{ padding: '10px 14px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Trigger Condition</span>
            <div className="field-row" style={{ marginTop: 8 }}>
              <div className="field" style={{ flex: 2 }}><label>Metric</label><select value={form.trigger_metric} onChange={e => setForm({ ...form, trigger_metric: e.target.value })}>{TRIGGER_METRICS.map(m => <option key={m} value={m}>{m.replace(/_/g, ' ')}</option>)}</select></div>
              <div className="field" style={{ flex: 1 }}><label>Op</label><select value={form.trigger_operator} onChange={e => setForm({ ...form, trigger_operator: e.target.value })}>{TRIGGER_OPERATORS.map(o => <option key={o} value={o}>{o}</option>)}</select></div>
              <div className="field" style={{ flex: 1 }}><label>Value</label><input type="number" value={form.trigger_value} onChange={e => setForm({ ...form, trigger_value: e.target.value })} required /></div>
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 2 }}><label>Action</label><select value={form.action_type} onChange={e => setForm({ ...form, action_type: e.target.value })}>{ACTION_TYPES.map(a => <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>)}</select></div>
            <div className="field" style={{ flex: 1 }}><label>Cooldown</label><input type="number" value={form.cooldown} onChange={e => setForm({ ...form, cooldown: e.target.value })} /></div>
            <div className="field" style={{ flex: 1 }}><label>Max/day</label><input type="number" value={form.maxPerDay} onChange={e => setForm({ ...form, maxPerDay: e.target.value })} /></div>
          </div>
          {createRule.isError && <p className="text-danger" style={{ fontSize: 12 }}>Failed to create rule.</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createRule.isPending}>{createRule.isPending ? 'Creating...' : <><Plus size={14} /> Create</>}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
