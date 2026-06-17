import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Zap, DollarSign, TrendingUp, TrendingDown, Thermometer,
  Upload, ChevronRight, FileText, AlertTriangle,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import ChartTooltip from '../components/ui/ChartTooltip'
import { useSiteContext } from '../contexts/SiteContext'
import { api } from '../lib/api'
import type { Bill } from '../lib/api'

interface CostSummary {
  totalSpend: number
  demandCharges: number
  energyCharges: number
  peakDemandKw: number
  billCount: number
  priorYearSpend: number
  monthlyCosts: { month: string; demand: number; energy: number; total: number }[]
}

function buildCostSummary(bills: Bill[]): CostSummary {
  const byMonth: Record<string, { month: string; demand: number; energy: number; total: number }> = {}
  let totalSpend = 0
  let demandCharges = 0
  let energyCharges = 0
  let peakDemandKw = 0
  let priorYearSpend = 0

  const now = new Date()
  const oneYearAgo = new Date(now.getFullYear() - 1, now.getMonth(), 1)
  const twoYearsAgo = new Date(now.getFullYear() - 2, now.getMonth(), 1)

  for (const bill of bills) {
    const start = new Date(bill.period_start)
    const key = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}`
    const label = start.toLocaleString('default', { month: 'short', year: '2-digit' })
    const total = Number(bill.total_cost || 0)
    const demand = Number(bill.demand_charge || 0)
    const energy = Number(bill.energy_charge || 0)
    const peak = Number(bill.peak_demand_kw || 0)

    if (!byMonth[key]) byMonth[key] = { month: label, demand: 0, energy: 0, total: 0 }
    byMonth[key].demand += demand
    byMonth[key].energy += energy
    byMonth[key].total += total

    if (start >= oneYearAgo) {
      totalSpend += total
      demandCharges += demand
      energyCharges += energy
      if (peak > peakDemandKw) peakDemandKw = peak
    } else if (start >= twoYearsAgo) {
      priorYearSpend += total
    }
  }

  const monthlyCosts = Object.entries(byMonth)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-13)
    .map(([, v]) => v)

  return { totalSpend, demandCharges, energyCharges, peakDemandKw, billCount: bills.length, priorYearSpend, monthlyCosts }
}

export default function FinanceHome() {
  const navigate = useNavigate()
  const { facilities } = useSiteContext()
  const [bills, setBills] = useState<Bill[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!facilities.length) { setLoaded(true); return }
    Promise.all(
      facilities.map(f => api.listBills(f.id).then(r => r.bills).catch(() => [] as Bill[]))
    ).then(results => {
      setBills(results.flat())
    }).finally(() => setLoaded(true))
  }, [facilities])

  if (!loaded) return <LoadingState />

  const summary = buildCostSummary(bills)
  const yoyDelta = summary.priorYearSpend > 0
    ? ((summary.totalSpend - summary.priorYearSpend) / summary.priorYearSpend) * 100
    : null
  const yoyUp = yoyDelta !== null && yoyDelta > 0

  const recentBills = [...bills]
    .sort((a, b) => new Date(b.period_start).getTime() - new Date(a.period_start).getTime())
    .slice(0, 6)

  return (
    <div className="page-container">
      <PageHeader
        title="Energy & Cost"
        subtitle="Portfolio utility spend, demand charges, and refrigerant cost exposure"
      >
        <button className="btn-secondary" onClick={() => navigate('/documents')}>
          <Upload size={14} /> Upload Bill
        </button>
        <button className="btn-primary" onClick={() => navigate('/reports')}>
          <FileText size={14} /> Export Report
        </button>
      </PageHeader>

      {/* KPI row */}
      <div className="stat-grid stagger">
        <StatCard
          icon={<DollarSign size={18} />}
          color="var(--text-primary)"
          value={summary.totalSpend > 0 ? `$${(summary.totalSpend / 1000).toFixed(0)}k` : '—'}
          label="Annual Spend (12 mo)"
        />
        <StatCard
          icon={yoyUp ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
          color={yoyDelta === null ? 'var(--text-muted)' : yoyUp ? 'var(--danger)' : 'var(--ok)'}
          value={yoyDelta !== null ? `${yoyUp ? '+' : ''}${yoyDelta.toFixed(1)}%` : '—'}
          label="vs Prior Year"
        />
        <StatCard
          icon={<Zap size={18} />}
          color="var(--warning)"
          value={summary.demandCharges > 0 ? `$${(summary.demandCharges / 1000).toFixed(0)}k` : '—'}
          label="Demand Charges"
        />
        <StatCard
          icon={<Thermometer size={18} />}
          color="var(--accent)"
          value={summary.peakDemandKw > 0 ? `${summary.peakDemandKw.toFixed(0)} kW` : '—'}
          label="Peak Demand"
        />
      </div>

      <div className="dashboard-grid">

        {/* Monthly cost trend */}
        <div className="card" style={{ gridColumn: 'span 2' }}>
          <div className="card-header">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <DollarSign size={15} /> Monthly Utility Spend
            </h3>
          </div>
          <div className="card-body">
            {summary.monthlyCosts.length === 0 ? (
              <EmptyState
                icon={<Upload size={24} />}
                title="No bill data"
                description="Upload utility bills to see cost trends over time."
                action={
                  <button className="btn-primary" onClick={() => navigate('/documents')}>
                    Upload bills
                  </button>
                }
              />
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={summary.monthlyCosts} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="demandGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--danger)" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="var(--danger)" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="energyGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="var(--accent)" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => v >= 1000 ? `$${(v / 1000).toFixed(0)}k` : `$${v}`} width={52} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area type="monotone" dataKey="demand" name="Demand $" stackId="1" stroke="var(--danger)" fill="url(#demandGrad)" strokeWidth={1.5} />
                  <Area type="monotone" dataKey="energy" name="Energy $" stackId="1" stroke="var(--accent)" fill="url(#energyGrad)" strokeWidth={1.5} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Demand charge breakdown */}
        <div className="card">
          <div className="card-header">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Zap size={15} /> Demand vs Energy Split
            </h3>
          </div>
          <div className="card-body">
            {summary.billCount === 0 ? (
              <div className="empty-state" style={{ padding: '1.5rem 0' }}>
                <p className="text-muted">Upload bills to see charge breakdown.</p>
              </div>
            ) : (
              <>
                <div style={{ marginBottom: 16 }}>
                  {[
                    { label: 'Demand charges', amount: summary.demandCharges, color: 'var(--danger)' },
                    { label: 'Energy charges', amount: summary.energyCharges, color: 'var(--accent)' },
                  ].map(row => {
                    const pct = summary.totalSpend > 0 ? (row.amount / summary.totalSpend) * 100 : 0
                    return (
                      <div key={row.label} style={{ marginBottom: 10 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 12 }}>
                          <span>{row.label}</span>
                          <span style={{ fontWeight: 600 }}>
                            ${row.amount.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            <span className="text-muted" style={{ fontWeight: 400, marginLeft: 6 }}>({pct.toFixed(0)}%)</span>
                          </span>
                        </div>
                        <div style={{ height: 6, background: 'var(--surface-raised)', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${pct}%`, background: row.color, borderRadius: 3 }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
                <button className="btn-ghost" style={{ fontSize: 12 }} onClick={() => navigate('/energy')}>
                  Full energy analysis <ChevronRight size={12} />
                </button>
              </>
            )}
          </div>
        </div>

        {/* Recent bills */}
        <div className="card">
          <div className="card-header">
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <FileText size={15} /> Recent Bills
            </h3>
            <button className="btn-ghost" style={{ fontSize: 12 }} onClick={() => navigate('/documents')}>
              View all <ChevronRight size={12} />
            </button>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {recentBills.length === 0 ? (
              <div className="empty-state" style={{ padding: '2rem' }}>
                <p className="text-muted">No bills uploaded yet.</p>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Site</th>
                    <th>Period</th>
                    <th style={{ textAlign: 'right' }}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {recentBills.map(bill => {
                    const facility = facilities.find(f => f.id === bill.facility_id)
                    const period = new Date(bill.period_start).toLocaleString('default', { month: 'short', year: '2-digit' })
                    return (
                      <tr key={bill.id} onClick={() => navigate(`/sites/${bill.facility_id}/bills`)} style={{ cursor: 'pointer' }}>
                        <td><span className="cell-primary">{facility?.name ?? 'Unknown site'}</span></td>
                        <td className="text-muted" style={{ fontSize: 12 }}>{period}</td>
                        <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                          ${Number(bill.total_cost).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Quick links for Finance */}
        <div className="card">
          <div className="card-header">
            <h3>Quick Access</h3>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { label: 'Upload utility bill', icon: <Upload size={14} />, to: '/documents' },
              { label: 'Refrigerant spend', icon: <Thermometer size={14} />, to: '/refrigerant' },
              { label: 'Energy analysis', icon: <Zap size={14} />, to: '/energy' },
              { label: 'Compliance exports', icon: <AlertTriangle size={14} />, to: '/reports' },
              { label: 'Site comparison', icon: <TrendingUp size={14} />, to: '/compare' },
            ].map(link => (
              <button
                key={link.to}
                className="btn-ghost"
                style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-start', fontSize: 13 }}
                onClick={() => navigate(link.to)}
              >
                {link.icon} {link.label} <ChevronRight size={12} style={{ marginLeft: 'auto' }} />
              </button>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}
