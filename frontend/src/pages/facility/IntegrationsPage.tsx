import { useState } from 'react'
import { useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Plus, Loader2, X, RefreshCw, Trash2, Wifi, WifiOff, TestTube } from 'lucide-react'
import {
  useIntegrations, useProviders, useCreateIntegration,
  useTestIntegration, useDeleteIntegration, useTriggerPoll,
} from '../../hooks/useIntegrations'
import type { IntegrationRecord } from '../../lib/api'

const stateBadge = (state: string) => {
  if (state === 'active' || state === 'connected') return 'badge-success'
  if (state === 'error' || state === 'failed') return 'badge-danger'
  if (state === 'polling' || state === 'syncing') return 'badge-info'
  return 'badge-neutral'
}

export default function IntegrationsPage() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const { data, isLoading } = useIntegrations(facilityId!)
  const [showAddModal, setShowAddModal] = useState(false)
  const integrations = data?.integrations ?? []

  const testIntegration = useTestIntegration(facilityId!)
  const deleteIntegration = useDeleteIntegration(facilityId!)
  const triggerPoll = useTriggerPoll(facilityId!)

  const [testResults, setTestResults] = useState<Record<string, { success: boolean; latency_ms?: number; error?: string }>>({})

  const handleTest = async (id: string) => {
    try {
      const result = await testIntegration.mutateAsync(id)
      setTestResults(prev => ({ ...prev, [id]: result }))
      if (result.success) {
        toast.success('Connection test passed')
      } else {
        toast.error(`Connection test failed${result.error ? `: ${result.error}` : ''}`)
      }
    } catch {
      setTestResults(prev => ({ ...prev, [id]: { success: false, error: 'Test failed' } }))
      toast.error('Connection test failed')
    }
  }

  const formatDateTime = (val: string | null | undefined) =>
    val ? new Date(val).toLocaleString() : '\u2014'

  return (
    <div className="page-container stack-lg">
      <div className="card">
        <div className="card-header">
          <h3>Integrations ({integrations.length})</h3>
          <button className="btn-primary" onClick={() => setShowAddModal(true)}>
            <Plus size={14} /> Add Integration
          </button>
        </div>

        <div className="card-body" style={{ padding: 0 }}>
          {isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Loader2 size={24} className="spin" /></div>
          ) : integrations.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><Wifi size={24} /></div>
              <h3>No integrations configured</h3>
              <p>Connect your refrigeration controllers, BMS systems, and IoT sensors to start collecting live data.</p>
              <button className="btn-ghost" style={{ marginTop: 12 }} onClick={() => setShowAddModal(true)}>
                <Plus size={14} /> Add your first integration
              </button>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>Integration</th><th>Provider</th><th>Type</th><th>State</th><th>Last Poll</th><th>Readings</th><th style={{ width: 120 }}>Actions</th></tr>
              </thead>
              <tbody>
                {integrations.map((integ: IntegrationRecord) => (
                  <tr key={integ.id}>
                    <td>
                      <span className="cell-primary">{integ.name}</span>
                      {integ.description && <span className="cell-secondary">{integ.description}</span>}
                    </td>
                    <td>{integ.provider}</td>
                    <td><span className="badge badge-info">{integ.integration_type}</span></td>
                    <td>
                      <span className={`badge ${stateBadge(integ.connection_state)}`}>
                        {integ.connection_state === 'active' || integ.connection_state === 'connected'
                          ? <Wifi size={11} /> : <WifiOff size={11} />}
                        {integ.connection_state}
                      </span>
                      {testResults[integ.id] && (
                        <span className={`badge ${testResults[integ.id].success ? 'badge-success' : 'badge-danger'}`} style={{ marginLeft: 4, fontSize: 10 }}>
                          {testResults[integ.id].success
                            ? `OK ${testResults[integ.id].latency_ms ? `(${testResults[integ.id].latency_ms}ms)` : ''}`
                            : 'Fail'}
                        </span>
                      )}
                    </td>
                    <td style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>{formatDateTime(integ.last_poll_at)}</td>
                    <td>{integ.total_readings_ingested?.toLocaleString() ?? '0'}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 2 }}>
                        <button className="icon-btn-sm" title="Test connection" onClick={() => handleTest(integ.id)}>
                          <TestTube size={13} />
                        </button>
                        <button className="icon-btn-sm" title="Poll now" onClick={() => triggerPoll.mutate(integ.id, {
                          onSuccess: () => toast.success('Poll triggered'),
                          onError: () => toast.error('Failed to trigger poll'),
                        })}>
                          <RefreshCw size={13} />
                        </button>
                        <button className="icon-btn-sm danger" title="Delete" onClick={() => {
                          if (confirm('Delete this integration?')) deleteIntegration.mutate(integ.id, {
                            onSuccess: () => toast.success('Integration deleted'),
                            onError: () => toast.error('Failed to delete integration'),
                          })
                        }}>
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showAddModal && <AddIntegrationModal facilityId={facilityId!} onClose={() => setShowAddModal(false)} />}
    </div>
  )
}

/* ── Add Integration Modal ─────────────────────────────── */
function AddIntegrationModal({ facilityId, onClose }: { facilityId: string; onClose: () => void }) {
  const { data: providerData } = useProviders()
  const createIntegration = useCreateIntegration(facilityId)
  const providers = providerData?.providers ?? []

  const [form, setForm] = useState({
    name: '', provider: '', integration_type: '', description: '',
    host: '', port: '', unit_id: '',
  })

  // Auto-fill integration_type when provider is selected
  const handleProviderChange = (provider: string) => {
    const match = providers.find(p => p.provider === provider)
    setForm({
      ...form,
      provider,
      integration_type: match?.integration_type ?? '',
    })
  }

  const uniqueProviders = [...new Set(providers.map(p => p.provider))]

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const config: Record<string, unknown> = {}
    if (form.host) config.host = form.host
    if (form.port) config.port = parseInt(form.port)
    if (form.unit_id) config.unit_id = parseInt(form.unit_id)

    createIntegration.mutate({
      name: form.name,
      provider: form.provider,
      integration_type: form.integration_type,
      description: form.description || undefined,
      config: Object.keys(config).length > 0 ? config : undefined,
      enabled: true,
    }, {
      onSuccess: () => { toast.success('Integration added'); onClose() },
      onError: () => toast.error('Failed to add integration'),
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Integration</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Integration name</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Main Compressor Rack" required autoFocus />
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Provider</label>
              <select value={form.provider} onChange={e => handleProviderChange(e.target.value)} required>
                <option value="">Select provider...</option>
                {uniqueProviders.map(p => <option key={p} value={p}>{p}</option>)}
                {uniqueProviders.length === 0 && (
                  <>
                    <option value="emerson_e2">Emerson E2</option>
                    <option value="danfoss_aksc">Danfoss AK-SC</option>
                    <option value="honeywell">Honeywell</option>
                    <option value="modbus_tcp">Modbus TCP</option>
                    <option value="bacnet_ip">BACnet/IP</option>
                  </>
                )}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Type</label>
              <input value={form.integration_type} onChange={e => setForm({ ...form, integration_type: e.target.value })} placeholder="controller" required />
            </div>
          </div>
          <div className="field">
            <label>Description</label>
            <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Optional description" />
          </div>
          <div style={{ padding: '10px 14px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Connection Settings</span>
            <div className="field-row" style={{ marginTop: 8 }}>
              <div className="field" style={{ flex: 3 }}>
                <label>Host / IP</label>
                <input value={form.host} onChange={e => setForm({ ...form, host: e.target.value })} placeholder="192.168.1.100" />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Port</label>
                <input type="number" value={form.port} onChange={e => setForm({ ...form, port: e.target.value })} placeholder="502" />
              </div>
              <div className="field" style={{ flex: 1 }}>
                <label>Unit ID</label>
                <input type="number" value={form.unit_id} onChange={e => setForm({ ...form, unit_id: e.target.value })} placeholder="1" />
              </div>
            </div>
          </div>
          {createIntegration.isError && <p className="text-danger" style={{ fontSize: 12 }}>Failed to create integration.</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createIntegration.isPending}>
              {createIntegration.isPending ? 'Adding...' : <><Plus size={14} /> Add Integration</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
