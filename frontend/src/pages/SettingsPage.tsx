import { useState, useEffect } from 'react'
import { Sun, Moon, User, Bell, Shield, Database, Key, AlertTriangle, Check, Loader2, Download, Plus, Trash2, Play, Mail, Globe, MessageSquare, Phone, X, Clock, Users, Activity } from 'lucide-react'
import type { DetectionSettings } from '../lib/api'
import toast from 'react-hot-toast'
import { useTheme } from '../contexts/ThemeContext'
import { useAuth } from '../contexts/AuthContext'
import { useSiteContext } from '../contexts/SiteContext'
import PageHeader from '../components/ui/PageHeader'
import { api } from '../lib/api'
import type { NotificationChannelRecord, NotificationChannelCreate } from '../lib/api'
import {
  useNotificationChannels,
  useCreateNotificationChannel,
  useUpdateNotificationChannel,
  useDeleteNotificationChannel,
  useTestNotificationChannel,
  useNotificationLogs,
} from '../hooks/useNotifications'
// Team management moved to /team — UserManagementPage

type TempUnit = 'F' | 'C'

export default function SettingsPage() {
  const { theme, toggle } = useTheme()
  const { user, logout } = useAuth()
  const { facilities } = useSiteContext()
  const [activeSection, setActiveSection] = useState('profile')

  // Profile state
  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)

  // Detection settings state
  const [detectionSettings, setDetectionSettings] = useState<DetectionSettings>({ auto_detection: false, forecasting: false })
  const [detectionLoading, setDetectionLoading] = useState(false)
  const [detectionSaving, setDetectionSaving] = useState(false)
  const canManageDetection = user?.role === 'owner' || user?.role === 'admin'

  useEffect(() => {
    if (activeSection === 'detection') {
      setDetectionLoading(true)
      api.getDetectionSettings()
        .then(s => setDetectionSettings(s))
        .catch(() => {})
        .finally(() => setDetectionLoading(false))
    }
  }, [activeSection])

  async function toggleDetectionFeature(key: keyof DetectionSettings) {
    if (!canManageDetection) return
    const next = { ...detectionSettings, [key]: !detectionSettings[key] }
    setDetectionSettings(next)
    setDetectionSaving(true)
    try {
      const saved = await api.updateDetectionSettings({ [key]: next[key] })
      setDetectionSettings(saved)
      toast.success(next[key] ? 'Enabled' : 'Disabled')
    } catch {
      setDetectionSettings(detectionSettings)
      toast.error('Failed to save')
    } finally {
      setDetectionSaving(false)
    }
  }

  // Temperature unit — persisted in localStorage
  const [tempUnit, setTempUnit] = useState<TempUnit>(() =>
    (localStorage.getItem('kelvex_temp_unit') as TempUnit) || 'F'
  )

  // Notification channel management
  const { data: channelsData, isLoading: channelsLoading } = useNotificationChannels()
  const { data: logsData } = useNotificationLogs(20)
  const createChannel = useCreateNotificationChannel()
  const updateChannel = useUpdateNotificationChannel()
  const deleteChannel = useDeleteNotificationChannel()
  const testChannel = useTestNotificationChannel()
  const [showAddChannel, setShowAddChannel] = useState(false)
  const [newChannel, setNewChannel] = useState<NotificationChannelCreate>({
    name: '', channel_type: 'email', config: {}, enabled: true,
  })
  const [showLogs, setShowLogs] = useState(false)

  // Team management moved to /team

  // Export state
  const [exporting, setExporting] = useState(false)
  const [exportDone, setExportDone] = useState(false)

  // Delete confirmation
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleteText, setDeleteText] = useState('')

  useEffect(() => {
    if (user) setFullName(user.full_name)
  }, [user])

  // ── Handlers ─────────────────────────────────

  const handleSaveProfile = async () => {
    if (!fullName.trim()) return
    setProfileSaving(true)
    try {
      await api.updateProfile({ full_name: fullName.trim() })
      setProfileSaved(true)
      toast.success('Profile saved')
      setTimeout(() => setProfileSaved(false), 2000)
    } catch {
      toast.error('Failed to save profile')
    } finally {
      setProfileSaving(false)
    }
  }

  const handleTempUnitChange = (unit: TempUnit) => {
    setTempUnit(unit)
    localStorage.setItem('kelvex_temp_unit', unit)
  }

  const handleAddChannel = async () => {
    if (!newChannel.name.trim()) return
    try {
      await createChannel.mutateAsync(newChannel)
      toast.success('Notification channel added')
      setShowAddChannel(false)
      setNewChannel({ name: '', channel_type: 'email', config: {}, enabled: true })
    } catch {
      toast.error('Failed to add channel')
    }
  }

  // handleInvite moved to /team page

  const handleExport = async () => {
    setExporting(true)
    try {
      const rows = [['Facility', 'City', 'State', 'SqFt', 'Zone Types']]
      for (const f of facilities) {
        rows.push([f.name, f.city || '', f.state || '', String(f.sqft || ''), (f.zone_types || []).join('; ')])
      }
      const csv = rows.map(r => r.map(c => `"${c}"`).join(',')).join('\n')
      const blob = new Blob([csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `kelvex-export-${new Date().toISOString().split('T')[0]}.csv`
      a.click()
      URL.revokeObjectURL(url)
      setExportDone(true)
      setTimeout(() => setExportDone(false), 3000)
    } finally {
      setExporting(false)
    }
  }

  const sections = [
    { id: 'profile', label: 'Profile', icon: <User size={15} /> },
    { id: 'appearance', label: 'Appearance', icon: <Sun size={15} /> },
    { id: 'notifications', label: 'Notifications', icon: <Bell size={15} /> },
    { id: 'digest', label: 'Digest Preview', icon: <Mail size={15} /> },
    { id: 'detection', label: 'Detection', icon: <Activity size={15} /> },
    { id: 'team', label: 'Team', icon: <Users size={15} /> },
    { id: 'security', label: 'Security', icon: <Shield size={15} /> },
    { id: 'data', label: 'Data & Export', icon: <Database size={15} /> },
    { id: 'api', label: 'API Keys', icon: <Key size={15} /> },
  ]

  const channelTypeIcon = (t: string) =>
    t === 'email' ? <Mail size={14} /> : t === 'slack' ? <MessageSquare size={14} /> : t === 'sms' ? <Phone size={14} /> : <Globe size={14} />

  return (
    <div className="page-container">
      <PageHeader title="Settings" subtitle="Platform configuration" />
      <div className="content-area" style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 20, alignItems: 'start' }}>
        {/* Left nav */}
        <div className="card" style={{ position: 'sticky', top: 80 }}>
          <div className="card-body" style={{ padding: 6 }}>
            {sections.map(s => (
              <button
                key={s.id}
                onClick={() => setActiveSection(s.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '8px 10px',
                  border: 'none', borderRadius: 'var(--radius-sm)', background: activeSection === s.id ? 'var(--accent-muted)' : 'none',
                  color: activeSection === s.id ? 'var(--accent)' : 'var(--text-secondary)', fontSize: '12.5px',
                  fontWeight: activeSection === s.id ? 600 : 500, cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
                  transition: 'all 120ms ease',
                }}
              >
                {s.icon} {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Right content */}
        <div className="stack-lg">
          {activeSection === 'profile' && (
            <div className="card">
              <div className="card-header"><h3>Profile</h3></div>
              <div className="card-body" style={{ maxWidth: 480 }}>
                <div className="field" style={{ marginBottom: 14 }}>
                  <label>Full name</label>
                  <input
                    value={fullName}
                    onChange={e => setFullName(e.target.value)}
                    placeholder="Your name"
                  />
                </div>
                <div className="field" style={{ marginBottom: 14 }}>
                  <label>Email</label>
                  <input value={user?.email ?? ''} disabled style={{ opacity: 0.6 }} />
                </div>
                <div className="field" style={{ marginBottom: 14 }}>
                  <label>Organization ID</label>
                  <input value={user?.org_id ?? ''} disabled style={{ opacity: 0.6, fontFamily: 'monospace', fontSize: 12 }} />
                </div>
                <button
                  className="btn-primary"
                  style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}
                  onClick={handleSaveProfile}
                  disabled={profileSaving || fullName.trim() === user?.full_name}
                >
                  {profileSaving ? <><Loader2 size={14} className="spin" /> Saving...</> :
                   profileSaved ? <><Check size={14} /> Saved</> :
                   'Save Changes'}
                </button>
              </div>
            </div>
          )}

          {activeSection === 'appearance' && (
            <div className="card">
              <div className="card-header"><h3>Appearance</h3></div>
              <div className="card-body">
                <div className="setting-row">
                  <div>
                    <div className="cell-primary">Theme</div>
                    <div className="text-muted">Switch between light and dark mode</div>
                  </div>
                  <button className="btn-secondary" onClick={toggle}>
                    {theme === 'light' ? <><Moon size={14} /> Dark Mode</> : <><Sun size={14} /> Light Mode</>}
                  </button>
                </div>
                <div className="setting-row">
                  <div>
                    <div className="cell-primary">Temperature unit</div>
                    <div className="text-muted">Display temperatures in Fahrenheit or Celsius</div>
                  </div>
                  <select
                    value={tempUnit}
                    onChange={e => handleTempUnitChange(e.target.value as TempUnit)}
                    style={{
                      padding: '6px 10px', fontSize: '12.5px', border: '1px solid var(--input-border)',
                      borderRadius: 'var(--radius-md)', background: 'var(--input-bg)', color: 'var(--text-primary)',
                      fontFamily: 'inherit',
                    }}
                  >
                    <option value="F">Fahrenheit</option>
                    <option value="C">Celsius</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {activeSection === 'notifications' && (
            <div className="stack-lg">
              {/* Channels card */}
              <div className="card">
                <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h3>Notification Channels</h3>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn-secondary" style={{ fontSize: 12 }} onClick={() => setShowLogs(!showLogs)}>
                      <Clock size={13} /> {showLogs ? 'Hide Logs' : 'View Logs'}
                    </button>
                    <button className="btn-primary" style={{ fontSize: 12 }} onClick={() => setShowAddChannel(true)}>
                      <Plus size={13} /> Add Channel
                    </button>
                  </div>
                </div>
                <div className="card-body">
                  {channelsLoading && <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-tertiary)' }}><Loader2 size={18} className="spin" /></div>}
                  {!channelsLoading && (!channelsData?.channels?.length) && (
                    <div className="empty-state" style={{ padding: '32px 20px' }}>
                      <div className="empty-icon"><Bell size={20} /></div>
                      <h3>No channels configured</h3>
                      <p>Add an email, SMS, webhook, or Slack channel to receive notifications from automation rules and alerts.</p>
                    </div>
                  )}
                  {channelsData?.channels?.map((ch: NotificationChannelRecord) => (
                    <div key={ch.id} className="setting-row" style={{ gap: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
                        <span style={{ color: 'var(--text-tertiary)' }}>{channelTypeIcon(ch.channel_type)}</span>
                        <div style={{ minWidth: 0 }}>
                          <div className="cell-primary">{ch.name}</div>
                          <div className="text-muted" style={{ fontSize: 11 }}>
                            {ch.channel_type === 'email' && (ch.config?.recipients as string[] || []).join(', ')}
                            {ch.channel_type === 'webhook' && (ch.config?.url as string || 'No URL')}
                            {ch.channel_type === 'slack' && (ch.config?.channel as string || 'Slack')}
                            {ch.channel_type === 'sms' && (ch.config?.recipients as string[] || []).join(', ')}
                          </div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <label style={{ cursor: 'pointer' }}>
                          <input
                            type="checkbox"
                            checked={ch.enabled}
                            onChange={() => updateChannel.mutate(
                              { channelId: ch.id, data: { enabled: !ch.enabled } },
                              { onSuccess: () => toast.success(ch.enabled ? 'Channel disabled' : 'Channel enabled'), onError: () => toast.error('Failed to update channel') }
                            )}
                            style={{
                              width: 36, height: 20, appearance: 'none', WebkitAppearance: 'none',
                              background: ch.enabled ? 'var(--accent)' : 'var(--border-default)',
                              borderRadius: 10, cursor: 'pointer', transition: 'background 200ms', border: 'none',
                            }}
                          />
                        </label>
                        <button
                          className="btn-secondary"
                          style={{ padding: '4px 8px', fontSize: 11 }}
                          onClick={() => testChannel.mutate(ch.id, { onSuccess: () => toast.success('Test notification sent'), onError: () => toast.error('Test failed') })}
                          disabled={!ch.enabled}
                          title="Send test notification"
                        >
                          <Play size={12} /> Test
                        </button>
                        <button
                          className="btn-secondary"
                          style={{ padding: '4px 8px', fontSize: 11, color: 'var(--danger)' }}
                          onClick={() => { if (confirm(`Delete channel "${ch.name}"?`)) deleteChannel.mutate(ch.id, { onSuccess: () => toast.success('Channel deleted'), onError: () => toast.error('Failed to delete channel') }) }}
                          title="Delete channel"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Add Channel Modal */}
              {showAddChannel && (
                <div className="card" style={{ border: '1px solid var(--accent)', position: 'relative' }}>
                  <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3>New Notification Channel</h3>
                    <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)' }} onClick={() => setShowAddChannel(false)}>
                      <X size={16} />
                    </button>
                  </div>
                  <div className="card-body" style={{ maxWidth: 500 }}>
                    <div className="field" style={{ marginBottom: 12 }}>
                      <label>Channel name</label>
                      <input value={newChannel.name} onChange={e => setNewChannel(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Ops Team Email" />
                    </div>
                    <div className="field" style={{ marginBottom: 12 }}>
                      <label>Type</label>
                      <select
                        value={newChannel.channel_type}
                        onChange={e => setNewChannel(p => ({ ...p, channel_type: e.target.value, config: {} }))}
                        style={{ padding: '6px 10px', fontSize: '12.5px', border: '1px solid var(--input-border)', borderRadius: 'var(--radius-md)', background: 'var(--input-bg)', color: 'var(--text-primary)', fontFamily: 'inherit', width: '100%' }}
                      >
                        <option value="email">Email</option>
                        <option value="sms">SMS</option>
                        <option value="webhook">Webhook</option>
                        <option value="slack">Slack</option>
                      </select>
                    </div>
                    {newChannel.channel_type === 'email' && (
                      <div className="field" style={{ marginBottom: 12 }}>
                        <label>Recipients (comma-separated emails)</label>
                        <input
                          value={(newChannel.config?.recipients as string[] || []).join(', ')}
                          onChange={e => setNewChannel(p => ({ ...p, config: { ...p.config, recipients: e.target.value.split(',').map(s => s.trim()).filter(Boolean) } }))}
                          placeholder="ops@company.com, manager@company.com"
                        />
                      </div>
                    )}
                    {newChannel.channel_type === 'sms' && (
                      <>
                        <div className="field" style={{ marginBottom: 12 }}>
                          <label>Phone numbers (comma-separated, with country code)</label>
                          <input
                            value={(newChannel.config?.recipients as string[] || []).join(', ')}
                            onChange={e => setNewChannel(p => ({ ...p, config: { ...p.config, recipients: e.target.value.split(',').map(s => s.trim()).filter(Boolean) } }))}
                            placeholder="+15551234567, +15559876543"
                          />
                        </div>
                        <div style={{ padding: '8px 10px', borderRadius: 6, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 12 }}>
                          <strong>Requires Twilio.</strong> Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER in your environment.
                          Without Twilio configured, SMS alerts will be logged but not delivered.
                        </div>
                      </>
                    )}
                    {newChannel.channel_type === 'webhook' && (
                      <div className="field" style={{ marginBottom: 12 }}>
                        <label>Webhook URL</label>
                        <input
                          value={(newChannel.config?.url as string) || ''}
                          onChange={e => setNewChannel(p => ({ ...p, config: { ...p.config, url: e.target.value } }))}
                          placeholder="https://hooks.example.com/notify"
                        />
                      </div>
                    )}
                    {newChannel.channel_type === 'slack' && (
                      <>
                        <div className="field" style={{ marginBottom: 12 }}>
                          <label>Incoming Webhook URL</label>
                          <input
                            value={(newChannel.config?.webhook_url as string) || ''}
                            onChange={e => setNewChannel(p => ({ ...p, config: { ...p.config, webhook_url: e.target.value } }))}
                            placeholder="https://hooks.slack.com/services/..."
                          />
                        </div>
                        <div className="field" style={{ marginBottom: 12 }}>
                          <label>Channel (optional)</label>
                          <input
                            value={(newChannel.config?.channel as string) || ''}
                            onChange={e => setNewChannel(p => ({ ...p, config: { ...p.config, channel: e.target.value } }))}
                            placeholder="#alerts"
                          />
                        </div>
                      </>
                    )}
                    <button
                      className="btn-primary"
                      style={{ marginTop: 6 }}
                      onClick={handleAddChannel}
                      disabled={!newChannel.name.trim() || createChannel.isPending}
                    >
                      {createChannel.isPending ? <><Loader2 size={14} className="spin" /> Creating...</> : 'Create Channel'}
                    </button>
                  </div>
                </div>
              )}

              {/* Logs card */}
              {showLogs && (
                <div className="card">
                  <div className="card-header"><h3>Recent Delivery Logs</h3></div>
                  <div className="card-body" style={{ padding: 0 }}>
                    {(!logsData?.logs?.length) ? (
                      <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>No logs yet</div>
                    ) : (
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Time</th>
                            <th>Subject</th>
                            <th>Type</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {logsData.logs.map(log => (
                            <tr key={log.id}>
                              <td style={{ fontSize: 11, whiteSpace: 'nowrap' }}>{new Date(log.sent_at).toLocaleString()}</td>
                              <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{log.subject}</td>
                              <td>{log.channel_type}</td>
                              <td>
                                <span className={`badge ${log.status === 'sent' ? 'badge-success' : log.status === 'failed' ? 'badge-danger' : 'badge-neutral'}`}>
                                  {log.status}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeSection === 'detection' && (
            <div className="stack-lg">
              {detectionLoading ? (
                <div className="card"><div className="card-body" style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)' }}><Loader2 size={16} className="spin" /> Loading...</div></div>
              ) : (
                <>
                  {/* Auto Detection */}
                  <div className="card">
                    <div className="card-header">
                      <div>
                        <h3 style={{ margin: 0 }}>Automated Leak Detection</h3>
                        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
                          Kelvex analyzes suction pressure trends, superheat readings, and refrigerant add patterns to automatically detect leaks — no manual logging required to trigger an alert.
                        </p>
                      </div>
                      <button
                        onClick={() => toggleDetectionFeature('auto_detection')}
                        disabled={!canManageDetection || detectionSaving}
                        style={{
                          width: 44, height: 24, borderRadius: 12, border: 'none', cursor: canManageDetection ? 'pointer' : 'not-allowed',
                          background: detectionSettings.auto_detection ? 'var(--accent)' : 'var(--border)',
                          position: 'relative', transition: 'background 200ms', flexShrink: 0,
                        }}
                        title={canManageDetection ? undefined : 'Admin or Owner required'}
                      >
                        <span style={{
                          position: 'absolute', top: 3, left: detectionSettings.auto_detection ? 22 : 3,
                          width: 18, height: 18, borderRadius: '50%', background: '#fff',
                          transition: 'left 200ms', display: 'block', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                        }} />
                      </button>
                    </div>
                    <div className="card-body" style={{ paddingTop: 0 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                        {[
                          { label: 'Pressure trend analysis', desc: 'EWMA on suction pressure — flags sustained drops over 72-hour windows' },
                          { label: 'Superheat corroboration', desc: 'Cross-checks pressure drift against superheat rise for higher confidence' },
                          { label: 'Add pattern anomaly', desc: 'Poisson rate test on refrigerant add frequency vs. historical baseline' },
                        ].map(f => (
                          <div key={f.label} style={{ padding: '10px 12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--accent)' }}>
                            <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 3 }}>{f.label}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{f.desc}</div>
                          </div>
                        ))}
                      </div>
                      {!canManageDetection && (
                        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 12 }}>Admin or Owner role required to change this setting.</p>
                      )}
                    </div>
                  </div>

                  {/* Forecasting */}
                  <div className="card">
                    <div className="card-header">
                      <div>
                        <h3 style={{ margin: 0 }}>Consumption Forecasting</h3>
                        <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
                          Projects refrigerant consumption 90 days forward per circuit. Shows days to AIM Act warning and threshold, and flags circuits trending toward exceedance before it happens.
                        </p>
                      </div>
                      <button
                        onClick={() => toggleDetectionFeature('forecasting')}
                        disabled={!canManageDetection || detectionSaving}
                        style={{
                          width: 44, height: 24, borderRadius: 12, border: 'none', cursor: canManageDetection ? 'pointer' : 'not-allowed',
                          background: detectionSettings.forecasting ? 'var(--accent)' : 'var(--border)',
                          position: 'relative', transition: 'background 200ms', flexShrink: 0,
                        }}
                        title={canManageDetection ? undefined : 'Admin or Owner required'}
                      >
                        <span style={{
                          position: 'absolute', top: 3, left: detectionSettings.forecasting ? 22 : 3,
                          width: 18, height: 18, borderRadius: '50%', background: '#fff',
                          transition: 'left 200ms', display: 'block', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
                        }} />
                      </button>
                    </div>
                    <div className="card-body" style={{ paddingTop: 0 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                        {[
                          { label: 'Linear regression', desc: 'Used for circuits with fewer than 6 months of add history — honest about uncertainty' },
                          { label: 'Exponential smoothing', desc: 'Holt-Winters model for circuits with 6+ months of data — adapts to seasonal patterns' },
                          { label: 'Confidence intervals', desc: 'Bootstrap CI for sparse data; statistical PI for richer history — shows low/high range' },
                        ].map(f => (
                          <div key={f.label} style={{ padding: '10px 12px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--success)' }}>
                            <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 3 }}>{f.label}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{f.desc}</div>
                          </div>
                        ))}
                      </div>
                      <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 12 }}>
                        Forecasts run daily and appear in the AIM Act tab on the Leak Tracking page. Circuits need at least 3 refrigerant adds before forecasting starts.
                      </p>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {activeSection === 'team' && (
            <div className="card">
              <div className="card-body" style={{ textAlign: 'center', padding: 40 }}>
                <p style={{ color: 'var(--text-secondary)', marginBottom: 16 }}>
                  Team management has moved to its own page with role-based access control and facility assignments.
                </p>
                <a href="/team" className="btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, textDecoration: 'none' }}>
                  Go to Team Management &rarr;
                </a>
              </div>
            </div>
          )}

          {activeSection === 'digest' && (
            <DigestPreviewSection />
          )}

          {activeSection === 'security' && (
            <SecuritySection onSignOut={logout} />
          )}

          {activeSection === 'data' && (
            <div className="card">
              <div className="card-header"><h3>Data & Export</h3></div>
              <div className="card-body">
                <div className="setting-row">
                  <div>
                    <div className="cell-primary">Export facility data</div>
                    <div className="text-muted">Download facility list as CSV ({facilities.length} facilities)</div>
                  </div>
                  <button
                    className="btn-secondary"
                    onClick={handleExport}
                    disabled={exporting || facilities.length === 0}
                    style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                  >
                    {exporting ? <><Loader2 size={14} className="spin" /> Exporting...</> :
                     exportDone ? <><Check size={14} /> Downloaded</> :
                     <><Download size={14} /> Export</>}
                  </button>
                </div>
                <div className="setting-row" style={{ borderBottom: 'none' }}>
                  <div>
                    <div className="cell-primary">Data retention</div>
                    <div className="text-muted">How long telemetry and event data is stored</div>
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>90 days</span>
                </div>
              </div>
            </div>
          )}

          {activeSection === 'api' && (
            <div className="card">
              <div className="card-header"><h3>API Keys</h3></div>
              <div className="card-body">
                <div className="empty-state" style={{ padding: '32px 20px' }}>
                  <div className="empty-icon"><Key size={20} /></div>
                  <h3>API keys coming soon</h3>
                  <p>API keys will allow external systems to interact with Kelvex programmatically. This feature is under development.</p>
                </div>
              </div>
            </div>
          )}

          {/* Danger zone */}
          <div className="card" style={{ borderColor: 'var(--danger-border)' }}>
            <div className="card-header" style={{ borderBottomColor: 'var(--danger-border)' }}>
              <h3 style={{ color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: 6 }}>
                <AlertTriangle size={14} /> Danger Zone
              </h3>
            </div>
            <div className="card-body">
              <div className="setting-row" style={{ borderBottom: 'none' }}>
                <div>
                  <div className="cell-primary">Delete account</div>
                  <div className="text-muted">Permanently delete your account and all associated data</div>
                </div>
                {!showDeleteConfirm ? (
                  <button
                    className="btn-secondary"
                    style={{ color: 'var(--danger)', borderColor: 'var(--danger-border)' }}
                    onClick={() => setShowDeleteConfirm(true)}
                  >
                    Delete Account
                  </button>
                ) : (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input
                      placeholder='Type "DELETE" to confirm'
                      value={deleteText}
                      onChange={e => setDeleteText(e.target.value)}
                      style={{ width: 180, fontSize: 12 }}
                    />
                    <button
                      className="btn-secondary"
                      style={{ color: 'var(--danger)', borderColor: 'var(--danger-border)', fontSize: 12 }}
                      disabled={deleteText !== 'DELETE'}
                      onClick={() => {
                        toast('Account deletion requires contacting support.', { icon: '\u26a0\ufe0f' })
                        setShowDeleteConfirm(false)
                        setDeleteText('')
                      }}
                    >
                      Confirm
                    </button>
                    <button
                      className="btn-secondary"
                      style={{ fontSize: 12 }}
                      onClick={() => { setShowDeleteConfirm(false); setDeleteText('') }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function SecuritySection({ onSignOut }: { onSignOut: () => void }) {
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [pwLoading, setPwLoading] = useState(false)
  const [pwError, setPwError] = useState<string | null>(null)
  const [pwDone, setPwDone] = useState(false)

  const handleChangePw = async (e: React.FormEvent) => {
    e.preventDefault()
    setPwError(null)
    if (newPw.length < 8) return setPwError('New password must be at least 8 characters.')
    if (newPw !== confirmPw) return setPwError('Passwords do not match.')
    setPwLoading(true)
    try {
      await api.changePassword(currentPw, newPw)
      setPwDone(true)
      setCurrentPw(''); setNewPw(''); setConfirmPw('')
      toast.success('Password changed')
    } catch (e: unknown) {
      setPwError(e instanceof Error ? e.message : 'Failed to change password.')
    } finally {
      setPwLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div className="card">
        <div className="card-header"><h3>Change Password</h3></div>
        <div className="card-body" style={{ maxWidth: 420 }}>
          {pwDone ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--success)', fontSize: 14 }}>
              <Check size={16} /> Password updated successfully.
            </div>
          ) : (
            <form onSubmit={handleChangePw} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className="field">
                <label>Current password</label>
                <input type="password" value={currentPw} onChange={e => setCurrentPw(e.target.value)} required autoComplete="current-password" />
              </div>
              <div className="field">
                <label>New password</label>
                <input type="password" value={newPw} onChange={e => setNewPw(e.target.value)} required autoComplete="new-password" placeholder="At least 8 characters" />
              </div>
              <div className="field">
                <label>Confirm new password</label>
                <input
                  type="password"
                  value={confirmPw}
                  onChange={e => setConfirmPw(e.target.value)}
                  required
                  autoComplete="new-password"
                  style={{ borderColor: confirmPw && confirmPw !== newPw ? 'rgba(248,113,113,.4)' : undefined }}
                />
              </div>
              {pwError && (
                <div style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.3)', borderRadius: 6, padding: '8px 12px', fontSize: 13, color: '#f87171' }}>
                  {pwError}
                </div>
              )}
              <button type="submit" className="btn-primary" disabled={pwLoading} style={{ alignSelf: 'flex-start' }}>
                {pwLoading ? <><Loader2 size={14} className="spin" /> Updating…</> : 'Update Password'}
              </button>
            </form>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3>Session</h3></div>
        <div className="card-body">
          <div className="setting-row" style={{ borderBottom: 'none' }}>
            <div>
              <div className="cell-primary">Sign out</div>
              <div className="text-muted">Sign out of your current session</div>
            </div>
            <button className="btn-secondary" onClick={onSignOut}>Sign Out</button>
          </div>
        </div>
      </div>
    </div>
  )
}

import { useCallback } from 'react'
import type { DigestPreview } from '../lib/api'

function DigestPreviewSection() {
  const [preview, setPreview] = useState<DigestPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [hours, setHours] = useState(24)

  const sevColors: Record<string, string> = {
    critical: 'var(--danger)', high: '#e67700', medium: 'var(--warning)',
    low: 'var(--info)', info: 'var(--text-secondary)',
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getDigestPreview(hours)
      setPreview(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [hours])

  useEffect(() => { load() }, [load])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="card">
        <div className="card-header"><h3>Email Digest Preview</h3></div>
        <div className="card-body">
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            {[12, 24, 48, 168].map(h => (
              <button
                key={h}
                onClick={() => setHours(h)}
                className={hours === h ? 'btn-primary' : 'btn-secondary'}
                style={{ padding: '5px 12px', fontSize: 12 }}
              >
                {h < 48 ? `${h}h` : `${h / 24}d`}
              </button>
            ))}
          </div>

          {loading ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Loader2 size={22} className="spin" /></div>
          ) : preview ? (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                <div style={{ padding: 16, background: 'var(--bg-secondary)', borderRadius: 8 }}>
                  <h4 style={{ margin: '0 0 10px', fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <AlertTriangle size={14} /> Alerts
                  </h4>
                  <div style={{ fontSize: 28, fontWeight: 700, color: preview.alerts.new_total > 0 ? 'var(--danger)' : 'var(--success)' }}>
                    {preview.alerts.new_total}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>new active alerts</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {Object.entries(preview.alerts.active_by_severity).map(([sev, count]) => (
                      count > 0 && (
                        <div key={sev} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ width: 8, height: 8, borderRadius: '50%', background: sevColors[sev] || '#888' }} />
                            {sev}
                          </span>
                          <span style={{ fontWeight: 600 }}>{count}</span>
                        </div>
                      )
                    ))}
                  </div>
                </div>
                <div style={{ padding: 16, background: 'var(--bg-secondary)', borderRadius: 8 }}>
                  <h4 style={{ margin: '0 0 10px', fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Activity size={14} /> Control Actions
                  </h4>
                  <div style={{ fontSize: 28, fontWeight: 700 }}>{preview.commands.total}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>commands issued</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Completed</span>
                      <span style={{ fontWeight: 600, color: 'var(--success)' }}>{preview.commands.completed}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Failed</span>
                      <span style={{ fontWeight: 600, color: 'var(--danger)' }}>{preview.commands.failed}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Automation fires</span>
                      <span style={{ fontWeight: 600 }}>{preview.automation.rule_fires_today}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                Covering {preview.facilities_count} facilit{preview.facilities_count === 1 ? 'y' : 'ies'}:{' '}
                {preview.facilities.map(f => f.name).join(', ')}
              </div>
            </div>
          ) : null}

          <div style={{ marginTop: 16, padding: '10px 12px', background: 'var(--bg-secondary)', borderRadius: 8, fontSize: 12, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <Shield size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            Sent daily at 7:00 UTC to all enabled notification channels. Configure channels in Notifications above.
          </div>
        </div>
      </div>
    </div>
  )
}
