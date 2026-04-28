"""
Tariff API — utility and rate schedule management.

Endpoints:
  POST   /tariffs/utilities                         — Create utility
  GET    /tariffs/utilities                          — List utilities
  POST   /tariffs/rate-schedules                     — Create rate schedule
  GET    /tariffs/rate-schedules                     — List rate schedules
  GET    /tariffs/rate-schedules/{id}                — Get rate schedule
  PATCH  /tariffs/rate-schedules/{id}                — Update rate schedule
  DELETE /tariffs/rate-schedules/{id}                — Delete rate schedule
  POST   /facilities/{id}/rate-schedule/{schedule_id} — Assign rate schedule to facility
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.tariff import Utility, RateSchedule
from app.models.facility import Facility
from app.schemas.tariff import (
    UtilityCreate, UtilityResponse, UtilityListResponse,
    RateScheduleCreate, RateScheduleUpdate, RateScheduleResponse, RateScheduleListResponse,
)

router = APIRouter(prefix="/tariffs", tags=["tariffs"])


# ── Helpers ──────────────────────────────────────

async def _get_schedule_for_mutation(
    schedule_id: UUID, user: User, db: AsyncSession
) -> RateSchedule:
    """
    Fetch a rate schedule and reject the request if a different org's facility
    already uses it. Rate schedules are shared reference data, so we can't
    org-scope them at the row level — this is the interim protection until we
    add a created_by_org_id column via migration.
    """
    result = await db.execute(select(RateSchedule).where(RateSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Rate schedule not found")

    other_org = (await db.execute(
        select(Facility.org_id).where(
            Facility.rate_schedule_id == schedule_id,
            Facility.org_id != user.org_id,
            Facility.deleted_at == None,
        ).limit(1)
    )).scalar_one_or_none()

    if other_org:
        raise HTTPException(
            status_code=403,
            detail="Rate schedule is assigned to another organization's facility",
        )

    return schedule


# ── Utilities ────────────────────────────────────

@router.post("/utilities", response_model=UtilityResponse, status_code=status.HTTP_201_CREATED)
async def create_utility(
    data: UtilityCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a utility company record."""
    utility = Utility(
        name=data.name,
        state=data.state,
        iso_region=data.iso_region,
        regulated=data.regulated,
    )
    db.add(utility)
    await db.commit()
    await db.refresh(utility)
    return utility


@router.get("/utilities", response_model=UtilityListResponse)
async def list_utilities(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all utilities."""
    result = await db.execute(select(Utility).order_by(Utility.name))
    utilities = list(result.scalars().all())
    return UtilityListResponse(utilities=utilities, total=len(utilities))


# ── Rate Schedules ───────────────────────────────

@router.post("/rate-schedules", response_model=RateScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_rate_schedule(
    data: RateScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a rate schedule with TOU periods, demand tiers, and ratchet clauses."""
    # Verify utility exists
    result = await db.execute(select(Utility).where(Utility.id == data.utility_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Utility not found")

    schedule = RateSchedule(
        utility_id=data.utility_id,
        schedule_name=data.schedule_name,
        description=data.description,
        sector=data.sector,
        effective_date=data.effective_date,
        end_date=data.end_date,
        demand_rates=data.demand_rates,
        energy_rates=data.energy_rates,
        fixed_charges=data.fixed_charges or {},
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.get("/rate-schedules", response_model=RateScheduleListResponse)
async def list_rate_schedules(
    utility_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List rate schedules, optionally filtered by utility."""
    query = select(RateSchedule).order_by(RateSchedule.schedule_name)
    if utility_id:
        query = query.where(RateSchedule.utility_id == utility_id)
    result = await db.execute(query)
    schedules = list(result.scalars().all())
    return RateScheduleListResponse(rate_schedules=schedules, total=len(schedules))


@router.get("/rate-schedules/{schedule_id}", response_model=RateScheduleResponse)
async def get_rate_schedule(
    schedule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a rate schedule by ID."""
    result = await db.execute(select(RateSchedule).where(RateSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Rate schedule not found")
    return schedule


@router.patch("/rate-schedules/{schedule_id}", response_model=RateScheduleResponse)
async def update_rate_schedule(
    schedule_id: UUID,
    data: RateScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a rate schedule."""
    schedule = await _get_schedule_for_mutation(schedule_id, current_user, db)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)

    await db.commit()
    await db.refresh(schedule)
    return schedule


@router.delete("/rate-schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rate_schedule(
    schedule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a rate schedule."""
    schedule = await _get_schedule_for_mutation(schedule_id, current_user, db)
    await db.delete(schedule)
    await db.commit()


# ── Facility assignment ──────────────────────────

assign_router = APIRouter(tags=["tariffs"])


@assign_router.post("/facilities/{facility_id}/rate-schedule/{schedule_id}")
async def assign_rate_schedule(
    facility_id: UUID,
    schedule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a rate schedule to a facility."""
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == current_user.org_id,
            Facility.deleted_at == None,
        )
    )
    facility = result.scalar_one_or_none()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    result = await db.execute(select(RateSchedule).where(RateSchedule.id == schedule_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Rate schedule not found")

    facility.rate_schedule_id = schedule_id
    await db.commit()
    return {"status": "ok", "facility_id": str(facility_id), "rate_schedule_id": str(schedule_id)}
