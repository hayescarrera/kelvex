import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Plus, Trash2, Cpu } from 'lucide-react'
import toast from 'react-hot-toast'
import LoadingState from '../../components/ui/LoadingState'
import EmptyState from '../../components/ui/EmptyState'
import { useEquipment, useCreateEquipment, useDeleteEquipment } from '../../hooks/useEquipment'

const EQUIPMENT_TYPES = [
  { value: 'compressor', label: 'Compressor' },
  { value: 'evaporator', label: 'Evaporator' },
  { value: 'condenser', label: 'Condenser' },
  { value: 'controller', label: 'Controller' },
  { value: 'vfd', label: 'VFD' },
  { value: 'other', label: 'Other' },
]

interface NewEquipmentForm {
  name: string
  type: string
  manufacturer: string
  model: string
}

const EMPTY_FORM: NewEquipmentForm = {
  name: '',
  type: 'compressor',
  manufacturer: '',
  model: '',
}

export default function EquipmentPage() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const { data: equipmentData, isLoading } = useEquipment(facilityId!)
  const equipment = equipmentData?.equipment ?? []
  const createEquipment = useCreateEquipment(facilityId!)
  const deleteEquipment = useDeleteEquipment(facilityId!)

  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<NewEquipmentForm>(EMPTY_FORM)

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    createEquipment.mutate(
      {
        name: form.name,
        equipment_type: form.type,
        manufacturer: form.manufacturer || undefined,
        model: form.model || undefined,
      },
      {
        onSuccess: () => {
          toast.success('Equipment added')
          setForm(EMPTY_FORM)
          setShowForm(false)
        },
        onError: () => {
          toast.error('Failed to add equipment')
        },
      }
    )
  }

  function handleDelete(equipmentId: string) {
    if (!window.confirm('Delete this equipment?')) return
    deleteEquipment.mutate(equipmentId, {
      onSuccess: () => {
        toast.success('Equipment deleted')
      },
      onError: () => {
        toast.error('Failed to delete equipment')
      },
    })
  }

  if (isLoading) return <LoadingState />

  return (
    <div className="stack-lg">
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          className="btn-primary"
          onClick={() => setShowForm((v) => !v)}
        >
          <Plus size={16} />
          Add Equipment
        </button>
      </div>

      {showForm && (
        <div className="card">
          <div className="card-header">
            <Cpu size={16} />
            <span>New Equipment</span>
          </div>
          <form onSubmit={handleSubmit}>
            <div className="card-body">
              <div className="inline-form">
                <div className="field">
                  <label>Name *</label>
                  <input
                    type="text"
                    name="name"
                    value={form.name}
                    onChange={handleChange}
                    required
                    placeholder="e.g. Compressor #1"
                  />
                </div>
                <div className="field">
                  <label>Type</label>
                  <select name="type" value={form.type} onChange={handleChange}>
                    {EQUIPMENT_TYPES.map(({ value, label }) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label>Manufacturer</label>
                  <input
                    type="text"
                    name="manufacturer"
                    value={form.manufacturer}
                    onChange={handleChange}
                    placeholder="e.g. Copeland"
                  />
                </div>
                <div className="field">
                  <label>Model</label>
                  <input
                    type="text"
                    name="model"
                    value={form.model}
                    onChange={handleChange}
                    placeholder="e.g. ZR125KC"
                  />
                </div>
              </div>
            </div>
            <div className="modal-actions" style={{ borderTop: '1px solid var(--border)', padding: '0.75rem 1rem' }}>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setShowForm(false)
                  setForm(EMPTY_FORM)
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn-primary"
                disabled={createEquipment.isPending}
              >
                {createEquipment.isPending ? 'Saving…' : 'Save Equipment'}
              </button>
            </div>
          </form>
        </div>
      )}

      {equipment.length === 0 ? (
        <EmptyState
          icon={<Cpu size={32} />}
          title="No equipment yet"
          description="Add equipment to start tracking your refrigeration assets."
        />
      ) : (
        <div className="card">
          <div className="card-body">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Manufacturer</th>
                  <th>Model</th>
                  <th>Added</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {equipment.map((eq: any) => (
                  <tr key={eq.id}>
                    <td>
                      <span className="cell-primary">{eq.name}</span>
                    </td>
                    <td>
                      <span className="badge badge-info">{eq.type ?? '—'}</span>
                    </td>
                    <td>
                      <span className="cell-secondary">{eq.manufacturer ?? '—'}</span>
                    </td>
                    <td>
                      <span className="cell-secondary">{eq.model ?? '—'}</span>
                    </td>
                    <td>
                      <span className="cell-secondary">
                        {eq.created_at
                          ? new Date(eq.created_at).toLocaleDateString()
                          : '—'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="icon-btn icon-btn-sm"
                        onClick={() => handleDelete(eq.id)}
                        disabled={deleteEquipment.isPending}
                        title="Delete equipment"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
