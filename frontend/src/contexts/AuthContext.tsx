import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { api, roleHome } from '../lib/api'

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
  login: (accessToken: string, refreshToken: string, persist?: boolean) => Promise<void>
  logout: () => void
  /** The default landing route for the current user's role. */
  homeRoute: string
}

const TOKEN_KEY = 'kelvex_token'
const REFRESH_KEY = 'kelvex_refresh_token'

function readToken() {
  return localStorage.getItem(TOKEN_KEY) ?? sessionStorage.getItem(TOKEN_KEY)
}
function readRefresh() {
  return localStorage.getItem(REFRESH_KEY) ?? sessionStorage.getItem(REFRESH_KEY)
}
function writeTokens(access: string, refresh: string, persist: boolean) {
  const store = persist ? localStorage : sessionStorage
  store.setItem(TOKEN_KEY, access)
  store.setItem(REFRESH_KEY, refresh)
}
function clearTokens() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
}
function isPersisted() {
  return !!localStorage.getItem(TOKEN_KEY)
}

const AuthCtx = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  permissions: [],
  hasPermission: () => false,
  login: async () => {},
  logout: () => {},
  homeRoute: '/',
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
    clearTokens()
    api.setTokens(null, null)
    setUser(null)
    setPermissions([])
  }, [])

  const fetchPermissions = useCallback(async () => {
    try {
      const perms = await api.getMyPermissions()
      setPermissions(perms.permissions)
    } catch {
      // Non-critical
    }
  }, [])

  const login = useCallback(async (accessToken: string, refreshToken: string, persist = false) => {
    writeTokens(accessToken, refreshToken, persist)
    api.setTokens(accessToken, refreshToken)
    const u = await api.getMe()
    // Persist any refreshed tokens that came back during getMe
    const latestAccess = api.getToken()
    const latestRefresh = api.getRefreshToken()
    if (latestAccess && latestRefresh) writeTokens(latestAccess, latestRefresh, persist)
    setUser(u as User)
    await fetchPermissions()
  }, [fetchPermissions])

  useEffect(() => {
    api.setUnauthorizedHandler(() => logout())
    return () => { api.setUnauthorizedHandler(null) }
  }, [logout])

  useEffect(() => {
    const accessToken = readToken()
    const refreshToken = readRefresh()
    if (!accessToken || !refreshToken) {
      setIsLoading(false)
      return
    }
    const persist = isPersisted()
    api.setTokens(accessToken, refreshToken)
    Promise.all([api.getMe(), api.getMyPermissions()])
      .then(([u, perms]) => {
        setUser(u as User)
        setPermissions(perms.permissions)
        const latest = api.getToken()
        const latestR = api.getRefreshToken()
        if (latest && latestR) writeTokens(latest, latestR, persist)
      })
      .catch(() => {
        clearTokens()
        api.setTokens(null, null)
      })
      .finally(() => setIsLoading(false))
  }, [])

  const homeRoute = user ? roleHome(user.role) : '/'

  return (
    <AuthCtx.Provider value={{ user, isAuthenticated: !!user, isLoading, permissions, hasPermission, login, logout, homeRoute }}>
      {children}
    </AuthCtx.Provider>
  )
}
