import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { Gauge, Loader2 } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import { useSiteContext } from '../contexts/SiteContext'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

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

export default function DemandPage() {
  const { facilities } = useSiteContext()

  // Fetch bills for all facilities
  const { data: allBillsData, isLoading } = useQuery({
    queryKey: ['bills', 'global-demand'],
    queryFn: async () => {
      const results = await Promise.all(
        facilities.map(f => api.listBills(f.id).catch(() => ({ bills: [], total: 0 })))
      )
      return results.flatMap(r => r.bills)
    },
    enabled: facilities.length > 0,
  })

  const allBills = allBillsData ?? []

  // Aggregate by month across facilities
  const monthlyMap: Record<string, { peak: number; count: number; totalKwh: number }> = {}
  for (const bill of allBills) {
    if (!bill.peak_demand_kw) continue
    const start = new Date(bill.period_start)
    const key = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}`
    if (!monthlyMap[key]) monthlyMap[key] = { peak: 0, count: 0, totalKwh: 0 }
    monthlyMap[key].peak = Math.max(monthlyMap[key].peak, Number(bill.peak_demand_kw))
    monthlyMap[key].totalKwh += Number(bill.total_kwh || 0)
    monthlyMap[key].count++
  }

  const chartData = Object.entries(monthlyMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-12)
    .map(([key, val]) => {
      const [y, m] = key.split('-')
      const month = new Date(Number(y), Number(m) - 1).toLocaleString('default', { month: 'short' })
      return {
        month,
        peak: Math.round(val.peak),
        avg: Math.round(val.totalKwh / 730 / val.count), // approx avg kW
      }
    })

  const maxPeak = chartData.length > 0 ? Math.max(...chartData.map(d => d.peak)) : 0
  const avgPeak = chartData.length > 0 ? Math.round(chartData.reduce((s, d) => s + d.peak, 0) / chartData.length) : 0

  return (
    <div className="page-container">
      <PageHeader title="Demand Analysis" subtitle="Portfolio-wide peak demand trends" />

      <div className="stat-grid stagger" style={{ marginTop: 20, marginBottom: 20 }}>
        <StatCard icon={<Gauge size={18} />} color="var(--danger)" value={maxPeak ? `${maxPeak} kW` : '--'} label="Peak Demand" />
        <StatCard icon={<Gauge size={18} />} color="var(--accent)" value={avgPeak ? `${avgPeak} kW` : '--'} label="Avg Peak" />
        <StatCard icon={<Gauge size={18} />} color="var(--success)" value={String(facilities.length)} label="Facilities" />
        <StatCard icon={<Gauge size={18} />} color="var(--warning)" value={String(allBills.length)} label="Bills Analyzed" />
      </div>

      <div className="card">
        <div className="card-header"><h3>Peak Demand by Month</h3></div>
        <div className="card-body">
          {isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
              <Loader2 size={24} className="spin" />
            </div>
          ) : chartData.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon"><Gauge size={32} /></div>
              <h3>No demand data</h3>
              <p>Upload utility bills to your facilities to see portfolio-wide demand trends.</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={340}>
              <AreaChart data={chartData} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="peakGradPortfolio" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="avgGradPortfolio" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-accent, #3b82f6)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="var(--color-accent, #3b82f6)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
                <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} unit=" kW" />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="peak" name="Peak" stroke="#ef4444" strokeWidth={2} fill="url(#peakGradPortfolio)" />
                <Area type="monotone" dataKey="avg" name="Avg" stroke="var(--color-accent, #3b82f6)" strokeWidth={2} fill="url(#avgGradPortfolio)" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  )
}
