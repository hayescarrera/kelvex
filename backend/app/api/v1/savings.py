"""
Savings Simulator API

Given a facility's bill history, model savings from various strategies.
"""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from decimal import Decimal

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.billing import UtilityBill
from app.models.refrigerant import RefrigerantAdd, RefrigerantCircuit
from app.services.demand_engine import SavingsSimulator, DemandChargeCalculator

router = APIRouter(prefix="/facilities/{facility_id}/savings", tags=["savings"])


@router.get("/simulate")
async def simulate_savings(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Simulate savings scenarios using the facility's bill history."""
    # Verify facility ownership
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == current_user.org_id,
        )
    )
    facility = result.scalar_one_or_none()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    # Get bills
    bills_result = await db.execute(
        select(UtilityBill)
        .where(UtilityBill.facility_id == facility_id)
        .order_by(UtilityBill.period_start)
    )
    bills = bills_result.scalars().all()

    if not bills:
        raise HTTPException(
            status_code=400,
            detail="No utility bills found. Upload bills first to run savings simulations."
        )

    # Calculate averages from bill history
    valid_bills = [b for b in bills if b.peak_demand_kw and b.demand_charge]
    if not valid_bills:
        raise HTTPException(
            status_code=400,
            detail="Bills must have peak_demand_kw and demand_charge to run simulations."
        )

    avg_peak = sum(float(b.peak_demand_kw) for b in valid_bills) / len(valid_bills)
    avg_demand_charge = sum(float(b.demand_charge) for b in valid_bills) / len(valid_bills)
    effective_rate = avg_demand_charge / avg_peak if avg_peak > 0 else 0

    # Run scenarios
    scenarios = SavingsSimulator.run_all_scenarios(
        peak_kw=avg_peak,
        demand_rate=effective_rate,
    )

    # Ratchet analysis
    ratchet_analysis = None
    if len(valid_bills) >= 3:
        calc = DemandChargeCalculator()
        bill_dicts = [
            {
                "period_start": b.period_start,
                "period_end": b.period_end,
                "peak_demand_kw": float(b.peak_demand_kw),
                "demand_charge": float(b.demand_charge),
                "total_kwh": float(b.total_kwh) if b.total_kwh else None,
                "total_cost": float(b.total_cost) if b.total_cost else None,
            }
            for b in valid_bills
        ]
        ratchet_results = calc.analyze_with_ratchet(bill_dicts)
        ratchet_months = [r for r in ratchet_results if r.ratchet_active]

        ratchet_analysis = {
            "months_affected": len(ratchet_months),
            "total_ratchet_penalty": sum(float(r.ratchet_penalty) for r in ratchet_months),
            "annual_ratchet_cost": sum(float(r.ratchet_penalty) for r in ratchet_months),
        }

    # Combined savings
    total_monthly = sum(s["monthly_savings"] for s in scenarios)
    total_annual = sum(s["annual_savings"] for s in scenarios)

    return {
        "facility_id": str(facility_id),
        "facility_name": facility.name,
        "summary": {
            "bills_analyzed": len(valid_bills),
            "avg_peak_demand_kw": round(avg_peak, 1),
            "avg_demand_charge": round(avg_demand_charge, 2),
            "effective_demand_rate": round(effective_rate, 2),
            "combined_monthly_savings": round(total_monthly, 2),
            "combined_annual_savings": round(total_annual, 2),
        },
        "scenarios": scenarios,
        "ratchet_analysis": ratchet_analysis,
    }


@router.get("/report")
async def savings_report(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Per-site quantified savings report combining energy optimization and
    refrigerant leak prevention impact.

    Methodology:
      - Demand response / load shifting: DOE Cold Storage study (2019) finds
        10-20% peak demand reduction from pre-cooling and load shed strategies.
        We use 10% as the conservative estimate.
      - Refrigerant charge impact on efficiency: ASHRAE Fundamentals (2021),
        Section 2.9 — each 1% of refrigerant undercharge increases compressor
        energy use by ~1.5-2%. We use 1.5% per 1% charge deficit as the
        efficiency penalty factor.
      - Refrigerant cost savings: avoided cost of refrigerant adds × current
        market rate. R-404A spot ~$12/lb, R-448A ~$18/lb (2024 market rates).
    """
    # Verify facility
    fac_result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == current_user.org_id,
        )
    )
    facility = fac_result.scalar_one_or_none()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    now = datetime.now(timezone.utc)
    year_ago = now - timedelta(days=365)

    # ── Energy savings (demand response + load shifting) ────────────
    bills_result = await db.execute(
        select(UtilityBill)
        .where(
            UtilityBill.facility_id == facility_id,
            UtilityBill.period_start >= year_ago,
        )
        .order_by(UtilityBill.period_start)
    )
    bills = bills_result.scalars().all()

    energy_data_available = len(bills) > 0
    annual_bill_total = sum(float(b.total_cost or 0) for b in bills)
    annual_demand_total = sum(float(b.demand_charge or 0) for b in bills)
    annual_energy_total = sum(float(b.energy_charge or 0) for b in bills)

    # Conservative DOE estimate: 10% demand reduction, 4% energy reduction
    demand_savings_est = annual_demand_total * 0.10
    energy_savings_est = annual_energy_total * 0.04
    total_energy_savings_est = demand_savings_est + energy_savings_est

    # ── Refrigerant savings ──────────────────────────────────────────
    # Sum refrigerant adds in the past 12 months
    adds_result = await db.execute(
        select(
            RefrigerantAdd.refrigerant_type,
            func.sum(RefrigerantAdd.amount_lbs).label("total_lbs"),
            func.sum(RefrigerantAdd.amount_lbs * RefrigerantAdd.cost_per_lb).label("total_cost"),
        )
        .where(
            RefrigerantAdd.facility_id == facility_id,
            RefrigerantAdd.added_at >= year_ago,
            RefrigerantAdd.cost_per_lb.isnot(None),
        )
        .group_by(RefrigerantAdd.refrigerant_type)
    )
    adds_by_type = adds_result.all()

    # Fallback market rates if cost_per_lb not recorded
    MARKET_RATES = {"R-404A": 12.0, "R-448A": 18.0, "R-134a": 8.0, "R-22": 35.0}

    # Also get total adds without cost filter for volume
    all_adds_result = await db.execute(
        select(
            func.sum(RefrigerantAdd.amount_lbs).label("total_lbs"),
        )
        .where(
            RefrigerantAdd.facility_id == facility_id,
            RefrigerantAdd.added_at >= year_ago,
        )
    )
    total_lbs_added = all_adds_result.scalar() or 0.0

    refrigerant_cost_tracked = sum(float(row.total_cost or 0) for row in adds_by_type)

    # Estimate cost if not tracked — use market rates
    if refrigerant_cost_tracked == 0 and total_lbs_added > 0:
        circuits_result = await db.execute(
            select(RefrigerantCircuit).where(
                RefrigerantCircuit.facility_id == facility_id,
                RefrigerantCircuit.is_active == True,
            ).limit(1)
        )
        circuit = circuits_result.scalar_one_or_none()
        ref_type = circuit.refrigerant_type if circuit else "R-404A"
        rate = MARKET_RATES.get(ref_type, 12.0)
        refrigerant_cost_tracked = total_lbs_added * rate

    # ── Refrigerant efficiency penalty ──────────────────────────────
    # ASHRAE: 1% charge loss → 1.5% efficiency loss
    # If we prevented all adds, we'd have avoided the efficiency penalty
    circuits_total_result = await db.execute(
        select(func.sum(RefrigerantCircuit.full_charge_lbs)).where(
            RefrigerantCircuit.facility_id == facility_id,
            RefrigerantCircuit.is_active == True,
            RefrigerantCircuit.full_charge_lbs.isnot(None),
        )
    )
    total_charge_lbs = circuits_total_result.scalar() or 0.0

    # Charge deficit fraction: what % of total charge was lost
    charge_deficit_pct = (total_lbs_added / total_charge_lbs * 100) if total_charge_lbs > 0 else 0.0
    energy_penalty_pct = min(charge_deficit_pct * 1.5, 20.0)  # cap at 20% penalty
    refrigerant_energy_penalty_cost = annual_energy_total * (energy_penalty_pct / 100) if energy_data_available else 0.0

    total_refrigerant_impact = refrigerant_cost_tracked + refrigerant_energy_penalty_cost
    total_quantified_savings = total_energy_savings_est + total_refrigerant_impact

    return {
        "facility_id": str(facility_id),
        "facility_name": facility.name,
        "report_period": {
            "start": year_ago.strftime("%Y-%m-%d"),
            "end": now.strftime("%Y-%m-%d"),
        },
        "energy_savings": {
            "available": energy_data_available,
            "bills_analyzed": len(bills),
            "annual_bill_total": round(annual_bill_total, 2),
            "demand_savings_est": round(demand_savings_est, 2),
            "energy_savings_est": round(energy_savings_est, 2),
            "total_est": round(total_energy_savings_est, 2),
            "demand_reduction_pct": 10.0,
            "energy_reduction_pct": 4.0,
        },
        "refrigerant_savings": {
            "total_lbs_added_12m": round(total_lbs_added, 1),
            "refrigerant_cost_12m": round(refrigerant_cost_tracked, 2),
            "charge_deficit_pct": round(charge_deficit_pct, 2),
            "energy_penalty_pct": round(energy_penalty_pct, 2),
            "refrigerant_energy_penalty_cost": round(refrigerant_energy_penalty_cost, 2),
            "total_refrigerant_impact": round(total_refrigerant_impact, 2),
        },
        "total_quantified_savings": round(total_quantified_savings, 2),
        "methodology": {
            "demand_response": "DOE Commercial Cold Storage Study (2019): 10–20% peak demand reduction from pre-cooling and load shed. Kelvex uses 10% (conservative).",
            "energy_optimization": "4% energy cost reduction from setpoint optimization and load shifting. Based on DOE Building Technologies Office guidelines.",
            "refrigerant_efficiency": "ASHRAE Fundamentals Handbook (2021) §2.9: each 1% refrigerant charge deficit increases compressor energy consumption by ~1.5%. Kelvex caps at 20% total penalty.",
            "refrigerant_cost": "Tracked from logged refrigerant additions. Market rate fallback: R-404A $12/lb, R-448A $18/lb, R-22 $35/lb (2024 spot prices).",
        },
    }
