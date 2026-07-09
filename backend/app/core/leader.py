"""
Leader election for in-process background engines.

Production runs multiple gunicorn workers, and each worker executes the
FastAPI lifespan. Without coordination, every worker starts its own copy of
the polling/schedule/rule/digest/health/monitor engines — duplicate emails,
duplicate rule firings, duplicate polls.

One worker holds a Redis lock (SET NX with TTL) and runs the engines; the
others stand by. The leader renews the lock on a heartbeat; standbys retry
acquisition so a new leader takes over within ~LOCK_TTL if the current one
dies. If Redis is unreachable, we assume a single-process deployment (dev)
and run the engines — duplicated engines beat no engines.
"""

import asyncio
import logging
import os
import socket
import uuid

from redis.asyncio import Redis

logger = logging.getLogger("kelvex.leader")

LOCK_KEY = "kelvex:engine-leader"
LOCK_TTL_SECONDS = 60
RENEW_INTERVAL_SECONDS = 20

# Lua: release/renew only if we still own the lock
_RENEW_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""
_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class EngineLeader:
    """Tries to become the engine leader; invokes callbacks on transitions.

    Usage:
        leader = EngineLeader(redis_url, on_elected=start_engines)
        await leader.start()   # returns immediately; election runs in background
        ...
        await leader.stop()
    """

    def __init__(self, redis_url: str, on_elected):
        self._redis_url = redis_url
        self._on_elected = on_elected
        self._instance_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._redis: Redis | None = None
        self._task: asyncio.Task | None = None
        self.is_leader = False

    async def start(self) -> None:
        try:
            self._redis = Redis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
        except Exception as e:
            logger.warning(
                "Redis unavailable for leader election (%s) — assuming single "
                "process and starting engines locally.", e,
            )
            self._redis = None
            await self._become_leader()
            return
        self._task = asyncio.create_task(self._election_loop())

    async def _become_leader(self) -> None:
        self.is_leader = True
        logger.info("Elected engine leader (%s)", self._instance_id)
        try:
            await self._on_elected()
        except Exception:
            logger.exception("Engine startup after election failed")

    async def _election_loop(self) -> None:
        while True:
            try:
                if self.is_leader:
                    renewed = await self._redis.eval(
                        _RENEW_SCRIPT, 1, LOCK_KEY, self._instance_id, str(LOCK_TTL_SECONDS)
                    )
                    if not renewed:
                        # Lock lost (e.g. long GC pause / Redis flush). Engines in
                        # this process keep running; another worker may also be
                        # elected now. Log loudly — this should be rare.
                        logger.error(
                            "Engine leader lock lost after election (%s). "
                            "Restart the API to re-consolidate engines.",
                            self._instance_id,
                        )
                        return
                else:
                    acquired = await self._redis.set(
                        LOCK_KEY, self._instance_id, nx=True, ex=LOCK_TTL_SECONDS
                    )
                    if acquired:
                        await self._become_leader()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Leader election loop error: %s", e)

            await asyncio.sleep(RENEW_INTERVAL_SECONDS)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._redis is not None:
            try:
                if self.is_leader:
                    await self._redis.eval(_RELEASE_SCRIPT, 1, LOCK_KEY, self._instance_id)
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
