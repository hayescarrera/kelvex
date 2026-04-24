# ColdGrid — Full Production Buildout Prompt

You are the AI co-developer for **ColdGrid**, an enterprise operational intelligence platform for cold storage facilities. The solo human developer is the CEO/CTO. Your job is to take this working but rough prototype and ship it as a production-level, functional, and beautiful application that **cold storage operators, general managers, and VPs love to use**.

ColdGrid monitors refrigeration equipment, ingests telemetry from Modbus/BACnet controllers and cloud APIs (Danfoss, Emerson, Schneider, JCI, Honeywell), analyzes utility bills for demand charge optimization, runs automation sequences, and gives facility teams real-time visibility into their operations.

---

## 1. WHAT EXISTS TODAY — CODEBASE MAP

### Tech Stack
- **Backend:** FastAPI 0.115 · SQLAlchemy 2.0 (async) · asyncpg · TimescaleDB (PG 16) · Redis 7 · Celery · Alembic
- **Frontend:** React 18 · TypeScript 5.6 · Vite 6 · react-router-dom 6 · Recharts 2.13 · Lucide React · CSS custom properties (no Tailwind, no MUI)
- **Infra:** Docker Compose (backend, timescaledb, redis, frontend)

### Backend (solid — 91 passing tests)

```
backend/
  app/
    main.py                    # FastAPI app, lifespan (polling engine + register map seeds),
                               # global exception handlers, request logging middleware, CORS
    core/
      config.py                # Pydantic settings (DB, Redis, Auth, OpenEI, CORS)
      database.py              # async_session factory, engine
      security.py              # JWT (HS256), bcrypt passwords, get_current_user dependency
    api/v1/
      router.py                # 10 routers: auth, facilities, bills, equipment, savings,
                               #   zones, alerts, controls, agents, integrations
      auth.py                  # POST register/login/refresh, GET /me
      facilities.py            # CRUD + org-scoped filtering
      bills.py                 # CRUD + CSV upload + demand analysis trigger
      equipment.py             # CRUD per facility
      zones.py                 # CRUD + equipment assignment
      alerts.py                # List + acknowledge/resolve + summary
      controls.py              # Sequences, automation rules, schedules, commands
      agents.py                # Edge agent registration + heartbeat
      integrations.py          # Provider list, integration CRUD, credential CRUD,
                               #   register maps, device discovery, polling trigger
      savings.py               # Savings simulation endpoint
    models/
      user.py                  # Organization, User (org-scoped multi-tenancy)
      facility.py              # Facility (+ Equipment inline)
      zone.py                  # Zone
      alert.py                 # Alert
      control.py               # ControlSequence, AutomationRule, Schedule, ControlCommand
      agent.py                 # EdgeAgent
      integration.py           # Integration, IntegrationCredential, RegisterMap
      billing.py               # UtilityBill, DemandAnalysis
      telemetry.py             # Telemetry (TimescaleDB hypertable)
      tariff.py                # Utility, RateSchedule, RatePeriod
    schemas/                   # Pydantic v2 request/response schemas for every model
    services/
      demand_engine.py         # Bill analysis + demand charge optimization
      polling_engine.py        # Asyncio background poller for integrations
    integrations/
      base.py                  # Abstract adapter interface
      register_map_seeds.py    # Seed data for Modbus/BACnet register maps
      adapters/                # 7 adapters: danfoss, emerson, schneider, jci, honeywell,
                               #   modbus_tcp, bacnet_ip
  migrations/versions/
    001_initial_schema.py      # Core tables + TimescaleDB hypertable
    002_platform_layers.py     # Zones, alerts, controls, agents
    003_integrations.py        # Integrations, credentials, register maps
  tests/
    conftest.py                # SQLite+aiosqlite test infra with PG type patches
    test_auth.py (14)          test_facilities.py (13)    test_equipment.py (7)
    test_zones.py (7)          test_bills.py (9)          test_agents.py (11)
    test_controls.py (10)      test_integrations.py (8)   test_security.py (7)
    test_health.py (3)
```

**65+ API endpoints.** 11 SQLAlchemy models. 91 passing pytest tests covering auth, CRUD, org isolation, security. Global JSON error handlers. Password strength validation. Configurable CORS.

### Frontend (rough prototype — needs major work)

```
frontend/src/
  main.tsx                     # ReactDOM entry
  App.tsx                      # 2 routes: /login → Login, /* → Dashboard
  index.css                    # Full design system: CSS variables, component classes,
                               #   light/dark theme via [data-theme="dark"], responsive breakpoints
  pages/
    Login.tsx                  # Self-contained login page with inline styles
    Dashboard.tsx              # *** 1,517 lines — MONOLITHIC — contains EVERYTHING ***
  lib/
    api.ts                     # API client with ~38 methods, TS interfaces
  components/                  # EMPTY
  hooks/                       # EMPTY
```

**Dashboard.tsx is the single biggest problem.** It contains:
- `ThemeContext` (light/dark toggle, localStorage persistence)
- `SiteContext` (global facility selection)
- Navigation sidebar with 11 pages
- All 11 page views: Fleet Overview, Facility Detail (8 sub-tabs: overview, zones, equipment, bills, analysis, automation, agents, integrations), Alerts, Demand Analysis, Savings Simulator, Utility Bills, Site Comparison, Settings
- Inline "components": PageHeader, StatCard, LoadingSpinner, ResourceBar, SavingsCard, ScenarioChip, AddFacilityModal, ChartTooltip
- All data fetching (raw useEffect + useState, no caching)
- All event handlers
- All rendering logic

### Design System (index.css — already built)
The CSS design system is complete with variables for both themes and classes for: `.app-layout`, `.sidebar`, `.nav-item`, `.site-selector`, `.page-header`, `.card`, `.stat-card`, `.btn-primary/secondary/ghost`, `.icon-btn`, `.badge`, `.data-table`, `.tab-bar`, `.field`, `.inline-form`, `.zone-card`, `.empty-state`, `.loading-state`, `.modal-overlay`, `.modal`, `.alert`, `.agent-grid`, `.resource-bar`, `.savings-card`, `.scenario-chip`, `.site-card`, `.compare-site-grid`, `.setting-row`, `.chart-tooltip`, plus responsive breakpoints.

### API Client (api.ts — already built)
38 typed API methods covering auth, facilities, equipment, zones, bills, alerts, controls, agents, integrations, credentials, register maps, savings. Auto-redirects on 401.

---

## 2. THE MISSION — WHAT "DONE" LOOKS LIKE

ColdGrid should feel like a tool that a **cold storage operator feels at home using** — familiar patterns from industrial monitoring tools they already know — **but is impressed by**, not lost in. The UI should convey trust, precision, and operational clarity. Think: Datadog for cold storage. Clean, dense where it needs to be, spacious where it doesn't.

### Target Users
1. **Operators** (hourly, on the floor): need quick glance at zone temps, active alerts, equipment status. Mobile-friendly. Big numbers, color-coded severity.
2. **General Managers** (run the facility): need facility overview, utility bill trends, demand charge analysis, savings opportunities. Dashboard-first.
3. **VPs / Regional** (multi-site): need fleet overview, site comparison, cross-facility benchmarking. Summary metrics, drill-down capability.

### Design Principles
- **Light mode default**, dark mode as toggle (already in CSS variables)
- **Dense but not cluttered** — operators need information density; GMs/VPs need whitespace and hierarchy
- **Industrial trust** — muted blues, grays, clean borders. Accent colors only for status (green=normal, amber=warning, red=critical, blue=info)
- **Fast perceived performance** — skeleton loaders, optimistic updates, cached data
- **Zero training needed** — every button, tab, and chart should be self-explanatory

---

## 3. FRONTEND REBUILD — STEP BY STEP

This is the primary body of work. The backend is solid. The frontend needs a complete architectural overhaul while preserving the existing design system and API client.

### Phase 1: Foundation (do this FIRST)

#### 1A. Install dependencies
```bash
npm install @tanstack/react-query @tanstack/react-query-devtools
npm install -D @types/node
```
Do NOT install Tailwind, MUI, or any CSS framework. The design system in `index.css` is the source of truth.

#### 1B. Create the folder structure
```
src/
  components/
    layout/
      AppLayout.tsx            # Sidebar + main content shell
      Sidebar.tsx              # Navigation sidebar
      SiteSelector.tsx         # Global facility picker (dropdown in sidebar)
      PageHeader.tsx           # Reusable page header with breadcrumbs
    ui/
      StatCard.tsx             # Metric card (value, label, trend, icon)
      Badge.tsx                # Status badge (severity/connection state)
      DataTable.tsx            # Sortable, filterable table with pagination
      LoadingState.tsx         # Skeleton/spinner states
      EmptyState.tsx           # No-data illustrations
      Modal.tsx                # Reusable modal (overlay + content)
      ConfirmDialog.tsx        # Destructive action confirmation
      ChartTooltip.tsx         # Recharts custom tooltip
      ResourceBar.tsx          # Capacity/utilization bar
      TabBar.tsx               # Horizontal tab navigation
      AlertBanner.tsx          # Inline alert/notification
    charts/
      TemperatureChart.tsx     # Time-series temperature line chart
      DemandChart.tsx          # Demand (kW) bar/line chart
      CostBreakdownChart.tsx   # Pie/donut for bill cost breakdown
      LoadProfileChart.tsx     # 24hr load profile area chart
      ComparisonChart.tsx      # Multi-facility overlay chart
    forms/
      FacilityForm.tsx         # Create/edit facility
      EquipmentForm.tsx        # Create/edit equipment
      ZoneForm.tsx             # Create/edit zone
      BillUploadForm.tsx       # CSV upload + manual entry
      IntegrationForm.tsx      # Integration setup wizard
      SequenceForm.tsx         # Control sequence builder
      RuleForm.tsx             # Automation rule editor
  pages/
    FleetOverview.tsx          # Multi-site dashboard (VP view)
    FacilityDetail.tsx         # Single facility with tab navigation
    FacilityOverview.tsx       # Facility overview tab
    ZonesPage.tsx              # Zone map + list
    EquipmentPage.tsx          # Equipment list + status
    BillsPage.tsx              # Utility bill list + analysis
    DemandAnalysis.tsx         # Demand charge deep-dive
    AutomationPage.tsx         # Sequences + rules + schedules
    AgentsPage.tsx             # Edge agent management
    IntegrationsPage.tsx       # Integration management
    AlertsPage.tsx             # Alert feed + filters
    SavingsSimulator.tsx       # What-if demand response calculator
    SiteComparison.tsx         # Side-by-side facility comparison
    SettingsPage.tsx           # User/org settings
    Login.tsx                  # (keep existing, but refactor to use CSS classes)
    NotFound.tsx               # 404 page
  hooks/
    useAuth.ts                 # Auth context + token management
    useFacilities.ts           # TanStack Query hooks for facilities
    useEquipment.ts            # TanStack Query hooks for equipment
    useZones.ts                # TanStack Query hooks for zones
    useBills.ts                # TanStack Query hooks for bills + analyses
    useAlerts.ts               # TanStack Query hooks for alerts
    useControls.ts             # TanStack Query hooks for sequences/rules
    useAgents.ts               # TanStack Query hooks for agents
    useIntegrations.ts         # TanStack Query hooks for integrations
    useSavings.ts              # TanStack Query hooks for savings simulation
    useTheme.ts                # Theme context + toggle
    useSiteContext.ts          # Global facility selection
  contexts/
    AuthContext.tsx             # Auth provider (token, user, login/logout)
    ThemeContext.tsx            # Theme provider (light/dark)
    SiteContext.tsx             # Selected facility provider
  lib/
    api.ts                     # (keep existing — it's solid)
    constants.ts               # Status colors, severity levels, zone types
    formatters.ts              # Number/currency/date/temperature formatters
    types.ts                   # Shared TypeScript interfaces (extract from api.ts)
```

#### 1C. Set up providers (App.tsx)
```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { SiteProvider } from './contexts/SiteContext';
import { AppLayout } from './components/layout/AppLayout';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,        // 30s — telemetry is near-real-time
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ThemeProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </ThemeProvider>
      </AuthProvider>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}

function AppRoutes() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <LoadingState fullScreen />;

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" /> : <Login />} />
      <Route element={isAuthenticated ? <ProtectedLayout /> : <Navigate to="/login" />}>
        <Route index element={<FleetOverview />} />
        <Route path="facilities/:facilityId" element={<FacilityDetail />}>
          <Route index element={<FacilityOverview />} />
          <Route path="zones" element={<ZonesPage />} />
          <Route path="equipment" element={<EquipmentPage />} />
          <Route path="bills" element={<BillsPage />} />
          <Route path="demand" element={<DemandAnalysis />} />
          <Route path="automation" element={<AutomationPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="integrations" element={<IntegrationsPage />} />
        </Route>
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="savings" element={<SavingsSimulator />} />
        <Route path="compare" element={<SiteComparison />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

function ProtectedLayout() {
  return (
    <SiteProvider>
      <AppLayout>
        <Outlet />
      </AppLayout>
    </SiteProvider>
  );
}
```

#### 1D. Extract contexts from Dashboard.tsx

Pull `ThemeContext` and `SiteContext` into their own files. The auth context should manage the token lifecycle (login, logout, refresh, auto-redirect on 401). Wire the 401 handler in `api.ts` to call the auth context's logout function.

#### 1E. Build TanStack Query hooks

Every hook file should follow this pattern:
```tsx
// hooks/useFacilities.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../lib/api';

export const facilityKeys = {
  all: ['facilities'] as const,
  list: () => [...facilityKeys.all, 'list'] as const,
  detail: (id: string) => [...facilityKeys.all, 'detail', id] as const,
};

export function useFacilities() {
  return useQuery({
    queryKey: facilityKeys.list(),
    queryFn: () => api.listFacilities(),
  });
}

export function useFacility(id: string) {
  return useQuery({
    queryKey: facilityKeys.detail(id),
    queryFn: () => api.getFacility(id),
    enabled: !!id,
  });
}

export function useCreateFacility() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createFacility,
    onSuccess: () => qc.invalidateQueries({ queryKey: facilityKeys.list() }),
  });
}
```

Do this for every entity: facilities, equipment, zones, bills, alerts, controls, agents, integrations, credentials, register maps, savings. This eliminates all the scattered useEffect/useState data fetching in Dashboard.tsx.

### Phase 2: Component Extraction

#### 2A. Layout components
Extract `AppLayout`, `Sidebar`, `SiteSelector`, and `PageHeader` FIRST. These are the shell. Every page renders inside `<AppLayout>`. The sidebar should:
- Show the ColdGrid logo at top
- Have a `<SiteSelector>` dropdown that sets the global facility context
- Show navigation grouped into sections: **Monitor** (Fleet, Alerts), **Analyze** (Demand, Savings, Bills, Compare), **Control** (Automation), **Configure** (Agents, Integrations, Settings)
- Highlight the active route
- Collapse to icons on mobile (hamburger menu)
- Show the theme toggle at the bottom

#### 2B. UI components
Extract from Dashboard.tsx into individual files. Each component should:
- Accept props (no internal data fetching)
- Use CSS classes from index.css (not inline styles)
- Be fully typed with TypeScript interfaces
- Handle loading, empty, and error states

**Priority components** (used on almost every page):
1. `StatCard` — value, label, optional trend arrow, optional icon
2. `DataTable` — columns config, data array, sortable headers, pagination (10/25/50 rows), optional row click handler
3. `Badge` — text + variant (success/warning/critical/info/neutral)
4. `Modal` — title, children, onClose, optional footer actions
5. `TabBar` — tabs array, active tab, onChange
6. `LoadingState` — skeleton mode (rectangles) for initial load, spinner for refetch
7. `EmptyState` — icon, title, description, optional CTA button

#### 2C. Chart components
Wrap Recharts in domain-specific components:
- `TemperatureChart`: time-series line chart with zone color coding, threshold lines for setpoints, responsive
- `DemandChart`: bar chart for peak demand (kW) with time-of-use shading
- `CostBreakdownChart`: donut chart — energy vs demand vs fixed charges
- `LoadProfileChart`: 24hr area chart showing typical vs actual load
- `ComparisonChart`: multi-line overlay for site comparison metrics

All charts should use the CSS variable colors (`var(--color-primary)`, etc.) and the custom `ChartTooltip` component.

#### 2D. Form components
Build form components for every create/edit workflow. Use controlled inputs with the existing `.field` and `.inline-form` CSS classes. Each form should:
- Validate client-side before submit
- Show inline validation errors
- Disable submit button while loading
- Call the appropriate TanStack Query mutation
- Close the modal and show a success toast on completion

### Phase 3: Page-by-Page Rebuild

Rebuild each page as its own file, using the extracted components and hooks. Delete code from Dashboard.tsx as you extract it. The goal is to reduce Dashboard.tsx to zero lines (delete it entirely when done).

#### Fleet Overview (`/` — the landing page)
This is the VP/GM view. Should show:
- **Summary bar**: total facilities, total alerts (by severity), total equipment, system health %
- **Facility cards grid**: one card per facility showing name, location, zone count, active alerts, last reading timestamp, connection status badge
- Click a facility card → navigate to `/facilities/:id`
- **Add Facility** button (opens modal)
- If only one facility exists, auto-redirect to its detail page

#### Facility Detail (`/facilities/:id`)
Tab-based layout with these sub-routes:
- **Overview** (`/facilities/:id`): summary stats (zones, equipment, alerts, latest bill), mini charts (24hr temp, demand), recent alerts list, quick actions
- **Zones** (`/facilities/:id/zones`): zone cards in a grid layout showing name, type, area, assigned equipment count, current temp (when telemetry exists). Click to expand. Create/edit zone modals.
- **Equipment** (`/facilities/:id/equipment`): data table with name, type, zone assignment, status, last reading. Sortable. Create/delete equipment.
- **Bills** (`/facilities/:id/bills`): data table of utility bills. Upload CSV button. Click a bill → show analysis (demand breakdown, peak events, cost breakdown chart). Run analysis button.
- **Demand** (`/facilities/:id/demand`): deep-dive demand analysis. Load profile chart, peak event timeline, demand charge breakdown, TOU period visualization.
- **Automation** (`/facilities/:id/automation`): three sub-tabs: Sequences (list + create/run), Rules (list + create/edit with enable/disable toggle), Schedules (read-only list).
- **Agents** (`/facilities/:id/agents`): data table of edge agents. Registration form. Status badges (online/offline based on last heartbeat). Agent key display (hidden by default, click to reveal).
- **Integrations** (`/facilities/:id/integrations`): provider cards showing available integrations. Connected integrations list. Setup wizard for new integrations. Credential management. Test connection button. Device discovery.

#### Alerts (`/alerts`)
- Filterable alert feed: by severity (critical/high/medium/low/info), status (active/acknowledged/resolved), facility, date range
- Alert cards with: timestamp, severity badge, facility name, zone (if applicable), message, acknowledge/resolve buttons
- Alert summary stats at top (counts by severity)
- Auto-refresh every 30 seconds

#### Savings Simulator (`/savings`)
- Input form: select facility, set parameters (pre-cool duration, demand target, DR event hours)
- Results display: estimated annual savings, demand charge reduction, energy cost impact
- Scenario comparison: save multiple scenarios as chips, compare side by side
- Charts: before/after load profile, monthly savings projection

#### Site Comparison (`/compare`)
- Multi-select facility picker (checkboxes, 2-5 facilities)
- Comparison grid: side-by-side metrics (sqft, zone count, equipment count, monthly cost, demand, alerts)
- Comparison charts: overlay line charts for cost trends, demand profiles
- Ranking: which facility is most/least efficient

#### Settings (`/settings`)
- **Profile section**: user name, email (read-only), change password form
- **Organization section**: org name, plan tier badge
- **Preferences**: theme toggle (light/dark), temperature unit (°F/°C), notification preferences
- **About**: version, API status health check

### Phase 4: Polish & Production Hardening

#### 4A. Loading & Error States
Every page and component must handle three states:
1. **Loading**: skeleton loaders (not spinners) on initial load. Use CSS `.loading-state` class. Show skeleton rectangles that match the shape of the content they replace.
2. **Error**: inline error message with retry button. Never a blank page. Use `.alert` class with error variant.
3. **Empty**: friendly illustration + descriptive text + CTA. "No equipment yet — add your first piece of equipment to start monitoring." Use `.empty-state` class.

#### 4B. Responsive Design
The CSS already has responsive breakpoints. Make sure:
- Sidebar collapses to bottom nav bar on mobile (<768px)
- Data tables become card lists on mobile
- Charts resize responsively (Recharts `<ResponsiveContainer>`)
- Modals go full-screen on mobile
- Touch targets are at least 44x44px

#### 4C. Toasts / Notifications
Add a lightweight toast system (build it, don't install a library). Toast on:
- Successful create/update/delete actions
- API errors that aren't handled inline
- Background events (agent came online, new alert)

Position: bottom-right. Auto-dismiss after 5s. Stack up to 3.

#### 4D. Keyboard Shortcuts
- `Cmd/Ctrl + K`: quick search (facility, equipment, zone by name)
- `Escape`: close any modal
- `?`: show keyboard shortcut help

#### 4E. URL State
Use URL search params for filter state on list pages (alerts, bills, equipment). This lets users bookmark filtered views and share links.

---

## 4. BACKEND IMPROVEMENTS

The backend is solid but needs these improvements for production:

### 4A. Real-time WebSocket Support
Add a WebSocket endpoint at `/api/v1/ws` for:
- Live telemetry streaming (when polling engine gets new data)
- Real-time alert notifications
- Agent heartbeat status updates

Use FastAPI's built-in WebSocket support. Broadcast to connected clients per org (org-scoped channels).

### 4B. Telemetry Ingestion
The `Telemetry` model exists but there's no ingestion endpoint. Add:
- `POST /api/v1/agents/{agent_id}/telemetry` — bulk telemetry push from edge agents (authenticated via agent key)
- `GET /api/v1/facilities/{id}/telemetry` — query telemetry with time range, metric name, equipment filters
- `GET /api/v1/facilities/{id}/telemetry/latest` — latest reading per equipment+metric (for live dashboard)

Validate against TimescaleDB hypertable. Add continuous aggregates for hourly/daily rollups.

### 4C. Rate Limiting
Add rate limiting middleware:
- Auth endpoints: 5 requests/minute per IP (brute force protection)
- General API: 100 requests/minute per user
- Telemetry ingestion: 1000 requests/minute per agent

Use Redis for rate limit counters.

### 4D. Pagination Consistency
Ensure ALL list endpoints return a consistent paginated response:
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "page_size": 25,
  "pages": 6
}
```
Accept `?page=1&page_size=25&sort_by=created_at&sort_dir=desc` on all list endpoints.

### 4E. Background Tasks
Move long-running operations to Celery tasks:
- Demand analysis (already slow for large bills)
- Bulk bill CSV processing
- Integration device discovery
- Register map imports

Return 202 Accepted with a task ID. Add `GET /api/v1/tasks/{task_id}` to poll status.

### 4F. Logging & Observability
- Structured JSON logging (use `structlog` or Python's `logging` with JSON formatter)
- Request ID middleware (generate UUID per request, include in all log lines)
- Health check should verify DB and Redis connectivity, not just return 200

### 4G. API Versioning
The `/api/v1/` prefix is already correct. Add response headers:
- `X-ColdGrid-Version: 0.3.0`
- `X-Request-Id: <uuid>`

---

## 5. DEPLOYMENT & DEVOPS

### 5A. Docker Production Config
Create `docker-compose.prod.yml`:
- Backend: Gunicorn + Uvicorn workers, `--workers 4`
- Frontend: Nginx serving built static files (not Vite dev server)
- TimescaleDB: connection pooling (PgBouncer sidecar), backup volume
- Redis: persistence enabled (AOF)
- Traefik or Nginx reverse proxy with TLS termination

### 5B. Environment Config
Expand `.env.example` with all configurable values:
```env
# Required
SECRET_KEY=<generate-a-64-char-random-string>
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/coldgrid
REDIS_URL=redis://redis:6379/0

# Optional
OPENEI_API_KEY=
CORS_ORIGINS=https://app.coldgrid.io
ENVIRONMENT=production
DEBUG=false
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
MAX_UPLOAD_SIZE_MB=50
LOG_LEVEL=INFO
SENTRY_DSN=
```

### 5C. CI/CD Pipeline
Create `.github/workflows/ci.yml`:
- **Lint**: `ruff check` (backend), `tsc --noEmit` (frontend)
- **Test**: `pytest` with coverage report, fail if <80%
- **Build**: Docker image build
- **Deploy**: push to container registry on main branch merge

### 5D. README
Create a README.md covering:
- What ColdGrid is (2 sentences)
- Quick start (docker compose up)
- Architecture diagram (mermaid)
- Environment variables table
- API documentation link (/docs)
- Development setup
- Testing instructions

---

## 6. DATA & DEMO

### 6A. Seed Data Script
Create `backend/scripts/seed_demo.py` that populates:
- 1 organization ("ColdGrid Demo")
- 1 admin user (demo@coldgrid.io / DemoPass123)
- 3 facilities (different sizes, locations)
- 5-10 zones per facility (freezer, cooler, dock, machine room)
- 10-20 equipment per facility (compressors, condensers, evaporators, VFDs)
- 6 months of utility bills with realistic cold storage numbers ($15K-45K/month, 200-500 peak kW)
- Demand analyses for each bill
- A few active alerts (1 critical, 2 warnings, some info)
- 2 edge agents per facility (1 online, 1 offline)
- 1 Modbus integration per facility
- Sample automation sequences and rules

This lets anyone spin up the app and immediately see a realistic, populated interface.

### 6B. Realistic Numbers
Cold storage facilities typically:
- 20,000–200,000 sq ft
- Freezer zones: -10°F to 0°F setpoint
- Cooler zones: 34°F to 38°F setpoint
- Dock zones: 45°F to 55°F
- Peak demand: 0.8–2.5 kW per 1,000 sq ft
- Monthly electric: $0.50–$1.50 per sq ft
- Demand charges: 30-60% of total bill
- Compressor types: reciprocating, screw, scroll
- Refrigerants: R-404A, R-507A, R-717 (ammonia), R-744 (CO2)
- Common controllers: Danfoss AK-PC, Emerson E2/EC, Honeywell JADE

Use these numbers in seed data so the UI looks real and credible to industry users.

---

## 7. WORK ORDER & PRIORITIES

Execute in this order:

### Sprint 1 — Foundation (estimated: 2-3 days)
1. Install TanStack Query
2. Create folder structure
3. Extract contexts (Auth, Theme, Site)
4. Build all TanStack Query hooks
5. Set up React Router with proper routes
6. Build AppLayout + Sidebar + SiteSelector
7. Build core UI components (StatCard, Badge, DataTable, Modal, TabBar, LoadingState, EmptyState)

### Sprint 2 — Pages (estimated: 3-4 days)
8. Fleet Overview page
9. Facility Detail shell + Overview tab
10. Zones page
11. Equipment page
12. Bills page + analysis view
13. Demand Analysis page
14. Alerts page
15. Automation page (sequences + rules + schedules)
16. Agents page
17. Integrations page
18. Savings Simulator
19. Site Comparison
20. Settings page
21. Delete Dashboard.tsx

### Sprint 3 — Backend Hardening (estimated: 2 days)
22. Telemetry ingestion + query endpoints
23. WebSocket support
24. Pagination consistency across all list endpoints
25. Rate limiting
26. Background task infrastructure (Celery)
27. Structured logging + request ID middleware

### Sprint 4 — Polish (estimated: 2-3 days)
28. Toast notification system
29. Skeleton loaders on every page
30. Empty states with CTAs
31. Error boundaries and error states
32. Responsive mobile layout
33. Keyboard shortcuts
34. URL state for filters
35. Seed data script
36. README

### Sprint 5 — Ship (estimated: 1-2 days)
37. Docker production config
38. CI/CD pipeline
39. Environment config hardening
40. Security audit (headers, CORS, rate limits)
41. Performance audit (bundle size, lazy loading routes)

---

## 8. CODE STANDARDS

### TypeScript
- Strict mode (`"strict": true` in tsconfig)
- No `any` types — use proper interfaces
- Export interfaces from `lib/types.ts`
- Use `const` assertions for constant objects
- Prefer `interface` over `type` for object shapes

### React Patterns
- Functional components only
- Custom hooks for all data fetching (TanStack Query)
- No prop drilling deeper than 2 levels — use context
- `React.memo` for expensive list item components
- Error boundaries around every page
- Lazy load routes: `const FleetOverview = React.lazy(() => import('./pages/FleetOverview'))`

### CSS
- Use the existing CSS classes in `index.css` — do NOT create new CSS files per component
- Use CSS variables for colors: `var(--color-primary)`, `var(--color-text)`, etc.
- If a new class is needed, add it to `index.css` following the existing naming convention
- No inline styles except for truly dynamic values (positioning, calculated widths)
- Use `className` strings, not CSS modules or styled-components

### API
- All API calls go through `lib/api.ts` — never call `fetch` directly in components
- All data access goes through TanStack Query hooks — never use `useEffect` for data fetching
- Mutations always invalidate the relevant query cache
- Optimistic updates for toggle/status changes (alert acknowledge, rule enable/disable)

### Git
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- One logical change per commit
- No commits with failing TypeScript or tests

---

## 9. CRITICAL CONSTRAINTS

1. **Do NOT install Tailwind, MUI, Chakra, or any CSS framework.** The design system in `index.css` is complete and should be used as-is. Add new classes to `index.css` if needed.
2. **Do NOT change the backend database schema** without creating a new Alembic migration.
3. **Do NOT break the existing 91 backend tests.** Run `pytest` after every backend change.
4. **Do NOT change the API response shapes** without updating both the frontend types and backend schemas.
5. **Keep the `api.ts` file** — extend it, don't replace it.
6. **Preserve the CSS variable theming** — all new components must work in both light and dark mode.
7. **Every list must handle: loading, empty, error, and populated states.**
8. **Every form must validate before submit and show inline errors.**
9. **Every destructive action (delete) must have a confirmation dialog.**
10. **All data must be org-scoped** — never show data from another organization.

---

## 10. CURRENT KNOWN ISSUES TO FIX

1. `Login.tsx` uses inline styles instead of CSS classes — refactor to use `.card`, `.field`, `.btn-primary` classes
2. `App.tsx` stores token in `sessionStorage` — move to `AuthContext` and handle refresh token rotation
3. No 404 page exists
4. No error boundaries exist
5. Frontend has no loading skeletons (just a basic spinner)
6. The `api.ts` 401 handler redirects via `window.location` — should use React Router navigation
7. No toast/notification system for action feedback
8. Browser back/forward doesn't work properly (no real routes)
9. The facility selector in the sidebar doesn't persist across page refreshes (should use URL params or localStorage)
10. Charts don't use responsive containers consistently

---

This document is your complete guide. Work through it systematically, sprint by sprint. After each sprint, run `tsc --noEmit` and `pytest` to verify nothing is broken. The end result should be an application that looks and feels like enterprise software that cold storage professionals trust with their operations.
