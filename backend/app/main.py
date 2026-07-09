import logging
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import async_session
from app.core.rate_limit import RateLimiter

settings = get_settings()
logger = logging.getLogger("kelvex")
auth_rate_limiter = RateLimiter(settings.REDIS_URL) if settings.REDIS_URL else None
api_rate_limiter = RateLimiter(settings.REDIS_URL) if settings.REDIS_URL else None
health_redis = Redis.from_url(settings.REDIS_URL, decode_responses=True) if settings.REDIS_URL else None

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[FastApiIntegration()],
    )


_engine_status: dict[str, str] = {}  # engine_name → "running" | "failed" | "skipped"


async def _start_all_engines():
    """Start every background engine. Runs only on the elected leader worker
    so multi-worker deployments don't duplicate polls, digests, and rules."""
    import logging
    logger = logging.getLogger("kelvex")

    # Start polling engine for cloud integrations
    try:
        from app.core.database import async_session
        from app.services.polling_engine import start_polling_engine
        await start_polling_engine(async_session)
        _engine_status["polling"] = "running"
        logger.info("Polling engine started")
    except Exception as e:
        _engine_status["polling"] = "failed"
        logger.warning(f"Polling engine startup skipped: {e}")

    # Start schedule engine
    try:
        from app.core.database import async_session
        from app.services.schedule_engine import start_schedule_engine
        await start_schedule_engine(async_session)
        _engine_status["schedule"] = "running"
        logger.info("Schedule engine started")
    except Exception as e:
        _engine_status["schedule"] = "failed"
        logger.warning(f"Schedule engine startup skipped: {e}")

    # Start automation rule engine
    try:
        from app.core.database import async_session
        from app.services.rule_engine import start_rule_engine
        await start_rule_engine(async_session)
        _engine_status["rule"] = "running"
        logger.info("Rule engine started")
    except Exception as e:
        _engine_status["rule"] = "failed"
        logger.warning(f"Rule engine startup skipped: {e}")

    # Start email digest scheduler
    try:
        from app.core.database import async_session
        from app.services.digest_service import start_digest_scheduler
        await start_digest_scheduler(async_session)
        _engine_status["digest"] = "running"
        logger.info("Digest scheduler started")
    except Exception as e:
        _engine_status["digest"] = "failed"
        logger.warning(f"Digest scheduler startup skipped: {e}")

    # Start compressor health engine
    try:
        from app.core.database import async_session
        from app.services.compressor_health import start_compressor_health_engine
        await start_compressor_health_engine(async_session)
        _engine_status["compressor_health"] = "running"
        logger.info("Compressor health engine started")
    except Exception as e:
        _engine_status["compressor_health"] = "failed"
        logger.warning(f"Compressor health engine startup skipped: {e}")

    # Start agent connectivity monitor
    try:
        from app.core.database import async_session
        from app.services.agent_monitor import start_agent_monitor
        await start_agent_monitor(async_session)
        _engine_status["agent_monitor"] = "running"
        logger.info("Agent monitor started")
    except Exception as e:
        _engine_status["agent_monitor"] = "failed"
        logger.warning(f"Agent monitor startup skipped: {e}")

    try:
        from app.services.energy_analytics import start_energy_analytics_engine
        await start_energy_analytics_engine()
        _engine_status["energy_analytics"] = "running"
        logger.info("Energy analytics engine started")
    except Exception as e:
        _engine_status["energy_analytics"] = "failed"
        logger.warning(f"Energy analytics engine startup skipped: {e}")

    # Seed register maps and device profiles on first run
    try:
        from app.core.database import async_session
        from app.integrations.register_map_seeds import seed_register_maps, seed_device_profiles
        async with async_session() as db:
            await seed_register_maps(db)
            await seed_device_profiles(db)
            logger.info("Register maps and device profiles seeded")
    except Exception as e:
        logger.warning(f"Register map seeding skipped: {e}")

    # Seed demo data if SEED_DEMO=true
    import os
    if os.getenv("SEED_DEMO", "").lower() in ("true", "1", "yes"):
        try:
            from app.core.database import async_session
            from app.seeds.demo_data import seed_demo_data
            async with async_session() as db:
                await seed_demo_data(db)
        except Exception as e:
            logger.warning(f"Demo data seeding skipped: {e}")


_engine_leader = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle — elect an engine leader, run engines there."""
    global _engine_leader
    from app.core.leader import EngineLeader

    if settings.REDIS_URL:
        _engine_leader = EngineLeader(settings.REDIS_URL, on_elected=_start_all_engines)
        await _engine_leader.start()
    else:
        await _start_all_engines()

    yield

    # Shutdown
    if _engine_leader:
        try:
            await _engine_leader.stop()
        except Exception:
            pass
    try:
        from app.services.polling_engine import stop_polling_engine
        await stop_polling_engine()
    except Exception:
        pass
    try:
        from app.services.schedule_engine import stop_schedule_engine
        await stop_schedule_engine()
    except Exception:
        pass
    try:
        from app.services.rule_engine import stop_rule_engine
        await stop_rule_engine()
    except Exception:
        pass
    try:
        from app.services.compressor_health import stop_compressor_health_engine
        await stop_compressor_health_engine()
    except Exception:
        pass
    try:
        from app.services.agent_monitor import stop_agent_monitor
        await stop_agent_monitor()
    except Exception:
        pass
    try:
        from app.services.energy_analytics import stop_energy_analytics_engine
        await stop_energy_analytics_engine()
    except Exception:
        pass
    if auth_rate_limiter:
        try:
            await auth_rate_limiter.close()
        except Exception:
            pass
    if api_rate_limiter:
        try:
            await api_rate_limiter.close()
        except Exception:
            pass
    if health_redis:
        try:
            await health_redis.aclose()
        except Exception:
            pass


app = FastAPI(
    title="Kelvex API",
    description="Operational intelligence platform for cold storage facilities — monitoring, controls, automation, and demand optimization",
    version="0.3.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Startup warning for insecure secret key ─────────────
if settings.SECRET_KEY == "dev-secret-key-change-in-production":
    import warnings
    warnings.warn(
        "Kelvex is running with the default SECRET_KEY. "
        "Set a strong SECRET_KEY environment variable before deploying to production.",
        UserWarning,
        stacklevel=1,
    )


# ── Global exception handlers ───────────────────────────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Consistent JSON error format for all HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Consistent JSON error format for validation errors."""
    errors = []
    for err in exc.errors():
        errors.append({
            "field": " → ".join(str(loc) for loc in err["loc"]),
            "message": err["msg"],
            "type": err["type"],
        })
    return JSONResponse(
        status_code=422,
        content={
            "error": True,
            "status_code": 422,
            "detail": "Validation error",
            "errors": errors,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — never leak stack traces."""
    logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "status_code": 500,
            "detail": "Internal server error",
        },
    )


# ── Request logging middleware ───────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 1)
    if request.url.path not in ("/health", "/docs", "/redoc", "/openapi.json"):
        logger.info(
            f"{request.method} {request.url.path} → {response.status_code} ({duration_ms}ms)"
        )
    return response


_AUTH_RATE_LIMITED_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/password-reset/request",
    "/api/v1/auth/password-reset/confirm",
}


@app.middleware("http")
async def auth_rate_limit(request: Request, call_next):
    """Apply brute-force protection to login/register only."""
    if request.url.path in _AUTH_RATE_LIMITED_PATHS and auth_rate_limiter:
        client_ip = request.client.host if request.client else "unknown"
        bucket_key = f"rl:auth:{client_ip}:{request.url.path}"
        result = await auth_rate_limiter.check(
            bucket_key=bucket_key,
            limit=settings.AUTH_RATE_LIMIT_PER_MINUTE,
            window_seconds=60,
        )
        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": True,
                    "status_code": 429,
                    "detail": "Rate limit exceeded. Try again later.",
                },
                headers={
                    "Retry-After": str(result.retry_after_seconds),
                    "X-RateLimit-Limit": str(settings.AUTH_RATE_LIMIT_PER_MINUTE),
                    "X-RateLimit-Remaining": str(result.remaining),
                },
            )
    return await call_next(request)


def _extract_rate_limit_subject(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "", 1).strip()
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except JWTError:
            pass
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


def _agent_key_from_request(request: Request) -> str | None:
    """Return the agent key for agent-facing routes.

    Legacy routes carry it in the path (/api/v1/agents/{cg_...}/...);
    v2 routes (/api/v1/agent/...) carry it as a Bearer token.
    """
    path = request.url.path
    prefix = "/api/v1/agents/"
    if path.startswith(prefix):
        # Cloud-facing agent management lives under /facilities/...; agent-
        # facing routes are exactly /agents/{key}/<action>, keys start "cg_".
        key = path[len(prefix):].split("/", 1)[0]
        return key if key.startswith("cg_") else None
    if path.startswith("/api/v1/agent/"):
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer cg_"):
            return auth[7:].strip()
    return None


@app.middleware("http")
async def api_rate_limit(request: Request, call_next):
    """Apply general API rate limit to authenticated traffic."""
    if request.url.path.startswith("/api/v1/") and not request.url.path.startswith("/api/v1/auth/") and api_rate_limiter:
        agent_key = _agent_key_from_request(request)
        if agent_key:
            # Per-agent bucket, higher ceiling: outage back-fills are bursty
            # and several agents can share one site IP.
            subject = f"agent:{agent_key}"
            limit = settings.AGENT_RATE_LIMIT_PER_MINUTE
        else:
            subject = _extract_rate_limit_subject(request)
            limit = settings.API_RATE_LIMIT_PER_MINUTE
        bucket_key = f"rl:api:{subject}"
        result = await api_rate_limiter.check(
            bucket_key=bucket_key,
            limit=limit,
            window_seconds=60,
        )
        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": True,
                    "status_code": 429,
                    "detail": "API rate limit exceeded. Try again later.",
                },
                headers={
                    "Retry-After": str(result.retry_after_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": str(result.remaining),
                },
            )
    return await call_next(request)


@app.middleware("http")
async def request_context_headers(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Kelvex-Version"] = app.version
    return response


# CORS — configurable via CORS_ORIGINS env var
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=settings.ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Include API routes
app.include_router(api_router)


@app.get("/health")
async def health_check():
    db_ok = True
    redis_ok = True

    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    if health_redis:
        try:
            await health_redis.ping()
        except Exception:
            redis_ok = False
    else:
        redis_ok = False

    engines_failed = [name for name, state in _engine_status.items() if state == "failed"]
    is_healthy = db_ok  # Redis and engines are optional
    status_text = "healthy" if is_healthy else "degraded"
    status_code = 200 if is_healthy or not settings.HEALTHCHECK_STRICT else 503

    if _engine_leader and not _engine_leader.is_leader:
        engines_view = "standby (engines run on the leader worker)"
    else:
        engines_view = _engine_status if _engine_status else "starting"

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status_text,
            "service": "kelvex-api",
            "checks": {
                "database": "healthy" if db_ok else "unhealthy",
                "redis": "healthy" if redis_ok else "unhealthy",
                "engines": engines_view,
            },
            **({"engines_failed": engines_failed} if engines_failed else {}),
        },
    )
