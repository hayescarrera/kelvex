"""
Module 4.1 — Excess Lift / Floating Head (daily)

Computes how many degrees above the achievable condensing temperature a system
is actually running, and translates that to annual kWh and dollar waste.

Achievable SCT = max(ambient_reference + design_approach_f, sct_floor_f)
  where ambient_reference = wet_bulb  for evaporative condensers
                           = dry_bulb  for air-cooled

Penalty: ~1.3%/°F of compressor energy. Weighted by hours of actual excess.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

import numpy as np

from app.services.energy_analytics.runner import (
    annualize_usd,
    get_facility_rate,
    get_energy_config,
    get_system_telemetry,
    upsert_opportunity,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.system import System
from app.models.facility import Facility

logger = logging.getLogger("kelvex.energy.excess_lift")

COEF_PCT_PER_F = 0.013   # 1.3%/°F lift reduction (industry standard; calibrate per fleet)
MIN_EXCESS_F   = 1.0     # ignore noise below 1°F
MAX_PENALTY    = 0.35    # cap at 35% — sanity check

METRICS = [
    "sct", "sst",
    "suction_pressure", "discharge_pressure",
    "compressor_power",
    "ambient_wet_bulb", "ambient_dry_bulb",
]


async def run_excess_lift(
    facility_id: uuid.UUID,
    db: AsyncSession,
    lookback_hours: float = 24.0,
) -> int:
    """
    Run excess-lift analysis for all systems in a facility.
    Returns the number of opportunities upserted.
    """
    usd_per_kwh = await get_facility_rate(facility_id, db)

    result = await db.execute(
        select(System.id).where(System.facility_id == facility_id)
    )
    system_ids = [row[0] for row in result.fetchall()]

    count = 0
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=lookback_hours)

    for system_id in system_ids:
        try:
            n = await _analyze_system(
                facility_id, system_id, usd_per_kwh,
                window_start, now, lookback_hours, db,
            )
            count += n
        except Exception:
            logger.exception("excess_lift failed for system %s", system_id)

    return count


async def _analyze_system(
    facility_id: uuid.UUID,
    system_id: uuid.UUID,
    usd_per_kwh: float,
    window_start: datetime,
    window_end: datetime,
    lookback_hours: float,
    db: AsyncSession,
) -> int:
    config = await get_energy_config(system_id, db)

    df = await get_system_telemetry(system_id, METRICS, lookback_hours, db)
    if df.empty or "sct" not in df.columns:
        return 0

    # Prefer controller-reported sct/sst; fall back to pressure conversion
    sct_col = "sct"
    if sct_col not in df.columns or df[sct_col].isna().all():
        return 0  # can't compute lift without condensing temp

    # Determine ambient reference column
    if config.condenser_type == "evaporative" and "ambient_wet_bulb" in df.columns:
        ref_col = "ambient_wet_bulb"
    elif "ambient_dry_bulb" in df.columns:
        ref_col = "ambient_dry_bulb"
    else:
        logger.debug("No ambient data for system %s — skipping excess_lift", system_id)
        return 0

    sct_floor = config.sct_floor_f or 70.0
    approach  = config.design_approach_f or 15.0

    df = df.dropna(subset=[sct_col, ref_col, "compressor_power"])
    if df.empty:
        return 0

    df["sct_achievable"] = (df[ref_col] + approach).clip(lower=sct_floor)
    df["excess_lift_f"]  = (df[sct_col] - df["sct_achievable"]).clip(lower=0)

    # Weight by actual compressor power — hours where machine was running hard matter more
    total_kwh = df["compressor_power"].sum() * (15 / 60)  # 15-min buckets
    if total_kwh <= 0:
        return 0

    avg_excess = float(np.average(df["excess_lift_f"], weights=df["compressor_power"]))
    if avg_excess < MIN_EXCESS_F:
        return 0

    penalty = min(avg_excess * COEF_PCT_PER_F, MAX_PENALTY)
    kwh_year, usd_year = annualize_usd(penalty, total_kwh, lookback_hours, usd_per_kwh)

    avg_sct         = float(df[sct_col].mean())
    avg_achievable  = float(df["sct_achievable"].mean())

    await upsert_opportunity(
        facility_id=facility_id,
        system_id=system_id,
        opp_type="excess_lift",
        window_start=window_start,
        window_end=window_end,
        data={
            "current_value":      round(avg_sct, 1),
            "target_value":       round(avg_achievable, 1),
            "estimated_kwh_year": round(kwh_year, 0),
            "estimated_usd_year": round(usd_year, 0),
            "confidence":         0.70,
            "recommended_action": (
                f"Lower head-pressure target — system averaged {avg_excess:.1f}°F above "
                f"achievable condensing temp ({avg_achievable:.1f}°F) "
                f"over the last {lookback_hours:.0f} hours."
            ),
            "evidence": {
                "avg_sct_f":        round(avg_sct, 2),
                "avg_achievable_f": round(avg_achievable, 2),
                "avg_excess_f":     round(avg_excess, 2),
                "coef_pct_per_f":   COEF_PCT_PER_F,
                "penalty_fraction": round(penalty, 4),
                "condenser_type":   config.condenser_type,
                "ref_col":          ref_col,
                "buckets_analyzed": len(df),
            },
        },
        db=db,
    )
    logger.info(
        "excess_lift: system %s — excess %.1f°F → $%.0f/yr",
        system_id, avg_excess, usd_year,
    )
    return 1
