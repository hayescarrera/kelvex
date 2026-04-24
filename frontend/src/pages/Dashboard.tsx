import { useState, useEffect, useRef, useCallback, createContext, useContext } from 'react'
import { api, Bill, DemandAnalysis, Equipment as EquipmentType, Facility, Zone, ControlSequence, AutomationRule, EdgeAgent } from '../lib/api'
import {
  Zap, Building2, LogOut, Plus, DollarSign,
  TrendingDown, Upload, ChevronRight, X,
  FileText, Settings, Activity, MapPin, Thermometer,
  Clock, AlertTriangle, ArrowLeft, Cpu,
  Trash2, Loader2, Shield, Radio, Wifi, WifiOff, PlayCircle, Eye, Gauge,
  Sun, Moon, ChevronDown, Check, BarChart3
} from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line
} from 'recharts'
import KelvexLogo from '../components/ui/KelvexLogo'

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Theme Context
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
type Theme = 'light' | 'dark'
const ThemeCtx = createContext<{ theme: Theme; toggle: () => void }>({ theme: 'light', toggle: () => {} })

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('coldgrid_theme') as Theme | null
    return saved || 'light'
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('coldgrid_theme', theme)
  }, [theme])
  const toggle = useCallback(() => setTheme(t => t === 'light' ? 'dark' : 'light'), [])
  return { theme, toggle }
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Site Context — persists selected facility across pages
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
interface SiteCtxType {
  site: Facility | null
  setSite: (f: Facility | null) => void
  facilities: Facility[]
}
const SiteCtx = createContext<SiteCtxType>({ site: null, setSite: () => {}, facilities: [] })

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Types
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
interface DashboardProps {
  user: { full_name: string; email: string }
  onLogout: () => void
}

type NavPage = 'fleet' | 'alerts' | 'demand' | 'savings' | 'bills' | 'sequences' | 'rules' | 'schedules' | 'agents' | 'compare' | 'settings'

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Mock data (for charts until real telemetry flows)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
const mockDemandData = [
  { month: 'Sep', peak: 847, avg: 612, target: 750 },
  { month: 'Oct', peak: 923, avg: 645, target: 750 },
  { month: 'Nov', peak: 756, avg: 598, target: 750 },
  { month: 'Dec', peak: 1102, avg: 701, target: 750 },
  { month: 'Jan', peak: 889, avg: 634, target: 750 },
  { month: 'Feb', peak: 812, avg: 621, target: 750 },
  { month: 'Mar', peak: 945, avg: 667, target: 750 },
]
const mockCostData = [
  { month: 'Sep', demand: 12400, energy: 18200 },
  { month: 'Oct', demand: 14100, energy: 17800 },
  { month: 'Nov', demand: 11200, energy: 16900 },
  { month: 'Dec', demand: 16800, energy: 19100 },
  { month: 'Jan', demand: 13500, energy: 18400 },
  { month: 'Feb', demand: 12100, energy: 17200 },
  { month: 'Mar', demand: 14400, energy: 18600 },
]

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Chart Tooltip — adapts to theme
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div style={{ color: 'var(--text-tertiary)', marginBottom: 6, fontSize: 11, fontWeight: 600 }}>{label}</div>
      {payload.map((p: any, i: number) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: p.color, flexShrink: 0 }} />
          <span style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>{p.name}:</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: 12 }}>
            {typeof p.value === 'number' && p.value > 100 ? p.value.toLocaleString() : p.value}
          </span>
        </div>
      ))}
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   MAIN DASHBOARD
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
export default function Dashboard({ user, onLogout }: DashboardProps) {
  const themeCtx = useTheme()
  const [facilities, setFacilities] = useState<Facility[]>([])
  const [loading, setLoading] = useState(true)
  const [activePage, setActivePage] = useState<NavPage>('fleet')
  const [selectedSite, setSelectedSite] = useState<Facility | null>(null)
  const [showAddFacility, setShowAddFacility] = useState(false)
  const [facilityTab, setFacilityTab] = useState<string>('overview')

  useEffect(() => { loadFacilities() }, [])

  const loadFacilities = async () => {
    try {
      const data = await api.listFacilities()
      setFacilities(data.facilities)
    } catch (err) { console.error('Failed to load facilities:', err) }
    finally { setLoading(false) }
  }

  const initials = user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)

  const nav = {
    operations: [
      { key: 'fleet' as const, label: 'Fleet Overview', icon: <Building2 size={17} /> },
      { key: 'alerts' as const, label: 'Alerts & Events', icon: <AlertTriangle size={17} /> },
    ],
    intelligence: [
      { key: 'demand' as const, label: 'Demand Analysis', icon: <Zap size={17} /> },
      { key: 'savings' as const, label: 'Savings Simulator', icon: <TrendingDown size={17} /> },
      { key: 'bills' as const, label: 'Utility Bills', icon: <FileText size={17} /> },
      { key: 'compare' as const, label: 'Site Comparison', icon: <BarChart3 size={17} /> },
    ],
    automation: [
      { key: 'sequences' as const, label: 'Control Sequences', icon: <PlayCircle size={17} /> },
      { key: 'rules' as const, label: 'Automation Rules', icon: <Shield size={17} /> },
      { key: 'schedules' as const, label: 'Schedules', icon: <Clock size={17} /> },
    ],
    system: [
      { key: 'agents' as const, label: 'Edge Agents', icon: <Radio size={17} /> },
      { key: 'settings' as const, label: 'Settings', icon: <Settings size={17} /> },
    ],
  }

  // Pages that require a site to be selected
  const siteRequired = new Set<NavPage>(['alerts', 'sequences', 'rules', 'schedules', 'agents'])

  const handleNav = (key: NavPage) => {
    setActivePage(key)
    if (key === 'fleet') setSelectedSite(null)
  }

  const handleSelectSite = (f: Facility) => {
    setSelectedSite(f)
    setFacilityTab('overview')
    setActivePage('fleet')
  }

  const renderNavSection = (label: string, items: { key: NavPage; label: string; icon: JSX.Element }[]) => (
    <div className="nav-section">
      <div className="nav-label">{label}</div>
      {items.map(item => (
        <button key={item.key} className={`nav-item${activePage === item.key ? ' active' : ''}`}
          onClick={() => handleNav(item.key)}>
          <span className="nav-icon">{item.icon}</span>
          <span className="nav-text">{item.label}</span>
          {activePage === item.key && <span className="nav-indicator" />}
        </button>
      ))}
    </div>
  )

  // Determine main content
  const needsSite = siteRequired.has(activePage) && !selectedSite

  return (
    <ThemeCtx.Provider value={themeCtx}>
    <SiteCtx.Provider value={{ site: selectedSite, setSite: setSelectedSite, facilities }}>
    <div className="app-layout">
      {/* ── Sidebar ──────────────────────────── */}
      <nav className="sidebar">
        <div className="sidebar-header">
          <div className="logo-row">
            <div className="logo-icon"><KelvexLogo size={17} /></div>
            <span className="logo-text">Kelvex</span>
          </div>
        </div>

        {/* Site Selector */}
        <SiteSelector onSelect={handleSelectSite} />

        <div className="nav-scroll">
          {renderNavSection('Operations', nav.operations)}
          {renderNavSection('Intelligence', nav.intelligence)}
          {renderNavSection('Automation', nav.automation)}
          {renderNavSection('System', nav.system)}
        </div>

        <div className="sidebar-footer">
          <div className="user-row">
            <div className="avatar">{initials}</div>
            <div className="user-info">
              <span className="user-name">{user.full_name}</span>
              <span className="user-email">{user.email}</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 4 }}>
            <button onClick={themeCtx.toggle} className="icon-btn" title={themeCtx.theme === 'light' ? 'Dark mode' : 'Light mode'}>
              {themeCtx.theme === 'light' ? <Moon size={14} /> : <Sun size={14} />}
            </button>
            <button onClick={onLogout} className="icon-btn" title="Sign out"><LogOut size={14} /></button>
          </div>
        </div>
      </nav>

      {/* ── Main Content ─────────────────────── */}
      <main className="main-content">
        {selectedSite && activePage === 'fleet' ? (
          <FacilityDetail facility={selectedSite} onBack={() => setSelectedSite(null)}
            activeTab={facilityTab} setActiveTab={setFacilityTab} onReload={loadFacilities} />
        ) : needsSite ? (
          <SiteRequiredPage pageName={activePage} />
        ) : activePage === 'fleet' ? (
          <FleetPage loading={loading} onAdd={() => setShowAddFacility(true)} onSelect={handleSelectSite} />
        ) : activePage === 'demand' ? (
          <DemandPage />
        ) : activePage === 'savings' ? (
          <SavingsPage />
        ) : activePage === 'bills' ? (
          <BillsPage />
        ) : activePage === 'compare' ? (
          <ComparisonPage />
        ) : activePage === 'alerts' ? (
          <AlertsPage />
        ) : activePage === 'sequences' ? (
          <ControlsTab />
        ) : activePage === 'rules' ? (
          <ControlsTab />
        ) : activePage === 'agents' ? (
          <AgentTab />
        ) : activePage === 'settings' ? (
          <SettingsPage />
        ) : null}
      </main>

      {/* ── Add Facility Modal ───────────────── */}
      {showAddFacility && (
        <AddFacilityModal onClose={() => setShowAddFacility(false)} onSuccess={() => { setShowAddFacility(false); loadFacilities() }} />
      )}
    </div>
    </SiteCtx.Provider>
    </ThemeCtx.Provider>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Site Selector (sidebar dropdown)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function SiteSelector({ onSelect }: { onSelect: (f: Facility) => void }) {
  const { site, facilities } = useContext(SiteCtx)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div className="site-selector" ref={ref}>
      <button className="site-selector-btn" onClick={() => setOpen(!open)}>
        <div className="site-selector-icon"><Building2 size={14} /></div>
        <div className="site-selector-text">
          <span className="site-selector-label">Active Site</span>
          <span className="site-selector-name">{site ? site.name : 'All Sites'}</span>
        </div>
        <ChevronDown size={14} style={{ opacity: 0.5, transition: 'transform 150ms', transform: open ? 'rotate(180deg)' : 'none' }} />
      </button>
      {open && (
        <div className="site-selector-dropdown">
          <button className={`site-option${!site ? ' active' : ''}`} onClick={() => { onSelect(null as any); setOpen(false) }}>
            <Building2 size={14} />
            <span>All Sites</span>
            {!site && <Check size={14} style={{ marginLeft: 'auto' }} />}
          </button>
          <div className="site-option-divider" />
          {facilities.map(f => (
            <button key={f.id} className={`site-option${site?.id === f.id ? ' active' : ''}`}
              onClick={() => { onSelect(f); setOpen(false) }}>
              <Building2 size={14} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 500 }}>{f.name}</div>
                {f.city && <div style={{ fontSize: 11, opacity: 0.6 }}>{f.city}, {f.state}</div>}
              </div>
              {site?.id === f.id && <Check size={14} style={{ marginLeft: 'auto' }} />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Site Required Page
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function SiteRequiredPage({ pageName }: { pageName: string }) {
  const { facilities } = useContext(SiteCtx)
  const { setSite } = useContext(SiteCtx)
  return (
    <div className="page-container">
      <PageHeader title={pageName.charAt(0).toUpperCase() + pageName.slice(1)} subtitle="Select a site to continue" />
      <div className="empty-state">
        <div className="empty-icon"><Building2 size={28} /></div>
        <h3>Select a site first</h3>
        <p>Use the site selector in the sidebar, or pick one below.</p>
        <div className="site-cards">
          {facilities.map(f => (
            <button key={f.id} className="site-card" onClick={() => setSite(f)}>
              <div className="site-card-icon"><Building2 size={16} /></div>
              <div>
                <div className="site-card-name">{f.name}</div>
                {f.city && <div className="site-card-loc">{f.city}, {f.state}</div>}
              </div>
              <ChevronRight size={14} style={{ marginLeft: 'auto', opacity: 0.3 }} />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Fleet Overview
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function FleetPage({ loading, onAdd, onSelect }: { loading: boolean; onAdd: () => void; onSelect: (f: Facility) => void }) {
  const { facilities } = useContext(SiteCtx)
  const [stats, setStats] = useState<Record<string, { equipment: number }>>({})
  const [totalEquipment, setTotalEquipment] = useState(0)

  useEffect(() => {
    if (!facilities.length) return
    Promise.all(facilities.map(f => api.listEquipment(f.id)))
      .then(results => {
        let total = 0
        const s: Record<string, { equipment: number }> = {}
        results.forEach((r, i) => { total += r.total; s[facilities[i].id] = { equipment: r.total } })
        setTotalEquipment(total); setStats(s)
      }).catch(() => {})
  }, [facilities])

  const totalZones = facilities.reduce((s, f) => s + (f.zone_types?.length ?? 0), 0)

  return (
    <div className="page-container">
      <PageHeader title="Fleet Overview" subtitle={`${facilities.length} facilit${facilities.length !== 1 ? 'ies' : 'y'} registered`}>
        <button className="btn-primary" onClick={onAdd}><Plus size={15} /> Add Facility</button>
      </PageHeader>

      <div className="stat-grid stagger">
        <StatCard icon={<Building2 size={18} />} color="var(--accent)" value={String(facilities.length)} label="Facilities" />
        <StatCard icon={<Cpu size={18} />} color="var(--success)" value={String(totalEquipment)} label="Equipment" />
        <StatCard icon={<Thermometer size={18} />} color="var(--warning)" value={String(totalZones)} label="Zones" />
        <StatCard icon={<Activity size={18} />} color="var(--danger)" value="0" label="Active Alerts" />
      </div>

      <div className="content-area">
        {loading ? <LoadingSpinner label="Loading facilities..." /> : facilities.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon"><Building2 size={28} /></div>
            <h3>No facilities yet</h3>
            <p>Add your first cold storage facility to start monitoring operations.</p>
            <button className="btn-ghost" onClick={onAdd}><Plus size={15} /> Add your first facility</button>
          </div>
        ) : (
          <div className="card">
            <table className="data-table">
              <thead><tr>
                <th>Facility</th><th>Location</th><th>Size</th><th>Equipment</th><th>Status</th><th style={{ width: 40 }}></th>
              </tr></thead>
              <tbody>
                {facilities.map(f => {
                  const fs = stats[f.id]
                  return (
                    <tr key={f.id} onClick={() => onSelect(f)}>
                      <td>
                        <div className="cell-with-icon">
                          <div className="table-icon"><Building2 size={14} /></div>
                          <div>
                            <span className="cell-primary">{f.name}</span>
                            {(f.zone_types?.length ?? 0) > 0 && (
                              <span className="cell-secondary">{f.zone_types!.join(', ')}</span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td><span className="cell-with-icon-inline"><MapPin size={13} />{[f.city, f.state].filter(Boolean).join(', ') || '\u2014'}</span></td>
                      <td>{f.sqft ? `${f.sqft.toLocaleString()} sqft` : '\u2014'}</td>
                      <td><span className="cell-with-icon-inline"><Cpu size={13} />{fs?.equipment ?? 0} units</span></td>
                      <td>
                        {(fs?.equipment ?? 0) > 0
                          ? <span className="badge badge-success"><span className="badge-dot" /> Online</span>
                          : <span className="badge badge-neutral"><span className="badge-dot" /> No agent</span>
                        }
                      </td>
                      <td><ChevronRight size={16} style={{ opacity: 0.3 }} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Facility Detail
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function FacilityDetail({ facility, onBack, activeTab, setActiveTab, onReload: _onReload }: {
  facility: Facility; onBack: () => void; activeTab: string; setActiveTab: (t: string) => void; onReload: () => void
}) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [billsKey, setBillsKey] = useState(0)

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return
    setUploading(true)
    try { await api.uploadBills(facility.id, file); setBillsKey(k => k + 1); setActiveTab('bills') }
    catch (err) { console.error('Upload failed:', err) }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const tabs = [
    { key: 'overview', label: 'Overview' },
    { key: 'zones', label: 'Zones' },
    { key: 'equipment', label: 'Equipment' },
    { key: 'bills', label: 'Utility Bills' },
    { key: 'demand', label: 'Demand' },
    { key: 'controls', label: 'Controls' },
    { key: 'agents', label: 'Agents' },
    { key: 'integrations', label: 'Integrations' },
  ]

  return (
    <div className="page-container">
      <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload} style={{ display: 'none' }} />

      <PageHeader title={facility.name} subtitle={[facility.city, facility.state].filter(Boolean).join(', ') + (facility.sqft ? ` \u00b7 ${facility.sqft.toLocaleString()} sqft` : '')}
        backAction={onBack}>
        <button className="btn-secondary" onClick={() => setActiveTab('settings')}><Settings size={14} /> Configure</button>
        <button className="btn-primary" onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? <><Loader2 size={14} className="spin" /> Uploading...</> : <><Upload size={14} /> Upload Bill</>}
        </button>
      </PageHeader>

      <div className="tab-bar">
        {tabs.map(t => (
          <button key={t.key} className={`tab${activeTab === t.key ? ' active' : ''}`} onClick={() => setActiveTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="content-area">
        {activeTab === 'overview' && <FacilityOverview facility={facility} key={`ov-${billsKey}`} />}
        {activeTab === 'zones' && <ZonesTab facilityId={facility.id} key={`z-${billsKey}`} />}
        {activeTab === 'equipment' && <EquipmentTab facilityId={facility.id} />}
        {activeTab === 'bills' && <BillsTab facilityId={facility.id} key={`b-${billsKey}`} />}
        {activeTab === 'demand' && <FacilityDemandTab facilityId={facility.id} key={`d-${billsKey}`} />}
        {activeTab === 'controls' && <ControlsTab facilityId={facility.id} />}
        {activeTab === 'agents' && <AgentTab facilityId={facility.id} />}
        {activeTab === 'integrations' && <IntegrationsTab facilityId={facility.id} />}
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Facility Overview Tab
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function FacilityOverview({ facility }: { facility: Facility }) {
  const [equipment, setEquipment] = useState<EquipmentType[]>([])
  const [bills, setBills] = useState<Bill[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.listEquipment(facility.id).then(d => setEquipment(d.equipment)),
      api.listBills(facility.id).then(d => setBills(d.bills)),
    ]).catch(() => {}).finally(() => setLoading(false))
  }, [facility.id])

  const latestBill = bills[0] ?? null
  const zones = facility.zone_types?.length ? facility.zone_types : []
  const eqByType: Record<string, EquipmentType[]> = {}
  equipment.forEach(eq => { if (!eqByType[eq.equipment_type]) eqByType[eq.equipment_type] = []; eqByType[eq.equipment_type].push(eq) })

  const zoneData: Record<string, { temp: string; setpoint: string; color: string }> = {
    freezer: { temp: '-10\u00b0F', setpoint: '-10\u00b0F', color: 'var(--freezer)' },
    cooler: { temp: '34\u00b0F', setpoint: '35\u00b0F', color: 'var(--cooler)' },
    dock: { temp: '48\u00b0F', setpoint: '50\u00b0F', color: 'var(--dock)' },
    blast: { temp: '-20\u00b0F', setpoint: '-20\u00b0F', color: 'var(--blast)' },
  }

  if (loading) return <LoadingSpinner />

  return (
    <div className="stack-lg">
      <div className="stat-grid-5 stagger">
        <StatCard icon={<Cpu size={18} />} color="var(--accent)" value={String(equipment.length)} label="Equipment" />
        <StatCard icon={<Thermometer size={18} />} color="var(--success)" value={String(zones.length)} label="Zones" />
        <StatCard icon={<Activity size={18} />} color="var(--warning)" value={equipment.length > 0 ? `${equipment.length}/${equipment.length}` : '--'} label="Online" />
        <StatCard icon={<AlertTriangle size={18} />} color="var(--danger)" value="0" label="Alerts" />
        <StatCard icon={<DollarSign size={18} />} color="#7c3aed" value={latestBill?.total_cost ? `$${Number(latestBill.total_cost).toLocaleString()}` : '--'} label="Last Bill" />
      </div>

      {zones.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3>Zone Status</h3>
            <span className="card-subtitle">{zones.length} zones configured</span>
          </div>
          <div className="card-body">
            <div className="zone-grid">
              {zones.map(zone => {
                const zd = zoneData[zone.toLowerCase()] || { temp: '--', setpoint: '--', color: 'var(--text-muted)' }
                return (
                  <div key={zone} className="zone-card" style={{ '--zone-color': zd.color } as any}>
                    <div className="zone-card-header">
                      <span className="zone-card-name">{zone}</span>
                      <span className="zone-card-badge">Normal</span>
                    </div>
                    <div className="zone-card-temp">{zd.temp}</div>
                    <div className="zone-card-meta">Setpoint: {zd.setpoint}</div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="card-header"><h3>Equipment by Type</h3><span className="card-subtitle">{equipment.length} units</span></div>
          <div className="card-body">
            {Object.keys(eqByType).length === 0 ? (
              <p className="text-muted" style={{ padding: 20, textAlign: 'center' }}>No equipment registered yet</p>
            ) : Object.entries(eqByType).map(([type, items]) => (
              <div key={type} className="eq-type-row">
                <div className="eq-type-header">
                  <span className="eq-type-name">{type}</span>
                  <span className="eq-type-count">{items.length}</span>
                </div>
                <div className="eq-type-chips">
                  {items.slice(0, 4).map(eq => <span key={eq.id} className="chip">{eq.name}</span>)}
                  {items.length > 4 && <span className="chip chip-muted">+{items.length - 4} more</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header"><h3>Recent Cost Trend</h3><span className="card-subtitle">Demand vs Energy</span></div>
          <div className="card-body" style={{ padding: '0 12px 12px' }}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={mockCostData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis dataKey="month" stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                <YAxis stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="demand" fill="var(--danger)" radius={[3, 3, 0, 0]} name="Demand $" />
                <Bar dataKey="energy" fill="var(--accent)" radius={[3, 3, 0, 0]} name="Energy $" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Zones Tab
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function ZonesTab({ facilityId }: { facilityId: string }) {
  const [zones, setZones] = useState<Zone[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { api.listZones(facilityId).then(r => setZones(r.zones || [])).catch(console.error).finally(() => setLoading(false)) }, [facilityId])
  if (loading) return <LoadingSpinner />

  const colorMap: Record<string, string> = { freezer: 'var(--freezer)', cooler: 'var(--cooler)', dock: 'var(--dock)', machine_room: 'var(--machine)' }

  return (
    <div className="stack-lg">
      <div className="card">
        <div className="card-header"><h3>Zone Status</h3><span className="card-subtitle">{zones.length} zones</span></div>
        <div className="card-body">
          {zones.length === 0 ? (
            <p className="text-muted" style={{ textAlign: 'center', padding: 32 }}>No zones configured. Add zones in Settings.</p>
          ) : (
            <div className="zone-grid">
              {zones.map(zone => (
                <div key={zone.id} className="zone-card" style={{ '--zone-color': colorMap[zone.zone_type] || 'var(--text-muted)' } as any}>
                  <div className="zone-card-header">
                    <span className="zone-card-name">{zone.name}</span>
                    <span className="zone-card-type">{zone.zone_type}</span>
                  </div>
                  <div className="zone-card-temp">{zone.current_temp ?? '--'}\u00b0F</div>
                  <div className="zone-card-meta">Setpoint: {zone.temp_setpoint ?? '--'}\u00b0F</div>
                  <div className="zone-card-meta">Humidity: {zone.current_humidity ?? '--'}%</div>
                  <div className={`zone-card-door ${zone.door_open ? 'open' : 'closed'}`}>
                    Door: {zone.door_open ? 'OPEN' : 'Closed'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Equipment Tab
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function EquipmentTab({ facilityId }: { facilityId: string }) {
  const [equipment, setEquipment] = useState<EquipmentType[]>([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState({ name: '', equipment_type: 'compressor', manufacturer: '', model: '' })
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    try { const d = await api.listEquipment(facilityId); setEquipment(d.equipment) }
    catch (e) { console.error(e) } finally { setLoading(false) }
  }, [facilityId])

  useEffect(() => { load() }, [load])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true)
    try {
      await api.createEquipment(facilityId, { name: form.name, equipment_type: form.equipment_type, manufacturer: form.manufacturer || undefined, model: form.model || undefined })
      setForm({ name: '', equipment_type: 'compressor', manufacturer: '', model: '' }); setShowAdd(false); load()
    } catch (err) { console.error(err) } finally { setSaving(false) }
  }

  const handleDelete = async (eqId: string) => {
    try { await api.deleteEquipment(facilityId, eqId); load() } catch (e) { console.error(e) }
  }

  if (loading) return <LoadingSpinner />

  return (
    <div className="stack-lg">
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn-primary" onClick={() => setShowAdd(true)}><Plus size={15} /> Add Equipment</button>
      </div>

      {showAdd && (
        <div className="card" style={{ padding: 20 }}>
          <form onSubmit={handleAdd} className="inline-form">
            <div className="field">
              <label>Name</label>
              <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Compressor #1" required />
            </div>
            <div className="field">
              <label>Type</label>
              <select value={form.equipment_type} onChange={e => setForm({ ...form, equipment_type: e.target.value })}>
                <option value="compressor">Compressor</option>
                <option value="evaporator">Evaporator</option>
                <option value="condenser">Condenser</option>
                <option value="controller">Controller</option>
                <option value="vfd">VFD</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div className="field">
              <label>Manufacturer</label>
              <input value={form.manufacturer} onChange={e => setForm({ ...form, manufacturer: e.target.value })} placeholder="Frick / Vilter" />
            </div>
            <div className="field">
              <label>Model</label>
              <input value={form.model} onChange={e => setForm({ ...form, model: e.target.value })} placeholder="RWB II" />
            </div>
            <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Adding...' : 'Add'}</button>
            <button type="button" className="btn-secondary" onClick={() => setShowAdd(false)}>Cancel</button>
          </form>
        </div>
      )}

      {equipment.length === 0 ? (
        <div className="empty-state"><div className="empty-icon"><Cpu size={28} /></div><h3>No equipment registered</h3><p>Add compressors, evaporators, and controllers to track your system.</p></div>
      ) : (
        <div className="card">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Type</th><th>Manufacturer</th><th>Model</th><th>Added</th><th style={{ width: 48 }}></th></tr></thead>
            <tbody>
              {equipment.map(eq => (
                <tr key={eq.id}>
                  <td><span className="cell-primary">{eq.name}</span></td>
                  <td><span className="badge badge-info">{eq.equipment_type}</span></td>
                  <td>{eq.manufacturer || '\u2014'}</td>
                  <td>{eq.model || '\u2014'}</td>
                  <td><span className="text-muted">{new Date(eq.created_at).toLocaleDateString()}</span></td>
                  <td><button className="icon-btn-sm" onClick={(e) => { e.stopPropagation(); handleDelete(eq.id) }} title="Delete"><Trash2 size={14} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Bills Tab
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function BillsTab({ facilityId }: { facilityId: string }) {
  const [bills, setBills] = useState<Bill[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [analyzing, setAnalyzing] = useState<string | null>(null)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try { const d = await api.listBills(facilityId); setBills(d.bills) }
    catch (e) { console.error(e) } finally { setLoading(false) }
  }, [facilityId])

  useEffect(() => { load() }, [load])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return
    setUploading(true); setError('')
    try { await api.uploadBills(facilityId, file); await load() }
    catch (err) { setError(err instanceof Error ? err.message : 'Upload failed') }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const handleAnalyze = async (id: string) => {
    setAnalyzing(id)
    try { await api.analyzeBill(facilityId, id) }
    catch (err) { setError(err instanceof Error ? err.message : 'Analysis failed') }
    finally { setAnalyzing(null) }
  }

  const handleDelete = async (id: string) => {
    try { await api.deleteBill(facilityId, id); await load() } catch (e) { console.error(e) }
  }

  if (loading) return <LoadingSpinner />

  return (
    <div className="stack-lg">
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn-primary" onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? <><Loader2 size={14} className="spin" /> Uploading...</> : <><Upload size={14} /> Upload Bill</>}
        </button>
        <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload} style={{ display: 'none' }} />
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      {bills.length === 0 ? (
        <div className="empty-state"><div className="empty-icon"><FileText size={28} /></div><h3>No bills uploaded</h3><p>Upload utility bills to analyze demand charges and savings.</p></div>
      ) : (
        <div className="card">
          <table className="data-table">
            <thead><tr><th>Period</th><th>Usage</th><th>Total Cost</th><th>Peak kW</th><th>Demand $</th><th>Energy $</th><th style={{ width: 80 }}>Actions</th></tr></thead>
            <tbody>
              {bills.map(b => (
                <tr key={b.id}>
                  <td><span className="text-muted">{new Date(b.period_start).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}</span></td>
                  <td>{b.total_kwh ? `${Number(b.total_kwh).toLocaleString()} kWh` : '\u2014'}</td>
                  <td><span className="cell-primary">{b.total_cost ? `$${Number(b.total_cost).toLocaleString()}` : '\u2014'}</span></td>
                  <td><span style={{ color: 'var(--danger)', fontWeight: 600 }}>{b.peak_demand_kw ? Number(b.peak_demand_kw).toLocaleString() : '\u2014'}</span></td>
                  <td><span style={{ color: 'var(--warning)' }}>{b.demand_charge ? `$${Number(b.demand_charge).toLocaleString()}` : '\u2014'}</span></td>
                  <td><span style={{ color: 'var(--accent)' }}>{b.energy_charge ? `$${Number(b.energy_charge).toLocaleString()}` : '\u2014'}</span></td>
                  <td>
                    <div style={{ display: 'flex', gap: 4 }}>
                      <button className="icon-btn-sm" onClick={() => handleAnalyze(b.id)} disabled={analyzing === b.id} title="Analyze">
                        {analyzing === b.id ? <Loader2 size={14} className="spin" /> : <Eye size={14} />}
                      </button>
                      <button className="icon-btn-sm danger" onClick={() => handleDelete(b.id)} title="Delete"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Facility Demand Tab
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function FacilityDemandTab({ facilityId }: { facilityId: string }) {
  const [data, setData] = useState<DemandAnalysis | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    api.listAnalyses(facilityId).then(r => setData(r.analyses?.length ? r.analyses[0] : null)).catch(console.error).finally(() => setLoading(false))
  }, [facilityId])
  if (loading) return <LoadingSpinner />
  if (!data) return <div className="empty-state"><div className="empty-icon"><Gauge size={28} /></div><h3>No analysis data</h3><p>Upload bills to see demand analysis and trends.</p></div>

  return (
    <div className="stack-lg">
      <div className="card">
        <div className="card-header"><h3>Demand vs Target</h3><span className="card-subtitle">Last 7 months</span></div>
        <div className="card-body" style={{ padding: '0 12px 12px' }}>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={mockDemandData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="peakG" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--danger)" stopOpacity={0.2} /><stop offset="100%" stopColor="var(--danger)" stopOpacity={0} /></linearGradient>
                <linearGradient id="avgG" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity={0.2} /><stop offset="100%" stopColor="var(--accent)" stopOpacity={0} /></linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="month" stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
              <YAxis stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="peak" stroke="var(--danger)" fill="url(#peakG)" name="Peak kW" />
              <Area type="monotone" dataKey="avg" stroke="var(--accent)" fill="url(#avgG)" name="Avg kW" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Controls Tab
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function ControlsTab({ facilityId }: { facilityId?: string }) {
  const { site } = useContext(SiteCtx)
  const fId = facilityId || site?.id
  const [sequences, setSequences] = useState<ControlSequence[]>([])
  const [rules, setRules] = useState<AutomationRule[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'sequences' | 'rules'>('sequences')

  useEffect(() => {
    if (!fId) { setLoading(false); return }
    Promise.all([api.listSequences(fId), api.listAutomationRules(fId)])
      .then(([s, r]) => { setSequences(s.sequences || []); setRules(r.rules || []) })
      .catch(console.error).finally(() => setLoading(false))
  }, [fId])

  if (loading) return <LoadingSpinner />

  return (
    <div className="stack-lg">
      <div className="tab-toggle">
        <button className={tab === 'sequences' ? 'active' : ''} onClick={() => setTab('sequences')}>Sequences ({sequences.length})</button>
        <button className={tab === 'rules' ? 'active' : ''} onClick={() => setTab('rules')}>Rules ({rules.length})</button>
      </div>

      {tab === 'sequences' && (sequences.length === 0 ? (
        <div className="card" style={{ padding: 24 }}>
          <p className="text-muted" style={{ marginBottom: 16 }}>No sequences yet. Get started with common cold storage automation:</p>
          <div className="scenario-grid">
            <ScenarioChip color="var(--accent)" title="Pre-cool Before Peak TOU" desc="Demand response" />
            <ScenarioChip color="var(--success)" title="Staggered Compressor Startup" desc="Load shedding" />
            <ScenarioChip color="var(--warning)" title="Night Setback Recovery" desc="Setpoint adjust" />
          </div>
        </div>
      ) : (
        <div className="card">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Type</th><th>Priority</th><th>Enabled</th><th>Last Run</th><th>Runs</th><th style={{ width: 50 }}></th></tr></thead>
            <tbody>
              {sequences.map(seq => (
                <tr key={seq.id}>
                  <td><span className="cell-primary">{seq.name}</span></td>
                  <td>{seq.sequence_type || '\u2014'}</td>
                  <td>{seq.priority ?? '\u2014'}</td>
                  <td>{seq.enabled ? <span className="badge badge-success">Active</span> : <span className="badge badge-neutral">Off</span>}</td>
                  <td><span className="text-muted">{seq.last_run_at ? new Date(seq.last_run_at).toLocaleDateString() : '\u2014'}</span></td>
                  <td>{seq.run_count ?? 0}</td>
                  <td><button className="icon-btn-sm" title="Run"><PlayCircle size={14} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {tab === 'rules' && (rules.length === 0 ? (
        <div className="empty-state"><p className="text-muted">No automation rules configured</p></div>
      ) : (
        <div className="card">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Enabled</th><th>Conditions</th><th>Cooldown</th><th>Last Triggered</th><th>Executions</th></tr></thead>
            <tbody>
              {rules.map(rule => (
                <tr key={rule.id}>
                  <td><span className="cell-primary">{rule.name}</span></td>
                  <td>{rule.enabled ? <span className="badge badge-success">Active</span> : <span className="badge badge-neutral">Off</span>}</td>
                  <td>{Object.keys(rule.trigger_conditions).length} conditions</td>
                  <td>{rule.cooldown_minutes}m</td>
                  <td><span className="text-muted">{rule.last_triggered_at ? new Date(rule.last_triggered_at).toLocaleDateString() : '\u2014'}</span></td>
                  <td>{rule.execution_count_today ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Agent Tab
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function AgentTab({ facilityId }: { facilityId?: string }) {
  const { site } = useContext(SiteCtx)
  const fId = facilityId || site?.id
  const [agents, setAgents] = useState<EdgeAgent[]>([])
  const [loading, setLoading] = useState(true)
  const [registering, setRegistering] = useState(false)
  const [regName, setRegName] = useState('')

  useEffect(() => {
    if (!fId) { setLoading(false); return }
    api.listAgents(fId).then(r => setAgents(r.agents || [])).catch(console.error).finally(() => setLoading(false))
  }, [fId])

  const handleRegister = async () => {
    if (!fId || !regName) return
    setRegistering(true)
    try { await api.registerAgent(fId, { name: regName }); setRegName(''); const r = await api.listAgents(fId); setAgents(r.agents || []) }
    catch (e) { console.error(e) } finally { setRegistering(false) }
  }

  if (loading) return <LoadingSpinner />

  return (
    <div className="stack-lg">
      <div className="card" style={{ padding: 16 }}>
        <div className="inline-form">
          <div className="field" style={{ flex: 1 }}>
            <label>Register new agent</label>
            <input value={regName} onChange={e => setRegName(e.target.value)} placeholder="Edge Agent name" />
          </div>
          <button className="btn-primary" onClick={handleRegister} disabled={registering || !regName}>
            {registering ? 'Registering...' : 'Register'}
          </button>
        </div>
      </div>

      {agents.length === 0 ? (
        <div className="empty-state"><div className="empty-icon"><Radio size={28} /></div><h3>No edge agents</h3><p>Register an edge agent to enable local device control and telemetry.</p></div>
      ) : (
        <div className="agent-grid">
          {agents.map(agent => (
            <div key={agent.id} className="card agent-card">
              <div className="agent-card-header">
                <div>
                  <h4>{agent.name}</h4>
                  <span className="text-muted">{agent.hardware_type || 'Generic'}</span>
                </div>
                <span className={`badge ${agent.connection_state === 'connected' ? 'badge-success' : 'badge-danger'}`}>
                  {agent.connection_state === 'connected' ? <><Wifi size={12} /> Connected</> : <><WifiOff size={12} /> Offline</>}
                </span>
              </div>
              <div className="agent-card-meta">
                <div><strong>Version:</strong> {agent.version || '\u2014'}</div>
                <div><strong>IP:</strong> {agent.ip_address || '\u2014'}</div>
                <div><strong>Heartbeat:</strong> {agent.last_heartbeat ? new Date(agent.last_heartbeat).toLocaleString() : '\u2014'}</div>
              </div>
              {(agent.cpu_percent !== null || agent.memory_percent !== null) && (
                <div className="agent-bars">
                  {agent.cpu_percent !== null && <ResourceBar label="CPU" value={agent.cpu_percent} color="var(--accent)" />}
                  {agent.memory_percent !== null && <ResourceBar label="Memory" value={agent.memory_percent} color="var(--success)" />}
                  {agent.disk_percent !== null && <ResourceBar label="Disk" value={agent.disk_percent} color="var(--warning)" />}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Integrations Tab
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function IntegrationsTab({ facilityId }: { facilityId: string }) {
  const [integrations, setIntegrations] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.listIntegrations(facilityId).then(r => setIntegrations(r.integrations || [])).catch(console.error).finally(() => setLoading(false))
  }, [facilityId])

  if (loading) return <LoadingSpinner />

  return (
    <div className="stack-lg">
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn-primary"><Plus size={15} /> Add Integration</button>
      </div>

      {integrations.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><Radio size={28} /></div>
          <h3>No integrations configured</h3>
          <p>Connect to Emerson, Danfoss, Honeywell, JCI, Schneider, or local Modbus/BACnet devices.</p>
          <div className="scenario-grid" style={{ marginTop: 20 }}>
            <ScenarioChip color="var(--accent)" title="Emerson Oversight" desc="E2/E3 controllers" />
            <ScenarioChip color="var(--success)" title="Danfoss Alsense" desc="AK-series" />
            <ScenarioChip color="var(--warning)" title="Honeywell Niagara" desc="BAS middleware" />
            <ScenarioChip color="#7c3aed" title="Modbus TCP" desc="Edge protocol" />
          </div>
        </div>
      ) : (
        <div className="card">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Provider</th><th>Type</th><th>State</th><th>Last Poll</th><th>Readings</th></tr></thead>
            <tbody>
              {integrations.map((i: any) => (
                <tr key={i.id}>
                  <td><span className="cell-primary">{i.name}</span></td>
                  <td>{i.provider}</td>
                  <td><span className="badge badge-info">{i.integration_type}</span></td>
                  <td><span className={`badge ${i.connection_state === 'connected' ? 'badge-success' : i.connection_state === 'error' ? 'badge-danger' : 'badge-neutral'}`}>{i.connection_state}</span></td>
                  <td><span className="text-muted">{i.last_poll_at ? new Date(i.last_poll_at).toLocaleString() : '\u2014'}</span></td>
                  <td>{(i.total_readings_ingested ?? 0).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Alerts Page
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function AlertsPage() {
  const { site } = useContext(SiteCtx)
  if (!site) return null
  return (
    <div className="page-container">
      <PageHeader title="Alerts & Events" subtitle={site.name} />
      <div className="content-area">
        <div className="empty-state"><div className="empty-icon"><AlertTriangle size={28} /></div><h3>No active alerts</h3><p>All systems operating within normal parameters.</p></div>
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Demand Page (portfolio-wide)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function DemandPage() {
  return (
    <div className="page-container">
      <PageHeader title="Demand Analysis" subtitle="Portfolio-wide peak demand trends" />
      <div className="content-area">
        <div className="card">
          <div className="card-header"><h3>Peak Demand Trends</h3><span className="card-subtitle">Last 7 months across all facilities</span></div>
          <div className="card-body" style={{ padding: '0 12px 12px' }}>
            <ResponsiveContainer width="100%" height={350}>
              <AreaChart data={mockDemandData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <defs><linearGradient id="dG" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--danger)" stopOpacity={0.2} /><stop offset="100%" stopColor="var(--danger)" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis dataKey="month" stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                <YAxis stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="peak" stroke="var(--danger)" fill="url(#dG)" name="Peak kW" />
                <Line type="monotone" dataKey="target" stroke="var(--success)" strokeDasharray="5 5" name="Target" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Savings Page
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function SavingsPage() {
  return (
    <div className="page-container">
      <PageHeader title="Savings Simulator" subtitle="Model energy savings from operational improvements" />
      <div className="content-area">
        <div className="savings-grid stagger">
          <SavingsCard title="Pre-cool Before Peak TOU" desc="Cool zones 2\u00b0F below setpoint during off-peak to reduce peak demand." savings="12-15%" color="var(--accent)" />
          <SavingsCard title="Compressor Load Shedding" desc="Stagger compressor ramp-ups to flatten demand spikes." savings="8-10%" color="var(--success)" />
          <SavingsCard title="Night Setback Recovery" desc="Raise setpoints during peak hours, recover overnight." savings="5-8%" color="var(--warning)" />
          <SavingsCard title="Evaporator Fan VFD" desc="Variable speed fans reduce energy while maintaining temps." savings="10-14%" color="#7c3aed" />
        </div>
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Bills Page (portfolio-wide)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function BillsPage() {
  const { facilities } = useContext(SiteCtx)
  const [allBills, setAllBills] = useState<(Bill & { facility_name: string })[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadFacilityId, setUploadFacilityId] = useState('')
  const [showUpload, setShowUpload] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(() => {
    if (!facilities.length) { setLoading(false); return }
    setLoading(true)
    Promise.all(facilities.map(f => api.listBills(f.id).then(d => d.bills.map(b => ({ ...b, facility_name: f.name })))))
      .then(r => setAllBills(r.flat().sort((a, b) => b.period_start.localeCompare(a.period_start))))
      .catch(console.error).finally(() => setLoading(false))
  }, [facilities])

  useEffect(() => { load() }, [load])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file || !uploadFacilityId) return
    setUploading(true); setError('')
    try { await api.uploadBills(uploadFacilityId, file); setShowUpload(false); load() }
    catch (err) { setError(err instanceof Error ? err.message : 'Upload failed') }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const totalSpend = allBills.reduce((s, b) => s + Number(b.total_cost ?? 0), 0)
  const totalDemand = allBills.reduce((s, b) => s + Number(b.demand_charge ?? 0), 0)

  return (
    <div className="page-container">
      <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload} style={{ display: 'none' }} />
      <PageHeader title="Utility Bills" subtitle={`${allBills.length} bills across ${facilities.length} facilities`}>
        <button className="btn-primary" onClick={() => setShowUpload(!showUpload)}><Upload size={15} /> Upload Bill</button>
      </PageHeader>

      {showUpload && (
        <div className="card inline-upload">
          <span className="text-secondary">Upload to:</span>
          <select value={uploadFacilityId} onChange={e => setUploadFacilityId(e.target.value)}>
            <option value="">Select facility</option>
            {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <button className="btn-primary" onClick={() => uploadFacilityId && fileRef.current?.click()} disabled={!uploadFacilityId || uploading}>
            {uploading ? 'Uploading...' : 'Choose CSV'}
          </button>
          <button className="btn-secondary" onClick={() => setShowUpload(false)}>Cancel</button>
          {error && <span className="text-danger">{error}</span>}
        </div>
      )}

      {allBills.length > 0 && (
        <div className="stat-grid stagger">
          <StatCard icon={<FileText size={18} />} color="var(--accent)" value={String(allBills.length)} label="Total Bills" />
          <StatCard icon={<DollarSign size={18} />} color="var(--warning)" value={`$${Math.round(totalSpend).toLocaleString()}`} label="Total Spend" />
          <StatCard icon={<Zap size={18} />} color="var(--danger)" value={`$${Math.round(totalDemand).toLocaleString()}`} label="Demand Charges" />
          <StatCard icon={<TrendingDown size={18} />} color="var(--success)" value={totalSpend > 0 ? `${Math.round(totalDemand / totalSpend * 100)}%` : '--'} label="Demand % of Bill" />
        </div>
      )}

      <div className="content-area">
        {loading ? <LoadingSpinner /> : allBills.length === 0 ? (
          <div className="empty-state"><div className="empty-icon"><FileText size={28} /></div><h3>No bills uploaded</h3><p>Upload utility bills to see cost analysis and savings opportunities.</p></div>
        ) : (
          <div className="card">
            <table className="data-table">
              <thead><tr><th>Facility</th><th>Period</th><th>Usage</th><th>Total Cost</th><th>Peak kW</th><th>Demand $</th><th>Energy $</th></tr></thead>
              <tbody>
                {allBills.map(b => (
                  <tr key={b.id}>
                    <td><span className="cell-primary">{b.facility_name}</span></td>
                    <td><span className="text-muted">{new Date(b.period_start).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })}</span></td>
                    <td>{b.total_kwh ? `${Number(b.total_kwh).toLocaleString()} kWh` : '\u2014'}</td>
                    <td><span className="cell-primary">{b.total_cost ? `$${Number(b.total_cost).toLocaleString()}` : '\u2014'}</span></td>
                    <td><span style={{ color: 'var(--danger)', fontWeight: 600 }}>{b.peak_demand_kw ? Number(b.peak_demand_kw).toLocaleString() : '\u2014'}</span></td>
                    <td><span style={{ color: 'var(--warning)' }}>{b.demand_charge ? `$${Number(b.demand_charge).toLocaleString()}` : '\u2014'}</span></td>
                    <td><span style={{ color: 'var(--accent)' }}>{b.energy_charge ? `$${Number(b.energy_charge).toLocaleString()}` : '\u2014'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Site Comparison Page
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function ComparisonPage() {
  const { facilities } = useContext(SiteCtx)
  const [selected, setSelected] = useState<string[]>([])
  const [siteData, setSiteData] = useState<Record<string, { bills: Bill[]; equipment: number }>>({})
  const [loading, setLoading] = useState(false)

  const toggleSite = (id: string) => {
    setSelected(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id])
  }

  useEffect(() => {
    if (selected.length === 0) return
    setLoading(true)
    Promise.all(selected.map(async id => {
      const [bills, eq] = await Promise.all([api.listBills(id), api.listEquipment(id)])
      return { id, bills: bills.bills, equipment: eq.total }
    }))
      .then(results => {
        const data: Record<string, { bills: Bill[]; equipment: number }> = {}
        results.forEach(r => { data[r.id] = { bills: r.bills, equipment: r.equipment } })
        setSiteData(data)
      })
      .catch(console.error).finally(() => setLoading(false))
  }, [selected])

  const colors = ['var(--accent)', 'var(--success)', 'var(--warning)', 'var(--danger)', '#7c3aed']

  // Build comparison data from bills
  const comparisonData: any[] = []
  if (selected.length >= 2) {
    const months = new Set<string>()
    selected.forEach(id => {
      siteData[id]?.bills.forEach(b => {
        months.add(new Date(b.period_start).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }))
      })
    })
    Array.from(months).sort().forEach(month => {
      const row: any = { month }
      selected.forEach(id => {
        const fac = facilities.find(f => f.id === id)
        const bill = siteData[id]?.bills.find(b =>
          new Date(b.period_start).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) === month
        )
        if (fac) row[fac.name] = bill?.peak_demand_kw ? Number(bill.peak_demand_kw) : null
      })
      comparisonData.push(row)
    })
  }

  return (
    <div className="page-container">
      <PageHeader title="Site Comparison" subtitle="Compare performance across facilities — works across different networks" />

      <div className="content-area">
        <div className="card" style={{ marginBottom: 20 }}>
          <div className="card-header"><h3>Select Sites to Compare</h3><span className="card-subtitle">Pick 2 or more facilities</span></div>
          <div className="card-body">
            <div className="compare-site-grid">
              {facilities.map((f, i) => (
                <button key={f.id} className={`compare-site-btn${selected.includes(f.id) ? ' active' : ''}`}
                  onClick={() => toggleSite(f.id)}
                  style={{ '--site-color': colors[i % colors.length] } as any}>
                  <div className="compare-site-check">
                    {selected.includes(f.id) && <Check size={14} />}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600 }}>{f.name}</div>
                    <div className="text-muted" style={{ fontSize: 12 }}>{f.city}, {f.state} {f.sqft ? `\u00b7 ${f.sqft.toLocaleString()} sqft` : ''}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading && <LoadingSpinner label="Loading comparison data..." />}

        {selected.length >= 2 && !loading && (
          <div className="stack-lg">
            {/* Summary table */}
            <div className="card">
              <div className="card-header"><h3>Summary</h3></div>
              <table className="data-table">
                <thead><tr><th>Metric</th>{selected.map(id => { const f = facilities.find(x => x.id === id); return <th key={id}>{f?.name}</th> })}</tr></thead>
                <tbody>
                  <tr>
                    <td><span className="cell-primary">Equipment</span></td>
                    {selected.map(id => <td key={id}>{siteData[id]?.equipment ?? 0} units</td>)}
                  </tr>
                  <tr>
                    <td><span className="cell-primary">Total Bills</span></td>
                    {selected.map(id => <td key={id}>{siteData[id]?.bills.length ?? 0}</td>)}
                  </tr>
                  <tr>
                    <td><span className="cell-primary">Avg Monthly Cost</span></td>
                    {selected.map(id => {
                      const b = siteData[id]?.bills || []
                      const avg = b.length ? b.reduce((s, x) => s + Number(x.total_cost ?? 0), 0) / b.length : 0
                      return <td key={id}>{avg > 0 ? `$${Math.round(avg).toLocaleString()}` : '\u2014'}</td>
                    })}
                  </tr>
                  <tr>
                    <td><span className="cell-primary">Avg Peak Demand</span></td>
                    {selected.map(id => {
                      const b = siteData[id]?.bills.filter(x => x.peak_demand_kw) || []
                      const avg = b.length ? b.reduce((s, x) => s + Number(x.peak_demand_kw ?? 0), 0) / b.length : 0
                      return <td key={id}><span style={{ color: 'var(--danger)', fontWeight: 600 }}>{avg > 0 ? `${Math.round(avg)} kW` : '\u2014'}</span></td>
                    })}
                  </tr>
                  <tr>
                    <td><span className="cell-primary">Demand % of Bill</span></td>
                    {selected.map(id => {
                      const b = siteData[id]?.bills || []
                      const totalCost = b.reduce((s, x) => s + Number(x.total_cost ?? 0), 0)
                      const totalDemand = b.reduce((s, x) => s + Number(x.demand_charge ?? 0), 0)
                      return <td key={id}>{totalCost > 0 ? `${Math.round(totalDemand / totalCost * 100)}%` : '\u2014'}</td>
                    })}
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Peak demand comparison chart */}
            {comparisonData.length > 0 && (
              <div className="card">
                <div className="card-header"><h3>Peak Demand Comparison</h3><span className="card-subtitle">kW by month</span></div>
                <div className="card-body" style={{ padding: '0 12px 12px' }}>
                  <ResponsiveContainer width="100%" height={320}>
                    <LineChart data={comparisonData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                      <XAxis dataKey="month" stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                      <YAxis stroke="var(--chart-text)" tick={{ fontSize: 11 }} />
                      <Tooltip content={<ChartTooltip />} />
                      {selected.map((id, i) => {
                        const fac = facilities.find(f => f.id === id)
                        return fac ? <Line key={id} type="monotone" dataKey={fac.name} stroke={colors[i % colors.length]} strokeWidth={2} dot={{ r: 3 }} connectNulls /> : null
                      })}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>
        )}

        {selected.length < 2 && !loading && (
          <div className="empty-state">
            <div className="empty-icon"><BarChart3 size={28} /></div>
            <h3>Select at least 2 sites</h3>
            <p>Comparison uses bill data already uploaded. No shared network required — Kelvex normalizes data from each site independently.</p>
          </div>
        )}
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Settings Page
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function SettingsPage() {
  const { theme, toggle } = useContext(ThemeCtx)
  return (
    <div className="page-container">
      <PageHeader title="Settings" subtitle="Platform configuration" />
      <div className="content-area">
        <div className="card" style={{ maxWidth: 600 }}>
          <div className="card-header"><h3>Appearance</h3></div>
          <div className="card-body">
            <div className="setting-row">
              <div>
                <div className="cell-primary">Theme</div>
                <div className="text-muted">Switch between light and dark mode</div>
              </div>
              <button className="btn-secondary" onClick={toggle}>
                {theme === 'light' ? <><Moon size={14} /> Dark Mode</> : <><Sun size={14} /> Light Mode</>}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Add Facility Modal
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function AddFacilityModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({ name: '', city: '', state: '', sqft: '' })
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setSaving(true)
    try {
      await api.createFacility({ name: form.name, city: form.city || undefined, state: form.state || undefined, sqft: form.sqft ? parseInt(form.sqft) : undefined })
      onSuccess()
    } catch (err) { console.error(err) } finally { setSaving(false) }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Facility</h3>
          <button className="icon-btn" onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="modal-body">
          <div className="field">
            <label>Facility name</label>
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="e.g. Main Distribution Center" required autoFocus />
          </div>
          <div className="field-row">
            <div className="field" style={{ flex: 2 }}>
              <label>City</label>
              <input value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} placeholder="Dallas" />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>State</label>
              <input value={form.state} onChange={e => setForm({ ...form, state: e.target.value.toUpperCase() })} placeholder="TX" maxLength={2} />
            </div>
          </div>
          <div className="field">
            <label>Square footage</label>
            <input type="number" value={form.sqft} onChange={e => setForm({ ...form, sqft: e.target.value })} placeholder="250000" />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Adding...' : <><Plus size={15} /> Add Facility</>}</button>
          </div>
        </form>
      </div>
    </div>
  )
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Shared Components
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
function PageHeader({ title, subtitle, children, backAction }: { title: string; subtitle?: string; children?: React.ReactNode; backAction?: () => void }) {
  return (
    <div className="page-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {backAction && <button className="icon-btn" onClick={backAction}><ArrowLeft size={18} /></button>}
        <div>
          <h1 className="page-title">{title}</h1>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
        </div>
      </div>
      {children && <div className="page-actions">{children}</div>}
    </div>
  )
}

function StatCard({ icon, color, value, label }: { icon: React.ReactNode; color: string; value: string; label: string }) {
  return (
    <div className="stat-card">
      <div className="stat-icon" style={{ color, background: `color-mix(in srgb, ${color} 10%, transparent)` }}>{icon}</div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  )
}

function LoadingSpinner({ label }: { label?: string }) {
  return (
    <div className="loading-state">
      <Loader2 size={20} className="spin" style={{ color: 'var(--accent)' }} />
      {label && <span>{label}</span>}
    </div>
  )
}

function ResourceBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="resource-bar">
      <div className="resource-bar-header"><span>{label}</span><span>{value}%</span></div>
      <div className="resource-bar-track"><div className="resource-bar-fill" style={{ width: `${value}%`, background: color }} /></div>
    </div>
  )
}

function SavingsCard({ title, desc, savings, color }: { title: string; desc: string; savings: string; color: string }) {
  return (
    <div className="savings-card" style={{ '--card-accent': color } as any}>
      <div className="savings-card-icon"><TrendingDown size={18} /></div>
      <h4>{title}</h4>
      <p>{desc}</p>
      <div className="savings-card-value">~{savings} <span>demand reduction</span></div>
    </div>
  )
}

function ScenarioChip({ color, title, desc }: { color: string; title: string; desc: string }) {
  return (
    <div className="scenario-chip" style={{ '--chip-color': color } as any}>
      <h5>{title}</h5>
      <p>{desc}</p>
    </div>
  )
}
