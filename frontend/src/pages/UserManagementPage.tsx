import { useState, useMemo } from 'react'
import toast from 'react-hot-toast'
import {
  Users, UserPlus, Shield, Building2, ChevronDown,
  MoreVertical, X, Check, Eye, EyeOff,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useSiteContext } from '../contexts/SiteContext'
import { useOrgMembers, useInviteMember, useUpdateMember, useRemoveMember } from '../hooks/useMembers'
import LoadingState from '../components/ui/LoadingState'
import {
  ROLE_LABELS, ROLE_ORDER, GLOBAL_ACCESS_ROLES,
  type UserRole, type OrgMember,
} from '../lib/api'

// ── Role badge color ────────────────────────────
function roleBadgeClass(role: UserRole): string {
  switch (role) {
    case 'owner': return 'badge badge-danger'
    case 'admin': return 'badge badge-warning'
    case 'plant_manager': return 'badge badge-info'
    case 'technician': return 'badge badge-success'
    case 'operator': return 'badge badge-default'
    case 'viewer': return 'badge badge-muted'
    default: return 'badge'
  }
}

// ── Invite Modal ────────────────────────────────
function InviteModal({ onClose }: { onClose: () => void }) {
  const { facilities } = useSiteContext()
  const invite = useInviteMember()
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('operator')
  const [selectedFacilities, setSelectedFacilities] = useState<string[]>([])
  const [showPassword, setShowPassword] = useState(false)

  const needsFacilityAccess = !GLOBAL_ACCESS_ROLES.includes(role)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    invite.mutate(
      {
        email,
        full_name: fullName,
        password,
        role,
        facility_ids: needsFacilityAccess ? selectedFacilities : [],
      },
      {
        onSuccess: () => { toast.success('Invite sent'); onClose() },
        onError: () => toast.error('Failed to send invite'),
      }
    )
  }

  const toggleFacility = (id: string) => {
    setSelectedFacilities(prev =>
      prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
    )
  }

  // Can't assign owner role through invite
  const assignableRoles = ROLE_ORDER.filter(r => r !== 'owner')

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <UserPlus size={18} /> Invite Team Member
          </h3>
          <button className="icon-btn" onClick={onClose}><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label className="form-label">Full Name</label>
              <input className="form-input" value={fullName} onChange={e => setFullName(e.target.value)} required placeholder="Jane Smith" />
            </div>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input className="form-input" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="jane@company.com" />
            </div>
            <div className="form-group">
              <label className="form-label">Temporary Password</label>
              <div style={{ position: 'relative' }}>
                <input
                  className="form-input"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  minLength={8}
                  placeholder="Min 8 characters"
                  style={{ paddingRight: 40 }}
                />
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)' }}
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Role</label>
              <div style={{ position: 'relative' }}>
                <select className="form-input" value={role} onChange={e => setRole(e.target.value as UserRole)}>
                  {assignableRoles.map(r => (
                    <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                  ))}
                </select>
                <ChevronDown size={14} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', opacity: 0.5 }} />
              </div>
              <span className="form-hint" style={{ marginTop: 4, fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>
                {role === 'admin' && 'Full access to all facilities and settings'}
                {role === 'plant_manager' && 'Manage automation, energy, and controls for assigned facilities'}
                {role === 'technician' && 'Control compressors and adjust setpoints at assigned facilities'}
                {role === 'operator' && 'View dashboards and trigger basic controls at assigned facilities'}
                {role === 'viewer' && 'Read-only access to assigned facilities'}
              </span>
            </div>

            {needsFacilityAccess && (
              <div className="form-group">
                <label className="form-label">Facility Access</label>
                {facilities.length === 0 ? (
                  <p style={{ color: 'var(--text-tertiary)', fontSize: '0.85rem' }}>No facilities found.</p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 160, overflow: 'auto' }}>
                    {facilities.map(f => (
                      <label key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.85rem' }}>
                        <input
                          type="checkbox"
                          checked={selectedFacilities.includes(f.id)}
                          onChange={() => toggleFacility(f.id)}
                        />
                        <Building2 size={14} style={{ opacity: 0.5 }} />
                        {f.name}
                        {f.city && f.state && <span style={{ color: 'var(--text-tertiary)', marginLeft: 4 }}>({f.city}, {f.state})</span>}
                      </label>
                    ))}
                  </div>
                )}
                {selectedFacilities.length === 0 && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--warning)' }}>
                    User won't see any facilities until assigned
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={invite.isPending}>
              {invite.isPending ? 'Inviting...' : 'Send Invite'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Edit Member Modal ───────────────────────────
function EditMemberModal({
  member, onClose,
}: { member: OrgMember; onClose: () => void }) {
  const { facilities } = useSiteContext()
  const { user: currentUser } = useAuth()
  const update = useUpdateMember()
  const [role, setRole] = useState<UserRole>(member.role)
  const [selectedFacilities, setSelectedFacilities] = useState<string[]>(
    member.facility_access.map(fa => fa.facility_id)
  )

  const needsFacilityAccess = !GLOBAL_ACCESS_ROLES.includes(role)
  const isOwner = member.role === 'owner'
  const isSelf = currentUser?.id === member.id

  // Can't change owner role and can't change own role
  const assignableRoles = ROLE_ORDER.filter(r => r !== 'owner')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    update.mutate(
      {
        userId: member.id,
        data: {
          role,
          facility_ids: needsFacilityAccess ? selectedFacilities : undefined,
        },
      },
      {
        onSuccess: () => { toast.success('Member role updated'); onClose() },
        onError: () => toast.error('Failed to update member'),
      }
    )
  }

  const toggleFacility = (id: string) => {
    setSelectedFacilities(prev =>
      prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3 style={{ margin: 0 }}>Edit {member.full_name}</h3>
          <button className="icon-btn" onClick={onClose}><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '8px 12px', background: 'var(--bg-tertiary)', borderRadius: 8 }}>
              <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'var(--accent)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 600, fontSize: '0.85rem' }}>
                {member.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)}
              </div>
              <div>
                <div style={{ fontWeight: 500 }}>{member.full_name}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)' }}>{member.email}</div>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Role</label>
              <select
                className="form-input"
                value={role}
                onChange={e => setRole(e.target.value as UserRole)}
                disabled={isOwner || isSelf}
              >
                {isOwner && <option value="owner">Owner</option>}
                {assignableRoles.map(r => (
                  <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                ))}
              </select>
              {isOwner && <span className="form-hint" style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>Owner role cannot be changed</span>}
              {isSelf && !isOwner && <span className="form-hint" style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>You cannot change your own role</span>}
            </div>

            {needsFacilityAccess && (
              <div className="form-group">
                <label className="form-label">Facility Access</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflow: 'auto' }}>
                  {facilities.map(f => (
                    <label key={f.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: '0.85rem' }}>
                      <input
                        type="checkbox"
                        checked={selectedFacilities.includes(f.id)}
                        onChange={() => toggleFacility(f.id)}
                      />
                      <Building2 size={14} style={{ opacity: 0.5 }} />
                      {f.name}
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={update.isPending || isOwner || isSelf}>
              {update.isPending ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Member Row ──────────────────────────────────
function MemberRow({
  member,
  canManage,
  isSelf,
  onEdit,
}: {
  member: OrgMember
  canManage: boolean
  isSelf: boolean
  onEdit: () => void
}) {
  const update = useUpdateMember()
  const remove = useRemoveMember()
  const [showMenu, setShowMenu] = useState(false)

  const initials = member.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)

  const toggleActive = () => {
    update.mutate({ userId: member.id, data: { is_active: !member.is_active } }, {
      onSuccess: () => toast.success('Member role updated'),
      onError: () => toast.error('Failed to update member'),
    })
  }

  const handleRemove = () => {
    if (confirm(`Remove ${member.full_name} from the organization?`)) {
      remove.mutate(member.id, {
        onSuccess: () => toast.success('Member removed'),
        onError: () => toast.error('Failed to remove member'),
      })
    }
  }

  const facilityLabel = GLOBAL_ACCESS_ROLES.includes(member.role)
    ? 'All facilities'
    : member.facility_access.length === 0
    ? 'No facilities assigned'
    : `${member.facility_access.length} facilit${member.facility_access.length === 1 ? 'y' : 'ies'}`

  return (
    <tr style={{ opacity: member.is_active ? 1 : 0.5 }}>
      <td>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%',
            background: isSelf ? 'var(--accent)' : 'var(--bg-tertiary)',
            color: isSelf ? '#fff' : 'var(--text-secondary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 600, fontSize: '0.75rem', flexShrink: 0,
          }}>
            {initials}
          </div>
          <div>
            <div style={{ fontWeight: 500, fontSize: '0.85rem' }}>
              {member.full_name} {isSelf && <span style={{ color: 'var(--text-tertiary)', fontWeight: 400 }}>(you)</span>}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>{member.email}</div>
          </div>
        </div>
      </td>
      <td><span className={roleBadgeClass(member.role)}>{ROLE_LABELS[member.role]}</span></td>
      <td>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem' }}>
          <Building2 size={13} style={{ opacity: 0.4 }} />
          <span style={{ color: member.facility_access.length === 0 && !GLOBAL_ACCESS_ROLES.includes(member.role) ? 'var(--warning)' : 'var(--text-secondary)' }}>
            {facilityLabel}
          </span>
        </div>
        {!GLOBAL_ACCESS_ROLES.includes(member.role) && member.facility_access.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
            {member.facility_access.map(fa => (
              <span key={fa.facility_id} className="badge badge-muted" style={{ fontSize: '0.7rem' }}>
                {fa.facility_name || fa.facility_id.slice(0, 8)}
              </span>
            ))}
          </div>
        )}
      </td>
      <td>
        <span className={`badge ${member.is_active ? 'badge-success' : 'badge-muted'}`}>
          {member.is_active ? 'Active' : 'Disabled'}
        </span>
      </td>
      <td style={{ textAlign: 'right', position: 'relative' }}>
        {canManage && !isSelf && member.role !== 'owner' && (
          <>
            <button className="icon-btn" onClick={() => setShowMenu(!showMenu)}>
              <MoreVertical size={15} />
            </button>
            {showMenu && (
              <div className="dropdown-menu" style={{
                position: 'absolute', right: 0, top: '100%', zIndex: 20,
                background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)',
                borderRadius: 8, padding: 4, minWidth: 160, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              }}>
                <button className="dropdown-item" onClick={() => { setShowMenu(false); onEdit() }}>
                  <Shield size={13} /> Edit Role & Access
                </button>
                <button className="dropdown-item" onClick={() => { setShowMenu(false); toggleActive() }}>
                  {member.is_active ? <EyeOff size={13} /> : <Check size={13} />}
                  {member.is_active ? 'Disable Account' : 'Enable Account'}
                </button>
                <button className="dropdown-item" style={{ color: 'var(--danger)' }} onClick={() => { setShowMenu(false); handleRemove() }}>
                  <X size={13} /> Remove Member
                </button>
              </div>
            )}
          </>
        )}
      </td>
    </tr>
  )
}

// ── Main Page ───────────────────────────────────
export default function UserManagementPage() {
  const { user: currentUser, hasPermission } = useAuth()
  const { data, isLoading } = useOrgMembers()
  const [showInvite, setShowInvite] = useState(false)
  const [editingMember, setEditingMember] = useState<OrgMember | null>(null)

  const canManage = hasPermission('users:invite')
  const members = data?.members ?? []

  const stats = useMemo(() => ({
    total: members.length,
    active: members.filter(m => m.is_active).length,
    admins: members.filter(m => m.role === 'owner' || m.role === 'admin').length,
    operators: members.filter(m => m.role === 'operator' || m.role === 'technician').length,
  }), [members])

  if (isLoading) {
    return <LoadingState />
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Users size={22} /> Team Management
          </h1>
          <p className="page-subtitle">Manage team members, roles, and facility access</p>
        </div>
        {canManage && (
          <button className="btn-primary" onClick={() => setShowInvite(true)}>
            <UserPlus size={15} /> Invite Member
          </button>
        )}
      </div>

      {/* Stats */}
      <div className="stat-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 24 }}>
        <div className="stat-card">
          <div className="stat-label">Total Members</div>
          <div className="stat-value">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Active</div>
          <div className="stat-value">{stats.active}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Admins</div>
          <div className="stat-value">{stats.admins}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Operators & Techs</div>
          <div className="stat-value">{stats.operators}</div>
        </div>
      </div>

      {/* Members table */}
      <div className="card">
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ width: '100%' }}>
            <thead>
              <tr>
                <th>Member</th>
                <th>Role</th>
                <th>Facility Access</th>
                <th>Status</th>
                <th style={{ width: 50 }}></th>
              </tr>
            </thead>
            <tbody>
              {members.map(m => (
                <MemberRow
                  key={m.id}
                  member={m}
                  canManage={canManage}
                  isSelf={m.id === currentUser?.id}
                  onEdit={() => setEditingMember(m)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Role reference */}
      <div className="card" style={{ marginTop: 24 }}>
        <h3 style={{ marginTop: 0, fontSize: '0.95rem' }}>
          <Shield size={15} style={{ verticalAlign: '-2px', marginRight: 6 }} />
          Role Permissions
        </h3>
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ width: '100%', fontSize: '0.8rem' }}>
            <thead>
              <tr>
                <th>Capability</th>
                {ROLE_ORDER.map(r => <th key={r} style={{ textAlign: 'center' }}>{ROLE_LABELS[r]}</th>)}
              </tr>
            </thead>
            <tbody>
              {[
                ['View dashboards', true, true, true, true, true, true],
                ['Control compressors', true, true, true, true, false, false],
                ['Trigger defrost/start-stop', true, true, true, true, true, false],
                ['Manage automation', true, true, true, false, false, false],
                ['View energy & bills', true, true, true, true, false, false],
                ['Manage agents', true, true, true, false, false, false],
                ['Invite & manage users', true, true, false, false, false, false],
                ['Edit org settings', true, true, false, false, false, false],
                ['All facilities (auto)', true, true, false, false, false, false],
              ].map(([label, ...perms]) => (
                <tr key={label as string}>
                  <td>{label as string}</td>
                  {(perms as boolean[]).map((has, i) => (
                    <td key={i} style={{ textAlign: 'center' }}>
                      {has ? <Check size={14} style={{ color: 'var(--success)' }} /> : <span style={{ color: 'var(--text-tertiary)', fontSize: 10 }}>·</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showInvite && <InviteModal onClose={() => setShowInvite(false)} />}
      {editingMember && <EditMemberModal member={editingMember} onClose={() => setEditingMember(null)} />}
    </div>
  )
}
