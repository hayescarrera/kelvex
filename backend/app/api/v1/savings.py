"""
Savings Simulator API

Given a facility's bill history, model savings from various strategies.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from decimal import Decimal

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.billing import UtilityBill
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
