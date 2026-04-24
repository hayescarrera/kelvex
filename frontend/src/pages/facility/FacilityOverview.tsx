import { useParams } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { Cpu, Thermometer, Activity, AlertTriangle, DollarSign } from 'lucide-react'
import StatCard from '../../components/ui/StatCard'
import LoadingState from '../../components/ui/LoadingState'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { useFacility } from '../../hooks/useFacilities'
import { useEquipment } from '../../hooks/useEquipment'
import { useBills } from '../../hooks/useBills'
import { useZones } from '../../hooks/useZones'
import type { Equipment as EquipmentType, Zone } from '../../lib/api'

export default function FacilityOverview() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const { isLoading: fl } = useFacility(facilityId!)
  const { data: eqData, isLoading: el } = useEquipment(facilityId!)
  const { data: billData, isLoading: bl } = useBills(facilityId!)
  const { data: zoneData, isLoading: zl } = useZones(facilityId!)

  if (fl || el || bl || zl) return <LoadingState />

  const equipment = eqData?.equipment ?? []
  const bills = billData?.bills ?? []
  const zones = zoneData?.zones ?? []
  const latestBill = bills[0] ?? null

  // Build cost chart from real bills — most recent 7
  const costData = bills
    .slice(0, 7)
    .reverse()
    .map(b => {
      const start = new Date(b.period_start)
      const month = start.toLocaleString('default', { month: 'short' })
      return {
        month,
        demand: Math.round(Number(b.demand_charge || 0)),
        energy: Math.round(Number(b.energy_charge || 0)),
      }
    })

  const eqByType: Record<string, EquipmentType[]> = {}
  equipment.forEach(eq => {
    if (!eqByType[eq.equipment_type]) eqByType[eq.equipment_type] = []
    eqByType[eq.equipment_type].push(eq)
  })

  const ZONE_COLORS: Record<string, string> = {
    freezer: 'var(--freezer)', cooler: 'var(--cooler)', dock: 'var(--dock)',
    machine_room: 'var(--machine)', blast_freezer: 'var(--freezer)', staging: 'var(--accent)',
  }

  return (
    <div className="stack-lg">
      <div className="stat-grid-5 stagger">
        <StatCard icon={<Cpu size={18} />} color="var(--accent)" value={String(equipment.length)} label="Equipment" />
        <StatCard icon={<Thermometer size={18} />} color="var(--success)" value={String(zones.length)} label="Zones" />
        <StatCard icon={<Activity size={18} />} color="var(--warning)" value={equipment.length > 0 ? `${equipment.length}/${equipment.length}` : '--'} label="Online" />
        <StatCard icon={<AlertTriangle size={18} />} color="var(--danger)" value="0" label="Alerts" />
        <StatCard icon={<DollarSign size={18} />} color="#7c3aed" value={latestBill?.total_cost ? `$${Number(latestBill.total_cost).toLocaleString()}` : '--'} label="Last Bill" />
      </div>

      {zones.length > 0 && (
        <div className="card">
          <div className="card-header"><h3>Zone Status</h3><span className="card-subtitle">{zones.length} zones</span></div>
          <div className="card-body">
            <div className="zone-grid">
              {zones.map((zone: Zone) => {
                const color = ZONE_COLORS[zone.zone_type] ?? 'var(--text-muted)'
                return (
                  <div key={zone.id} className="zone-card" style={{ '--zone-color': color } as any}>
                    <div className="zone-card-header">
                      <span className="zone-card-name">{zone.name}</span>
                      <span className="zone-card-badge">{zone.state || 'normal'}</span>
                    </div>
                    <div className="zone-card-temp">
                      {zone.current_temp != null ? `${zone.current_temp}°${zone.temp_unit || 'F'}` : '—'}
                    </div>
                    <div className="zone-card-meta">
                      Setpoint: {zone.temp_setpoint != null ? `${zone.temp_setpoint}°${zone.temp_unit || 'F'}` : '—'}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="card-header"><h3>Equipment by Type</h3><span className="card-subtitle">{equipment.length} units</span></div>
          <div className="card-body">
            {Object.keys(eqByType).length === 0 ? (
              <p className="text-muted" style={{ padding: 20, textAlign: 'center' }}>No equipment registered yet</p>
            ) : Object.entries(eqByType).map(([type, items]) => (
              <div key={type} className="eq-type-row">
                <div className="eq-type-header">
                  <span className="eq-type-name">{type}</span>
                  <span className="eq-type-count">{items.length}</span>
                </div>
                <div className="eq-type-chips">
                  {items.slice(0, 4).map(eq => <span key={eq.id} className="chip">{eq.name}</span>)}
                  {items.length > 4 && <span className="chip chip-muted">+{items.length - 4} more</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h3>Recent Cost Trend</h3><span className="card-subtitle">Demand vs Energy</span></div>
          <div className="card-body" style={{ padding: '0 12px 12px' }}>
            {costData.length === 0 ? (
              <p className="text-muted" style={{ padding: 40, textAlign: 'center' }}>Upload bills to see cost trends</p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={costData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis dataKey="month" stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                  <YAxis stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="demand" fill="var(--danger)" radius={[3, 3, 0, 0]} name="Demand $" />
                  <Bar dataKey="energy" fill="var(--accent)" radius={[3, 3, 0, 0]} name="Energy $" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
