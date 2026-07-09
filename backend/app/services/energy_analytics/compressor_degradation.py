"""
Module 4.3 — Compressor Degradation / COP Drift (weekly, 30-day baseline)

Models expected compressor power from operating conditions (SST, SCT, lift)
using a linear regression fit on a clean 30-day baseline window. Then tracks
residuals in the most recent 7 days. Excess draw > 6% over baseline triggers
an opportunity with a dollar estimate.

Uses numpy least-squares (scipy is available but numpy is sufficient here).
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

import numpy as np

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

logger = logging.getLogger("kelvex.energy.compressor_degradation")

DEGRADATION_THRESHOLD = 0.06   # 6% excess before flagging
BASELINE_HOURS        = 720    # 30 days
RECENT_HOURS          = 168    # 7 days

METRICS = ["sst", "sct", "suction_pressure", "discharge_pressure", "compressor_power"]


async def run_compressor_degradation(
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
            logger.exception("compressor_degradation failed for system %s", system_id)

    return count


async def _analyze_system(
    facility_id: uuid.UUID,
    system_id: uuid.UUID,
    usd_per_kwh: float,
    now: datetime,
    db: AsyncSession,
) -> int:
    df_base = await get_system_telemetry(system_id, METRICS, BASELINE_HOURS, db)
    df_recent = await get_system_telemetry(system_id, METRICS, RECENT_HOURS, db)

    if df_base.empty or df_recent.empty:
        return 0

    required = {"compressor_power"}
    cond_col = "sct" if "sct" in df_base.columns else None
    suc_col  = "sst" if "sst" in df_base.columns else None

    if cond_col is None or suc_col is None:
        return 0  # can't build lift-based model without condensing/suction temps

    df_base   = df_base.dropna(subset=[cond_col, suc_col, "compressor_power"])
    df_recent = df_recent.dropna(subset=[cond_col, suc_col, "compressor_power"])

    if len(df_base) < 50 or len(df_recent) < 10:
        return 0  # insufficient data for reliable baseline

    # ── Fit baseline model: kW = f(sst, sct, lift) ────────────
    def _features(df):
        sst = df[suc_col].values
        sct = df[cond_col].values
        lift = sct - sst
        return np.column_stack([np.ones(len(sst)), sst, sct, lift])

    X_base = _features(df_base)
    y_base = df_base["compressor_power"].values

    try:
        coeffs, _, _, _ = np.linalg.lstsq(X_base, y_base, rcond=None)
    except np.linalg.LinAlgError:
        logger.debug("lstsq failed for system %s — skipping degradation", system_id)
        return 0

    resid_base = y_base - X_base @ coeffs
    resid_std  = float(resid_base.std())

    # ── Apply to recent window ────────────────────────────────
    X_recent  = _features(df_recent)
    predicted = X_recent @ coeffs
    actual    = df_recent["compressor_power"].values
    residuals = actual - predicted

    # Only count positive residuals (drawing more than expected)
    pos_resid = residuals[residuals > 0]
    if len(pos_resid) < 5:
        return 0

    mean_excess_kw = float(pos_resid.mean())
    mean_actual_kw = float(df_recent["compressor_power"].mean())
    if mean_actual_kw <= 0:
        return 0

    excess_frac = mean_excess_kw / mean_actual_kw
    if excess_frac < DEGRADATION_THRESHOLD:
        return 0

    runtime_hours = RECENT_HOURS  # assume continuous operation (conservative)
    kwh_year = mean_excess_kw * runtime_hours * (8760 / RECENT_HOURS)
    usd_year = kwh_year * usd_per_kwh
    confidence = min(excess_frac / 0.15, 1.0)  # full confidence at 15%+ excess

    window_start = now - timedelta(hours=RECENT_HOURS)

    await upsert_opportunity(
        facility_id=facility_id,
        system_id=system_id,
        opp_type="compressor_degradation",
        window_start=window_start,
        window_end=now,
        data={
            "current_value":      round(mean_actual_kw, 1),
            "target_value":       round(mean_actual_kw - mean_excess_kw, 1),
            "estimated_kwh_year": round(kwh_year, 0),
            "estimated_usd_year": round(usd_year, 0),
            "confidence":         round(confidence, 2),
            "recommended_action": (
                f"Compressor drawing ~{excess_frac*100:.0f}% above its 30-day baseline "
                f"at like conditions ({mean_excess_kw:.1f} kW excess). "
                f"Inspect valves, rings, oil, or refrigerant charge."
            ),
            "evidence": {
                "mean_actual_kw":     round(mean_actual_kw, 2),
                "mean_excess_kw":     round(mean_excess_kw, 2),
                "excess_fraction":    round(excess_frac, 4),
                "baseline_samples":   len(df_base),
                "recent_samples":     len(df_recent),
                "resid_std_baseline": round(resid_std, 2),
                "threshold_used":     DEGRADATION_THRESHOLD,
            },
        },
        db=db,
    )
    logger.info(
        "compressor_degradation: system %s — %.0f%% excess → $%.0f/yr",
        system_id, excess_frac * 100, usd_year,
    )
    return 1
