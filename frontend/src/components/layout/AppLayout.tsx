import { useState, useCallback, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import Sidebar from './Sidebar'
import KelvexLogo from '../ui/KelvexLogo'

export default function AppLayout({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  // Close mobile nav on route change
  const prevPath = useState(location.pathname)[0]
  if (location.pathname !== prevPath && mobileOpen) {
    setMobileOpen(false)
  }

  const closeMobile = useCallback(() => setMobileOpen(false), [])

  return (
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

      {/* Sidebar with mobile toggle */}
      <div className={mobileOpen ? 'sidebar-mobile-open' : ''}>
        <Sidebar onNavClick={closeMobile} mobileOpen={mobileOpen} />
      </div>

      <main className="main-content">
        {children}
      </main>
    </div>
  )
}
