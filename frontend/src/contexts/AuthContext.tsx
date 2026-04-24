import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { api } from '../lib/api'

import type { UserRole } from '../lib/api'

interface User {
  id: string
  email: string
  full_name: string
  org_id: string
  is_admin: boolean
  role: UserRole
}

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  permissions: string[]
  hasPermission: (perm: string) => boolean
  login: (accessToken: string, refreshToken: string) => Promise<void>
  logout: () => void
}

const AuthCtx = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  permissions: [],
  hasPermission: () => false,
  login: async () => {},
  logout: () => {},
})

export function useAuth() {
  return useContext(AuthCtx)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [permissions, setPermissions] = useState<string[]>([])

  const hasPermission = useCallback((perm: string) => permissions.includes(perm), [permissions])

  const logout = useCallback(() => {
    sessionStorage.removeItem('coldgrid_token')
    sessionStorage.removeItem('coldgrid_refresh_token')
    api.setTokens(null, null)
    setUser(null)
    setPermissions([])
  }, [])

  const fetchPermissions = useCallback(async () => {
    try {
      const perms = await api.getMyPermissions()
      setPermissions(perms.permissions)
    } catch {
      // Non-critical — permissions will be empty
    }
  }, [])

  const login = useCallback(async (accessToken: string, refreshToken: string) => {
    sessionStorage.setItem('coldgrid_token', accessToken)
    sessionStorage.setItem('coldgrid_refresh_token', refreshToken)
    api.setTokens(accessToken, refreshToken)
    const u = await api.getMe()
    const latestAccess = api.getToken()
    const latestRefresh = api.getRefreshToken()
    if (latestAccess) sessionStorage.setItem('coldgrid_token', latestAccess)
    if (latestRefresh) sessionStorage.setItem('coldgrid_refresh_token', latestRefresh)
    setUser(u as User)
    await fetchPermissions()
  }, [fetchPermissions])

  useEffect(() => {
    api.setUnauthorizedHandler(() => logout())
    return () => { api.setUnauthorizedHandler(null) }
  }, [logout])

  useEffect(() => {
    const accessToken = sessionStorage.getItem('coldgrid_token')
    const refreshToken = sessionStorage.getItem('coldgrid_refresh_token')
    if (!accessToken || !refreshToken) {
      setIsLoading(false)
      return
    }
    api.setTokens(accessToken, refreshToken)
    Promise.all([api.getMe(), api.getMyPermissions()])
      .then(([u, perms]) => {
        setUser(u as User)
        setPermissions(perms.permissions)
        const latest = api.getToken()
        const latestR = api.getRefreshToken()
        if (latest) sessionStorage.setItem('coldgrid_token', latest)
        if (latestR) sessionStorage.setItem('coldgrid_refresh_token', latestR)
      })
      .catch(() => {
        sessionStorage.removeItem('coldgrid_token')
        sessionStorage.removeItem('coldgrid_refresh_token')
        api.setTokens(null, null)
      })
      .finally(() => setIsLoading(false))
  }, [])

  return (
    <AuthCtx.Provider value={{ user, isAuthenticated: !!user, isLoading, permissions, hasPermission, login, logout }}>
      {children}
    </AuthCtx.Provider>
  )
}
