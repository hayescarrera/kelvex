"""
Leak Detection Engine — pure sync Python.

All functions are importable without any async or DB dependencies.
Callers are responsible for fetching data from the database; these
functions only perform the statistical analysis.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


# ── EWMA ─────────────────────────────────────────────────────────────────────

def compute_ewma(values: list[float], alpha: float = 0.15) -> list[float]:
    """
    Exponentially weighted moving average.

    Returns a same-length list. The first element equals the first input value
    (initialised from data, not from zero). Subsequent elements are:
        ewma[i] = alpha * values[i] + (1 - alpha) * ewma[i-1]
    """
    if not values:
        return []
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1.0 - alpha) * result[-1])
    return result


# ── Pressure drift detection ──────────────────────────────────────────────────

def detect_pressure_drift(
    hourly_pressures: list[float],
    design_suction_psi: Optional[float],
    window_hours: int = 72,
) -> dict:
    """
    EWMA + threshold check on suction pressure trend.

    Parameters
    ----------
    hourly_pressures:
        Ordered oldest→newest hourly average suction pressure (psi).
    design_suction_psi:
        Nominal design suction pressure for the rack (optional).
    window_hours:
        How many recent hours to use for the analysis window.

    Returns
    -------
    dict with keys:
        detected, severity, drift_pct, confidence, details
    """
    _default = {
        "detected": False,
        "severity": "none",
        "drift_pct": 0.0,
        "confidence": "suspected",
        "details": "Insufficient pressure data for analysis.",
    }

    window = hourly_pressures[-window_hours:] if len(hourly_pressures) >= window_hours else hourly_pressures

    # Need at least a few points to form a meaningful baseline
    if len(window) < 6:
        return _default

    ewma_vals = compute_ewma(window, alpha=0.15)

    # Baseline = average of the first third of the EWMA series
    third = max(1, len(ewma_vals) // 3)
    baseline = float(np.mean(ewma_vals[:third]))
    current = ewma_vals[-1]

    if baseline <= 0:
        return {**_default, "details": "Baseline pressure is zero or negative; cannot compute drift."}

    drift_pct = (baseline - current) / baseline * 100.0  # positive = pressure dropped

    # Design threshold check
    design_flag = False
    design_msg = ""
    if design_suction_psi is not None and design_suction_psi > 0:
        if current < design_suction_psi * 0.80:
            design_flag = True
            design_msg = (
                f" Current EWMA ({current:.1f} psi) is below 80% of design "
                f"({design_suction_psi:.1f} psi)."
            )

    if drift_pct > 15 or (design_flag and drift_pct > 10):
        severity = "severe"
        confidence = "confirmed"
        detected = True
    elif drift_pct > 10 or design_flag:
        severity = "moderate"
        confidence = "likely"
        detected = True
    elif drift_pct > 5:
        severity = "mild"
        confidence = "suspected"
        detected = True
    else:
        severity = "none"
        confidence = "suspected"
        detected = False

    details = (
        f"Suction pressure EWMA baseline: {baseline:.1f} psi, "
        f"current: {current:.1f} psi, drift: {drift_pct:.1f}%.{design_msg}"
    )

    return {
        "detected": detected,
        "severity": severity,
        "drift_pct": round(drift_pct, 2),
        "confidence": confidence,
        "details": details,
    }


# ── Superheat rise detection ──────────────────────────────────────────────────

def detect_superheat_rise(
    hourly_superheat: list[float],
    window_hours: int = 48,
) -> dict:
    """
    EWMA on superheat. Flags if superheat rises > 4°F from baseline over window.

    Returns
    -------
    dict with keys: detected, rise_f, details
    """
    _default = {"detected": False, "rise_f": 0.0, "details": "Insufficient superheat data."}

    window = hourly_superheat[-window_hours:] if len(hourly_superheat) >= window_hours else hourly_superheat

    if len(window) < 6:
        return _default

    ewma_vals = compute_ewma(window, alpha=0.15)

    third = max(1, len(ewma_vals) // 3)
    baseline = float(np.mean(ewma_vals[:third]))
    current = ewma_vals[-1]

    rise_f = current - baseline  # positive = superheat went up

    detected = rise_f > 4.0
    details = (
        f"Superheat EWMA baseline: {baseline:.1f}°F, current: {current:.1f}°F, "
        f"rise: {rise_f:.1f}°F (threshold: 4°F)."
    )

    return {
        "detected": detected,
        "rise_f": round(rise_f, 2),
        "details": details,
    }


# ── Add-pattern anomaly detection ────────────────────────────────────────────

def detect_add_pattern_anomaly(
    add_timestamps: list[datetime],
    add_amounts: list[float],
    lookback_days: int = 365,
) -> dict:
    """
    Poisson rate test on add frequency + Mann-Whitney U on inter-add intervals.

    Parameters
    ----------
    add_timestamps:
        Historical add timestamps ordered oldest→newest.
    add_amounts:
        Corresponding amounts in lbs (same length).
    lookback_days:
        Full historical window to consider.

    Returns
    -------
    dict with keys:
        detected, method, p_value, current_rate_per_30d, baseline_rate_per_30d, details
    """
    _default = {
        "detected": False,
        "method": "insufficient_data",
        "p_value": None,
        "current_rate_per_30d": 0.0,
        "baseline_rate_per_30d": 0.0,
        "details": "Insufficient refrigerant add history.",
    }

    if len(add_timestamps) < 2:
        return _default

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)

    # Ensure timestamps are tz-aware for comparison
    def _ensure_aware(ts: datetime) -> datetime:
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts

    pairs = [
        (ts, amt)
        for ts, amt in zip(add_timestamps, add_amounts)
        if _ensure_aware(ts) >= cutoff
    ]

    if len(pairs) < 2:
        return _default

    timestamps_aware = [_ensure_aware(ts) for ts, _ in pairs]

    # Split into current 90-day window vs older baseline
    current_cutoff = now - timedelta(days=90)
    current_adds = [ts for ts in timestamps_aware if ts >= current_cutoff]
    baseline_adds = [ts for ts in timestamps_aware if ts < current_cutoff]

    current_rate = len(current_adds) / 3.0  # per 30 days (90d window → /3)

    if len(baseline_adds) < 2:
        # Not enough history to establish a baseline — use lookback period average
        days_span = (timestamps_aware[-1] - timestamps_aware[0]).total_seconds() / 86400
        if days_span <= 0:
            return _default
        baseline_rate = (len(timestamps_aware) - len(current_adds)) / max(1, (days_span - 90) / 30)
    else:
        # Use the span of the baseline timestamps only, not the full range.
        # Using the full range (which includes the current 90-day window) inflates
        # the baseline period and deflates baseline_rate, causing false negatives.
        baseline_span_days = (baseline_adds[-1] - baseline_adds[0]).total_seconds() / 86400
        baseline_rate = len(baseline_adds) / max(1.0, baseline_span_days / 30)

    # ── Poisson rate test ─────────────────────────────────────────
    # Test: is the current-90d count higher than expected under the baseline rate?
    expected_current = baseline_rate * 3  # 3 × 30-day periods in 90 days
    observed_current = len(current_adds)

    if expected_current > 0:
        # One-sided Poisson test: P(X >= observed | lambda = expected)
        p_value_poisson = 1.0 - stats.poisson.cdf(observed_current - 1, mu=expected_current)
    else:
        p_value_poisson = 1.0

    # ── Mann-Whitney U on inter-add intervals ─────────────────────
    p_value_mw = None
    method = "poisson"

    if len(timestamps_aware) >= 6:
        sorted_ts = sorted(timestamps_aware)
        # Split intervals at the same 90-day boundary used by the Poisson test.
        # An interval belongs to the "recent" window if its earlier endpoint is
        # within the current 90-day window; "historical" if its later endpoint
        # is before the current window. This keeps both tests consistent.
        recent_intervals = [
            (sorted_ts[i + 1] - sorted_ts[i]).total_seconds() / 86400
            for i in range(len(sorted_ts) - 1)
            if sorted_ts[i] >= current_cutoff
        ]
        historical_intervals = [
            (sorted_ts[i + 1] - sorted_ts[i]).total_seconds() / 86400
            for i in range(len(sorted_ts) - 1)
            if sorted_ts[i + 1] <= current_cutoff
        ]

        if len(historical_intervals) >= 3 and len(recent_intervals) >= 2:
            stat, p_value_mw = stats.mannwhitneyu(
                recent_intervals, historical_intervals, alternative="less"
            )
            method = "mann_whitney"

    # Choose the more significant result
    if method == "mann_whitney" and p_value_mw is not None:
        p_value = float(p_value_mw)
    else:
        p_value = float(p_value_poisson)
        method = "poisson"

    detected = p_value < 0.10

    details = (
        f"Current rate: {current_rate:.2f} adds/30d, "
        f"baseline rate: {baseline_rate:.2f} adds/30d. "
        f"Method: {method}, p-value: {p_value:.4f}."
    )

    return {
        "detected": detected,
        "method": method,
        "p_value": round(p_value, 6),
        "current_rate_per_30d": round(current_rate, 3),
        "baseline_rate_per_30d": round(baseline_rate, 3),
        "details": details,
    }


# ── Signal combiner ───────────────────────────────────────────────────────────

def combine_signals(
    pressure_result: dict,
    superheat_result: dict,
    add_pattern_result: dict,
) -> dict:
    """
    Combine detection signals into a final verdict.

    Logic
    -----
    - Add pattern alone (no pressure data):
        suspected if p < 0.10, likely if p < 0.05
    - Pressure drift alone: use pressure severity
    - Both signals fire: upgrade confidence one level, method = multi_signal
    - Superheat rise + pressure: adds "confirmed" if pressure was "likely"

    Returns
    -------
    dict with keys:
        should_create_event, confidence, detection_method, summary
    """
    _confidence_rank = {"suspected": 0, "likely": 1, "confirmed": 2}
    _rank_confidence = {0: "suspected", 1: "likely", 2: "confirmed"}

    pressure_fired = pressure_result.get("detected", False)
    superheat_fired = superheat_result.get("detected", False)
    add_pattern_fired = add_pattern_result.get("detected", False)

    pressure_confidence = pressure_result.get("confidence", "suspected")
    add_p_value = add_pattern_result.get("p_value")

    # No signals at all → no event
    if not pressure_fired and not add_pattern_fired:
        return {
            "should_create_event": False,
            "confidence": "suspected",
            "detection_method": "pressure_trend",
            "summary": "No anomalies detected in pressure trend or refrigerant add pattern.",
        }

    # ── Add pattern only (no pressure data available) ─────────────────────────
    if add_pattern_fired and not pressure_fired:
        if add_p_value is not None and add_p_value < 0.05:
            confidence = "likely"
        else:
            confidence = "suspected"
        return {
            "should_create_event": True,
            "confidence": confidence,
            "detection_method": "refrigerant_add_pattern",
            "summary": (
                f"Refrigerant add pattern anomaly detected. {add_pattern_result.get('details', '')} "
                f"No corroborating pressure data available."
            ),
        }

    # ── Pressure drift only ───────────────────────────────────────────────────
    if pressure_fired and not add_pattern_fired:
        confidence = pressure_confidence
        # Upgrade if superheat also fired
        if superheat_fired and pressure_confidence == "likely":
            confidence = "confirmed"
        summary_parts = [f"Pressure drift detected. {pressure_result.get('details', '')}"]
        if superheat_fired:
            summary_parts.append(f"Superheat rise corroborates: {superheat_result.get('details', '')}")
        return {
            "should_create_event": True,
            "confidence": confidence,
            "detection_method": "pressure_trend",
            "summary": " ".join(summary_parts),
        }

    # ── Both pressure and add pattern fired ───────────────────────────────────
    # Upgrade confidence one level
    base_rank = _confidence_rank.get(pressure_confidence, 0)
    upgraded_rank = min(2, base_rank + 1)
    confidence = _rank_confidence[upgraded_rank]

    # Superheat adds another level if pressure was at "likely"
    if superheat_fired and base_rank >= 1:
        confidence = "confirmed"

    summary_parts = [
        f"Multiple signals indicate a refrigerant leak.",
        f"Pressure: {pressure_result.get('details', '')}",
        f"Add pattern: {add_pattern_result.get('details', '')}",
    ]
    if superheat_fired:
        summary_parts.append(f"Superheat: {superheat_result.get('details', '')}")

    return {
        "should_create_event": True,
        "confidence": confidence,
        "detection_method": "multi_signal",
        "summary": " ".join(summary_parts),
    }
