import pytest

from app.core.rate_limit import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_memory_fallback_blocks_after_limit():
    limiter = RateLimiter("redis://invalid:6379/0")
    limiter._use_memory_fallback = True

    first = await limiter.check("rl:test:1", limit=2, window_seconds=60)
    second = await limiter.check("rl:test:1", limit=2, window_seconds=60)
    third = await limiter.check("rl:test:1", limit=2, window_seconds=60)

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds >= 1


@pytest.mark.asyncio
async def test_rate_limiter_memory_fallback_separate_buckets():
    limiter = RateLimiter("redis://invalid:6379/0")
    limiter._use_memory_fallback = True

    a = await limiter.check("rl:test:a", limit=1, window_seconds=60)
    b = await limiter.check("rl:test:b", limit=1, window_seconds=60)

    assert a.allowed is True
    assert b.allowed is True
