import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Building2, ChevronDown, Check, LayoutDashboard, Search } from 'lucide-react'
import { useSiteContext } from '../../contexts/SiteContext'
import type { Facility } from '../../lib/api'

export default function SiteSelector() {
  const { site, setSite, facilities } = useSiteContext()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
    else setQuery('')
  }, [open])

  // Extract the sub-path after /sites/:id so we can preserve it when switching
  function getSiteSubPath(): string {
    const m = location.pathname.match(/^\/sites\/[^/]+(\/.*)?$/)
    return m?.[1] ?? ''
  }

  function handleSelectSite(f: Facility) {
    setSite(f)
    const subPath = getSiteSubPath()
    navigate(`/sites/${f.id}${subPath}`)
    setOpen(false)
    setQuery('')
  }

  function handleSelectPortfolio() {
    setSite(null)
    navigate('/')
    setOpen(false)
    setQuery('')
  }

  const filtered = query.trim()
    ? facilities.filter(f =>
        f.name.toLowerCase().includes(query.toLowerCase()) ||
        f.city?.toLowerCase().includes(query.toLowerCase()) ||
        f.state?.toLowerCase().includes(query.toLowerCase())
      )
    : facilities

  const isPortfolio = !site

  return (
    <div className="site-selector" ref={ref}>
      <button
        className="site-selector-btn"
        onClick={() => setOpen(!open)}
        aria-label="Switch site"
      >
        <div className="site-selector-icon">
          {isPortfolio
            ? <LayoutDashboard size={14} />
            : <Building2 size={14} />
          }
        </div>
        <div className="site-selector-text">
          <span className="site-selector-label">
            {isPortfolio ? 'Viewing' : 'Active site'}
          </span>
          <span className="site-selector-name">
            {isPortfolio ? 'Portfolio' : site.name}
          </span>
        </div>
        <ChevronDown
          size={14}
          className="site-selector-chevron"
          style={{ transform: open ? 'rotate(180deg)' : 'none' }}
        />
      </button>

      {open && (
        <div className="site-selector-dropdown">
          {/* Search — only show if more than 4 sites */}
          {facilities.length > 4 && (
            <div className="site-search-wrap">
              <Search size={12} className="site-search-icon" />
              <input
                ref={inputRef}
                className="site-search-input"
                placeholder="Search sites…"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onClick={e => e.stopPropagation()}
              />
            </div>
          )}

          {/* Portfolio option */}
          {!query && (
            <>
              <button
                className={`site-option${isPortfolio ? ' active' : ''}`}
                onClick={handleSelectPortfolio}
              >
                <LayoutDashboard size={14} style={{ flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 500 }}>Portfolio</div>
                  <div style={{ fontSize: 11, opacity: 0.55 }}>All {facilities.length} sites</div>
                </div>
                {isPortfolio && <Check size={13} style={{ marginLeft: 'auto', flexShrink: 0 }} />}
              </button>
              <div className="site-option-divider" />
            </>
          )}

          {/* Site list */}
          {filtered.length === 0 ? (
            <div style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>
              No sites match "{query}"
            </div>
          ) : (
            filtered.map(f => (
              <button
                key={f.id}
                className={`site-option${site?.id === f.id ? ' active' : ''}`}
                onClick={() => handleSelectSite(f)}
              >
                <Building2 size={14} style={{ flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {f.name}
                  </div>
                  {(f.city || f.state) && (
                    <div style={{ fontSize: 11, opacity: 0.55 }}>
                      {[f.city, f.state].filter(Boolean).join(', ')}
                    </div>
                  )}
                </div>
                {site?.id === f.id && <Check size={13} style={{ marginLeft: 'auto', flexShrink: 0 }} />}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
