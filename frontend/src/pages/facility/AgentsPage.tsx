import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Wifi, WifiOff, Loader2, Download, Copy, Check, Terminal } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAgents, useRegisterAgent } from '../../hooks/useAgents'
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
    lines.push(`# No devices configured yet. Add devices via the platform,`)
    lines.push(`# or let the agent auto-discover via network scan.`)
    lines.push(`devices: []`)
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
  const [downloading, setDownloading] = useState(false)

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

  const installCmd = `curl -fsSL https://github.com/hayescarrera/kelvex/releases/latest/download/install.sh | sudo bash`

  return (
    <div className="card" style={{ borderColor: 'var(--accent)', marginBottom: '1rem' }}>
      <div className="card-header" style={{ background: 'var(--accent-subtle, rgba(99,102,241,0.08))' }}>
        <span>Agent registered: <strong>{agent.name}</strong></span>
      </div>
      <div className="card-body stack-md">
        <p className="text-muted" style={{ fontSize: '0.88rem' }}>
          Follow these steps on the gateway device (Raspberry Pi, Intel NUC, etc.):
        </p>

        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
            <Terminal size={14} />
            <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>1. Install the agent</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'var(--surface-2)', borderRadius: '6px', padding: '0.5rem 0.75rem' }}>
            <code style={{ flex: 1, fontSize: '0.78rem', wordBreak: 'break-all' }}>{installCmd}</code>
            <CopyButton text={installCmd} />
          </div>
        </div>

        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
            <Download size={14} />
            <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>2. Download and copy your config</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button className="btn-primary" onClick={handleDownload} disabled={downloading} style={{ fontSize: '0.84rem' }}>
              {downloading ? <Loader2 size={13} className="spin" /> : <Download size={13} />}
              Download agent.yaml
            </button>
            <span className="text-muted" style={{ fontSize: '0.8rem' }}>
              Then: <code>sudo cp agent.yaml /etc/kelvex/agent.yaml && sudo systemctl restart kelvex-agent</code>
            </span>
          </div>
        </div>

        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', background: 'var(--surface-2)', borderRadius: '6px', padding: '0.5rem 0.75rem' }}>
          <span style={{ fontWeight: 600 }}>Agent key:</span>{' '}
          <code>{agent.agent_key}</code>
          <CopyButton text={agent.agent_key} />
        </div>
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

      <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border)' }}>
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
