# ColdGrid

Demand management platform for commercial cold storage facilities. Monitor refrigeration systems, analyze utility bills, optimize peak demand, and automate control sequences across your portfolio.

## Architecture

**Backend:** FastAPI + SQLAlchemy (async) + TimescaleDB + Redis  
**Frontend:** React 18 + TypeScript + Vite + TanStack Query + Recharts  
**Infrastructure:** Docker Compose, Nginx reverse proxy, Alembic migrations

## Quick Start (Development)

```bash
# 1. Copy environment config
cp .env.example .env

# 2. Start all services (hot-reload enabled)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# 3. Open the app
#    Frontend: http://localhost:5173
#    API docs: http://localhost:8000/docs
#    Health:   http://localhost:8000/health
```

The dev stack runs Vite dev server with hot reload (port 5173) and Uvicorn with `--reload` (port 8000). Database migrations run automatically on backend startup.

## Production Deployment

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env — set strong SECRET_KEY, CREDENTIAL_ENCRYPTION_KEY, DB password, CORS_ORIGINS

# 2. Build and start
docker compose up --build -d

# 3. Frontend is served via Nginx on port 80
#    API is on port 8000 (proxied through Nginx at /api)
```

### Required Environment Variables (Production)

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing key. Generate with `openssl rand -hex 32` |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key for encrypting integration credentials. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `POSTGRES_PASSWORD` | Database password (change from default) |
| `CORS_ORIGINS` | Comma-separated allowed origins, e.g. `https://app.coldgrid.io` |
| `ENVIRONMENT` | Set to `production` |

### Optional Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | Built from PG vars | Full async connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection for rate limiting and caching |
| `OPENEI_API_KEY` | — | OpenEI utility rate lookup (free key) |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `5` | Login endpoint rate limit |
| `API_RATE_LIMIT_PER_MINUTE` | `100` | General API rate limit |
| `SENTRY_DSN` | — | Sentry error tracking |
| `HEALTHCHECK_STRICT` | `false` | Fail health check if Redis is down |

### Database Migrations

Migrations run automatically via `alembic upgrade head` in the backend entrypoint (`start.sh`). To create a new migration after model changes:

```bash
docker compose exec backend alembic revision --autogenerate -m "description of change"
docker compose exec backend alembic upgrade head
```

### Secrets Management

In production, avoid storing secrets in `.env` files on disk. Use your platform's secrets manager:

- **AWS:** Secrets Manager or SSM Parameter Store
- **GCP:** Secret Manager
- **Azure:** Key Vault
- **Kubernetes:** External Secrets Operator

Inject secrets as environment variables at runtime.

## Project Structure

```
coldgrid/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # FastAPI route handlers
│   │   ├── core/            # Config, database, security, rate limiting
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic request/response schemas
│   │   ├── services/        # Background engines (schedule, rule, polling)
│   │   └── integrations/    # Equipment protocol adapters (Modbus, BACnet, etc.)
│   ├── migrations/          # Alembic database migrations
│   ├── tests/               # pytest test suite
│   └── start.sh             # Entrypoint: run migrations + start Uvicorn
├── frontend/
│   ├── src/
│   │   ├── components/      # Shared UI components
│   │   ├── contexts/        # React contexts (auth, theme, site)
│   │   ├── hooks/           # TanStack Query hooks for all API resources
│   │   ├── lib/             # API client, utilities
│   │   └── pages/           # Page components (fleet, facility, automation, etc.)
│   ├── Dockerfile           # Multi-stage production build (Vite → Nginx)
│   ├── Dockerfile.dev       # Development with hot reload
│   └── nginx.conf           # Nginx config for SPA + API proxy
├── nginx/                   # Standalone Nginx config
├── docker-compose.yml       # Production stack
├── docker-compose.dev.yml   # Development overrides (hot reload)
└── .env.example             # Environment variable template
```

## Running Tests

```bash
# Backend (with coverage)
cd backend
pytest

# Frontend (type check)
cd frontend
npx tsc --noEmit
```

The backend test suite runs with `pytest-cov` and requires 40% minimum coverage. Current coverage is ~49% across 97 tests.

## API Documentation

Interactive API docs are available at `/docs` (Swagger UI) or `/redoc` when the backend is running. All endpoints require JWT authentication except `/auth/register`, `/auth/login`, and `/health`.

## Key Features

- **Fleet Overview** — Portfolio-wide view of all facilities with real-time status
- **Facility Management** — Full CRUD for facilities, zones, equipment, and utility bills
- **Demand Analysis** — Peak demand trending from utility bill data with cost breakdown
- **Control Sequences** — Define and execute multi-step refrigeration control operations
- **Automation Rules** — Condition-based triggers (temperature, demand, price) with automatic actions
- **Schedules** — Cron, daily, weekly, and one-time scheduling for control sequences
- **Integration Adapters** — Protocol support for Modbus TCP, BACnet/IP, and vendor APIs (JCI, Honeywell, Emerson, Danfoss, Schneider)
- **Savings Simulator** — Estimate demand charge savings per control strategy
- **Alerts** — Severity-based alert system with acknowledge/resolve workflow
- **Edge Agents** — Command queue architecture for dispatching operations to on-site controllers
