"""
Module 4.6 — Setpoint Drift (hourly)

Watches head_pressure_setpoint, suction_setpoint, and box_setpoint.
When a setpoint moves away from its established baseline and stays there,
raises an opportunity with the dollar cost of the gap.

This is the anti-backslide loop — highest-leverage recurring value because
settings get overridden (manual tweaks, power cycles, technician adjustments)
and never reverted. The loop re-creates value every time drift happens.
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

logger = logging.getLogger("kelvex.energy.setpoint_drift")

# Minimum delta to flag — below this is within normal variation
MIN_DRIFT_F      = 2.0    # °F (or equivalent pressure units)
MIN_DRIFT_PSI    = 2.0    # psig
MAX_PENALTY      = 0.25   # cap sanity check
COEF_PCT_PER_F   = 0.013  # same lift coefficient

# Metrics to monitor for drift
SETPOINT_METRICS = [
    "head_pressure_setpoint",
    "suction_setpoint",
    "box_setpoint",
    "compressor_power",
]

# Baseline window — use last 30 days to establish expected setpoints
BASELINE_HOURS = 720   # 30 days
RECENT_HOURS   = 4     # compare last 4 hours against baseline


async def run_setpoint_drift(
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
            logger.exception("setpoint_drift failed for system %s", system_id)

    return count


async def _analyze_system(
    facility_id: uuid.UUID,
    system_id: uuid.UUID,
    usd_per_kwh: float,
    now: datetime,
    db: AsyncSession,
) -> int:
    # Fetch baseline (30 days) and recent (4 hours) separately
    df_base = await get_system_telemetry(system_id, SETPOINT_METRICS, BASELINE_HOURS, db)
    df_recent = await get_system_telemetry(system_id, SETPOINT_METRICS, RECENT_HOURS, db)

    if df_base.empty or df_recent.empty:
        return 0

    count = 0
    window_start = now - timedelta(hours=RECENT_HOURS)

    for sp_col, threshold, sp_label in [
        ("head_pressure_setpoint", MIN_DRIFT_PSI, "head pressure setpoint"),
        ("suction_setpoint",       MIN_DRIFT_PSI, "suction setpoint"),
        ("box_setpoint",           MIN_DRIFT_F,   "box temperature setpoint"),
    ]:
        if sp_col not in df_base.columns or sp_col not in df_recent.columns:
            continue
        if df_base[sp_col].isna().all() or df_recent[sp_col].isna().all():
            continue

        baseline_val = float(df_base[sp_col].median())
        current_val  = float(df_recent[sp_col].median())
        delta = current_val - baseline_val

        if abs(delta) < threshold:
            continue

        # Translate setpoint delta to energy penalty using lift coefficient
        penalty = min(abs(delta) * COEF_PCT_PER_F, MAX_PENALTY)

        # Estimate baseline comp kWh from 30-day window
        if "compressor_power" in df_base.columns and not df_base["compressor_power"].isna().all():
            # Each bucket is 15 min → 0.25 hr; total kWh in baseline window
            comp_kwh_baseline = float(df_base["compressor_power"].sum()) * 0.25
            kwh_year, usd_year = annualize_usd(penalty, comp_kwh_baseline, BASELINE_HOURS, usd_per_kwh)
        else:
            # No power data — skip dollar estimate but still flag the drift
            kwh_year, usd_year = 0.0, 0.0

        direction = "above" if delta > 0 else "below"

        await upsert_opportunity(
            facility_id=facility_id,
            system_id=system_id,
            opp_type="setpoint_drift",
            window_start=window_start,
            window_end=now,
            data={
                "current_value":      round(current_val, 2),
                "target_value":       round(baseline_val, 2),
                "estimated_kwh_year": round(kwh_year, 0),
                "estimated_usd_year": round(usd_year, 0),
                "confidence":         0.80,
                "recommended_action": (
                    f"{sp_label.capitalize()} is {abs(delta):.1f} units {direction} "
                    f"its 30-day baseline ({baseline_val:.1f} → {current_val:.1f}). "
                    f"Review and revert if the change was unintentional."
                ),
                "evidence": {
                    "setpoint_metric":  sp_col,
                    "baseline_value":   round(baseline_val, 2),
                    "current_value":    round(current_val, 2),
                    "delta":            round(delta, 2),
                    "penalty_fraction": round(penalty, 4),
                    "baseline_days":    BASELINE_HOURS // 24,
                },
            },
            db=db,
        )
        logger.info(
            "setpoint_drift: system %s — %s drifted %.1f units → $%.0f/yr",
            system_id, sp_col, delta, usd_year,
        )
        count += 1

    return count
