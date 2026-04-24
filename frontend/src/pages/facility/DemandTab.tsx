import { useParams } from 'react-router-dom'
import { Gauge } from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useAnalyses } from '../../hooks/useBills'
import { useBills } from '../../hooks/useBills'

const ChartTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="card" style={{ padding: '0.5rem 0.75rem', minWidth: 140 }}>
      <p style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{label}</p>
      {payload.map((entry: any) => (
        <p key={entry.dataKey} style={{ color: entry.color, margin: '0.125rem 0', fontSize: '0.85rem' }}>
          {entry.name}: {entry.value} kW
        </p>
      ))}
    </div>
  )
}

export default function DemandTab() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const { data: billData } = useBills(facilityId!)
  const { data: analysisData } = useAnalyses(facilityId!)

  const bills = billData?.bills ?? []
  const analyses = analysisData?.analyses ?? []

  // Build demand data from bills (peak_demand_kw)
  const demandFromBills = bills
    .filter(b => b.peak_demand_kw)
    .slice(0, 12)
    .reverse()
    .map(b => {
      const start = new Date(b.period_start)
      const month = start.toLocaleString('default', { month: 'short' })
      return {
        month,
        peak: Math.round(Number(b.peak_demand_kw || 0)),
        avg: Math.round(Number(b.total_kwh || 0) / 730), // approx avg kW from kWh
      }
    })

  // Supplement with analysis data if available
  const demandFromAnalyses = analyses
    .slice(0, 12)
    .reverse()
    .map((a: any) => ({
      month: new Date(a.created_at).toLocaleString('default', { month: 'short' }),
      peak: Math.round(a.peak_demand_kw || 0),
      avg: Math.round(a.avg_demand_kw || 0),
    }))

  const chartData = demandFromBills.length > 0 ? demandFromBills :
                    demandFromAnalyses.length > 0 ? demandFromAnalyses : []

  return (
    <div className="page-container">
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Gauge size={18} />
            <span>Peak Demand Trends</span>
          </div>
        </div>

        <div className="card-body">
          {chartData.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><Gauge size={32} /></div>
              <h3>No demand data available</h3>
              <p>Upload and analyze utility bills to see demand trends here.</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <AreaChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="peakGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="avgGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-accent, #3b82f6)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="var(--color-accent, #3b82f6)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
                <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} unit=" kW" />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="peak" name="Peak" stroke="#ef4444" strokeWidth={2} fill="url(#peakGrad)" />
                <Area type="monotone" dataKey="avg" name="Avg" stroke="var(--color-accent, #3b82f6)" strokeWidth={2} fill="url(#avgGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  )
}
