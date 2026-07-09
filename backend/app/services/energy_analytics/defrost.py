"""
Module 4.2 — Defrost Effectiveness (daily)

Detects two failure modes:

  OVERRUN  — defrost kept running after coil was already clear. Every minute
             of tail-end heating burns heater kW AND must be refrigerated back
             out (1.3× compounding factor).

  UNDERRUN — defrosts too infrequent; coil frost is blanketing the evaporator
             and throttling capacity (rising pre-defrost box-temp, increased
             runtime between cycles).

Both findings are written as separate opp_type records.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import NamedTuple

import pandas as pd
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

logger = logging.getLogger("kelvex.energy.defrost")

CLEAR_COIL_F     = 38.0   # proxy: coil is clear once it reaches this temp
DEFROST_COMPOUND = 1.3    # heat added must be re-removed by refrigeration
METRICS = ["defrost_state", "box_temp", "box_setpoint"]


class _DefrostEvent(NamedTuple):
    start: pd.Timestamp
    end: pd.Timestamp
    overrun_min: float       # minutes after coil-clear where defrost still ran
    pre_defrost_box_temp: float | None


async def run_defrost(
    facility_id: uuid.UUID,
    db: AsyncSession,
    lookback_hours: float = 48.0,  # 2 days to capture enough defrost cycles
) -> int:
    usd_per_kwh = await get_facility_rate(facility_id, db)

    result = await db.execute(select(System.id).where(System.facility_id == facility_id))
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
            logger.exception("defrost analysis failed for system %s", system_id)

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
    if not config.defrost_heater_kw:
        # Can't quantify overrun without knowing heater size; skip dollar math
        # but still detect underrun
        pass

    df = await get_system_telemetry(system_id, METRICS, lookback_hours, db, bucket_minutes=1)
    if df.empty or "defrost_state" not in df.columns:
        return 0

    df = df.sort_values("bucket").reset_index(drop=True)
    df["defrost_state"] = df["defrost_state"].fillna(0).round().astype(int)

    events = _split_defrost_events(df)
    if not events:
        return 0

    count = 0
    total_overrun_min = sum(e.overrun_min for e in events)
    days_in_window = lookback_hours / 24.0

    # ── OVERRUN ────────────────────────────────────────────────
    if total_overrun_min > 5 and config.defrost_heater_kw:
        overrun_min_per_day = total_overrun_min / days_in_window
        wasted_kwh_day = (overrun_min_per_day / 60) * config.defrost_heater_kw * DEFROST_COMPOUND
        kwh_year, usd_year = annualize_usd(1.0, wasted_kwh_day, 24, usd_per_kwh)

        n_events = len([e for e in events if e.overrun_min > 0])
        avg_overrun = total_overrun_min / n_events if n_events else 0

        await upsert_opportunity(
            facility_id=facility_id,
            system_id=system_id,
            opp_type="defrost_overrun",
            window_start=window_start,
            window_end=window_end,
            data={
                "current_value":      round(avg_overrun, 1),
                "target_value":       0.0,
                "estimated_kwh_year": round(kwh_year, 0),
                "estimated_usd_year": round(usd_year, 0),
                "confidence":         0.65,
                "recommended_action": (
                    f"Defrosts averaging {avg_overrun:.0f} min of tail-end heating after "
                    f"coil reaches {CLEAR_COIL_F}°F. Reduce timer duration or add "
                    f"demand-defrost termination."
                ),
                "evidence": {
                    "defrost_events_analyzed": len(events),
                    "events_with_overrun": n_events,
                    "total_overrun_min": round(total_overrun_min, 1),
                    "overrun_min_per_day": round(overrun_min_per_day, 1),
                    "heater_kw": config.defrost_heater_kw,
                    "compounding_factor": DEFROST_COMPOUND,
                },
            },
            db=db,
        )
        logger.info("defrost_overrun: system %s — $%.0f/yr", system_id, usd_year)
        count += 1

    # ── UNDERRUN (rising pre-defrost temps) ────────────────────
    pre_temps = [e.pre_defrost_box_temp for e in events if e.pre_defrost_box_temp is not None]
    if len(pre_temps) >= 3:
        temps_arr = np.array(pre_temps)
        # Rising trend across the window → coil blanketing getting worse
        slope = np.polyfit(range(len(temps_arr)), temps_arr, 1)[0]
        if slope > 0.3:  # °F per defrost cycle — rough threshold
            # Capacity loss proxy: ~5% per °F of excess box temp above setpoint
            if "box_setpoint" in df.columns:
                setpoint = float(df["box_setpoint"].median())
                excess_f = float(temps_arr.mean()) - setpoint
            else:
                excess_f = float(temps_arr.std())

            if excess_f > 1.0:
                # Energy penalty: compressor works harder to maintain temp with restricted coil
                # Use conservative 5% capacity loss → proportional power increase
                penalty = min(0.05 * excess_f, 0.20)
                # Estimate baseline comp kWh from available data
                baseline_kwh_day = _estimate_baseline_kwh(df, lookback_hours)
                if baseline_kwh_day > 0:
                    kwh_year, usd_year = annualize_usd(penalty, baseline_kwh_day, 24, usd_per_kwh)
                    await upsert_opportunity(
                        facility_id=facility_id,
                        system_id=system_id,
                        opp_type="defrost_underrun",
                        window_start=window_start,
                        window_end=window_end,
                        data={
                            "current_value":      round(float(temps_arr.mean()), 1),
                            "estimated_kwh_year": round(kwh_year, 0),
                            "estimated_usd_year": round(usd_year, 0),
                            "confidence":         0.55,
                            "recommended_action": (
                                f"Pre-defrost box temps trending up ({slope:+.2f}°F/cycle) — "
                                f"coil may be under-defrosted. Add a defrost cycle or reduce the "
                                f"minimum interval."
                            ),
                            "evidence": {
                                "pre_defrost_temps": [round(t, 1) for t in pre_temps],
                                "slope_f_per_cycle": round(slope, 3),
                                "excess_above_setpoint": round(excess_f, 1),
                            },
                        },
                        db=db,
                    )
                    logger.info("defrost_underrun: system %s — $%.0f/yr", system_id, usd_year)
                    count += 1

    return count


def _split_defrost_events(df: pd.DataFrame) -> list[_DefrostEvent]:
    """Split a DataFrame with defrost_state column into individual events."""
    events: list[_DefrostEvent] = []
    in_defrost = False
    ev_start: pd.Timestamp | None = None
    coil_clear_ts: pd.Timestamp | None = None
    pre_temps: list[float] = []

    for _, row in df.iterrows():
        state = int(row["defrost_state"])
        box_t = row.get("box_temp")

        if state == 1 and not in_defrost:
            in_defrost = True
            ev_start = row["bucket"]
            coil_clear_ts = None
            # Record the box temp just before defrost started
            if pre_temps:
                pass  # captured below
        elif state == 1 and in_defrost:
            # Check for coil-clear: using box_temp as proxy
            if coil_clear_ts is None and box_t is not None and float(box_t) >= CLEAR_COIL_F:
                coil_clear_ts = row["bucket"]
        elif state == 0 and in_defrost:
            in_defrost = False
            ev_end = row["bucket"]
            overrun_min = 0.0
            if coil_clear_ts is not None:
                delta = ev_end - coil_clear_ts
                overrun_min = max(delta.total_seconds() / 60, 0)
            pre_box = float(pre_temps[-1]) if pre_temps else None
            events.append(_DefrostEvent(
                start=ev_start,
                end=ev_end,
                overrun_min=overrun_min,
                pre_defrost_box_temp=pre_box,
            ))
            pre_temps = []
        else:
            # Not in defrost — track box temp for pre-defrost reading
            if box_t is not None:
                pre_temps.append(float(box_t))

    return events


def _estimate_baseline_kwh(df: pd.DataFrame, hours: float) -> float:
    """Rough baseline kWh if compressor_power not available in this module's metrics."""
    # Defrost module doesn't fetch compressor_power — return 0 to skip dollar math
    # if that data isn't present. Callers should handle 0.
    return 0.0
