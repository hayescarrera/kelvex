import { useState, useCallback } from 'react'
import toast from 'react-hot-toast'
import {
  Loader2, Plus, X, Trash2, AlertTriangle, Bell, BellRing, ChevronDown,
  ChevronUp, Power, PowerOff, Play, Copy, Shield, Zap, Thermometer,
  Gauge, DoorOpen, Activity,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import { useSiteContext } from '../contexts/SiteContext'
import {
  useAutomationRules, useCreateAutomationRule, useUpdateAutomationRule,
  useDeleteAutomationRule, useSequences,
} from '../hooks/useControls'
import { useNotificationChannels, useUpdateNotificationChannel } from '../hooks/useNotifications'
import { useZones } from '../hooks/useZones'
import { useEquipment } from '../hooks/useEquipment'
import { useFacilities } from '../hooks/useFacilities'
import type { AutomationRule, AutomationRuleCreate, Zone, Equipment } from '../lib/api'

// ── Constants ───────────────────────────────────
const SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'] as const
const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--danger)',
  high: '#e67700',
  medium: 'var(--warning)',
  low: 'var(--info)',
  info: 'var(--text-secondary)',
}
const SEVERITY_LABELS: Record<string, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
}
const OPERATORS = [
  { value: '>', label: '>' },
  { value: '>=', label: '>=' },
  { value: '<', label: '<' },
  { value: '<=', label: '<=' },
  { value: '==', label: '=' },
  { value: '!=', label: '!=' },
]
const ZONE_METRICS = [
  { value: 'temp', label: 'Temperature', icon: Thermometer, unit: '°F' },
  { value: 'humidity', label: 'Humidity', icon: Gauge, unit: '%' },
  { value: 'door_open', label: 'Door Open', icon: DoorOpen, unit: '' },
]
const FACILITY_METRICS = [
  { value: 'demand_kw', label: 'Demand (kW)', icon: Zap, unit: 'kW' },
  { value: 'avg_temp', label: 'Avg Temperature', icon: Thermometer, unit: '°F' },
  { value: 'max_temp', label: 'Max Temperature', icon: Thermometer, unit: '°F' },
  { value: 'min_temp', label: 'Min Temperature', icon: Thermometer, unit: '°F' },
]
const EQUIPMENT_METRICS = [
  { value: 'suction_pressure', label: 'Suction Pressure', unit: 'PSI' },
  { value: 'discharge_pressure', label: 'Discharge Pressure', unit: 'PSI' },
  { value: 'oil_pressure', label: 'Oil Pressure', unit: 'PSI' },
  { value: 'motor_amps', label: 'Motor Amps', unit: 'A' },
  { value: 'discharge_temp', label: 'Discharge Temp', unit: '°F' },
  { value: 'oil_temp', label: 'Oil Temp', unit: '°F' },
  { value: 'runtime_hours', label: 'Runtime Hours', unit: 'hrs' },
]
const ALERT_CATEGORIES = [
  'temperature', 'humidity', 'equipment', 'demand', 'energy', 'door', 'system',
]
const ACTION_TYPES = [
  { value: 'create_alert', label: 'Create Alert' },
  { value: 'send_notification', label: 'Send Notification' },
  { value: 'execute_sequence', label: 'Execute Sequence' },
]

// ── Types ───────────────────────────────────────
interface Condition {
  source: string
  metric: string
  operator: string
  value: number | string
}
interface RuleAction {
  type: string
  message?: string
  severity?: string
  category?: string
  subject?: string
  body?: string
  channel_id?: string
  target?: string
}
interface RuleFormData {
  name: string
  description: string
  allConditions: Condition[]
  anyConditions: Condition[]
  actions: RuleAction[]
  cooldown_minutes: number
  max_executions_per_day: number
}

const emptyCondition = (): Condition => ({
  source: 'facility', metric: 'demand_kw', operator: '>', value: 0,
})
const emptyAction = (): RuleAction => ({
  type: 'create_alert', message: '', severity: 'high', category: 'system',
})
const defaultForm = (): RuleFormData => ({
  name: '',
  description: '',
  allConditions: [emptyCondition()],
  anyConditions: [],
  actions: [emptyAction()],
  cooldown_minutes: 30,
  max_executions_per_day: 10,
})

// ── Helpers ─────────────────────────────────────
function parseSource(src: string): { type: string; id?: string } {
  if (src === 'facility') return { type: 'facility' }
  const [type, id] = src.split(':')
  return { type, id }
}

function conditionLabel(c: Condition, zones: Zone[], equipment: Equipment[]): string {
  const { type, id } = parseSource(c.source)
  let sourceName = 'Facility'
  if (type === 'zone') {
    const z = zones.find(z => z.id === id)
    sourceName = z ? z.name : `Zone ${id?.slice(0, 8)}`
  } else if (type === 'equipment') {
    const e = equipment.find(e => e.id === id)
    sourceName = e ? e.name : `Equipment ${id?.slice(0, 8)}`
  }
  return `${sourceName} → ${c.metric} ${c.operator} ${c.value}`
}

function ruleToForm(rule: AutomationRule): RuleFormData {
  const tc = rule.trigger_conditions || {}
  return {
    name: rule.name,
    description: rule.description || '',
    allConditions: (tc.all as unknown as Condition[]) || [],
    anyConditions: (tc.any as unknown as Condition[]) || [],
    actions: (rule.actions as unknown as RuleAction[]) || [],
    cooldown_minutes: rule.cooldown_minutes,
    max_executions_per_day: rule.max_executions_per_day,
  }
}

function formToPayload(form: RuleFormData): AutomationRuleCreate {
  const trigger_conditions: Record<string, unknown> = {}
  if (form.allConditions.length) trigger_conditions.all = form.allConditions
  if (form.anyConditions.length) trigger_conditions.any = form.anyConditions
  return {
    name: form.name,
    description: form.description || undefined,
    trigger_conditions,
    actions: form.actions as unknown as Record<string, unknown>[],
    cooldown_minutes: form.cooldown_minutes,
    max_executions_per_day: form.max_executions_per_day,
  }
}

// ═══════════════════════════════════════════════════
// Condition Editor
// ═══════════════════════════════════════════════════
function ConditionEditor({
  condition, onChange, onRemove, zones, equipment,
}: {
  condition: Condition
  onChange: (c: Condition) => void
  onRemove: () => void
  zones: Zone[]
  equipment: Equipment[]
}) {
  const { type } = parseSource(condition.source)

  const handleSourceType = (newType: string) => {
    if (newType === 'facility') {
      onChange({ ...condition, source: 'facility', metric: 'demand_kw' })
    } else if (newType === 'zone') {
      const firstZone = zones[0]
      onChange({ ...condition, source: firstZone ? `zone:${firstZone.id}` : 'zone:', metric: 'temp' })
    } else if (newType === 'equipment') {
      const firstEq = equipment[0]
      onChange({ ...condition, source: firstEq ? `equipment:${firstEq.id}` : 'equipment:', metric: 'suction_pressure' })
    }
  }

  const handleSourceId = (id: string) => {
    onChange({ ...condition, source: `${type}:${id}` })
  }

  const metrics = type === 'zone' ? ZONE_METRICS
    : type === 'equipment' ? EQUIPMENT_METRICS
    : FACILITY_METRICS

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <select
        value={type}
        onChange={e => handleSourceType(e.target.value)}
        style={{ width: 130, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13 }}
      >
        <option value="facility">Facility</option>
        <option value="zone">Zone</option>
        <option value="equipment">Equipment</option>
      </select>

      {type === 'zone' && (
        <select
          value={parseSource(condition.source).id || ''}
          onChange={e => handleSourceId(e.target.value)}
          style={{ width: 160, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13 }}
        >
          {zones.map(z => <option key={z.id} value={z.id}>{z.name}</option>)}
          {!zones.length && <option value="">No zones</option>}
        </select>
      )}

      {type === 'equipment' && (
        <select
          value={parseSource(condition.source).id || ''}
          onChange={e => handleSourceId(e.target.value)}
          style={{ width: 160, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13 }}
        >
          {equipment.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
          {!equipment.length && <option value="">No equipment</option>}
        </select>
      )}

      <select
        value={condition.metric}
        onChange={e => onChange({ ...condition, metric: e.target.value })}
        style={{ width: 160, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13 }}
      >
        {metrics.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
      </select>

      <select
        value={condition.operator}
        onChange={e => onChange({ ...condition, operator: e.target.value })}
        style={{ width: 70, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13 }}
      >
        {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>

      <input
        type="number"
        value={condition.value}
        onChange={e => onChange({ ...condition, value: parseFloat(e.target.value) || 0 })}
        style={{ width: 80, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13 }}
      />

      <span className="text-muted" style={{ fontSize: 12 }}>
        {metrics.find(m => m.value === condition.metric)?.unit || ''}
      </span>

      <button className="icon-btn-sm" onClick={onRemove} title="Remove condition">
        <X size={14} />
      </button>
    </div>
  )
}

// ═══════════════════════════════════════════════════
// Action Editor
// ═══════════════════════════════════════════════════
function ActionEditor({
  action, onChange, onRemove, channels, sequences,
}: {
  action: RuleAction
  onChange: (a: RuleAction) => void
  onRemove: () => void
  channels: { id: string; name: string; channel_type: string }[]
  sequences: { id: string; name: string }[]
}) {
  return (
    <div style={{ padding: 12, border: '1px solid var(--border)', borderRadius: 8, background: 'var(--bg-primary)' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
        <select
          value={action.type}
          onChange={e => {
            const t = e.target.value
            if (t === 'create_alert') onChange({ type: t, message: '', severity: 'high', category: 'system' })
            else if (t === 'send_notification') onChange({ type: t, subject: '', body: '' })
            else if (t === 'execute_sequence') onChange({ type: t, target: sequences[0]?.id || '' })
          }}
          style={{ width: 180, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', fontSize: 13 }}
        >
          {ACTION_TYPES.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
        </select>
        <div style={{ flex: 1 }} />
        <button className="icon-btn-sm" onClick={onRemove} title="Remove action"><X size={14} /></button>
      </div>

      {action.type === 'create_alert' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <div className="field" style={{ flex: 1, margin: 0 }}>
              <label style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>Message</label>
              <input
                value={action.message || ''}
                onChange={e => onChange({ ...action, message: e.target.value })}
                placeholder="Alert message..."
              />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <div className="field" style={{ width: 140, margin: 0 }}>
              <label style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>Severity</label>
              <select
                value={action.severity || 'high'}
                onChange={e => onChange({ ...action, severity: e.target.value })}
              >
                {SEVERITIES.map(s => <option key={s} value={s}>{SEVERITY_LABELS[s]}</option>)}
              </select>
            </div>
            <div className="field" style={{ width: 140, margin: 0 }}>
              <label style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>Category</label>
              <select
                value={action.category || 'system'}
                onChange={e => onChange({ ...action, category: e.target.value })}
              >
                {ALERT_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
        </div>
      )}

      {action.type === 'send_notification' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="field" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>Channel</label>
            <select
              value={action.channel_id || ''}
              onChange={e => onChange({ ...action, channel_id: e.target.value || undefined })}
            >
              <option value="">All matching channels</option>
              {channels.map(ch => (
                <option key={ch.id} value={ch.id}>{ch.name} ({ch.channel_type})</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>Subject</label>
            <input
              value={action.subject || ''}
              onChange={e => onChange({ ...action, subject: e.target.value })}
              placeholder="Notification subject..."
            />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>Body</label>
            <textarea
              value={action.body || ''}
              onChange={e => onChange({ ...action, body: e.target.value })}
              placeholder="Notification body..."
              rows={2}
            />
          </div>
        </div>
      )}

      {action.type === 'execute_sequence' && (
        <div className="field" style={{ margin: 0 }}>
          <label style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>Sequence</label>
          <select
            value={action.target || ''}
            onChange={e => onChange({ ...action, target: e.target.value })}
          >
            {sequences.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            {!sequences.length && <option value="">No sequences available</option>}
          </select>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════
// Rule Builder Modal
// ═══════════════════════════════════════════════════
function RuleBuilderModal({
  onClose, onSave, editingRule, zones, equipment, channels, sequences, saving,
}: {
  onClose: () => void
  onSave: (form: RuleFormData) => void
  editingRule: AutomationRule | null
  zones: Zone[]
  equipment: Equipment[]
  channels: { id: string; name: string; channel_type: string }[]
  sequences: { id: string; name: string }[]
  saving: boolean
}) {
  const [form, setForm] = useState<RuleFormData>(
    editingRule ? ruleToForm(editingRule) : defaultForm()
  )

  const updateAllCondition = (idx: number, c: Condition) => {
    const next = [...form.allConditions]
    next[idx] = c
    setForm({ ...form, allConditions: next })
  }
  const updateAnyCondition = (idx: number, c: Condition) => {
    const next = [...form.anyConditions]
    next[idx] = c
    setForm({ ...form, anyConditions: next })
  }
  const updateAction = (idx: number, a: RuleAction) => {
    const next = [...form.actions]
    next[idx] = a
    setForm({ ...form, actions: next })
  }

  const valid = form.name.trim() &&
    (form.allConditions.length > 0 || form.anyConditions.length > 0) &&
    form.actions.length > 0

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 720, maxHeight: '90vh', overflow: 'auto' }} onClick={e => e.stopPropagation()}>
        <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <h3 style={{ margin: 0, fontSize: 16 }}>
            {editingRule ? 'Edit Alert Rule' : 'New Alert Rule'}
          </h3>
          <button className="icon-btn-sm" onClick={onClose}><X size={16} /></button>
        </div>

        <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Name & Description */}
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="field" style={{ flex: 2, margin: 0 }}>
              <label>Rule Name</label>
              <input
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. High temp zone alert"
              />
            </div>
            <div className="field" style={{ flex: 3, margin: 0 }}>
              <label>Description</label>
              <input
                value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })}
                placeholder="Optional description..."
              />
            </div>
          </div>

          {/* ALL Conditions */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span className="badge badge-info" style={{ fontSize: 11, fontWeight: 600 }}>ALL</span>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                All of these conditions must be true
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {form.allConditions.map((c, i) => (
                <ConditionEditor
                  key={i}
                  condition={c}
                  onChange={c => updateAllCondition(i, c)}
                  onRemove={() => setForm({ ...form, allConditions: form.allConditions.filter((_, j) => j !== i) })}
                  zones={zones}
                  equipment={equipment}
                />
              ))}
              <button
                className="btn-ghost"
                style={{ alignSelf: 'flex-start', fontSize: 12, padding: '4px 12px' }}
                onClick={() => setForm({ ...form, allConditions: [...form.allConditions, emptyCondition()] })}
              >
                <Plus size={12} /> Add AND condition
              </button>
            </div>
          </div>

          {/* ANY Conditions */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span className="badge badge-warning" style={{ fontSize: 11, fontWeight: 600 }}>ANY</span>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                At least one of these conditions must be true
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {form.anyConditions.map((c, i) => (
                <ConditionEditor
                  key={i}
                  condition={c}
                  onChange={c => updateAnyCondition(i, c)}
                  onRemove={() => setForm({ ...form, anyConditions: form.anyConditions.filter((_, j) => j !== i) })}
                  zones={zones}
                  equipment={equipment}
                />
              ))}
              <button
                className="btn-ghost"
                style={{ alignSelf: 'flex-start', fontSize: 12, padding: '4px 12px' }}
                onClick={() => setForm({ ...form, anyConditions: [...form.anyConditions, emptyCondition()] })}
              >
                <Plus size={12} /> Add OR condition
              </button>
            </div>
          </div>

          {/* Actions */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                Actions
              </span>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                What happens when conditions are met
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {form.actions.map((a, i) => (
                <ActionEditor
                  key={i}
                  action={a}
                  onChange={a => updateAction(i, a)}
                  onRemove={() => setForm({ ...form, actions: form.actions.filter((_, j) => j !== i) })}
                  channels={channels}
                  sequences={sequences}
                />
              ))}
              <button
                className="btn-ghost"
                style={{ alignSelf: 'flex-start', fontSize: 12, padding: '4px 12px' }}
                onClick={() => setForm({ ...form, actions: [...form.actions, emptyAction()] })}
              >
                <Plus size={12} /> Add action
              </button>
            </div>
          </div>

          {/* Execution limits */}
          <div style={{ display: 'flex', gap: 12 }}>
            <div className="field" style={{ width: 180, margin: 0 }}>
              <label>Cooldown (minutes)</label>
              <input
                type="number"
                min={1}
                value={form.cooldown_minutes}
                onChange={e => setForm({ ...form, cooldown_minutes: parseInt(e.target.value) || 30 })}
              />
            </div>
            <div className="field" style={{ width: 180, margin: 0 }}>
              <label>Max per day</label>
              <input
                type="number"
                min={1}
                value={form.max_executions_per_day}
                onChange={e => setForm({ ...form, max_executions_per_day: parseInt(e.target.value) || 10 })}
              />
            </div>
          </div>
        </div>

        <div className="modal-actions">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={!valid || saving} onClick={() => onSave(form)}>
            {saving && <Loader2 size={14} className="spin" />}
            {editingRule ? 'Update Rule' : 'Create Rule'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════
// Notification Channel Routing Section
// ═══════════════════════════════════════════════════
function ChannelRoutingCard({
  channel, facilities, onUpdate,
}: {
  channel: { id: string; name: string; channel_type: string; enabled: boolean; facility_ids: string[] | null; min_severity: string | null; categories: string[] | null }
  facilities: { id: string; name: string }[]
  onUpdate: (data: Record<string, unknown>) => void
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden' }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
          cursor: 'pointer', background: 'var(--bg-primary)',
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: channel.enabled ? 'var(--success)' : 'var(--text-secondary)',
        }} />
        <span style={{ fontWeight: 500, fontSize: 13, flex: 1 }}>{channel.name}</span>
        <span className="badge badge-neutral" style={{ fontSize: 11 }}>{channel.channel_type}</span>
        {channel.min_severity && (
          <span className="badge" style={{ fontSize: 11, background: SEVERITY_COLORS[channel.min_severity] + '22', color: SEVERITY_COLORS[channel.min_severity] }}>
            {'>='} {SEVERITY_LABELS[channel.min_severity]}
          </span>
        )}
        {channel.facility_ids && (
          <span className="badge badge-info" style={{ fontSize: 11 }}>
            {channel.facility_ids.length} {channel.facility_ids.length === 1 ? 'facility' : 'facilities'}
          </span>
        )}
        {channel.categories && (
          <span className="badge badge-neutral" style={{ fontSize: 11 }}>
            {channel.categories.length} {channel.categories.length === 1 ? 'category' : 'categories'}
          </span>
        )}
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </div>

      {expanded && (
        <div style={{ padding: '12px 14px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 12, background: 'var(--bg-secondary)' }}>
          {/* Min severity */}
          <div className="field" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, marginBottom: 2 }}>Minimum Severity</label>
            <select
              value={channel.min_severity || ''}
              onChange={e => onUpdate({ min_severity: e.target.value || null })}
            >
              <option value="">All severities</option>
              {SEVERITIES.map(s => <option key={s} value={s}>{SEVERITY_LABELS[s]}</option>)}
            </select>
          </div>

          {/* Facility filter */}
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4, display: 'block' }}>
              Facility Filter
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {facilities.map(f => {
                const checked = channel.facility_ids ? channel.facility_ids.includes(f.id) : false
                return (
                  <label key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, cursor: 'pointer', padding: '3px 8px', borderRadius: 4, border: '1px solid var(--border)', background: checked ? 'var(--accent-bg)' : 'transparent' }}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={e => {
                        let next: string[] | null
                        if (e.target.checked) {
                          next = [...(channel.facility_ids || []), f.id]
                        } else {
                          next = (channel.facility_ids || []).filter(id => id !== f.id)
                          if (!next.length) next = null
                        }
                        onUpdate({ facility_ids: next })
                      }}
                    />
                    {f.name}
                  </label>
                )
              })}
              {!facilities.length && <span className="text-muted" style={{ fontSize: 12 }}>No facilities</span>}
            </div>
            {!channel.facility_ids && (
              <span className="text-muted" style={{ fontSize: 11, marginTop: 2, display: 'block' }}>
                No filter — receives alerts from all facilities
              </span>
            )}
          </div>

          {/* Category filter */}
          <div>
            <label style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4, display: 'block' }}>
              Category Filter
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {ALERT_CATEGORIES.map(cat => {
                const checked = channel.categories ? channel.categories.includes(cat) : false
                return (
                  <label key={cat} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, cursor: 'pointer', padding: '3px 8px', borderRadius: 4, border: '1px solid var(--border)', background: checked ? 'var(--accent-bg)' : 'transparent' }}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={e => {
                        let next: string[] | null
                        if (e.target.checked) {
                          next = [...(channel.categories || []), cat]
                        } else {
                          next = (channel.categories || []).filter(c => c !== cat)
                          if (!next.length) next = null
                        }
                        onUpdate({ categories: next })
                      }}
                    />
                    {cat}
                  </label>
                )
              })}
            </div>
            {!channel.categories && (
              <span className="text-muted" style={{ fontSize: 11, marginTop: 2, display: 'block' }}>
                No filter — receives all alert categories
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════
// Rule Card (list item)
// ═══════════════════════════════════════════════════
function RuleCard({
  rule, onEdit, onToggle, onDelete, onDuplicate, zones, equipment,
}: {
  rule: AutomationRule
  onEdit: () => void
  onToggle: () => void
  onDelete: () => void
  onDuplicate: () => void
  zones: Zone[]
  equipment: Equipment[]
}) {
  const tc = rule.trigger_conditions || {}
  const allConds = (tc.all as unknown as Condition[]) || []
  const anyConds = (tc.any as unknown as Condition[]) || []
  const actions = (rule.actions as unknown as RuleAction[]) || []

  const severityAction = actions.find(a => a.type === 'create_alert')
  const severity = severityAction?.severity || 'info'

  return (
    <div className="card" style={{ cursor: 'pointer' }} onClick={onEdit}>
      <div className="card-body" style={{ padding: 14 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <div style={{
            width: 4, height: 36, borderRadius: 2, marginTop: 2, flexShrink: 0,
            background: SEVERITY_COLORS[severity] || 'var(--border)',
          }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ fontWeight: 600, fontSize: 14 }}>{rule.name}</span>
              {!rule.enabled && <span className="badge badge-neutral" style={{ fontSize: 10 }}>Disabled</span>}
              {rule.enabled && <span className="badge badge-success" style={{ fontSize: 10 }}>Active</span>}
            </div>
            {rule.description && (
              <p className="text-secondary" style={{ fontSize: 12, margin: '0 0 6px' }}>{rule.description}</p>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {allConds.map((c, i) => (
                <span key={`all-${i}`} className="badge badge-info" style={{ fontSize: 10 }}>
                  {conditionLabel(c, zones, equipment)}
                </span>
              ))}
              {anyConds.length > 0 && allConds.length > 0 && (
                <span className="text-muted" style={{ fontSize: 10, alignSelf: 'center' }}>+</span>
              )}
              {anyConds.map((c, i) => (
                <span key={`any-${i}`} className="badge badge-warning" style={{ fontSize: 10 }}>
                  {conditionLabel(c, zones, equipment)}
                </span>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 4, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
            <button className="icon-btn-sm" title={rule.enabled ? 'Disable' : 'Enable'} onClick={onToggle}>
              {rule.enabled ? <PowerOff size={13} /> : <Power size={13} />}
            </button>
            <button className="icon-btn-sm" title="Duplicate" onClick={onDuplicate}>
              <Copy size={13} />
            </button>
            <button className="icon-btn-sm" title="Delete" onClick={onDelete} style={{ color: 'var(--danger)' }}>
              <Trash2 size={13} />
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12, marginTop: 8, fontSize: 11, color: 'var(--text-secondary)' }}>
          <span>Actions: {actions.length}</span>
          <span>Cooldown: {rule.cooldown_minutes}m</span>
          <span>Today: {rule.execution_count_today}/{rule.max_executions_per_day}</span>
          {rule.last_triggered_at && (
            <span>Last: {new Date(rule.last_triggered_at).toLocaleString()}</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════
export default function AlertRulesPage() {
  const { site } = useSiteContext()
  const facilityId = site?.id

  const { data: ruleData, isLoading: rulesLoading } = useAutomationRules(facilityId)
  const { data: channelData } = useNotificationChannels()
  const { data: zoneData } = useZones(facilityId ?? '')
  const { data: eqData } = useEquipment(facilityId ?? '')
  const { data: seqData } = useSequences(facilityId)
  const { data: facData } = useFacilities()

  const rules = ruleData?.rules ?? []
  const channels = channelData?.channels ?? []
  const zones = zoneData?.zones ?? []
  const equipment = eqData?.equipment ?? []
  const sequences = seqData?.sequences ?? []
  const facilities = facData?.facilities ?? []

  const createRule = useCreateAutomationRule(facilityId ?? '')
  const updateRule = useUpdateAutomationRule(facilityId ?? '')
  const deleteRule = useDeleteAutomationRule(facilityId ?? '')
  const updateChannelMut = useUpdateNotificationChannel()

  const [showModal, setShowModal] = useState(false)
  const [editingRule, setEditingRule] = useState<AutomationRule | null>(null)
  const [tab, setTab] = useState<'rules' | 'routing'>('rules')

  const handleSave = useCallback(async (form: RuleFormData) => {
    const payload = formToPayload(form)
    try {
      if (editingRule) {
        await updateRule.mutateAsync({ ruleId: editingRule.id, data: payload })
        toast.success('Alert rule updated')
      } else {
        await createRule.mutateAsync(payload)
        toast.success('Alert rule created')
      }
      setShowModal(false)
      setEditingRule(null)
    } catch {
      toast.error('Failed to save alert rule')
    }
  }, [editingRule, updateRule, createRule])

  const handleDuplicate = useCallback((rule: AutomationRule) => {
    const form = ruleToForm(rule)
    form.name = `${form.name} (copy)`
    const payload = formToPayload(form)
    createRule.mutate(payload, {
      onSuccess: () => toast.success('Alert rule created'),
      onError: () => toast.error('Failed to create alert rule'),
    })
  }, [createRule])


  // Stats
  const activeRules = rules.filter(r => r.enabled).length
  const totalFirings = rules.reduce((sum, r) => sum + r.execution_count_today, 0)
  const alertRules = rules.filter(r => (r.actions as unknown as RuleAction[]).some(a => a.type === 'create_alert')).length

  if (!facilityId) {
    return (
      <div className="page-container">
        <PageHeader title="Alert Rules" subtitle="Configure alert triggers and notification routing" />
        <div className="content-area">
          <div className="card">
            <div className="card-body">
              <div className="empty-state">
                <div className="empty-icon"><Shield size={24} /></div>
                <h3>No facility selected</h3>
                <p>Choose a facility from the site selector to manage alert rules.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-container">
      <PageHeader title="Alert Rules" subtitle={`${site?.name} — Triggers, actions, and notification routing`}>
        <button className="btn-primary" onClick={() => { setEditingRule(null); setShowModal(true) }}>
          <Plus size={14} /> New Rule
        </button>
      </PageHeader>

      {/* Stat cards */}
      <div className="stat-grid stagger" style={{ marginTop: 20 }}>
        <StatCard icon={<Shield size={18} />} color="var(--accent)" value={String(rules.length)} label="Total Rules" />
        <StatCard icon={<Play size={18} />} color="var(--success)" value={String(activeRules)} label="Active" />
        <StatCard icon={<AlertTriangle size={18} />} color="var(--warning)" value={String(alertRules)} label="Alert Rules" />
        <StatCard icon={<Activity size={18} />} color="var(--info)" value={String(totalFirings)} label="Fired Today" />
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 0, marginTop: 20, borderBottom: '1px solid var(--border)' }}>
        <button
          onClick={() => setTab('rules')}
          style={{
            padding: '8px 20px', border: 'none', background: 'none', cursor: 'pointer',
            fontWeight: tab === 'rules' ? 600 : 400, fontSize: 13,
            color: tab === 'rules' ? 'var(--accent)' : 'var(--text-secondary)',
            borderBottom: tab === 'rules' ? '2px solid var(--accent)' : '2px solid transparent',
          }}
        >
          <Shield size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
          Rules ({rules.length})
        </button>
        <button
          onClick={() => setTab('routing')}
          style={{
            padding: '8px 20px', border: 'none', background: 'none', cursor: 'pointer',
            fontWeight: tab === 'routing' ? 600 : 400, fontSize: 13,
            color: tab === 'routing' ? 'var(--accent)' : 'var(--text-secondary)',
            borderBottom: tab === 'routing' ? '2px solid var(--accent)' : '2px solid transparent',
          }}
        >
          <BellRing size={14} style={{ marginRight: 6, verticalAlign: -2 }} />
          Notification Routing ({channels.length})
        </button>
      </div>

      {/* Rules tab */}
      {tab === 'rules' && (
        <div className="content-area" style={{ marginTop: 16 }}>
          {rulesLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Loader2 size={24} className="spin" />
            </div>
          ) : rules.length === 0 ? (
            <div className="card">
              <div className="card-body">
                <div className="empty-state">
                  <div className="empty-icon"><Shield size={24} /></div>
                  <h3>No alert rules yet</h3>
                  <p>Create rules to automatically trigger alerts when zone temperatures, equipment metrics, or demand thresholds are exceeded.</p>
                  <button className="btn-primary" onClick={() => { setEditingRule(null); setShowModal(true) }}>
                    <Plus size={14} /> Create First Rule
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {rules.map(rule => (
                <RuleCard
                  key={rule.id}
                  rule={rule}
                  zones={zones}
                  equipment={equipment}
                  onEdit={() => { setEditingRule(rule); setShowModal(true) }}
                  onToggle={() => updateRule.mutate({ ruleId: rule.id, data: { enabled: !rule.enabled } }, {
                    onSuccess: () => toast.success('Alert rule updated'),
                    onError: () => toast.error('Failed to update alert rule'),
                  })}
                  onDelete={() => {
                    if (confirm(`Delete rule "${rule.name}"?`)) deleteRule.mutate(rule.id, {
                      onSuccess: () => toast.success('Alert rule deleted'),
                      onError: () => toast.error('Failed to delete alert rule'),
                    })
                  }}
                  onDuplicate={() => handleDuplicate(rule)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Routing tab */}
      {tab === 'routing' && (
        <div className="content-area" style={{ marginTop: 16 }}>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-body" style={{ padding: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Bell size={15} style={{ color: 'var(--accent)' }} />
                <span style={{ fontSize: 13 }}>
                  Configure which facilities, severities, and categories each notification channel responds to.
                  Channels with no filters receive all notifications.
                </span>
              </div>
            </div>
          </div>

          {channels.length === 0 ? (
            <div className="card">
              <div className="card-body">
                <div className="empty-state">
                  <div className="empty-icon"><Bell size={24} /></div>
                  <h3>No notification channels</h3>
                  <p>Set up notification channels in Settings to configure routing.</p>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {channels.map(ch => (
                <ChannelRoutingCard
                  key={ch.id}
                  channel={ch}
                  facilities={facilities}
                  onUpdate={(data) => {
                    updateChannelMut.mutate({ channelId: ch.id, data: data as any })
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Builder modal */}
      {showModal && (
        <RuleBuilderModal
          onClose={() => { setShowModal(false); setEditingRule(null) }}
          onSave={handleSave}
          editingRule={editingRule}
          zones={zones}
          equipment={equipment}
          channels={channels.map(c => ({ id: c.id, name: c.name, channel_type: c.channel_type }))}
          sequences={sequences.map(s => ({ id: s.id, name: s.name }))}
          saving={createRule.isPending || updateRule.isPending}
        />
      )}
    </div>
  )
}

