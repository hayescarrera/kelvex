import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { SiteProvider } from './contexts/SiteContext'
import { Toaster } from 'react-hot-toast'
import ErrorBoundary from './components/ErrorBoundary'
import AppLayout from './components/layout/AppLayout'
import LoadingState from './components/ui/LoadingState'

// Eagerly loaded (needed immediately on auth check)
import Login from './pages/Login'

// Lazy-loaded page components
const FleetOverview = lazy(() => import('./pages/FleetOverview'))
const FinanceHome = lazy(() => import('./pages/FinanceHome'))
const OpsHome = lazy(() => import('./pages/OpsHome'))
const SitesPage = lazy(() => import('./pages/SitesPage'))
const FacilityDetail = lazy(() => import('./pages/FacilityDetail'))
const FacilityOverview = lazy(() => import('./pages/facility/FacilityOverview'))
const ZonesPage = lazy(() => import('./pages/facility/ZonesPage'))
const EquipmentPage = lazy(() => import('./pages/facility/EquipmentPage'))
const BillsPage = lazy(() => import('./pages/facility/BillsPage'))
const DemandTab = lazy(() => import('./pages/facility/DemandTab'))
const ControlsPage = lazy(() => import('./pages/facility/ControlsPage'))
const AgentsPage = lazy(() => import('./pages/facility/AgentsPage'))
const IntegrationsPage = lazy(() => import('./pages/facility/IntegrationsPage'))
const AlertsPage = lazy(() => import('./pages/AlertsPage'))
const DemandPage = lazy(() => import('./pages/DemandPage'))
const SavingsSimulator = lazy(() => import('./pages/SavingsSimulator'))
const BillsGlobal = lazy(() => import('./pages/BillsGlobal'))
const SiteComparison = lazy(() => import('./pages/SiteComparison'))
const AutomationPage = lazy(() => import('./pages/AutomationPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const CompressorFleet = lazy(() => import('./pages/CompressorFleet'))
const EnergyOptimization = lazy(() => import('./pages/EnergyOptimization'))
const EdgeAgentsPage = lazy(() => import('./pages/EdgeAgentsPage'))
const LiveMonitorPage = lazy(() => import('./pages/LiveMonitorPage'))
const UserManagementPage = lazy(() => import('./pages/UserManagementPage'))
const AlertRulesPage = lazy(() => import('./pages/AlertRulesPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const DocumentsPage = lazy(() => import('./pages/DocumentsPage'))
const ControllerAccessPage = lazy(() => import('./pages/ControllerAccessPage'))
const NotificationSettingsPage = lazy(() => import('./pages/NotificationSettingsPage'))
const AcceptInvitePage = lazy(() => import('./pages/AcceptInvitePage'))
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage'))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'))
const ActivityLogPage = lazy(() => import('./pages/ActivityLogPage'))
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'))
const LeakTrackingPage = lazy(() => import('./pages/LeakTrackingPage'))
const MaintenancePage = lazy(() => import('./pages/MaintenancePage'))
const FacilityMapPage = lazy(() => import('./pages/FacilityMapPage'))
const NotFound = lazy(() => import('./pages/NotFound'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
})

function ProtectedLayout() {
  return (
    <SiteProvider>
      <AppLayout>
        <ErrorBoundary>
          <Suspense fallback={<LoadingState label="Loading page..." />}>
            <Outlet />
          </Suspense>
        </ErrorBoundary>
      </AppLayout>
    </SiteProvider>
  )
}

function RoleHome() {
  const { user } = useAuth()
  switch (user?.role) {
    case 'finance':    return <FinanceHome />
    case 'technician': return <SitesPage />
    default:           return <FleetOverview />
  }
}

function RequireAuth() {
  const { isAuthenticated } = useAuth()
  const location = useLocation()
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />
  return <ProtectedLayout />
}

function AppRoutes() {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) return <LoadingState fullScreen label="Loading..." />

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" /> : <Login />}
      />
      <Route path="/accept-invite" element={<AcceptInvitePage />} />
      <Route path="/forgot-password" element={<Suspense fallback={null}><ForgotPasswordPage /></Suspense>} />
      <Route path="/reset-password" element={<Suspense fallback={null}><ResetPasswordPage /></Suspense>} />
      <Route element={<RequireAuth />}>
        {/* Role-aware home */}
        <Route index element={<RoleHome />} />

        {/* Named role landing pages (direct links from sidebar) */}
        <Route path="energy" element={<FinanceHome />} />
        <Route path="sites" element={<SitesPage />} />
        <Route path="operations" element={<OpsHome />} />

        {/* Site detail — spec: /sites/:siteId */}
        <Route path="sites/:facilityId" element={<FacilityDetail />}>
          <Route index element={<FacilityOverview />} />
          <Route path="map" element={<FacilityMapPage />} />
          <Route path="zones" element={<ZonesPage />} />
          <Route path="equipment" element={<EquipmentPage />} />
          <Route path="compressors" element={<CompressorFleet />} />
          <Route path="monitor" element={<LiveMonitorPage />} />
          <Route path="energy" element={<EnergyOptimization />} />
          <Route path="controls" element={<ControlsPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="bills" element={<BillsPage />} />
          <Route path="demand" element={<DemandTab />} />
        </Route>

        {/* Backward-compat alias: /facilities/:id → /sites/:id */}
        <Route path="facilities/:facilityId" element={<FacilityDetail />}>
          <Route index element={<FacilityOverview />} />
          <Route path="map" element={<FacilityMapPage />} />
          <Route path="zones" element={<ZonesPage />} />
          <Route path="equipment" element={<EquipmentPage />} />
          <Route path="compressors" element={<CompressorFleet />} />
          <Route path="monitor" element={<LiveMonitorPage />} />
          <Route path="energy" element={<EnergyOptimization />} />
          <Route path="controls" element={<ControlsPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
          <Route path="bills" element={<BillsPage />} />
          <Route path="demand" element={<DemandTab />} />
        </Route>

        {/* Global nav pages — spec §2 */}
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="refrigerant" element={<LeakTrackingPage />} />
        <Route path="maintenance" element={<MaintenancePage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="tunnel" element={<ControllerAccessPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="settings/notifications" element={<NotificationSettingsPage />} />
        <Route path="admin" element={<OnboardingPage />} />

        {/* Legacy paths — keep working */}
        <Route path="leak-tracking" element={<Navigate to="/refrigerant" replace />} />
        <Route path="compliance" element={<Navigate to="/refrigerant" replace />} />
        <Route path="food-safety" element={<Navigate to="/refrigerant" replace />} />
        <Route path="alert-rules" element={<AlertRulesPage />} />
        <Route path="demand" element={<DemandPage />} />
        <Route path="savings" element={<SavingsSimulator />} />
        <Route path="bills" element={<BillsGlobal />} />
        <Route path="compare" element={<SiteComparison />} />
        <Route path="automation" element={<AutomationPage />} />
        <Route path="schedules" element={<AutomationPage />} />
        <Route path="agents" element={<EdgeAgentsPage />} />
        <Route path="team" element={<UserManagementPage />} />
        <Route path="activity" element={<ActivityLogPage />} />
        <Route path="onboarding" element={<OnboardingPage />} />

        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ThemeProvider>
          <ErrorBoundary>
            <AppRoutes />
            <Toaster
              position="bottom-right"
              toastOptions={{
                duration: 3500,
                style: { background: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', fontSize: '0.875rem' },
                success: { iconTheme: { primary: 'var(--success)', secondary: '#fff' } },
                error: { iconTheme: { primary: 'var(--danger)', secondary: '#fff' }, duration: 5000 },
              }}
            />
          </ErrorBoundary>
        </ThemeProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
