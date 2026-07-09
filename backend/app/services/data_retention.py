"""
TimescaleDB compression/retention for telemetry + pruning for reading tables.

Reality check (2026-07 audit): `telemetry` is the only hypertable (created on
`time` in migration 001). `compressor_readings` and `zone_readings` have uuid
primary keys, which TimescaleDB won't accept for hypertable conversion, so
they get plain time-based pruning instead. Raw sensor data is NOT the
compliance record — leak events, repairs, and leak-rate history live in their
own tables and are never pruned here.

Scheduled daily from Celery beat (see app/workers/ops_tasks.py). All
operations are idempotent.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# Compress telemetry chunks older than this many days (columnar, ~10-20x
# smaller); drop them entirely after the retention window.
TELEMETRY_COMPRESS_AFTER_DAYS = 14
TELEMETRY_RETAIN_DAYS = 730
# Reading tables are lower-volume (1-15 min intervals) but still unbounded.
READINGS_RETAIN_DAYS = 730


async def apply_retention_policies(engine: AsyncEngine) -> dict:
    """Ensure telemetry compression + retention policies exist. Idempotent."""
    results: dict = {"compression": None, "retention": None, "errors": []}

    async with engine.begin() as conn:
        try:
            check = await conn.execute(text(
                "SELECT compression_enabled FROM timescaledb_information.hypertables "
                "WHERE hypertable_name = 'telemetry'"
            ))
            row = check.first()
        except Exception as e:
            # No TimescaleDB (e.g. sqlite tests / vanilla PG) — nothing to do.
            logger.warning("TimescaleDB not available, skipping policies: %s", e)
            results["errors"].append(f"timescaledb unavailable: {e}")
            return results

        if row is None:
            results["errors"].append("telemetry is not a hypertable")
            return results

        try:
            if not row[0]:
                await conn.execute(text(
                    "ALTER TABLE telemetry SET (timescaledb.compress, "
                    "timescaledb.compress_segmentby = 'equipment_id', "
                    "timescaledb.compress_orderby = 'time DESC, metric_name')"
                ))
            await conn.execute(text(
                f"SELECT add_compression_policy('telemetry', "
                f"INTERVAL '{TELEMETRY_COMPRESS_AFTER_DAYS} days', if_not_exists => true)"
            ))
            results["compression"] = f"compress after {TELEMETRY_COMPRESS_AFTER_DAYS}d"
        except Exception as e:
            logger.warning("Telemetry compression policy failed: %s", e)
            results["errors"].append(f"compression: {e}")

        try:
            await conn.execute(text(
                f"SELECT add_retention_policy('telemetry', "
                f"INTERVAL '{TELEMETRY_RETAIN_DAYS} days', if_not_exists => true)"
            ))
            results["retention"] = f"drop after {TELEMETRY_RETAIN_DAYS}d"
        except Exception as e:
            logger.warning("Telemetry retention policy failed: %s", e)
            results["errors"].append(f"retention: {e}")

    return results


async def prune_reading_tables(engine: AsyncEngine) -> dict:
    """Delete compressor/zone readings past the retention window."""
    results: dict = {"errors": []}
    for table, time_col in (
        ("compressor_readings", "recorded_at"),
        ("zone_readings", "recorded_at"),
    ):
        try:
            async with engine.begin() as conn:
                res = await conn.execute(text(
                    f"DELETE FROM {table} "
                    f"WHERE {time_col} < now() - INTERVAL '{READINGS_RETAIN_DAYS} days'"
                ))
                results[table] = res.rowcount
                if res.rowcount:
                    logger.info("Pruned %s rows from %s", res.rowcount, table)
        except Exception as e:
            logger.warning("Pruning %s failed: %s", table, e)
            results["errors"].append(f"{table}: {e}")
    return results


async def get_retention_stats(engine: AsyncEngine) -> dict:
    """Current storage stats for hypertables (for ops visibility)."""
    stats: dict = {}
    async with engine.begin() as conn:
        try:
            result = await conn.execute(text("""
                SELECT
                    hypertable_name,
                    pg_size_pretty(hypertable_size(format('%I.%I', hypertable_schema, hypertable_name)::regclass)) AS total_size,
                    num_chunks,
                    compression_enabled
                FROM timescaledb_information.hypertables
                WHERE hypertable_schema = 'public'
                ORDER BY hypertable_name
            """))
            stats["hypertables"] = [
                {"name": r[0], "total_size": r[1], "num_chunks": r[2], "compression": r[3]}
                for r in result.fetchall()
            ]
        except Exception as e:
            stats["error"] = str(e)
    return stats
