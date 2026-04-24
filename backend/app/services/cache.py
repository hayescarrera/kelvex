"""
Redis caching layer for ColdGrid dashboard queries.

Provides:
  - `cache_get(key)` / `cache_set(key, value, ttl)` — basic KV ops
  - `@cached(prefix, ttl)` — decorator for async route handlers
  - `cache_invalidate(pattern)` — pattern-based invalidation
  - Health check and stats

Configuration via environment:
  REDIS_URL — defaults to redis://localhost:6379/0

Falls back gracefully if Redis is unavailable — queries run uncached.
"""

import json
import hashlib
import functools
import logging
from datetime import timedelta
from typing import Any, Callable
from uuid import UUID

logger = logging.getLogger(__name__)

# ── Redis Client ─────────────────────────────────

_redis = None


class _UUIDEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)


async def get_redis():
    """Lazy-initialize Redis connection."""
    global _redis
    if _redis is not None:
        return _redis

    try:
        import os
        import redis.asyncio as aioredis

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis = aioredis.from_url(url, decode_responses=True, socket_timeout=2)
        # Test connection
        await _redis.ping()
        logger.info(f"Redis connected: {url}")
        return _redis
    except Exception as e:
        logger.warning(f"Redis unavailable, caching disabled: {e}")
        _redis = None
        return None


# ── Core Operations ──────────────────────────────

async def cache_get(key: str) -> Any | None:
    """Get a value from cache. Returns None on miss or Redis unavailable."""
    r = await get_redis()
    if not r:
        return None
    try:
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.debug(f"Cache get error for {key}: {e}")
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """Set a value in cache with TTL. Returns True on success."""
    r = await get_redis()
    if not r:
        return False
    try:
        raw = json.dumps(value, cls=_UUIDEncoder)
        await r.setex(key, ttl_seconds, raw)
        return True
    except Exception as e:
        logger.debug(f"Cache set error for {key}: {e}")
        return False


async def cache_invalidate(pattern: str) -> int:
    """Invalidate all keys matching a pattern. Returns count deleted."""
    r = await get_redis()
    if not r:
        return 0
    try:
        keys = []
        async for key in r.scan_iter(match=pattern, count=100):
            keys.append(key)
        if keys:
            return await r.delete(*keys)
        return 0
    except Exception as e:
        logger.debug(f"Cache invalidate error for {pattern}: {e}")
        return 0


async def cache_health() -> dict:
    """Health check and basic stats."""
    r = await get_redis()
    if not r:
        return {"status": "unavailable"}
    try:
        info = await r.info("memory", "keyspace", "stats")
        return {
            "status": "connected",
            "used_memory_human": info.get("used_memory_human", "?"),
            "connected_clients": info.get("connected_clients", 0),
            "total_keys": sum(
                db.get("keys", 0) for db in info.values()
                if isinstance(db, dict) and "keys" in db
            ),
            "hit_rate": _calc_hit_rate(info),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _calc_hit_rate(info: dict) -> str:
    hits = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    total = hits + misses
    if total == 0:
        return "N/A"
    return f"{hits / total * 100:.1f}%"


# ── Cache Key Builder ────────────────────────────

def make_cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:
    """Build a deterministic cache key from prefix + arguments."""
    parts = [prefix]
    for a in args:
        parts.append(str(a) if a is not None else "_")
    for k in sorted(kwargs.keys()):
        v = kwargs[k]
        if v is not None:
            parts.append(f"{k}={v}")
    raw = ":".join(parts)
    # Hash if too long
    if len(raw) > 200:
        h = hashlib.md5(raw.encode()).hexdigest()[:12]
        return f"{prefix}:{h}"
    return raw


# ── Decorator ────────────────────────────────────

def cached(prefix: str, ttl_seconds: int = 300):
    """
    Decorator for caching async function results.

    Usage:
        @cached("fleet_overview", ttl_seconds=60)
        async def get_fleet_overview(org_id: UUID):
            ...

    The cache key is built from `prefix` + all function arguments.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = make_cache_key(prefix, *args, **kwargs)

            # Try cache
            hit = await cache_get(key)
            if hit is not None:
                return hit

            # Call function
            result = await func(*args, **kwargs)

            # Store in cache
            await cache_set(key, result, ttl_seconds)
            return result

        # Expose invalidation helper
        wrapper.invalidate = lambda *args, **kwargs: cache_invalidate(
            make_cache_key(prefix, *args, **kwargs)
        )
        wrapper.invalidate_all = lambda: cache_invalidate(f"{prefix}:*")

        return wrapper
    return decorator


# ── Predefined Cache Prefixes ────────────────────

# These are used across the app for consistent key namespacing:
#
# CACHE_PREFIX_FLEET = "fleet"             — fleet overview stats
# CACHE_PREFIX_FACILITY = "facility"       — facility detail
# CACHE_PREFIX_ALERTS = "alerts_summary"   — cross-facility alert counts
# CACHE_PREFIX_COMPLIANCE = "compliance"   — compliance dashboard
# CACHE_PREFIX_ENERGY = "energy"           — energy optimization data
# CACHE_PREFIX_COMPRESSORS = "compressors" — compressor fleet stats
#
# Invalidation pattern: cache_invalidate("fleet:*") clears all fleet caches

CACHE_PREFIX_FLEET = "fleet"
CACHE_PREFIX_FACILITY = "facility"
CACHE_PREFIX_ALERTS = "alerts_summary"
CACHE_PREFIX_COMPLIANCE = "compliance"
CACHE_PREFIX_ENERGY = "energy"
CACHE_PREFIX_COMPRESSORS = "compressors"
