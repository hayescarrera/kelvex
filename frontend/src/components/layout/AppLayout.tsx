import { useState, useCallback, useEffect, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Menu, X, AlertTriangle } from 'lucide-react'
import Sidebar from './Sidebar'
import KelvexLogo from '../ui/KelvexLogo'
import { useAlertSummary } from '../../hooks/useAlerts'

function getPageTitle(pathname: string): string {
  if (pathname === '/') return 'Dashboard'
  if (pathname === '/alerts') return 'Alerts'
  if (pathname === '/alert-rules') return 'Alert Rules'
  if (pathname === '/leak-tracking') return 'Leak Tracking'
  if (pathname === '/compliance') return 'Compliance'
  if (pathname === '/food-safety') return 'Food Safety'
  if (pathname === '/maintenance') return 'Maintenance & Audit'
  if (pathname === '/reports') return 'Reports & Exports'
  if (pathname === '/documents') return 'Documents'
  if (pathname === '/refrigerant') return 'Refrigerant & Compliance'
  if (pathname === '/energy') return 'Energy & Cost'
  if (pathname === '/sites') return 'Sites'
  if (pathname === '/operations') return 'Fleet Health'
  if (pathname === '/tunnel') return 'Controller Access'
  if (pathname === '/admin') return 'Admin Console'
  if (pathname === '/settings') return 'Settings'
  if (pathname === '/agents') return 'Edge Agents'
  if (pathname === '/team') return 'Team'
  if (pathname === '/activity') return 'Activity Log'
  if (pathname === '/onboarding') return 'Setup'
  if (pathname === '/demand') return 'Demand'
  if (pathname === '/savings') return 'Savings Simulator'
  if (pathname === '/bills') return 'Utility Bills'
  if (pathname === '/compare') return 'Site Comparison'
  if (pathname === '/automation' || pathname === '/schedules') return 'Automation'
  if (pathname.startsWith('/sites/')) return 'Site'
  if (pathname.startsWith('/facilities/')) return 'Site'
  return ''
}

function useDocumentTitle() {
  const { data } = useAlertSummary()
  const location = useLocation()
  useEffect(() => {
    const critical = data?.by_severity?.critical ?? 0
    const total = data?.total_active ?? 0
    const alertPrefix = critical > 0 ? `(${critical} critical) ` : total > 0 ? `(${total} alerts) ` : ''
    const pageTitle = getPageTitle(location.pathname)
    document.title = alertPrefix + (pageTitle ? `${pageTitle} | Kelvex` : 'Kelvex')
  }, [data, location.pathname])
}

function CriticalAlertBanner() {
  const { data } = useAlertSummary()
  const navigate = useNavigate()
  const [dismissed, setDismissed] = useState(false)
  const critical = data?.by_severity?.critical ?? 0

  // Re-show if new criticals appear after dismissal
  const [lastSeenCount, setLastSeenCount] = useState(0)
  useEffect(() => {
    if (critical > lastSeenCount) {
      setDismissed(false)
      setLastSeenCount(critical)
    }
  }, [critical, lastSeenCount])

  if (!critical || dismissed) return null

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0,
      zIndex: 1000,
      background: 'linear-gradient(90deg, #7f1d1d, #991b1b)',
      borderBottom: '1px solid rgba(248,113,113,0.3)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 16px',
      height: 40,
      gap: 10,
    }}>
      <AlertTriangle size={15} style={{ color: '#fca5a5', flexShrink: 0 }} />
      <span style={{ fontSize: 13, color: '#fecaca', flex: 1, fontWeight: 500 }}>
        {critical} critical alert{critical > 1 ? 's' : ''} require immediate attention
      </span>
      <button
        onClick={() => navigate('/alerts')}
        style={{
          fontSize: 12, fontWeight: 600, color: '#fff',
          background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.2)',
          borderRadius: 5, padding: '3px 10px', cursor: 'pointer',
        }}
      >
        View alerts
      </button>
      <button
        onClick={() => setDismissed(true)}
        style={{ background: 'none', border: 'none', color: '#fca5a5', cursor: 'pointer', padding: 4, display: 'flex', alignItems: 'center' }}
        aria-label="Dismiss"
      >
        <X size={14} />
      </button>
    </div>
  )
}

export default function AppLayout({ children }: { children: ReactNode }) {
  useDocumentTitle()
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  const prevPath = useState(location.pathname)[0]
  if (location.pathname !== prevPath && mobileOpen) {
    setMobileOpen(false)
  }

  const closeMobile = useCallback(() => setMobileOpen(false), [])

  return (
    <>
      <CriticalAlertBanner />
      <div className="app-layout">
        {/* Mobile header */}
        <div className="mobile-header">
          <button
            className="mobile-nav-toggle"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
          >
            {mobileOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
          <KelvexLogo size={16} />
          <span className="logo-text">Kelvex</span>
        </div>

        {/* Mobile overlay */}
        <div
          className={`mobile-overlay${mobileOpen ? ' visible' : ''}`}
          onClick={closeMobile}
        />

        {/* Sidebar */}
        <div className={mobileOpen ? 'sidebar-mobile-open' : ''}>
          <Sidebar onNavClick={closeMobile} mobileOpen={mobileOpen} />
        </div>

        <main className="main-content">
          {children}
        </main>
      </div>
    </>
  )
}
