import { useState, useEffect, useCallback } from 'react'
import {
  FileText, Download, ShieldCheck, Zap, Droplets,
  DollarSign, RefreshCw, CheckCircle, Clock, AlertTriangle,
} from 'lucide-react'
import toast from 'react-hot-toast'
import PageHeader from '../components/ui/PageHeader'
import LoadingState from '../components/ui/LoadingState'
import { useSiteContext } from '../contexts/SiteContext'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../lib/api'
import type { ComplianceReportEntry, Facility } from '../lib/api'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function statusColor(state: string) {
  return state === 'signed_off' ? 'var(--success)' : state === 'generated' ? 'var(--accent)' : 'var(--text-muted)'
}

function statusLabel(state: string) {
  return state === 'signed_off' ? 'Signed Off' : state === 'generated' ? 'Generated' : state
}

// ── Export button card ────────────────────────────────────────────────────────
interface ExportCardProps {
  icon: React.ReactNode
  title: string
  description: string
  onExport: () => void
  loading?: boolean
  disabled?: boolean
}

function ExportCard({ icon, title, description, onExport, loading, disabled }: ExportCardProps) {
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
      <div className="card-body" style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8, background: 'var(--accent-muted)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--accent)', flexShrink: 0,
          }}>
            {icon}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>{title}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>{description}</div>
          </div>
        </div>
      </div>
      <div style={{ padding: '0 16px 14px' }}>
        <button className="btn-secondary" style={{ width: '100%', justifyContent: 'center', gap: 6, fontSize: 13 }}
          onClick={onExport} disabled={loading || disabled}>
          {loading ? <RefreshCw size={13} className="spin" /> : <Download size={13} />}
          {loading ? 'Generating...' : 'Export'}
        </button>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function ReportsPage() {
  const { site, facilities } = useSiteContext()
  const { hasPermission } = useAuth()
  const facilityId = site?.id

  const [reports, setReports] = useState<ComplianceReportEntry[]>([])
  const [loadingReports, setLoadingReports] = useState(true)
  const [generatingAIM, setGeneratingAIM] = useState<string | null>(null)
  const [exportingCSV, setExportingCSV] = useState<string | null>(null)
  const [selectedFacilityForReport, setSelectedFacilityForReport] = useState(facilityId ?? '')

  const loadReports = useCallback(async () => {
    setLoadingReports(true)
    try {
      const params: Record<string, string> = {}
      if (facilityId) params.facility_id = facilityId
      const res = await api.listComplianceReports(params)
      setReports(res.reports)
    } catch {
      setReports([])
    } finally {
      setLoadingReports(false)
    }
  }, [facilityId])

  useEffect(() => { loadReports() }, [loadReports])
  useEffect(() => {
    if (facilityId) setSelectedFacilityForReport(facilityId)
  }, [facilityId])

  async function handleGenerateAIMPacket(fId: string) {
    if (!fId) { toast.error('Select a site first'); return }
    setGeneratingAIM(fId)
    try {
      const report = await api.generateComplianceReport({
        facility_id: fId,
        report_type: 'aim_act',
        title: `AIM Act Compliance Packet — ${new Date().toLocaleDateString()}`,
      })
      toast.success('AIM Act packet generated')
      loadReports()
      // In production: trigger download of report.pdf_url
      console.info('Report generated:', report.id)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to generate report')
    } finally {
      setGeneratingAIM(null)
    }
  }

  async function handleExportRefrigerantCSV() {
    if (!facilityId) { toast.error('Select a site first'); return }
    setExportingCSV('refrigerant')
    try {
      // Using audit CSV as a proxy — production would have a dedicated refrigerant export endpoint
      const data = await api.exportAuditCSV(facilityId)
      const blob = new Blob([data.csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `refrigerant-log-${site?.name ?? 'site'}-${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Refrigerant log exported')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExportingCSV(null)
    }
  }

  async function handleExportEnergyCSV() {
    if (!facilityId) { toast.error('Select a site first'); return }
    setExportingCSV('energy')
    try {
      const data = await api.exportPowerCSV(facilityId)
      const blob = new Blob([data.csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `energy-${site?.name ?? 'site'}-${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Energy data exported')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExportingCSV(null)
    }
  }

  async function handleExportAlertsCSV() {
    if (!facilityId) { toast.error('Select a site first'); return }
    setExportingCSV('alerts')
    try {
      const data = await api.exportAlertsCSV(facilityId)
      const blob = new Blob([data.csv], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `alerts-${site?.name ?? 'site'}-${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Alerts exported')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExportingCSV(null)
    }
  }

  async function handleSignOff(reportId: string) {
    try {
      await api.signOffReport(reportId)
      toast.success('Report signed off')
      loadReports()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Sign-off failed')
    }
  }

  const canSign = hasPermission('reports:generate') || hasPermission('audit:view')

  const facilityForAIM = facilities.find(f => f.id === selectedFacilityForReport)

  return (
    <div className="page-container">
      <PageHeader
        title="Reports & Exports"
        subtitle="Compliance packets, regulatory exports, and data downloads"
      />

      {/* AIM Act compliance section */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <ShieldCheck size={15} /> AIM Act Compliance Packet
          </h3>
        </div>
        <div className="card-body">
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 16, lineHeight: 1.6 }}>
            Generate a signed compliance packet with EPA-method leak rates, circuit history, and repair records.
            Required for sites with HFC equipment above the 35% annualized threshold.
          </p>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              value={selectedFacilityForReport}
              onChange={e => setSelectedFacilityForReport(e.target.value)}
              style={{ padding: '7px 10px', fontSize: 13, borderRadius: 6, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
            >
              <option value="">Select site...</option>
              {facilities.map((f: Facility) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
            <button className="btn-primary"
              onClick={() => handleGenerateAIMPacket(selectedFacilityForReport)}
              disabled={!selectedFacilityForReport || generatingAIM !== null}
              style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              {generatingAIM ? <RefreshCw size={14} className="spin" /> : <ShieldCheck size={14} />}
              {generatingAIM ? 'Generating...' : 'Generate AIM Act Packet'}
            </button>
            {facilityForAIM && (
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {facilityForAIM.name}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Export grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginBottom: 24 }}>
        <ExportCard
          icon={<Droplets size={18} />}
          title="Refrigerant Log CSV"
          description="All refrigerant adds, leak events, and repairs for the selected site. Required for EPA audit responses."
          onExport={handleExportRefrigerantCSV}
          loading={exportingCSV === 'refrigerant'}
          disabled={!facilityId}
        />
        <ExportCard
          icon={<Zap size={18} />}
          title="Energy Data CSV"
          description="Power readings and demand data. Use for utility negotiations, benchmarking, or incentive programs."
          onExport={handleExportEnergyCSV}
          loading={exportingCSV === 'energy'}
          disabled={!facilityId}
        />
        <ExportCard
          icon={<AlertTriangle size={18} />}
          title="Alerts Export CSV"
          description="Full alert history with timestamps, severity, and resolution notes. Good for service review meetings."
          onExport={handleExportAlertsCSV}
          loading={exportingCSV === 'alerts'}
          disabled={!facilityId}
        />
        <ExportCard
          icon={<DollarSign size={18} />}
          title="Utility Bills CSV"
          description="Parsed bill data across all sites. Useful for financial reporting and budget variance analysis."
          onExport={() => toast('Bill export coming soon', { icon: 'ℹ️' })}
          disabled={false}
        />
      </div>

      {/* Generated reports list */}
      <div className="card">
        <div className="card-header">
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <FileText size={15} /> Generated Reports
          </h3>
          <button className="btn-ghost" style={{ fontSize: 12 }} onClick={loadReports}>
            <RefreshCw size={12} />
          </button>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {loadingReports ? (
            <LoadingState label="Loading reports..." />
          ) : reports.length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
              <FileText size={24} style={{ display: 'block', margin: '0 auto 8px', opacity: 0.4 }} />
              No reports generated yet. Use the AIM Act packet above to create one.
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Report</th>
                  <th>Type</th>
                  <th>Generated</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {reports.map(r => (
                  <tr key={r.id}>
                    <td className="cell-primary">{r.title ?? 'Compliance Report'}</td>
                    <td>
                      <span style={{
                        fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                        background: 'var(--bg-tertiary)', color: 'var(--text-secondary)',
                        textTransform: 'uppercase',
                      }}>
                        {(r.report_type ?? 'report').replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {formatDate(r.created_at)}
                    </td>
                    <td>
                      <span style={{
                        display: 'flex', alignItems: 'center', gap: 4,
                        fontSize: 12, color: statusColor(r.state ?? ''), fontWeight: 600,
                      }}>
                        {r.state === 'signed_off'
                          ? <CheckCircle size={12} />
                          : <Clock size={12} />}
                        {statusLabel(r.state ?? '')}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        {r.state !== 'signed_off' && canSign && (
                          <button className="btn-secondary" onClick={() => handleSignOff(r.id)}
                            style={{ fontSize: 11, padding: '4px 10px' }}>
                            <ShieldCheck size={11} /> Sign Off
                          </button>
                        )}
                        <button className="btn-ghost" style={{ fontSize: 11, padding: '4px 10px' }}
                          onClick={() => toast('PDF download coming soon', { icon: '📄' })}>
                          <Download size={11} />
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
    </div>
  )
}
