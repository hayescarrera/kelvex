import { useState, useEffect, useRef } from 'react'
import { Building2, ChevronDown, Check } from 'lucide-react'
import { useSiteContext } from '../../contexts/SiteContext'
import type { Facility } from '../../lib/api'

interface SiteSelectorProps {
  onSelect?: (f: Facility) => void
}

export default function SiteSelector({ onSelect }: SiteSelectorProps) {
  const { site, setSite, facilities } = useSiteContext()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelect = (f: Facility | null) => {
    setSite(f)
    if (f && onSelect) onSelect(f)
    setOpen(false)
  }

  return (
    <div className="site-selector" ref={ref}>
      <button className="site-selector-btn" onClick={() => setOpen(!open)}>
        <div className="site-selector-icon"><Building2 size={14} /></div>
        <div className="site-selector-text">
          <span className="site-selector-label">Active Site</span>
          <span className="site-selector-name">{site ? site.name : 'All Sites'}</span>
        </div>
        <ChevronDown
          size={14}
          style={{ opacity: 0.5, transition: 'transform 150ms', transform: open ? 'rotate(180deg)' : 'none' }}
        />
      </button>
      {open && (
        <div className="site-selector-dropdown">
          <button
            className={`site-option${!site ? ' active' : ''}`}
            onClick={() => handleSelect(null)}
          >
            <Building2 size={14} />
            <span>All Sites</span>
            {!site && <Check size={14} style={{ marginLeft: 'auto' }} />}
          </button>
          <div className="site-option-divider" />
          {facilities.map(f => (
            <button
              key={f.id}
              className={`site-option${site?.id === f.id ? ' active' : ''}`}
              onClick={() => handleSelect(f)}
            >
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
