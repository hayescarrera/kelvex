import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Hexagon, Building2, Radio, Zap, CheckCircle, ArrowRight, ArrowLeft,
  Copy, Terminal, Wifi,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../lib/api'
import toast from 'react-hot-toast'

const STEPS = [
  { id: 'welcome', title: 'Welcome', icon: Hexagon },
  { id: 'facility', title: 'Add Facility', icon: Building2 },
  { id: 'agent', title: 'Connect Agent', icon: Radio },
  { id: 'verify', title: 'Verify', icon: Zap },
  { id: 'done', title: 'All Set', icon: CheckCircle },
]

export default function OnboardingPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [facilityName, setFacilityName] = useState('')
  const [facilityCity, setFacilityCity] = useState('')
  const [facilityState, setFacilityState] = useState('')
  const [facilityId, setFacilityId] = useState<string | null>(null)
  const [agentToken, setAgentToken] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const currentStep = STEPS[step]

  async function createFacility() {
    if (!facilityName.trim()) {
      toast.error('Enter a facility name')
      return
    }
    setCreating(true)
    try {
      const fac = await api.createFacility({
        name: facilityName,
        city: facilityCity || undefined,
        state: facilityState || undefined,
      }) as { id: string }
      setFacilityId(fac.id)
      toast.success('Facility created!')
      setStep(2)
    } catch (e) {
      toast.error('Failed to create facility')
    } finally {
      setCreating(false)
    }
  }

  async function provisionAgent() {
    if (!facilityId) return
    setCreating(true)
    try {
      const agent = await api.registerAgent(facilityId, {
        name: `${facilityName} Agent`,
      })
      setAgentToken(agent.agent_key || 'agent-key-provisioned')
      toast.success('Agent provisioned!')
      setStep(3)
    } catch (e) {
      toast.error('Failed to provision agent')
    } finally {
      setCreating(false)
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
  }

  return (
    <div className="page-container" style={{ maxWidth: 720, margin: '0 auto' }}>
      {/* Progress bar */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 32 }}>
        {STEPS.map((s, i) => (
          <div key={s.id} style={{
            flex: 1, height: 4, borderRadius: 2,
            background: i <= step ? 'var(--accent)' : 'var(--border)',
            transition: 'background 0.3s',
          }} />
        ))}
      </div>

      {/* Step indicator */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, alignItems: 'center' }}>
        {STEPS.map((s, i) => {
          const Icon = s.icon
          const isActive = i === step
          const isDone = i < step
          return (
            <div key={s.id} style={{
              display: 'flex', alignItems: 'center', gap: 6, fontSize: 12,
              color: isActive ? 'var(--accent)' : isDone ? 'var(--success)' : 'var(--text-tertiary)',
              fontWeight: isActive ? 600 : 400,
            }}>
              <Icon size={14} />
              <span className="hidden-mobile">{s.title}</span>
              {i < STEPS.length - 1 && <ArrowRight size={10} style={{ color: 'var(--border)', marginLeft: 4 }} />}
            </div>
          )
        })}
      </div>

      {/* Step content */}
      <div className="card">
        <div className="card-body" style={{ padding: 32 }}>

          {/* Welcome */}
          {currentStep.id === 'welcome' && (
            <div style={{ textAlign: 'center' }}>
              <div style={{
                width: 64, height: 64, borderRadius: '50%', background: 'var(--accent-bg)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px',
              }}>
                <Hexagon size={28} style={{ color: 'var(--accent)' }} />
              </div>
              <h2 style={{ margin: '0 0 8px', fontSize: 22 }}>Welcome to Kelvex{user ? `, ${user.full_name.split(' ')[0]}` : ''}</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: 14, maxWidth: 440, margin: '0 auto 24px' }}>
                Let's get your cold storage facility connected and monitored.
                This wizard will guide you through setting up your first facility and connecting an edge agent.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 360, margin: '0 auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, background: 'var(--bg-secondary)', borderRadius: 8 }}>
                  <Building2 size={18} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                  <div style={{ fontSize: 13 }}><strong>Step 1:</strong> Create your first facility</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, background: 'var(--bg-secondary)', borderRadius: 8 }}>
                  <Radio size={18} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                  <div style={{ fontSize: 13 }}><strong>Step 2:</strong> Connect an edge agent</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, background: 'var(--bg-secondary)', borderRadius: 8 }}>
                  <Zap size={18} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                  <div style={{ fontSize: 13 }}><strong>Step 3:</strong> Verify data flow</div>
                </div>
              </div>
            </div>
          )}

          {/* Add Facility */}
          {currentStep.id === 'facility' && (
            <div>
              <h2 style={{ margin: '0 0 8px', fontSize: 18 }}>Create Your First Facility</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 20 }}>
                A facility represents a physical cold storage warehouse. You can add more later.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div>
                  <label className="form-label">Facility Name *</label>
                  <input
                    type="text" className="form-input" placeholder="e.g. Main Warehouse"
                    value={facilityName} onChange={e => setFacilityName(e.target.value)}
                  />
                </div>
                <div className="field-row" style={{ display: 'flex', gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">City</label>
                    <input type="text" className="form-input" placeholder="e.g. Chicago"
                      value={facilityCity} onChange={e => setFacilityCity(e.target.value)} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">State</label>
                    <input type="text" className="form-input" placeholder="e.g. IL"
                      value={facilityState} onChange={e => setFacilityState(e.target.value)} />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Connect Agent */}
          {currentStep.id === 'agent' && (
            <div>
              <h2 style={{ margin: '0 0 8px', fontSize: 18 }}>Connect an Edge Agent</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 20 }}>
                The Kelvex edge agent runs on-site and bridges your compressor controllers to the cloud via Modbus.
              </p>
              {!agentToken ? (
                <div style={{ textAlign: 'center', padding: 20 }}>
                  <Wifi size={32} style={{ color: 'var(--accent)', marginBottom: 12 }} />
                  <p style={{ fontSize: 13, marginBottom: 16 }}>
                    Click below to provision an agent for <strong>{facilityName}</strong>.
                  </p>
                  <button className="btn-primary" onClick={provisionAgent} disabled={creating}>
                    {creating ? 'Provisioning...' : 'Provision Agent'}
                  </button>
                </div>
              ) : (
                <div>
                  <div style={{ marginBottom: 16 }}>
                    <label className="form-label">Agent API Key</label>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <code style={{
                        flex: 1, padding: 10, background: 'var(--bg-secondary)', borderRadius: 6,
                        fontSize: 12, fontFamily: 'monospace', wordBreak: 'break-all',
                      }}>
                        {agentToken}
                      </code>
                      <button className="btn-secondary" onClick={() => copyToClipboard(agentToken)}>
                        <Copy size={14} />
                      </button>
                    </div>
                  </div>
                  <div style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <Terminal size={14} />
                      <span style={{ fontSize: 12, fontWeight: 600 }}>Install on your on-site machine:</span>
                    </div>
                    <pre style={{
                      margin: 0, padding: 12, background: '#1a1a2e', color: '#e0e0ff',
                      borderRadius: 6, fontSize: 12, overflow: 'auto',
                    }}>
{`# Download and install the Kelvex agent
curl -fsSL https://releases.kelvex.io/agent/latest/install.sh | sudo bash

# Configure with your API key
kelvex-agent configure \\
  --api-key ${agentToken} \\
  --server https://app.kelvex.io

# Start the agent
coldgrid-agent start`}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Verify */}
          {currentStep.id === 'verify' && (
            <div style={{ textAlign: 'center' }}>
              <Zap size={32} style={{ color: 'var(--warning)', marginBottom: 12 }} />
              <h2 style={{ margin: '0 0 8px', fontSize: 18 }}>Waiting for Data...</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: 13, maxWidth: 440, margin: '0 auto 20px' }}>
                Once your edge agent is running and connected, telemetry data will start flowing in.
                You can skip this step and verify later from the Live Monitor.
              </p>
              <div style={{
                padding: 16, background: 'var(--bg-secondary)', borderRadius: 8,
                fontSize: 13, color: 'var(--text-secondary)',
              }}>
                If your agent is running, data should appear within 60 seconds.
                Check the <strong>Edge Agents</strong> page to see agent status.
              </div>
            </div>
          )}

          {/* Done */}
          {currentStep.id === 'done' && (
            <div style={{ textAlign: 'center' }}>
              <div style={{
                width: 64, height: 64, borderRadius: '50%', background: '#0d9f5f22',
                display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px',
              }}>
                <CheckCircle size={28} style={{ color: 'var(--success)' }} />
              </div>
              <h2 style={{ margin: '0 0 8px', fontSize: 22 }}>You're All Set!</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: 14, maxWidth: 440, margin: '0 auto 24px' }}>
                Your facility is created and your agent is provisioned.
                Head to the dashboard to start monitoring.
              </p>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
                <button className="btn-primary" onClick={() => navigate('/')}>
                  Go to Dashboard
                </button>
                <button className="btn-secondary" onClick={() => navigate('/settings')}>
                  Configure Settings
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 20 }}>
        <button
          className="btn-secondary"
          onClick={() => setStep(Math.max(0, step - 1))}
          disabled={step === 0}
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
        >
          <ArrowLeft size={14} /> Back
        </button>

        {currentStep.id === 'facility' ? (
          <button className="btn-primary" onClick={createFacility} disabled={creating}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {creating ? 'Creating...' : 'Create & Continue'} <ArrowRight size={14} />
          </button>
        ) : currentStep.id === 'agent' && !agentToken ? (
          <button className="btn-secondary" onClick={() => setStep(step + 1)}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            Skip <ArrowRight size={14} />
          </button>
        ) : currentStep.id !== 'done' ? (
          <button className="btn-primary" onClick={() => setStep(Math.min(STEPS.length - 1, step + 1))}
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {currentStep.id === 'verify' ? 'Skip & Finish' : 'Continue'} <ArrowRight size={14} />
          </button>
        ) : null}
      </div>
    </div>
  )
}
