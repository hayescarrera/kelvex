"""
Energy Optimization API — load shifting, demand forecasting, and savings.

Endpoints:
  GET  /facilities/{id}/energy/rate-windows           — Today's rate windows
  GET  /facilities/{id}/energy/precool-schedule        — Optimal pre-cool windows
  GET  /facilities/{id}/energy/demand-forecast          — Current cycle demand forecast
  GET  /facilities/{id}/energy/savings-projection       — Annual savings model
  GET  /facilities/{id}/energy/current-rate             — Current rate period
"""

from uuid import UUID
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.tariff import RateSchedule
from app.services.energy_optimizer import (
    get_rate_windows, get_current_rate,
    compute_precool_windows, compute_demand_forecast,
    compute_savings_projection,
)

router = APIRouter(prefix="/facilities/{facility_id}/energy", tags=["energy"])


async def _get_facility(facility_id: UUID, user: User, db: AsyncSession) -> Facility:
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == user.org_id,
            Facility.deleted_at == None,
        )
    )
    facility = result.scalar_one_or_none()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    return facility


@router.get("/current-rate")
async def current_rate(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current rate period and cost for the facility."""
    facility = await _get_facility(facility_id, current_user, db)
    if not facility.rate_schedule_id:
        raise HTTPException(status_code=400, detail="No rate schedule assigned to this facility")

    result = await db.execute(
        select(RateSchedule).where(RateSchedule.id == facility.rate_schedule_id)
    )
    rs = result.scalar_one_or_none()
    if not rs:
        raise HTTPException(status_code=404, detail="Rate schedule not found")

    now = datetime.now(timezone.utc)
    rate_info = get_current_rate(rs, now)
    rate_info["schedule_name"] = rs.schedule_name
    rate_info["timestamp"] = now.isoformat()
    return rate_info


@router.get("/rate-windows")
async def rate_windows(
    facility_id: UUID,
    target_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get hourly rate windows for the specified day (default: today)."""
    facility = await _get_facility(facility_id, current_user, db)
    if not facility.rate_schedule_id:
        raise HTTPException(status_code=400, detail="No rate schedule assigned")

    result = await db.execute(
        select(RateSchedule).where(RateSchedule.id == facility.rate_schedule_id)
    )
    rs = result.scalar_one_or_none()
    if not rs:
        raise HTTPException(status_code=404, detail="Rate schedule not found")

    td = target_date or datetime.now(timezone.utc).date()
    windows = get_rate_windows(rs, td)
    return {
        "facility_id": str(facility_id),
        "date": td.isoformat(),
        "schedule_name": rs.schedule_name,
        "windows": windows,
    }


@router.get("/precool-schedule")
async def precool_schedule(
    facility_id: UUID,
    target_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute optimal pre-cool schedule based on rate structure and zones."""
    await _get_facility(facility_id, current_user, db)
    return await compute_precool_windows(facility_id, db, target_date)


@router.get("/demand-forecast")
async def demand_forecast(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get demand charge forecast for the current billing cycle."""
    await _get_facility(facility_id, current_user, db)
    return await compute_demand_forecast(facility_id, db)


@router.get("/savings-projection")
async def savings_projection(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Model annual savings from load shifting optimization."""
    await _get_facility(facility_id, current_user, db)
    return await compute_savings_projection(facility_id, db)
