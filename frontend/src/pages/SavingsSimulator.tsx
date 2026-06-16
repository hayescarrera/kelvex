import { useState } from 'react'
import { Calculator, TrendingDown, DollarSign, Droplets, Info } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import { useSiteContext } from '../contexts/SiteContext'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

const STRATEGIES = [
  {
    id: 'pre_cool',
    title: 'Pre-cool Before Peak TOU',
    description: 'Cool zones 2°F below setpoint during off-peak hours to reduce on-peak demand',
    savingsRange: [0.12, 0.15],
    color: 'var(--accent)',
  },
  {
    id: 'load_shed',
    title: 'Compressor Load Shedding',
    description: 'Stagger compressor ramp-ups to flatten peak demand spikes',
    savingsRange: [0.08, 0.10],
    color: 'var(--success)',
  },
  {
    id: 'night_setback',
    title: 'Night Setback Recovery',
    description: 'Raise setpoints during peak TOU periods, recover during off-peak overnight',
    savingsRange: [0.05, 0.08],
    color: 'var(--warning)',
  },
  {
    id: 'vfd',
    title: 'Evaporator Fan VFD Optimization',
    description: 'Variable frequency drives on evaporator fans reduce runtime energy consumption',
    savingsRange: [0.10, 0.14],
    color: '#7c3aed',
  },
]

export default function SavingsSimulator() {
  const { facilities, site } = useSiteContext()
  const [selectedFacility, setSelectedFacility] = useState(site?.id || '')

  // Fetch bills for the selected facility
  const { data: billData, isLoading } = useQuery({
    queryKey: ['bills', selectedFacility, 'savings-sim'],
    queryFn: () => api.listBills(selectedFacility),
    enabled: !!selectedFacility,
  })

  const bills = billData?.bills ?? []

  const { data: reportData, isLoading: reportLoading, isError: reportError } = useQuery({
    queryKey: ['savings-report', selectedFacility],
    queryFn: () => api.getSavingsReport(selectedFacility),
    enabled: !!selectedFacility,
  })

  // Calculate annual costs from bills
  const annualDemandCost = bills.reduce((sum, b) => sum + Number(b.demand_charge || 0), 0)
  const annualTotalCost = bills.reduce((sum, b) => sum + Number(b.total_cost || 0), 0)
  const hasBillData = bills.length > 0

  // Calculate savings per strategy
  const strategySavings = STRATEGIES.map(s => {
    const demandSaving = annualDemandCost * ((s.savingsRange[0] + s.savingsRange[1]) / 2)
    const lowSaving = annualDemandCost * s.savingsRange[0]
    const highSaving = annualDemandCost * s.savingsRange[1]
    return { ...s, demandSaving, lowSaving, highSaving }
  })

  const totalPotentialSavings = strategySavings.reduce((s, st) => s + st.demandSaving, 0)
  // Strategies overlap, so realistic combined is ~60% of sum
  const realisticSavings = totalPotentialSavings * 0.6

  return (
    <div className="page-container">
      <PageHeader title="Savings Simulator" subtitle="Estimate demand and energy savings by control strategy" />

      <div style={{ marginBottom: 20, marginTop: 16 }}>
        <select
          value={selectedFacility}
          onChange={e => setSelectedFacility(e.target.value)}
          style={{
            padding: '8px 12px', fontSize: '13px', border: '1px solid var(--input-border)',
            borderRadius: 'var(--radius-md)', background: 'var(--input-bg)', color: 'var(--text-primary)',
            fontFamily: 'inherit', minWidth: 240,
          }}
        >
          <option value="">Select a facility...</option>
          {facilities.map(f => (
            <option key={f.id} value={f.id}>{f.name}</option>
          ))}
        </select>
      </div>

      {isLoading && <LoadingState />}

      {!isLoading && selectedFacility && (
        <>
          <div className="stat-grid stagger" style={{ marginBottom: 24 }}>
            <StatCard
              icon={<DollarSign size={18} />} color="var(--text-primary)"
              value={hasBillData ? `$${annualTotalCost.toLocaleString()}` : '--'}
              label={`Annual Cost (${bills.length} bills)`}
            />
            <StatCard
              icon={<TrendingDown size={18} />} color="var(--danger)"
              value={hasBillData ? `$${annualDemandCost.toLocaleString()}` : '--'}
              label="Demand Charges"
            />
            <StatCard
              icon={<Calculator size={18} />} color="var(--success)"
              value={hasBillData ? `$${Math.round(realisticSavings).toLocaleString()}` : '--'}
              label="Estimated Annual Savings"
            />
          </div>

          {!hasBillData ? (
            <div className="card">
              <div className="card-body">
                <div className="empty-state">
                  <div className="empty-icon"><Calculator size={32} /></div>
                  <h3>No bill data available</h3>
                  <p>Upload utility bills for this facility to calculate savings projections.</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="savings-grid">
              {strategySavings.map(s => (
                <div key={s.id} className="card" style={{ borderTop: `3px solid ${s.color}` }}>
                  <div className="card-body">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                      <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>{s.title}</h3>
                      <span style={{
                        background: s.color, color: '#fff', borderRadius: '9999px',
                        padding: '0.2rem 0.6rem', fontSize: '0.8rem', fontWeight: 700, whiteSpace: 'nowrap', marginLeft: '0.5rem',
                      }}>
                        ${Math.round(s.lowSaving).toLocaleString()} – ${Math.round(s.highSaving).toLocaleString()}/yr
                      </span>
                    </div>
                    <p className="text-muted" style={{ margin: '0 0 8px', fontSize: '0.875rem' }}>{s.description}</p>
                    <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                      {Math.round(s.savingsRange[0] * 100)}–{Math.round(s.savingsRange[1] * 100)}% demand charge reduction
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* ── Quantified Savings Report ──────────────────────── */}
          <div className="card" style={{ marginTop: 24 }}>
            <div className="card-header">
              <div>
                <h3 style={{ margin: 0 }}>Quantified Savings Report</h3>
                {reportData && (
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {reportData.report_period.start} → {reportData.report_period.end}
                  </span>
                )}
              </div>
              {reportData && (
                <span style={{ fontSize: 20, fontWeight: 700, color: 'var(--success)' }}>
                  ${reportData.total_quantified_savings.toLocaleString(undefined, { maximumFractionDigits: 0 })} total impact
                </span>
              )}
            </div>
            <div className="card-body">
              {reportLoading && <LoadingState />}
              {reportError && (
                <p style={{ color: 'var(--danger)', fontSize: 13 }}>Unable to load savings report.</p>
              )}
              {reportData && (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                    <div style={{ padding: '14px 16px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)' }}>
                        <TrendingDown size={13} /> Energy Optimization
                      </div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--success)' }}>
                        ${reportData.energy_savings.total_est.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                        {reportData.energy_savings.demand_reduction_pct}% demand reduction + {reportData.energy_savings.energy_reduction_pct}% energy reduction
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                        Based on {reportData.energy_savings.bills_analyzed} bills · ${reportData.energy_savings.annual_bill_total.toLocaleString(undefined, { maximumFractionDigits: 0 })} annual spend
                      </div>
                    </div>
                    <div style={{ padding: '14px 16px', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)' }}>
                        <Droplets size={13} /> Refrigerant Leak Prevention
                      </div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--accent)' }}>
                        ${reportData.refrigerant_savings.total_refrigerant_impact.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                        {reportData.refrigerant_savings.total_lbs_added_12m.toFixed(0)} lbs added · {reportData.refrigerant_savings.charge_deficit_pct.toFixed(1)}% charge deficit
                      </div>
                      {reportData.refrigerant_savings.energy_penalty_pct > 0 && (
                        <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 4 }}>
                          +{reportData.refrigerant_savings.energy_penalty_pct.toFixed(1)}% energy penalty from undercharge (ASHRAE)
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Methodology */}
                  <details style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    <summary style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, userSelect: 'none' }}>
                      <Info size={12} /> View methodology & citations
                    </summary>
                    <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                      {Object.entries(reportData.methodology).map(([k, v]) => (
                        <div key={k} style={{ padding: '8px 10px', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)' }}>
                          <div style={{ fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2, color: 'var(--text-secondary)' }}>
                            {k.replace(/_/g, ' ')}
                          </div>
                          {v}
                        </div>
                      ))}
                    </div>
                  </details>
                </>
              )}
            </div>
          </div>
        </>
      )}

      {!selectedFacility && !isLoading && (
        <div className="card">
          <div className="card-body">
            <div className="empty-state">
              <div className="empty-icon"><Calculator size={32} /></div>
              <h3>Select a facility</h3>
              <p>Choose a facility above to calculate potential savings from demand management strategies.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
