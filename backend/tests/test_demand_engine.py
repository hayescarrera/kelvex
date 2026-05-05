"""
Unit tests for demand_engine: DemandChargeCalculator and SavingsSimulator.
Pure Python — no DB or HTTP required.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.services.demand_engine import DemandChargeCalculator, SavingsSimulator


# ── DemandChargeCalculator.analyze_bill ──────────────────


class TestAnalyzeBill:
    def setup_method(self):
        self.calc = DemandChargeCalculator()

    def test_basic_analysis(self):
        result = self.calc.analyze_bill(
            period_start=date(2025, 3, 1),
            period_end=date(2025, 3, 31),
            peak_demand_kw=450.0,
            demand_charge=Decimal("5400.00"),
        )
        assert result.peak_demand_kw == 450.0
        assert result.demand_charge_actual == Decimal("5400.00")
        assert result.savings_potential > 0
        assert result.savings_pct > 0
        assert len(result.recommendations) == 3

    def test_zero_demand_no_savings(self):
        result = self.calc.analyze_bill(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            peak_demand_kw=0.0,
            demand_charge=Decimal("0.00"),
        )
        assert result.savings_potential == Decimal("0")
        assert result.savings_pct == 0.0
        assert len(result.recommendations) == 0

    def test_summer_month_peak_driver(self):
        result = self.calc.analyze_bill(
            period_start=date(2025, 7, 1),
            period_end=date(2025, 7, 31),
            peak_demand_kw=500.0,
            demand_charge=Decimal("6000.00"),
        )
        drivers = [e["driver"] for e in result.peak_events]
        assert any("Summer" in d for d in drivers)

    def test_winter_month_no_summer_driver(self):
        result = self.calc.analyze_bill(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            peak_demand_kw=400.0,
            demand_charge=Decimal("4800.00"),
        )
        drivers = [e["driver"] for e in result.peak_events]
        assert not any("Summer" in d for d in drivers)

    def test_low_load_factor_flagged(self):
        # Low load factor: total_kwh << peak_kw * hours
        result = self.calc.analyze_bill(
            period_start=date(2025, 2, 1),
            period_end=date(2025, 2, 28),
            peak_demand_kw=500.0,
            demand_charge=Decimal("5000.00"),
            total_kwh=50000.0,  # load factor = 50000/(500*720) ≈ 0.14 → "Low"
        )
        drivers = [e["driver"] for e in result.peak_events]
        assert any("Low load factor" in d for d in drivers)

    def test_moderate_load_factor(self):
        # Moderate load factor: ~0.5
        result = self.calc.analyze_bill(
            period_start=date(2025, 2, 1),
            period_end=date(2025, 2, 28),
            peak_demand_kw=300.0,
            demand_charge=Decimal("3600.00"),
            total_kwh=108000.0,  # load factor = 108000/(300*720) = 0.5 → "Moderate"
        )
        drivers = [e["driver"] for e in result.peak_events]
        assert any("Moderate load factor" in d for d in drivers)

    def test_recommendations_structure(self):
        result = self.calc.analyze_bill(
            period_start=date(2025, 4, 1),
            period_end=date(2025, 4, 30),
            peak_demand_kw=400.0,
            demand_charge=Decimal("4800.00"),
        )
        for rec in result.recommendations:
            assert "scenario" in rec
            assert "reduced_peak_kw" in rec
            assert "monthly_savings" in rec
            assert "annual_savings" in rec
            assert rec["annual_savings"] == rec["monthly_savings"] * 12

    def test_10pct_savings_is_default_scenario(self):
        result = self.calc.analyze_bill(
            period_start=date(2025, 4, 1),
            period_end=date(2025, 4, 30),
            peak_demand_kw=400.0,
            demand_charge=Decimal("4800.00"),
        )
        assert result.savings_pct == pytest.approx(10.0, abs=0.1)


# ── DemandChargeCalculator.analyze_with_ratchet ──────────


class TestAnalyzeWithRatchet:
    def setup_method(self):
        self.calc = DemandChargeCalculator()

    def _make_bills(self, peaks: list[float]) -> list[dict]:
        bills = []
        for i, peak in enumerate(peaks):
            month = (i % 12) + 1
            year = 2024 + (i // 12)
            bills.append({
                "period_start": date(year, month, 1),
                "period_end": date(year, month, 28),
                "peak_demand_kw": peak,
                "demand_charge": peak * 12.0,
                "total_kwh": peak * 500,
            })
        return bills

    def test_no_ratchet_first_month(self):
        bills = self._make_bills([400.0])
        results = self.calc.analyze_with_ratchet(bills)
        assert len(results) == 1
        assert results[0].ratchet_active is False

    def test_ratchet_activates_after_high_peak(self):
        # Month 1: 500 kW peak, Month 2: 300 kW (below 80% of 500 = 400)
        bills = self._make_bills([500.0, 300.0])
        results = self.calc.analyze_with_ratchet(bills, ratchet_pct=0.80)
        assert results[1].ratchet_active is True
        assert results[1].ratchet_demand_kw == pytest.approx(400.0)
        assert results[1].ratchet_penalty > 0

    def test_ratchet_does_not_activate_when_peak_exceeds_threshold(self):
        # Month 1: 400 kW, Month 2: 400 kW — no ratchet needed
        bills = self._make_bills([400.0, 400.0])
        results = self.calc.analyze_with_ratchet(bills, ratchet_pct=0.80)
        assert results[1].ratchet_active is False

    def test_multi_month_lookback(self):
        peaks = [500.0, 300.0, 300.0, 300.0]
        bills = self._make_bills(peaks)
        results = self.calc.analyze_with_ratchet(bills, ratchet_pct=0.80, lookback_months=11)
        # All months after the 500 kW peak should be ratcheted
        assert all(r.ratchet_active for r in results[1:])

    def test_returns_one_result_per_bill(self):
        bills = self._make_bills([400.0, 350.0, 420.0, 380.0])
        results = self.calc.analyze_with_ratchet(bills)
        assert len(results) == 4

    def test_results_sorted_chronologically(self):
        bills = self._make_bills([400.0, 350.0, 420.0])
        results = self.calc.analyze_with_ratchet(bills)
        dates = [r.period_start for r in results]
        assert dates == sorted(dates)


# ── SavingsSimulator ─────────────────────────────────────


class TestThermalLoadShifting:
    def test_basic_calculation(self):
        result = SavingsSimulator.thermal_load_shifting(
            peak_kw=400.0, demand_rate=12.0
        )
        assert result["scenario"] == "Thermal Load Shifting"
        assert result["current_peak_kw"] == 400.0
        assert result["reduced_peak_kw"] == pytest.approx(340.0)
        assert result["reduction_kw"] == pytest.approx(60.0)
        assert result["monthly_savings"] == pytest.approx(720.0)
        assert result["annual_savings"] == pytest.approx(8640.0)

    def test_custom_capacity_pct(self):
        result = SavingsSimulator.thermal_load_shifting(
            peak_kw=500.0, demand_rate=10.0, pre_cool_capacity_pct=0.20
        )
        assert result["reduction_kw"] == pytest.approx(100.0)
        assert result["monthly_savings"] == pytest.approx(1000.0)

    def test_zero_rate(self):
        result = SavingsSimulator.thermal_load_shifting(peak_kw=400.0, demand_rate=0.0)
        assert result["monthly_savings"] == 0.0
        assert result["annual_savings"] == 0.0


class TestCompressorStaggering:
    def test_basic_calculation(self):
        result = SavingsSimulator.compressor_staggering(
            peak_kw=400.0, demand_rate=12.0
        )
        assert result["scenario"] == "Compressor Staggering"
        assert result["current_peak_kw"] == 400.0
        assert result["reduced_peak_kw"] == pytest.approx(360.0)
        assert result["reduction_kw"] == pytest.approx(40.0)
        assert result["monthly_savings"] == pytest.approx(480.0)
        assert result["annual_savings"] == pytest.approx(5760.0)

    def test_num_compressors_in_description(self):
        result = SavingsSimulator.compressor_staggering(
            peak_kw=400.0, demand_rate=12.0, num_compressors=6
        )
        assert "6" in result["implementation"]

    def test_custom_reduction(self):
        result = SavingsSimulator.compressor_staggering(
            peak_kw=500.0, demand_rate=10.0, stagger_reduction_pct=0.15
        )
        assert result["reduction_kw"] == pytest.approx(75.0)


class TestSetpointOptimization:
    def test_basic_calculation(self):
        result = SavingsSimulator.setpoint_optimization(
            peak_kw=400.0, demand_rate=12.0
        )
        assert result["scenario"] == "Setpoint Optimization"
        assert result["current_peak_kw"] == 400.0
        assert result["reduced_peak_kw"] == pytest.approx(368.0)
        assert result["reduction_kw"] == pytest.approx(32.0)
        assert result["monthly_savings"] == pytest.approx(384.0)
        assert result["annual_savings"] == pytest.approx(4608.0)

    def test_temp_flexibility_in_result(self):
        result = SavingsSimulator.setpoint_optimization(
            peak_kw=400.0, demand_rate=12.0, temp_flex_f=3.0
        )
        assert result["temp_flexibility_f"] == 3.0
        assert "3.0" in result["implementation"]


class TestRunAllScenarios:
    def test_returns_three_scenarios(self):
        results = SavingsSimulator.run_all_scenarios(peak_kw=400.0, demand_rate=12.0)
        assert len(results) == 3

    def test_scenario_names(self):
        results = SavingsSimulator.run_all_scenarios(peak_kw=400.0, demand_rate=12.0)
        names = [r["scenario"] for r in results]
        assert "Thermal Load Shifting" in names
        assert "Compressor Staggering" in names
        assert "Setpoint Optimization" in names

    def test_all_scenarios_have_savings(self):
        results = SavingsSimulator.run_all_scenarios(peak_kw=400.0, demand_rate=12.0)
        for r in results:
            assert r["monthly_savings"] > 0
            assert r["annual_savings"] == r["monthly_savings"] * 12

    def test_num_compressors_forwarded(self):
        results = SavingsSimulator.run_all_scenarios(
            peak_kw=400.0, demand_rate=12.0, num_compressors=6
        )
        stagger = next(r for r in results if r["scenario"] == "Compressor Staggering")
        assert "6" in stagger["implementation"]
