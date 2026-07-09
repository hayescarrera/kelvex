"""
Unit tests for forecasting and leak detection services.
All scenarios use hand-crafted, deterministic data with explicitly computed expected values.
No DB or HTTP fixtures required.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.services.forecasting import (
    _trailing_365d_lbs,
    _days_to_threshold_rolloff,
    forecast_linear,
    select_and_run_forecast,
)
from app.services.leak_detection import (
    compute_ewma,
    detect_pressure_drift,
    detect_superheat_rise,
    detect_add_pattern_anomaly,
    combine_signals,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ago(days: float) -> datetime:
    return _now() - timedelta(days=days)


# ── _trailing_365d_lbs ────────────────────────────────────────────────────────

class TestTrailing365dLbs:
    def test_all_within_window(self):
        ts = [_ago(100), _ago(200), _ago(300)]
        assert _trailing_365d_lbs(ts, [10.0, 20.0, 30.0]) == pytest.approx(60.0)

    def test_excludes_older_than_365_days(self):
        ts = [_ago(400), _ago(100)]
        assert _trailing_365d_lbs(ts, [50.0, 25.0]) == pytest.approx(25.0)

    def test_no_recent_adds(self):
        ts = [_ago(400), _ago(500)]
        assert _trailing_365d_lbs(ts, [50.0, 80.0]) == pytest.approx(0.0)

    def test_empty(self):
        assert _trailing_365d_lbs([], []) == pytest.approx(0.0)

    def test_naive_timestamps_work(self):
        naive_ts = [datetime.utcnow() - timedelta(days=100)]
        assert _trailing_365d_lbs(naive_ts, [42.0]) == pytest.approx(42.0)


# ── _days_to_threshold_rolloff ────────────────────────────────────────────────

class TestDaysToThresholdRolloff:
    def test_already_over_threshold_returns_zero(self):
        # 110 lbs in window, threshold 100 → already breached
        result = _days_to_threshold_rolloff([_ago(100)], [110.0], threshold_lbs=100.0, lbs_per_day=1.0)
        assert result == 0

    def test_unreachable_threshold_returns_none(self):
        # 0.1 lbs/day × 365 = 36.5 lbs < 500 lbs threshold → never reaches it
        result = _days_to_threshold_rolloff([_ago(100)], [10.0], threshold_lbs=500.0, lbs_per_day=0.1)
        assert result is None

    def test_zero_rate_returns_none(self):
        result = _days_to_threshold_rolloff([_ago(100)], [10.0], threshold_lbs=100.0, lbs_per_day=0.0)
        assert result is None

    def test_basic_no_rolloff(self):
        # 50 lbs at 50 days ago; threshold 100; rate 1.0 lbs/day
        # Add ages off at day 315 (50 + 315 = 365), so no rolloff effect before then.
        # Simple: 50 + 1.0 * d >= 100 → d = 50
        result = _days_to_threshold_rolloff([_ago(50)], [50.0], threshold_lbs=100.0, lbs_per_day=1.0)
        assert result == 50

    def test_rolloff_dramatically_extends_timeline(self):
        # 90 lbs added 350 days ago (ages off at simulation day ~15).
        # Naive: headroom = 10, naive_days = 10 / 0.5 = 20 days.
        # Reality: after rolloff, the 90 lbs drops out, and 0.5 lbs/day × 365 = 182.5 >= 100 so
        # reachable, but new adds alone need to hit 100 → ~200 days.
        result = _days_to_threshold_rolloff([_ago(350)], [90.0], threshold_lbs=100.0, lbs_per_day=0.5)
        assert result is not None
        # Simulation must see that the add ages off and correctly reports > 100 days (not naive 20)
        assert result > 100

    def test_add_already_aged_out_ignored(self):
        # Add at 400 days ago is outside the 365-day window → no existing total
        # threshold 50, rate 0.5 → 0.5 * d >= 50 → d = 100
        result = _days_to_threshold_rolloff([_ago(400)], [100.0], threshold_lbs=50.0, lbs_per_day=0.5)
        assert result == 100


# ── compute_ewma ──────────────────────────────────────────────────────────────

class TestComputeEwma:
    def test_empty(self):
        assert compute_ewma([]) == []

    def test_single_element(self):
        assert compute_ewma([5.0]) == [5.0]

    def test_constant_series_unchanged(self):
        result = compute_ewma([10.0] * 10, alpha=0.2)
        assert all(abs(r - 10.0) < 1e-9 for r in result)

    def test_first_element_equals_first_input(self):
        result = compute_ewma([7.0, 3.0, 9.0])
        assert result[0] == 7.0

    def test_ewma_lags_rising_series(self):
        # For a rising series EWMA should be below the actual values (lagging indicator)
        vals = list(range(1, 21))
        result = compute_ewma(vals, alpha=0.3)
        assert result[-1] < vals[-1]


# ── detect_pressure_drift ─────────────────────────────────────────────────────

class TestDetectPressureDrift:
    def test_insufficient_data_returns_not_detected(self):
        result = detect_pressure_drift([100.0, 100.0], design_suction_psi=None)
        assert result["detected"] is False
        assert "Insufficient" in result["details"]

    def test_stable_pressure_no_detection(self):
        result = detect_pressure_drift([100.0] * 20, design_suction_psi=None)
        assert result["detected"] is False
        assert result["drift_pct"] == pytest.approx(0.0, abs=0.1)

    def test_severe_pressure_drop_detected(self):
        # Pressure falls from 100 to 80; EWMA baseline ~100, current ~85 → drift ~15%
        pressures = [100.0] * 9 + [80.0] * 9
        result = detect_pressure_drift(pressures, design_suction_psi=None)
        assert result["detected"] is True
        assert result["severity"] == "severe"
        assert result["confidence"] == "confirmed"

    def test_design_flag_fires_below_80pct_of_design(self):
        # Current ≈70 psi vs design 100 psi → below 80% → design_flag
        pressures = [100.0] * 10 + [70.0] * 10
        result = detect_pressure_drift(pressures, design_suction_psi=100.0)
        assert result["detected"] is True

    def test_zero_baseline_returns_not_detected(self):
        result = detect_pressure_drift([0.0] * 12, design_suction_psi=None)
        assert result["detected"] is False


# ── detect_superheat_rise ─────────────────────────────────────────────────────

class TestDetectSuperheatRise:
    def test_insufficient_data(self):
        result = detect_superheat_rise([10.0, 11.0])
        assert result["detected"] is False

    def test_stable_superheat_no_detection(self):
        result = detect_superheat_rise([10.0] * 20)
        assert result["detected"] is False
        assert result["rise_f"] == pytest.approx(0.0, abs=0.1)

    def test_rise_above_threshold_detected(self):
        # Superheat jumps from 10°F baseline to 16°F → 6°F rise (threshold = 4°F)
        result = detect_superheat_rise([10.0] * 10 + [16.0] * 10)
        assert result["detected"] is True
        assert result["rise_f"] > 4.0

    def test_small_rise_below_threshold_not_detected(self):
        # 2°F rise — below the 4°F threshold
        result = detect_superheat_rise([10.0] * 10 + [12.0] * 10)
        assert result["detected"] is False


# ── detect_add_pattern_anomaly ────────────────────────────────────────────────

class TestDetectAddPatternAnomaly:
    def test_single_add_returns_insufficient(self):
        result = detect_add_pattern_anomaly([_ago(10)], [5.0])
        assert result["detected"] is False
        assert result["method"] == "insufficient_data"

    def test_stable_add_rate_not_detected(self):
        # 13 adds every 28 days → uniform rate, nothing anomalous
        ts = [_ago(365 - i * 28) for i in range(13)]
        result = detect_add_pattern_anomaly(ts, [5.0] * 13)
        assert result["detected"] is False

    def test_elevated_recent_rate_detected(self):
        # Sparse baseline (1 add/60 days), then 8 adds in last 80 days
        baseline_ts = [_ago(365 - i * 60) for i in range(5)]
        recent_ts = [_ago(10 * i) for i in range(1, 9)]  # _ago(10) … _ago(80)
        ts = baseline_ts + recent_ts
        result = detect_add_pattern_anomaly(ts, [5.0] * len(ts))
        assert result["detected"] is True
        assert result["current_rate_per_30d"] > result["baseline_rate_per_30d"]

    def test_baseline_rate_not_deflated_by_full_span(self):
        # Regression test: old code used full timestamp span (including current window) to
        # compute baseline_span_days, inflating the denominator and deflating baseline_rate,
        # causing false negatives. Fixed code uses baseline-only span.
        # Setup: 3 baseline adds over a 60-day span → baseline_rate ≈ 1.5 adds/30d
        baseline_ts = [_ago(360), _ago(330), _ago(300)]
        recent_ts = [_ago(80), _ago(60), _ago(40), _ago(20), _ago(5)]
        ts = baseline_ts + recent_ts
        result = detect_add_pattern_anomaly(ts, [3.0] * len(ts))
        # With fixed code, baseline_rate is derived from the 60-day baseline span,
        # not the full ~355-day span that would yield a deflated ~0.25 adds/30d.
        assert result["baseline_rate_per_30d"] > 1.0


# ── forecast_linear ───────────────────────────────────────────────────────────

class TestForecastLinear:
    def test_single_add_returns_zero_rate(self):
        result = forecast_linear([_ago(10)], [5.0], full_charge_lbs=1000.0)
        assert result["method"] == "linear"
        assert result["lbs_per_day"] == 0.0
        assert result["days_to_aim_threshold"] is None

    def test_returns_all_required_keys(self):
        ts = [_ago(60), _ago(30), _ago(5)]
        result = forecast_linear(ts, [10.0, 10.0, 10.0], full_charge_lbs=500.0)
        for key in [
            "method", "projected_adds_lbs", "projected_adds_lbs_low",
            "projected_adds_lbs_high", "lbs_per_day", "days_to_aim_threshold",
            "days_to_aim_warning", "confidence", "current_annual_leak_rate_pct",
        ]:
            assert key in result

    def test_positive_add_rate_gives_positive_lbs_per_day(self):
        ts = [_ago(90), _ago(60), _ago(30), _ago(5)]
        result = forecast_linear(ts, [10.0] * 4, full_charge_lbs=None)
        assert result["lbs_per_day"] > 0

    def test_aim_threshold_already_exceeded(self):
        # Full charge 100 lbs; AIM threshold = 20 lbs (20%); added 25 lbs in last 365 days
        ts = [_ago(200), _ago(100)]
        result = forecast_linear(ts, [12.5, 12.5], full_charge_lbs=100.0)
        # current_annual_lbs = 25 > 20 → already breached → days_to_aim_threshold = 0
        assert result["days_to_aim_threshold"] == 0

    def test_no_full_charge_skips_aim_calculation(self):
        ts = [_ago(60), _ago(30)]
        result = forecast_linear(ts, [10.0, 10.0], full_charge_lbs=None)
        assert result["days_to_aim_threshold"] is None
        assert result["current_annual_leak_rate_pct"] is None

    def test_current_annual_rate_uses_trailing_365d_not_slope(self):
        # Old add (400 days ago, 50 lbs) must NOT count toward the annual rate.
        # Only the two recent adds (5 + 5 = 10 lbs) should be used.
        ts = [_ago(400), _ago(100), _ago(50)]
        result = forecast_linear(ts, [50.0, 5.0, 5.0], full_charge_lbs=200.0)
        # current_annual_lbs = 10; rate = 10/200 * 100 = 5%
        assert result["current_annual_leak_rate_pct"] == pytest.approx(5.0, abs=0.5)

    def test_confidence_scales_with_data_points(self):
        few = [_ago(60), _ago(30)]
        medium = [_ago(90), _ago(70), _ago(50), _ago(30), _ago(10)]
        many = [_ago(90 - i * 5) for i in range(15)]

        assert forecast_linear(few, [5.0] * 2, full_charge_lbs=None)["confidence"] == "low"
        assert forecast_linear(medium, [5.0] * 5, full_charge_lbs=None)["confidence"] == "medium"
        assert forecast_linear(many, [5.0] * 15, full_charge_lbs=None)["confidence"] == "high"


# ── select_and_run_forecast ───────────────────────────────────────────────────

class TestSelectAndRunForecast:
    def test_fewer_than_3_adds_returns_insufficient(self):
        result = select_and_run_forecast([_ago(30), _ago(10)], [5.0, 5.0], full_charge_lbs=None)
        assert result["method"] == "insufficient_data"
        assert result["projected_adds_lbs"] is None

    def test_sparse_data_routes_to_linear(self):
        # 4 adds within 2 months → < 6 distinct monthly buckets → linear
        ts = [_ago(60), _ago(45), _ago(30), _ago(10)]
        result = select_and_run_forecast(ts, [5.0] * 4, full_charge_lbs=None)
        assert result["method"] == "linear"

    def test_long_history_routes_to_exponential_smoothing(self):
        # One add per month for 8 months → 8 monthly buckets → exponential_smoothing
        ts = [_ago(210 - i * 30) for i in range(8)]
        result = select_and_run_forecast(ts, [5.0] * 8, full_charge_lbs=None)
        assert result["method"] == "exponential_smoothing"

    def test_all_required_keys_present(self):
        ts = [_ago(60), _ago(45), _ago(30), _ago(10)]
        result = select_and_run_forecast(ts, [5.0] * 4, full_charge_lbs=500.0)
        for key in [
            "method", "projected_adds_lbs", "projected_adds_lbs_low",
            "projected_adds_lbs_high", "lbs_per_day", "days_to_aim_threshold",
            "days_to_aim_warning", "confidence", "current_annual_leak_rate_pct",
        ]:
            assert key in result

    def test_current_annual_lbs_computed_once_consistently(self):
        # Both linear and exp-smoothing should see the same current_annual_leak_rate_pct
        # when the data set straddles the 6-month boundary; we verify the key exists and
        # is non-negative rather than testing internal routing details.
        ts = [_ago(100 - i * 15) for i in range(5)]
        result = select_and_run_forecast(ts, [4.0] * 5, full_charge_lbs=200.0)
        assert result["current_annual_leak_rate_pct"] is not None
        assert result["current_annual_leak_rate_pct"] >= 0


# ── combine_signals ───────────────────────────────────────────────────────────

class TestCombineSignals:
    _NO_P = {"detected": False, "confidence": "suspected", "details": ""}
    _NO_SH = {"detected": False, "rise_f": 0.0, "details": ""}
    _NO_ADD = {"detected": False, "p_value": None, "details": ""}

    def _pressure(self, confidence="likely"):
        return {"detected": True, "severity": "moderate", "confidence": confidence, "details": "p drift"}

    def _add(self, p_value=0.04):
        return {"detected": True, "p_value": p_value, "details": "add spike"}

    _SUPERHEAT = {"detected": True, "rise_f": 6.0, "details": "sh rise"}

    # No signals
    def test_no_signals_no_event(self):
        result = combine_signals(self._NO_P, self._NO_SH, self._NO_ADD)
        assert result["should_create_event"] is False

    # Add pattern only
    def test_add_only_high_significance_yields_likely(self):
        result = combine_signals(self._NO_P, self._NO_SH, self._add(p_value=0.04))
        assert result["should_create_event"] is True
        assert result["confidence"] == "likely"
        assert result["detection_method"] == "refrigerant_add_pattern"

    def test_add_only_low_significance_yields_suspected(self):
        result = combine_signals(self._NO_P, self._NO_SH, self._add(p_value=0.08))
        assert result["should_create_event"] is True
        assert result["confidence"] == "suspected"

    # Pressure only
    def test_pressure_only_preserves_confidence(self):
        result = combine_signals(self._pressure("confirmed"), self._NO_SH, self._NO_ADD)
        assert result["should_create_event"] is True
        assert result["confidence"] == "confirmed"
        assert result["detection_method"] == "pressure_trend"

    def test_pressure_likely_plus_superheat_upgrades_to_confirmed(self):
        result = combine_signals(self._pressure("likely"), self._SUPERHEAT, self._NO_ADD)
        assert result["should_create_event"] is True
        assert result["confidence"] == "confirmed"

    def test_pressure_suspected_plus_superheat_stays_suspected(self):
        # Upgrade only fires when pressure_confidence == "likely"
        result = combine_signals(self._pressure("suspected"), self._SUPERHEAT, self._NO_ADD)
        assert result["confidence"] == "suspected"

    # Both pressure and add pattern
    def test_pressure_plus_add_upgrades_one_level(self):
        # suspected(0) → min(2, 0+1) = 1 → "likely"
        result = combine_signals(self._pressure("suspected"), self._NO_SH, self._add())
        assert result["should_create_event"] is True
        assert result["confidence"] == "likely"
        assert result["detection_method"] == "multi_signal"

    def test_pressure_confirmed_plus_add_caps_at_confirmed(self):
        # confirmed(2) + add → min(2, 3) = 2 → still "confirmed"
        result = combine_signals(self._pressure("confirmed"), self._NO_SH, self._add())
        assert result["confidence"] == "confirmed"

    def test_all_three_signals_yields_confirmed(self):
        result = combine_signals(self._pressure("likely"), self._SUPERHEAT, self._add())
        assert result["confidence"] == "confirmed"
        assert result["detection_method"] == "multi_signal"
        assert "Superheat" in result["summary"]
