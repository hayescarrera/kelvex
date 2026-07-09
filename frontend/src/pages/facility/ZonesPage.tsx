import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Thermometer, Plus, X, Loader2, Trash2, Edit3, Radio, ChevronDown, ChevronRight } from 'lucide-react'
import LoadingState from '../../components/ui/LoadingState'
import EmptyState from '../../components/ui/EmptyState'
import {
  useZones, useCreateZone, useUpdateZone, useDeleteZone,
  useZoneSensors, useCreateZoneSensor, useUpdateZoneSensor, useDeleteZoneSensor,
} from '../../hooks/useZones'
import type { Zone, ZoneCreate, ZoneSensor, ZoneSensorCreate } from '../../lib/api'

const ZONE_TYPES = ['freezer', 'cooler', 'dock', 'machine_room', 'blast_freezer', 'staging']
const SENSOR_TYPES = ['temperature', 'humidity', 'door_contact', 'ammonia', 'pressure_differential', 'glycol_temp']
const DATA_TYPES = ['uint16', 'int16', 'float32', 'uint32']
const REGISTER_TYPES = ['holding', 'input']

const ZONE_COLORS: Record<string, string> = {
  freezer: 'var(--freezer)',
  cooler: 'var(--cooler)',
  dock: 'var(--dock)',
  machine_room: 'var(--machine)',
  blast_freezer: 'var(--freezer)',
  staging: 'var(--accent)',
}

const defaultZoneForm = (): ZoneCreate => ({
  name: '',
  zone_type: 'freezer',
  temp_setpoint: undefined,
  temp_unit: 'F',
  temp_alarm_high: undefined,
  temp_alarm_low: undefined,
  humidity_setpoint: undefined,
  area_sqft: undefined,
})

const defaultSensorForm = (): ZoneSensorCreate => ({
  name: '',
  sensor_type: 'temperature',
  unit: 'degF',
  host: '',
  port: 502,
  slave_id: 1,
  register_address: undefined,
  register_type: 'holding',
  data_type: 'uint16',
  scale: 1.0,
  offset: 0.0,
  alarm_high: undefined,
  alarm_low: undefined,
  poll_interval_sec: 30,
})

function SensorStateChip({ state }: { state: string }) {
  const colors: Record<string, string> = {
    normal: 'var(--success)',
    warning: 'var(--warning)',
    alarm: 'var(--danger)',
    offline: 'var(--text-muted)',
  }
  return (
    <span style={{ fontSize: '0.72rem', color: colors[state] ?? 'var(--text-muted)', fontWeight: 600 }}>
      {state}
    </span>
  )
}

function ZoneSensorsPanel({
  zone,
  facilityId,
}: {
  zone: Zone
  facilityId: string
}) {
  const { data, isLoading } = useZoneSensors(facilityId, zone.id)
  const createSensor = useCreateZoneSensor(facilityId, zone.id)
  const updateSensor = useUpdateZoneSensor(facilityId, zone.id)
  const deleteSensor = useDeleteZoneSensor(facilityId, zone.id)

  const [showForm, setShowForm] = useState(false)
  const [editingSensor, setEditingSensor] = useState<ZoneSensor | null>(null)
  const [form, setForm] = useState<ZoneSensorCreate>(defaultSensorForm())

  const sensors = data?.sensors ?? []

  const openCreate = () => {
    setEditingSensor(null)
    setForm(defaultSensorForm())
    setShowForm(true)
  }

  const openEdit = (s: ZoneSensor) => {
    setEditingSensor(s)
    setForm({
      name: s.name,
      sensor_type: s.sensor_type,
      unit: s.unit ?? 'degF',
      host: s.host ?? '',
      port: s.port,
      slave_id: s.slave_id,
      register_address: s.register_address ?? undefined,
      register_type: s.register_type,
      data_type: s.data_type,
      scale: s.scale,
      offset: s.offset,
      alarm_high: s.alarm_high ?? undefined,
      alarm_low: s.alarm_low ?? undefined,
      poll_interval_sec: s.poll_interval_sec,
    })
    setShowForm(true)
  }

  const handleSave = () => {
    if (!form.name.trim()) return
    const payload = { ...form, host: form.host || undefined }
    if (editingSensor) {
      updateSensor.mutate(
        { sensorId: editingSensor.id, data: payload },
        { onSuccess: () => setShowForm(false) },
      )
    } else {
      createSensor.mutate(payload, { onSuccess: () => setShowForm(false) })
    }
  }

  const handleDelete = (s: ZoneSensor) => {
    if (!confirm(`Remove sensor "${s.name}"?`)) return
    deleteSensor.mutate(s.id)
  }

  const sf = (key: keyof ZoneSensorCreate, val: string | number | boolean | undefined) =>
    setForm(prev => ({ ...prev, [key]: val }))

  return (
    <div style={{ borderTop: '1px solid var(--border)', marginTop: '0.75rem', paddingTop: '0.75rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
          <Radio size={11} style={{ verticalAlign: 'middle', marginRight: 4 }} />
          Sensors {sensors.length > 0 ? `(${sensors.length})` : ''}
        </span>
        <button
          className="btn-ghost"
          onClick={openCreate}
          style={{ fontSize: '0.72rem', padding: '0.15rem 0.4rem' }}
        >
          <Plus size={11} /> Add
        </button>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '0.5rem' }}>
          <Loader2 size={14} className="spin" />
        </div>
      ) : sensors.length === 0 ? (
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>
          No sensors — add one to start monitoring this zone.
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {sensors.map(s => (
            <div key={s.id} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              background: 'var(--surface-2)', borderRadius: 4, padding: '0.3rem 0.5rem',
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {s.name}
                  <span style={{ marginLeft: 6, fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 400 }}>
                    {s.sensor_type}
                  </span>
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'flex', gap: 8 }}>
                  {s.current_value != null && (
                    <span>{s.current_value}{s.unit ? ` ${s.unit}` : ''}</span>
                  )}
                  {s.register_address != null ? (
                    <span>reg {s.register_address}</span>
                  ) : (
                    <span style={{ color: 'var(--warning)' }}>no register configured</span>
                  )}
                  <SensorStateChip state={s.current_state} />
                </div>
              </div>
              <div style={{ display: 'flex', gap: 2, marginLeft: 8 }}>
                <button className="icon-btn-sm" onClick={() => openEdit(s)} title="Edit sensor">
                  <Edit3 size={11} />
                </button>
                <button className="icon-btn-sm danger" onClick={() => handleDelete(s)} title="Remove sensor">
                  <Trash2 size={11} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
            <div className="modal-header">
              <h3>{editingSensor ? 'Edit Sensor' : `Add Sensor — ${zone.name}`}</h3>
              <button className="btn-ghost" onClick={() => setShowForm(false)} style={{ padding: 4 }}>
                <X size={16} />
              </button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div className="field">
                  <label>Name</label>
                  <input value={form.name} onChange={e => sf('name', e.target.value)} placeholder="Probe 1" />
                </div>
                <div className="field">
                  <label>Type</label>
                  <select value={form.sensor_type} onChange={e => sf('sensor_type', e.target.value)}
                    style={{ width: '100%', padding: '8px 10px', fontSize: 13, border: '1px solid var(--input-border)', borderRadius: 'var(--radius-md)', background: 'var(--input-bg)', color: 'var(--text-primary)', fontFamily: 'inherit' }}>
                    {SENSOR_TYPES.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
                  </select>
                </div>
              </div>

              <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 4 }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Modbus Connection</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 8 }}>
                <div className="field">
                  <label>Host / IP</label>
                  <input value={form.host ?? ''} onChange={e => sf('host', e.target.value)} placeholder="192.168.1.100" />
                </div>
                <div className="field">
                  <label>Port</label>
                  <input type="number" value={form.port ?? 502} onChange={e => sf('port', Number(e.target.value))} style={{ width: 70 }} />
                </div>
                <div className="field">
                  <label>Slave ID</label>
                  <input type="number" value={form.slave_id ?? 1} onChange={e => sf('slave_id', Number(e.target.value))} style={{ width: 70 }} />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 8 }}>
                <div className="field">
                  <label>Register Addr</label>
                  <input type="number" value={form.register_address ?? ''} onChange={e => sf('register_address', e.target.value ? Number(e.target.value) : undefined)} placeholder="30001" />
                </div>
                <div className="field">
                  <label>Reg Type</label>
                  <select value={form.register_type} onChange={e => sf('register_type', e.target.value)}
                    style={{ width: '100%', padding: '8px 6px', fontSize: 12, border: '1px solid var(--input-border)', borderRadius: 'var(--radius-md)', background: 'var(--input-bg)', color: 'var(--text-primary)', fontFamily: 'inherit' }}>
                    {REGISTER_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label>Data Type</label>
                  <select value={form.data_type} onChange={e => sf('data_type', e.target.value)}
                    style={{ width: '100%', padding: '8px 6px', fontSize: 12, border: '1px solid var(--input-border)', borderRadius: 'var(--radius-md)', background: 'var(--input-bg)', color: 'var(--text-primary)', fontFamily: 'inherit' }}>
                    {DATA_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="field">
                  <label>Unit</label>
                  <input value={form.unit ?? ''} onChange={e => sf('unit', e.target.value)} placeholder="degF" />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                <div className="field">
                  <label>Scale</label>
                  <input type="number" step="any" value={form.scale ?? 1} onChange={e => sf('scale', Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>Offset</label>
                  <input type="number" step="any" value={form.offset ?? 0} onChange={e => sf('offset', Number(e.target.value))} />
                </div>
                <div className="field">
                  <label>Poll (sec)</label>
                  <input type="number" value={form.poll_interval_sec ?? 30} onChange={e => sf('poll_interval_sec', Number(e.target.value))} />
                </div>
              </div>

              <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 4 }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Alarms</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div className="field">
                  <label>High alarm</label>
                  <input type="number" step="any" value={form.alarm_high ?? ''} onChange={e => sf('alarm_high', e.target.value ? Number(e.target.value) : undefined)} placeholder="e.g. 35" />
                </div>
                <div className="field">
                  <label>Low alarm</label>
                  <input type="number" step="any" value={form.alarm_low ?? ''} onChange={e => sf('alarm_low', e.target.value ? Number(e.target.value) : undefined)} placeholder="e.g. -15" />
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
              <button
                className="btn-primary" onClick={handleSave}
                disabled={!form.name.trim() || createSensor.isPending || updateSensor.isPending}
              >
                {(createSensor.isPending || updateSensor.isPending)
                  ? <><Loader2 size={14} className="spin" /> Saving...</>
                  : editingSensor ? 'Save Changes' : 'Add Sensor'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ZonesPage() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const { data, isLoading } = useZones(facilityId!)
  const createZone = useCreateZone(facilityId!)
  const updateZone = useUpdateZone(facilityId!)
  const deleteZone = useDeleteZone(facilityId!)

  const [showModal, setShowModal] = useState(false)
  const [editingZone, setEditingZone] = useState<Zone | null>(null)
  const [form, setForm] = useState<ZoneCreate>(defaultZoneForm())
  const [expandedZones, setExpandedZones] = useState<Set<string>>(new Set())

  const zones = data?.zones ?? []

  const toggleExpanded = (zoneId: string) =>
    setExpandedZones(prev => {
      const next = new Set(prev)
      if (next.has(zoneId)) next.delete(zoneId)
      else next.add(zoneId)
      return next
    })

  const openCreate = () => {
    setEditingZone(null)
    setForm(defaultZoneForm())
    setShowModal(true)
  }

  const openEdit = (zone: Zone) => {
    setEditingZone(zone)
    setForm({
      name: zone.name,
      zone_type: zone.zone_type,
      temp_setpoint: zone.temp_setpoint ?? undefined,
      temp_unit: zone.temp_unit || 'F',
      temp_alarm_high: zone.temp_alarm_high ?? undefined,
      temp_alarm_low: zone.temp_alarm_low ?? undefined,
      humidity_setpoint: zone.humidity_setpoint ?? undefined,
      area_sqft: zone.area_sqft ?? undefined,
    })
    setShowModal(true)
  }

  const handleSave = () => {
    if (!form.name.trim()) return
    if (editingZone) {
      updateZone.mutate(
        { zoneId: editingZone.id, data: form },
        { onSuccess: () => setShowModal(false) },
      )
    } else {
      createZone.mutate(form, {
        onSuccess: () => setShowModal(false),
      })
    }
  }

  const handleDelete = (zone: Zone) => {
    if (!confirm(`Delete zone "${zone.name}"? This cannot be undone.`)) return
    deleteZone.mutate(zone.id)
  }

  const setField = (key: keyof ZoneCreate, val: string | number | undefined) =>
    setForm(prev => ({ ...prev, [key]: val }))

  if (isLoading) return <LoadingState />

  if (zones.length === 0 && !showModal) {
    return (
      <>
        <EmptyState
          icon={<Thermometer size={32} />}
          title="No zones configured"
          description="Add your first zone to start monitoring temperatures."
          action={
            <button className="btn-primary" onClick={openCreate} style={{ marginTop: 12 }}>
              <Plus size={14} /> Add Zone
            </button>
          }
        />
      </>
    )
  }

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <button className="btn-primary" onClick={openCreate}>
          <Plus size={14} /> Add Zone
        </button>
      </div>

      <div className="zone-grid">
        {zones.map((zone: Zone) => {
          const color = ZONE_COLORS[zone.zone_type] ?? 'var(--accent)'
          const isDoorOpen = zone.door_open === true
          const isExpanded = expandedZones.has(zone.id)

          return (
            <div key={zone.id} className="zone-card" style={{ borderTopColor: color }}>
              <div className="zone-card-header">
                <span className="cell-primary">{zone.name}</span>
                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                  <span className="chip" style={{ color }}>{zone.zone_type?.replace('_', ' ')}</span>
                  <button className="icon-btn-sm" onClick={() => openEdit(zone)} title="Edit zone">
                    <Edit3 size={13} />
                  </button>
                  <button className="icon-btn-sm danger" onClick={() => handleDelete(zone)} title="Delete zone">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.25rem', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '2.25rem', fontWeight: 700, color }}>
                  {zone.current_temp != null ? zone.current_temp : '—'}
                </span>
                <span className="cell-secondary" style={{ fontSize: '1rem' }}>°{zone.temp_unit || 'F'}</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.8125rem' }}>
                <div>
                  <div className="text-muted">Setpoint</div>
                  <div className="cell-primary">
                    {zone.temp_setpoint != null ? `${zone.temp_setpoint}°${zone.temp_unit || 'F'}` : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-muted">Humidity</div>
                  <div className="cell-primary">
                    {zone.current_humidity != null ? `${zone.current_humidity}%` : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-muted">Door</div>
                  <div style={{ fontWeight: 600, color: isDoorOpen ? 'var(--danger)' : undefined }}>
                    {isDoorOpen ? 'OPEN' : 'Closed'}
                  </div>
                </div>
                <div>
                  <div className="text-muted">State</div>
                  <div className="cell-primary">{zone.state || 'normal'}</div>
                </div>
              </div>

              <button
                className="btn-ghost"
                onClick={() => toggleExpanded(zone.id)}
                style={{ fontSize: '0.75rem', width: '100%', marginTop: '0.75rem', justifyContent: 'flex-start', gap: 4 }}
              >
                {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                Sensors
              </button>

              {isExpanded && (
                <ZoneSensorsPanel zone={zone} facilityId={facilityId!} />
              )}
            </div>
          )
        })}
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 460 }}>
            <div className="modal-header">
              <h3>{editingZone ? 'Edit Zone' : 'Add Zone'}</h3>
              <button className="btn-ghost" onClick={() => setShowModal(false)} style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div className="modal-body">
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Zone name</label>
                <input value={form.name} onChange={e => setField('name', e.target.value)} placeholder="Freezer 1" />
              </div>
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Zone type</label>
                <select
                  value={form.zone_type}
                  onChange={e => setField('zone_type', e.target.value)}
                  style={{
                    width: '100%', padding: '8px 10px', fontSize: '13px', border: '1px solid var(--input-border)',
                    borderRadius: 'var(--radius-md)', background: 'var(--input-bg)', color: 'var(--text-primary)', fontFamily: 'inherit',
                  }}
                >
                  {ZONE_TYPES.map(t => (
                    <option key={t} value={t}>{t.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>
                  ))}
                </select>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                <div className="field">
                  <label>Temp setpoint (°{form.temp_unit || 'F'})</label>
                  <input
                    type="number" value={form.temp_setpoint ?? ''}
                    onChange={e => setField('temp_setpoint', e.target.value ? Number(e.target.value) : undefined)}
                    placeholder="-10"
                  />
                </div>
                <div className="field">
                  <label>Area (sqft)</label>
                  <input
                    type="number" value={form.area_sqft ?? ''}
                    onChange={e => setField('area_sqft', e.target.value ? Number(e.target.value) : undefined)}
                    placeholder="5000"
                  />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                <div className="field">
                  <label>High alarm (°{form.temp_unit || 'F'})</label>
                  <input
                    type="number" value={form.temp_alarm_high ?? ''}
                    onChange={e => setField('temp_alarm_high', e.target.value ? Number(e.target.value) : undefined)}
                    placeholder="5"
                  />
                </div>
                <div className="field">
                  <label>Low alarm (°{form.temp_unit || 'F'})</label>
                  <input
                    type="number" value={form.temp_alarm_low ?? ''}
                    onChange={e => setField('temp_alarm_low', e.target.value ? Number(e.target.value) : undefined)}
                    placeholder="-25"
                  />
                </div>
              </div>
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Humidity setpoint (%)</label>
                <input
                  type="number" value={form.humidity_setpoint ?? ''}
                  onChange={e => setField('humidity_setpoint', e.target.value ? Number(e.target.value) : undefined)}
                  placeholder="85"
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
              <button
                className="btn-primary" onClick={handleSave}
                disabled={!form.name.trim() || createZone.isPending || updateZone.isPending}
              >
                {(createZone.isPending || updateZone.isPending) ?
                  <><Loader2 size={14} className="spin" /> Saving...</> :
                  editingZone ? 'Save Changes' : 'Create Zone'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
