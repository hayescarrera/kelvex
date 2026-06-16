import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Thermometer, Plus, X, Loader2, Trash2, Edit3 } from 'lucide-react'
import LoadingState from '../../components/ui/LoadingState'
import EmptyState from '../../components/ui/EmptyState'
import { useZones, useCreateZone, useUpdateZone, useDeleteZone } from '../../hooks/useZones'
import type { Zone, ZoneCreate } from '../../lib/api'

const ZONE_TYPES = ['freezer', 'cooler', 'dock', 'machine_room', 'blast_freezer', 'staging']

const ZONE_COLORS: Record<string, string> = {
  freezer: 'var(--freezer)',
  cooler: 'var(--cooler)',
  dock: 'var(--dock)',
  machine_room: 'var(--machine)',
  blast_freezer: 'var(--freezer)',
  staging: 'var(--accent)',
}

const defaultForm = (): ZoneCreate => ({
  name: '',
  zone_type: 'freezer',
  temp_setpoint: undefined,
  temp_unit: 'F',
  temp_alarm_high: undefined,
  temp_alarm_low: undefined,
  humidity_setpoint: undefined,
  area_sqft: undefined,
})

export default function ZonesPage() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const { data, isLoading } = useZones(facilityId!)
  const createZone = useCreateZone(facilityId!)
  const updateZone = useUpdateZone(facilityId!)
  const deleteZone = useDeleteZone(facilityId!)

  const [showModal, setShowModal] = useState(false)
  const [editingZone, setEditingZone] = useState<Zone | null>(null)
  const [form, setForm] = useState<ZoneCreate>(defaultForm())

  const zones = data?.zones ?? []

  const openCreate = () => {
    setEditingZone(null)
    setForm(defaultForm())
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

          return (
            <div key={zone.id} className="zone-card" style={{ borderTopColor: color }}>
              <div className="zone-card-header">
                <span className="cell-primary">{zone.name}</span>
                <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                  <span className="chip" style={{ color }}>{zone.zone_type?.replace('_', ' ')}</span>
                  <button
                    className="icon-btn-sm"
                    onClick={() => openEdit(zone)}
                    title="Edit zone"
                  >
                    <Edit3 size={13} />
                  </button>
                  <button
                    className="icon-btn-sm danger"
                    onClick={() => handleDelete(zone)}
                    title="Delete zone"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.25rem', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '2.25rem', fontWeight: 700, color }}>
                  {zone.current_temp != null ? zone.current_temp : ''}
                </span>
                <span className="cell-secondary" style={{ fontSize: '1rem' }}>°{zone.temp_unit || 'F'}</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.8125rem' }}>
                <div>
                  <div className="text-muted">Setpoint</div>
                  <div className="cell-primary">
                    {zone.temp_setpoint != null ? `${zone.temp_setpoint}°${zone.temp_unit || 'F'}` : ''}
                  </div>
                </div>
                <div>
                  <div className="text-muted">Humidity</div>
                  <div className="cell-primary">
                    {zone.current_humidity != null ? `${zone.current_humidity}%` : ''}
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
            </div>
          )
        })}
      </div>

      {/* Create / Edit Modal */}
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
