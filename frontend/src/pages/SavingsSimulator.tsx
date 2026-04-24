import { useState } from 'react'
import { Calculator, TrendingDown, Loader2, DollarSign } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
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

      {isLoading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
          <Loader2 size={24} className="spin" />
        </div>
      )}

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
