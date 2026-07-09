"""
Module 4.5 — Charge Anomaly (daily)

Shared signal with leak detection:
  superheat  = suction_temp − SST   (dew-point saturation temp at suction pressure)
  subcooling = SCT − liquid_temp    (bubble-point saturation temp at cond pressure)

Undercharge / developing leak:
  Rising superheat + falling capacity → charge loss, ~15–25% capacity penalty.

Overcharge:
  High subcooling + high discharge temp → liquid flood-back risk, power +10–20%.

Emits `charge_anomaly` opportunity AND sets a flag in evidence for the
leak-detection module to pick up.
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
from app.services.energy_analytics.thermo import sat_temp_f

logger = logging.getLogger("kelvex.energy.charge_anomaly")

BASELINE_HOURS = 720   # 30 days
RECENT_HOURS   = 24    # today

# Thresholds
MIN_SUPERHEAT_F     = 8.0    # below this is flood-back risk
TARGET_SUPERHEAT_F  = 10.0   # ideal: 8–12°F
HIGH_SUPERHEAT_F    = 20.0   # above this → undercharge / leak signal
HIGH_SUBCOOLING_F   = 20.0   # above this → overcharge signal
MIN_SUBCOOLING_F    = 5.0    # minimum healthy subcooling

UNDERCHARGE_PENALTY = 0.18   # 18% capacity loss proxy → proportional power increase
OVERCHARGE_PENALTY  = 0.12   # 12% power increase

METRICS = [
    "sst", "sct",
    "suction_temp",     # actual suction line temp (superheat source)
    "liquid_temp",      # liquid line temp (subcooling source)
    "suction_pressure",
    "discharge_pressure",
    "compressor_power",
    "discharge_temp",
]


async def run_charge_anomaly(
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
            logger.exception("charge_anomaly failed for system %s", system_id)

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

    # ── Compute superheat and subcooling ────────────────────────
    df_base   = _add_sh_sc(df_base, config.refrigerant)
    df_recent = _add_sh_sc(df_recent, config.refrigerant)

    if df_recent.empty:
        return 0

    # Check if we have enough signal
    has_sh = "superheat_f" in df_recent.columns and not df_recent["superheat_f"].isna().all()
    has_sc = "subcooling_f" in df_recent.columns and not df_recent["subcooling_f"].isna().all()

    if not has_sh and not has_sc:
        return 0

    count = 0
    window_start = now - timedelta(hours=RECENT_HOURS)

    # ── UNDERCHARGE / LEAK SIGNAL ───────────────────────────────
    if has_sh:
        sh_recent = float(df_recent["superheat_f"].dropna().mean())
        sh_base   = float(df_base["superheat_f"].dropna().mean()) if not df_base.empty and "superheat_f" in df_base.columns else None

        # Rising superheat trend within recent window
        sh_series = df_recent["superheat_f"].dropna().values
        sh_trend  = 0.0
        if len(sh_series) >= 4:
            sh_trend = float(np.polyfit(range(len(sh_series)), sh_series, 1)[0])

        undercharge = sh_recent > HIGH_SUPERHEAT_F or (sh_base is not None and sh_recent > sh_base + 5.0)

        if undercharge:
            comp_kwh_day = _comp_kwh(df_recent)
            kwh_year, usd_year = annualize_usd(UNDERCHARGE_PENALTY, comp_kwh_day, RECENT_HOURS, usd_per_kwh)

            # Rising trend in superheat is a stronger leak signal
            leak_signal = sh_trend > 0.5 or sh_recent > HIGH_SUPERHEAT_F + 5

            await upsert_opportunity(
                facility_id=facility_id,
                system_id=system_id,
                opp_type="charge_anomaly",
                window_start=window_start,
                window_end=now,
                data={
                    "current_value":      round(sh_recent, 1),
                    "target_value":       round(TARGET_SUPERHEAT_F, 1),
                    "estimated_kwh_year": round(kwh_year, 0),
                    "estimated_usd_year": round(usd_year, 0),
                    "confidence":         0.70,
                    "recommended_action": (
                        f"Superheat averaging {sh_recent:.1f}°F — elevated above normal "
                        f"({TARGET_SUPERHEAT_F:.0f}°F target). "
                        f"Check refrigerant charge and inspect for developing leak."
                    ),
                    "evidence": {
                        "anomaly_type":        "undercharge",
                        "superheat_recent_f":  round(sh_recent, 2),
                        "superheat_base_f":    round(sh_base, 2) if sh_base else None,
                        "superheat_trend":     round(sh_trend, 3),
                        "high_superheat_threshold_f": HIGH_SUPERHEAT_F,
                        "leak_signal":         leak_signal,
                        "refrigerant":         config.refrigerant,
                        "penalty_fraction":    UNDERCHARGE_PENALTY,
                    },
                },
                db=db,
            )
            logger.info(
                "charge_anomaly (undercharge): system %s — SH %.1f°F → $%.0f/yr (leak_signal=%s)",
                system_id, sh_recent, usd_year, leak_signal,
            )
            count += 1

    # ── OVERCHARGE SIGNAL ────────────────────────────────────────
    if has_sc:
        sc_recent = float(df_recent["subcooling_f"].dropna().mean())

        if sc_recent > HIGH_SUBCOOLING_F:
            comp_kwh_day = _comp_kwh(df_recent)
            kwh_year, usd_year = annualize_usd(OVERCHARGE_PENALTY, comp_kwh_day, RECENT_HOURS, usd_per_kwh)

            # High discharge temp adds confidence to overcharge (liquid slugging → motor heat)
            disc_temp_high = False
            if "discharge_temp" in df_recent.columns:
                dt_mean = float(df_recent["discharge_temp"].dropna().mean())
                disc_temp_high = dt_mean > 220.0  # °F threshold for discharge temp alarm

            await upsert_opportunity(
                facility_id=facility_id,
                system_id=system_id,
                opp_type="charge_anomaly",
                window_start=window_start,
                window_end=now,
                data={
                    "current_value":      round(sc_recent, 1),
                    "target_value":       round(10.0, 1),   # target ~10°F subcooling
                    "estimated_kwh_year": round(kwh_year, 0),
                    "estimated_usd_year": round(usd_year, 0),
                    "confidence":         0.65,
                    "recommended_action": (
                        f"Subcooling averaging {sc_recent:.1f}°F — above normal range "
                        f"(target 8–15°F). System may be overcharged; "
                        f"reclaim excess refrigerant and recheck charge."
                    ),
                    "evidence": {
                        "anomaly_type":           "overcharge",
                        "subcooling_recent_f":    round(sc_recent, 2),
                        "high_subcooling_threshold_f": HIGH_SUBCOOLING_F,
                        "discharge_temp_elevated": disc_temp_high,
                        "refrigerant":            config.refrigerant,
                        "penalty_fraction":       OVERCHARGE_PENALTY,
                    },
                },
                db=db,
            )
            logger.info(
                "charge_anomaly (overcharge): system %s — SC %.1f°F → $%.0f/yr",
                system_id, sc_recent, usd_year,
            )
            count += 1

    return count


def _add_sh_sc(df, refrigerant: str):
    """Add superheat_f and subcooling_f columns where possible."""
    if df.empty:
        return df

    df = df.copy()

    # Superheat: prefer direct measurement; fall back to pressure conversion
    if "suction_temp" in df.columns and "sst" in df.columns:
        df["superheat_f"] = df["suction_temp"] - df["sst"]
    elif "suction_temp" in df.columns and "suction_pressure" in df.columns:
        def row_sst(row):
            try:
                return sat_temp_f(refrigerant, float(row["suction_pressure"]), quality=1)
            except Exception:
                return None
        df["sst_calc"]    = df.apply(row_sst, axis=1)
        df["superheat_f"] = df["suction_temp"] - df["sst_calc"]

    # Subcooling: prefer direct measurement; fall back to pressure conversion
    if "liquid_temp" in df.columns and "sct" in df.columns:
        df["subcooling_f"] = df["sct"] - df["liquid_temp"]
    elif "liquid_temp" in df.columns and "discharge_pressure" in df.columns:
        def row_sct(row):
            try:
                return sat_temp_f(refrigerant, float(row["discharge_pressure"]), quality=0)
            except Exception:
                return None
        df["sct_calc"]     = df.apply(row_sct, axis=1)
        df["subcooling_f"] = df["sct_calc"] - df["liquid_temp"]

    # Clamp to plausible range — bad sensors show ±100°F noise
    for col in ("superheat_f", "subcooling_f"):
        if col in df.columns:
            df[col] = df[col].where(df[col].between(-5, 80))

    return df


def _comp_kwh(df) -> float:
    if "compressor_power" in df.columns:
        return float(df["compressor_power"].sum()) * 0.25  # 15-min buckets
    return 0.0
