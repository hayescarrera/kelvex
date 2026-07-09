import { useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Activity, Plus, X, Heart, AlertTriangle, Zap,
  RefreshCw, TrendingDown, Calendar, ExternalLink,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSiteContext } from '../contexts/SiteContext'
import {
  useCompressorSummary, useCompressorReadings, useCreateCompressor,
  useHealthCheck, useHealthTrend,
} from '../hooks/useCompressors'
import type { CompressorHealthSummary } from '../lib/api'

export default function CompressorFleet() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const { facilities } = useSiteContext()
  const facility = facilities.find(f => f.id === facilityId)
  const { data: summary, isLoading } = useCompressorSummary(facilityId)
  const [showAdd, setShowAdd] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)

  if (isLoading) return <LoadingState />

  return (
    <div>
      <PageHeader
        title="Compressor Fleet"
        subtitle={facility ? `${facility.name} — Refrigeration Plant` : 'Refrigeration Plant'}
      >
        <button className="btn-primary" onClick={() => setShowAdd(true)}><Plus size={15} /> Add Compressor</button>
      </PageHeader>

      {/* Stats */}
      {summary && (
        <div className="stat-grid stagger">
          <StatCard icon={<Activity size={18} />} color="var(--accent)" value={String(summary.total_compressors)} label="Compressors" />
          <StatCard icon={<Zap size={18} />} color="var(--success)" value={String(summary.running)} label="Running" />
          <StatCard icon={<AlertTriangle size={18} />} color={summary.in_alarm > 0 ? 'var(--danger)' : 'var(--success)'} value={String(summary.in_alarm)} label="In Alarm" />
          <StatCard
            icon={<Heart size={18} />}
            color={!summary.avg_health_score ? 'var(--text-muted)' : summary.avg_health_score >= 70 ? 'var(--success)' : summary.avg_health_score >= 40 ? 'var(--warning)' : 'var(--danger)'}
            value={summary.avg_health_score ? `${summary.avg_health_score}` : ''}
            label="Avg Health Score"
          />
        </div>
      )}

      {/* Power summary bar */}
      {summary && (summary.total_kw || summary.total_capacity_tons) && (
        <div className="card" style={{ marginTop: 16, marginBottom: 16 }}>
          <div className="card-body" style={{ display: 'flex', gap: 32, alignItems: 'center' }}>
            {summary.total_kw && (
              <div>
                <span className="text-muted" style={{ fontSize: 11 }}>Total Load</span>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{summary.total_kw} kW</div>
              </div>
            )}
            {summary.total_capacity_tons && (
              <div>
                <span className="text-muted" style={{ fontSize: 11 }}>Total Capacity</span>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{summary.total_capacity_tons} TR</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Compressor list */}
      <div className="content-area">
        {!summary || summary.total_compressors === 0 ? (
          <EmptyState
            icon={<Activity size={28} />}
            title="No compressors registered"
            description="Add your ammonia screw compressors to start monitoring health and performance."
            action={<button className="btn-ghost" onClick={() => setShowAdd(true)}><Plus size={15} /> Add compressor</button>}
          />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 12 }}>
            {summary.compressors.map(comp => (
              <CompressorCard
                key={comp.compressor_id}
                comp={comp}
                facilityId={facilityId!}
                isSelected={selected === comp.compressor_id}
                onSelect={() => setSelected(selected === comp.compressor_id ? null : comp.compressor_id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Detail panel */}
      {selected && facilityId && (
        <CompressorDetail facilityId={facilityId} compressorId={selected} onClose={() => setSelected(null)} />
      )}

      {showAdd && facilityId && <AddCompressorModal facilityId={facilityId} onClose={() => setShowAdd(false)} />}
    </div>
  )
}

function CompressorCard({ comp, facilityId, isSelected, onSelect }: {
  comp: CompressorHealthSummary; facilityId: string; isSelected: boolean
  onSelect: () => void
}) {
  const healthCheck = useHealthCheck(facilityId)

  const healthColor = !comp.health_score ? 'var(--text-muted)'
    : comp.health_score >= 70 ? 'var(--success)'
    : comp.health_score >= 40 ? 'var(--warning)'
    : 'var(--danger)'

  return (
    <div
      className="card"
      style={{ cursor: 'pointer', borderColor: isSelected ? 'var(--accent)' : undefined }}
      onClick={onSelect}
    >
      <div className="card-header" style={{ padding: '12px 16px' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 13 }}>{comp.name}</div>
          <div className="text-muted" style={{ fontSize: 11 }}>
            {[comp.manufacturer, comp.model].filter(Boolean).join(' ') || comp.tag || 'Compressor'}
            {comp.rack_name && ` · ${comp.rack_name}`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className={`badge badge-${comp.state === 'running' ? 'success' : comp.state === 'alarm' ? 'danger' : 'neutral'}`}>
            <span className="badge-dot" /> {comp.state}
          </span>
          {comp.portal_url && (
            <a
              href={comp.portal_url}
              target="_blank"
              rel="noopener noreferrer"
              className="icon-btn-sm"
              title="Open cloud portal"
              onClick={e => e.stopPropagation()}
              style={{ display: 'inline-flex', alignItems: 'center' }}
            >
              <ExternalLink size={13} />
            </a>
          )}
          <button className="icon-btn-sm" title="Health check" onClick={e => { e.stopPropagation(); healthCheck.mutate(comp.compressor_id) }}>
            <RefreshCw size={13} />
          </button>
        </div>
      </div>
      <div className="card-body" style={{ padding: '12px 16px' }}>
        {/* Health score bar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Heart size={14} style={{ color: healthColor }} />
          <div style={{ flex: 1, height: 6, background: 'var(--bg-tertiary)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{
              width: `${comp.health_score ?? 0}%`, height: '100%',
              background: healthColor, borderRadius: 3,
              transition: 'width 0.3s ease',
            }} />
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: healthColor, minWidth: 30, textAlign: 'right' }}>
            {comp.health_score ?? ''}
          </span>
        </div>

        {/* Key metrics */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, fontSize: 11 }}>
          <div>
            <div className="text-muted">Discharge</div>
            <div style={{ fontWeight: 600 }}>{comp.discharge_pressure_psi?.toFixed(0) ?? ''} psi</div>
          </div>
          <div>
            <div className="text-muted">Suction</div>
            <div style={{ fontWeight: 600 }}>{comp.suction_pressure_psi?.toFixed(0) ?? ''} psi</div>
          </div>
          <div>
            <div className="text-muted">Oil Temp</div>
            <div style={{ fontWeight: 600 }}>{comp.oil_temp_f?.toFixed(0) ?? ''}°F</div>
          </div>
          <div>
            <div className="text-muted">Bearing</div>
            <div style={{ fontWeight: 600, color: comp.anomalies.some(a => a.includes('bearing') || a.includes('Bearing')) ? 'var(--danger)' : undefined }}>
              {comp.bearing_temp_f?.toFixed(0) ?? ''}°F
            </div>
          </div>
          <div>
            <div className="text-muted">Vibration</div>
            <div style={{ fontWeight: 600, color: comp.anomalies.some(a => a.includes('ibration')) ? 'var(--danger)' : undefined }}>
              {comp.vibration_ips?.toFixed(3) ?? ''} in/s
            </div>
          </div>
          <div>
            <div className="text-muted">Load</div>
            <div style={{ fontWeight: 600 }}>{comp.slide_valve_pct?.toFixed(0) ?? ''}%</div>
          </div>
        </div>

        {/* Anomalies */}
        {comp.anomalies.length > 0 && (
          <div style={{ marginTop: 10, padding: '6px 8px', background: 'var(--danger-bg)', borderRadius: 'var(--radius-sm)', fontSize: 11, color: 'var(--danger)' }}>
            <AlertTriangle size={11} style={{ marginRight: 4, verticalAlign: -1 }} />
            {comp.anomalies[0]}
            {comp.anomalies.length > 1 && <span className="text-muted"> +{comp.anomalies.length - 1} more</span>}
          </div>
        )}
      </div>
    </div>
  )
}

function CompressorDetail({ facilityId, compressorId, onClose }: {
  facilityId: string; compressorId: string; onClose: () => void
}) {
  const { data, isLoading } = useCompressorReadings(facilityId, compressorId, 24)
  const { data: trend } = useHealthTrend(facilityId, compressorId)

  const chartData = (data?.readings ?? []).map(r => ({
    time: new Date(r.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    discharge_psi: r.discharge_pressure_psi,
    suction_psi: r.suction_pressure_psi,
    oil_temp: r.oil_temp_f,
    bearing_temp: r.bearing_temp_f,
    vibration: r.vibration_ips,
    kw: r.kw,
  }))

  const urgencyColor = {
    immediate: 'var(--danger)',
    soon: 'var(--warning)',
    monitor: 'var(--accent)',
    healthy: 'var(--success)',
  }[trend?.maintenance_urgency ?? 'healthy']

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="card-header">
        <h3>24-Hour Telemetry</h3>
        <button className="icon-btn" onClick={onClose}><X size={16} /></button>
      </div>

      {/* Maintenance forecast banner */}
      {trend && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '10px 16px', borderBottom: '1px solid var(--border)',
          background: `color-mix(in srgb, ${urgencyColor} 8%, transparent)`,
        }}>
          {trend.maintenance_urgency === 'immediate' || trend.maintenance_urgency === 'soon'
            ? <TrendingDown size={14} style={{ color: urgencyColor }} />
            : <Calendar size={14} style={{ color: urgencyColor }} />
          }
          <div style={{ flex: 1, fontSize: 12 }}>
            <strong style={{ color: urgencyColor }}>
              {trend.maintenance_urgency === 'immediate' && 'Immediate intervention needed'}
              {trend.maintenance_urgency === 'soon' && `Maintenance recommended within ${trend.days_to_maintenance_threshold} days`}
              {trend.maintenance_urgency === 'monitor' && `Maintenance projected in ~${trend.days_to_maintenance_threshold} days`}
              {trend.maintenance_urgency === 'healthy' && 'Health trending healthy'}
            </strong>
            {trend.projected_maintenance_date && (
              <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>
                Threshold by {trend.projected_maintenance_date}
              </span>
            )}
            {trend.trend_slope_per_day !== null && (
              <span style={{ color: 'var(--text-muted)', marginLeft: 8, fontSize: 11 }}>
                ({trend.trend_slope_per_day > 0 ? '+' : ''}{trend.trend_slope_per_day?.toFixed(2)} pts/day)
              </span>
            )}
          </div>
        </div>
      )}

      <div className="card-body">
        {isLoading ? <LoadingState /> : chartData.length === 0 ? (
          <p className="text-muted" style={{ textAlign: 'center', padding: 20 }}>No readings in the last 24 hours</p>
        ) : (
          <div className="dashboard-grid">
            <div>
              <h4 style={{ fontSize: 12, marginBottom: 8, color: 'var(--text-muted)' }}>Pressures (PSI)</h4>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} width={40} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="discharge_psi" stroke="var(--danger)" dot={false} name="Discharge" />
                  <Line type="monotone" dataKey="suction_psi" stroke="var(--accent)" dot={false} name="Suction" />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h4 style={{ fontSize: 12, marginBottom: 8, color: 'var(--text-muted)' }}>Temperatures (°F)</h4>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} width={40} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="oil_temp" stroke="var(--warning)" dot={false} name="Oil Temp" />
                  <Line type="monotone" dataKey="bearing_temp" stroke="var(--danger)" dot={false} name="Bearing Temp" />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h4 style={{ fontSize: 12, marginBottom: 8, color: 'var(--text-muted)' }}>Vibration (in/s)</h4>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} width={40} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="vibration" stroke="#7c3aed" dot={false} name="Vibration" />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div>
              <h4 style={{ fontSize: 12, marginBottom: 8, color: 'var(--text-muted)' }}>Power (kW)</h4>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} width={40} />
                  <Tooltip content={<ChartTooltip />} />
                  <Line type="monotone" dataKey="kw" stroke="var(--success)" dot={false} name="kW" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function AddCompressorModal({ facilityId, onClose }: { facilityId: string; onClose: () => void }) {
  const createComp = useCreateCompressor(facilityId)
  const [form, setForm] = useState({
    name: '', manufacturer: '', model: '', tag: '',
    compressor_type: 'screw', refrigerant: 'NH3',
    hp: '', capacity_tons: '', rack_name: '',
    refrigerant_charge_lbs: '', portal_url: '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createComp.mutate({
      name: form.name,
      manufacturer: form.manufacturer || undefined,
      model: form.model || undefined,
      tag: form.tag || undefined,
      compressor_type: form.compressor_type,
      refrigerant: form.refrigerant,
      hp: form.hp ? parseFloat(form.hp) : undefined,
      capacity_tons: form.capacity_tons ? parseFloat(form.capacity_tons) : undefined,
      rack_name: form.rack_name || undefined,
      refrigerant_charge_lbs: form.refrigerant_charge_lbs ? parseFloat(form.refrigerant_charge_lbs) : undefined,
      portal_url: form.portal_url || undefined,
    }, {
      onSuccess: () => onClose(),
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Compressor</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Compressor name</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Frick RWF II #1" required autoFocus />
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Manufacturer</label>
              <select value={form.manufacturer} onChange={e => setForm({ ...form, manufacturer: e.target.value })}>
                <option value="">Select...</option>
                <option value="Frick">Frick (Johnson Controls)</option>
                <option value="Vilter">Vilter (Emerson)</option>
                <option value="Mycom">Mycom (Mayekawa)</option>
                <option value="GEA">GEA</option>
                <option value="Bitzer">Bitzer</option>
                <option value="Other">Other</option>
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Model</label>
              <input value={form.model} onChange={e => setForm({ ...form, model: e.target.value })} placeholder="e.g. RWF II 480" />
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Type</label>
              <select value={form.compressor_type} onChange={e => setForm({ ...form, compressor_type: e.target.value })}>
                <option value="screw">Screw</option>
                <option value="reciprocating">Reciprocating</option>
                <option value="scroll">Scroll</option>
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Refrigerant</label>
              <select value={form.refrigerant} onChange={e => setForm({ ...form, refrigerant: e.target.value })}>
                <option value="NH3">NH3 (Ammonia)</option>
                <option value="R-404A">R-404A</option>
                <option value="R-22">R-22</option>
                <option value="CO2">CO2</option>
                <option value="R-448A">R-448A</option>
              </select>
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Horsepower</label>
              <input type="number" value={form.hp} onChange={e => setForm({ ...form, hp: e.target.value })} placeholder="500" />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Capacity (TR)</label>
              <input type="number" value={form.capacity_tons} onChange={e => setForm({ ...form, capacity_tons: e.target.value })} placeholder="200" />
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Tag / ID</label>
              <input value={form.tag} onChange={e => setForm({ ...form, tag: e.target.value })} placeholder="COMP-A1" />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Rack / Engine Room</label>
              <input value={form.rack_name} onChange={e => setForm({ ...form, rack_name: e.target.value })} placeholder="Engine Room 1" />
            </div>
          </div>
          <div className="field">
            <label>Refrigerant charge (lbs)</label>
            <input type="number" value={form.refrigerant_charge_lbs} onChange={e => setForm({ ...form, refrigerant_charge_lbs: e.target.value })} placeholder="5000" />
          </div>
          <div className="field">
            <label>Cloud Portal URL <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>(optional)</span></label>
            <input type="url" value={form.portal_url} onChange={e => setForm({ ...form, portal_url: e.target.value })} placeholder="https://connected.emerson.com/..." />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createComp.isPending}>
              {createComp.isPending ? 'Adding...' : <><Plus size={15} /> Add Compressor</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
