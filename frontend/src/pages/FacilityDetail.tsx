import { useRef, useState, useEffect } from 'react'
import { useParams, Outlet, NavLink, useNavigate } from 'react-router-dom'
import { Upload, Edit3, Loader2, X } from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import LoadingState from '../components/ui/LoadingState'
import { useFacility, useUpdateFacility } from '../hooks/useFacilities'
import { useUploadBills } from '../hooks/useBills'
import { useSiteContext } from '../contexts/SiteContext'

const TABS = [
  { label: 'Overview',      to: '.'            },
  { label: 'Floor Plan',    to: 'map'          },
  { label: 'Zones',         to: 'zones'        },
  { label: 'Equipment',     to: 'equipment'    },
  { label: 'Intelligence',  to: 'energy'       },
  { label: 'Controls',      to: 'controls'     },
  { label: 'Connections',   to: 'connections'  },
]

export default function FacilityDetail() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const { data: facility, isLoading } = useFacility(facilityId!)
  const uploadBills = useUploadBills(facilityId!)
  const updateFacility = useUpdateFacility(facilityId!)
  const { setSite } = useSiteContext()

  // Keep sidebar in sync with whatever site you navigated to directly
  useEffect(() => {
    if (facility) setSite(facility)
  }, [facility]) // eslint-disable-line react-hooks/exhaustive-deps
  const [showEdit, setShowEdit] = useState(false)

  // Edit form state
  const [editName, setEditName] = useState('')
  const [editAddress, setEditAddress] = useState('')
  const [editCity, setEditCity] = useState('')
  const [editState, setEditState] = useState('')
  const [editSqft, setEditSqft] = useState('')

  const openEditModal = () => {
    if (!facility) return
    setEditName(facility.name)
    setEditAddress(facility.address || '')
    setEditCity(facility.city || '')
    setEditState(facility.state || '')
    setEditSqft(facility.sqft ? String(facility.sqft) : '')
    setShowEdit(true)
  }

  const handleEditSave = () => {
    if (!editName.trim()) return
    updateFacility.mutate(
      {
        name: editName.trim(),
        address: editAddress.trim() || undefined,
        city: editCity.trim() || undefined,
        state: editState.trim() || undefined,
        sqft: editSqft ? Number(editSqft) : undefined,
      },
      { onSuccess: () => setShowEdit(false) },
    )
  }

  const handleUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    uploadBills.mutate(file, {
      onSettled: () => { if (fileRef.current) fileRef.current.value = '' },
    })
  }

  if (isLoading) return <LoadingState />

  const subtitle = [facility?.city, facility?.state].filter(Boolean).join(', ') +
    (facility?.sqft ? ` \u00b7 ${facility.sqft.toLocaleString()} sqft` : '')

  return (
    <div className="page-container">
      <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload} style={{ display: 'none' }} />

      <PageHeader title={facility?.name ?? 'Facility'} subtitle={subtitle || undefined} backAction={() => navigate('/')}>
        <button className="btn-secondary" onClick={openEditModal}><Edit3 size={14} /> Edit</button>
        <button className="btn-primary" onClick={() => fileRef.current?.click()} disabled={uploadBills.isPending}>
          {uploadBills.isPending ? <><Loader2 size={14} className="spin" /> Uploading...</> : <><Upload size={14} /> Upload Bill</>}
        </button>
      </PageHeader>

      <div className="tab-bar">
        {TABS.map(({ label, to }) => (
          <NavLink key={to} to={to} end={to === '.'} className={({ isActive }) => `tab${isActive ? ' active' : ''}`}>
            {label}
          </NavLink>
        ))}
      </div>

      <div className="content-area">
        <Outlet />
      </div>

      {/* Edit Facility Modal */}
      {showEdit && (
        <div className="modal-overlay" onClick={() => setShowEdit(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 440 }}>
            <div className="modal-header">
              <h3>Edit Facility</h3>
              <button className="btn-ghost" onClick={() => setShowEdit(false)} style={{ padding: 4 }}><X size={16} /></button>
            </div>
            <div className="modal-body">
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Facility name</label>
                <input value={editName} onChange={e => setEditName(e.target.value)} placeholder="Warehouse name" />
              </div>
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Address</label>
                <input value={editAddress} onChange={e => setEditAddress(e.target.value)} placeholder="Street address" />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 12, marginBottom: 12 }}>
                <div className="field">
                  <label>City</label>
                  <input value={editCity} onChange={e => setEditCity(e.target.value)} placeholder="City" />
                </div>
                <div className="field">
                  <label>State</label>
                  <input value={editState} onChange={e => setEditState(e.target.value)} placeholder="IL" maxLength={2} />
                </div>
              </div>
              <div className="field" style={{ marginBottom: 12 }}>
                <label>Square footage</label>
                <input value={editSqft} onChange={e => setEditSqft(e.target.value)} placeholder="50000" type="number" />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowEdit(false)}>Cancel</button>
              <button className="btn-primary" onClick={handleEditSave} disabled={!editName.trim() || updateFacility.isPending}>
                {updateFacility.isPending ? <><Loader2 size={14} className="spin" /> Saving...</> : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
