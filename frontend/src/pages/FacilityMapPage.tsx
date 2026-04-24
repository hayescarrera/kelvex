import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Loader2, MapPin, Save, Edit3, Eye, Trash2,
  RefreshCw, ZoomIn, ZoomOut, Maximize2,
  Cpu, Zap, AlertTriangle, Square, Type,
} from 'lucide-react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useSiteContext } from '../contexts/SiteContext'
import toast from 'react-hot-toast'
import type {
  FloorPlanData, FloorPlanElement, Zone, Compressor, Alert as AlertT,
} from '../lib/api'

// ── Constants ──────────────────────────────────

const ZONE_TYPE_COLORS: Record<string, string> = {
  frozen: '#3b82f6',
  freezer: '#3b82f6',
  cooler: '#06b6d4',
  dock: '#f59e0b',
  dry: '#8b5cf6',
  prep: '#10b981',
  default: '#6b7280',
}

const STATE_COLORS: Record<string, string> = {
  running: '#10b981',
  online: '#10b981',
  idle: '#f59e0b',
  stopped: '#6b7280',
  offline: '#6b7280',
  fault: '#ef4444',
  alarm: '#ef4444',
}

function tempColor(temp: number | null, setpoint: number | null, alarmHigh: number | null, alarmLow: number | null): string {
  if (temp == null) return '#6b7280'
  if (alarmHigh != null && temp > alarmHigh) return '#ef4444'
  if (alarmLow != null && temp < alarmLow) return '#ef4444'
  if (setpoint != null && Math.abs(temp - setpoint) > 5) return '#f59e0b'
  return '#10b981'
}

const POLL_INTERVAL = 8000

type Mode = 'live' | 'edit'

const ELEMENT_PALETTE: { type: FloorPlanElement['type']; label: string; icon: typeof Square }[] = [
  { type: 'zone', label: 'Zone', icon: Square },
  { type: 'compressor', label: 'Compressor', icon: Cpu },
  { type: 'equipment', label: 'Equipment', icon: Zap },
  { type: 'label', label: 'Label', icon: Type },
  { type: 'wall', label: 'Wall', icon: Square },
]


// ── Main Component ─────────────────────────────

export default function FacilityMapPage() {
  const { facilityId: paramFacilityId } = useParams<{ facilityId: string }>()
  const { site } = useSiteContext()
  const [mode, setMode] = useState<Mode>('live')
  const [floorPlan, setFloorPlan] = useState<FloorPlanData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [zoom, setZoom] = useState(1)

  // Live data
  const [zones, setZones] = useState<Zone[]>([])
  const [compressors, setCompressors] = useState<Compressor[]>([])
  const [alerts, setAlerts] = useState<AlertT[]>([])

  // Edit state
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [dragging, setDragging] = useState<{ id: string; offsetX: number; offsetY: number } | null>(null)
  const [resizing, setResizing] = useState<{ id: string; startW: number; startH: number; startX: number; startY: number } | null>(null)
  const canvasRef = useRef<HTMLDivElement>(null)

  // Link dialog
  const [linkDialog, setLinkDialog] = useState<{ elementId: string; type: string } | null>(null)

  // Use route param first, fall back to site selector
  const facilityId = paramFacilityId || site?.id

  // ── Load floor plan + live data ───────────

  const loadFloorPlan = useCallback(async () => {
    if (!facilityId) return
    setLoading(true)
    try {
      const res = await api.getFloorPlan(facilityId)
      let plan = res.floor_plan

      // Auto-populate from existing zones/compressors if floor plan is empty
      if (plan.elements.length === 0) {
        const [zoneRes, compRes] = await Promise.all([
          api.listZones(facilityId).catch(() => ({ zones: [] })),
          api.listCompressors(facilityId).catch(() => ({ compressors: [] })),
        ])
        const autoElements: FloorPlanElement[] = []

        // Place zones on the canvas
        ;(zoneRes.zones || []).forEach((z, i) => {
          const col = i % 3
          const row = Math.floor(i / 3)
          autoElements.push({
            id: `auto_zone_${z.id}`,
            type: 'zone',
            x: z.position_x ?? (40 + col * 200),
            y: z.position_y ?? (40 + row * 160),
            width: z.width ?? 180,
            height: z.height ?? 130,
            label: z.name,
            ref_id: z.id,
            config: { color: ZONE_TYPE_COLORS[z.zone_type] || ZONE_TYPE_COLORS.default },
          })
        })

        // Place compressors below zones
        const compStartY = autoElements.length > 0
          ? Math.max(...autoElements.map(e => e.y + e.height)) + 40
          : 40
        ;(compRes.compressors || []).forEach((c, i) => {
          autoElements.push({
            id: `auto_comp_${c.id}`,
            type: 'compressor',
            x: 40 + i * 100,
            y: compStartY,
            width: 80,
            height: 80,
            label: c.name,
            ref_id: c.id,
            config: { color: '#3b82f6' },
          })
        })

        if (autoElements.length > 0) {
          plan = { ...plan, elements: autoElements }
          // Save the auto-generated layout
          api.saveFloorPlan(facilityId, plan).catch(() => {})
          toast.success(`Auto-placed ${zoneRes.zones?.length || 0} zones and ${compRes.compressors?.length || 0} compressors`)
        }
      }

      setFloorPlan(plan)
    } catch {
      setFloorPlan({
        canvas: { width: 900, height: 600, background: '#f8f9fa', grid_size: 20 },
        elements: [],
      })
    } finally {
      setLoading(false)
    }
  }, [facilityId])

  const loadLiveData = useCallback(async () => {
    if (!facilityId) return
    try {
      const [zoneRes, compRes, alertRes] = await Promise.all([
        api.listZones(facilityId),
        api.listCompressors(facilityId),
        api.listAlerts(facilityId, { state: 'active', limit: 50 }),
      ])
      setZones(zoneRes.zones || [])
      setCompressors(compRes.compressors || [])
      setAlerts(alertRes.alerts || [])
    } catch (e) {
      console.error('Live data fetch failed', e)
    }
  }, [facilityId])

  useEffect(() => {
    loadFloorPlan()
    loadLiveData()
  }, [loadFloorPlan, loadLiveData])

  // Poll live data
  useEffect(() => {
    if (mode !== 'live' || !facilityId) return
    const interval = setInterval(loadLiveData, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [mode, facilityId, loadLiveData])

  // ── Auto-save (debounced) ─────────────────
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hasEdited = useRef(false)

  useEffect(() => {
    // Only auto-save in edit mode after user has made changes
    if (mode !== 'edit' || !facilityId || !floorPlan || !hasEdited.current) return
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current)
    autoSaveTimer.current = setTimeout(async () => {
      try {
        await api.saveFloorPlan(facilityId, floorPlan)
      } catch {
        // Silent — manual save is still available
      }
    }, 1500) // 1.5s debounce
    return () => { if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current) }
  }, [floorPlan, mode, facilityId])

  // Save on navigate away / mode switch
  useEffect(() => {
    return () => {
      if (hasEdited.current && facilityId && floorPlan) {
        api.saveFloorPlan(facilityId, floorPlan).catch(() => {})
      }
    }
  }, [facilityId]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Save ──────────────────────────────────

  async function handleSave() {
    if (!facilityId || !floorPlan) return
    setSaving(true)
    try {
      await api.saveFloorPlan(facilityId, floorPlan)
      toast.success('Floor plan saved')
    } catch {
      toast.error('Failed to save')
    } finally {
      setSaving(false)
    }
  }

  // ── Element CRUD ──────────────────────────

  function markEdited() { hasEdited.current = true }

  async function addElement(type: FloorPlanElement['type']) {
    if (!floorPlan || !facilityId) return
    markEdited()
    const id = `el_${Date.now()}`
    const defaults: Record<string, Partial<FloorPlanElement>> = {
      zone: { width: 160, height: 120, label: 'New Zone', config: { color: ZONE_TYPE_COLORS.cooler } },
      compressor: { width: 80, height: 80, label: 'Compressor', config: { color: '#3b82f6' } },
      equipment: { width: 60, height: 60, label: 'Equipment', config: { color: '#8b5cf6' } },
      label: { width: 120, height: 30, label: 'Label', config: { fontSize: 14 } },
      wall: { width: 200, height: 8, label: '', config: { color: '#374151' } },
    }
    const d = defaults[type] || {}
    let refId: string | undefined

    // Create real database record for zones
    if (type === 'zone') {
      try {
        const zone = await api.createZone(facilityId, {
          name: `Zone ${floorPlan.elements.filter(e => e.type === 'zone').length + 1}`,
          zone_type: 'cooler',
          temp_setpoint: 35,
          temp_unit: 'degF',
          temp_tolerance: 3,
          temp_alarm_high: 41,
          temp_alarm_low: 28,
        })
        refId = zone.id
        d.label = zone.name
        toast.success('Zone created')
        loadLiveData() // Refresh zone list
      } catch {
        toast.error('Failed to create zone')
        return
      }
    }

    const newEl: FloorPlanElement = {
      id, type,
      x: 40 + Math.random() * 200, y: 40 + Math.random() * 200,
      width: d.width || 100, height: d.height || 100,
      label: d.label || type, ref_id: refId, config: d.config,
    }
    setFloorPlan({ ...floorPlan, elements: [...floorPlan.elements, newEl] })
    setSelectedId(id)
  }

  function updateElement(id: string, updates: Partial<FloorPlanElement>) {
    if (!floorPlan) return
    markEdited()
    setFloorPlan({
      ...floorPlan,
      elements: floorPlan.elements.map(el => el.id === id ? { ...el, ...updates } : el),
    })
  }

  function removeElement(id: string) {
    if (!floorPlan) return
    markEdited()
    setFloorPlan({ ...floorPlan, elements: floorPlan.elements.filter(el => el.id !== id) })
    if (selectedId === id) setSelectedId(null)
  }

  function linkElement(elementId: string, refId: string) {
    updateElement(elementId, { ref_id: refId })
    setLinkDialog(null)
  }

  // ── Drag handlers ─────────────────────────

  function getCanvasCoords(e: React.MouseEvent): { cx: number; cy: number } {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return { cx: 0, cy: 0 }
    return { cx: (e.clientX - rect.left) / zoom, cy: (e.clientY - rect.top) / zoom }
  }

  function handleCanvasMouseDown(e: React.MouseEvent) {
    if (mode !== 'edit') return
    // Click on empty space deselects
    if ((e.target as HTMLElement).dataset.canvas) {
      setSelectedId(null)
    }
  }

  function handleElementMouseDown(e: React.MouseEvent, el: FloorPlanElement) {
    if (mode !== 'edit') return
    e.stopPropagation()
    setSelectedId(el.id)
    const { cx, cy } = getCanvasCoords(e)
    setDragging({ id: el.id, offsetX: cx - el.x, offsetY: cy - el.y })
  }

  function handleResizeMouseDown(e: React.MouseEvent, el: FloorPlanElement) {
    if (mode !== 'edit') return
    e.stopPropagation()
    setResizing({ id: el.id, startW: el.width, startH: el.height, startX: e.clientX, startY: e.clientY })
  }

  function handleCanvasMouseMove(e: React.MouseEvent) {
    if (dragging && floorPlan) {
      const { cx, cy } = getCanvasCoords(e)
      const grid = floorPlan.canvas.grid_size
      const x = Math.round((cx - dragging.offsetX) / grid) * grid
      const y = Math.round((cy - dragging.offsetY) / grid) * grid
      updateElement(dragging.id, { x: Math.max(0, x), y: Math.max(0, y) })
    }
    if (resizing && floorPlan) {
      const dx = e.clientX - resizing.startX
      const dy = e.clientY - resizing.startY
      const grid = floorPlan.canvas.grid_size
      const w = Math.max(grid * 2, Math.round((resizing.startW + dx / zoom) / grid) * grid)
      const h = Math.max(grid * 2, Math.round((resizing.startH + dy / zoom) / grid) * grid)
      updateElement(resizing.id, { width: w, height: h })
    }
  }

  function handleCanvasMouseUp() {
    setDragging(null)
    setResizing(null)
  }

  // ── Resolve live data for an element ──────

  function getZoneForElement(el: FloorPlanElement): Zone | undefined {
    if (!el.ref_id) return undefined
    return zones.find(z => z.id === el.ref_id)
  }

  function getCompressorForElement(el: FloorPlanElement): Compressor | undefined {
    if (!el.ref_id) return undefined
    return compressors.find(c => c.id === el.ref_id)
  }

  function getAlertsForRef(refId: string | undefined): AlertT[] {
    if (!refId) return []
    return alerts.filter(a => a.zone_id === refId || a.equipment_id === refId)
  }

  // ── No facility selected ──────────────────

  if (!facilityId) {
    return (
      <div className="empty-state" style={{ padding: 40 }}>
        <div className="empty-icon"><MapPin size={24} /></div>
        <h3>No Facility Selected</h3>
        <p>Choose a facility from the selector to view its floor plan.</p>
      </div>
    )
  }

  const selectedEl = floorPlan?.elements.find(el => el.id === selectedId)

  return (
    <div>
      {/* Mode toggle bar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <button
          className={mode === 'live' ? 'btn-primary' : 'btn-secondary'}
          onClick={() => setMode('live')}
          style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}
        >
          <Eye size={14} /> Live
        </button>
        <button
          className={mode === 'edit' ? 'btn-primary' : 'btn-secondary'}
          onClick={() => setMode('edit')}
          style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}
        >
          <Edit3 size={14} /> Edit Layout
        </button>
        {mode === 'edit' && (
          <button className="btn-primary" onClick={handleSave} disabled={saving}
            style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <Save size={14} /> {saving ? 'Saving...' : 'Save'}
          </button>
        )}
        {mode === 'live' && (
          <button className="btn-secondary" onClick={loadLiveData}
            style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
            <RefreshCw size={14} /> Refresh
          </button>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-tertiary)' }}>
          {mode === 'edit' ? 'Drag to position, resize handles on corners' : 'Auto-refreshes every 8s'}
        </span>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <Loader2 size={24} className="spin" />
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 16 }}>
          {/* Palette (edit mode) */}
          {mode === 'edit' && (
            <div style={{ width: 180, flexShrink: 0 }}>
              <div className="card">
                <div className="card-header" style={{ fontSize: 12 }}>Add Element</div>
                <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 10 }}>
                  {ELEMENT_PALETTE.map(p => {
                    const Icon = p.icon
                    return (
                      <button key={p.type} className="btn-secondary"
                        onClick={() => addElement(p.type)}
                        style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, justifyContent: 'flex-start' }}>
                        <Icon size={14} /> {p.label}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* Properties panel */}
              {selectedEl && (
                <div className="card" style={{ marginTop: 12 }}>
                  <div className="card-header" style={{ fontSize: 12 }}>Properties</div>
                  <div className="card-body" style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div>
                      <label className="form-label" style={{ fontSize: 11 }}>Label</label>
                      <input type="text" className="form-input" value={selectedEl.label}
                        onChange={e => updateElement(selectedEl.id, { label: e.target.value })}
                        style={{ fontSize: 12, padding: '4px 8px' }} />
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <div style={{ flex: 1 }}>
                        <label className="form-label" style={{ fontSize: 11 }}>W</label>
                        <input type="number" className="form-input" value={selectedEl.width}
                          onChange={e => updateElement(selectedEl.id, { width: Number(e.target.value) })}
                          style={{ fontSize: 12, padding: '4px 8px' }} />
                      </div>
                      <div style={{ flex: 1 }}>
                        <label className="form-label" style={{ fontSize: 11 }}>H</label>
                        <input type="number" className="form-input" value={selectedEl.height}
                          onChange={e => updateElement(selectedEl.id, { height: Number(e.target.value) })}
                          style={{ fontSize: 12, padding: '4px 8px' }} />
                      </div>
                    </div>

                    {/* Link to data source */}
                    {(selectedEl.type === 'zone' || selectedEl.type === 'compressor' || selectedEl.type === 'equipment') && (
                      <div>
                        <label className="form-label" style={{ fontSize: 11 }}>Link To</label>
                        <button className="btn-secondary" style={{ width: '100%', fontSize: 11 }}
                          onClick={() => setLinkDialog({ elementId: selectedEl.id, type: selectedEl.type })}>
                          {selectedEl.ref_id ? 'Change Link...' : 'Link to data...'}
                        </button>
                        {selectedEl.ref_id && (
                          <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 4 }}>
                            Linked: {selectedEl.ref_id.slice(0, 8)}...
                          </div>
                        )}
                      </div>
                    )}

                    <button className="btn-secondary" onClick={() => removeElement(selectedEl.id)}
                      style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>
                      <Trash2 size={12} /> Remove
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Canvas */}
          <div className="card" style={{ flex: 1, overflow: 'auto' }}>
            <div className="card-body" style={{ padding: 0, position: 'relative' }}>
              {/* Zoom controls */}
              <div style={{
                position: 'absolute', top: 8, right: 8, zIndex: 20,
                display: 'flex', gap: 4, background: 'var(--bg-primary)',
                padding: 4, borderRadius: 6, border: '1px solid var(--border-subtle)',
              }}>
                <button className="btn-secondary" onClick={() => setZoom(Math.min(2, zoom + 0.15))} style={{ padding: '4px 6px' }}><ZoomIn size={14} /></button>
                <button className="btn-secondary" onClick={() => setZoom(Math.max(0.4, zoom - 0.15))} style={{ padding: '4px 6px' }}><ZoomOut size={14} /></button>
                <button className="btn-secondary" onClick={() => setZoom(1)} style={{ padding: '4px 6px' }}><Maximize2 size={14} /></button>
              </div>

              <div
                ref={canvasRef}
                data-canvas="true"
                onMouseDown={handleCanvasMouseDown}
                onMouseMove={handleCanvasMouseMove}
                onMouseUp={handleCanvasMouseUp}
                onMouseLeave={handleCanvasMouseUp}
                style={{
                  width: (floorPlan?.canvas.width || 900) * zoom,
                  height: (floorPlan?.canvas.height || 600) * zoom,
                  position: 'relative',
                  background: floorPlan?.canvas.background || '#f8f9fa',
                  backgroundImage: mode === 'edit'
                    ? `linear-gradient(var(--border-subtle) 1px, transparent 1px), linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px)`
                    : 'none',
                  backgroundSize: mode === 'edit' ? `${(floorPlan?.canvas.grid_size || 20) * zoom}px ${(floorPlan?.canvas.grid_size || 20) * zoom}px` : 'auto',
                  cursor: dragging ? 'grabbing' : mode === 'edit' ? 'crosshair' : 'default',
                  minHeight: 500,
                  transformOrigin: 'top left',
                }}
              >
                {floorPlan?.elements.map(el => {
                  const isSelected = selectedId === el.id && mode === 'edit'
                  const zone = el.type === 'zone' ? getZoneForElement(el) : undefined
                  const comp = el.type === 'compressor' ? getCompressorForElement(el) : undefined
                  const elAlerts = getAlertsForRef(el.ref_id)
                  const hasAlert = elAlerts.length > 0

                  return (
                    <div
                      key={el.id}
                      onMouseDown={e => handleElementMouseDown(e, el)}
                      style={{
                        position: 'absolute',
                        left: el.x * zoom, top: el.y * zoom,
                        width: el.width * zoom, height: el.height * zoom,
                        cursor: mode === 'edit' ? (dragging?.id === el.id ? 'grabbing' : 'grab') : 'default',
                        zIndex: isSelected ? 10 : 1,
                      }}
                    >
                      {/* Zone rendering */}
                      {el.type === 'zone' && (
                        <div style={{
                          width: '100%', height: '100%',
                          borderRadius: 6 * zoom,
                          border: `${isSelected ? 3 : 2}px solid ${isSelected ? 'var(--accent)' : (zone ? tempColor(zone.current_temp, zone.temp_setpoint, zone.temp_alarm_high, zone.temp_alarm_low) : (el.config?.color as string || '#6b7280'))}`,
                          background: `color-mix(in srgb, ${zone ? tempColor(zone.current_temp, zone.temp_setpoint, zone.temp_alarm_high, zone.temp_alarm_low) : (el.config?.color as string || '#6b7280')} 8%, transparent)`,
                          display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                          overflow: 'hidden', padding: 4 * zoom,
                        }}>
                          <div style={{ fontSize: 11 * zoom, fontWeight: 600, color: 'var(--text-primary)' }}>
                            {zone?.name || el.label}
                          </div>
                          {zone && mode === 'live' && (
                            <>
                              <div style={{
                                fontSize: 22 * zoom, fontWeight: 700, fontFamily: 'monospace', lineHeight: 1.1,
                                color: tempColor(zone.current_temp, zone.temp_setpoint, zone.temp_alarm_high, zone.temp_alarm_low),
                              }}>
                                {zone.current_temp != null ? `${zone.current_temp.toFixed(1)}°` : '—'}
                              </div>
                              <div style={{ fontSize: 9 * zoom, color: 'var(--text-tertiary)' }}>
                                Set: {zone.temp_setpoint ?? '—'}° {zone.temp_unit === 'degC' ? 'C' : 'F'}
                              </div>
                              {zone.door_open && (
                                <div style={{
                                  fontSize: 8 * zoom, padding: `${1 * zoom}px ${4 * zoom}px`,
                                  background: '#f59e0b33', color: '#f59e0b', borderRadius: 4 * zoom,
                                  fontWeight: 700, marginTop: 2 * zoom,
                                }}>
                                  DOOR OPEN
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      )}

                      {/* Compressor rendering */}
                      {el.type === 'compressor' && (
                        <div style={{
                          width: '100%', height: '100%',
                          borderRadius: 8 * zoom,
                          border: `${isSelected ? 3 : 2}px solid ${isSelected ? 'var(--accent)' : (comp ? (STATE_COLORS[comp.state] || '#6b7280') : '#3b82f6')}`,
                          background: `color-mix(in srgb, ${comp ? (STATE_COLORS[comp.state] || '#6b7280') : '#3b82f6'} 10%, var(--bg-primary))`,
                          display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                          padding: 4 * zoom,
                        }}>
                          <Cpu size={16 * zoom} style={{ color: comp ? STATE_COLORS[comp.state] || '#6b7280' : '#3b82f6', marginBottom: 2 * zoom }} />
                          <div style={{ fontSize: 10 * zoom, fontWeight: 600, textAlign: 'center' }}>
                            {comp?.name || el.label}
                          </div>
                          {comp && mode === 'live' && (
                            <>
                              <div style={{
                                fontSize: 8 * zoom, padding: `${1 * zoom}px ${4 * zoom}px`, marginTop: 2 * zoom,
                                borderRadius: 4 * zoom, fontWeight: 700, textTransform: 'uppercase',
                                background: `color-mix(in srgb, ${STATE_COLORS[comp.state] || '#6b7280'} 20%, transparent)`,
                                color: STATE_COLORS[comp.state] || '#6b7280',
                              }}>
                                {comp.state}
                              </div>
                              {comp.hp && (
                                <div style={{ fontSize: 9 * zoom, color: 'var(--text-tertiary)', marginTop: 1 * zoom }}>
                                  {comp.hp} HP
                                </div>
                              )}
                              {comp.health_score != null && (
                                <div style={{
                                  fontSize: 9 * zoom, fontWeight: 600, marginTop: 1 * zoom,
                                  color: comp.health_score > 80 ? '#10b981' : comp.health_score > 50 ? '#f59e0b' : '#ef4444',
                                }}>
                                  Health: {comp.health_score}%
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      )}

                      {/* Equipment rendering */}
                      {el.type === 'equipment' && (
                        <div style={{
                          width: '100%', height: '100%',
                          borderRadius: 6 * zoom,
                          border: `${isSelected ? 3 : 2}px solid ${isSelected ? 'var(--accent)' : (el.config?.color as string || '#8b5cf6')}`,
                          background: `color-mix(in srgb, ${el.config?.color as string || '#8b5cf6'} 8%, var(--bg-primary))`,
                          display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center',
                          padding: 4 * zoom,
                        }}>
                          <Zap size={14 * zoom} style={{ color: el.config?.color as string || '#8b5cf6' }} />
                          <div style={{ fontSize: 10 * zoom, fontWeight: 600, textAlign: 'center', marginTop: 2 * zoom }}>
                            {el.label}
                          </div>
                        </div>
                      )}

                      {/* Label rendering */}
                      {el.type === 'label' && (
                        <div style={{
                          width: '100%', height: '100%',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: ((el.config?.fontSize as number) || 14) * zoom,
                          fontWeight: 600, color: 'var(--text-primary)',
                          border: isSelected ? '2px dashed var(--accent)' : 'none',
                        }}>
                          {el.label}
                        </div>
                      )}

                      {/* Wall rendering */}
                      {el.type === 'wall' && (
                        <div style={{
                          width: '100%', height: '100%',
                          background: el.config?.color as string || '#374151',
                          borderRadius: 2 * zoom,
                          border: isSelected ? '2px dashed var(--accent)' : 'none',
                        }} />
                      )}

                      {/* Alert badge */}
                      {hasAlert && mode === 'live' && (
                        <div style={{
                          position: 'absolute', top: -6 * zoom, right: -6 * zoom,
                          width: 18 * zoom, height: 18 * zoom, borderRadius: '50%',
                          background: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          animation: 'pulse 2s infinite', zIndex: 5,
                        }}>
                          <AlertTriangle size={10 * zoom} style={{ color: '#fff' }} />
                        </div>
                      )}

                      {/* Resize handle (edit mode) */}
                      {isSelected && mode === 'edit' && (
                        <div
                          onMouseDown={e => handleResizeMouseDown(e, el)}
                          style={{
                            position: 'absolute', bottom: -4, right: -4,
                            width: 10, height: 10, borderRadius: 2,
                            background: 'var(--accent)', cursor: 'se-resize',
                            border: '1px solid #fff',
                          }}
                        />
                      )}
                    </div>
                  )
                })}

                {/* Empty state */}
                {floorPlan?.elements.length === 0 && (
                  <div style={{
                    position: 'absolute', inset: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexDirection: 'column', gap: 12, color: 'var(--text-tertiary)',
                  }}>
                    <MapPin size={32} />
                    <div style={{ fontSize: 14, fontWeight: 600 }}>No floor plan configured</div>
                    <div style={{ fontSize: 12 }}>
                      {mode === 'edit'
                        ? 'Use the palette on the left to add zones and equipment'
                        : 'Switch to Edit Layout mode to build your floor plan'}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Live data sidebar */}
          {mode === 'live' && (zones.length > 0 || compressors.length > 0) && (
            <div style={{ width: 220, flexShrink: 0 }}>
              {/* Zone summary */}
              {zones.length > 0 && (
                <div className="card" style={{ marginBottom: 12 }}>
                  <div className="card-header" style={{ fontSize: 12 }}>Zones ({zones.length})</div>
                  <div className="card-body" style={{ padding: 0 }}>
                    {zones.map(z => (
                      <div key={z.id} style={{
                        padding: '8px 12px', borderBottom: '1px solid var(--border-subtle)',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      }}>
                        <div>
                          <div style={{ fontSize: 12, fontWeight: 600 }}>{z.name}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{z.zone_type}</div>
                        </div>
                        <div style={{
                          fontSize: 14, fontWeight: 700, fontFamily: 'monospace',
                          color: tempColor(z.current_temp, z.temp_setpoint, z.temp_alarm_high, z.temp_alarm_low),
                        }}>
                          {z.current_temp != null ? `${z.current_temp.toFixed(1)}°` : '—'}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Compressor summary */}
              {compressors.length > 0 && (
                <div className="card">
                  <div className="card-header" style={{ fontSize: 12 }}>Compressors ({compressors.length})</div>
                  <div className="card-body" style={{ padding: 0 }}>
                    {compressors.map(c => (
                      <div key={c.id} style={{
                        padding: '8px 12px', borderBottom: '1px solid var(--border-subtle)',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      }}>
                        <div>
                          <div style={{ fontSize: 12, fontWeight: 600 }}>{c.name}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{c.hp ? `${c.hp} HP` : c.compressor_type}</div>
                        </div>
                        <div style={{
                          fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                          padding: '2px 6px', borderRadius: 6,
                          color: STATE_COLORS[c.state] || '#6b7280',
                          background: `color-mix(in srgb, ${STATE_COLORS[c.state] || '#6b7280'} 15%, transparent)`,
                        }}>
                          {c.state}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Active alerts */}
              {alerts.length > 0 && (
                <div className="card" style={{ marginTop: 12 }}>
                  <div className="card-header" style={{ fontSize: 12, color: 'var(--danger)' }}>
                    Active Alerts ({alerts.length})
                  </div>
                  <div className="card-body" style={{ padding: 0 }}>
                    {alerts.slice(0, 5).map(a => (
                      <div key={a.id} style={{
                        padding: '6px 12px', borderBottom: '1px solid var(--border-subtle)',
                        fontSize: 11,
                      }}>
                        <div style={{ fontWeight: 600, color: a.severity === 'critical' ? 'var(--danger)' : 'var(--warning)' }}>
                          {a.severity.toUpperCase()}
                        </div>
                        <div style={{ color: 'var(--text-secondary)' }}>{a.title || a.category}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Link dialog */}
      {linkDialog && (
        <div className="modal-overlay" onClick={() => setLinkDialog(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 400 }}>
            <div className="modal-header">
              <h3 style={{ margin: 0, fontSize: 16 }}>Link to {linkDialog.type}</h3>
            </div>
            <div className="modal-body" style={{ maxHeight: 300, overflow: 'auto' }}>
              {linkDialog.type === 'zone' && zones.map(z => (
                <button key={z.id} className="btn-secondary" style={{
                  width: '100%', textAlign: 'left', marginBottom: 6, fontSize: 12,
                  display: 'flex', justifyContent: 'space-between',
                }}
                  onClick={() => linkElement(linkDialog.elementId, z.id)}>
                  <span>{z.name}</span>
                  <span style={{ color: 'var(--text-tertiary)' }}>{z.zone_type}</span>
                </button>
              ))}
              {linkDialog.type === 'compressor' && compressors.map(c => (
                <button key={c.id} className="btn-secondary" style={{
                  width: '100%', textAlign: 'left', marginBottom: 6, fontSize: 12,
                  display: 'flex', justifyContent: 'space-between',
                }}
                  onClick={() => linkElement(linkDialog.elementId, c.id)}>
                  <span>{c.name}</span>
                  <span style={{ color: 'var(--text-tertiary)' }}>{c.compressor_type}</span>
                </button>
              ))}
              {linkDialog.type === 'equipment' && (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', padding: 12 }}>
                  Equipment linking uses alert matching. Add the equipment via the Zones page first.
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setLinkDialog(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0% { box-shadow: 0 0 0 0 rgba(239,68,68,0.6); }
          70% { box-shadow: 0 0 0 8px rgba(239,68,68,0); }
          100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); }
        }
      `}</style>
    </div>
  )
}
