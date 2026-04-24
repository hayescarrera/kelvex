"""
TimescaleDB data retention, compression, and continuous aggregate policies.

This module provides SQL statements and a service to manage:
  - Hypertable conversion for time-series tables
  - Compression policies (compress chunks older than N days)
  - Retention policies (drop chunks older than N days)
  - Continuous aggregates for pre-computed roll-ups (hourly, daily)
  - Refresh policies to keep continuous aggregates up to date

Usage:
  Call `apply_retention_policies(engine)` on startup or via a management command.
  Policies are idempotent — safe to re-run.
"""

from datetime import timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
import logging

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────

HYPERTABLE_CONFIG = {
    "telemetry": {
        "time_column": "recorded_at",
        "chunk_interval": "1 day",
        "compress_after_days": 7,
        "drop_after_days": 365,
    },
    "compressor_readings": {
        "time_column": "recorded_at",
        "chunk_interval": "1 day",
        "compress_after_days": 7,
        "drop_after_days": 365,
    },
    "zone_readings": {
        "time_column": "recorded_at",
        "chunk_interval": "1 day",
        "compress_after_days": 7,
        "drop_after_days": 365,
        "compress_segmentby": "zone_id",
    },
    "compliance_logs": {
        "time_column": "checked_at",
        "chunk_interval": "1 day",
        "compress_after_days": 30,
        "drop_after_days": 730,  # 2 years for HACCP audit trail
        "compress_segmentby": "ccp_id",
    },
}

# ── Continuous Aggregates ────────────────────────

CONTINUOUS_AGGREGATES = [
    {
        "name": "telemetry_hourly",
        "source_table": "telemetry",
        "time_column": "recorded_at",
        "sql": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_hourly
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 hour', recorded_at) AS bucket,
                facility_id,
                equipment_id,
                metric_name,
                avg(value) AS avg_value,
                min(value) AS min_value,
                max(value) AS max_value,
                count(*) AS sample_count
            FROM telemetry
            GROUP BY bucket, facility_id, equipment_id, metric_name
            WITH NO DATA;
        """,
        "refresh_start": "30 days",
        "refresh_end": "1 hour",
        "refresh_interval": "1 hour",
    },
    {
        "name": "telemetry_daily",
        "source_table": "telemetry",
        "time_column": "recorded_at",
        "sql": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_daily
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 day', recorded_at) AS bucket,
                facility_id,
                equipment_id,
                metric_name,
                avg(value) AS avg_value,
                min(value) AS min_value,
                max(value) AS max_value,
                count(*) AS sample_count
            FROM telemetry
            GROUP BY bucket, facility_id, equipment_id, metric_name
            WITH NO DATA;
        """,
        "refresh_start": "365 days",
        "refresh_end": "1 day",
        "refresh_interval": "1 day",
    },
    {
        "name": "compressor_readings_hourly",
        "source_table": "compressor_readings",
        "time_column": "recorded_at",
        "sql": """
            CREATE MATERIALIZED VIEW IF NOT EXISTS compressor_readings_hourly
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 hour', recorded_at) AS bucket,
                compressor_id,
                avg(suction_pressure) AS avg_suction_pressure,
                avg(discharge_pressure) AS avg_discharge_pressure,
                avg(suction_temp) AS avg_suction_temp,
                avg(discharge_temp) AS avg_discharge_temp,
                avg(power_kw) AS avg_power_kw,
                max(power_kw) AS max_power_kw,
                avg(oil_pressure) AS avg_oil_pressure,
                count(*) AS sample_count
            FROM compressor_readings
            GROUP BY bucket, compressor_id
            WITH NO DATA;
        """,
        "refresh_start": "30 days",
        "refresh_end": "1 hour",
        "refresh_interval": "1 hour",
    },
]


# ── Apply Policies ───────────────────────────────

async def apply_retention_policies(engine: AsyncEngine) -> dict:
    """
    Apply all TimescaleDB retention, compression, and continuous aggregate
    policies. Idempotent — safe to call on every startup.

    Returns a summary dict of what was applied.
    """
    results = {"hypertables": [], "compression": [], "retention": [], "aggregates": [], "errors": []}

    async with engine.begin() as conn:
        # Check if TimescaleDB extension is available
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        except Exception as e:
            logger.warning(f"TimescaleDB not available: {e}")
            results["errors"].append(f"TimescaleDB extension not available: {e}")
            return results

        # 1. Convert tables to hypertables
        for table, config in HYPERTABLE_CONFIG.items():
            try:
                # Check if already a hypertable
                check = await conn.execute(text(
                    "SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name = :table"
                ), {"table": table})
                is_hypertable = (check.scalar() or 0) > 0

                if not is_hypertable:
                    await conn.execute(text(
                        f"SELECT create_hypertable('{table}', '{config['time_column']}', "
                        f"chunk_time_interval => INTERVAL '{config['chunk_interval']}', "
                        f"migrate_data => true, if_not_exists => true)"
                    ))
                    results["hypertables"].append(f"{table} (created)")
                    logger.info(f"Created hypertable: {table}")
                else:
                    results["hypertables"].append(f"{table} (exists)")
            except Exception as e:
                logger.warning(f"Failed to create hypertable {table}: {e}")
                results["errors"].append(f"hypertable {table}: {e}")

        # 2. Compression policies
        for table, config in HYPERTABLE_CONFIG.items():
            try:
                # Enable compression
                segmentby = config.get("compress_segmentby", "facility_id")
                await conn.execute(text(
                    f"ALTER TABLE {table} SET (timescaledb.compress, "
                    f"timescaledb.compress_segmentby = '{segmentby}')"
                ))

                # Add compression policy
                await conn.execute(text(
                    f"SELECT add_compression_policy('{table}', "
                    f"INTERVAL '{config['compress_after_days']} days', "
                    f"if_not_exists => true)"
                ))
                results["compression"].append(f"{table}: compress after {config['compress_after_days']}d")
                logger.info(f"Compression policy set for {table}")
            except Exception as e:
                logger.warning(f"Compression policy failed for {table}: {e}")
                results["errors"].append(f"compression {table}: {e}")

        # 3. Retention policies
        for table, config in HYPERTABLE_CONFIG.items():
            try:
                await conn.execute(text(
                    f"SELECT add_retention_policy('{table}', "
                    f"INTERVAL '{config['drop_after_days']} days', "
                    f"if_not_exists => true)"
                ))
                results["retention"].append(f"{table}: drop after {config['drop_after_days']}d")
                logger.info(f"Retention policy set for {table}")
            except Exception as e:
                logger.warning(f"Retention policy failed for {table}: {e}")
                results["errors"].append(f"retention {table}: {e}")

        # 4. Continuous aggregates
        for agg in CONTINUOUS_AGGREGATES:
            try:
                # Check if exists
                check = await conn.execute(text(
                    "SELECT count(*) FROM timescaledb_information.continuous_aggregates "
                    "WHERE view_name = :name"
                ), {"name": agg["name"]})
                exists = (check.scalar() or 0) > 0

                if not exists:
                    await conn.execute(text(agg["sql"]))

                    # Add refresh policy
                    await conn.execute(text(
                        f"SELECT add_continuous_aggregate_policy('{agg['name']}', "
                        f"start_offset => INTERVAL '{agg['refresh_start']}', "
                        f"end_offset => INTERVAL '{agg['refresh_end']}', "
                        f"schedule_interval => INTERVAL '{agg['refresh_interval']}', "
                        f"if_not_exists => true)"
                    ))
                    results["aggregates"].append(f"{agg['name']} (created)")
                    logger.info(f"Created continuous aggregate: {agg['name']}")
                else:
                    results["aggregates"].append(f"{agg['name']} (exists)")
            except Exception as e:
                logger.warning(f"Continuous aggregate failed for {agg['name']}: {e}")
                results["errors"].append(f"aggregate {agg['name']}: {e}")

    return results


async def get_retention_stats(engine: AsyncEngine) -> dict:
    """Get current storage stats for hypertables."""
    stats = {}
    async with engine.begin() as conn:
        try:
            # Hypertable sizes
            result = await conn.execute(text("""
                SELECT
                    hypertable_name,
                    pg_size_pretty(hypertable_size(format('%I.%I', hypertable_schema, hypertable_name)::regclass)) AS total_size,
                    num_chunks,
                    num_compressed_chunks
                FROM timescaledb_information.hypertables
                WHERE hypertable_schema = 'public'
                ORDER BY hypertable_name
            """))
            rows = result.fetchall()
            stats["hypertables"] = [
                {
                    "name": r[0],
                    "total_size": r[1],
                    "num_chunks": r[2],
                    "compressed_chunks": r[3],
                }
                for r in rows
            ]

            # Continuous aggregate info
            agg_result = await conn.execute(text("""
                SELECT view_name, view_definition
                FROM timescaledb_information.continuous_aggregates
                WHERE materialization_hypertable_schema = 'public'
            """))
            agg_rows = agg_result.fetchall()
            stats["continuous_aggregates"] = [
                {"name": r[0]} for r in agg_rows
            ]

            # Compression stats
            comp_result = await conn.execute(text("""
                SELECT
                    hypertable_name,
                    number_compressed_chunks,
                    pg_size_pretty(before_compression_total_bytes) AS before_size,
                    pg_size_pretty(after_compression_total_bytes) AS after_size
                FROM hypertable_compression_stats('public')
            """))
            comp_rows = comp_result.fetchall()
            stats["compression"] = [
                {
                    "table": r[0],
                    "compressed_chunks": r[1],
                    "before_size": r[2],
                    "after_size": r[3],
                }
                for r in comp_rows
            ]
        except Exception as e:
            stats["error"] = str(e)

    return stats
