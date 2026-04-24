"""
ColdGrid Demand Charge Calculator Engine

This is the core analytical engine. Given a utility bill's data and an optional
rate schedule, it computes:
  - Demand charge breakdown (flat / TOU / ratchet)
  - Savings potential from peak shaving scenarios
  - Key peak events (which intervals drove the bill)
  - Load profile categorization

Phase 1: Works with monthly bill data (no interval meter data needed).
Phase 2: Will incorporate 15-min telemetry from edge agents.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class DemandChargeResult:
    """Output of a demand charge analysis for one billing period."""
    period_start: date
    period_end: date

    # Actual charges from the bill
    peak_demand_kw: float
    demand_charge_actual: Decimal

    # Ratchet analysis
    ratchet_demand_kw: Optional[float] = None
    ratchet_active: bool = False
    ratchet_penalty: Decimal = Decimal("0")

    # Optimization projections
    demand_charge_optimized: Decimal = Decimal("0")
    savings_potential: Decimal = Decimal("0")
    savings_pct: float = 0.0

    # What drove the peak
    peak_events: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)


class DemandChargeCalculator:
    """
    Calculates demand charges and identifies savings opportunities.

    Usage:
        calc = DemandChargeCalculator(rate_schedule=rate_dict)
        result = calc.analyze_bill(bill)
        result = calc.analyze_history(bills)  # multi-month with ratchet
    """

    def __init__(self, rate_schedule: Optional[dict] = None):
        self.rate = rate_schedule or {}
        self.demand_rates = self.rate.get("demand_rates", {})
        self.ratchet_config = self.demand_rates.get("ratchet", {})

    def analyze_bill(
        self,
        period_start: date,
        period_end: date,
        peak_demand_kw: float,
        demand_charge: Decimal,
        total_kwh: Optional[float] = None,
        total_cost: Optional[Decimal] = None,
    ) -> DemandChargeResult:
        """
        Analyze a single billing period.
        Even without a rate schedule, we can identify the demand charge
        component and estimate savings from peak reduction.
        """
        result = DemandChargeResult(
            period_start=period_start,
            period_end=period_end,
            peak_demand_kw=peak_demand_kw,
            demand_charge_actual=demand_charge,
        )

        # ── Estimate savings at various reduction levels ──
        # Industry benchmarks for cold storage demand reduction
        scenarios = [
            {"name": "Conservative (5% peak reduction)", "pct": 0.05},
            {"name": "Moderate (10% peak reduction)", "pct": 0.10},
            {"name": "Aggressive (20% peak reduction)", "pct": 0.20},
        ]

        if peak_demand_kw > 0 and demand_charge > 0:
            # Derive effective demand rate ($/kW)
            effective_rate = float(demand_charge) / peak_demand_kw

            # Calculate savings for moderate scenario as the default
            moderate_reduction_kw = peak_demand_kw * 0.10
            result.demand_charge_optimized = Decimal(
                str(round((peak_demand_kw - moderate_reduction_kw) * effective_rate, 2))
            )
            result.savings_potential = demand_charge - result.demand_charge_optimized
            result.savings_pct = round(float(result.savings_potential) / float(demand_charge) * 100, 1)

            # Build recommendations
            for s in scenarios:
                reduced_kw = peak_demand_kw * (1 - s["pct"])
                saved = Decimal(str(round(peak_demand_kw * s["pct"] * effective_rate, 2)))
                result.recommendations.append({
                    "scenario": s["name"],
                    "reduced_peak_kw": round(reduced_kw, 1),
                    "monthly_savings": float(saved),
                    "annual_savings": float(saved * 12),
                })

        # ── Identify what likely drove the peak ──
        # Without interval data, we make educated guesses based on cold storage patterns
        if peak_demand_kw > 0:
            result.peak_events = self._identify_peak_drivers(
                peak_demand_kw, period_start, total_kwh
            )

        return result

    def analyze_with_ratchet(
        self,
        bills: list[dict],
        ratchet_pct: float = 0.80,
        lookback_months: int = 11,
    ) -> list[DemandChargeResult]:
        """
        Analyze multiple bills accounting for ratchet clauses.

        A ratchet clause means your billed demand is the greater of:
          (a) This month's actual peak, or
          (b) ratchet_pct * highest peak in the previous lookback_months

        This is where cold storage operators get crushed — one hot day
        in July can inflate demand charges through the following June.
        """
        results = []
        sorted_bills = sorted(bills, key=lambda b: b["period_start"])

        for i, bill in enumerate(sorted_bills):
            peak = bill["peak_demand_kw"]
            demand_charge = Decimal(str(bill["demand_charge"]))

            # Look back at prior months
            lookback_peaks = [
                b["peak_demand_kw"]
                for b in sorted_bills[max(0, i - lookback_months):i]
            ]

            ratchet_kw = None
            ratchet_active = False
            ratchet_penalty = Decimal("0")

            if lookback_peaks:
                ratchet_threshold = max(lookback_peaks) * ratchet_pct
                if ratchet_threshold > peak:
                    ratchet_kw = ratchet_threshold
                    ratchet_active = True
                    # The extra kW you're paying for due to ratchet
                    if peak > 0 and demand_charge > 0:
                        rate_per_kw = float(demand_charge) / peak
                        ratchet_penalty = Decimal(
                            str(round((ratchet_threshold - peak) * rate_per_kw, 2))
                        )

            result = self.analyze_bill(
                period_start=bill["period_start"],
                period_end=bill["period_end"],
                peak_demand_kw=peak,
                demand_charge=demand_charge,
                total_kwh=bill.get("total_kwh"),
                total_cost=bill.get("total_cost") and Decimal(str(bill["total_cost"])),
            )
            result.ratchet_demand_kw = ratchet_kw
            result.ratchet_active = ratchet_active
            result.ratchet_penalty = ratchet_penalty

            results.append(result)

        return results

    def _identify_peak_drivers(
        self,
        peak_kw: float,
        period_start: date,
        total_kwh: Optional[float],
    ) -> list[dict]:
        """
        Without interval data, use heuristics common to cold storage
        to identify likely peak demand drivers.
        """
        events = []
        month = period_start.month

        # Summer months: condensers work harder, compressors run longer
        if month in (6, 7, 8, 9):
            events.append({
                "driver": "Summer ambient temperature",
                "impact": "high",
                "description": "High outdoor temps increase condenser load and compressor runtime",
            })

        # Load factor analysis (if we have kWh)
        if total_kwh and peak_kw > 0:
            days_in_period = 30  # approximate
            hours = days_in_period * 24
            load_factor = total_kwh / (peak_kw * hours)

            if load_factor < 0.4:
                events.append({
                    "driver": "Low load factor",
                    "impact": "high",
                    "description": f"Load factor of {load_factor:.0%} suggests sharp peaks — "
                                   "likely multiple compressors starting simultaneously",
                })
            elif load_factor < 0.6:
                events.append({
                    "driver": "Moderate load factor",
                    "impact": "medium",
                    "description": f"Load factor of {load_factor:.0%} — "
                                   "some peak optimization opportunity exists",
                })

        # Compressor cycling (always relevant for cold storage)
        events.append({
            "driver": "Compressor staging",
            "impact": "medium",
            "description": "Staggering compressor starts can reduce coincident peak demand 5-15%",
        })

        return events


class SavingsSimulator:
    """
    Models savings scenarios for a facility given its bill history.
    """

    @staticmethod
    def thermal_load_shifting(
        peak_kw: float,
        demand_rate: float,
        pre_cool_capacity_pct: float = 0.15,
    ) -> dict:
        """
        Estimate savings from pre-cooling during off-peak hours.
        Cold storage has thermal mass — you can "charge" it like a battery.
        """
        reduced_peak = peak_kw * (1 - pre_cool_capacity_pct)
        monthly_savings = (peak_kw - reduced_peak) * demand_rate
        return {
            "scenario": "Thermal Load Shifting",
            "current_peak_kw": peak_kw,
            "reduced_peak_kw": round(reduced_peak, 1),
            "reduction_kw": round(peak_kw - reduced_peak, 1),
            "monthly_savings": round(monthly_savings, 2),
            "annual_savings": round(monthly_savings * 12, 2),
            "implementation": "Adjust compressor schedules to pre-cool during off-peak hours",
        }

    @staticmethod
    def compressor_staggering(
        peak_kw: float,
        demand_rate: float,
        num_compressors: int = 4,
        stagger_reduction_pct: float = 0.10,
    ) -> dict:
        """
        Prevent multiple compressors from starting at the same time.
        """
        reduced_peak = peak_kw * (1 - stagger_reduction_pct)
        monthly_savings = (peak_kw - reduced_peak) * demand_rate
        return {
            "scenario": "Compressor Staggering",
            "current_peak_kw": peak_kw,
            "reduced_peak_kw": round(reduced_peak, 1),
            "reduction_kw": round(peak_kw - reduced_peak, 1),
            "monthly_savings": round(monthly_savings, 2),
            "annual_savings": round(monthly_savings * 12, 2),
            "implementation": f"Stagger {num_compressors} compressor starts with 2-5 min delays",
        }

    @staticmethod
    def setpoint_optimization(
        peak_kw: float,
        demand_rate: float,
        temp_flex_f: float = 2.0,
        reduction_pct: float = 0.08,
    ) -> dict:
        """
        Widen temperature setpoints during peak TOU periods.
        Most frozen products are safe with +/- 2°F temporary swings.
        """
        reduced_peak = peak_kw * (1 - reduction_pct)
        monthly_savings = (peak_kw - reduced_peak) * demand_rate
        return {
            "scenario": "Setpoint Optimization",
            "current_peak_kw": peak_kw,
            "reduced_peak_kw": round(reduced_peak, 1),
            "reduction_kw": round(peak_kw - reduced_peak, 1),
            "monthly_savings": round(monthly_savings, 2),
            "annual_savings": round(monthly_savings * 12, 2),
            "temp_flexibility_f": temp_flex_f,
            "implementation": f"Allow {temp_flex_f}°F setpoint flexibility during on-peak TOU periods",
        }

    @classmethod
    def run_all_scenarios(
        cls,
        peak_kw: float,
        demand_rate: float,
        num_compressors: int = 4,
    ) -> list[dict]:
        """Run all savings scenarios and return results."""
        return [
            cls.thermal_load_shifting(peak_kw, demand_rate),
            cls.compressor_staggering(peak_kw, demand_rate, num_compressors),
            cls.setpoint_optimization(peak_kw, demand_rate),
        ]
