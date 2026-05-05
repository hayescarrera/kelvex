import { useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Upload, FileText, Loader2, Eye, Trash2, Plus, X } from 'lucide-react'
import { useBills, useUploadBills, useAnalyzeBill, useDeleteBill, useCreateBill } from '../../hooks/useBills'

export default function BillsPage() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [showAddModal, setShowAddModal] = useState(false)

  const { data, isLoading } = useBills(facilityId!)
  const bills = data?.bills ?? []
  const uploadMutation = useUploadBills(facilityId!)
  const analyzeMutation = useAnalyzeBill(facilityId!)
  const deleteMutation = useDeleteBill(facilityId!)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      uploadMutation.mutate(file, {
        onSuccess: () => toast.success('Bills uploaded'),
        onError: () => toast.error('Failed to upload bills'),
      })
      e.target.value = ''
    }
  }

  const formatPeriod = (dateStr: string) => {
    const d = new Date(dateStr)
    return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  }

  const formatCurrency = (val: number) =>
    val != null ? `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'

  const formatNumber = (val: number, decimals = 0) =>
    val != null ? val.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) : '—'

  return (
    <div className="stack-lg">
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <FileText size={18} />
            <span>Utility Bills</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {uploadMutation.isError && (
              <span className="badge badge-danger">Upload failed</span>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />
            <button
              className="btn-secondary"
              onClick={() => setShowAddModal(true)}
            >
              <Plus size={15} /> Add Bill
            </button>
            <button
              className="btn-primary"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadMutation.isPending}
            >
              {uploadMutation.isPending ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <Upload size={15} />
              )}
              Upload CSV
            </button>
          </div>
        </div>

        <div className="card-body">
          {isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
              <Loader2 size={24} className="spin" />
            </div>
          ) : bills.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <FileText size={32} />
              </div>
              <p>No bills uploaded yet</p>
              <p className="text-muted">Upload a CSV file or add a bill manually to get started</p>
              <button className="btn-ghost" style={{ marginTop: 12 }} onClick={() => setShowAddModal(true)}>
                <Plus size={14} /> Add your first bill
              </button>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Usage kWh</th>
                  <th>Total Cost</th>
                  <th style={{ color: 'var(--color-danger, #ef4444)' }}>Peak kW</th>
                  <th style={{ color: 'var(--color-warning, #f59e0b)' }}>Demand $</th>
                  <th style={{ color: 'var(--color-accent, #3b82f6)' }}>Energy $</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {bills.map((bill: any) => (
                  <tr key={bill.id}>
                    <td className="cell-primary">{formatPeriod(bill.period_start ?? bill.period)}</td>
                    <td>{formatNumber(bill.total_kwh ?? bill.usage_kwh)}</td>
                    <td>{formatCurrency(bill.total_cost)}</td>
                    <td style={{ color: 'var(--color-danger, #ef4444)', fontWeight: 600 }}>
                      {formatNumber(bill.peak_demand_kw ?? bill.peak_kw, 1)}
                    </td>
                    <td style={{ color: 'var(--color-warning, #f59e0b)' }}>
                      {formatCurrency(bill.demand_charge)}
                    </td>
                    <td style={{ color: 'var(--color-accent, #3b82f6)' }}>
                      {formatCurrency(bill.energy_charge)}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                          className="icon-btn icon-btn-sm"
                          title="Analyze"
                          disabled={analyzeMutation.isPending}
                          onClick={() => analyzeMutation.mutate(bill.id, {
                            onSuccess: () => toast.success('Analysis complete'),
                            onError: () => toast.error('Failed to analyze bill'),
                          })}
                        >
                          {analyzeMutation.isPending && analyzeMutation.variables === bill.id ? (
                            <Loader2 size={14} className="spin" />
                          ) : (
                            <Eye size={14} />
                          )}
                        </button>
                        <button
                          className="icon-btn icon-btn-sm"
                          title="Delete"
                          disabled={deleteMutation.isPending}
                          onClick={() => deleteMutation.mutate(bill.id, {
                            onSuccess: () => toast.success('Bill deleted'),
                            onError: () => toast.error('Failed to delete bill'),
                          })}
                        >
                          {deleteMutation.isPending && deleteMutation.variables === bill.id ? (
                            <Loader2 size={14} className="spin" />
                          ) : (
                            <Trash2 size={14} />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {showAddModal && <AddBillModal facilityId={facilityId!} onClose={() => setShowAddModal(false)} />}
    </div>
  )
}

function AddBillModal({ facilityId, onClose }: { facilityId: string; onClose: () => void }) {
  const createBill = useCreateBill(facilityId)
  const [form, setForm] = useState({
    period_start: '', period_end: '',
    total_kwh: '', total_cost: '',
    peak_demand_kw: '', demand_charge: '', energy_charge: '',
  })

  const setField = (key: string, val: string) => setForm(prev => ({ ...prev, [key]: val }))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createBill.mutate({
      period_start: form.period_start,
      period_end: form.period_end,
      total_kwh: form.total_kwh ? parseFloat(form.total_kwh) : undefined,
      total_cost: form.total_cost ? parseFloat(form.total_cost) : undefined,
      peak_demand_kw: form.peak_demand_kw ? parseFloat(form.peak_demand_kw) : undefined,
      demand_charge: form.demand_charge ? parseFloat(form.demand_charge) : undefined,
      energy_charge: form.energy_charge ? parseFloat(form.energy_charge) : undefined,
    }, {
      onSuccess: () => { toast.success('Bill added'); onClose() },
      onError: () => toast.error('Failed to add bill'),
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Utility Bill</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Period Start</label>
              <input type="date" value={form.period_start} onChange={e => setField('period_start', e.target.value)} required />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Period End</label>
              <input type="date" value={form.period_end} onChange={e => setField('period_end', e.target.value)} required />
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Total kWh</label>
              <input type="number" step="any" value={form.total_kwh} onChange={e => setField('total_kwh', e.target.value)} placeholder="125000" />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Total Cost ($)</label>
              <input type="number" step="0.01" value={form.total_cost} onChange={e => setField('total_cost', e.target.value)} placeholder="18500.00" />
            </div>
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Peak Demand (kW)</label>
              <input type="number" step="any" value={form.peak_demand_kw} onChange={e => setField('peak_demand_kw', e.target.value)} placeholder="450" />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Demand Charge ($)</label>
              <input type="number" step="0.01" value={form.demand_charge} onChange={e => setField('demand_charge', e.target.value)} placeholder="5200.00" />
            </div>
          </div>
          <div className="field">
            <label>Energy Charge ($)</label>
            <input type="number" step="0.01" value={form.energy_charge} onChange={e => setField('energy_charge', e.target.value)} placeholder="13300.00" />
          </div>
          {createBill.isError && <p className="text-danger" style={{ fontSize: 12 }}>Failed to add bill.</p>}
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={createBill.isPending}>
              {createBill.isPending ? 'Adding...' : <><Plus size={14} /> Add Bill</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
