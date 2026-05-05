import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Wifi, WifiOff, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAgents, useRegisterAgent } from '../../hooks/useAgents'
import ResourceBar from '../../components/ui/ResourceBar'

export default function AgentsPage() {
  const { facilityId } = useParams<{ facilityId: string }>()
  const [agentName, setAgentName] = useState('')

  const { data, isLoading } = useAgents(facilityId!)
  const agents = data?.agents ?? []
  const registerMutation = useRegisterAgent(facilityId!)

  const handleRegister = (e: React.FormEvent) => {
    e.preventDefault()
    if (!agentName.trim()) return
    registerMutation.mutate({ name: agentName.trim() }, {
      onSuccess: () => {
        setAgentName('')
        toast.success('Agent registered')
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
      <div className="card">
        <div className="card-header">
          <span>Register Agent</span>
        </div>
        <div className="card-body">
          <form className="inline-form" onSubmit={handleRegister}>
            <div className="field">
              <input
                type="text"
                placeholder="Agent name"
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
              {agents.map((agent: any) => (
                <div key={agent.id} className="agent-card">
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
                    <span>{formatHeartbeat(agent.last_heartbeat_at)}</span>
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
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
