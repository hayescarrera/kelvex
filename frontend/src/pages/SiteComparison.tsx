import { useState, useEffect } from 'react'
import { Check, BarChart3 } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { useSiteContext } from '../contexts/SiteContext'
import { api } from '../lib/api'

const CHART_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#7c3aed', '#06b6d4']

const months = ['Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar']

const ChartTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="card" style={{ padding: '0.5rem 0.75rem', minWidth: 160 }}>
      <p style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color, margin: '0.125rem 0', fontSize: '0.85rem' }}>
          {entry.name}: {entry.value} kW
        </p>
      ))}
    </div>
  )
}

interface FacilityData {
  id: string
  name: string
  equipmentCount: number
  billCount: number
  avgMonthlyCost: number
  avgPeakKw: number
  demandPct: number
  peakByMonth: Record<string, number>
}

export default function SiteComparison() {
  const { facilities } = useSiteContext()
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [facilityData, setFacilityData] = useState<Record<string, FacilityData>>({})
  const [loading, setLoading] = useState(false)

  const toggleFacility = (id: string) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  useEffect(() => {
    if (selectedIds.length < 2) return

    const toFetch = selectedIds.filter(id => !facilityData[id])
    if (toFetch.length === 0) return

    setLoading(true)
    Promise.all(
      toFetch.map(async (id) => {
        const [billsResp, equipResp] = await Promise.all([
          api.listBills(id).catch(() => ({ bills: [], total: 0 })),
          api.listEquipment(id).catch(() => ({ equipment: [], total: 0 })),
        ])

        const billArr = billsResp.bills ?? []
        const equipArr = equipResp.equipment ?? []

        const totalCost = billArr.reduce((s: number, b: any) => s + (b.total_cost ?? 0), 0)
        const avgMonthlyCost = billArr.length ? totalCost / billArr.length : 0

        const totalPeak = billArr.reduce((s: number, b: any) => s + (b.peak_kw ?? 0), 0)
        const avgPeakKw = billArr.length ? totalPeak / billArr.length : 0

        const totalDemand = billArr.reduce((s: number, b: any) => s + (b.demand_charge ?? 0), 0)
        const demandPct = totalCost > 0 ? (totalDemand / totalCost) * 100 : 0

        const peakByMonth: Record<string, number> = {}
        billArr.forEach((b: any) => {
          if (b.period_start || b.period) {
            const d = new Date(b.period_start ?? b.period)
            const label = d.toLocaleDateString('en-US', { month: 'short' })
            peakByMonth[label] = b.peak_kw ?? 0
          }
        })

        return {
          id,
          name: facilities?.find((f: any) => f.id === id)?.name ?? id,
          equipmentCount: equipArr.length,
          billCount: billArr.length,
          avgMonthlyCost,
          avgPeakKw,
          demandPct,
          peakByMonth,
        } as FacilityData
      })
    )
      .then(results => {
        setFacilityData(prev => {
          const next = { ...prev }
          results.forEach(r => { next[r.id] = r })
          return next
        })
      })
      .finally(() => setLoading(false))
  }, [selectedIds]) // eslint-disable-line react-hooks/exhaustive-deps

  const selectedData = selectedIds
    .filter(id => facilityData[id])
    .map(id => facilityData[id])

  const chartData = months.map(month => {
    const entry: Record<string, any> = { month }
    selectedData.forEach(fd => {
      entry[fd.name] = fd.peakByMonth[month] ?? null
    })
    return entry
  })

  return (
    <div className="page-container">
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ margin: 0 }}>Site Comparison</h1>
        <p className="text-muted" style={{ margin: '0.25rem 0 0' }}>Compare energy metrics across facilities</p>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card-header">
          <span>Select Facilities</span>
          <span className="text-muted" style={{ fontSize: '0.82rem' }}>Choose 2 or more to compare</span>
        </div>
        <div className="card-body">
          {!facilities || facilities.length === 0 ? (
            <p className="text-muted">No facilities available</p>
          ) : (
            <div className="compare-site-grid">
              {facilities.map((facility: any) => {
                const selected = selectedIds.includes(facility.id)
                return (
                  <button
                    key={facility.id}
                    className={`compare-site-btn${selected ? ' selected' : ''}`}
                    onClick={() => toggleFacility(facility.id)}
                  >
                    <span className="compare-site-check">
                      {selected && <Check size={12} />}
                    </span>
                    <span>{facility.name}</span>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {selectedIds.length < 2 ? (
        <div className="card">
          <div className="card-body">
            <div className="empty-state">
              <div className="empty-icon">
                <BarChart3 size={32} />
              </div>
              <p>Select at least 2 facilities to compare</p>
            </div>
          </div>
        </div>
      ) : (
        <>
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="card-header">
              <span>Summary</span>
            </div>
            <div className="card-body">
              {loading ? (
                <p className="text-muted">Loading data...</p>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Facility</th>
                      <th>Equipment</th>
                      <th>Total Bills</th>
                      <th>Avg Monthly Cost</th>
                      <th>Avg Peak Demand</th>
                      <th>Demand % of Bill</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedIds.map((id, idx) => {
                      const fd = facilityData[id]
                      const name = facilities?.find((f: any) => f.id === id)?.name ?? id
                      return (
                        <tr key={id}>
                          <td className="cell-primary" style={{ color: CHART_COLORS[idx % CHART_COLORS.length] }}>
                            {name}
                          </td>
                          <td>{fd ? fd.equipmentCount : '—'}</td>
                          <td>{fd ? fd.billCount : '—'}</td>
                          <td>
                            {fd
                              ? `$${fd.avgMonthlyCost.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
                              : '—'}
                          </td>
                          <td>{fd ? `${fd.avgPeakKw.toFixed(1)} kW` : '—'}</td>
                          <td>{fd ? `${fd.demandPct.toFixed(1)}%` : '—'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-header">
              <span>Peak Demand by Month</span>
            </div>
            <div className="card-body">
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
                  <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} unit=" kW" />
                  <Tooltip content={<ChartTooltip />} />
                  {selectedData.map((fd, idx) => (
                    <Line
                      key={fd.id}
                      type="monotone"
                      dataKey={fd.name}
                      stroke={CHART_COLORS[idx % CHART_COLORS.length]}
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
