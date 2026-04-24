"""
Energy Optimization & Load Shifting Engine

Core value proposition: reduce demand charges and energy costs by
intelligently scheduling compressor loads around TOU rate windows.

Key capabilities:
  1. Rate structure analysis — parse TOU periods into actionable windows
  2. Pre-cool scheduling — identify optimal pre-cool windows before peak
  3. Peak shaving — detect when demand is approaching billing peak
  4. Savings projection — model monthly/annual savings from load shifting
  5. Real-time recommendations — current and upcoming shift opportunities
"""

import logging
from datetime import datetime, timezone, timedelta, date, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tariff import RateSchedule
from app.models.billing import UtilityBill, DemandAnalysis
from app.models.facility import Facility
from app.models.compressor import Compressor, CompressorReading
from app.models.zone import Zone

logger = logging.getLogger("coldgrid.energy_optimizer")


# ── Rate Structure Analysis ──────────────────────

class RatePeriod:
    """A TOU rate period with time windows."""
    def __init__(self, name: str, rate: float, months: list[int] | None = None,
                 hours: list[int] | None = None):
        self.name = name
        self.rate = rate
        self.months = months  # [6,7,8,9] or None for all months
        self.hours = hours    # [start_hour, end_hour] or None for all hours

    def is_active(self, dt: datetime) -> bool:
        if self.months and dt.month not in self.months:
            return False
        if self.hours:
            return self.hours[0] <= dt.hour < self.hours[1]
        return True


def parse_rate_periods(rate_data: dict[str, Any], rate_type: str = "energy") -> list[RatePeriod]:
    """Parse JSONB rate structure into RatePeriod objects."""
    periods = []

    if "tou" in rate_data:
        for entry in rate_data["tou"]:
            periods.append(RatePeriod(
                name=entry.get("period", "unknown"),
                rate=float(entry.get("rate", 0)),
                months=entry.get("months"),
                hours=entry.get("hours"),
            ))
    elif "flat" in rate_data:
        periods.append(RatePeriod(
            name="flat",
            rate=float(rate_data["flat"].get("rate", 0)),
        ))

    return sorted(periods, key=lambda p: p.rate, reverse=True)


def get_current_rate(rate_schedule: RateSchedule, dt: datetime) -> dict[str, Any]:
    """Get the current energy and demand rate at a given time."""
    energy_periods = parse_rate_periods(rate_schedule.energy_rates, "energy")
    demand_periods = parse_rate_periods(rate_schedule.demand_rates, "demand")

    current_energy = None
    for period in energy_periods:
        if period.is_active(dt):
            current_energy = period
            break

    current_demand = None
    for period in demand_periods:
        if period.is_active(dt):
            current_demand = period
            break

    return {
        "energy_rate": current_energy.rate if current_energy else 0,
        "energy_period": current_energy.name if current_energy else "unknown",
        "demand_rate": current_demand.rate if current_demand else 0,
        "demand_period": current_demand.name if current_demand else "unknown",
    }


def get_rate_windows(rate_schedule: RateSchedule, target_date: date) -> list[dict[str, Any]]:
    """
    Get all rate windows for a given day, sorted chronologically.
    Returns list of {period, start_hour, end_hour, energy_rate, demand_rate}.
    """
    energy_periods = parse_rate_periods(rate_schedule.energy_rates)
    demand_periods = parse_rate_periods(rate_schedule.demand_rates)

    windows = []
    for hour in range(24):
        dt = datetime(target_date.year, target_date.month, target_date.day, hour, tzinfo=timezone.utc)

        energy_rate = 0.0
        energy_name = "off_peak"
        for p in energy_periods:
            if p.is_active(dt):
                energy_rate = p.rate
                energy_name = p.name
                break

        demand_rate = 0.0
        for p in demand_periods:
            if p.is_active(dt):
                demand_rate = p.rate
                break

        windows.append({
            "hour": hour,
            "energy_period": energy_name,
            "energy_rate": energy_rate,
            "demand_rate": demand_rate,
        })

    return windows


# ── Pre-Cool Scheduling ──────────────────────────

async def compute_precool_windows(
    facility_id: UUID,
    db: AsyncSession,
    target_date: date | None = None,
) -> dict[str, Any]:
    """
    Compute optimal pre-cool windows for a facility.

    Strategy: Pull zones to low end of temp range during off-peak hours
    so compressors can coast (reduced load) through on-peak hours.
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    # Load facility with rate schedule
    result = await db.execute(
        select(Facility).where(Facility.id == facility_id)
    )
    facility = result.scalar_one_or_none()
    if not facility or not facility.rate_schedule_id:
        return {"error": "No rate schedule assigned to facility"}

    result = await db.execute(
        select(RateSchedule).where(RateSchedule.id == facility.rate_schedule_id)
    )
    rate_schedule = result.scalar_one_or_none()
    if not rate_schedule:
        return {"error": "Rate schedule not found"}

    # Get zones
    result = await db.execute(
        select(Zone).where(Zone.facility_id == facility_id)
    )
    zones = list(result.scalars().all())

    # Get compressors for total capacity
    result = await db.execute(
        select(Compressor).where(Compressor.facility_id == facility_id)
    )
    compressors = list(result.scalars().all())
    total_hp = sum(c.hp or 0 for c in compressors)
    total_tons = sum(c.capacity_tons or 0 for c in compressors)

    # Analyze rate windows
    windows = get_rate_windows(rate_schedule, target_date)

    # Find on-peak and off-peak windows
    energy_rates = {w["hour"]: w["energy_rate"] for w in windows}
    max_rate = max(energy_rates.values()) if energy_rates else 0
    min_rate = min(energy_rates.values()) if energy_rates else 0

    on_peak_hours = [h for h, r in energy_rates.items() if r == max_rate and max_rate > min_rate]
    off_peak_hours = [h for h, r in energy_rates.items() if r == min_rate]

    # Pre-cool window: 2–4 hours before on-peak starts
    if on_peak_hours:
        peak_start = min(on_peak_hours)
        precool_start = max(0, peak_start - 4)
        precool_end = peak_start
        precool_hours = list(range(precool_start, precool_end))
    else:
        precool_hours = []

    # Coast window: during on-peak, reduce compressor load
    coast_hours = on_peak_hours

    # Calculate estimated savings
    # Assume ~0.746 kW per HP for compressor load
    estimated_load_kw = total_hp * 0.746
    rate_diff = max_rate - min_rate

    # Pre-cool shifts ~30% of on-peak load to off-peak
    shift_fraction = 0.30
    shifted_kwh_daily = estimated_load_kw * shift_fraction * len(on_peak_hours)
    energy_savings_daily = shifted_kwh_daily * rate_diff

    # Demand savings: pre-cooling smooths the peak
    # Estimate 10–15% peak demand reduction
    demand_reduction_pct = 0.12

    # Thermal mass modeling per zone
    zone_strategies = []
    for zone in zones:
        if zone.temp_setpoint is not None:
            alarm_low = zone.temp_alarm_low or (zone.temp_setpoint - 5)
            precool_target = alarm_low + 1  # Pull to bottom of range

            zone_strategies.append({
                "zone_id": str(zone.id),
                "zone_name": zone.name,
                "zone_type": zone.zone_type,
                "current_setpoint": zone.temp_setpoint,
                "precool_target": precool_target,
                "temp_delta": round(zone.temp_setpoint - precool_target, 1),
                "precool_hours": precool_hours,
                "coast_hours": coast_hours,
            })

    return {
        "facility_id": str(facility_id),
        "target_date": target_date.isoformat(),
        "rate_schedule": rate_schedule.schedule_name,
        "rate_windows": windows,
        "on_peak_hours": on_peak_hours,
        "off_peak_hours": off_peak_hours,
        "precool_window": {
            "start_hour": min(precool_hours) if precool_hours else None,
            "end_hour": max(precool_hours) + 1 if precool_hours else None,
            "hours": precool_hours,
        },
        "coast_window": {
            "hours": coast_hours,
        },
        "plant_summary": {
            "total_compressors": len(compressors),
            "total_hp": total_hp,
            "total_capacity_tons": total_tons,
            "estimated_load_kw": round(estimated_load_kw, 1),
        },
        "zone_strategies": zone_strategies,
        "estimated_savings": {
            "energy_savings_daily": round(energy_savings_daily, 2),
            "energy_savings_monthly": round(energy_savings_daily * 22, 2),  # ~22 work days
            "demand_reduction_pct": demand_reduction_pct,
            "rate_differential": round(rate_diff, 4),
            "shifted_kwh_daily": round(shifted_kwh_daily, 1),
        },
    }


# ── Demand Charge Forecasting ────────────────────

async def compute_demand_forecast(
    facility_id: UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Track rolling peak kW for the current billing cycle and forecast
    month-end demand charge.
    """
    now = datetime.now(timezone.utc)
    # Current billing cycle (approximate: 1st to end of month)
    cycle_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cycle_end = (cycle_start + timedelta(days=32)).replace(day=1)
    days_in_cycle = (cycle_end - cycle_start).days
    days_elapsed = (now - cycle_start).days + 1

    # Load facility with rate schedule
    result = await db.execute(select(Facility).where(Facility.id == facility_id))
    facility = result.scalar_one_or_none()
    if not facility:
        return {"error": "Facility not found"}

    # Get rate schedule for ratchet info
    ratchet = None
    demand_rate = 0.0
    if facility.rate_schedule_id:
        result = await db.execute(
            select(RateSchedule).where(RateSchedule.id == facility.rate_schedule_id)
        )
        rs = result.scalar_one_or_none()
        if rs:
            ratchet = rs.demand_rates.get("ratchet")
            # Get flat or max TOU demand rate
            if "flat" in rs.demand_rates:
                demand_rate = float(rs.demand_rates["flat"].get("rate", 0))
            elif "tou" in rs.demand_rates:
                demand_rate = max(float(p.get("rate", 0)) for p in rs.demand_rates["tou"])

    # Current cycle peak from compressor readings (sum of all compressor kW at each timestamp)
    result = await db.execute(
        select(
            func.max(
                select(func.sum(CompressorReading.kw))
                .where(
                    CompressorReading.compressor_id.in_(
                        select(Compressor.id).where(Compressor.facility_id == facility_id)
                    ),
                    CompressorReading.recorded_at >= cycle_start,
                    CompressorReading.recorded_at < cycle_end,
                )
                .group_by(CompressorReading.recorded_at)
                .correlate_except(CompressorReading)
                .scalar_subquery()
            )
        )
    )
    current_peak_kw = result.scalar() or 0

    # Also check utility bills for historical peaks
    result = await db.execute(
        select(UtilityBill)
        .where(UtilityBill.facility_id == facility_id)
        .order_by(desc(UtilityBill.period_start))
        .limit(12)
    )
    recent_bills = list(result.scalars().all())

    historical_peaks = [
        {"period": b.period_start.isoformat(), "peak_kw": float(b.peak_demand_kw or 0)}
        for b in recent_bills if b.peak_demand_kw
    ]
    max_historical_peak = max((b.peak_demand_kw or 0 for b in recent_bills), default=0)

    # Ratchet calculation
    ratchet_demand = 0.0
    if ratchet and max_historical_peak > 0:
        ratchet_pct = ratchet.get("pct", 0.8)
        ratchet_demand = float(max_historical_peak) * ratchet_pct

    # Billed demand = max(current_peak, ratchet_demand, minimum_demand)
    min_demand = float(facility.rate_schedule.demand_rates.get("minimum_demand_kw", 0)) if facility.rate_schedule_id else 0
    billed_demand = max(current_peak_kw, ratchet_demand, min_demand)

    # Projected charge
    projected_charge = round(billed_demand * demand_rate, 2)

    # Risk assessment: what % of peak have we used with what % of month remaining
    pct_month_elapsed = days_elapsed / days_in_cycle
    pct_peak_used = (current_peak_kw / max_historical_peak * 100) if max_historical_peak > 0 else 0

    if pct_peak_used > 90:
        risk_level = "critical"
        risk_message = f"Already at {pct_peak_used:.0f}% of historical peak with {days_in_cycle - days_elapsed} days remaining"
    elif pct_peak_used > 75:
        risk_level = "high"
        risk_message = f"At {pct_peak_used:.0f}% of historical peak — reduce load during on-peak hours"
    elif pct_peak_used > 50:
        risk_level = "moderate"
        risk_message = f"At {pct_peak_used:.0f}% of historical peak — on track"
    else:
        risk_level = "low"
        risk_message = f"At {pct_peak_used:.0f}% of historical peak — well under control"

    return {
        "facility_id": str(facility_id),
        "billing_cycle": {
            "start": cycle_start.date().isoformat(),
            "end": cycle_end.date().isoformat(),
            "days_total": days_in_cycle,
            "days_elapsed": days_elapsed,
            "pct_elapsed": round(pct_month_elapsed * 100, 1),
        },
        "demand": {
            "current_peak_kw": round(current_peak_kw, 1),
            "ratchet_demand_kw": round(ratchet_demand, 1),
            "billed_demand_kw": round(billed_demand, 1),
            "demand_rate_per_kw": demand_rate,
            "projected_charge": projected_charge,
        },
        "risk": {
            "level": risk_level,
            "message": risk_message,
            "pct_of_historical_peak": round(pct_peak_used, 1),
        },
        "historical_peaks": historical_peaks,
        "ratchet": ratchet,
    }


# ── Savings Projection ──────────────────────────

async def compute_savings_projection(
    facility_id: UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Model annual savings from load shifting based on historical bills
    and current rate structure.
    """
    result = await db.execute(select(Facility).where(Facility.id == facility_id))
    facility = result.scalar_one_or_none()
    if not facility:
        return {"error": "Facility not found"}

    # Get bills
    result = await db.execute(
        select(UtilityBill)
        .where(UtilityBill.facility_id == facility_id)
        .order_by(desc(UtilityBill.period_start))
        .limit(12)
    )
    bills = list(result.scalars().all())

    if not bills:
        return {"error": "No utility bills — upload bills to see savings projections"}

    annual_cost = sum(float(b.total_cost or 0) for b in bills)
    annual_demand = sum(float(b.demand_charge or 0) for b in bills)
    annual_energy = sum(float(b.energy_charge or 0) for b in bills)
    avg_peak_kw = sum(float(b.peak_demand_kw or 0) for b in bills) / len(bills) if bills else 0

    # Load shifting savings model
    # Conservative: 8–12% demand charge reduction, 3–5% energy cost reduction
    demand_savings_pct = 0.10  # 10% demand charge reduction
    energy_savings_pct = 0.04  # 4% energy cost reduction

    demand_savings = annual_demand * demand_savings_pct
    energy_savings = annual_energy * energy_savings_pct
    total_savings = demand_savings + energy_savings

    # Advanced: if we have compressor data, refine the estimate
    result = await db.execute(
        select(Compressor).where(Compressor.facility_id == facility_id)
    )
    compressors = list(result.scalars().all())
    total_hp = sum(c.hp or 0 for c in compressors)

    if total_hp > 0 and facility.rate_schedule_id:
        # More precise estimate based on actual compressor capacity
        result = await db.execute(
            select(RateSchedule).where(RateSchedule.id == facility.rate_schedule_id)
        )
        rs = result.scalar_one_or_none()
        if rs and "tou" in rs.energy_rates:
            rates = [float(p.get("rate", 0)) for p in rs.energy_rates["tou"]]
            if len(rates) >= 2:
                rate_spread = max(rates) - min(rates)
                # kW shifted * hours shifted * rate spread * work days
                load_kw = total_hp * 0.746
                shifted_kw = load_kw * 0.30  # shift 30% of load
                peak_hours = 8  # typical on-peak window
                energy_savings = shifted_kw * peak_hours * rate_spread * 260  # work days/yr
                demand_savings = avg_peak_kw * 0.12 * 12  # 12% peak reduction, annual
                if rs.demand_rates.get("flat"):
                    demand_savings *= float(rs.demand_rates["flat"].get("rate", 0))
                elif rs.demand_rates.get("tou"):
                    max_demand_rate = max(float(p.get("rate", 0)) for p in rs.demand_rates["tou"])
                    demand_savings *= max_demand_rate
                total_savings = demand_savings + energy_savings

    return {
        "facility_id": str(facility_id),
        "current_costs": {
            "annual_total": round(annual_cost, 2),
            "annual_demand": round(annual_demand, 2),
            "annual_energy": round(annual_energy, 2),
            "avg_peak_kw": round(avg_peak_kw, 1),
            "bills_analyzed": len(bills),
        },
        "projected_savings": {
            "annual_total": round(total_savings, 2),
            "monthly_avg": round(total_savings / 12, 2),
            "demand_savings": round(demand_savings, 2),
            "energy_savings": round(energy_savings, 2),
            "demand_reduction_pct": round(demand_savings_pct * 100, 1) if not compressors else 12.0,
            "energy_reduction_pct": round(energy_savings_pct * 100, 1) if not compressors else 4.0,
        },
        "plant_capacity": {
            "total_compressors": len(compressors),
            "total_hp": total_hp,
            "estimated_load_kw": round(total_hp * 0.746, 1) if total_hp else None,
        },
    }
