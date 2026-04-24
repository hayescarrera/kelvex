"""
Polling Engine — background worker that runs integration adapters on schedule.

This is the heart of the data ingestion pipeline. It:
  1. Loads all enabled integrations from the database
  2. Groups them by poll interval
  3. Runs each adapter's poll() method on schedule
  4. Writes telemetry readings to TimescaleDB
  5. Updates integration stats (last_poll, error counts, etc.)

For cloud API integrations, this runs in the backend process.
For edge protocol integrations (Modbus TCP, BACnet/IP), the edge agent
runs its own polling loop — those integrations are skipped here.

Designed to run as an asyncio background task within the FastAPI app,
or as a standalone worker process.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.crypto import decrypt_json
from app.models.integration import Integration, IntegrationCredential
from app.models.telemetry import Telemetry
from app.integrations.adapters import get_adapter_class

logger = logging.getLogger("coldgrid.polling_engine")


class PollingEngine:
    """
    Manages scheduled polling of all enabled cloud integrations.

    Usage:
        engine = PollingEngine(database_url="postgresql+asyncpg://...")
        await engine.start()   # runs forever
        await engine.stop()    # graceful shutdown
    """

    def __init__(
        self,
        database_url: str | None = None,
        session_factory: async_sessionmaker | None = None,
        tick_interval: int = 5,
    ):
        """
        Args:
            database_url: Database connection string (creates its own engine)
            session_factory: Or provide an existing session factory
            tick_interval: How often (seconds) to check for integrations due for polling
        """
        self._tick_interval = tick_interval
        self._running = False
        self._tasks: dict[UUID, asyncio.Task] = {}
        self._adapters: dict[UUID, object] = {}  # cached adapter instances

        if session_factory:
            self._session_factory = session_factory
        elif database_url:
            engine = create_async_engine(database_url, pool_size=5, max_overflow=10)
            self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        else:
            raise ValueError("Provide either database_url or session_factory")

    async def start(self):
        """Start the polling engine main loop."""
        logger.info("Polling engine starting")
        self._running = True

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Polling engine tick error: {e}", exc_info=True)

            await asyncio.sleep(self._tick_interval)

        logger.info("Polling engine stopped")

    async def stop(self):
        """Graceful shutdown."""
        logger.info("Polling engine shutting down")
        self._running = False

        # Cancel running poll tasks
        for task in self._tasks.values():
            task.cancel()

        # Disconnect all cached adapters
        for adapter in self._adapters.values():
            try:
                await adapter.disconnect()
            except Exception:
                pass

        self._tasks.clear()
        self._adapters.clear()

    async def _tick(self):
        """
        Check for integrations that are due for polling.
        Only cloud_api and bas_middleware types — edge_protocol is handled
        by the edge agent's own loop.
        """
        async with self._session_factory() as db:
            result = await db.execute(
                select(Integration).where(
                    Integration.enabled == True,
                    Integration.integration_type.in_(["cloud_api", "bas_middleware"]),
                )
            )
            integrations = result.scalars().all()

        now = datetime.now(timezone.utc)

        for integration in integrations:
            # Skip if already polling
            if integration.id in self._tasks and not self._tasks[integration.id].done():
                continue

            # Check if it's time to poll
            poll_interval = integration.config.get("poll_interval_sec", 60)
            if integration.last_poll_at:
                elapsed = (now - integration.last_poll_at).total_seconds()
                if elapsed < poll_interval:
                    continue

            # Skip if no device map configured
            if not integration.device_map:
                continue

            # Launch poll task
            task = asyncio.create_task(
                self._poll_integration(integration.id),
                name=f"poll-{integration.provider}-{integration.id}",
            )
            self._tasks[integration.id] = task

    async def _poll_integration(self, integration_id: UUID):
        """Poll a single integration and ingest readings."""
        async with self._session_factory() as db:
            # Re-fetch with fresh session
            result = await db.execute(
                select(Integration).where(Integration.id == integration_id)
            )
            integration = result.scalar_one_or_none()
            if not integration or not integration.enabled:
                return

            # Get credentials
            credentials = None
            if integration.credential_id:
                cred_result = await db.execute(
                    select(IntegrationCredential).where(
                        IntegrationCredential.id == integration.credential_id
                    )
                )
                cred = cred_result.scalar_one_or_none()
                if cred:
                    credentials = decrypt_json(cred.credentials_encrypted)

            now = datetime.now(timezone.utc)

            try:
                # Get or create adapter instance
                adapter = self._get_or_create_adapter(
                    integration_id, integration.provider,
                    integration.config, credentials,
                )

                # Authenticate if needed
                await adapter.authenticate()

                # Poll
                readings = await adapter.poll(device_map=integration.device_map)

                # Ingest readings into TimescaleDB
                ingested = 0
                for reading in readings:
                    try:
                        telemetry = Telemetry(
                            equipment_id=reading.equipment_id,
                            metric_name=reading.metric_name,
                            value=reading.value,
                            unit=reading.unit,
                            recorded_at=reading.timestamp or now,
                            quality=reading.quality,
                        )
                        db.add(telemetry)
                        ingested += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to create telemetry record: {e}"
                        )

                if ingested > 0:
                    await db.flush()

                # Update integration stats
                await db.execute(
                    update(Integration)
                    .where(Integration.id == integration_id)
                    .values(
                        last_poll_at=now,
                        last_success_at=now,
                        connection_state="connected",
                        total_polls=Integration.total_polls + 1,
                        total_readings_ingested=(
                            Integration.total_readings_ingested + ingested
                        ),
                        updated_at=now,
                    )
                )
                await db.commit()

                logger.debug(
                    f"Polled {integration.provider} ({integration.name}): "
                    f"{ingested} readings ingested"
                )

            except Exception as e:
                logger.error(
                    f"Poll failed for {integration.provider} ({integration.name}): {e}"
                )
                # Update error state
                try:
                    await db.execute(
                        update(Integration)
                        .where(Integration.id == integration_id)
                        .values(
                            last_poll_at=now,
                            last_error=str(e)[:1000],
                            last_error_at=now,
                            connection_state="error",
                            total_polls=Integration.total_polls + 1,
                            total_errors=Integration.total_errors + 1,
                            updated_at=now,
                        )
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()

                # Evict cached adapter on error so it reconnects next time
                self._adapters.pop(integration_id, None)

    def _get_or_create_adapter(
        self, integration_id: UUID, provider: str,
        config: dict, credentials: dict | None,
    ):
        """Get cached adapter or create a new one."""
        if integration_id not in self._adapters:
            adapter_cls = get_adapter_class(provider)
            self._adapters[integration_id] = adapter_cls(
                config=config, credentials=credentials,
            )
        return self._adapters[integration_id]

    async def poll_once(self, integration_id: UUID):
        """Poll a single integration immediately (for manual trigger)."""
        await self._poll_integration(integration_id)


# ── FastAPI Lifespan Integration ────────────────────────

_engine_instance: PollingEngine | None = None


async def start_polling_engine(session_factory: async_sessionmaker):
    """Start the polling engine as a background task."""
    global _engine_instance
    _engine_instance = PollingEngine(session_factory=session_factory)
    asyncio.create_task(_engine_instance.start())
    logger.info("Polling engine background task started")


async def stop_polling_engine():
    """Stop the polling engine."""
    global _engine_instance
    if _engine_instance:
        await _engine_instance.stop()
        _engine_instance = None
