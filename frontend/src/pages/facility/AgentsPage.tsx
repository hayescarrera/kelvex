import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Wifi, WifiOff, Loader2, Download, Copy, Check, Terminal, Save } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAgents, useRegisterAgent, useUpdateAgent } from '../../hooks/useAgents'
import { api, type EdgeAgent, type AgentConfigBundle } from '../../lib/api'
import ResourceBar from '../../components/ui/ResourceBar'

function buildYaml(cfg: AgentConfigBundle): string {
  const lines: string[] = [
    `agent:`,
    `  name: "${cfg.agent_name}"`,
    `  key: "${cfg.agent_key}"`,
    ``,
    `platform:`,
    `  url: "${cfg.platform_url}"`,
    `  heartbeat_interval_sec: ${cfg.heartbeat_interval_sec}`,
    ``,
    `local:`,
    `  web_port: 8080`,
    `  web_enabled: true`,
    `  buffer_path: "/var/lib/kelvex/buffer.db"`,
    `  buffer_max_mb: 500`,
    ``,
  ]

  if (cfg.devices.length > 0) {
    lines.push(`devices:`)
    for (const d of cfg.devices) {
      lines.push(`  - name: "${d.name}"`)
      lines.push(`    host: "${d.host}"`)
      lines.push(`    port: ${d.port}`)
      lines.push(`    slave_id: ${d.slave_id}`)
      lines.push(`    protocol: "${d.protocol}"`)
      lines.push(`    poll_interval_sec: ${d.poll_interval_sec}`)
      if (d.compressor_id) lines.push(`    compressor_id: "${d.compressor_id}"`)
      if (d.registers && Object.keys(d.registers).length > 0) {
        lines.push(`    registers:`)
        for (const [regName, regCfg] of Object.entries(d.registers as Record<string, Record<string, unknown>>)) {
          lines.push(`      ${regName}:`)
          for (const [k, v] of Object.entries(regCfg)) {
            lines.push(`        ${k}: ${typeof v === 'string' ? `"${v}"` : v}`)
          }
        }
      }
    }
  } else {
    lines.push(`# No compressor devices configured yet.`)
    lines.push(`# Add devices via the platform or use the network scan to discover them.`)
    lines.push(`devices: []`)
  }

  const zoneSensors = (cfg as typeof cfg & { zone_sensors?: unknown[] }).zone_sensors ?? []
  if (zoneSensors.length > 0) {
    lines.push(``)
    lines.push(`zone_sensors:`)
    for (const s of zoneSensors as Record<string, unknown>[]) {
      lines.push(`  - sensor_id: "${s.sensor_id}"`)
      lines.push(`    zone_id: "${s.zone_id}"`)
      lines.push(`    name: "${s.name}"`)
      lines.push(`    sensor_type: "${s.sensor_type}"`)
      lines.push(`    unit: "${s.unit}"`)
      lines.push(`    host: "${s.host}"`)
      lines.push(`    port: ${s.port}`)
      lines.push(`    slave_id: ${s.slave_id}`)
      lines.push(`    register_address: ${s.register_address}`)
      lines.push(`    register_type: "${s.register_type}"`)
      lines.push(`    data_type: "${s.data_type}"`)
      lines.push(`    scale: ${s.scale}`)
      lines.push(`    offset: ${s.offset}`)
      lines.push(`    poll_interval_sec: ${s.poll_interval_sec}`)
    }
  }

  return lines.join('\n') + '\n'
}

function downloadYaml(yaml: string, agentName: string) {
  const blob = new Blob([yaml], { type: 'text/yaml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${agentName.replace(/\s+/g, '-').toLowerCase()}-agent.yaml`
  a.click()
  URL.revokeObjectURL(url)
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={copy} className="btn-ghost" style={{ padding: '0.2rem 0.5rem', fontSize: '0.78rem' }}>
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function NewAgentSetup({ agent, facilityId }: { agent: EdgeAgent; facilityId: string }) {
  const [loading, setLoading] = useState(false)
  const [installCmd, setInstallCmd] = useState<string | null>(null)

  const handleGenerate = async () => {
    setLoading(true)
    try {
      const result = await api.createSetupToken(facilityId, agent.id)
      setInstallCmd(result.install_command)
    } catch {
      toast.error('Failed to generate install command')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card" style={{ borderColor: 'var(--accent)', marginBottom: '1rem' }}>
      <div className="card-header" style={{ background: 'var(--accent-subtle, rgba(99,102,241,0.08))' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Terminal size={14} />
          Agent registered: <strong>{agent.name}</strong>
        </span>
      </div>
      <div className="card-body stack-md">
        <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', margin: 0 }}>
          Run one command on the gateway device. It installs the agent, writes your config,
          and starts the service automatically.
        </p>

        {!installCmd ? (
          <button
            className="btn-primary"
            onClick={handleGenerate}
            disabled={loading}
            style={{ fontSize: '0.84rem', alignSelf: 'flex-start' }}
          >
            {loading ? <Loader2 size={13} className="spin" /> : <Terminal size={13} />}
            {loading ? 'Generating...' : 'Get Install Command'}
          </button>
        ) : (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>Paste this into the terminal on your gateway device</span>
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--surface-2)', borderRadius: 6, padding: '0.6rem 0.75rem',
              border: '1px solid var(--border)',
            }}>
              <code style={{ flex: 1, fontSize: '0.78rem', wordBreak: 'break-all' }}>{installCmd}</code>
              <CopyButton text={installCmd} />
            </div>
            <p style={{ fontSize: '0.77rem', color: 'var(--text-muted)', marginTop: 6 }}>
              Link expires in 60 minutes. Auto-detects x86-64 / ARM64 / ARMv7 and installs a
              systemd service that starts on boot.
            </p>
            <button
              className="btn-ghost"
              onClick={handleGenerate}
              disabled={loading}
              style={{ fontSize: '0.78rem', marginTop: 4 }}
            >
              {loading ? <Loader2 size={11} className="spin" /> : null}
              Regenerate
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function AgentsPage() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const [agentName, setAgentName] = useState('')
  const [newAgent, setNewAgent] = useState<EdgeAgent | null>(null)

  const { data, isLoading } = useAgents(facilityId!)
  const agents = data?.agents ?? []
  const registerMutation = useRegisterAgent(facilityId!)

  const handleRegister = (e: React.FormEvent) => {
    e.preventDefault()
    if (!agentName.trim()) return
    registerMutation.mutate({ name: agentName.trim() }, {
      onSuccess: (agent) => {
        setAgentName('')
        setNewAgent(agent)
      },
      onError: () => {
        toast.error('Failed to register agent')
      },
    })
  }

  const formatHeartbeat = (val: string | null | undefined) => {
    if (!val) return 'Never'
    const diff = Date.now() - new Date(val).getTime()
    const secs = Math.floor(diff / 1000)
    if (secs < 60) return `${secs}s ago`
    const mins = Math.floor(secs / 60)
    if (mins < 60) return `${mins}m ago`
    return `${Math.floor(mins / 60)}h ago`
  }

  const connectionBadge = (state: string) => {
    const connected = state === 'connected' || state === 'online'
    return (
      <span className={`badge ${connected ? 'badge-success' : 'badge-neutral'}`}
        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
        {connected ? <Wifi size={11} /> : <WifiOff size={11} />}
        {state}
      </span>
    )
  }

  return (
    <div className="stack-lg">
      {newAgent && facilityId && (
        <NewAgentSetup agent={newAgent} facilityId={facilityId} />
      )}

      <div className="card">
        <div className="card-header">
          <span>Register Agent</span>
        </div>
        <div className="card-body">
          <form className="inline-form" onSubmit={handleRegister}>
            <div className="field">
              <input
                type="text"
                placeholder="Agent name (e.g. warehouse-01)"
                value={agentName}
                onChange={e => setAgentName(e.target.value)}
                disabled={registerMutation.isPending}
              />
            </div>
            <button
              type="submit"
              className="btn-primary"
              disabled={registerMutation.isPending || !agentName.trim()}
            >
              {registerMutation.isPending ? <Loader2 size={15} className="spin" /> : null}
              Register
            </button>
          </form>
          {registerMutation.isError && (
            <p className="text-muted" style={{ color: 'var(--color-danger, #ef4444)', marginTop: '0.5rem' }}>
              Registration failed. Please try again.
            </p>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span>Agents ({agents.length})</span>
        </div>
        <div className="card-body">
          {isLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
              <Loader2 size={24} className="spin" />
            </div>
          ) : agents.length === 0 ? (
            <div className="empty-state">
              <p>No agents registered</p>
              <p className="text-muted">Register an agent above to get started</p>
            </div>
          ) : (
            <div className="agent-grid">
              {agents.map((agent: EdgeAgent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  facilityId={facilityId!}
                  connectionBadge={connectionBadge}
                  formatHeartbeat={formatHeartbeat}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function AgentCard({
  agent,
  facilityId,
  connectionBadge,
  formatHeartbeat,
}: {
  agent: EdgeAgent
  facilityId: string
  connectionBadge: (state: string) => React.ReactNode
  formatHeartbeat: (val: string | null | undefined) => string
}) {
  const [downloading, setDownloading] = useState(false)
  const [editingUrl, setEditingUrl] = useState(false)
  const [urlValue, setUrlValue] = useState(agent.controller_url ?? '')
  const updateAgent = useUpdateAgent(facilityId)

  const handleDownload = async () => {
    setDownloading(true)
    try {
      const cfg = await api.getAgentConfig(facilityId, agent.id)
      const yaml = buildYaml(cfg)
      downloadYaml(yaml, agent.name)
    } catch {
      toast.error('Failed to generate config')
    } finally {
      setDownloading(false)
    }
  }

  const handleSaveUrl = () => {
    updateAgent.mutate(
      { agentId: agent.id, data: { controller_url: urlValue || null } },
      { onSuccess: () => setEditingUrl(false) }
    )
  }

  return (
    <div className="agent-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
        <span className="cell-primary" style={{ fontWeight: 600 }}>{agent.name}</span>
        {connectionBadge(agent.connection_state ?? 'offline')}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.25rem 0.75rem', fontSize: '0.82rem', marginBottom: '0.75rem' }}>
        {agent.hardware_type && (
          <>
            <span className="text-muted">Hardware</span>
            <span>{agent.hardware_type}</span>
          </>
        )}
        {agent.version && (
          <>
            <span className="text-muted">Version</span>
            <span>{agent.version}</span>
          </>
        )}
        {agent.ip_address && (
          <>
            <span className="text-muted">IP</span>
            <span>{agent.ip_address}</span>
          </>
        )}
        <span className="text-muted">Last Heartbeat</span>
        <span>{formatHeartbeat(agent.last_heartbeat)}</span>
      </div>

      {agent.cpu_percent != null && (
        <ResourceBar label="CPU" value={agent.cpu_percent} color="var(--accent)" />
      )}
      {agent.memory_percent != null && (
        <ResourceBar label="Memory" value={agent.memory_percent} color="var(--success)" />
      )}
      {agent.disk_percent != null && (
        <ResourceBar label="Disk" value={agent.disk_percent} color="var(--warning)" />
      )}

      {/* Controller URL */}
      <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border)' }}>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 4 }}>Controller URL</div>
        {editingUrl ? (
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              type="text"
              value={urlValue}
              onChange={e => setUrlValue(e.target.value)}
              placeholder="http://192.168.1.50"
              style={{ flex: 1, fontSize: '0.8rem', padding: '3px 8px' }}
              autoFocus
            />
            <button className="btn-primary" onClick={handleSaveUrl} disabled={updateAgent.isPending}
              style={{ fontSize: '0.78rem', padding: '3px 8px' }}>
              {updateAgent.isPending ? <Loader2 size={11} className="spin" /> : <Save size={11} />}
            </button>
            <button className="btn-ghost" onClick={() => { setEditingUrl(false); setUrlValue(agent.controller_url ?? '') }}
              style={{ fontSize: '0.78rem', padding: '3px 8px' }}>✕</button>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {agent.controller_url ? (
              <>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {agent.controller_url}
                </span>
                <button className="btn-ghost" onClick={() => setEditingUrl(true)}
                  style={{ fontSize: '0.75rem', padding: '2px 6px' }}>Edit</button>
              </>
            ) : (
              <button className="btn-ghost" onClick={() => setEditingUrl(true)}
                style={{ fontSize: '0.78rem', padding: '2px 6px', color: 'var(--text-muted)' }}>
                + Set controller URL
              </button>
            )}
          </div>
        )}
      </div>

      <div style={{ marginTop: '0.5rem' }}>
        <button
          className="btn-ghost"
          onClick={handleDownload}
          disabled={downloading}
          style={{ fontSize: '0.8rem', width: '100%' }}
        >
          {downloading ? <Loader2 size={12} className="spin" /> : <Download size={12} />}
          Download config
        </button>
      </div>
    </div>
  )
}
