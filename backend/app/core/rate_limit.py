import asyncio
import time
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int
    remaining: int


class RateLimiter:
    """
    Redis-backed rate limiter with in-memory fallback.
    """

    # After a Redis failure, retry it this often instead of degrading to the
    # per-process memory store forever (memory limits are per-worker, so a
    # sticky fallback quietly multiplies the effective limit by worker count).
    REDIS_RETRY_SECONDS = 30

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis: Redis | None = None
        self._redis_retry_at: float = 0.0
        self._memory_store: dict[str, tuple[int, float]] = {}
        self._memory_lock = asyncio.Lock()

    async def _get_redis(self) -> Redis | None:
        if self._redis is not None:
            return self._redis
        if time.time() < self._redis_retry_at:
            return None
        try:
            self._redis = Redis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
        except Exception:
            self._redis = None
            self._redis_retry_at = time.time() + self.REDIS_RETRY_SECONDS
        return self._redis

    async def check(self, bucket_key: str, limit: int, window_seconds: int) -> RateLimitResult:
        redis = await self._get_redis()
        if redis is None:
            return await self._check_memory(bucket_key, limit, window_seconds)
        try:
            current_raw = await redis.incr(bucket_key)
            current = int(current_raw)
            if current == 1:
                await redis.expire(bucket_key, window_seconds)
            ttl = await redis.ttl(bucket_key)
            retry_after = max(int(ttl), 1)
            allowed = current <= limit
            remaining = max(limit - current, 0)
            return RateLimitResult(
                allowed=allowed,
                retry_after_seconds=retry_after,
                remaining=remaining,
            )
        except Exception:
            self._redis = None
            self._redis_retry_at = time.time() + self.REDIS_RETRY_SECONDS
            return await self._check_memory(bucket_key, limit, window_seconds)

    async def _check_memory(
        self, bucket_key: str, limit: int, window_seconds: int
    ) -> RateLimitResult:
        now = time.time()
        async with self._memory_lock:
            count, expires_at = self._memory_store.get(bucket_key, (0, now + window_seconds))
            if now >= expires_at:
                count = 0
                expires_at = now + window_seconds

            count += 1
            self._memory_store[bucket_key] = (count, expires_at)

            retry_after = max(int(expires_at - now), 1)
            allowed = count <= limit
            remaining = max(limit - count, 0)
            return RateLimitResult(
                allowed=allowed,
                retry_after_seconds=retry_after,
                remaining=remaining,
            )

    async def close(self):
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

