"""
Energy Analytics Engine — background task orchestrator.

Schedule:
  setpoint_drift      every hour
  excess_lift         every 24 h
  defrost             every 24 h
  condenser_fouling   every 24 h
  charge_anomaly      every 24 h
  compressor_degr.    every 168 h (7 days)

Each run fetches all facilities from the DB and fans out to per-facility
module calls. Errors in one facility never block others.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.facility import Facility

from app.services.energy_analytics.excess_lift         import run_excess_lift
from app.services.energy_analytics.defrost             import run_defrost
from app.services.energy_analytics.setpoint_drift      import run_setpoint_drift
from app.services.energy_analytics.compressor_degradation import run_compressor_degradation
from app.services.energy_analytics.condenser_fouling   import run_condenser_fouling
from app.services.energy_analytics.charge_anomaly      import run_charge_anomaly

logger = logging.getLogger("kelvex.energy.engine")

_INTERVAL_SETPOINT   = 3600        # 1 h
_INTERVAL_DAILY      = 86400       # 24 h
_INTERVAL_WEEKLY     = 86400 * 7   # 7 days

_stop_event: asyncio.Event | None = None
_task: asyncio.Task | None = None


async def start_energy_analytics_engine() -> None:
    global _stop_event, _task
    if _task is not None:
        return  # already running
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_engine_loop(_stop_event), name="energy_analytics_engine")
    logger.info("Energy analytics engine started")


async def stop_energy_analytics_engine() -> None:
    global _task, _stop_event
    if _stop_event:
        _stop_event.set()
    if _task:
        try:
            await asyncio.wait_for(_task, timeout=30)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            _task.cancel()
    _task = None
    _stop_event = None
    logger.info("Energy analytics engine stopped")


async def _engine_loop(stop: asyncio.Event) -> None:
    # Track last-run time per module
    last_run: dict[str, datetime | None] = {
        "setpoint":    None,
        "daily":       None,
        "weekly":      None,
    }

    logger.info("Engine loop running")

    while not stop.is_set():
        now = datetime.now(timezone.utc)

        def _due(key: str, interval_s: int) -> bool:
            lr = last_run[key]
            if lr is None:
                return True
            return (now - lr).total_seconds() >= interval_s

        try:
            async with AsyncSessionLocal() as db:
                facility_ids = await _get_facility_ids(db)

            if _due("setpoint", _INTERVAL_SETPOINT):
                await _run_all(facility_ids, run_setpoint_drift, "setpoint_drift")
                last_run["setpoint"] = now

            if _due("daily", _INTERVAL_DAILY):
                await _run_all(facility_ids, run_excess_lift,       "excess_lift")
                await _run_all(facility_ids, run_defrost,           "defrost")
                await _run_all(facility_ids, run_condenser_fouling, "condenser_fouling")
                await _run_all(facility_ids, run_charge_anomaly,    "charge_anomaly")
                last_run["daily"] = now

            if _due("weekly", _INTERVAL_WEEKLY):
                await _run_all(facility_ids, run_compressor_degradation, "compressor_degradation")
                last_run["weekly"] = now

        except Exception:
            logger.exception("Engine loop iteration failed")

        # Sleep in small chunks so stop_event is responsive
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass

    logger.info("Engine loop exiting")


async def _get_facility_ids(db: AsyncSession) -> list:
    result = await db.execute(select(Facility.id))
    return [row[0] for row in result.fetchall()]


async def _run_all(facility_ids: list, fn, label: str) -> None:
    for facility_id in facility_ids:
        try:
            async with AsyncSessionLocal() as db:
                count = await fn(facility_id, db)
                await db.commit()
            if count:
                logger.debug("%s: facility %s → %d opportunities", label, facility_id, count)
        except Exception:
            logger.exception("%s failed for facility %s", label, facility_id)
