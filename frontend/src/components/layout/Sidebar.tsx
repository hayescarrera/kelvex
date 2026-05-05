import { NavLink } from 'react-router-dom'
import {
  Building2, AlertTriangle, Settings, LogOut, Sun, Moon,
  ShieldCheck, Wrench, ClipboardList, BarChart3, PlayCircle, Radio,
  Users, History, Shield,
} from 'lucide-react'
import KelvexLogo from '../ui/KelvexLogo'
import { useAuth } from '../../contexts/AuthContext'
import { useTheme } from '../../contexts/ThemeContext'
import { useSiteContext } from '../../contexts/SiteContext'
import { useAlertSummary } from '../../hooks/useAlerts'
import SiteSelector from './SiteSelector'

function AlertBadge({ count, hasCritical }: { count: number; hasCritical: boolean }) {
  if (count === 0) return null
  return (
    <span style={{
      marginLeft: 'auto',
      minWidth: 18,
      height: 18,
      padding: '0 5px',
      borderRadius: 9,
      fontSize: 11,
      fontWeight: 700,
      lineHeight: '18px',
      textAlign: 'center',
      background: hasCritical ? 'var(--danger)' : 'rgba(234, 179, 8, 0.85)',
      color: '#fff',
      flexShrink: 0,
      boxShadow: hasCritical ? '0 0 0 2px rgba(239,68,68,0.25)' : 'none',
      animation: hasCritical ? 'badge-pulse 2s ease-in-out infinite' : 'none',
    }}>
      {count > 99 ? '99+' : count}
    </span>
  )
}

function useNavSections(alertCount: number, hasCritical: boolean) {
  const { site } = useSiteContext()
  const facilityPrefix = site ? `/facilities/${site.id}` : null

  return [
    {
      label: 'Overview',
      items: [
        { to: '/', icon: <Building2 size={17} />, label: 'Dashboard', end: true, badge: null },
        ...(facilityPrefix
          ? [{ to: facilityPrefix, icon: <BarChart3 size={17} />, label: site?.name || 'Facility', badge: null }]
          : []
        ),
      ],
    },
    {
      label: 'Operations',
      items: [
        {
          to: '/alerts', icon: <AlertTriangle size={17} />, label: 'Alerts',
          badge: <AlertBadge count={alertCount} hasCritical={hasCritical} />,
        },
        { to: '/alert-rules', icon: <Shield size={17} />, label: 'Alert Rules', badge: null },
        { to: '/automation', icon: <PlayCircle size={17} />, label: 'Automation', badge: null },
        { to: '/compliance', icon: <ShieldCheck size={17} />, label: 'Compliance', badge: null },
        { to: '/maintenance', icon: <Wrench size={17} />, label: 'Maintenance', badge: null },
        { to: '/reports', icon: <ClipboardList size={17} />, label: 'Reports', badge: null },
      ],
    },
    {
      label: 'System',
      items: [
        { to: '/agents', icon: <Radio size={17} />, label: 'Edge Agents', badge: null },
        { to: '/team', icon: <Users size={17} />, label: 'Team', badge: null },
        { to: '/activity', icon: <History size={17} />, label: 'Activity Log', badge: null },
        { to: '/settings', icon: <Settings size={17} />, label: 'Settings', badge: null },
      ],
    },
  ]
}

interface SidebarProps {
  onNavClick?: () => void
  mobileOpen?: boolean
}

export default function Sidebar({ onNavClick, mobileOpen }: SidebarProps = {}) {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const { data: alertSummary } = useAlertSummary()

  const alertCount = alertSummary?.total_active ?? 0
  const hasCritical = (alertSummary?.by_severity?.critical ?? 0) > 0
  const sections = useNavSections(alertCount, hasCritical)

  const initials = user
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : '??'

  return (
    <nav className={`sidebar${mobileOpen ? ' mobile-open' : ''}`}>
      <div className="sidebar-header">
        <div className="logo-row">
          <KelvexLogo size={20} />
          <span className="logo-text">Kelvex</span>
        </div>
      </div>

      <SiteSelector />

      <div className="nav-scroll">
        {sections.map(section => (
          <div key={section.label} className="nav-section">
            <div className="nav-label">{section.label}</div>
            {section.items.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={'end' in item ? (item as any).end : undefined}
                onClick={onNavClick}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              >
                <span className="nav-icon">{item.icon}</span>
                <span className="nav-text">{item.label}</span>
                {item.badge}
              </NavLink>
            ))}
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        <div className="user-row">
          <div className="avatar">{initials}</div>
          <div className="user-info">
            <span className="user-name">{user?.full_name}</span>
            <span className="user-email">{user?.email}</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          <button onClick={toggle} className="icon-btn" title={theme === 'light' ? 'Dark mode' : 'Light mode'}>
            {theme === 'light' ? <Moon size={14} /> : <Sun size={14} />}
          </button>
          <button onClick={logout} className="icon-btn" title="Sign out">
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </nav>
  )
}
