import { useState, useEffect, useCallback } from 'react'
import {
  Monitor, Lock, Plus, X, ShieldAlert, Clock, CheckCircle,
} from 'lucide-react'
import toast from 'react-hot-toast'
import PageHeader from '../components/ui/PageHeader'
import LoadingState from '../components/ui/LoadingState'
import { api } from '../lib/api'
import { useSiteContext } from '../contexts/SiteContext'
import { useAuth } from '../contexts/AuthContext'
import type { TunnelSession, Facility } from '../lib/api'

function formatDt(iso: string) {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: '2-digit',
    hour: 'numeric', minute: '2-digit',
  })
}

function sessionDuration(started: string, ended: string | null): string {
  const end = ended ? new Date(ended) : new Date()
  const ms = end.getTime() - new Date(started).getTime()
  const mins = Math.floor(ms / 60000)
  if (mins < 60) return `${mins}m`
  return `${Math.floor(mins / 60)}h ${mins % 60}m`
}

// ── Start Session Modal ───────────────────────────────────────────────────────
interface StartSessionModalProps {
  facilities: Facility[]
  defaultFacilityId?: string
  onClose: () => void
  onSuccess: () => void
}

function StartSessionModal({ facilities, defaultFacilityId, onClose, onSuccess }: StartSessionModalProps) {
  const [starting, setStarting] = useState(false)
  const [form, setForm] = useState({
    facility_id: defaultFacilityId ?? (facilities[0]?.id ?? ''),
    target_device: '',
    notes: '',
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.facility_id) { toast.error('Select a site'); return }
    setStarting(true)
    try {
      await api.startTunnelSession({
        facility_id: form.facility_id,
        target_device: form.target_device || undefined,
        notes: form.notes || undefined,
      })
      toast.success('Tunnel session started — connection details will appear in the agent')
      onSuccess()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to start session')
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 460 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Monitor size={16} /> Start Controller Session
          </h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div style={{
            padding: '10px 12px', background: 'var(--warning-bg, color-mix(in srgb, var(--warning) 12%, transparent))',
            border: '1px solid var(--warning-border, color-mix(in srgb, var(--warning) 30%, transparent))',
            borderRadius: 6, fontSize: 12, color: 'var(--text-secondary)', marginBottom: 16,
          }}>
            Sessions are logged with your name, IP address, and timestamp. All activity is audited.
          </div>
          <div className="field">
            <label>Site *</label>
            <select value={form.facility_id} onChange={e => setForm({ ...form, facility_id: e.target.value })} required>
              <option value="">Select a site...</option>
              {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Target Device <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>(optional)</span></label>
            <input value={form.target_device} onChange={e => setForm({ ...form, target_device: e.target.value })}
              placeholder="e.g. Rack Controller A, Zone 3 Panel" />
          </div>
          <div className="field">
            <label>Reason / Notes</label>
            <textarea rows={2} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
              placeholder="Optional — describe the purpose of this session" />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={starting}>
              {starting ? 'Starting...' : <><Monitor size={14} /> Start Session</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function ControllerAccessPage() {
  const { hasPermission } = useAuth()
  const { site, facilities } = useSiteContext()
  const [sessions, setSessions] = useState<TunnelSession[]>([])
  const [loading, setLoading] = useState(true)
  const [showStart, setShowStart] = useState(false)
  const [endingId, setEndingId] = useState<string | null>(null)

  const canAccess = hasPermission('tunnel:access')
  const facilityId = site?.id

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = facilityId ? { facility_id: facilityId, limit: 100 } : { limit: 100 }
      const res = await api.listTunnelSessions(params)
      setSessions(res.sessions)
    } catch {
      setSessions([])
    } finally {
      setLoading(false)
    }
  }, [facilityId])

  useEffect(() => { load() }, [load])

  async function handleEndSession(sessionId: string) {
    setEndingId(sessionId)
    try {
      await api.endTunnelSession(sessionId, { end_reason: 'user_ended' })
      toast.success('Session ended')
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to end session')
    } finally {
      setEndingId(null)
    }
  }

  const activeSessions = sessions.filter(s => !s.ended_at)
  const pastSessions = sessions.filter(s => s.ended_at)

  if (!canAccess) {
    return (
      <div className="page-container">
        <PageHeader title="Controller Access" subtitle="Secure tunnel to site controllers" />
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12,
          padding: '60px 24px', textAlign: 'center',
        }}>
          <Lock size={40} style={{ color: 'var(--text-muted)' }} />
          <h3 style={{ margin: 0 }}>Access Restricted</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: 14, maxWidth: 340 }}>
            Controller tunnel access requires the <strong>tunnel:access</strong> permission.
            Contact your account admin to request access.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-container">
      <PageHeader
        title="Controller Access"
        subtitle="Reverse tunnel to site controllers — all sessions are logged and audited"
      >
        <button className="btn-primary" onClick={() => setShowStart(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Plus size={14} /> Start Session
        </button>
      </PageHeader>

      {/* Active sessions banner */}
      {activeSessions.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
          background: 'color-mix(in srgb, var(--warning) 12%, transparent)',
          border: '1px solid color-mix(in srgb, var(--warning) 30%, transparent)',
          borderRadius: 8, marginBottom: 16, fontSize: 13,
        }}>
          <ShieldAlert size={15} style={{ color: 'var(--warning)', flexShrink: 0 }} />
          <span style={{ fontWeight: 600, color: 'var(--warning)' }}>
            {activeSessions.length} active tunnel session{activeSessions.length > 1 ? 's' : ''}
          </span>
          <span style={{ color: 'var(--text-secondary)' }}>
            — {activeSessions.map(s => s.user_email).join(', ')}
          </span>
        </div>
      )}

      {/* Active sessions table */}
      {activeSessions.length > 0 && (
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Monitor size={14} /> Active Sessions
            </h3>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Site</th>
                  <th>Target</th>
                  <th>Started</th>
                  <th>Duration</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {activeSessions.map(s => {
                  const fac = facilities.find(f => f.id === s.facility_id)
                  return (
                    <tr key={s.id}>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>{s.user_email}</div>
                        {s.notes && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.notes}</div>}
                      </td>
                      <td style={{ fontSize: 13 }}>{fac?.name ?? s.facility_id}</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.target_device ?? '—'}</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                        {formatDt(s.started_at)}
                      </td>
                      <td style={{ fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
                        <span style={{ color: 'var(--warning)', fontWeight: 600 }}>
                          {sessionDuration(s.started_at, null)}
                        </span>
                      </td>
                      <td>
                        <button className="btn-secondary" onClick={() => handleEndSession(s.id)}
                          disabled={endingId === s.id}
                          style={{ fontSize: 11, padding: '4px 10px', color: 'var(--danger)', borderColor: 'var(--danger)' }}>
                          {endingId === s.id ? 'Ending...' : 'End Session'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Session history */}
      <div className="card">
        <div className="card-header">
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Clock size={14} /> Session History
          </h3>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {loading ? (
            <LoadingState label="Loading sessions..." />
          ) : pastSessions.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
              <CheckCircle size={24} style={{ display: 'block', margin: '0 auto 8px', opacity: 0.4 }} />
              No past sessions. Start a session to connect to a site controller.
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Site</th>
                  <th>Target</th>
                  <th>Started</th>
                  <th>Duration</th>
                  <th>End Reason</th>
                </tr>
              </thead>
              <tbody>
                {pastSessions.map(s => {
                  const fac = facilities.find(f => f.id === s.facility_id)
                  return (
                    <tr key={s.id}>
                      <td>
                        <div style={{ fontSize: 13 }}>{s.user_email}</div>
                        {s.notes && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{s.notes}</div>}
                      </td>
                      <td style={{ fontSize: 13 }}>{fac?.name ?? s.facility_id}</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.target_device ?? '—'}</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                        {formatDt(s.started_at)}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                        {sessionDuration(s.started_at, s.ended_at)}
                      </td>
                      <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        {s.end_reason?.replace(/_/g, ' ') ?? '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showStart && (
        <StartSessionModal
          facilities={facilities}
          defaultFacilityId={facilityId}
          onClose={() => setShowStart(false)}
          onSuccess={load}
        />
      )}
    </div>
  )
}
