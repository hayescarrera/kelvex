from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user, get_accessible_facility_ids, require_permission, get_facility_scoped
from app.models.user import User
from app.models.facility import Facility
from app.schemas.facility import (
    FacilityCreate,
    FacilityUpdate,
    FacilityResponse,
    FacilityListResponse,
)
from app.services.audit_service import log_activity

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=FacilityListResponse)
async def list_facilities(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    accessible: list = Depends(get_accessible_facility_ids),
    db: AsyncSession = Depends(get_db),
):
    """List facilities the current user can access (scoped by role + facility assignments)."""
    base_filter = [
        Facility.org_id == current_user.org_id,
        Facility.deleted_at == None,
    ]
    # Non-global roles only see assigned facilities
    if accessible is not None:
        base_filter.append(Facility.id.in_(accessible))

    count_result = await db.execute(
        select(func.count(Facility.id)).where(*base_filter)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Facility)
        .where(*base_filter)
        .order_by(Facility.name)
        .offset(skip)
        .limit(limit)
    )
    facilities = result.scalars().all()

    return FacilityListResponse(facilities=facilities, total=total)


@router.post("", response_model=FacilityResponse, status_code=status.HTTP_201_CREATED)
async def create_facility(
    data: FacilityCreate,
    current_user: User = Depends(require_permission("facilities:create")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new facility. Requires facilities:create permission."""
    facility = Facility(
        org_id=current_user.org_id,
        name=data.name,
        address=data.address,
        city=data.city,
        state=data.state,
        zip_code=data.zip_code,
        sqft=data.sqft,
        zone_types=data.zone_types,
    )
    db.add(facility)
    await db.flush()
    await db.refresh(facility)
    await log_activity(db, user=current_user, action="create", resource_type="facility",
                       resource_id=str(facility.id), resource_name=facility.name,
                       facility_id=facility.id, summary=f"Created facility '{facility.name}'")
    return facility


@router.get("/{facility_id}", response_model=FacilityResponse)
async def get_facility(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific facility."""
    facility = await get_facility_scoped(facility_id, current_user, db)
    return facility


@router.patch("/{facility_id}", response_model=FacilityResponse)
async def update_facility(
    facility_id: UUID,
    data: FacilityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a facility."""
    facility = await get_facility_scoped(facility_id, current_user, db)

    update_data = data.model_dump(exclude_unset=True)
    old_vals = {k: getattr(facility, k) for k in update_data}
    for field, value in update_data.items():
        setattr(facility, field, value)

    await db.flush()
    await db.refresh(facility)
    from app.services.audit_service import diff_changes
    changes = diff_changes(old_vals, update_data)
    await log_activity(db, user=current_user, action="update", resource_type="facility",
                       resource_id=str(facility.id), resource_name=facility.name,
                       facility_id=facility.id, changes=changes,
                       summary=f"Updated facility '{facility.name}'")
    return facility


@router.delete("/{facility_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_facility(
    facility_id: UUID,
    current_user: User = Depends(require_permission("facilities:delete")),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a facility. Requires facilities:delete permission."""
    facility = await get_facility_scoped(facility_id, current_user, db)

    facility.deleted_at = datetime.now(timezone.utc)
    await log_activity(db, user=current_user, action="delete", resource_type="facility",
                       resource_id=str(facility.id), resource_name=facility.name,
                       facility_id=facility.id, summary=f"Deleted facility '{facility.name}'")


# ── Floor Plan ─────────────────────────────────────

@router.get("/{facility_id}/floor-plan")
async def get_floor_plan(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the floor plan layout for a facility."""
    facility = await get_facility_scoped(facility_id, current_user, db)
    return {
        "facility_id": str(facility.id),
        "floor_plan": facility.floor_plan or {
            "canvas": {"width": 900, "height": 600, "background": "#f8f9fa", "grid_size": 20},
            "elements": [],
        },
    }


@router.put("/{facility_id}/floor-plan")
async def save_floor_plan(
    facility_id: UUID,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save floor plan layout for a facility."""
    facility = await get_facility_scoped(facility_id, current_user, db)
    facility.floor_plan = payload.get("floor_plan", payload)
    await db.commit()
    await db.refresh(facility)
    return {"facility_id": str(facility.id), "floor_plan": facility.floor_plan}
