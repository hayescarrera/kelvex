"""
Unit tests for the cache service.

Tests the no-Redis fallback paths and all pure utility functions.
Redis-specific paths (actual set/get) are not tested here — they require
a live Redis and would duplicate integration-level verification.
"""
import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.services.cache import (
    _UUIDEncoder,
    _calc_hit_rate,
    make_cache_key,
    cache_get,
    cache_set,
    cache_invalidate,
    cache_health,
    cached,
    CACHE_PREFIX_FLEET,
    CACHE_PREFIX_FACILITY,
    CACHE_PREFIX_ALERTS,
    CACHE_PREFIX_COMPLIANCE,
    CACHE_PREFIX_ENERGY,
    CACHE_PREFIX_COMPRESSORS,
)


# ── Pure utility functions ────────────────────────────────


class TestMakeCacheKey:
    def test_simple_prefix_only(self):
        key = make_cache_key("fleet")
        assert key == "fleet"

    def test_prefix_with_args(self):
        uid = uuid.uuid4()
        key = make_cache_key("facility", uid, "overview")
        assert key == f"facility:{uid}:overview"

    def test_none_arg_becomes_underscore(self):
        key = make_cache_key("energy", None, "2025-01")
        assert "_" in key
        assert "2025-01" in key

    def test_kwargs_sorted_alphabetically(self):
        key1 = make_cache_key("alerts", org="abc", facility="xyz")
        key2 = make_cache_key("alerts", facility="xyz", org="abc")
        assert key1 == key2

    def test_kwargs_none_values_excluded(self):
        key = make_cache_key("alerts", org="abc", facility=None)
        assert "facility" not in key
        assert "org=abc" in key

    def test_long_key_is_hashed(self):
        long_args = ["x" * 50 for _ in range(5)]
        key = make_cache_key("prefix", *long_args)
        assert key.startswith("prefix:")
        assert len(key) < 200

    def test_key_not_hashed_when_short(self):
        key = make_cache_key("fleet", "abc")
        assert key == "fleet:abc"

    def test_uuid_stringified(self):
        uid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        key = make_cache_key("facility", uid)
        assert "12345678-1234-5678-1234-567812345678" in key


class TestCalcHitRate:
    def test_zero_requests(self):
        assert _calc_hit_rate({"keyspace_hits": 0, "keyspace_misses": 0}) == "N/A"

    def test_all_hits(self):
        result = _calc_hit_rate({"keyspace_hits": 100, "keyspace_misses": 0})
        assert result == "100.0%"

    def test_all_misses(self):
        result = _calc_hit_rate({"keyspace_hits": 0, "keyspace_misses": 100})
        assert result == "0.0%"

    def test_mixed(self):
        result = _calc_hit_rate({"keyspace_hits": 75, "keyspace_misses": 25})
        assert result == "75.0%"

    def test_missing_keys_treated_as_zero(self):
        result = _calc_hit_rate({})
        assert result == "N/A"


class TestUUIDEncoder:
    def test_uuid_serialized_as_string(self):
        uid = uuid.uuid4()
        result = json.dumps({"id": uid}, cls=_UUIDEncoder)
        data = json.loads(result)
        assert data["id"] == str(uid)

    def test_non_uuid_passthrough(self):
        result = json.dumps({"name": "test", "count": 5}, cls=_UUIDEncoder)
        data = json.loads(result)
        assert data["name"] == "test"
        assert data["count"] == 5

    def test_unhandled_type_raises(self):
        with pytest.raises(TypeError):
            json.dumps({"val": Decimal("3.14")}, cls=_UUIDEncoder)


# ── No-Redis fallback paths ───────────────────────────────


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    """Patch get_redis to simulate Redis being unavailable."""
    import app.services.cache as cache_module
    monkeypatch.setattr(cache_module, "_redis", None)

    async def _no_redis():
        return None

    monkeypatch.setattr(cache_module, "get_redis", _no_redis)


@pytest.mark.asyncio
class TestCacheGetNoRedis:
    async def test_returns_none_on_miss(self):
        result = await cache_get("some:key")
        assert result is None

    async def test_returns_none_for_any_key(self):
        assert await cache_get("fleet:123") is None
        assert await cache_get("") is None


@pytest.mark.asyncio
class TestCacheSetNoRedis:
    async def test_returns_false(self):
        result = await cache_set("fleet:123", {"data": True}, ttl_seconds=60)
        assert result is False

    async def test_does_not_raise_for_any_value(self):
        await cache_set("key", None)
        await cache_set("key", [1, 2, 3])
        await cache_set("key", {"nested": {"deep": True}})


@pytest.mark.asyncio
class TestCacheInvalidateNoRedis:
    async def test_returns_zero(self):
        result = await cache_invalidate("fleet:*")
        assert result == 0


@pytest.mark.asyncio
class TestCacheHealthNoRedis:
    async def test_returns_unavailable(self):
        result = await cache_health()
        assert result == {"status": "unavailable"}


@pytest.mark.asyncio
class TestCachedDecoratorNoRedis:
    async def test_always_calls_through(self):
        call_count = 0

        @cached("test_prefix", ttl_seconds=60)
        async def expensive_fn(x: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"value": x * 2}

        result1 = await expensive_fn(5)
        result2 = await expensive_fn(5)

        assert result1 == {"value": 10}
        assert result2 == {"value": 10}
        assert call_count == 2  # no Redis = no caching, called every time

    async def test_invalidate_helper_does_not_raise(self):
        @cached("test_inv", ttl_seconds=60)
        async def fn() -> dict:
            return {}

        await fn.invalidate()
        await fn.invalidate_all()

    async def test_different_args_produce_different_calls(self):
        results = []

        @cached("test_args", ttl_seconds=60)
        async def fn(x: int) -> int:
            results.append(x)
            return x

        await fn(1)
        await fn(2)
        await fn(1)

        assert results == [1, 2, 1]


# ── Constants ─────────────────────────────────────────────


class TestCachePrefixConstants:
    def test_prefixes_are_strings(self):
        assert isinstance(CACHE_PREFIX_FLEET, str)
        assert isinstance(CACHE_PREFIX_FACILITY, str)
        assert isinstance(CACHE_PREFIX_ALERTS, str)
        assert isinstance(CACHE_PREFIX_COMPLIANCE, str)
        assert isinstance(CACHE_PREFIX_ENERGY, str)
        assert isinstance(CACHE_PREFIX_COMPRESSORS, str)

    def test_prefixes_are_unique(self):
        prefixes = [
            CACHE_PREFIX_FLEET,
            CACHE_PREFIX_FACILITY,
            CACHE_PREFIX_ALERTS,
            CACHE_PREFIX_COMPLIANCE,
            CACHE_PREFIX_ENERGY,
            CACHE_PREFIX_COMPRESSORS,
        ]
        assert len(set(prefixes)) == len(prefixes)
