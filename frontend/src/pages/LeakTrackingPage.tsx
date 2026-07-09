import { useState, useEffect, useCallback } from 'react'
import toast from 'react-hot-toast'
import {
  Droplets, AlertTriangle, Wrench, ShieldCheck, Plus, X,
  ChevronRight, Filter, TrendingUp, CheckCircle, Activity,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { useSiteContext } from '../contexts/SiteContext'
import { api } from '../lib/api'
import type {
  LeakEvent, RefrigerantAdd, RepairRecord,
  RefrigerantCircuit, RefrigerantDashboard,
  AIMActSummary, CircuitForecast,
} from '../lib/api'

type Tab = 'overview' | 'aim-act' | 'leak-events' | 'refrigerant-log' | 'repairs' | 'circuits'

const REFRIGERANT_TYPES = ['R-404A', 'R-448A', 'R-410A', 'R-22', 'R-134a', 'Other']
const DETECTION_METHODS = ['electronic_detector', 'uv_dye', 'soap_bubble', 'visual_inspection', 'pressure_test', 'sensor_alert', 'other']
const CONFIDENCE_LEVELS = ['confirmed', 'likely', 'suspected']
const VERIFICATION_METHODS = ['electronic_leak_detector', 'pressure_test', 'uv_dye', 'soap_bubble', 'other']
const AUTO_DETECTION_METHODS = new Set(['pressure_trend', 'refrigerant_add_pattern', 'multi_signal'])

function statusBadge(status: string) {
  const map: Record<string, string> = {
    open: 'badge-danger',
    investigating: 'badge-warning',
    repaired: 'badge-success',
    closed: 'badge-neutral',
    false_positive: 'badge-neutral',
  }
  return map[status] ?? 'badge-neutral'
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function daysOpen(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
}

function leakCostEstimate(event: LeakEvent): number | null {
  if (event.estimated_loss_lbs == null) return null
  return Math.round(event.estimated_loss_lbs * 15)
}

const STATUS_PRIORITY: Record<string, number> = {
  open: 0, investigating: 1, repaired: 2, closed: 3, false_positive: 4,
}

function TabBar({ tab, setTab, counts }: { tab: Tab; setTab: (t: Tab) => void; counts: Partial<Record<Tab, number>> }) {
  const tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'aim-act', label: 'AIM Act' },
    { id: 'leak-events', label: 'Leak Events' },
    { id: 'refrigerant-log', label: 'Refrigerant Log' },
    { id: 'repairs', label: 'Repairs' },
    { id: 'circuits', label: 'Circuits' },
  ]
  return (
    <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)', marginBottom: 24 }}>
      {tabs.map(t => (
        <button
          key={t.id}
          onClick={() => setTab(t.id)}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: tab === t.id ? 600 : 400,
            color: tab === t.id ? 'var(--accent)' : 'var(--text-secondary)',
            borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
            background: 'none', border: 'none', cursor: 'pointer', marginBottom: -1,
            display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          {t.label}
          {counts[t.id] != null && counts[t.id]! > 0 && (
            <span style={{
              fontSize: 11, fontWeight: 600, padding: '1px 6px', borderRadius: 10,
              background: tab === t.id ? 'var(--accent-muted)' : 'var(--bg-tertiary)',
              color: tab === t.id ? 'var(--accent)' : 'var(--text-muted)',
            }}>
              {counts[t.id]}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

// ── Monthly bar chart data helper ──────────────────────────────────────────
function buildMonthlyAddChart(adds: RefrigerantAdd[]) {
  const now = new Date()
  const months: { key: string; label: string; lbs: number }[] = []
  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const label = d.toLocaleString('default', { month: 'short', year: '2-digit' })
    months.push({ key, label, lbs: 0 })
  }
  for (const add of adds) {
    const d = new Date(add.added_at)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const bucket = months.find(m => m.key === key)
    if (bucket) bucket.lbs += add.amount_lbs
  }
  return months
}

// ─────────────────────────────────────────────────────────────────────────────
// Log Leak Event Modal
// ─────────────────────────────────────────────────────────────────────────────
interface LogLeakEventModalProps {
  facilityId: string
  onClose: () => void
  onSuccess: () => void
}

function LogLeakEventModal({ facilityId, onClose, onSuccess }: LogLeakEventModalProps) {
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    rack_name: '',
    zone_name: '',
    detection_method: 'electronic_detector',
    confidence: 'suspected',
    detected_at: new Date().toISOString().slice(0, 16),
    estimated_loss_lbs: '',
    notes: '',
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.rack_name) { toast.error('Rack name is required'); return }
    setSaving(true)
    try {
      await api.createLeakEvent({
        facility_id: facilityId,
        rack_name: form.rack_name,
        zone_name: form.zone_name || undefined,
        detection_method: form.detection_method,
        confidence: form.confidence,
        detected_at: new Date(form.detected_at).toISOString(),
        estimated_loss_lbs: form.estimated_loss_lbs ? parseFloat(form.estimated_loss_lbs) : undefined,
        notes: form.notes || undefined,
      })
      toast.success('Leak event logged')
      onSuccess()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to log leak event')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Log Leak Event</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Rack Name *</label>
              <input value={form.rack_name} onChange={e => setForm({ ...form, rack_name: e.target.value })}
                placeholder="e.g. Rack A-12" required autoFocus />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Zone / Area</label>
              <input value={form.zone_name} onChange={e => setForm({ ...form, zone_name: e.target.value })}
                placeholder="Optional" />
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Detection Method</label>
              <select value={form.detection_method} onChange={e => setForm({ ...form, detection_method: e.target.value })}>
                {DETECTION_METHODS.map(m => (
                  <option key={m} value={m}>{m.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                ))}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Confidence</label>
              <select value={form.confidence} onChange={e => setForm({ ...form, confidence: e.target.value })}>
                {CONFIDENCE_LEVELS.map(c => (
                  <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Detected At</label>
              <input type="datetime-local" value={form.detected_at}
                onChange={e => setForm({ ...form, detected_at: e.target.value })} />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Est. Loss (lbs)</label>
              <input type="number" step="0.1" min="0" value={form.estimated_loss_lbs}
                onChange={e => setForm({ ...form, estimated_loss_lbs: e.target.value })}
                placeholder="Optional" />
            </div>
          </div>
          <div className="field">
            <label>Notes</label>
            <textarea rows={3} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
              placeholder="Additional context..." />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : <><Plus size={14} /> Log Event</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Log Refrigerant Add Modal
// ─────────────────────────────────────────────────────────────────────────────
interface LogAddModalProps {
  facilityId: string
  onClose: () => void
  onSuccess: () => void
}

function LogAddModal({ facilityId, onClose, onSuccess }: LogAddModalProps) {
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    rack_name: '',
    refrigerant_type: 'R-404A',
    amount_lbs: '',
    cost_per_lb: '',
    technician_name: '',
    technician_epa_cert: '',
    added_at: new Date().toISOString().slice(0, 16),
    notes: '',
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.rack_name || !form.amount_lbs || !form.technician_name) {
      toast.error('Rack, amount, and technician are required'); return
    }
    setSaving(true)
    try {
      await api.createRefrigerantAdd({
        facility_id: facilityId,
        rack_name: form.rack_name,
        refrigerant_type: form.refrigerant_type,
        amount_lbs: parseFloat(form.amount_lbs),
        cost_per_lb: form.cost_per_lb ? parseFloat(form.cost_per_lb) : undefined,
        technician_name: form.technician_name,
        technician_epa_cert: form.technician_epa_cert || undefined,
        added_at: new Date(form.added_at).toISOString(),
        notes: form.notes || undefined,
      })
      toast.success('Refrigerant add logged')
      onSuccess()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to log refrigerant add')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Log Refrigerant Add</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Rack Name *</label>
              <input value={form.rack_name} onChange={e => setForm({ ...form, rack_name: e.target.value })}
                placeholder="e.g. Rack B-04" required autoFocus />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Refrigerant Type</label>
              <select value={form.refrigerant_type} onChange={e => setForm({ ...form, refrigerant_type: e.target.value })}>
                {REFRIGERANT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Amount (lbs) *</label>
              <input type="number" step="0.1" min="0" value={form.amount_lbs}
                onChange={e => setForm({ ...form, amount_lbs: e.target.value })} required />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Cost per lb ($)</label>
              <input type="number" step="0.01" min="0" value={form.cost_per_lb}
                onChange={e => setForm({ ...form, cost_per_lb: e.target.value })}
                placeholder="Optional" />
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Technician *</label>
              <input value={form.technician_name} onChange={e => setForm({ ...form, technician_name: e.target.value })}
                placeholder="Full name" required />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>EPA Cert # <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>(optional)</span></label>
              <input value={form.technician_epa_cert} onChange={e => setForm({ ...form, technician_epa_cert: e.target.value })}
                placeholder="e.g. EPA-608-12345" />
            </div>
          </div>
          <div className="field">
            <label>Date Added</label>
            <input type="datetime-local" value={form.added_at}
              onChange={e => setForm({ ...form, added_at: e.target.value })} />
          </div>
          <div className="field">
            <label>Notes</label>
            <textarea rows={2} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
              placeholder="Optional notes..." />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : <><Plus size={14} /> Log Add</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Log Repair Modal
// ─────────────────────────────────────────────────────────────────────────────
interface LogRepairModalProps {
  facilityId: string
  onClose: () => void
  onSuccess: () => void
}

function LogRepairModal({ facilityId, onClose, onSuccess }: LogRepairModalProps) {
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    rack_name: '',
    description: '',
    technician_name: '',
    technician_company: '',
    repaired_at: new Date().toISOString().slice(0, 16),
    parts_replaced: '',
    verified_leak_free: false,
    verification_method: 'electronic_leak_detector',
    refrigerant_recovered_lbs: '',
    notes: '',
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.rack_name || !form.description || !form.technician_name) {
      toast.error('Rack, description, and technician are required'); return
    }
    setSaving(true)
    try {
      await api.createRepair({
        facility_id: facilityId,
        rack_name: form.rack_name,
        description: form.description,
        technician_name: form.technician_name,
        technician_company: form.technician_company || undefined,
        repaired_at: new Date(form.repaired_at).toISOString(),
        parts_replaced: form.parts_replaced || undefined,
        verified_leak_free: form.verified_leak_free,
        verification_method: form.verified_leak_free ? form.verification_method : undefined,
        refrigerant_recovered_lbs: form.refrigerant_recovered_lbs ? parseFloat(form.refrigerant_recovered_lbs) : undefined,
        notes: form.notes || undefined,
      })
      toast.success('Repair logged')
      onSuccess()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to log repair')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 540 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Log Repair</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Rack Name *</label>
              <input value={form.rack_name} onChange={e => setForm({ ...form, rack_name: e.target.value })}
                placeholder="e.g. Rack A-12" required autoFocus />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Technician *</label>
              <input value={form.technician_name} onChange={e => setForm({ ...form, technician_name: e.target.value })}
                placeholder="Full name" required />
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Company</label>
              <input value={form.technician_company} onChange={e => setForm({ ...form, technician_company: e.target.value })}
                placeholder="Optional" />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Repaired At</label>
              <input type="datetime-local" value={form.repaired_at}
                onChange={e => setForm({ ...form, repaired_at: e.target.value })} />
            </div>
          </div>
          <div className="field">
            <label>Description *</label>
            <textarea rows={2} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="What was repaired..." required />
          </div>
          <div className="field">
            <label>Parts Replaced</label>
            <input value={form.parts_replaced} onChange={e => setForm({ ...form, parts_replaced: e.target.value })}
              placeholder="e.g. Schrader valve, evaporator coil" />
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Refrigerant Recovered (lbs)</label>
              <input type="number" step="0.1" min="0" value={form.refrigerant_recovered_lbs}
                onChange={e => setForm({ ...form, refrigerant_recovered_lbs: e.target.value })}
                placeholder="Optional" />
            </div>
            <div className="field" style={{ flex: 1, justifyContent: 'flex-end' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginTop: 24 }}>
                <input type="checkbox" checked={form.verified_leak_free}
                  onChange={e => setForm({ ...form, verified_leak_free: e.target.checked })} />
                Verified Leak-Free
              </label>
            </div>
          </div>
          {form.verified_leak_free && (
            <div className="field">
              <label>Verification Method</label>
              <select value={form.verification_method} onChange={e => setForm({ ...form, verification_method: e.target.value })}>
                {VERIFICATION_METHODS.map(m => (
                  <option key={m} value={m}>{m.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                ))}
              </select>
            </div>
          )}
          <div className="field">
            <label>Notes</label>
            <textarea rows={2} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
              placeholder="Additional notes..." />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : <><Plus size={14} /> Log Repair</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Add Circuit Modal
// ─────────────────────────────────────────────────────────────────────────────
interface AddCircuitModalProps {
  facilityId: string
  onClose: () => void
  onSuccess: () => void
}

function AddCircuitModal({ facilityId, onClose, onSuccess }: AddCircuitModalProps) {
  const [saving, setSaving] = useState(false)
  const [racks, setRacks] = useState<import('../lib/api').RackTelemetry[]>([])
  const [form, setForm] = useState({
    name: '',
    refrigerant_type: 'R-404A',
    full_charge_lbs: '',
    rack_id: '',
  })

  useEffect(() => {
    api.listRacks(facilityId).then(r => setRacks(r.racks)).catch(() => {})
  }, [facilityId])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name) { toast.error('Circuit name is required'); return }
    setSaving(true)
    try {
      await api.createCircuit({
        facility_id: facilityId,
        name: form.name,
        refrigerant_type: form.refrigerant_type,
        full_charge_lbs: form.full_charge_lbs ? parseFloat(form.full_charge_lbs) : undefined,
        rack_id: form.rack_id || undefined,
      })
      toast.success('Circuit added')
      onSuccess()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to add circuit')
    } finally {
      setSaving(false)
    }
  }

  const selectedRack = racks.find(r => r.rack_id === form.rack_id)

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 480 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Refrigerant Circuit</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Circuit Name *</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Freezer Rack A" required autoFocus />
          </div>
          <div className="field">
            <label>Link to Compressor Rack <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>(optional — enables live pressure monitoring)</span></label>
            <select value={form.rack_id} onChange={e => setForm({ ...form, rack_id: e.target.value })}>
              <option value="">Not linked</option>
              {racks.map(r => (
                <option key={r.rack_id} value={r.rack_id}>{r.rack_name}{r.suction_group ? ` — ${r.suction_group}` : ''}</option>
              ))}
            </select>
            {selectedRack && (
              <div style={{ marginTop: 6, padding: '8px 10px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-sm)', fontSize: 12, color: 'var(--text-secondary)', display: 'flex', gap: 16 }}>
                <span>{selectedRack.active_compressors ?? ''} compressors running</span>
                <span>{selectedRack.avg_suction_psi != null ? `${selectedRack.avg_suction_psi} psi suction` : 'No pressure data'}</span>
                {selectedRack.total_kw != null && <span>{selectedRack.total_kw.toFixed(1)} kW</span>}
              </div>
            )}
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Refrigerant Type</label>
              <select value={form.refrigerant_type} onChange={e => setForm({ ...form, refrigerant_type: e.target.value })}>
                {REFRIGERANT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Full Charge (lbs)</label>
              <input type="number" step="0.1" min="0" value={form.full_charge_lbs}
                onChange={e => setForm({ ...form, full_charge_lbs: e.target.value })}
                placeholder="e.g. 200" />
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : <><Plus size={14} /> Add Circuit</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Update Leak Event Status Modal
// ─────────────────────────────────────────────────────────────────────────────
interface UpdateStatusModalProps {
  event: LeakEvent
  onClose: () => void
  onSuccess: () => void
}

function UpdateStatusModal({ event, onClose, onSuccess }: UpdateStatusModalProps) {
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(event.status)
  const [notes, setNotes] = useState('')

  const STATUSES = ['open', 'investigating', 'repaired', 'closed', 'false_positive']

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.updateLeakEvent(event.id, { status, notes: notes || undefined })
      toast.success('Status updated')
      onSuccess()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update status')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 400 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Update Leak Event Status</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Rack</label>
            <div style={{ fontSize: 13, fontWeight: 600, padding: '6px 0' }}>{event.rack_name}</div>
          </div>
          <div className="field">
            <label>New Status</label>
            <select value={status} onChange={e => setStatus(e.target.value)}>
              {STATUSES.map(s => (
                <option key={s} value={s}>{s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Notes</label>
            <textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="Optional update notes..." />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Saving...' : 'Update Status'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────
export default function LeakTrackingPage() {
  const { site } = useSiteContext()
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)

  const [dashboard, setDashboard] = useState<RefrigerantDashboard | null>(null)
  const [leakEvents, setLeakEvents] = useState<LeakEvent[]>([])
  const [adds, setAdds] = useState<RefrigerantAdd[]>([])
  const [repairs, setRepairs] = useState<RepairRecord[]>([])
  const [circuits, setCircuits] = useState<RefrigerantCircuit[]>([])
  // Filters
  const [leakStatusFilter, setLeakStatusFilter] = useState('')

  // AIM Act — lazy-loaded on first tab open
  const [aimActLoaded, setAimActLoaded] = useState(false)
  const [aimActLoading, setAimActLoading] = useState(false)
  const [aimActSummary, setAimActSummary] = useState<AIMActSummary | null>(null)
  const [forecasts, setForecasts] = useState<CircuitForecast[]>([])

  // Modals
  const [showLogLeak, setShowLogLeak] = useState(false)
  const [showLogAdd, setShowLogAdd] = useState(false)
  const [showLogRepair, setShowLogRepair] = useState(false)
  const [showAddCircuit, setShowAddCircuit] = useState(false)
  const [updateStatusEvent, setUpdateStatusEvent] = useState<LeakEvent | null>(null)

  const facilityId = site?.id

  const load = useCallback(async () => {
    setLoading(true)
    setAimActLoaded(false)
    try {
      const [dashRes, leakRes, addRes, repairRes, circuitRes] = await Promise.all([
        api.getRefrigerantDashboard(facilityId).catch(() => null),
        api.listLeakEvents(facilityId ? { facility_id: facilityId, limit: 200 } : { limit: 200 }).catch(() => ({ leak_events: [], total: 0 })),
        api.listRefrigerantAdds(facilityId ? { facility_id: facilityId, limit: 200 } : { limit: 200 }).catch(() => ({ adds: [], total: 0 })),
        api.listRepairs(facilityId ? { facility_id: facilityId, limit: 200 } : { limit: 200 }).catch(() => ({ repairs: [], total: 0 })),
        api.listCircuits(facilityId).catch(() => ({ circuits: [] })),
      ])
      setDashboard(dashRes)
      setLeakEvents(leakRes.leak_events)
      setAdds(addRes.adds)
      setRepairs(repairRes.repairs)
      setCircuits(circuitRes.circuits)
    } catch (err) {
      console.error('LeakTrackingPage load error:', err)
    } finally {
      setLoading(false)
    }
  }, [facilityId])

  const loadAimAct = useCallback(async () => {
    if (aimActLoaded) return
    setAimActLoading(true)
    try {
      const [summary, fcasts] = await Promise.all([
        api.getAIMActSummary(facilityId).catch(() => null),
        api.getDetectionForecasts(facilityId).catch(() => []),
      ])
      setAimActSummary(summary)
      setForecasts(Array.isArray(fcasts) ? fcasts : [])
      setAimActLoaded(true)
    } catch {
      // silent
    } finally {
      setAimActLoading(false)
    }
  }, [facilityId, aimActLoaded])

  const handleCreateWorkOrderFromLeak = useCallback(async (leakEventId: string) => {
    try {
      const task = await api.createWorkOrderFromLeakEvent(leakEventId)
      toast.success(`Work order created: ${task.title}`)
    } catch {
      toast.error('Failed to create work order')
    }
  }, [])

  const checkCallback = useCallback(async (repairId: string) => {
    try {
      const result = await api.detectCallback(repairId)
      if (result.callback_detected === null) {
        toast(result.reason ?? 'Cannot check yet', { icon: 'ℹ️' })
        return
      }
      // Update local state with new callback data
      setRepairs(prev => prev.map(r => r.id === repairId
        ? { ...r, callback_detected: result.callback_detected ?? null, callback_lbs_within_30d: result.callback_lbs_within_30d ?? null }
        : r
      ))
      if (result.callback_detected) {
        toast.error(`Callback detected — ${result.callback_lbs_within_30d?.toFixed(1)} lbs added after repair`)
      } else {
        toast.success('No callback detected — repair appears to have held')
      }
    } catch {
      toast.error('Failed to check callback status')
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (tab === 'aim-act') loadAimAct() }, [tab, loadAimAct])

  const filteredLeakEvents = leakStatusFilter
    ? leakEvents.filter(e => e.status === leakStatusFilter)
    : leakEvents

  const monthlyChart = buildMonthlyAddChart(adds)
  const recentLeaks = leakEvents.slice(0, 10)

  if (loading) {
    return (
      <div className="page-container">
        <PageHeader title="Refrigerant & Compliance" subtitle="Refrigerant tracking, leak detection, and AIM Act compliance" />
        <LoadingState label="Loading refrigerant data..." />
      </div>
    )
  }

  return (
    <div className="page-container">
      <PageHeader
        title="Refrigerant & Compliance"
        subtitle={site ? `${site.name} — Refrigerant tracking and AIM Act compliance` : 'Portfolio refrigerant tracking and AIM Act compliance'}
      >
        <button className="btn-secondary" style={{ fontSize: 12 }} onClick={() => {
          toast('AIM Act export coming soon — will generate a signed PDF packet', { icon: '📋' })
        }}>
          <ShieldCheck size={14} /> AIM Act Packet
        </button>
        <button className="btn-primary" onClick={() => setShowLogAdd(true)}>
          <Plus size={14} /> Log Refrigerant Add
        </button>
      </PageHeader>

      <TabBar tab={tab} setTab={setTab} counts={{
        'leak-events': leakEvents.length,
        'refrigerant-log': adds.length,
        'repairs': repairs.length,
        'circuits': circuits.length,
      }} />

      {/* ── OVERVIEW TAB ────────────────────────────────────────────────────── */}
      {tab === 'overview' && (
        <div>
          <div className="stat-grid stagger" style={{ marginBottom: 24 }}>
            <StatCard
              icon={<AlertTriangle size={18} />}
              color={(dashboard?.open_leak_events ?? 0) > 0 ? 'var(--danger)' : 'var(--success)'}
              value={String(dashboard?.open_leak_events ?? 0)}
              label="Open Leaks"
            />
            <StatCard
              icon={<Droplets size={18} />}
              color="var(--warning)"
              value={`${(dashboard?.refrigerant_added_30d_lbs ?? 0).toFixed(1)} lbs`}
              label="Refrigerant Added (30d)"
            />
            <StatCard
              icon={<Wrench size={18} />}
              color="var(--info)"
              value={String(dashboard?.repairs_30d ?? 0)}
              label="Repairs (30d)"
            />
            <StatCard
              icon={<ShieldCheck size={18} />}
              color={(dashboard?.sites_above_threshold ?? 0) > 0 ? 'var(--danger)' : 'var(--success)'}
              value={String(dashboard?.sites_above_threshold ?? 0)}
              label="Sites Above AIM-Act Threshold"
            />
          </div>

          <div className="dashboard-grid">
            {/* Recent Leak Events */}
            <div className="card">
              <div className="card-header">
                <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <AlertTriangle size={15} /> Recent Leak Events
                </h3>
                <button className="btn-ghost" style={{ fontSize: 12 }} onClick={() => setTab('leak-events')}>
                  View all <ChevronRight size={12} />
                </button>
              </div>
              <div className="card-body" style={{ padding: 0 }}>
                {recentLeaks.length === 0 ? (
                  <div className="empty-state" style={{ padding: '2rem 0' }}>
                    <div className="empty-icon"><CheckCircle size={22} /></div>
                    <h3>No leak events</h3>
                    <p>Log a leak event to start tracking refrigerant health.</p>
                  </div>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Rack / Zone</th>
                        <th>Status</th>
                        <th>Urgency</th>
                        <th>Est. Cost</th>
                        <th style={{ width: 80 }}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...recentLeaks].sort((a, b) =>
                        (STATUS_PRIORITY[a.status] ?? 9) - (STATUS_PRIORITY[b.status] ?? 9)
                      ).map(ev => {
                        const days = daysOpen(ev.detected_at)
                        const cost = leakCostEstimate(ev)
                        const isActive = ev.status === 'open' || ev.status === 'investigating'
                        return (
                          <tr key={ev.id}>
                            <td>
                              <span className="cell-primary">{ev.rack_name}</span>
                              {ev.zone_name && <span className="cell-secondary">{ev.zone_name}</span>}
                            </td>
                            <td><span className={`badge ${statusBadge(ev.status)}`}><span className="badge-dot" /> {ev.status.replace(/_/g, ' ')}</span></td>
                            <td>
                              {isActive ? (
                                <span style={{
                                  fontSize: 12, fontWeight: 600,
                                  color: days >= 7 ? 'var(--danger)' : days >= 3 ? 'var(--warning)' : 'var(--text-secondary)',
                                }}>
                                  {days}d open
                                </span>
                              ) : (
                                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{formatDate(ev.detected_at)}</span>
                              )}
                            </td>
                            <td style={{ fontSize: 13, fontWeight: cost ? 600 : 400, color: cost ? 'var(--danger)' : 'var(--text-muted)' }}>
                              {cost != null ? `~$${cost.toLocaleString()}` : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                            </td>
                            <td>
                              <button className="btn-ghost" style={{ fontSize: 11, padding: '3px 8px' }}
                                onClick={() => setUpdateStatusEvent(ev)}>
                                Update
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* Monthly Refrigerant Adds Chart */}
            <div className="card">
              <div className="card-header">
                <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <TrendingUp size={15} /> Refrigerant Added — Last 6 Months
                </h3>
              </div>
              <div className="card-body">
                {adds.length === 0 ? (
                  <div className="empty-state" style={{ padding: '1.5rem 0' }}>
                    <p className="text-muted">No refrigerant adds recorded yet.</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={monthlyChart} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
                      <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                      <YAxis tick={{ fontSize: 11 }} width={36} />
                      <Tooltip formatter={(v: number) => [`${v.toFixed(1)} lbs`, 'Added']} />
                      <Bar dataKey="lbs" name="Refrigerant (lbs)" fill="var(--accent)" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── AIM ACT TAB ─────────────────────────────────────────────────────── */}
      {tab === 'aim-act' && (
        <div>
          {aimActLoading ? (
            <LoadingState label="Loading AIM Act compliance data..." />
          ) : !aimActSummary ? (
            <EmptyState
              icon={<ShieldCheck size={24} />}
              title="No AIM Act data"
              description="Log refrigerant adds and configure circuits to start tracking AIM Act compliance."
            />
          ) : (
            <>
              <div className="stat-grid stagger" style={{ marginBottom: 24 }}>
                <StatCard
                  icon={<ShieldCheck size={18} />}
                  color={aimActSummary.facility_summary.circuits_above_threshold > 0 ? 'var(--danger)' : 'var(--success)'}
                  value={String(aimActSummary.facility_summary.circuits_above_threshold)}
                  label="Above AIM Threshold"
                />
                <StatCard
                  icon={<Droplets size={18} />}
                  color="var(--warning)"
                  value={`${aimActSummary.facility_summary.total_added_lbs.toFixed(1)} lbs`}
                  label="Total Added (365d)"
                />
                <StatCard
                  icon={<Activity size={18} />}
                  color={
                    aimActSummary.facility_summary.avg_leak_rate_pct != null && aimActSummary.facility_summary.avg_leak_rate_pct >= 20
                      ? 'var(--danger)'
                      : aimActSummary.facility_summary.avg_leak_rate_pct != null && aimActSummary.facility_summary.avg_leak_rate_pct >= 15
                        ? 'var(--warning)'
                        : 'var(--success)'
                  }
                  value={aimActSummary.facility_summary.avg_leak_rate_pct != null ? `${aimActSummary.facility_summary.avg_leak_rate_pct.toFixed(1)}%` : '—'}
                  label="Avg Leak Rate"
                />
                <StatCard
                  icon={<TrendingUp size={18} />}
                  color="var(--accent)"
                  value={String(forecasts.length)}
                  label="Circuits Forecasted"
                />
              </div>

              <div className="card">
                <div className="card-body" style={{ padding: 0 }}>
                  {aimActSummary.circuits.length === 0 ? (
                    <EmptyState
                      icon={<ShieldCheck size={24} />}
                      title="No circuits tracked"
                      description="Add refrigerant adds to start AIM Act tracking. Set full charge on circuits for precise leak rate calculations."
                    />
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Circuit / Rack</th>
                          <th>Refrigerant</th>
                          <th>Full Charge</th>
                          <th>Added (365d)</th>
                          <th>Leak Rate</th>
                          <th>AIM Act Status</th>
                          <th>Days to Warning</th>
                          <th>Days to Threshold</th>
                          <th>Forecast</th>
                        </tr>
                      </thead>
                      <tbody>
                        {aimActSummary.circuits.map(circuit => {
                          const forecast = forecasts.find(f =>
                            (circuit.circuit_id && f.circuit_id === circuit.circuit_id) ||
                            f.circuit_name === circuit.circuit_name
                          )
                          const leakRateColor = circuit.leak_rate_pct == null ? 'var(--text-muted)'
                            : circuit.leak_rate_pct >= 20 ? 'var(--danger)'
                            : circuit.leak_rate_pct >= 15 ? 'var(--warning)'
                            : 'var(--success)'
                          const aimStatusBadge = circuit.status === 'exceeds_threshold' ? 'badge-danger'
                            : circuit.status === 'warning' ? 'badge-warning'
                            : circuit.status === 'no_charge_data' ? 'badge-neutral'
                            : 'badge-success'
                          const aimStatusLabel = circuit.status === 'exceeds_threshold' ? 'Exceeds (>20%)'
                            : circuit.status === 'warning' ? 'Warning (>15%)'
                            : circuit.status === 'no_charge_data' ? 'No charge data'
                            : 'Compliant'
                          return (
                            <tr key={circuit.circuit_id ?? circuit.circuit_name}>
                              <td>
                                <span className="cell-primary">{circuit.circuit_name}</span>
                                {circuit.rack_name && <span className="cell-secondary">{circuit.rack_name}</span>}
                                {circuit.open_leak_events > 0 && (
                                  <span style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--danger)', marginTop: 2 }}>
                                    {circuit.open_leak_events} open leak{circuit.open_leak_events !== 1 ? 's' : ''}
                                  </span>
                                )}
                              </td>
                              <td style={{ fontSize: 12 }}>{circuit.refrigerant_type}</td>
                              <td style={{ fontFamily: 'monospace', fontSize: 13 }}>
                                {circuit.full_charge_lbs != null ? `${circuit.full_charge_lbs.toFixed(0)} lbs` : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                              </td>
                              <td style={{ fontFamily: 'monospace', fontSize: 13, fontWeight: 600 }}>
                                {circuit.total_added_lbs.toFixed(1)} lbs
                              </td>
                              <td>
                                <span style={{ fontFamily: 'monospace', fontSize: 14, fontWeight: 700, color: leakRateColor }}>
                                  {circuit.leak_rate_pct != null ? `${circuit.leak_rate_pct.toFixed(1)}%` : '—'}
                                </span>
                              </td>
                              <td>
                                <span className={`badge ${aimStatusBadge}`}>
                                  <span className="badge-dot" /> {aimStatusLabel}
                                </span>
                              </td>
                              <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                                {forecast?.days_to_aim_warning != null
                                  ? forecast.days_to_aim_warning === 0
                                    ? <span style={{ color: 'var(--warning)', fontWeight: 700 }}>Now</span>
                                    : `${forecast.days_to_aim_warning}d`
                                  : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                              </td>
                              <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                                {forecast?.days_to_aim_threshold != null
                                  ? forecast.days_to_aim_threshold === 0
                                    ? <span style={{ color: 'var(--danger)', fontWeight: 700 }}>Now</span>
                                    : (
                                      <span style={{ color: forecast.days_to_aim_threshold <= 30 ? 'var(--danger)' : forecast.days_to_aim_threshold <= 90 ? 'var(--warning)' : 'var(--text-primary)', fontWeight: forecast.days_to_aim_threshold <= 90 ? 600 : 400 }}>
                                        {forecast.days_to_aim_threshold}d
                                      </span>
                                    )
                                  : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                              </td>
                              <td>
                                {forecast ? (
                                  <div style={{ fontSize: 11 }}>
                                    <span style={{ color: 'var(--text-secondary)' }}>
                                      {forecast.method === 'linear' ? 'Linear' : forecast.method === 'exponential_smoothing' ? 'Exp. Smoothing' : forecast.method}
                                    </span>
                                    {forecast.confidence && (
                                      <span style={{
                                        marginLeft: 4, fontWeight: 600, fontSize: 10, textTransform: 'uppercase',
                                        color: forecast.confidence === 'high' ? 'var(--success)' : forecast.confidence === 'medium' ? 'var(--warning)' : 'var(--text-muted)',
                                      }}>
                                        {forecast.confidence}
                                      </span>
                                    )}
                                    {forecast.projected_adds_lbs != null && (
                                      <div style={{ color: 'var(--text-muted)', marginTop: 2 }}>
                                        +{forecast.projected_adds_lbs.toFixed(1)} lbs proj.
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                    {aimActSummary && aimActSummary.circuits.length > 0 ? 'Need ≥3 adds' : '—'}
                                  </span>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>

              <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--bg-secondary)', borderRadius: 8, fontSize: 12, color: 'var(--text-secondary)', display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                <ShieldCheck size={14} style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 1 }} />
                <span>
                  AIM Act thresholds for commercial refrigeration: <strong>&gt;15% annual leak rate</strong> triggers a warning; <strong>&gt;20%</strong> requires repair within 30 days.
                  Rates use a rolling 365-day window. Forecasts project 90 days forward — circuits need at least 3 refrigerant adds to generate a forecast.
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── LEAK EVENTS TAB ─────────────────────────────────────────────────── */}
      {tab === 'leak-events' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Filter size={14} style={{ color: 'var(--text-muted)' }} />
              <select
                value={leakStatusFilter}
                onChange={e => setLeakStatusFilter(e.target.value)}
                style={{ padding: '5px 10px', fontSize: 12, border: '1px solid var(--input-border)', borderRadius: 'var(--radius-sm)', background: 'var(--input-bg)', color: 'var(--text-primary)', fontFamily: 'inherit' }}
              >
                <option value="">All statuses</option>
                <option value="open">Open</option>
                <option value="investigating">Investigating</option>
                <option value="repaired">Repaired</option>
                <option value="closed">Closed</option>
                <option value="false_positive">False Positive</option>
              </select>
            </div>
            <button className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              onClick={() => {
                if (!facilityId) { toast.error('Select a facility first'); return }
                setShowLogLeak(true)
              }}>
              <Plus size={14} /> Log Leak Event
            </button>
          </div>

          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              {filteredLeakEvents.length === 0 ? (
                <EmptyState
                  icon={<Droplets size={24} />}
                  title="No leak events"
                  description="Log a leak event when a refrigerant leak is detected."
                />
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Rack / Zone</th>
                      <th>Detection</th>
                      <th>Status</th>
                      <th>Detected</th>
                      <th>Loss / Est. Cost</th>
                      <th style={{ width: 90 }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...filteredLeakEvents].sort((a, b) =>
                      (STATUS_PRIORITY[a.status] ?? 9) - (STATUS_PRIORITY[b.status] ?? 9)
                    ).map(ev => {
                      const cost = leakCostEstimate(ev)
                      const days = daysOpen(ev.detected_at)
                      const isActive = ev.status === 'open' || ev.status === 'investigating'
                      return (
                        <tr key={ev.id}>
                          <td>
                            <span className="cell-primary">{ev.rack_name}</span>
                            {ev.zone_name && <span className="cell-secondary">{ev.zone_name}</span>}
                            {isActive && days >= 3 && (
                              <span style={{
                                display: 'inline-block', marginTop: 2, fontSize: 10, fontWeight: 700,
                                color: days >= 7 ? 'var(--danger)' : 'var(--warning)',
                              }}>
                                {days}d open
                              </span>
                            )}
                          </td>
                          <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              {ev.detection_method.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                              {AUTO_DETECTION_METHODS.has(ev.detection_method) && (
                                <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 6px', background: 'var(--accent)', color: 'white', borderRadius: 'var(--radius-sm)', letterSpacing: '0.04em' }}>AUTO</span>
                              )}
                            </span>
                          </td>
                          <td>
                            <span className={`badge ${statusBadge(ev.status)}`}><span className="badge-dot" /> {ev.status.replace(/_/g, ' ')}</span>
                          </td>
                          <td style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>{formatDateTime(ev.detected_at)}</td>
                          <td>
                            {ev.estimated_loss_lbs != null ? (
                              <div>
                                <span style={{ fontSize: 13, fontFamily: 'monospace' }}>{ev.estimated_loss_lbs} lbs</span>
                                {cost != null && (
                                  <span style={{ fontSize: 11, color: 'var(--danger)', fontWeight: 600, marginLeft: 6 }}>~${cost.toLocaleString()}</span>
                                )}
                              </div>
                            ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                          </td>
                          <td>
                            <div style={{ display: 'flex', gap: 4 }}>
                              <button className="btn-secondary" style={{ fontSize: 11, padding: '4px 8px' }}
                                onClick={() => setUpdateStatusEvent(ev)}>
                                Update
                              </button>
                              {isActive && (
                                <button
                                  className="btn-secondary"
                                  style={{ fontSize: 11, padding: '4px 8px', display: 'flex', alignItems: 'center', gap: 3 }}
                                  onClick={() => handleCreateWorkOrderFromLeak(ev.id)}
                                  title="Auto-generate maintenance work order from this leak event"
                                >
                                  <Wrench size={10} /> WO
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
        </div>
      )}

      {/* ── REFRIGERANT LOG TAB ──────────────────────────────────────────────── */}
      {tab === 'refrigerant-log' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
            <button className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              onClick={() => {
                if (!facilityId) { toast.error('Select a facility first'); return }
                setShowLogAdd(true)
              }}>
              <Plus size={14} /> Log Refrigerant Add
            </button>
          </div>

          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              {adds.length === 0 ? (
                <EmptyState
                  icon={<Droplets size={24} />}
                  title="No refrigerant adds"
                  description="Log refrigerant adds to track consumption and calculate AIM Act leak rates."
                />
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Rack</th>
                      <th>Refrigerant</th>
                      <th>Amount (lbs)</th>
                      <th>Cost</th>
                      <th>Technician</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {adds.map(add => (
                      <tr key={add.id}>
                        <td style={{ fontSize: 12, whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
                          {formatDate(add.added_at)}
                        </td>
                        <td>
                          <span className="cell-primary">{add.rack_name}</span>
                        </td>
                        <td style={{ fontSize: 12 }}>{add.refrigerant_type}</td>
                        <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>{add.amount_lbs.toFixed(1)}</td>
                        <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                          {add.cost_per_lb != null ? `$${add.cost_per_lb.toFixed(2)}/lb` : ''}
                        </td>
                        <td style={{ fontSize: 13 }}>{add.technician_name}</td>
                        <td style={{ fontSize: 12, color: 'var(--text-tertiary)', maxWidth: 200 }}>
                          {add.notes ?? ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── REPAIRS TAB ─────────────────────────────────────────────────────── */}
      {tab === 'repairs' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
            <button className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              onClick={() => {
                if (!facilityId) { toast.error('Select a facility first'); return }
                setShowLogRepair(true)
              }}>
              <Plus size={14} /> Log Repair
            </button>
          </div>

          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              {repairs.length === 0 ? (
                <EmptyState
                  icon={<Wrench size={24} />}
                  title="No repairs logged"
                  description="Log repair records to document corrective actions and maintain audit trail."
                />
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Rack</th>
                      <th>Description</th>
                      <th>Technician</th>
                      <th>Verified Leak-Free</th>
                      <th>Callback Status</th>
                      <th>Recovered (lbs)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {repairs.map(r => (
                      <tr key={r.id}>
                        <td style={{ fontSize: 12, whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
                          {formatDate(r.repaired_at)}
                        </td>
                        <td><span className="cell-primary">{r.rack_name}</span></td>
                        <td style={{ fontSize: 13, maxWidth: 260 }}>
                          <span className="cell-primary">{r.description}</span>
                          {r.parts_replaced && <span className="cell-secondary">Parts: {r.parts_replaced}</span>}
                        </td>
                        <td style={{ fontSize: 13 }}>
                          <span className="cell-primary">{r.technician_name}</span>
                          {r.technician_company && <span className="cell-secondary">{r.technician_company}</span>}
                        </td>
                        <td>
                          {r.verified_leak_free
                            ? <span className="badge badge-success"><span className="badge-dot" /> Verified</span>
                            : <span className="badge badge-neutral">Not verified</span>}
                        </td>
                        <td>
                          {r.callback_detected === true && (
                            <span className="badge badge-danger" title={`${r.callback_lbs_within_30d?.toFixed(1)} lbs added within 30 days`}>
                              <span className="badge-dot" /> Callback
                            </span>
                          )}
                          {r.callback_detected === false && (
                            <span className="badge badge-success"><span className="badge-dot" /> Held</span>
                          )}
                          {r.callback_detected === null && (
                            <button
                              className="btn-secondary"
                              style={{ padding: '3px 8px', fontSize: 11 }}
                              onClick={() => checkCallback(r.id)}
                            >
                              Check
                            </button>
                          )}
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: 13 }}>
                          {r.refrigerant_recovered_lbs != null ? `${r.refrigerant_recovered_lbs.toFixed(1)}` : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── CIRCUITS TAB ─────────────────────────────────────────────────────── */}
      {tab === 'circuits' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
            <button className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              onClick={() => {
                if (!facilityId) { toast.error('Select a facility first'); return }
                setShowAddCircuit(true)
              }}>
              <Plus size={14} /> Add Circuit
            </button>
          </div>

          <div className="card">
            <div className="card-body" style={{ padding: 0 }}>
              {circuits.length === 0 ? (
                <EmptyState
                  icon={<Activity size={24} />}
                  title="No circuits configured"
                  description="Add refrigerant circuits to enable AIM Act leak rate tracking. Set the full charge to calculate annual leak rates."
                />
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Circuit</th>
                      <th>Refrigerant</th>
                      <th>Full Charge (lbs)</th>
                      <th>Rack / Compressors</th>
                      <th>Suction psi</th>
                      <th>Discharge psi</th>
                      <th>Load (kW)</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {circuits.map(c => (
                      <tr key={c.id}>
                        <td><span className="cell-primary">{c.name}</span></td>
                        <td style={{ fontSize: 12 }}>{c.refrigerant_type}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: 13 }}>
                          {c.full_charge_lbs != null ? `${c.full_charge_lbs.toFixed(1)}` : ''}
                        </td>
                        <td>
                          {c.rack ? (
                            <div>
                              <span className="cell-primary">{c.rack.rack_name}</span>
                              <span className="cell-secondary">{c.rack.active_compressors ?? ''} compressors</span>
                            </div>
                          ) : <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Not linked</span>}
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: 13,
                          color: c.rack?.avg_suction_psi != null && c.rack.design_suction_psi != null && c.rack.avg_suction_psi < c.rack.design_suction_psi * 0.85
                            ? 'var(--warning)' : 'var(--text-primary)' }}>
                          {c.rack?.avg_suction_psi != null ? `${c.rack.avg_suction_psi}` : ''}
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: 13,
                          color: c.rack?.avg_discharge_psi != null && c.rack.design_discharge_psi != null && c.rack.avg_discharge_psi > c.rack.design_discharge_psi * 1.1
                            ? 'var(--danger)' : 'var(--text-primary)' }}>
                          {c.rack?.avg_discharge_psi != null ? `${c.rack.avg_discharge_psi}` : ''}
                        </td>
                        <td style={{ fontFamily: 'monospace', fontSize: 13 }}>
                          {c.rack?.total_kw != null ? c.rack.total_kw.toFixed(1) : ''}
                        </td>
                        <td>
                          {c.is_active
                            ? <span className="badge badge-success"><span className="badge-dot" /> Active</span>
                            : <span className="badge badge-neutral">Inactive</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Modals ───────────────────────────────────────────────────────────── */}
      {showLogLeak && facilityId && (
        <LogLeakEventModal
          facilityId={facilityId}
          onClose={() => setShowLogLeak(false)}
          onSuccess={load}
        />
      )}
      {showLogAdd && facilityId && (
        <LogAddModal
          facilityId={facilityId}
          onClose={() => setShowLogAdd(false)}
          onSuccess={load}
        />
      )}
      {showLogRepair && facilityId && (
        <LogRepairModal
          facilityId={facilityId}
          onClose={() => setShowLogRepair(false)}
          onSuccess={load}
        />
      )}
      {showAddCircuit && facilityId && (
        <AddCircuitModal
          facilityId={facilityId}
          onClose={() => setShowAddCircuit(false)}
          onSuccess={load}
        />
      )}
      {updateStatusEvent && (
        <UpdateStatusModal
          event={updateStatusEvent}
          onClose={() => setUpdateStatusEvent(null)}
          onSuccess={load}
        />
      )}
    </div>
  )
}
