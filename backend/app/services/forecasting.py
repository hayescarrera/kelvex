"""
Refrigerant Consumption Forecasting Engine — pure sync Python.

Models available:
  - forecast_linear: OLS regression with bootstrap CI (sparse data)
  - forecast_exponential_smoothing: Holt-Winters via statsmodels (≥6 monthly buckets)
  - select_and_run_forecast: dispatcher that picks the right model

AIM Act thresholds used:
  - "warning" threshold: 10% annual leak rate of full charge
  - "AIM threshold": 15% annual leak rate of full charge

Key design decisions:
  - current_annual_leak_rate_pct is computed from the actual trailing 365-day adds
    (matching the AIM Act endpoint formula), not from the regression slope × 365.
  - days_to_aim_threshold/warning are computed via a rolling-window simulation that
    correctly accounts for old adds aging out of the 365-day window. The naive formula
    (headroom / daily_rate) overestimates days remaining when large historical adds
    are about to age off; the simulation fixes this.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# AIM Act annual leak rate thresholds (fraction of full charge)
AIM_THRESHOLD_PCT = 15.0   # must repair ≥ this
AIM_WARNING_PCT = 10.0     # approaching threshold


# ── Data helpers ──────────────────────────────────────────────────────────────

def _days_since_first(timestamps: list[datetime]) -> np.ndarray:
    """Return array of days elapsed since the first timestamp."""
    def _aware(ts: datetime) -> datetime:
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    t0 = _aware(timestamps[0])
    return np.array(
        [(_aware(ts) - t0).total_seconds() / 86400.0 for ts in timestamps],
        dtype=float,
    )


def _cumulative_lbs(amounts: list[float]) -> np.ndarray:
    return np.cumsum(np.array(amounts, dtype=float))


def _trailing_365d_lbs(
    add_timestamps: list[datetime],
    add_amounts_lbs: list[float],
) -> float:
    """
    Sum of refrigerant added in the trailing 365 days.

    This is the AIM Act definition of annual refrigerant consumption and must be
    used for current_annual_leak_rate_pct and threshold calculations rather than
    the regression slope extrapolated to 365 days, which is a forward-looking
    projection not a backward-looking measurement.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=365)

    def _aware(ts: datetime) -> datetime:
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    return float(sum(
        amt for ts, amt in zip(add_timestamps, add_amounts_lbs)
        if _aware(ts) >= cutoff
    ))


def _days_to_threshold_rolloff(
    add_timestamps: list[datetime],
    add_amounts_lbs: list[float],
    threshold_lbs: float,
    lbs_per_day: float,
    max_days: int = 730,
) -> Optional[int]:
    """
    Simulate the AIM Act rolling 365-day window to find when accumulated adds
    will cross threshold_lbs.

    The naive formula (headroom / daily_rate) ignores that historical adds age out
    of the 365-day window, which causes it to overstate headroom when large adds
    from ~11 months ago are about to drop off. This simulation accounts for that.

    Returns days from today until threshold is breached, or None if the steady-state
    rate (lbs_per_day × 365) is too low to ever reach threshold.
    """
    if lbs_per_day <= 0:
        return None

    # At steady state the rolling total converges to lbs_per_day * 365.
    # If even that equilibrium is below threshold, threshold is unreachable.
    if lbs_per_day * 365 < threshold_lbs:
        return None

    now = datetime.now(timezone.utc)

    def _aware(ts: datetime) -> datetime:
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    # Current age (days from now) of each add still within the 365-day window
    existing: list[tuple[float, float]] = [
        ((now - _aware(ts)).total_seconds() / 86400, amt)
        for ts, amt in zip(add_timestamps, add_amounts_lbs)
        if 0 <= (now - _aware(ts)).total_seconds() / 86400 <= 365
    ]

    current_total = sum(amt for _, amt in existing)
    if current_total >= threshold_lbs:
        return 0

    # Day-by-day simulation.
    # At future day d, an existing add with current age `age_now` is still in the
    # window if (age_now + d) <= 365, i.e., age_now <= 365 - d.
    for day in range(1, max_days + 1):
        still_in = sum(amt for age, amt in existing if age <= 365 - day)
        rolling = still_in + lbs_per_day * day
        if rolling >= threshold_lbs:
            return day

    return None


# ── Bootstrap CI ──────────────────────────────────────────────────────────────

def _bootstrap_ci(
    x: np.ndarray,
    y: np.ndarray,
    predict_x: float,
    n_iter: int = 500,
    seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap CI for a linear regression prediction at predict_x."""
    rng = np.random.default_rng(seed)
    n = len(x)
    predictions = []
    for _ in range(n_iter):
        idx = rng.integers(0, n, size=n)
        xs, ys = x[idx], y[idx]
        if np.ptp(xs) == 0:
            continue
        try:
            slope, intercept = np.polyfit(xs, ys, 1)
            predictions.append(slope * predict_x + intercept)
        except Exception:
            continue
    if not predictions:
        return float(np.nan), float(np.nan)
    return float(np.percentile(predictions, 10)), float(np.percentile(predictions, 90))


# ── Forecast models ───────────────────────────────────────────────────────────

def forecast_linear(
    add_timestamps: list[datetime],
    add_amounts_lbs: list[float],
    full_charge_lbs: Optional[float],
    horizon_days: int = 90,
    *,
    current_annual_lbs: Optional[float] = None,
) -> dict:
    """
    Linear regression on cumulative adds vs days since first add.

    Uses 500-iteration bootstrap for CI bounds (useful for sparse data).

    current_annual_lbs
        Pre-computed trailing-365d total.  If None it is computed here.
        Pass from select_and_run_forecast to avoid recomputing.

    Returns
    -------
    dict with keys:
        method, projected_adds_lbs, projected_adds_lbs_low, projected_adds_lbs_high,
        lbs_per_day, days_to_aim_threshold, days_to_aim_warning,
        confidence, current_annual_leak_rate_pct
    """
    n = len(add_timestamps)
    if n < 2:
        return {
            "method": "linear",
            "projected_adds_lbs": 0.0,
            "projected_adds_lbs_low": 0.0,
            "projected_adds_lbs_high": 0.0,
            "lbs_per_day": 0.0,
            "days_to_aim_threshold": None,
            "days_to_aim_warning": None,
            "confidence": "low",
            "current_annual_leak_rate_pct": None,
        }

    if n < 4:
        confidence = "low"
    elif n <= 12:
        confidence = "medium"
    else:
        confidence = "high"

    days = _days_since_first(add_timestamps)
    cumulative = _cumulative_lbs(add_amounts_lbs)

    try:
        slope, intercept = np.polyfit(days, cumulative, 1)
    except Exception as exc:
        logger.warning("Linear fit failed: %s", exc)
        slope = float(np.sum(add_amounts_lbs)) / max(1.0, float(days[-1]))
        intercept = 0.0

    lbs_per_day = max(0.0, float(slope))

    def _aware(ts: datetime) -> datetime:
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    last_day = float((_aware(add_timestamps[-1]) - _aware(add_timestamps[0])).total_seconds() / 86400)
    projected = lbs_per_day * horizon_days

    # Bootstrap CI anchored at current cumulative total + forward projection
    predict_at = last_day + horizon_days
    low, high = _bootstrap_ci(days, cumulative, predict_at, n_iter=500)
    current_cumulative = float(intercept + slope * last_day)
    projected_low = max(0.0, low - current_cumulative) if not np.isnan(low) else projected * 0.7
    projected_high = max(0.0, high - current_cumulative) if not np.isnan(high) else projected * 1.3

    # AIM Act calculations — use trailing 365-day actual adds, not slope × 365
    days_to_aim_threshold: Optional[int] = None
    days_to_aim_warning: Optional[int] = None
    current_annual_leak_rate_pct: Optional[float] = None

    if full_charge_lbs and full_charge_lbs > 0:
        if current_annual_lbs is None:
            current_annual_lbs = _trailing_365d_lbs(add_timestamps, add_amounts_lbs)

        aim_lbs = full_charge_lbs * (AIM_THRESHOLD_PCT / 100.0)
        warn_lbs = full_charge_lbs * (AIM_WARNING_PCT / 100.0)

        # current_annual_leak_rate_pct matches the AIM Act endpoint's backward-looking formula
        current_annual_leak_rate_pct = round(current_annual_lbs / full_charge_lbs * 100.0, 2)

        # Rolling-window simulation: accounts for historical adds aging off the 365-day window
        days_to_aim_threshold = _days_to_threshold_rolloff(
            add_timestamps, add_amounts_lbs, aim_lbs, lbs_per_day
        )
        days_to_aim_warning = _days_to_threshold_rolloff(
            add_timestamps, add_amounts_lbs, warn_lbs, lbs_per_day
        )

    return {
        "method": "linear",
        "projected_adds_lbs": round(projected, 3),
        "projected_adds_lbs_low": round(projected_low, 3),
        "projected_adds_lbs_high": round(projected_high, 3),
        "lbs_per_day": round(lbs_per_day, 4),
        "days_to_aim_threshold": days_to_aim_threshold,
        "days_to_aim_warning": days_to_aim_warning,
        "confidence": confidence,
        "current_annual_leak_rate_pct": current_annual_leak_rate_pct,
    }


def _monthly_buckets(
    add_timestamps: list[datetime],
    add_amounts_lbs: list[float],
) -> list[float]:
    """Aggregate adds into monthly buckets (calendar month, lbs/month)."""
    from collections import defaultdict

    def _aware(ts: datetime) -> datetime:
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    buckets: dict[tuple[int, int], float] = defaultdict(float)
    for ts, amt in zip(add_timestamps, add_amounts_lbs):
        t = _aware(ts)
        buckets[(t.year, t.month)] += amt

    if not buckets:
        return []

    # Fill in zero months between first and last
    years_months = sorted(buckets.keys())
    start_y, start_m = years_months[0]
    end_y, end_m = years_months[-1]

    result = []
    y, m = start_y, start_m
    while (y, m) <= (end_y, end_m):
        result.append(buckets.get((y, m), 0.0))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


def forecast_exponential_smoothing(
    monthly_adds: list[float],
    full_charge_lbs: Optional[float],
    horizon_months: int = 3,
    *,
    current_annual_lbs: Optional[float] = None,
    add_timestamps: Optional[list[datetime]] = None,
    add_amounts_lbs: Optional[list[float]] = None,
) -> dict:
    """
    Holt-Winters ExponentialSmoothing for circuits with 6+ monthly buckets.

    Falls back to a simple linear extrapolation if statsmodels fails.

    current_annual_lbs
        Pre-computed trailing-365d total.  Required for AIM Act calculations.
    add_timestamps / add_amounts_lbs
        Original add history (needed for the rolling-window days-to-threshold
        simulation).  If None, falls back to the naive headroom formula.
    """
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = ExponentialSmoothing(
                monthly_adds,
                trend="add",
                seasonal=None,
                initialization_method="estimated",
            )
            fit = model.fit(optimized=True, disp=False)
            forecast_vals = fit.forecast(horizon_months)

        projected_monthly = float(np.sum(forecast_vals))
        projected_lbs = max(0.0, projected_monthly)

        # Rough CI: ±30% for medium data, ±20% for larger series
        ci_pct = 0.30 if len(monthly_adds) < 12 else 0.20
        projected_low = max(0.0, projected_lbs * (1.0 - ci_pct))
        projected_high = projected_lbs * (1.0 + ci_pct)

        horizon_days = horizon_months * 30
        lbs_per_day = projected_lbs / max(1, horizon_days)

        confidence = "medium" if len(monthly_adds) < 12 else "high"

        days_to_aim_threshold: Optional[int] = None
        days_to_aim_warning: Optional[int] = None
        current_annual_leak_rate_pct: Optional[float] = None

        if full_charge_lbs and full_charge_lbs > 0 and current_annual_lbs is not None:
            aim_lbs = full_charge_lbs * (AIM_THRESHOLD_PCT / 100.0)
            warn_lbs = full_charge_lbs * (AIM_WARNING_PCT / 100.0)

            current_annual_leak_rate_pct = round(current_annual_lbs / full_charge_lbs * 100.0, 2)

            if add_timestamps and add_amounts_lbs:
                # Rolling-window simulation (most accurate)
                days_to_aim_threshold = _days_to_threshold_rolloff(
                    add_timestamps, add_amounts_lbs, aim_lbs, lbs_per_day
                )
                days_to_aim_warning = _days_to_threshold_rolloff(
                    add_timestamps, add_amounts_lbs, warn_lbs, lbs_per_day
                )
            elif lbs_per_day > 0:
                # Fallback: naive headroom formula (no rolloff correction)
                headroom_threshold = max(0.0, aim_lbs - current_annual_lbs)
                headroom_warning = max(0.0, warn_lbs - current_annual_lbs)
                days_to_aim_threshold = 0 if headroom_threshold <= 0 else int(headroom_threshold / lbs_per_day)
                days_to_aim_warning = 0 if headroom_warning <= 0 else int(headroom_warning / lbs_per_day)

        return {
            "method": "exponential_smoothing",
            "projected_adds_lbs": round(projected_lbs, 3),
            "projected_adds_lbs_low": round(projected_low, 3),
            "projected_adds_lbs_high": round(projected_high, 3),
            "lbs_per_day": round(lbs_per_day, 4),
            "days_to_aim_threshold": days_to_aim_threshold,
            "days_to_aim_warning": days_to_aim_warning,
            "confidence": confidence,
            "current_annual_leak_rate_pct": current_annual_leak_rate_pct,
        }

    except Exception as exc:
        logger.warning(
            "Exponential smoothing failed (%s); falling back to linear extrapolation.", exc
        )
        now = datetime.now(timezone.utc)
        fake_timestamps = [
            now - timedelta(days=(len(monthly_adds) - i) * 30)
            for i in range(len(monthly_adds))
        ]
        result = forecast_linear(
            fake_timestamps, monthly_adds, full_charge_lbs,
            horizon_days=horizon_months * 30,
            current_annual_lbs=current_annual_lbs,
        )
        result["method"] = "exponential_smoothing"
        return result


# ── Dispatcher ────────────────────────────────────────────────────────────────

def select_and_run_forecast(
    add_timestamps: list[datetime],
    add_amounts_lbs: list[float],
    full_charge_lbs: Optional[float],
    horizon_days: int = 90,
) -> dict:
    """
    Dispatch to the appropriate forecast model based on data availability.

    Rules:
      < 3 adds               → insufficient_data
      3–5 adds or < 6mo      → forecast_linear
      6+ monthly buckets     → forecast_exponential_smoothing

    Always returns the same dict shape.
    """
    _empty = {
        "method": "insufficient_data",
        "projected_adds_lbs": None,
        "projected_adds_lbs_low": None,
        "projected_adds_lbs_high": None,
        "lbs_per_day": None,
        "days_to_aim_threshold": None,
        "days_to_aim_warning": None,
        "confidence": "low",
        "current_annual_leak_rate_pct": None,
    }

    n = len(add_timestamps)

    if n < 3:
        return _empty

    # Compute trailing 365-day total once; passed to both models for consistency
    # so current_annual_leak_rate_pct always matches the AIM Act endpoint
    current_annual_lbs = _trailing_365d_lbs(add_timestamps, add_amounts_lbs)

    monthly = _monthly_buckets(add_timestamps, add_amounts_lbs)

    if len(monthly) >= 6:
        return forecast_exponential_smoothing(
            monthly,
            full_charge_lbs,
            horizon_months=max(1, horizon_days // 30),
            current_annual_lbs=current_annual_lbs,
            add_timestamps=add_timestamps,
            add_amounts_lbs=add_amounts_lbs,
        )

    return forecast_linear(
        add_timestamps, add_amounts_lbs, full_charge_lbs, horizon_days,
        current_annual_lbs=current_annual_lbs,
    )
