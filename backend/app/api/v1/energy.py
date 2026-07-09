"""
Energy Optimization API — load shifting, demand forecasting, savings, and analytics opportunities.

Endpoints:
  GET  /facilities/{id}/energy/rate-windows           — Today's rate windows
  GET  /facilities/{id}/energy/precool-schedule        — Optimal pre-cool windows
  GET  /facilities/{id}/energy/demand-forecast          — Current cycle demand forecast
  GET  /facilities/{id}/energy/savings-projection       — Annual savings model
  GET  /facilities/{id}/energy/current-rate             — Current rate period
  GET  /facilities/{id}/energy/opportunities            — Energy-saving opportunities
  GET  /facilities/{id}/energy/opportunities/summary    — Aggregated opportunity summary
  PATCH /facilities/{id}/energy/opportunities/{opp_id} — Update opportunity status
  GET  /facilities/{id}/energy/system-config/{system_id} — Fetch analytics config
  PUT  /facilities/{id}/energy/system-config/{system_id} — Update analytics config
"""

from uuid import UUID
from datetime import datetime, timezone, date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user, get_facility_scoped
from app.models.user import User
from app.models.facility import Facility
from app.models.tariff import RateSchedule
from app.models.energy import EnergyOpportunity, EnergySystemConfig
from app.services.energy_optimizer import (
    get_rate_windows, get_current_rate,
    compute_precool_windows, compute_demand_forecast,
    compute_savings_projection,
)

router = APIRouter(prefix="/facilities/{facility_id}/energy", tags=["energy"])


async def _get_facility(facility_id: UUID, user: User, db: AsyncSession):
    return await get_facility_scoped(facility_id, user, db)


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


# ── Opportunity endpoints ──────────────────────────────────────────────────


@router.get("/opportunities")
async def list_opportunities(
    facility_id: UUID,
    status: str | None = Query(None, description="Filter by status: open, dismissed, work_order_created"),
    opp_type: str | None = Query(None, description="Filter by opportunity type"),
    system_id: UUID | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_facility(facility_id, current_user, db)

    q = select(EnergyOpportunity).where(EnergyOpportunity.facility_id == facility_id)
    if status:
        q = q.where(EnergyOpportunity.status == status)
    if opp_type:
        q = q.where(EnergyOpportunity.opp_type == opp_type)
    if system_id:
        q = q.where(EnergyOpportunity.system_id == system_id)
    q = q.order_by(EnergyOpportunity.estimated_usd_year.desc().nullslast()).limit(limit).offset(offset)

    result = await db.execute(q)
    opps = result.scalars().all()

    return {
        "facility_id": str(facility_id),
        "count": len(opps),
        "opportunities": [_opp_dict(o) for o in opps],
    }


@router.get("/opportunities/summary")
async def opportunities_summary(
    facility_id: UUID,
    status: str = Query("open"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(
            EnergyOpportunity.opp_type,
            func.count(EnergyOpportunity.id).label("count"),
            func.sum(EnergyOpportunity.estimated_usd_year).label("total_usd_year"),
            func.sum(EnergyOpportunity.estimated_kwh_year).label("total_kwh_year"),
        )
        .where(
            EnergyOpportunity.facility_id == facility_id,
            EnergyOpportunity.status == status,
        )
        .group_by(EnergyOpportunity.opp_type)
        .order_by(func.sum(EnergyOpportunity.estimated_usd_year).desc())
    )
    rows = result.all()

    total_usd = sum((r.total_usd_year or 0) for r in rows)
    total_kwh = sum((r.total_kwh_year or 0) for r in rows)

    return {
        "facility_id": str(facility_id),
        "status_filter": status,
        "total_estimated_usd_year": round(total_usd, 0),
        "total_estimated_kwh_year": round(total_kwh, 0),
        "by_type": [
            {
                "opp_type": r.opp_type,
                "count": r.count,
                "estimated_usd_year": round(r.total_usd_year or 0, 0),
                "estimated_kwh_year": round(r.total_kwh_year or 0, 0),
            }
            for r in rows
        ],
    }


class OpportunityPatch(BaseModel):
    status: Literal["open", "dismissed", "work_order_created"]
    work_order_id: UUID | None = None


@router.patch("/opportunities/{opp_id}")
async def patch_opportunity(
    facility_id: UUID,
    opp_id: UUID,
    body: OpportunityPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(EnergyOpportunity).where(
            EnergyOpportunity.id == opp_id,
            EnergyOpportunity.facility_id == facility_id,
        )
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    opp.status = body.status
    if body.work_order_id:
        opp.work_order_id = body.work_order_id
    await db.commit()
    await db.refresh(opp)
    return _opp_dict(opp)


# ── System config endpoints ────────────────────────────────────────────────


class SystemConfigUpdate(BaseModel):
    refrigerant: str | None = None
    condenser_type: str | None = None
    sct_floor_f: float | None = None
    design_approach_f: float | None = None
    defrost_heater_kw: float | None = None
    rated_tons: float | None = None


@router.get("/system-config/{system_id}")
async def get_system_config(
    facility_id: UUID,
    system_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(EnergySystemConfig).where(EnergySystemConfig.system_id == system_id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="No config found for this system")
    return _config_dict(cfg)


@router.put("/system-config/{system_id}")
async def update_system_config(
    facility_id: UUID,
    system_id: UUID,
    body: SystemConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(EnergySystemConfig).where(EnergySystemConfig.system_id == system_id)
    )
    cfg = result.scalar_one_or_none()
    if not cfg:
        raise HTTPException(status_code=404, detail="No config found for this system")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(cfg, field, value)
    await db.commit()
    await db.refresh(cfg)
    return _config_dict(cfg)


# ── Serialization helpers ──────────────────────────────────────────────────


def _opp_dict(o: EnergyOpportunity) -> dict:
    return {
        "id":                    str(o.id),
        "facility_id":           str(o.facility_id),
        "system_id":             str(o.system_id) if o.system_id else None,
        "opp_type":              o.opp_type,
        "status":                o.status,
        "window_start":          o.window_start.isoformat() if o.window_start else None,
        "window_end":            o.window_end.isoformat() if o.window_end else None,
        "current_value":         o.current_value,
        "target_value":          o.target_value,
        "estimated_kwh_year":    o.estimated_kwh_year,
        "estimated_usd_year":    o.estimated_usd_year,
        "confidence":            o.confidence,
        "recommended_action":    o.recommended_action,
        "evidence":              o.evidence,
        "work_order_id":         str(o.work_order_id) if o.work_order_id else None,
        "created_at":            o.created_at.isoformat() if o.created_at else None,
        "updated_at":            o.updated_at.isoformat() if o.updated_at else None,
    }


def _config_dict(c: EnergySystemConfig) -> dict:
    return {
        "system_id":          str(c.system_id),
        "refrigerant":        c.refrigerant,
        "condenser_type":     c.condenser_type,
        "sct_floor_f":        c.sct_floor_f,
        "design_approach_f":  c.design_approach_f,
        "defrost_heater_kw":  c.defrost_heater_kw,
        "rated_tons":         c.rated_tons,
    }
