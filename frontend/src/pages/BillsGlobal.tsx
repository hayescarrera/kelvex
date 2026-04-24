import { useState, useEffect, useCallback, useRef } from 'react'
import { FileText, DollarSign, Zap, TrendingDown, Upload } from 'lucide-react'
import { api, type Bill } from '../lib/api'
import { useSiteContext } from '../contexts/SiteContext'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'

export default function BillsGlobal() {
  const { facilities } = useSiteContext()
  const [allBills, setAllBills] = useState<(Bill & { facility_name: string })[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadFacilityId, setUploadFacilityId] = useState('')
  const [showUpload, setShowUpload] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(() => {
    if (!facilities.length) { setLoading(false); return }
    setLoading(true)
    Promise.all(
      facilities.map(f =>
        api.listBills(f.id).then(d => d.bills.map(b => ({ ...b, facility_name: f.name })))
      )
    )
      .then(r => setAllBills(r.flat().sort((a, b) => b.period_start.localeCompare(a.period_start))))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [facilities])

  useEffect(() => { load() }, [load])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !uploadFacilityId) return
    setUploading(true); setError('')
    try { await api.uploadBills(uploadFacilityId, file); setShowUpload(false); load() }
    catch (err) { setError(err instanceof Error ? err.message : 'Upload failed') }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const totalSpend = allBills.reduce((s, b) => s + Number(b.total_cost ?? 0), 0)
  const totalDemand = allBills.reduce((s, b) => s + Number(b.demand_charge ?? 0), 0)

  return (
    <div className="page-container">
      <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload} style={{ display: 'none' }} />
      <PageHeader title="Utility Bills" subtitle={`${allBills.length} bills across ${facilities.length} facilities`}>
        <button className="btn-primary" onClick={() => setShowUpload(!showUpload)}>
          <Upload size={15} /> Upload Bill
        </button>
      </PageHeader>

      {showUpload && (
        <div className="card inline-upload">
          <span className="text-secondary">Upload to:</span>
          <select value={uploadFacilityId} onChange={e => setUploadFacilityId(e.target.value)}>
            <option value="">Select facility</option>
            {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <button className="btn-primary" onClick={() => uploadFacilityId && fileRef.current?.click()} disabled={!uploadFacilityId || uploading}>
            {uploading ? 'Uploading...' : 'Choose CSV'}
          </button>
          <button className="btn-secondary" onClick={() => setShowUpload(false)}>Cancel</button>
          {error && <span className="text-danger">{error}</span>}
        </div>
      )}

      {allBills.length > 0 && (
        <div className="stat-grid stagger">
          <StatCard icon={<FileText size={18} />} color="var(--accent)" value={String(allBills.length)} label="Total Bills" />
          <StatCard icon={<DollarSign size={18} />} color="var(--warning)" value={`$${Math.round(totalSpend).toLocaleString()}`} label="Total Spend" />
          <StatCard icon={<Zap size={18} />} color="var(--danger)" value={`$${Math.round(totalDemand).toLocaleString()}`} label="Demand Charges" />
          <StatCard icon={<TrendingDown size={18} />} color="var(--success)" value={totalSpend > 0 ? `${Math.round(totalDemand / totalSpend * 100)}%` : '--'} label="Demand % of Bill" />
        </div>
      )}

      <div className="content-area">
        {loading ? <LoadingState label="Loading bills..." /> : allBills.length === 0 ? (
          <EmptyState icon={<FileText size={28} />} title="No bills uploaded" description="Upload utility bills to see cost analysis and savings opportunities." />
        ) : (
          <div className="card">
            <table className="data-table">
              <thead><tr><th>Facility</th><th>Period</th><th>Usage</th><th>Total Cost</th><th>Peak kW</th><th>Demand $</th><th>Energy $</th></tr></thead>
              <tbody>
                {allBills.map(b => (
                  <tr key={b.id}>
                    <td><span className="cell-primary">{b.facility_name}</span></td>
                    <td><span className="text-muted">{new Date(b.period_start).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}</span></td>
                    <td>{b.total_kwh ? `${Number(b.total_kwh).toLocaleString()} kWh` : '\u2014'}</td>
                    <td><span className="cell-primary">{b.total_cost ? `$${Number(b.total_cost).toLocaleString()}` : '\u2014'}</span></td>
                    <td><span style={{ color: 'var(--danger)', fontWeight: 600 }}>{b.peak_demand_kw ? Number(b.peak_demand_kw).toLocaleString() : '\u2014'}</span></td>
                    <td><span style={{ color: 'var(--warning)' }}>{b.demand_charge ? `$${Number(b.demand_charge).toLocaleString()}` : '\u2014'}</span></td>
                    <td><span style={{ color: 'var(--accent)' }}>{b.energy_charge ? `$${Number(b.energy_charge).toLocaleString()}` : '\u2014'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
