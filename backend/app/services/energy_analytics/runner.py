"""
Shared utilities for energy analytics modules.

- annualize_usd        — standard dollar/kWh conversion used by all modules
- get_facility_rate    — blended $/kWh from facility record or derived from bills
- get_system_telemetry — fetch telemetry for a system as a wide pandas DataFrame
- upsert_opportunity   — idempotent write to energy_opportunities
- get_energy_config    — fetch or create EnergySystemConfig for a system
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Iterable

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import UtilityBill
from app.models.energy import EnergySystemConfig, EnergyOpportunity
from app.models.facility import Facility

logger = logging.getLogger("kelvex.energy.runner")

# National average all-in rate used only as last resort — always prefer real bills
_DEFAULT_RATE_USD_KWH = 0.12
_POWER_METRICS = frozenset({"compressor_power", "compressor_amps"})


# ── Core math ────────────────────────────────────────────────────────────────

def annualize_usd(
    penalty_fraction: float,
    baseline_kwh_window: float,
    hours_in_window: float,
    usd_per_kwh: float,
) -> tuple[float, float]:
    """Return (kwh_year, usd_year) for a given penalty fraction and baseline window."""
    kwh_year = (baseline_kwh_window / hours_in_window) * 8760 * penalty_fraction
    return kwh_year, kwh_year * usd_per_kwh


# ── Facility rate ─────────────────────────────────────────────────────────────

async def get_facility_rate(facility_id: uuid.UUID, db: AsyncSession) -> float:
    """
    Return all-in blended $/kWh for a facility.

    Priority:
      1. facilities.blended_usd_per_kwh (manually set from actual bill)
      2. Derived from most recent 3 utility bills (total_cost / total_kwh)
      3. National default (0.12) — logged as a warning
    """
    result = await db.execute(
        select(Facility.blended_usd_per_kwh).where(Facility.id == facility_id)
    )
    explicit = result.scalar_one_or_none()
    if explicit and explicit > 0:
        return explicit

    # Derive from recent bills
    result = await db.execute(
        select(UtilityBill.total_cost, UtilityBill.total_kwh)
        .where(
            UtilityBill.facility_id == facility_id,
            UtilityBill.total_kwh > 0,
            UtilityBill.total_cost > 0,
        )
        .order_by(UtilityBill.period_end.desc())
        .limit(3)
    )
    bills = result.fetchall()
    if bills:
        total_cost = sum(float(b.total_cost) for b in bills)
        total_kwh  = sum(float(b.total_kwh)  for b in bills)
        if total_kwh > 0:
            return total_cost / total_kwh

    logger.warning(
        "No blended rate for facility %s — using default %.2f $/kWh. "
        "Set facilities.blended_usd_per_kwh from an actual utility bill.",
        facility_id, _DEFAULT_RATE_USD_KWH,
    )
    return _DEFAULT_RATE_USD_KWH


# ── Telemetry fetch ───────────────────────────────────────────────────────────

async def get_system_telemetry(
    system_id: uuid.UUID,
    metrics: Iterable[str],
    hours_back: float,
    db: AsyncSession,
    bucket_minutes: int = 15,
) -> pd.DataFrame:
    """
    Fetch telemetry for all equipment in a system, bucketed and pivoted.

    Returns a DataFrame indexed by bucket timestamp with one column per metric.
    Power metrics (compressor_power, compressor_amps) are SUMmed across equipment;
    all others are AVGed (max across equipment — handles multi-probe systems).

    Empty DataFrame is returned when there is no data.
    """
    metrics_list = list(metrics)
    if not metrics_list:
        return pd.DataFrame()

    sql = text("""
        SELECT
            time_bucket(:bucket_interval, t.time)  AS bucket,
            t.metric_name,
            CASE
                WHEN t.metric_name = ANY(:power_metrics) THEN sum(t.value)
                ELSE avg(t.value)
            END AS value
        FROM telemetry t
        JOIN equipment e ON e.id = t.equipment_id
        WHERE e.system_id = :system_id
          AND t.time >= now() - make_interval(hours => :hours_back)
          AND t.metric_name = ANY(:metrics)
          AND t.quality <= 1
        GROUP BY 1, t.metric_name
        ORDER BY 1
    """)

    result = await db.execute(sql, {
        "system_id": str(system_id),
        "hours_back": hours_back,
        "metrics": metrics_list,
        "power_metrics": list(_POWER_METRICS),
        "bucket_interval": f"{bucket_minutes} minutes",
    })
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame()

    df_long = pd.DataFrame(rows, columns=["bucket", "metric_name", "value"])
    df_wide = df_long.pivot_table(
        index="bucket", columns="metric_name", values="value", aggfunc="first"
    ).reset_index()
    df_wide.columns.name = None
    df_wide["bucket"] = pd.to_datetime(df_wide["bucket"], utc=True)
    return df_wide


# ── Opportunity upsert ────────────────────────────────────────────────────────

async def upsert_opportunity(
    facility_id: uuid.UUID,
    system_id: uuid.UUID,
    opp_type: str,
    window_start: datetime,
    window_end: datetime,
    data: dict,
    db: AsyncSession,
    equipment_id: uuid.UUID | None = None,
) -> None:
    """
    Idempotent upsert into energy_opportunities.

    The unique constraint (system_id, equipment_id, opp_type, window_start) means
    re-running the same daily job produces one row, not duplicates. Existing open
    opportunities are updated in-place with fresh estimates; resolved/dismissed ones
    are left untouched.
    """
    stmt = (
        pg_insert(EnergyOpportunity)
        .values(
            id=uuid.uuid4(),
            facility_id=facility_id,
            system_id=system_id,
            equipment_id=equipment_id,
            opp_type=opp_type,
            window_start=window_start,
            window_end=window_end,
            detected_at=datetime.now(timezone.utc),
            **{k: v for k, v in data.items() if k in {
                "current_value", "target_value",
                "estimated_kwh_year", "estimated_usd_year",
                "confidence", "recommended_action", "evidence",
            }},
            status="open",
        )
        .on_conflict_do_update(
            constraint="uq_opportunity_per_window",
            set_={
                "detected_at": datetime.now(timezone.utc),
                "current_value": data.get("current_value"),
                "target_value": data.get("target_value"),
                "estimated_kwh_year": data.get("estimated_kwh_year"),
                "estimated_usd_year": data.get("estimated_usd_year"),
                "confidence": data.get("confidence"),
                "recommended_action": data.get("recommended_action"),
                "evidence": data.get("evidence"),
            },
            where=EnergyOpportunity.status == "open",
        )
    )
    await db.execute(stmt)


# ── System energy config ──────────────────────────────────────────────────────

async def get_energy_config(
    system_id: uuid.UUID,
    db: AsyncSession,
) -> EnergySystemConfig:
    """
    Return the EnergySystemConfig for a system, creating defaults if not present.
    """
    result = await db.execute(
        select(EnergySystemConfig).where(EnergySystemConfig.system_id == system_id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        config = EnergySystemConfig(system_id=system_id)
        db.add(config)
        await db.flush()
    return config
