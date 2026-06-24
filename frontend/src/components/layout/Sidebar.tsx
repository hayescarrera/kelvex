import { NavLink } from 'react-router-dom'
import {
  Home, MapPin, Bell, Thermometer, Zap, Wrench,
  FileText, BarChart2, Plug, Settings, LogOut,
  Sun, Moon, ShieldCheck,
} from 'lucide-react'
import KelvexLogo from '../ui/KelvexLogo'
import { useAuth } from '../../contexts/AuthContext'
import { useTheme } from '../../contexts/ThemeContext'
import { useSiteContext } from '../../contexts/SiteContext'
import { useAlertSummary } from '../../hooks/useAlerts'
import type { UserRole } from '../../lib/api'
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
      background: hasCritical ? 'var(--danger)' : 'rgba(234,179,8,0.85)',
      color: '#fff',
      flexShrink: 0,
      animation: hasCritical ? 'badge-pulse 2s ease-in-out infinite' : 'none',
    }}>
      {count > 99 ? '99+' : count}
    </span>
  )
}

interface NavItem {
  to: string
  icon: React.ReactNode
  label: string
  badge?: React.ReactNode
  end?: boolean
  gate?: UserRole[]  // if set, only these roles see this item
}

function buildNavItems(
  role: UserRole | undefined,
  siteId: string | null,
  alertCount: number,
  hasCritical: boolean,
): { label: string; items: NavItem[] }[] {
  const siteHref = siteId ? `/sites/${siteId}` : '/sites'
  const alertBadge = <AlertBadge count={alertCount} hasCritical={hasCritical} />

  // Core nav — spec §2, always visible
  const coreItems: NavItem[] = [
    { to: '/',          icon: <Home size={16} />,       label: 'Portfolio',              end: true },
    { to: siteHref,     icon: <MapPin size={16} />,     label: 'Sites' },
    { to: '/alerts',    icon: <Bell size={16} />,       label: 'Alerts',  badge: alertBadge },
    { to: '/refrigerant', icon: <Thermometer size={16} />, label: 'Refrigerant & Compliance' },
    { to: '/energy',    icon: <Zap size={16} />,        label: 'Energy & Cost' },
    { to: '/maintenance', icon: <Wrench size={16} />,   label: 'Maintenance & Audit' },
    { to: '/documents', icon: <FileText size={16} />,   label: 'Documents' },
    { to: '/reports',   icon: <BarChart2 size={16} />,  label: 'Reports & Exports' },
    {
      to: '/tunnel',
      icon: <Plug size={16} />,
      label: 'Controller Access',
      gate: ['kelvex_admin', 'owner', 'admin', 'technician'],
    },
  ]

  // Filter gated items
  const visibleCore = coreItems.filter(
    item => !item.gate || (role && item.gate.includes(role))
  )

  // Role-aware ordering: put the role's primary items first
  function reorder(items: NavItem[]): NavItem[] {
    if (!role) return items
    let priority: string[] = []
    if (role === 'finance') priority = ['/energy', '/documents', '/reports']
    if (role === 'technician') priority = ['/sites', '/alerts', '/tunnel', '/maintenance']
    if (role === 'ops_manager' || role === 'plant_manager')
      priority = ['/', '/alerts', '/maintenance', '/refrigerant']
    if (!priority.length) return items

    const hi = items.filter(i => priority.includes(i.to))
    const lo = items.filter(i => !priority.includes(i.to))
    return [...hi, ...lo]
  }

  const orderedCore = reorder(visibleCore)

  const settingsItems: NavItem[] = [
    { to: '/settings', icon: <Settings size={16} />, label: 'Settings' },
    { to: '/settings/notifications', icon: <Bell size={16} />, label: 'Notifications' },
  ]

  if (role === 'kelvex_admin') {
    settingsItems.unshift({
      to: '/admin',
      icon: <ShieldCheck size={16} />,
      label: 'Admin Console',
    })
  }

  return [
    { label: 'Navigation', items: orderedCore },
    { label: 'Account',    items: settingsItems },
  ]
}

interface SidebarProps {
  onNavClick?: () => void
  mobileOpen?: boolean
}

export default function Sidebar({ onNavClick, mobileOpen }: SidebarProps = {}) {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const { site } = useSiteContext()
  const { data: alertSummary } = useAlertSummary()

  const alertCount = alertSummary?.total_active ?? 0
  const hasCritical = (alertSummary?.by_severity?.critical ?? 0) > 0
  const sections = buildNavItems(
    user?.role,
    site?.id ?? null,
    alertCount,
    hasCritical,
  )

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
        {user?.org_name && (
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)', paddingLeft: 2, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {user.org_name}
          </div>
        )}
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
                end={item.end}
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
