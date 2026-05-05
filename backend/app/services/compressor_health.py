"""
Compressor Health Scoring & Anomaly Detection Engine

Computes a 0–100 health score for each compressor based on recent
telemetry readings. Detects anomalies by comparing readings against:
  1. Static alarm thresholds set on the compressor
  2. Statistical baselines (rolling averages + standard deviation)
  3. Rate-of-change indicators (sudden spikes)

The engine runs periodically via the background task system and can
also be triggered on-demand via the API.
"""

import asyncio
import logging
import math
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compressor import Compressor, CompressorReading
from app.models.alert import Alert

logger = logging.getLogger("coldgrid.compressor_health")

# Health score weights (must sum to 1.0)
WEIGHTS = {
    "discharge_pressure": 0.15,
    "suction_pressure": 0.10,
    "discharge_temp": 0.10,
    "oil_temp": 0.15,
    "bearing_temp": 0.20,
    "vibration": 0.15,
    "amp_draw": 0.10,
    "efficiency": 0.05,
}

# Default thresholds when not set on the compressor (for NH3 screw compressors)
DEFAULT_THRESHOLDS = {
    "discharge_psi_high": 250.0,    # ~185 psig typical, alarm at 250
    "suction_psi_low": 5.0,         # varies by temp, 5 psi is too low
    "oil_temp_high": 180.0,         # °F
    "bearing_temp_high": 200.0,     # °F
    "vibration_high": 0.3,          # in/s — ISO 10816 alert level
    "amp_draw_high_pct": 1.15,      # 115% of baseline
}

# Number of recent readings to use for baseline
BASELINE_WINDOW = 100


async def compute_health_score(
    compressor_id: UUID,
    db: AsyncSession,
    lookback_hours: int = 24,
) -> tuple[float | None, list[str]]:
    """
    Compute health score for a compressor based on recent readings.

    Returns:
        (score, anomalies) where score is 0–100 or None if insufficient data,
        and anomalies is a list of human-readable anomaly descriptions.
    """
    # Load compressor
    result = await db.execute(select(Compressor).where(Compressor.id == compressor_id))
    comp = result.scalar_one_or_none()
    if not comp:
        return None, ["Compressor not found"]

    # Load recent readings
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    result = await db.execute(
        select(CompressorReading)
        .where(
            CompressorReading.compressor_id == compressor_id,
            CompressorReading.recorded_at >= since,
        )
        .order_by(desc(CompressorReading.recorded_at))
        .limit(500)
    )
    readings = list(result.scalars().all())

    if len(readings) < 3:
        return None, ["Insufficient data — need at least 3 readings"]

    # Load baseline (older readings for statistical comparison)
    baseline_result = await db.execute(
        select(CompressorReading)
        .where(
            CompressorReading.compressor_id == compressor_id,
            CompressorReading.running == True,
        )
        .order_by(desc(CompressorReading.recorded_at))
        .limit(BASELINE_WINDOW)
    )
    baseline = list(baseline_result.scalars().all())

    anomalies: list[str] = []
    scores: dict[str, float] = {}

    # Only score readings where the compressor was running
    running_readings = [r for r in readings if r.running is True]
    if not running_readings:
        running_readings = readings  # fallback

    latest = readings[0]

    # ── Discharge pressure scoring ───────────────
    scores["discharge_pressure"] = _score_parameter(
        values=[r.discharge_pressure_psi for r in running_readings if r.discharge_pressure_psi is not None],
        baseline_values=[r.discharge_pressure_psi for r in baseline if r.discharge_pressure_psi is not None],
        alarm_high=comp.alarm_discharge_psi_high or DEFAULT_THRESHOLDS["discharge_psi_high"],
        label="Discharge pressure",
        unit="psi",
        anomalies=anomalies,
        higher_is_worse=True,
    )

    # ── Suction pressure scoring ─────────────────
    scores["suction_pressure"] = _score_parameter(
        values=[r.suction_pressure_psi for r in running_readings if r.suction_pressure_psi is not None],
        baseline_values=[r.suction_pressure_psi for r in baseline if r.suction_pressure_psi is not None],
        alarm_low=comp.alarm_suction_psi_low or DEFAULT_THRESHOLDS["suction_psi_low"],
        label="Suction pressure",
        unit="psi",
        anomalies=anomalies,
        higher_is_worse=False,
    )

    # ── Discharge temp scoring ───────────────────
    scores["discharge_temp"] = _score_parameter(
        values=[r.discharge_temp_f for r in running_readings if r.discharge_temp_f is not None],
        baseline_values=[r.discharge_temp_f for r in baseline if r.discharge_temp_f is not None],
        alarm_high=comp.max_discharge_temp_f or 300.0,
        label="Discharge temp",
        unit="°F",
        anomalies=anomalies,
        higher_is_worse=True,
    )

    # ── Oil temperature scoring ──────────────────
    scores["oil_temp"] = _score_parameter(
        values=[r.oil_temp_f for r in running_readings if r.oil_temp_f is not None],
        baseline_values=[r.oil_temp_f for r in baseline if r.oil_temp_f is not None],
        alarm_high=comp.alarm_oil_temp_high or DEFAULT_THRESHOLDS["oil_temp_high"],
        label="Oil temp",
        unit="°F",
        anomalies=anomalies,
        higher_is_worse=True,
    )

    # ── Bearing temperature scoring ──────────────
    scores["bearing_temp"] = _score_parameter(
        values=[r.bearing_temp_f for r in running_readings if r.bearing_temp_f is not None],
        baseline_values=[r.bearing_temp_f for r in baseline if r.bearing_temp_f is not None],
        alarm_high=comp.alarm_bearing_temp_high or DEFAULT_THRESHOLDS["bearing_temp_high"],
        label="Bearing temp",
        unit="°F",
        anomalies=anomalies,
        higher_is_worse=True,
    )

    # ── Vibration scoring ────────────────────────
    scores["vibration"] = _score_parameter(
        values=[r.vibration_ips for r in running_readings if r.vibration_ips is not None],
        baseline_values=[r.vibration_ips for r in baseline if r.vibration_ips is not None],
        alarm_high=comp.alarm_vibration_high or DEFAULT_THRESHOLDS["vibration_high"],
        label="Vibration",
        unit="in/s",
        anomalies=anomalies,
        higher_is_worse=True,
    )

    # ── Amp draw scoring ─────────────────────────
    scores["amp_draw"] = _score_parameter(
        values=[r.amp_draw for r in running_readings if r.amp_draw is not None],
        baseline_values=[r.amp_draw for r in baseline if r.amp_draw is not None],
        alarm_high=comp.alarm_amp_draw_high,  # may be None — will use baseline
        label="Amp draw",
        unit="A",
        anomalies=anomalies,
        higher_is_worse=True,
    )

    # ── Efficiency scoring ───────────────────────
    eff_values = [r.efficiency_pct for r in running_readings if r.efficiency_pct is not None]
    if eff_values:
        avg_eff = sum(eff_values) / len(eff_values)
        # Lower kW/ton is better — invert score
        scores["efficiency"] = min(100.0, max(0.0, avg_eff))
    else:
        scores["efficiency"] = 100.0  # no data = no penalty

    # ── Weighted composite score ─────────────────
    total_score = 0.0
    total_weight = 0.0
    for key, weight in WEIGHTS.items():
        if key in scores:
            total_score += scores[key] * weight
            total_weight += weight

    final_score = round(total_score / total_weight, 1) if total_weight > 0 else None

    # ── Rate of change anomalies ─────────────────
    if len(running_readings) >= 5:
        _check_rate_of_change(running_readings[:10], anomalies)

    return final_score, anomalies


def _score_parameter(
    values: list[float],
    baseline_values: list[float],
    label: str,
    unit: str,
    anomalies: list[str],
    higher_is_worse: bool,
    alarm_high: float | None = None,
    alarm_low: float | None = None,
) -> float:
    """
    Score a single parameter 0–100.

    Uses alarm thresholds + statistical deviation from baseline.
    """
    if not values:
        return 100.0  # no data = no penalty

    current_avg = sum(values[-5:]) / min(len(values), 5)  # recent average

    # Threshold-based scoring
    if higher_is_worse and alarm_high:
        # Score = how far from alarm threshold (100 = well below, 0 = at/above)
        margin = alarm_high - current_avg
        range_width = alarm_high * 0.3  # 30% of threshold as scoring range
        threshold_score = max(0.0, min(100.0, (margin / range_width) * 100)) if range_width > 0 else 100.0
    elif not higher_is_worse and alarm_low is not None:
        margin = current_avg - alarm_low
        range_width = alarm_low * 0.5 if alarm_low > 0 else 10.0
        threshold_score = max(0.0, min(100.0, (margin / range_width) * 100)) if range_width > 0 else 100.0
    else:
        threshold_score = 100.0

    # Statistical deviation scoring
    if len(baseline_values) >= 10:
        bl_mean = sum(baseline_values) / len(baseline_values)
        bl_std = _std(baseline_values, bl_mean)
        if bl_std > 0:
            z_score = abs(current_avg - bl_mean) / bl_std
            stat_score = max(0.0, 100.0 - (z_score * 20.0))  # 5 sigma = 0
            if z_score > 2.5:
                direction = "above" if current_avg > bl_mean else "below"
                anomalies.append(
                    f"{label} {direction} baseline: {current_avg:.1f} {unit} "
                    f"(baseline: {bl_mean:.1f} ± {bl_std:.1f})"
                )
        else:
            stat_score = 100.0
    else:
        stat_score = 100.0

    # Blend: 60% threshold, 40% statistical
    combined = threshold_score * 0.6 + stat_score * 0.4

    # Flag threshold breaches
    if higher_is_worse and alarm_high and current_avg > alarm_high:
        anomalies.append(f"{label} exceeds alarm: {current_avg:.1f} {unit} > {alarm_high:.1f} {unit}")
    if not higher_is_worse and alarm_low is not None and current_avg < alarm_low:
        anomalies.append(f"{label} below alarm: {current_avg:.1f} {unit} < {alarm_low:.1f} {unit}")

    return round(combined, 1)


def _std(values: list[float], mean: float) -> float:
    """Standard deviation."""
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _check_rate_of_change(readings: list[CompressorReading], anomalies: list[str]):
    """
    Detect sudden spikes in key parameters over recent readings.
    """
    params = [
        ("bearing_temp_f", "Bearing temp", "°F", 15.0),   # 15°F spike
        ("vibration_ips", "Vibration", "in/s", 0.1),       # 0.1 in/s spike
        ("discharge_pressure_psi", "Discharge pressure", "psi", 30.0),  # 30 psi spike
        ("oil_temp_f", "Oil temp", "°F", 20.0),            # 20°F spike
    ]

    for attr, label, unit, spike_threshold in params:
        values = [(getattr(r, attr), r.recorded_at) for r in readings if getattr(r, attr) is not None]
        if len(values) >= 2:
            newest_val = values[0][0]
            oldest_val = values[-1][0]
            delta = newest_val - oldest_val
            if abs(delta) > spike_threshold:
                direction = "spike" if delta > 0 else "drop"
                anomalies.append(
                    f"Rapid {label} {direction}: {delta:+.1f} {unit} over last {len(values)} readings"
                )


# ── Background Engine ────────────────────────────

_task: asyncio.Task | None = None


async def start_compressor_health_engine(session_factory):
    """Start the periodic health scoring background loop."""
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_health_loop(session_factory))
    logger.info("Compressor health engine started")


async def stop_compressor_health_engine():
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None


async def _health_loop(session_factory):
    """Run health checks every 5 minutes."""
    while True:
        try:
            async with session_factory() as db:
                # Get all compressors that have recent readings
                cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
                result = await db.execute(
                    select(Compressor).where(
                        Compressor.last_reading_at >= cutoff,
                    )
                )
                compressors = list(result.scalars().all())

                for comp in compressors:
                    try:
                        score, anomalies = await compute_health_score(comp.id, db)
                        if score is not None:
                            comp.health_score = score
                            # Auto-set alarm state if score is critically low
                            if score < 40 and comp.state not in ("maintenance", "offline"):
                                comp.state = "alarm"
                                # Create alert for critical health
                                await _create_health_alert(comp, score, anomalies, db)
                            elif score >= 70 and comp.state == "alarm":
                                comp.state = "running"  # auto-recover
                    except Exception as e:
                        logger.warning(f"Health check failed for {comp.name}: {e}")

                await db.commit()
                logger.debug(f"Health check complete for {len(compressors)} compressors")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Compressor health engine error: {e}")

        await asyncio.sleep(300)  # 5 minutes


async def _create_health_alert(
    comp: Compressor,
    score: float,
    anomalies: list[str],
    db: AsyncSession,
):
    """Create an alert when compressor health drops critically."""
    # Check if there's already an active alert for this compressor.
    # trigger_value stores the compressor UUID as the stable dedup key.
    result = await db.execute(
        select(Alert).where(
            Alert.facility_id == comp.facility_id,
            Alert.alert_type == "compressor_health",
            Alert.trigger_value == str(comp.id),
            Alert.state == "active",
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return  # don't spam alerts

    alert = Alert(
        facility_id=comp.facility_id,
        equipment_id=None,  # Compressors are not in the equipment table
        severity="critical" if score < 25 else "high",
        category="equipment",
        alert_type="compressor_health",
        title=f"{comp.name} health critical: {score}/100",
        message=f"Compressor health score dropped to {score}/100. Anomalies: {'; '.join(anomalies[:5])}",
        state="active",
        trigger_value=str(comp.id),
        threshold_value="40",
        context={"compressor_id": str(comp.id), "anomalies": anomalies, "health_score": score},
    )
    db.add(alert)
