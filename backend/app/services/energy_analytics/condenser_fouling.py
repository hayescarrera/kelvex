"""
Module 4.4 — Condenser Fouling (daily)

Approach temp = SCT − ambient reference (wet-bulb for evaporative, dry-bulb for air-cooled).
Baseline the clean approach over 30 days; a rising approach at constant load/fan speed
indicates fouling which forces higher head pressure and compressor penalty.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.system import System
from app.services.energy_analytics.runner import (
    annualize_usd,
    get_facility_rate,
    get_energy_config,
    get_system_telemetry,
    upsert_opportunity,
)

logger = logging.getLogger("kelvex.energy.condenser_fouling")

APPROACH_ALERT_RISE_F = 3.0   # °F rise over clean baseline before flagging
COEF_PCT_PER_F        = 0.013 # same lift coefficient — extra approach = extra head
MAX_PENALTY           = 0.20

METRICS = ["sct", "ambient_wet_bulb", "ambient_dry_bulb", "compressor_power"]
BASELINE_HOURS = 720   # 30 days
RECENT_HOURS   = 24    # today


async def run_condenser_fouling(
    facility_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    usd_per_kwh = await get_facility_rate(facility_id, db)

    result = await db.execute(select(System.id).where(System.facility_id == facility_id))
    system_ids = [row[0] for row in result.fetchall()]

    count = 0
    now = datetime.now(timezone.utc)

    for system_id in system_ids:
        try:
            n = await _analyze_system(facility_id, system_id, usd_per_kwh, now, db)
            count += n
        except Exception:
            logger.exception("condenser_fouling failed for system %s", system_id)

    return count


async def _analyze_system(
    facility_id: uuid.UUID,
    system_id: uuid.UUID,
    usd_per_kwh: float,
    now: datetime,
    db: AsyncSession,
) -> int:
    config = await get_energy_config(system_id, db)

    df_base   = await get_system_telemetry(system_id, METRICS, BASELINE_HOURS, db)
    df_recent = await get_system_telemetry(system_id, METRICS, RECENT_HOURS, db)

    if df_base.empty or df_recent.empty:
        return 0
    if "sct" not in df_base.columns:
        return 0

    ref_col = _ref_col(config.condenser_type, df_base)
    if ref_col is None:
        return 0

    df_base   = df_base.dropna(subset=["sct", ref_col])
    df_recent = df_recent.dropna(subset=["sct", ref_col])

    if df_base.empty or df_recent.empty:
        return 0

    approach_baseline = float((df_base["sct"] - df_base[ref_col]).mean())
    approach_now      = float((df_recent["sct"] - df_recent[ref_col]).mean())
    rise = approach_now - approach_baseline

    if rise < APPROACH_ALERT_RISE_F:
        return 0

    penalty = min(rise * COEF_PCT_PER_F, MAX_PENALTY)

    comp_kwh_day = 0.0
    if "compressor_power" in df_recent.columns:
        comp_kwh_day = float(df_recent["compressor_power"].sum()) * 0.25

    kwh_year, usd_year = annualize_usd(penalty, comp_kwh_day, RECENT_HOURS, usd_per_kwh)

    window_start = now - timedelta(hours=RECENT_HOURS)

    await upsert_opportunity(
        facility_id=facility_id,
        system_id=system_id,
        opp_type="condenser_fouling",
        window_start=window_start,
        window_end=now,
        data={
            "current_value":      round(approach_now, 1),
            "target_value":       round(approach_baseline, 1),
            "estimated_kwh_year": round(kwh_year, 0),
            "estimated_usd_year": round(usd_year, 0),
            "confidence":         0.65,
            "recommended_action": (
                f"Condenser approach up {rise:.1f}°F vs clean baseline "
                f"({approach_baseline:.1f}°F → {approach_now:.1f}°F). "
                f"Schedule condenser cleaning and inspect fan operation."
            ),
            "evidence": {
                "approach_baseline_f":  round(approach_baseline, 2),
                "approach_now_f":       round(approach_now, 2),
                "rise_f":               round(rise, 2),
                "condenser_type":       config.condenser_type,
                "ref_col":              ref_col,
                "alert_threshold_f":    APPROACH_ALERT_RISE_F,
            },
        },
        db=db,
    )
    logger.info(
        "condenser_fouling: system %s — approach +%.1f°F → $%.0f/yr",
        system_id, rise, usd_year,
    )
    return 1


def _ref_col(condenser_type: str, df) -> str | None:
    if condenser_type == "evaporative" and "ambient_wet_bulb" in df.columns:
        return "ambient_wet_bulb"
    if "ambient_dry_bulb" in df.columns:
        return "ambient_dry_bulb"
    return None
