import { useState } from 'react'
import AgentsPage from './AgentsPage'
import IntegrationsPage from './IntegrationsPage'

type Tab = 'agents' | 'integrations'

export default function ConnectionsPage() {
  const [tab, setTab] = useState<Tab>('agents')

  return (
    <div>
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {([
          { key: 'agents',       label: 'Edge Agents' },
          { key: 'integrations', label: 'Integrations' },
        ] as { key: Tab; label: string }[]).map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: tab === t.key ? 600 : 400,
              color: tab === t.key ? 'var(--accent)' : 'var(--text-secondary)',
              borderBottom: tab === t.key ? '2px solid var(--accent)' : '2px solid transparent',
              background: 'none', border: 'none', cursor: 'pointer', marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'agents'       && <AgentsPage />}
      {tab === 'integrations' && <IntegrationsPage />}
    </div>
  )
}
