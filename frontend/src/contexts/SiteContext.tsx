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

export function SiteProvider({ children }: { children: ReactNode }) {
  const [site, setSiteState] = useState<Facility | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['facilities', 'list'],
    queryFn: () => api.listFacilities(),
    staleTime: 60_000,
  })

  const facilities = data?.facilities ?? []

  // Restore persisted site selection
  useEffect(() => {
    const savedId = sessionStorage.getItem('coldgrid_site')
    if (savedId && facilities.length > 0) {
      const found = facilities.find(f => f.id === savedId)
      if (found) setSiteState(found)
    }
  }, [facilities])

  const setSite = (f: Facility | null) => {
    setSiteState(f)
    if (f) {
      sessionStorage.setItem('coldgrid_site', f.id)
    } else {
      sessionStorage.removeItem('coldgrid_site')
    }
  }

  return (
    <SiteCtx.Provider value={{ site, setSite, facilities, isLoading }}>
      {children}
    </SiteCtx.Provider>
  )
}
