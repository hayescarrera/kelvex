"""
Celery tasks for automated leak detection and forecasting.

Each task bridges sync Celery → async SQLAlchemy via asyncio.run().
A single circuit failure is caught and logged; the batch continues.
"""

import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.workers.celery_app import celery_app
from app.core.config import get_settings
from app.models.org_feature import OrgFeature
from app.models.refrigerant import RefrigerantCircuit, LeakEvent, RefrigerantAdd
from app.models.compressor import Compressor, CompressorReading
from app.models.zone_sensor import CompressorRack
from app.models.circuit_forecast import CircuitForecast
from app.services.leak_detection import (
    detect_pressure_drift,
    detect_superheat_rise,
    detect_add_pattern_anomaly,
    combine_signals,
)
from app.services.forecasting import select_and_run_forecast

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _worker_sessions():
    """Fresh engine per asyncio.run() call.

    Celery runs each task in a new event loop; a module-level engine's pooled
    asyncpg connections stay bound to the loop that created them, so reusing
    them across tasks fails. NullPool gives every session its own connection
    on the current loop, and dispose() closes everything before the loop dies.
    """
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


# ── Celery tasks ──────────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.detection_tasks.run_detection_batch")
def run_detection_batch():
    """Hourly task: runs leak detection for all orgs with auto_detection enabled."""
    asyncio.run(_async_detection_batch())


@celery_app.task(name="app.workers.detection_tasks.run_forecasting_batch")
def run_forecasting_batch():
    """Daily task: updates forecasts for all circuits with enough data."""
    asyncio.run(_async_forecasting_batch())


# ── Detection batch ───────────────────────────────────────────────────────────

async def _async_detection_batch() -> None:
    """Full detection pipeline for orgs with auto_detection enabled."""
    logger.info("Starting automated leak detection batch.")

    async with _worker_sessions() as session_factory:
        async with session_factory() as db:
            # 1. Orgs with auto_detection enabled
            result = await db.execute(
                select(OrgFeature.org_id).where(
                    and_(
                        OrgFeature.feature_key == "auto_detection",
                        OrgFeature.enabled.is_(True),
                    )
                )
            )
            org_ids = [row[0] for row in result.fetchall()]

        if not org_ids:
            logger.info("No orgs with auto_detection enabled.")
            return

        logger.info("Running detection for %d orgs.", len(org_ids))

        for org_id in org_ids:
            try:
                await _detect_for_org(session_factory, org_id)
            except Exception:
                logger.exception("Detection batch failed for org %s.", org_id)

    logger.info("Detection batch complete.")


async def _detect_for_org(session_factory: async_sessionmaker, org_id) -> None:
    """Run detection for all active circuits belonging to one org."""
    async with session_factory() as db:
        result = await db.execute(
            select(RefrigerantCircuit).where(
                and_(
                    RefrigerantCircuit.org_id == org_id,
                    RefrigerantCircuit.is_active.is_(True),
                )
            )
        )
        circuits = result.scalars().all()

    for circuit in circuits:
        try:
            await _detect_for_circuit(session_factory, circuit)
        except Exception:
            logger.exception(
                "Detection failed for circuit %s (org %s).", circuit.id, org_id
            )


async def _detect_for_circuit(session_factory: async_sessionmaker, circuit: RefrigerantCircuit) -> None:
    """Run all detection signals for a single circuit and create a LeakEvent if warranted."""
    now = datetime.now(timezone.utc)
    circuit_id = circuit.id
    org_id = circuit.org_id
    facility_id = circuit.facility_id

    hourly_pressures: list[float] = []
    hourly_superheat: list[float] = []
    design_suction_psi: float | None = None
    rack = None
    rack_name_str = "Unknown"

    async with session_factory() as db:
        # ── Rack + compressors ─────────────────────────────────────────────────
        if circuit.rack_id is not None:
            rack_result = await db.execute(
                select(CompressorRack).where(CompressorRack.id == circuit.rack_id)
            )
            rack = rack_result.scalar_one_or_none()

        if rack is not None:
            rack_name_str = rack.name
            design_suction_psi = rack.design_suction_psi

            # Compressors on this rack
            comp_result = await db.execute(
                select(Compressor).where(
                    and_(
                        Compressor.rack_name == rack.name,
                        Compressor.facility_id == facility_id,
                    )
                )
            )
            compressors = comp_result.scalars().all()
            comp_ids = [c.id for c in compressors]

            if comp_ids:
                # Last 72h readings — aggregate hourly averages
                cutoff_72h = now - timedelta(hours=72)
                readings_result = await db.execute(
                    select(CompressorReading).where(
                        and_(
                            CompressorReading.compressor_id.in_(comp_ids),
                            CompressorReading.recorded_at >= cutoff_72h,
                        )
                    ).order_by(CompressorReading.recorded_at)
                )
                readings = readings_result.scalars().all()

                # Bucket into hourly averages
                hourly_pressures, hourly_superheat = _aggregate_hourly(readings)

        # ── Refrigerant adds ───────────────────────────────────────────────────
        cutoff_365d = now - timedelta(days=365)
        adds_result = await db.execute(
            select(RefrigerantAdd).where(
                and_(
                    RefrigerantAdd.circuit_id == circuit_id,
                    RefrigerantAdd.added_at >= cutoff_365d,
                )
            ).order_by(RefrigerantAdd.added_at)
        )
        adds = adds_result.scalars().all()
        add_timestamps = [a.added_at for a in adds]
        add_amounts = [a.amount_lbs for a in adds]

    # ── Pure-Python detection ─────────────────────────────────────────────────
    pressure_result = detect_pressure_drift(hourly_pressures, design_suction_psi)
    superheat_result = detect_superheat_rise(hourly_superheat)
    add_result = detect_add_pattern_anomaly(add_timestamps, add_amounts)

    verdict = combine_signals(pressure_result, superheat_result, add_result)

    if not verdict["should_create_event"]:
        return

    # ── Duplicate check + event creation ─────────────────────────────────────
    async with session_factory() as db:
        cutoff_7d = now - timedelta(days=7)
        dup_result = await db.execute(
            select(LeakEvent).where(
                and_(
                    LeakEvent.circuit_id == circuit_id,
                    LeakEvent.status.in_(["open", "investigating"]),
                    LeakEvent.detected_at >= cutoff_7d,
                )
            )
        )
        existing = dup_result.scalar_one_or_none()

        if existing is not None:
            logger.debug(
                "Skipping duplicate event for circuit %s; existing event %s.",
                circuit_id, existing.id,
            )
            return

        event = LeakEvent(
            org_id=org_id,
            facility_id=facility_id,
            circuit_id=circuit_id,
            rack_name=rack_name_str,
            detection_method=verdict["detection_method"],
            confidence=verdict["confidence"],
            status="open",
            detected_at=now,
            notes=verdict["summary"],
        )
        db.add(event)
        await db.commit()
        logger.info(
            "Created LeakEvent for circuit %s (method=%s, confidence=%s).",
            circuit_id, verdict["detection_method"], verdict["confidence"],
        )


def _aggregate_hourly(
    readings: list[CompressorReading],
) -> tuple[list[float], list[float]]:
    """
    Group CompressorReading rows into hourly buckets and compute mean
    suction_pressure_psi and superheat_f per bucket.

    Returns (hourly_pressures, hourly_superheat) ordered oldest→newest.
    """
    pressure_buckets: dict[datetime, list[float]] = defaultdict(list)
    superheat_buckets: dict[datetime, list[float]] = defaultdict(list)

    for r in readings:
        ts = r.recorded_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        bucket_hour = ts.replace(minute=0, second=0, microsecond=0)

        if r.suction_pressure_psi is not None:
            pressure_buckets[bucket_hour].append(r.suction_pressure_psi)
        if r.superheat_f is not None:
            superheat_buckets[bucket_hour].append(r.superheat_f)

    all_hours = sorted(set(list(pressure_buckets.keys()) + list(superheat_buckets.keys())))

    hourly_pressures = [
        float(sum(pressure_buckets[h]) / len(pressure_buckets[h]))
        for h in all_hours
        if h in pressure_buckets
    ]
    hourly_superheat = [
        float(sum(superheat_buckets[h]) / len(superheat_buckets[h]))
        for h in all_hours
        if h in superheat_buckets
    ]

    return hourly_pressures, hourly_superheat


# ── Forecasting batch ─────────────────────────────────────────────────────────

async def _async_forecasting_batch() -> None:
    """Full forecasting pipeline for orgs with forecasting enabled."""
    logger.info("Starting refrigerant forecasting batch.")

    async with _worker_sessions() as session_factory:
        async with session_factory() as db:
            result = await db.execute(
                select(OrgFeature.org_id).where(
                    and_(
                        OrgFeature.feature_key == "forecasting",
                        OrgFeature.enabled.is_(True),
                    )
                )
            )
            org_ids = [row[0] for row in result.fetchall()]

        if not org_ids:
            logger.info("No orgs with forecasting enabled.")
            return

        logger.info("Running forecasting for %d orgs.", len(org_ids))

        for org_id in org_ids:
            try:
                await _forecast_for_org(session_factory, org_id)
            except Exception:
                logger.exception("Forecasting batch failed for org %s.", org_id)

    logger.info("Forecasting batch complete.")


async def _forecast_for_org(session_factory: async_sessionmaker, org_id) -> None:
    """Update forecasts for all active circuits in an org."""
    async with session_factory() as db:
        result = await db.execute(
            select(RefrigerantCircuit).where(
                and_(
                    RefrigerantCircuit.org_id == org_id,
                    RefrigerantCircuit.is_active.is_(True),
                )
            )
        )
        circuits = result.scalars().all()

    for circuit in circuits:
        try:
            await _forecast_for_circuit(session_factory, circuit)
        except Exception:
            logger.exception(
                "Forecasting failed for circuit %s (org %s).", circuit.id, org_id
            )


async def _forecast_for_circuit(session_factory: async_sessionmaker, circuit: RefrigerantCircuit) -> None:
    """Compute and upsert the forecast for a single circuit."""
    now = datetime.now(timezone.utc)

    async with session_factory() as db:
        adds_result = await db.execute(
            select(RefrigerantAdd).where(
                RefrigerantAdd.circuit_id == circuit.id
            ).order_by(RefrigerantAdd.added_at)
        )
        adds = adds_result.scalars().all()

    if not adds:
        return

    add_timestamps = [a.added_at for a in adds]
    add_amounts = [a.amount_lbs for a in adds]

    result = select_and_run_forecast(
        add_timestamps=add_timestamps,
        add_amounts_lbs=add_amounts,
        full_charge_lbs=circuit.full_charge_lbs,
        horizon_days=90,
    )

    async with session_factory() as db:
        # Upsert: try to find existing row by circuit_id
        existing_result = await db.execute(
            select(CircuitForecast).where(CircuitForecast.circuit_id == circuit.id)
        )
        forecast_row = existing_result.scalar_one_or_none()

        if forecast_row is None:
            forecast_row = CircuitForecast(
                circuit_id=circuit.id,
                org_id=circuit.org_id,
            )
            db.add(forecast_row)

        forecast_row.method = result["method"]
        forecast_row.projected_adds_lbs = result.get("projected_adds_lbs")
        forecast_row.projected_adds_lbs_low = result.get("projected_adds_lbs_low")
        forecast_row.projected_adds_lbs_high = result.get("projected_adds_lbs_high")
        forecast_row.lbs_per_day = result.get("lbs_per_day")
        forecast_row.days_to_aim_threshold = result.get("days_to_aim_threshold")
        forecast_row.days_to_aim_warning = result.get("days_to_aim_warning")
        forecast_row.current_annual_leak_rate_pct = result.get("current_annual_leak_rate_pct")
        forecast_row.confidence = result.get("confidence")
        forecast_row.horizon_days = 90
        forecast_row.computed_at = now

        await db.commit()
        logger.debug("Upserted forecast for circuit %s (method=%s).", circuit.id, result["method"])
