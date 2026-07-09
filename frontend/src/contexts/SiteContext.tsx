import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type Facility } from '../lib/api'

interface SiteContextType {
  site: Facility | null
  setSite: (f: Facility | null) => void
  facilities: Facility[]
  isLoading: boolean
}

const SiteCtx = createContext<SiteContextType>({
  site: null,
  setSite: () => {},
  facilities: [],
  isLoading: true,
})

export function useSiteContext() {
  return useContext(SiteCtx)
}

const STORAGE_KEY = 'kelvex_active_site'

export function SiteProvider({ children }: { children: ReactNode }) {
  const [site, setSiteState] = useState<Facility | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['facilities', 'list'],
    queryFn: () => api.listFacilities(),
    staleTime: 60_000,
  })

  const facilities = data?.facilities ?? []

  // Restore persisted site on load
  useEffect(() => {
    if (facilities.length === 0) return
    const savedId = localStorage.getItem(STORAGE_KEY)
    if (savedId) {
      const found = facilities.find(f => f.id === savedId)
      if (found) setSiteState(found)
    }
  }, [facilities])

  const setSite = (f: Facility | null) => {
    setSiteState(f)
    if (f) {
      localStorage.setItem(STORAGE_KEY, f.id)
    } else {
      localStorage.removeItem(STORAGE_KEY)
    }
  }

  return (
    <SiteCtx.Provider value={{ site, setSite, facilities, isLoading }}>
      {children}
    </SiteCtx.Provider>
  )
}
