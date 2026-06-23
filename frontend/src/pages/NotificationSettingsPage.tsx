import { useState, useEffect, useCallback } from 'react'
import { api, NotificationPolicy, NotificationPolicyCreate, NotificationChannelRecord } from '../lib/api'
import PageHeader from '../components/ui/PageHeader'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { Bell, Hash, Volume2 } from 'lucide-react'

const SEVERITIES = ['info', 'low', 'medium', 'high', 'critical'] as const
const CATEGORIES = ['temperature', 'pressure', 'equipment', 'power', 'refrigerant', 'connectivity', 'compliance', 'security'] as const

const SEV_COLOR: Record<string, string> = {
  info: 'var(--muted)',
  low: 'var(--ok)',
  medium: 'var(--warn)',
  high: '#DD6B20',
  critical: 'var(--crit)',
}

const HOUR_OPTS = Array.from({ length: 24 }, (_, i) => ({
  value: i,
  label: `${String(i).padStart(2, '0')}:00 UTC`,
}))

const DEFAULT_POLICY: NotificationPolicyCreate = {
  name: 'My alerts',
  min_severity: 'high',
  quiet_hours_enabled: false,
  quiet_hours_start: 22,
  quiet_hours_end: 7,
  quiet_hours_bypass_severity: 'critical',
  cooldown_minutes: 60,
  digest_mode: false,
  digest_interval_hours: 4,
  escalation_enabled: false,
  escalation_delay_minutes: 30,
  escalation_min_severity: 'critical',
}

// ── Policy form modal ──────────────────────────────────────────────────────

function PolicyModal({
  initial,
  channels,
  onSave,
  onClose,
}: {
  initial: NotificationPolicyCreate & { id?: string }
  channels: NotificationChannelRecord[]
  onSave: (data: NotificationPolicyCreate & { id?: string }) => Promise<void>
  onClose: () => void
}) {
  const [form, setForm] = useState({ ...initial })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const set = (k: keyof NotificationPolicyCreate, v: unknown) =>
    setForm(f => ({ ...f, [k]: v }))

  const toggleCategory = (cat: string) => {
    const cur = form.categories ?? []
    set('categories', cur.includes(cat) ? cur.filter(c => c !== cat) : [...cur, cat])
  }

  const toggleChannel = (id: string) => {
    const cur = form.channel_ids ?? []
    set('channel_ids', cur.includes(id) ? cur.filter(c => c !== id) : [...cur, id])
  }

  const handleSave = async () => {
    setSaving(true)
    setErr(null)
    try {
      await onSave(form)
      onClose()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 640, maxHeight: '90vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{form.id ? 'Edit policy' : 'New notification policy'}</h2>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

          {/* Name */}
          <div className="form-row">
            <div>
              <label>Policy name</label>
              <input value={form.name ?? ''} onChange={e => set('name', e.target.value)} placeholder="My alerts" />
            </div>
          </div>

          {/* Severity threshold */}
          <div>
            <label style={{ display: 'block', marginBottom: 8 }}>Minimum severity</label>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>
              Only notify for alerts at or above this level.
            </p>
            <div style={{ display: 'flex', gap: 6 }}>
              {SEVERITIES.map(s => (
                <button
                  key={s}
                  onClick={() => set('min_severity', s)}
                  style={{
                    flex: 1,
                    padding: '6px 4px',
                    border: `1px solid ${form.min_severity === s ? SEV_COLOR[s] : 'var(--border)'}`,
                    borderRadius: 4,
                    background: form.min_severity === s ? SEV_COLOR[s] + '22' : 'transparent',
                    color: form.min_severity === s ? SEV_COLOR[s] : 'var(--muted)',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                    textTransform: 'uppercase',
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Categories */}
          <div>
            <label style={{ display: 'block', marginBottom: 8 }}>Alert categories</label>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>
              Leave all unselected to receive every category.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {CATEGORIES.map(cat => {
                const selected = !form.categories || form.categories.includes(cat)
                return (
                  <button
                    key={cat}
                    onClick={() => toggleCategory(cat)}
                    style={{
                      padding: '4px 10px',
                      border: `1px solid ${selected ? 'var(--accent)' : 'var(--border)'}`,
                      borderRadius: 12,
                      background: selected ? 'var(--accent-dim)' : 'transparent',
                      color: selected ? 'var(--accent)' : 'var(--muted)',
                      fontSize: 12,
                      cursor: 'pointer',
                    }}
                  >
                    {cat}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Channels */}
          <div>
            <label style={{ display: 'block', marginBottom: 8 }}>Delivery channels</label>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>
              Leave unselected to use all enabled channels.
            </p>
            {channels.length === 0 ? (
              <p style={{ fontSize: 13, color: 'var(--muted)' }}>No channels configured yet. Add one in the Channels tab.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {channels.map(ch => {
                  const selected = !form.channel_ids || form.channel_ids.includes(ch.id)
                  return (
                    <label key={ch.id} style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13 }}>
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleChannel(ch.id)}
                      />
                      <span style={{ fontWeight: 600 }}>{ch.name}</span>
                      <span style={{ color: 'var(--muted)', fontSize: 11, textTransform: 'uppercase' }}>{ch.channel_type}</span>
                    </label>
                  )
                })}
              </div>
            )}
          </div>

          {/* Quiet hours */}
          <div style={{ background: 'var(--surface)', borderRadius: 6, padding: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: 4 }}>
              <input
                type="checkbox"
                checked={!!form.quiet_hours_enabled}
                onChange={e => set('quiet_hours_enabled', e.target.checked)}
              />
              <span style={{ fontWeight: 600, fontSize: 14 }}>Quiet hours</span>
            </label>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: form.quiet_hours_enabled ? 12 : 0 }}>
              Suppress notifications during off hours. All times are UTC.
            </p>
            {form.quiet_hours_enabled && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div>
                    <label>Start (UTC)</label>
                    <select value={form.quiet_hours_start ?? 22} onChange={e => set('quiet_hours_start', +e.target.value)}>
                      {HOUR_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label>End (UTC)</label>
                    <select value={form.quiet_hours_end ?? 7} onChange={e => set('quiet_hours_end', +e.target.value)}>
                      {HOUR_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                </div>
                <div>
                  <label>Still notify for</label>
                  <select
                    value={form.quiet_hours_bypass_severity ?? ''}
                    onChange={e => set('quiet_hours_bypass_severity', e.target.value || null)}
                  >
                    <option value="">Nothing — full silence</option>
                    {SEVERITIES.map(s => (
                      <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)} and above</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* Cooldown */}
          <div>
            <label style={{ display: 'block', marginBottom: 4 }}>Cooldown between alerts</label>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
              Don't re-notify for the same alert type at the same site within this window.
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="number"
                min={0}
                max={10080}
                value={form.cooldown_minutes ?? 60}
                onChange={e => set('cooldown_minutes', +e.target.value)}
                style={{ width: 80 }}
              />
              <span style={{ fontSize: 13, color: 'var(--muted)' }}>minutes</span>
              <span style={{ fontSize: 12, color: 'var(--muted)' }}>
                ({form.cooldown_minutes && form.cooldown_minutes >= 60
                  ? `${(form.cooldown_minutes / 60).toFixed(1).replace(/\.0$/, '')}h`
                  : `${form.cooldown_minutes ?? 0}m`})
              </span>
            </div>
          </div>

          {/* Digest */}
          <div style={{ background: 'var(--surface)', borderRadius: 6, padding: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: 4 }}>
              <input
                type="checkbox"
                checked={!!form.digest_mode}
                onChange={e => set('digest_mode', e.target.checked)}
              />
              <span style={{ fontWeight: 600, fontSize: 14 }}>Digest mode</span>
            </label>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: form.digest_mode ? 12 : 0 }}>
              Batch alerts into a single summary email instead of per-alert messages.
            </p>
            {form.digest_mode && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 13 }}>Send every</span>
                <select
                  value={form.digest_interval_hours ?? 4}
                  onChange={e => set('digest_interval_hours', +e.target.value)}
                  style={{ width: 100 }}
                >
                  {[1, 2, 4, 8, 12, 24].map(h => (
                    <option key={h} value={h}>{h}h</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Escalation */}
          <div style={{ background: 'var(--surface)', borderRadius: 6, padding: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', marginBottom: 4 }}>
              <input
                type="checkbox"
                checked={!!form.escalation_enabled}
                onChange={e => set('escalation_enabled', e.target.checked)}
              />
              <span style={{ fontWeight: 600, fontSize: 14 }}>Escalation</span>
            </label>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: form.escalation_enabled ? 12 : 0 }}>
              If an alert isn't acknowledged within the delay window, send a second notification.
            </p>
            {form.escalation_enabled && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div>
                    <label>Escalate after</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <input
                        type="number"
                        min={1}
                        max={1440}
                        value={form.escalation_delay_minutes ?? 30}
                        onChange={e => set('escalation_delay_minutes', +e.target.value)}
                        style={{ width: 70 }}
                      />
                      <span style={{ fontSize: 13, color: 'var(--muted)' }}>min</span>
                    </div>
                  </div>
                  <div>
                    <label>For severity ≥</label>
                    <select
                      value={form.escalation_min_severity ?? 'critical'}
                      onChange={e => set('escalation_min_severity', e.target.value)}
                    >
                      {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            )}
          </div>

          {err && <p style={{ color: 'var(--crit)', fontSize: 13 }}>{err}</p>}

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button className="btn" onClick={onClose}>Cancel</button>
            <button className="btn btn-accent" onClick={handleSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save policy'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Channel form modal ─────────────────────────────────────────────────────

function ChannelModal({
  initial,
  onSave,
  onClose,
}: {
  initial?: Partial<NotificationChannelRecord>
  onSave: (data: { name: string; channel_type: string; config: Record<string, string>; enabled: boolean }) => Promise<void>
  onClose: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [type, setType] = useState(initial?.channel_type ?? 'email')
  const [config, setConfig] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(initial?.config ?? {}).map(([k, v]) => [k, String(v)]))
  )
  const [saving, setSaving] = useState(false)

  const setConf = (k: string, v: string) => setConfig(c => ({ ...c, [k]: v }))

  const handleSave = async () => {
    setSaving(true)
    try { await onSave({ name, channel_type: type, config, enabled: true }) }
    finally { setSaving(false) }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{initial?.id ? 'Edit channel' : 'Add channel'}</h2>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="form-row two">
            <div>
              <label>Name</label>
              <input value={name} onChange={e => setName(e.target.value)} placeholder="Ops team email" />
            </div>
            <div>
              <label>Type</label>
              <select value={type} onChange={e => { setType(e.target.value); setConfig({}) }}>
                <option value="email">Email</option>
                <option value="slack">Slack</option>
                <option value="webhook">Webhook</option>
                <option value="sms">SMS (Twilio)</option>
              </select>
            </div>
          </div>

          {type === 'email' && (
            <>
              <div className="form-row">
                <div>
                  <label>Recipients (comma-separated)</label>
                  <input value={config.recipients ?? ''} onChange={e => setConf('recipients', e.target.value)} placeholder="ops@company.com, manager@company.com" />
                </div>
              </div>
              <p style={{ fontSize: 11, color: 'var(--muted)' }}>Leave SMTP fields empty to use the org-level SMTP settings.</p>
            </>
          )}
          {type === 'slack' && (
            <div className="form-row">
              <div>
                <label>Slack Incoming Webhook URL</label>
                <input value={config.webhook_url ?? ''} onChange={e => setConf('webhook_url', e.target.value)} placeholder="https://hooks.slack.com/…" />
              </div>
            </div>
          )}
          {type === 'webhook' && (
            <div className="form-row">
              <div>
                <label>Webhook URL</label>
                <input value={config.url ?? ''} onChange={e => setConf('url', e.target.value)} placeholder="https://your-system.com/webhook" />
              </div>
            </div>
          )}
          {type === 'sms' && (
            <>
              <div className="form-row">
                <div>
                  <label>To numbers (comma-separated)</label>
                  <input value={config.recipients ?? ''} onChange={e => setConf('recipients', e.target.value)} placeholder="+15551234567, +15559876543" />
                </div>
              </div>
              <div className="form-row two">
                <div><label>Twilio Account SID</label><input value={config.account_sid ?? ''} onChange={e => setConf('account_sid', e.target.value)} /></div>
                <div><label>Auth Token</label><input type="password" value={config.auth_token ?? ''} onChange={e => setConf('auth_token', e.target.value)} /></div>
              </div>
              <div className="form-row"><div><label>From number</label><input value={config.from_number ?? ''} onChange={e => setConf('from_number', e.target.value)} placeholder="+15550000000" /></div></div>
            </>
          )}

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button className="btn" onClick={onClose}>Cancel</button>
            <button className="btn btn-accent" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : 'Save channel'}</button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main page ──────────────────────────────────────────────────────────────

type Tab = 'policies' | 'channels' | 'logs'

export default function NotificationSettingsPage() {
  const [tab, setTab] = useState<Tab>('policies')
  const [policies, setPolicies] = useState<NotificationPolicy[]>([])
  const [channels, setChannels] = useState<NotificationChannelRecord[]>([])
  const [logs, setLogs] = useState<{ id: string; subject: string; channel_type: string; status: string; sent_at: string; error_message: string | null }[]>([])
  const [loading, setLoading] = useState(true)
  const [policyModal, setPolicyModal] = useState<(NotificationPolicyCreate & { id?: string }) | null>(null)
  const [channelModal, setChannelModal] = useState<Partial<NotificationChannelRecord> | true | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ id: string; ok: boolean } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [p, c] = await Promise.all([
        api.listNotificationPolicies(),
        api.listNotificationChannels(),
      ])
      setPolicies(p.policies)
      setChannels(c.channels)
      if (tab === 'logs') {
        const l = await api.listNotificationLogs(100)
        setLogs(l.logs as typeof logs)
      }
    } finally {
      setLoading(false)
    }
  }, [tab])

  useEffect(() => { load() }, [load])

  const savePolicy = async (data: NotificationPolicyCreate & { id?: string }) => {
    if (data.id) {
      await api.updateNotificationPolicy(data.id, data)
    } else {
      await api.createNotificationPolicy(data)
    }
    await load()
  }

  const deletePolicy = async (id: string) => {
    if (!confirm('Delete this notification policy?')) return
    await api.deleteNotificationPolicy(id)
    await load()
  }

  const testPolicy = async (id: string) => {
    setTestingId(id)
    try {
      await api.testNotificationPolicy(id)
      setTestResult({ id, ok: true })
    } catch {
      setTestResult({ id, ok: false })
    } finally {
      setTestingId(null)
      setTimeout(() => setTestResult(null), 4000)
    }
  }

  const saveChannel = async (data: Parameters<typeof api.createNotificationChannel>[0] & { id?: string }) => {
    if (data.id) {
      await api.updateNotificationChannel(data.id, data)
    } else {
      await api.createNotificationChannel(data)
    }
    setChannelModal(null)
    await load()
  }

  const deleteChannel = async (id: string) => {
    if (!confirm('Delete this channel?')) return
    await api.deleteNotificationChannel(id)
    await load()
  }

  const testChannel = async (id: string) => {
    setTestingId(id)
    try {
      await api.testNotificationChannel(id)
      setTestResult({ id, ok: true })
    } catch {
      setTestResult({ id, ok: false })
    } finally {
      setTestingId(null)
      setTimeout(() => setTestResult(null), 4000)
    }
  }

  const policyStatusSummary = (p: NotificationPolicy) => {
    const parts: string[] = []
    parts.push(`≥ ${p.min_severity}`)
    if (p.categories) parts.push(p.categories.slice(0, 2).join(', ') + (p.categories.length > 2 ? ` +${p.categories.length - 2}` : ''))
    if (p.quiet_hours_enabled) parts.push(`quiet ${String(p.quiet_hours_start).padStart(2,'0')}–${String(p.quiet_hours_end).padStart(2,'0')}h UTC`)
    if (p.cooldown_minutes) parts.push(`cooldown ${p.cooldown_minutes}m`)
    if (p.digest_mode) parts.push(`digest ${p.digest_interval_hours}h`)
    if (p.escalation_enabled) parts.push(`escalate ${p.escalation_delay_minutes}m`)
    return parts.join(' · ')
  }

  return (
    <div className="page">
      <PageHeader
        title="Notifications"
        subtitle="Configure when and how you get alerted."
      >
        {tab === 'policies' && (
          <button className="btn btn-accent" onClick={() => setPolicyModal({ ...DEFAULT_POLICY })}>
            New policy
          </button>
        )}
        {tab === 'channels' && (
          <button className="btn btn-accent" onClick={() => setChannelModal(true)}>
            Add channel
          </button>
        )}
      </PageHeader>

      {/* Tabs */}
      <div style={{ borderBottom: '1px solid var(--border)', marginBottom: 24, display: 'flex', gap: 0 }}>
        {(['policies', 'channels', 'logs'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '8px 18px',
              border: 'none',
              borderBottom: `2px solid ${tab === t ? 'var(--accent)' : 'transparent'}`,
              background: 'none',
              color: tab === t ? 'var(--accent)' : 'var(--muted)',
              fontWeight: tab === t ? 600 : 400,
              fontSize: 14,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {loading ? <LoadingState /> : (
        <>
          {/* ── Policies tab ── */}
          {tab === 'policies' && (
            policies.length === 0 ? (
              <EmptyState
                icon={<Bell size={24} />}
                title="No notification policies"
                description="Create a policy to start receiving alert notifications."
                action={<button className="btn btn-accent" onClick={() => setPolicyModal({ ...DEFAULT_POLICY })}>Create your first policy</button>}
              />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {policies.map(p => (
                  <div key={p.id} className="panel" style={{ padding: 0 }}>
                    <div className="panel-bar" style={{ justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <span
                          style={{
                            width: 8, height: 8, borderRadius: '50%',
                            background: p.enabled ? 'var(--ok)' : 'var(--muted)',
                            display: 'inline-block',
                          }}
                        />
                        <span className="t" style={{ fontWeight: 600 }}>{p.name}</span>
                        {!p.enabled && <span style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase' }}>disabled</span>}
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        {testResult?.id === p.id && (
                          <span style={{ fontSize: 12, color: testResult.ok ? 'var(--ok)' : 'var(--crit)' }}>
                            {testResult.ok ? '✓ sent' : '✗ failed'}
                          </span>
                        )}
                        <button
                          className="btn"
                          style={{ padding: '4px 10px', fontSize: 12 }}
                          disabled={testingId === p.id}
                          onClick={() => testPolicy(p.id)}
                        >
                          {testingId === p.id ? 'Testing…' : 'Test'}
                        </button>
                        <button
                          className="btn"
                          style={{ padding: '4px 10px', fontSize: 12 }}
                          onClick={() => setPolicyModal({ ...p, facility_ids: p.facility_ids ?? undefined, categories: p.categories ?? undefined })}
                        >
                          Edit
                        </button>
                        <button
                          className="btn"
                          style={{ padding: '4px 10px', fontSize: 12, color: 'var(--crit)' }}
                          onClick={() => deletePolicy(p.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <div style={{ padding: '10px 16px' }}>
                      <p style={{ margin: 0, fontSize: 12, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>
                        {policyStatusSummary(p)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}

          {/* ── Channels tab ── */}
          {tab === 'channels' && (
            channels.length === 0 ? (
              <EmptyState
                icon={<Hash size={24} />}
                title="No channels configured"
                description="Add an email, Slack, or webhook channel to start delivering alerts."
                action={<button className="btn btn-accent" onClick={() => setChannelModal(true)}>Add your first channel</button>}
              />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {channels.map(ch => (
                  <div key={ch.id} className="panel" style={{ padding: 0 }}>
                    <div className="panel-bar" style={{ justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: ch.enabled ? 'var(--ok)' : 'var(--muted)', display: 'inline-block' }} />
                        <span className="t" style={{ fontWeight: 600 }}>{ch.name}</span>
                        <span style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', fontFamily: 'var(--mono)' }}>{ch.channel_type}</span>
                        {ch.min_severity && (
                          <span style={{ fontSize: 11, color: SEV_COLOR[ch.min_severity], textTransform: 'uppercase' }}>≥ {ch.min_severity}</span>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        {testResult?.id === ch.id && (
                          <span style={{ fontSize: 12, color: testResult.ok ? 'var(--ok)' : 'var(--crit)' }}>
                            {testResult.ok ? '✓ sent' : '✗ failed'}
                          </span>
                        )}
                        <button className="btn" style={{ padding: '4px 10px', fontSize: 12 }} disabled={testingId === ch.id} onClick={() => testChannel(ch.id)}>
                          {testingId === ch.id ? 'Testing…' : 'Test'}
                        </button>
                        <button className="btn" style={{ padding: '4px 10px', fontSize: 12 }} onClick={() => setChannelModal(ch)}>Edit</button>
                        <button className="btn" style={{ padding: '4px 10px', fontSize: 12, color: 'var(--crit)' }} onClick={() => deleteChannel(ch.id)}>Delete</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}

          {/* ── Logs tab ── */}
          {tab === 'logs' && (
            logs.length === 0 ? (
              <EmptyState icon={<Volume2 size={24} />} title="No delivery logs yet" description="Logs appear here after notifications are sent." />
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['Subject', 'Channel', 'Status', 'Sent at'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '6px 10px', color: 'var(--muted)', fontWeight: 500 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {logs.map(l => (
                    <tr key={l.id} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '8px 10px', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.subject}</td>
                      <td style={{ padding: '8px 10px', color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 11 }}>{l.channel_type}</td>
                      <td style={{ padding: '8px 10px' }}>
                        <span style={{ color: l.status === 'sent' ? 'var(--ok)' : 'var(--crit)', fontSize: 12, fontWeight: 600, textTransform: 'uppercase' }}>
                          {l.status}
                        </span>
                        {l.error_message && <span style={{ fontSize: 11, color: 'var(--muted)', marginLeft: 6 }}>{l.error_message.slice(0, 60)}</span>}
                      </td>
                      <td style={{ padding: '8px 10px', color: 'var(--muted)', fontSize: 11 }}>{new Date(l.sent_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </>
      )}

      {policyModal && (
        <PolicyModal
          initial={policyModal}
          channels={channels}
          onSave={savePolicy}
          onClose={() => setPolicyModal(null)}
        />
      )}
      {channelModal && (
        <ChannelModal
          initial={channelModal === true ? undefined : channelModal}
          onSave={saveChannel as typeof saveChannel}
          onClose={() => setChannelModal(null)}
        />
      )}
    </div>
  )
}
