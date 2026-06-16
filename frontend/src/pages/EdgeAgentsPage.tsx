/**
 * Edge Agents — IoT gateway management page.
 *
 * This is the control center for connecting refrigeration controllers
 * to Kelvex. The flow for a technician:
 *
 *   1. Register an agent (gets an API key)
 *   2. Pick a controller profile (Emerson E2, Danfoss AK-SC, etc.)
 *   3. Enter the controller's IP address on the site network
 *   4. Link it to a rack/site in Kelvex
 *   5. Download the config file → drop on the gateway device
 *   6. Data starts flowing
 */

import { useState } from 'react'
import toast from 'react-hot-toast'
import {
  Plus, X, Wifi, WifiOff, Download, RefreshCw, Copy, Check,
  ChevronDown, ChevronUp, HardDrive, Clock, AlertTriangle,
  Server, Plug, Circle, CheckCircle, Radar,
} from 'lucide-react'
import PageHeader from '../components/ui/PageHeader'
import StatCard from '../components/ui/StatCard'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { useSiteContext } from '../contexts/SiteContext'
import {
  useAgents, useRegisterAgent, useTestAgent, useScanNetwork,
  useDeviceProfiles, useAgentDevices, useAddAgentDevice, useRemoveAgentDevice,
  useAgentConfig, useDiscoveries, useApproveDiscovery,
} from '../hooks/useAgents'
import { useCompressorSummary } from '../hooks/useCompressors'
import type { EdgeAgent, AgentDevice, DiscoveredDevice } from '../lib/api'

// ── Main Page ──────────────────────────────────────

export default function EdgeAgentsPage() {
  const { site } = useSiteContext()
  const facilityId = site?.id
  const { data, isLoading } = useAgents(facilityId)
  const agents = data?.agents ?? []

  const [showRegister, setShowRegister] = useState(false)
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null)

  const connected = agents.filter(a => a.connection_state === 'connected').length
  const offline = agents.filter(a => a.connection_state !== 'connected').length

  if (!facilityId) {
    return (
      <div className="page-container">
        <PageHeader title="Edge Agents" subtitle="Select a facility to manage agents" />
        <EmptyState icon={<Server size={40} />} title="Select a facility from the sidebar to manage edge agents." />
      </div>
    )
  }

  return (
    <div className="page-container stack-lg">
      <PageHeader
        title="Edge Agents"
        subtitle="Connect your compressor controllers to Kelvex"
      >
        <button className="btn-primary" onClick={() => setShowRegister(true)}>
          <Plus size={15} /> New Agent
        </button>
      </PageHeader>

      <div className="stat-grid">
        <StatCard label="Total Agents" value={String(agents.length)} icon={<Server size={16} />} color="var(--accent)" />
        <StatCard label="Connected" value={String(connected)} icon={<Wifi size={16} />} color="var(--success)" />
        <StatCard label="Offline" value={String(offline)} icon={<WifiOff size={16} />} color={offline > 0 ? 'var(--danger)' : 'var(--text-tertiary)'} />
        <StatCard label="Facility" value={site?.name ?? ''} icon={<HardDrive size={16} />} color="var(--accent)" />
      </div>

      {showRegister && (
        <RegisterAgentCard
          facilityId={facilityId}
          onClose={() => setShowRegister(false)}
        />
      )}

      {isLoading ? (
        <LoadingState label="Loading agents..." />
      ) : agents.length === 0 && !showRegister ? (
        <EmptyState
          icon={<Server size={40} />}
          title="No edge agents registered"
          description="Register an agent to start connecting your compressor controllers to Kelvex."
          action={<button className="btn-primary" onClick={() => setShowRegister(true)}><Plus size={15} /> Register First Agent</button>}
        />
      ) : (
        <div className="stack-md">
          {agents.map(agent => (
            <AgentCard
              key={agent.id}
              agent={agent}
              facilityId={facilityId}
              expanded={expandedAgent === agent.id}
              onToggle={() => setExpandedAgent(expandedAgent === agent.id ? null : agent.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}


// ── Register Agent Card ────────────────────────────

function RegisterAgentCard({ facilityId, onClose }: { facilityId: string; onClose: () => void }) {
  const [name, setName] = useState('')
  const [hwType, setHwType] = useState('raspberry_pi')
  const registerMut = useRegisterAgent(facilityId)
  const [newAgentKey, setNewAgentKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    registerMut.mutate({ name: name.trim(), hardware_type: hwType }, {
      onSuccess: (agent) => {
        setNewAgentKey(agent.agent_key)
        toast.success('Agent registered')
      },
      onError: () => toast.error('Failed to register agent'),
    })
  }

  const copyKey = () => {
    if (newAgentKey) {
      navigator.clipboard.writeText(newAgentKey)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <span>Register New Agent</span>
        <button className="icon-btn" onClick={onClose}><X size={15} /></button>
      </div>
      <div className="card-body">
        {newAgentKey ? (
          <div className="stack-sm">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 16px', background: 'var(--bg-success-subtle, rgba(34,197,94,0.08))', borderRadius: 8, border: '1px solid var(--success)' }}>
              <Check size={16} style={{ color: 'var(--success)' }} />
              <span style={{ fontWeight: 600 }}>Agent registered successfully</span>
            </div>
            <div>
              <label className="field-label" style={{ display: 'block', marginBottom: 4, fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Agent Key (save this — it won't be shown again)</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <code style={{
                  flex: 1, padding: '10px 12px', background: 'var(--bg-tertiary)',
                  borderRadius: 6, fontSize: '0.82rem', fontFamily: 'monospace',
                  border: '1px solid var(--border-subtle)', wordBreak: 'break-all',
                }}>{newAgentKey}</code>
                <button className="btn-secondary" onClick={copyKey} style={{ whiteSpace: 'nowrap' }}>
                  {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy</>}
                </button>
              </div>
            </div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Next: expand the agent below and add your controller devices. Then download the config file and drop it on your gateway.
            </p>
            <button className="btn-primary" onClick={onClose}>Done</button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="stack-sm">
            <div className="field">
              <label className="field-label">Agent Name</label>
              <input
                type="text"
                placeholder="e.g. Engine Room Gateway"
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="field-label">Hardware Type</label>
              <select value={hwType} onChange={e => setHwType(e.target.value)}>
                <option value="raspberry_pi">Raspberry Pi</option>
                <option value="industrial_pc">Industrial PC (Moxa/Advantech)</option>
                <option value="vm">Virtual Machine</option>
                <option value="docker">Docker Container</option>
              </select>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit" className="btn-primary" disabled={registerMut.isPending || !name.trim()}>
                {registerMut.isPending ? 'Registering...' : 'Register Agent'}
              </button>
              <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}


// ── Agent Card (expandable) ────────────────────────

function AgentCard({ agent, facilityId, expanded, onToggle }: {
  agent: EdgeAgent
  facilityId: string
  expanded: boolean
  onToggle: () => void
}) {
  const testMut = useTestAgent(facilityId)
  const scanMut = useScanNetwork(facilityId)
  const isOnline = agent.connection_state === 'connected'

  const formatTime = (val: string | null) => {
    if (!val) return 'Never'
    const diff = Date.now() - new Date(val).getTime()
    const secs = Math.floor(diff / 1000)
    if (secs < 60) return `${secs}s ago`
    const mins = Math.floor(secs / 60)
    if (mins < 60) return `${mins}m ago`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}h ago`
    return `${Math.floor(hours / 24)}d ago`
  }

  return (
    <div className="card">
      <div
        className="card-header"
        style={{ cursor: 'pointer' }}
        onClick={onToggle}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Circle
            size={10}
            fill={isOnline ? 'var(--success)' : 'var(--text-tertiary)'}
            stroke="none"
          />
          <span style={{ fontWeight: 600 }}>{agent.name}</span>
          <span className={`badge ${isOnline ? 'badge-success' : 'badge-neutral'}`}>
            {isOnline ? 'Connected' : agent.connection_state}
          </span>
          {agent.version && (
            <span className="badge badge-neutral">v{agent.version}</span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
            <Clock size={11} style={{ verticalAlign: -1, marginRight: 3 }} />
            {formatTime(agent.last_heartbeat)}
          </span>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>

      {expanded && (
        <div className="card-body stack-md">
          {/* Agent info row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
            <InfoItem label="IP Address" value={agent.ip_address || ''} />
            <InfoItem label="Hardware" value={agent.hardware_type || ''} />
            <InfoItem label="Last Telemetry" value={formatTime(agent.last_telemetry_at)} />
            <InfoItem label="Pending Commands" value={String(agent.pending_commands)} />
          </div>

          {/* Resource bars */}
          {(agent.cpu_percent != null || agent.memory_percent != null) && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <MiniResourceBar label="CPU" value={agent.cpu_percent} />
              <MiniResourceBar label="Memory" value={agent.memory_percent} />
              <MiniResourceBar label="Disk" value={agent.disk_percent} />
            </div>
          )}

          {/* Discovery section */}
          <DiscoverySection facilityId={facilityId} agentId={agent.id} />

          {/* Devices section */}
          <AgentDevicesSection facilityId={facilityId} agentId={agent.id} />

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8, paddingTop: 8, borderTop: '1px solid var(--border-subtle)' }}>
            <button
              className="btn-primary"
              onClick={() => scanMut.mutate({ agentId: agent.id })}
              disabled={scanMut.isPending || !isOnline}
              title={!isOnline ? 'Agent must be online to scan' : ''}
            >
              <Radar size={14} /> {scanMut.isPending ? 'Scanning...' : 'Scan Network'}
            </button>
            <button
              className="btn-secondary"
              onClick={() => testMut.mutate(agent.id)}
              disabled={testMut.isPending}
            >
              <RefreshCw size={14} /> Test Connection
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


// ── Discovery Section ──────────────────────────────

function DiscoverySection({ facilityId, agentId }: { facilityId: string; agentId: string }) {
  const { data } = useDiscoveries(facilityId, agentId)
  const { data: profData } = useDeviceProfiles()
  const profiles = profData?.profiles ?? []
  const approveMut = useApproveDiscovery(facilityId, agentId)

  const devices = data?.devices ?? []
  const unprovisioned = devices.filter(d => !d.already_provisioned && !d.provisioned)

  if (unprovisioned.length === 0) return null

  return (
    <div className="stack-sm">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Radar size={14} style={{ color: 'var(--accent)' }} />
        <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600 }}>
          Discovered Devices ({unprovisioned.length})
        </h4>
        {data?.scan_timestamp && (
          <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
            Scanned {new Date(data.scan_timestamp).toLocaleString()}
          </span>
        )}
      </div>

      <div className="stack-xs">
        {unprovisioned.map((device, idx) => (
          <DiscoveryCard
            key={`${device.host}-${idx}`}
            device={device}
            profiles={profiles}
            onApprove={(approveData) => approveMut.mutate(approveData)}
            isApproving={approveMut.isPending}
          />
        ))}
      </div>
    </div>
  )
}


function DiscoveryCard({ device, profiles, onApprove, isApproving }: {
  device: DiscoveredDevice
  profiles: Array<{ id: string; display_name: string; manufacturer: string; model: string; default_port: number; default_slave_id: number }>
  onApprove: (data: Record<string, unknown>) => void
  isApproving: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const [compName, setCompName] = useState(
    device.device_info?.product_code
      ? `${device.device_info.vendor || ''} ${device.device_info.product_code}`.trim()
      : `Controller at ${device.host}`
  )
  const [tag, setTag] = useState('')
  const [hp, setHp] = useState('')
  const [refrigerant, setRefrigerant] = useState(
    device.matched_refrigerants?.[0] || 'NH3'
  )

  const matchedProfile = profiles.find(p => p.id === device.matched_profile_id)

  const handleApprove = () => {
    onApprove({
      host: device.host,
      port: device.port,
      slave_id: device.slave_id,
      profile_id: device.matched_profile_id || undefined,
      compressor_name: compName,
      tag: tag || undefined,
      manufacturer: device.matched_manufacturer || matchedProfile?.manufacturer,
      model: matchedProfile?.model,
      refrigerant,
      hp: hp ? parseFloat(hp) : undefined,
    })
  }

  return (
    <div style={{
      padding: '12px 14px', borderRadius: 8,
      border: '2px solid var(--accent)',
      background: 'var(--bg-accent-subtle, rgba(59,130,246,0.04))',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Circle size={8} fill="var(--accent)" stroke="none" />
            <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{device.host}:{device.port}</span>
            {device.matched_profile && (
              <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>
                <CheckCircle size={10} style={{ marginRight: 3 }} />
                {device.matched_profile}
              </span>
            )}
          </div>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)', paddingLeft: 16 }}>
            {device.protocol.replace('_', ' ').toUpperCase()} &middot; Slave {device.slave_id}
            {device.device_info?.vendor && <> &middot; {device.device_info.vendor}</>}
            {device.device_info?.firmware_version && <> &middot; FW {device.device_info.firmware_version}</>}
            {device.device_info?.serial && <> &middot; S/N {device.device_info.serial}</>}
          </div>
          {device.sample_values && Object.keys(device.sample_values).length > 0 && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', paddingLeft: 16, marginTop: 4 }}>
              Live: {Object.entries(device.sample_values).slice(0, 4).map(([k, v]) =>
                `${k.replace(/_/g, ' ')}: ${v}`
              ).join(' · ')}
            </div>
          )}
        </div>
        <button
          className="btn-secondary btn-sm"
          onClick={() => setExpanded(!expanded)}
          style={{ whiteSpace: 'nowrap' }}
        >
          {expanded ? 'Cancel' : 'Approve & Add'}
        </button>
      </div>

      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border-subtle)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
            <div className="field">
              <label className="field-label">Compressor Name</label>
              <input
                type="text"
                value={compName}
                onChange={e => setCompName(e.target.value)}
                placeholder="e.g. Compressor #1"
              />
            </div>
            <div className="field">
              <label className="field-label">Tag</label>
              <input
                type="text"
                value={tag}
                onChange={e => setTag(e.target.value)}
                placeholder="e.g. COMP-A1"
              />
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
            <div className="field">
              <label className="field-label">Refrigerant</label>
              <select value={refrigerant} onChange={e => setRefrigerant(e.target.value)}>
                <option value="NH3">NH3 (Ammonia)</option>
                <option value="R-404A">R-404A</option>
                <option value="CO2">CO2</option>
                <option value="R-22">R-22</option>
                <option value="R-448A">R-448A</option>
              </select>
            </div>
            <div className="field">
              <label className="field-label">Horsepower</label>
              <input
                type="number"
                value={hp}
                onChange={e => setHp(e.target.value)}
                placeholder="e.g. 350"
              />
            </div>
          </div>
          <button
            className="btn-primary"
            onClick={handleApprove}
            disabled={isApproving || !compName.trim()}
          >
            <CheckCircle size={14} />
            {isApproving ? 'Creating...' : 'Create Compressor & Start Monitoring'}
          </button>
        </div>
      )}
    </div>
  )
}


// ── Agent Devices Section ──────────────────────────

function AgentDevicesSection({ facilityId, agentId }: { facilityId: string; agentId: string }) {
  const { data: devData, isLoading: devLoading } = useAgentDevices(facilityId, agentId)
  const devices = devData?.devices ?? []
  const [showAddDevice, setShowAddDevice] = useState(false)
  const [showConfig, setShowConfig] = useState(false)
  const removeMut = useRemoveAgentDevice(facilityId, agentId)

  return (
    <div className="stack-sm">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: 0, fontSize: '0.9rem', fontWeight: 600 }}>
          <Plug size={14} style={{ verticalAlign: -2, marginRight: 6 }} />
          Controller Devices ({devices.length})
        </h4>
        <div style={{ display: 'flex', gap: 6 }}>
          {devices.length > 0 && (
            <button className="btn-secondary btn-sm" onClick={() => setShowConfig(!showConfig)}>
              <Download size={13} /> Config
            </button>
          )}
          <button className="btn-primary btn-sm" onClick={() => setShowAddDevice(true)}>
            <Plus size={13} /> Add Device
          </button>
        </div>
      </div>

      {showConfig && (
        <ConfigDownload facilityId={facilityId} agentId={agentId} onClose={() => setShowConfig(false)} />
      )}

      {showAddDevice && (
        <AddDeviceForm
          facilityId={facilityId}
          agentId={agentId}
          onClose={() => setShowAddDevice(false)}
        />
      )}

      {devLoading ? (
        <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: '0.82rem' }}>Loading devices...</div>
      ) : devices.length === 0 ? (
        <div style={{
          padding: '24px', textAlign: 'center', borderRadius: 8,
          border: '2px dashed var(--border-subtle)', color: 'var(--text-tertiary)',
        }}>
          <Plug size={24} style={{ marginBottom: 8, opacity: 0.5 }} />
          <p style={{ margin: 0, fontSize: '0.85rem' }}>No devices configured</p>
          <p style={{ margin: '4px 0 0', fontSize: '0.78rem' }}>
            Add a controller to start receiving compressor data
          </p>
        </div>
      ) : (
        <div className="stack-xs">
          {devices.map(device => (
            <DeviceRow
              key={device.id}
              device={device}
              onRemove={() => removeMut.mutate(device.id, {
                onSuccess: () => toast.success('Agent decommissioned'),
                onError: () => toast.error('Failed to remove device'),
              })}
            />
          ))}
        </div>
      )}
    </div>
  )
}


// ── Device Row ─────────────────────────────────────

function DeviceRow({ device, onRemove }: { device: AgentDevice; onRemove: () => void }) {
  const stateColor = device.connection_state === 'online'
    ? 'var(--success)' : device.connection_state === 'error'
    ? 'var(--danger)' : 'var(--text-tertiary)'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
      background: 'var(--bg-secondary)', borderRadius: 8,
      border: '1px solid var(--border-subtle)',
    }}>
      <Circle size={8} fill={stateColor} stroke="none" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{device.name}</div>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
          {device.host}:{device.port} &middot; Slave {device.slave_id} &middot;
          Poll {device.poll_interval_sec}s
          {device.poll_count > 0 && <> &middot; {device.poll_count.toLocaleString()} reads</>}
          {device.error_count > 0 && (
            <span style={{ color: 'var(--danger)' }}> &middot; {device.error_count} errors</span>
          )}
        </div>
      </div>
      {device.last_error && (
        <span title={device.last_error} style={{ cursor: 'help' }}>
          <AlertTriangle size={14} style={{ color: 'var(--warning)' }} />
        </span>
      )}
      <button className="icon-btn" onClick={onRemove} title="Remove device">
        <X size={14} />
      </button>
    </div>
  )
}


// ── Add Device Form (the wizard) ───────────────────

function AddDeviceForm({ facilityId, agentId, onClose }: {
  facilityId: string; agentId: string; onClose: () => void
}) {
  const { data: profData } = useDeviceProfiles()
  const profiles = profData?.profiles ?? []
  const { data: compData } = useCompressorSummary(facilityId)
  const compressors = compData?.compressors ?? []
  const addMut = useAddAgentDevice(facilityId, agentId)

  const [step, setStep] = useState(1)
  const [profileId, setProfileId] = useState<string>('')
  const [host, setHost] = useState('')
  const [port, setPort] = useState(502)
  const [slaveId, setSlaveId] = useState(1)
  const [name, setName] = useState('')
  const [compressorId, setCompressorId] = useState<string>('')
  const [pollInterval, setPollInterval] = useState(15)

  const selectedProfile = profiles.find(p => p.id === profileId)

  // When profile changes, update defaults
  const handleProfileChange = (id: string) => {
    setProfileId(id)
    const prof = profiles.find(p => p.id === id)
    if (prof) {
      setPort(prof.default_port)
      setSlaveId(prof.default_slave_id)
      if (!name) setName(`${prof.manufacturer} ${prof.model}`)
    }
  }

  const handleSubmit = () => {
    addMut.mutate({
      profile_id: profileId || undefined,
      compressor_id: compressorId || undefined,
      name: name.trim() || 'Unnamed Device',
      host,
      port,
      slave_id: slaveId,
      poll_interval_sec: pollInterval,
    }, {
      onSuccess: () => { toast.success('Agent updated'); onClose() },
      onError: () => toast.error('Failed to add device'),
    })
  }

  return (
    <div style={{
      padding: 16, borderRadius: 8, border: '1px solid var(--border-subtle)',
      background: 'var(--bg-secondary)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h4 style={{ margin: 0, fontSize: '0.9rem' }}>Add Controller Device — Step {step} of 3</h4>
        <button className="icon-btn" onClick={onClose}><X size={14} /></button>
      </div>

      {/* Step indicators */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {[1, 2, 3].map(s => (
          <div key={s} style={{
            flex: 1, height: 3, borderRadius: 2,
            background: s <= step ? 'var(--accent)' : 'var(--border-subtle)',
          }} />
        ))}
      </div>

      {step === 1 && (
        <div className="stack-sm">
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>
            Select the controller model. Kelvex has pre-built register maps for major manufacturers —
            the entire point mapping is done automatically.
          </p>
          <div className="field">
            <label className="field-label">Controller Model</label>
            <div className="stack-xs">
              {profiles.map(p => (
                <label
                  key={p.id}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 12, padding: '12px 14px',
                    borderRadius: 8, cursor: 'pointer',
                    border: `2px solid ${profileId === p.id ? 'var(--accent)' : 'var(--border-subtle)'}`,
                    background: profileId === p.id ? 'var(--bg-accent-subtle, rgba(59,130,246,0.05))' : 'transparent',
                  }}
                  onClick={() => handleProfileChange(p.id)}
                >
                  <input
                    type="radio"
                    checked={profileId === p.id}
                    onChange={() => handleProfileChange(p.id)}
                    style={{ marginTop: 2 }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{p.display_name}</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)', marginTop: 2 }}>
                      {p.protocol.replace('_', ' ').toUpperCase()} &middot;
                      {Object.keys(p.register_map).length} registers &middot;
                      {p.refrigerant_types.join(', ')}
                    </div>
                    {p.description && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginTop: 4, lineHeight: 1.4 }}>
                        {p.description}
                      </div>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn-secondary" onClick={onClose}>Cancel</button>
            <button
              className="btn-primary"
              disabled={!profileId}
              onClick={() => setStep(2)}
            >
              Next: Network Settings
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="stack-sm">
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>
            Enter the controller's network address on the plant network.
            The edge agent will use this to poll Modbus registers.
          </p>
          <div className="field">
            <label className="field-label">Device Name</label>
            <input
              type="text"
              placeholder="e.g. Compressor #1 Controller"
              value={name}
              onChange={e => setName(e.target.value)}
            />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 8 }}>
            <div className="field">
              <label className="field-label">IP Address</label>
              <input
                type="text"
                placeholder="192.168.1.50"
                value={host}
                onChange={e => setHost(e.target.value)}
              />
            </div>
            <div className="field" style={{ width: 80 }}>
              <label className="field-label">Port</label>
              <input
                type="number"
                value={port}
                onChange={e => setPort(+e.target.value)}
              />
            </div>
            <div className="field" style={{ width: 80 }}>
              <label className="field-label">Slave ID</label>
              <input
                type="number"
                value={slaveId}
                onChange={e => setSlaveId(+e.target.value)}
              />
            </div>
          </div>
          <div className="field" style={{ width: 140 }}>
            <label className="field-label">Poll Interval (sec)</label>
            <select value={pollInterval} onChange={e => setPollInterval(+e.target.value)}>
              <option value={5}>5s (fast)</option>
              <option value={10}>10s</option>
              <option value={15}>15s (default)</option>
              <option value={30}>30s</option>
              <option value={60}>60s</option>
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn-secondary" onClick={() => setStep(1)}>Back</button>
            <button
              className="btn-primary"
              disabled={!host.trim()}
              onClick={() => setStep(3)}
            >
              Next: Link Compressor
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="stack-sm">
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: 0 }}>
            Link this controller to a compressor in Kelvex. Telemetry data from this device
            will automatically populate that compressor's health dashboard.
          </p>

          {selectedProfile && (
            <div style={{
              padding: '10px 14px', borderRadius: 8,
              background: 'var(--bg-tertiary)', fontSize: '0.82rem',
            }}>
              <strong>{selectedProfile.display_name}</strong> at {host}:{port}
              <br />
              <span style={{ color: 'var(--text-tertiary)' }}>
                {Object.keys(selectedProfile.register_map).length} registers will be polled every {pollInterval}s
              </span>
            </div>
          )}

          <div className="field">
            <label className="field-label">Link to Compressor</label>
            <select
              value={compressorId}
              onChange={e => setCompressorId(e.target.value)}
            >
              <option value="">— Select compressor —</option>
              {compressors.map((c: any) => (
                <option key={c.compressor.id} value={c.compressor.id}>
                  {c.compressor.name} {c.compressor.tag ? `(${c.compressor.tag})` : ''}
                  {' — '}{c.compressor.manufacturer || 'Unknown'} {c.compressor.model || ''}
                </option>
              ))}
            </select>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginTop: 4, display: 'block' }}>
              Don't see your compressor? Add it on the Compressors page first.
            </span>
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn-secondary" onClick={() => setStep(2)}>Back</button>
            <button
              className="btn-primary"
              disabled={addMut.isPending}
              onClick={handleSubmit}
            >
              {addMut.isPending ? 'Adding...' : 'Add Device'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


// ── Config Download ────────────────────────────────

function ConfigDownload({ facilityId, agentId, onClose }: {
  facilityId: string; agentId: string; onClose: () => void
}) {
  const { data: config, isLoading } = useAgentConfig(facilityId, agentId)
  const [copied, setCopied] = useState(false)

  if (isLoading || !config) {
    return <div style={{ padding: 16, textAlign: 'center', fontSize: '0.82rem', color: 'var(--text-tertiary)' }}>Generating config...</div>
  }

  // Generate YAML-like config for the edge agent
  const yamlConfig = `# Kelvex Edge Agent Configuration
# Generated: ${new Date().toISOString()}
# Drop this file at /etc/kelvex/agent.yaml on your gateway device

agent:
  name: "${config.agent_name}"
  key: "${config.agent_key}"

platform:
  url: "${config.platform_url}"
  heartbeat_interval_sec: ${config.heartbeat_interval_sec}

devices:
${config.devices.map(d => `  - name: "${d.name}"
    host: "${d.host}"
    port: ${d.port}
    slave_id: ${d.slave_id}
    protocol: ${d.protocol}
    poll_interval_sec: ${d.poll_interval_sec}
    compressor_id: "${d.compressor_id || ''}"
    registers:
${Object.entries(d.registers).map(([key, val]: [string, any]) =>
  `      ${key}: { register: ${val.register}, type: "${val.type}", data_type: "${val.data_type}", scale: ${val.scale}, unit: "${val.unit}" }`
).join('\n')}`).join('\n')}
`

  const handleCopy = () => {
    navigator.clipboard.writeText(yamlConfig)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    const blob = new Blob([yamlConfig], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `kelvex-agent-${config.agent_name.toLowerCase().replace(/\s+/g, '-')}.yaml`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div style={{
      padding: 16, borderRadius: 8, border: '1px solid var(--border-subtle)',
      background: 'var(--bg-tertiary)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h4 style={{ margin: 0, fontSize: '0.85rem' }}>Agent Configuration</h4>
        <button className="icon-btn" onClick={onClose}><X size={14} /></button>
      </div>
      <pre style={{
        padding: 12, borderRadius: 6, background: 'var(--bg-primary)',
        border: '1px solid var(--border-subtle)', fontSize: '0.75rem',
        overflow: 'auto', maxHeight: 300, margin: '0 0 12px',
        fontFamily: 'monospace', lineHeight: 1.5,
      }}>{yamlConfig}</pre>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn-primary btn-sm" onClick={handleDownload}>
          <Download size={13} /> Download YAML
        </button>
        <button className="btn-secondary btn-sm" onClick={handleCopy}>
          {copied ? <><Check size={13} /> Copied</> : <><Copy size={13} /> Copy</>}
        </button>
      </div>
      <p style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', margin: '8px 0 0' }}>
        Place this file at <code>/etc/kelvex/agent.yaml</code> on your gateway and run
        <code style={{ marginLeft: 4 }}>kelvex-agent start</code>
      </p>
    </div>
  )
}


// ── Utility Components ─────────────────────────────

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: '0.85rem', fontWeight: 500 }}>{value}</div>
    </div>
  )
}

function MiniResourceBar({ label, value }: { label: string; value: number | null }) {
  if (value == null) return null
  const color = value > 90 ? 'var(--danger)' : value > 70 ? 'var(--warning)' : 'var(--success)'
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', marginBottom: 3 }}>
        <span style={{ color: 'var(--text-tertiary)' }}>{label}</span>
        <span style={{ fontWeight: 600 }}>{Math.round(value)}%</span>
      </div>
      <div style={{ height: 4, borderRadius: 2, background: 'var(--border-subtle)' }}>
        <div style={{ width: `${Math.min(value, 100)}%`, height: '100%', borderRadius: 2, background: color, transition: 'width 0.3s' }} />
      </div>
    </div>
  )
}
