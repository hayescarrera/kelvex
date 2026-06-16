import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Play, Plus, X, Power, PowerOff, CheckCircle, XCircle, Clock, Shield } from 'lucide-react'
import LoadingState from '../../components/ui/LoadingState'
import EmptyState from '../../components/ui/EmptyState'
import {
  useSequences, useCreateSequence, useRunSequence,
  useAutomationRules, useCreateAutomationRule, useUpdateAutomationRule,
  usePlantCommands, useCancelCommand, useApproveCommand, useControlAuditLog,
} from '../../hooks/useControls'
import type { PlantCommand } from '../../lib/api'

const SEQUENCE_TYPES = ['pre_cool', 'load_shed', 'night_setback', 'demand_response', 'defrost', 'custom']
const TRIGGER_METRICS = ['zone_temp', 'demand_kw', 'energy_price', 'outdoor_temp', 'schedule']
const TRIGGER_OPERATORS = ['gt', 'lt', 'gte', 'lte', 'eq']
const ACTION_TYPES = ['set_setpoint', 'disable_equipment', 'enable_equipment', 'run_sequence', 'send_alert']

const CMD_STATE_BADGE: Record<string, string> = {
  pending_approval: 'badge-warning',
  pending: 'badge-info',
  sent: 'badge-info',
  acknowledged: 'badge-info',
  completed: 'badge-success',
  failed: 'badge-danger',
  cancelled: 'badge-neutral',
  expired: 'badge-neutral',
}

function formatRelTime(val: string | null | undefined) {
  if (!val) return '—'
  const d = new Date(val)
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return d.toLocaleDateString()
}

export default function ControlsPage() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const [activeTab, setActiveTab] = useState<'sequences' | 'rules' | 'commands' | 'audit'>('sequences')
  const [showSeqModal, setShowSeqModal] = useState(false)
  const [showRuleModal, setShowRuleModal] = useState(false)

  const { data: seqData, isLoading: seqLoading } = useSequences(facilityId!)
  const { data: ruleData, isLoading: rulesLoading } = useAutomationRules(facilityId!)
  const { data: cmdData, isLoading: cmdLoading } = usePlantCommands(facilityId!)
  const { data: auditData, isLoading: auditLoading } = useControlAuditLog(facilityId!)
  const sequences = seqData?.sequences ?? []
  const rules = ruleData?.rules ?? []
  const commands = cmdData?.commands ?? []
  const auditLogs = auditData?.logs ?? []

  const runSequence = useRunSequence(facilityId!)
  const updateRule = useUpdateAutomationRule(facilityId!)
  const cancelCmd = useCancelCommand(facilityId!)
  const approveCmd = useApproveCommand(facilityId!)

  const pendingApprovalCount = commands.filter((c: PlantCommand) => c.state === 'pending_approval').length

  const formatDateTime = (val: string | null | undefined) =>
    val ? new Date(val).toLocaleString() : '\u2014'

  const toggleRule = (ruleId: string, currentEnabled: boolean) => {
    const enabling = !currentEnabled
    updateRule.mutate({ ruleId, data: { enabled: enabling } as any })
  }

  return (
    <div className="stack-lg">
      <div className="card">
        <div className="card-header">
          <div className="tab-toggle" style={{ marginBottom: 0 }}>
            <button className={activeTab === 'sequences' ? 'active' : ''} onClick={() => setActiveTab('sequences')}>
              Sequences ({sequences.length})
            </button>
            <button className={activeTab === 'rules' ? 'active' : ''} onClick={() => setActiveTab('rules')}>
              Rules ({rules.length})
            </button>
            <button className={activeTab === 'commands' ? 'active' : ''} onClick={() => setActiveTab('commands')}
              style={{ position: 'relative' }}>
              Command Queue
              {pendingApprovalCount > 0 && (
                <span style={{
                  marginLeft: 6, fontSize: 10, padding: '1px 6px', borderRadius: 8,
                  background: 'var(--warning)', color: '#fff', fontWeight: 700,
                }}>
                  {pendingApprovalCount}
                </span>
              )}
            </button>
            <button className={activeTab === 'audit' ? 'active' : ''} onClick={() => setActiveTab('audit')}>
              Audit Log
            </button>
          </div>
          {(activeTab === 'sequences' || activeTab === 'rules') && (
            <button
              className="btn-primary"
              onClick={() => activeTab === 'sequences' ? setShowSeqModal(true) : setShowRuleModal(true)}
            >
              <Plus size={14} /> {activeTab === 'sequences' ? 'New Sequence' : 'New Rule'}
            </button>
          )}
        </div>

        <div className="card-body" style={{ padding: 0 }}>
          {activeTab === 'sequences' && (
            <>
              {seqLoading ? (
                <LoadingState rows={4} />
              ) : sequences.length === 0 ? (
                <div className="empty-state">
                  <h3>No sequences configured</h3>
                  <p>Control sequences automate refrigeration operations like pre-cooling, load shedding, and demand response.</p>
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
                    {sequences.map((seq: any) => (
                      <tr key={seq.id}>
                        <td>
                          <span className="cell-primary">{seq.name}</span>
                          {seq.description && <span className="cell-secondary">{seq.description}</span>}
                        </td>
                        <td><span className="badge badge-info">{seq.sequence_type?.replace(/_/g, ' ')}</span></td>
                        <td>{seq.priority ?? '\u2014'}</td>
                        <td>
                          <span className={`badge ${seq.enabled ? 'badge-success' : 'badge-neutral'}`}>
                            <span className="badge-dot" /> {seq.enabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </td>
                        <td style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>{formatDateTime(seq.last_run_at)}</td>
                        <td>{seq.run_count ?? 0}</td>
                        <td>
                          <button
                            className="icon-btn-sm"
                            title="Run now"
                            onClick={() => runSequence.mutate(seq.id, {
                          })}
                            disabled={runSequence.isPending}
                          >
                            <Play size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}

          {activeTab === 'rules' && (
            <>
              {rulesLoading ? (
                <LoadingState rows={3} />
              ) : rules.length === 0 ? (
                <div className="empty-state">
                  <h3>No automation rules</h3>
                  <p>Rules automatically trigger sequences when conditions are met — like shedding load when demand exceeds a threshold.</p>
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
                    {rules.map((rule: any) => (
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
                        <td style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>{formatDateTime(rule.last_triggered_at)}</td>
                        <td>{rule.execution_count_today ?? 0}</td>
                        <td>
                          <button
                            className="icon-btn-sm"
                            title={rule.enabled ? 'Disable' : 'Enable'}
                            onClick={() => toggleRule(rule.id, rule.enabled)}
                          >
                            {rule.enabled ? <PowerOff size={14} /> : <Power size={14} />}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
          {activeTab === 'commands' && (
            <>
              {cmdLoading ? (
                <LoadingState rows={4} />
              ) : commands.length === 0 ? (
                <EmptyState
                  icon={<CheckCircle size={22} />}
                  title="No commands"
                  description="Commands issued via control sequences or plant control will appear here."
                />
              ) : (
                <>
                  {pendingApprovalCount > 0 && (
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '10px 16px', background: 'color-mix(in srgb, var(--warning) 12%, transparent)',
                      borderBottom: '1px solid var(--border)', fontSize: 13,
                    }}>
                      <Shield size={14} style={{ color: 'var(--warning)' }} />
                      <strong>{pendingApprovalCount} command{pendingApprovalCount !== 1 ? 's' : ''} awaiting approval</strong>
                      <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>— Review and approve before they execute</span>
                    </div>
                  )}
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Command</th>
                        <th>State</th>
                        <th>Source</th>
                        <th>Issued</th>
                        <th style={{ width: 120 }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {commands.map((cmd: PlantCommand) => {
                        const target = (cmd.parameters.compressor_name || cmd.parameters.zone_name || cmd.parameters.device_name) as string | undefined
                        return (
                          <tr key={cmd.id}>
                            <td>
                              <span className="cell-primary">{cmd.command_type.replace(/_/g, ' ')}</span>
                              {target && <span className="cell-secondary">{target}</span>}
                            </td>
                            <td>
                              <span className={`badge ${CMD_STATE_BADGE[cmd.state] ?? 'badge-neutral'}`}>
                                <span className="badge-dot" /> {cmd.state.replace(/_/g, ' ')}
                              </span>
                            </td>
                            <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{cmd.source}</td>
                            <td>
                              <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text-tertiary)' }}>
                                <Clock size={12} /> {formatRelTime(cmd.issued_at)}
                              </span>
                            </td>
                            <td>
                              <div style={{ display: 'flex', gap: 4 }}>
                                {cmd.state === 'pending_approval' && (
                                  <button
                                    className="btn-primary"
                                    style={{ padding: '3px 8px', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}
                                    onClick={() => approveCmd.mutate(cmd.id)}
                                    disabled={approveCmd.isPending}
                                    title="Approve — release for execution"
                                  >
                                    <CheckCircle size={12} /> Approve
                                  </button>
                                )}
                                {(cmd.state === 'pending' || cmd.state === 'pending_approval') && (
                                  <button
                                    className="btn-secondary"
                                    style={{ padding: '3px 8px', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}
                                    onClick={() => cancelCmd.mutate(cmd.id)}
                                    disabled={cancelCmd.isPending}
                                    title="Cancel — prevent execution"
                                  >
                                    <XCircle size={12} /> Cancel
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </>
              )}
            </>
          )}

          {activeTab === 'audit' && (
            <>
              {auditLoading ? (
                <LoadingState rows={5} />
              ) : auditLogs.length === 0 ? (
                <EmptyState
                  icon={<Shield size={22} />}
                  title="No audit entries"
                  description="Every control action taken at this facility is logged here."
                />
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Action</th>
                      <th>Target</th>
                      <th>Result</th>
                      <th>When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.map((log: any) => (
                      <tr key={log.id}>
                        <td><span className="cell-primary">{log.action.replace(/_/g, ' ')}</span></td>
                        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                          {log.target_name || log.target_type}
                        </td>
                        <td>
                          <span className={`badge ${log.result === 'queued' || log.result === 'ok' ? 'badge-success' : log.result === 'failed' ? 'badge-danger' : 'badge-neutral'}`}>
                            {log.result ?? '—'}
                          </span>
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{formatRelTime(log.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      </div>

      {showSeqModal && <CreateSequenceModal facilityId={facilityId!} onClose={() => setShowSeqModal(false)} />}
      {showRuleModal && <CreateRuleModal facilityId={facilityId!} onClose={() => setShowRuleModal(false)} />}
    </div>
  )
}

/* ── Create Sequence Modal ─────────────────────────────── */
function CreateSequenceModal({ facilityId, onClose }: { facilityId: string; onClose: () => void }) {
  const createSeq = useCreateSequence(facilityId)
  const [form, setForm] = useState({
    name: '', description: '', sequence_type: 'pre_cool', priority: '5',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createSeq.mutate({
      name: form.name,
      description: form.description || undefined,
      sequence_type: form.sequence_type,
      priority: parseInt(form.priority) || 5,
      steps: [{ action: 'set_setpoint', target: 'all_zones', params: {} }],
    }, {
      onSuccess: () => onClose(),
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>New Control Sequence</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Sequence name</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Evening Pre-Cool" required autoFocus />
          </div>
          <div className="field">
            <label>Description</label>
            <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="What this sequence does..." rows={2} />
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 2 }}>
              <label>Type</label>
              <select value={form.sequence_type} onChange={e => setForm({ ...form, sequence_type: e.target.value })}>
                {SEQUENCE_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Priority</label>
              <input type="number" value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })} min="1" max="10" />
            </div>
          </div>
          {createSeq.isError && <p className="text-danger" style={{ fontSize: 12 }}>Failed to create sequence. Check your inputs.</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createSeq.isPending}>
              {createSeq.isPending ? 'Creating...' : <><Plus size={14} /> Create Sequence</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/* ── Create Rule Modal ─────────────────────────────────── */
function CreateRuleModal({ facilityId, onClose }: { facilityId: string; onClose: () => void }) {
  const createRule = useCreateAutomationRule(facilityId)
  const [form, setForm] = useState({
    name: '', description: '',
    trigger_metric: 'demand_kw', trigger_operator: 'gt', trigger_value: '',
    action_type: 'run_sequence', cooldown: '15', maxPerDay: '10',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createRule.mutate({
      name: form.name,
      description: form.description || undefined,
      trigger_conditions: {
        metric: form.trigger_metric,
        operator: form.trigger_operator,
        value: parseFloat(form.trigger_value),
      },
      actions: [{ type: form.action_type, params: {} }],
      cooldown_minutes: parseInt(form.cooldown) || 15,
      max_executions_per_day: parseInt(form.maxPerDay) || 10,
    }, {
      onSuccess: () => onClose(),
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>New Automation Rule</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Rule name</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Peak Demand Load Shed" required autoFocus />
          </div>
          <div className="field">
            <label>Description</label>
            <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="When to trigger and what it does" />
          </div>
          <div style={{ padding: '10px 14px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Trigger Condition</span>
            <div className="field-row" style={{ marginTop: 8 }}>
              <div className="field" style={{ flex: 2 }}>
                <label>Metric</label>
                <select value={form.trigger_metric} onChange={e => setForm({ ...form, trigger_metric: e.target.value })}>
                  {TRIGGER_METRICS.map(m => <option key={m} value={m}>{m.replace(/_/g, ' ')}</option>)}
                </select>
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Operator</label>
                <select value={form.trigger_operator} onChange={e => setForm({ ...form, trigger_operator: e.target.value })}>
                  {TRIGGER_OPERATORS.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Value</label>
                <input type="number" value={form.trigger_value} onChange={e => setForm({ ...form, trigger_value: e.target.value })} placeholder="500" required />
              </div>
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 2 }}>
              <label>Action</label>
              <select value={form.action_type} onChange={e => setForm({ ...form, action_type: e.target.value })}>
                {ACTION_TYPES.map(a => <option key={a} value={a}>{a.replace(/_/g, ' ')}</option>)}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Cooldown (min)</label>
              <input type="number" value={form.cooldown} onChange={e => setForm({ ...form, cooldown: e.target.value })} />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Max/day</label>
              <input type="number" value={form.maxPerDay} onChange={e => setForm({ ...form, maxPerDay: e.target.value })} />
            </div>
          </div>
          {createRule.isError && <p className="text-danger" style={{ fontSize: 12 }}>Failed to create rule.</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createRule.isPending}>
              {createRule.isPending ? 'Creating...' : <><Plus size={14} /> Create Rule</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
