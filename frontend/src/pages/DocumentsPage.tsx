import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Upload, FileText, Trash2, X, Filter,
  File, Image, BookOpen, Award, Wrench,
} from 'lucide-react'
import toast from 'react-hot-toast'
import PageHeader from '../components/ui/PageHeader'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { api } from '../lib/api'
import { useSiteContext } from '../contexts/SiteContext'
import type { Document, Facility } from '../lib/api'

const DOC_TYPES = [
  { value: 'bill', label: 'Utility Bill', icon: <FileText size={13} /> },
  { value: 'permit', label: 'Permit / Certificate', icon: <Award size={13} /> },
  { value: 'manual', label: 'Equipment Manual', icon: <BookOpen size={13} /> },
  { value: 'inspection', label: 'Inspection Report', icon: <Wrench size={13} /> },
  { value: 'photo', label: 'Photo / Image', icon: <Image size={13} /> },
  { value: 'other', label: 'Other', icon: <File size={13} /> },
]

function docTypeIcon(type: string) {
  return DOC_TYPES.find(d => d.value === type)?.icon ?? <File size={13} />
}

function docTypeLabel(type: string) {
  return DOC_TYPES.find(d => d.value === type)?.label ?? type
}

function formatBytes(bytes: number | null): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// ── Upload Modal ──────────────────────────────────────────────────────────────
interface UploadModalProps {
  facilities: Facility[]
  defaultFacilityId?: string
  onClose: () => void
  onSuccess: () => void
}

function UploadModal({ facilities, defaultFacilityId, onClose, onSuccess }: UploadModalProps) {
  const [uploading, setUploading] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [form, setForm] = useState({
    facility_id: defaultFacilityId ?? (facilities[0]?.id ?? ''),
    document_type: 'bill',
    name: '',
  })
  const fileRef = useRef<HTMLInputElement>(null)

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f)
    if (!form.name) setForm(prev => ({ ...prev, name: f.name.replace(/\.[^/.]+$/, '') }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!file) { toast.error('Select a file to upload'); return }
    setUploading(true)
    try {
      await api.uploadDocument(file, {
        facility_id: form.facility_id || undefined,
        document_type: form.document_type,
        name: form.name || file.name,
      })
      toast.success('Document uploaded')
      onSuccess()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 480 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Upload Document</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          {/* Drop zone */}
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => {
              e.preventDefault()
              const f = e.dataTransfer.files?.[0]
              if (f) { setFile(f); if (!form.name) setForm(prev => ({ ...prev, name: f.name.replace(/\.[^/.]+$/, '') })) }
            }}
            style={{
              border: `2px dashed ${file ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 8, padding: '24px 16px', textAlign: 'center',
              cursor: 'pointer', marginBottom: 16, transition: 'border-color 0.15s',
              background: file ? 'var(--accent-muted)' : 'var(--bg-secondary)',
            }}
          >
            <input ref={fileRef} type="file" style={{ display: 'none' }} onChange={handleFileChange}
              accept=".pdf,.csv,.xlsx,.jpg,.jpeg,.png,.doc,.docx" />
            {file ? (
              <div style={{ fontSize: 13, color: 'var(--accent)', fontWeight: 600 }}>
                <Upload size={20} style={{ display: 'block', margin: '0 auto 8px' }} />
                {file.name} — {formatBytes(file.size)}
              </div>
            ) : (
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                <Upload size={20} style={{ display: 'block', margin: '0 auto 8px' }} />
                Click or drag file here<br />
                <span style={{ fontSize: 11 }}>PDF, CSV, Excel, images</span>
              </div>
            )}
          </div>

          <div className="field">
            <label>Document Name</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="Auto-filled from filename" />
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 1 }}>
              <label>Type</label>
              <select value={form.document_type} onChange={e => setForm({ ...form, document_type: e.target.value })}>
                {DOC_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Site</label>
              <select value={form.facility_id} onChange={e => setForm({ ...form, facility_id: e.target.value })}>
                <option value="">All sites / General</option>
                {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </div>
          </div>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={uploading || !file}>
              {uploading ? 'Uploading...' : <><Upload size={14} /> Upload</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function DocumentsPage() {
  const { site, facilities } = useSiteContext()
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [showUpload, setShowUpload] = useState(false)
  const [typeFilter, setTypeFilter] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<Document | null>(null)
  const [deleting, setDeleting] = useState(false)

  const facilityId = site?.id

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = { limit: '200' }
      if (facilityId) params.facility_id = facilityId
      if (typeFilter) params.document_type = typeFilter
      const res = await api.listDocuments(params as Parameters<typeof api.listDocuments>[0])
      setDocs(res.documents)
    } catch {
      // silent — endpoint may not be deployed yet
      setDocs([])
    } finally {
      setLoading(false)
    }
  }, [facilityId, typeFilter])

  useEffect(() => { load() }, [load])

  async function handleDelete() {
    if (!confirmDelete) return
    setDeleting(true)
    try {
      await api.deleteDocument(confirmDelete.id)
      toast.success('Document deleted')
      setConfirmDelete(null)
      load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  const facilityName = (id: string | null) => facilities.find(f => f.id === id)?.name ?? '—'

  return (
    <div className="page-container">
      <PageHeader
        title="Documents"
        subtitle="Utility bills, permits, manuals, and inspection reports"
      >
        <button className="btn-primary" onClick={() => setShowUpload(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Upload size={14} /> Upload Document
        </button>
      </PageHeader>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <Filter size={13} style={{ color: 'var(--text-muted)' }} />
        <button onClick={() => setTypeFilter('')} style={{
          padding: '4px 12px', fontSize: 12, borderRadius: 6, cursor: 'pointer',
          background: !typeFilter ? 'var(--accent-muted)' : 'var(--bg-secondary)',
          color: !typeFilter ? 'var(--accent)' : 'var(--text-secondary)',
          border: `1px solid ${!typeFilter ? 'var(--accent)' : 'var(--border)'}`,
        }}>All</button>
        {DOC_TYPES.map(t => (
          <button key={t.value} onClick={() => setTypeFilter(typeFilter === t.value ? '' : t.value)} style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '4px 12px', fontSize: 12, borderRadius: 6, cursor: 'pointer',
            background: typeFilter === t.value ? 'var(--accent-muted)' : 'var(--bg-secondary)',
            color: typeFilter === t.value ? 'var(--accent)' : 'var(--text-secondary)',
            border: `1px solid ${typeFilter === t.value ? 'var(--accent)' : 'var(--border)'}`,
          }}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Document list */}
      <div className="card">
        <div className="card-body" style={{ padding: 0 }}>
          {loading ? (
            <LoadingState label="Loading documents..." />
          ) : docs.length === 0 ? (
            <EmptyState
              icon={<FileText size={24} />}
              title="No documents yet"
              description="Upload utility bills, permits, inspection reports, and equipment manuals."
              action={
                <button className="btn-primary" onClick={() => setShowUpload(true)}>
                  <Upload size={14} /> Upload First Document
                </button>
              }
            />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Type</th>
                  <th>Site</th>
                  <th>Size</th>
                  <th>Uploaded</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {docs.map(doc => (
                  <tr key={doc.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ color: 'var(--accent)' }}>{docTypeIcon(doc.document_type)}</span>
                        <span className="cell-primary">{doc.name}</span>
                      </div>
                    </td>
                    <td>
                      <span style={{
                        fontSize: 11, padding: '2px 8px', borderRadius: 10, fontWeight: 600,
                        background: 'var(--bg-tertiary)', color: 'var(--text-secondary)',
                      }}>
                        {docTypeLabel(doc.document_type)}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {facilityName(doc.facility_id)}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {formatBytes(doc.size_bytes)}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {formatDate(doc.created_at)}
                    </td>
                    <td>
                      <button className="icon-btn-sm" title="Delete"
                        onClick={() => setConfirmDelete(doc)}
                        style={{ color: 'var(--danger)' }}>
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Upload modal */}
      {showUpload && (
        <UploadModal
          facilities={facilities}
          defaultFacilityId={facilityId}
          onClose={() => setShowUpload(false)}
          onSuccess={load}
        />
      )}

      {/* Delete confirm */}
      {confirmDelete && (
        <div className="modal-overlay" onClick={() => setConfirmDelete(null)}>
          <div className="modal" style={{ maxWidth: 380 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Delete Document</h3>
              <button className="icon-btn" onClick={() => setConfirmDelete(null)}><X size={18} /></button>
            </div>
            <div className="modal-body">
              <p style={{ fontSize: 14, marginBottom: 16 }}>
                Delete <strong>{confirmDelete.name}</strong>? This cannot be undone.
              </p>
              <div className="modal-actions">
                <button className="btn-secondary" onClick={() => setConfirmDelete(null)}>Cancel</button>
                <button className="btn-danger" onClick={handleDelete} disabled={deleting}
                  style={{ background: 'var(--danger)', color: '#fff', border: 'none', borderRadius: 6, padding: '7px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
                  {deleting ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
