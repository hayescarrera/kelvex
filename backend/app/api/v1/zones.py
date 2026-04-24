"""
Zones API — thermal zone management within a facility.

Endpoints:
  POST   /facilities/{id}/zones                     — Create zone
  GET    /facilities/{id}/zones                      — List zones
  GET    /facilities/{id}/zones/{zone_id}            — Get zone
  PATCH  /facilities/{id}/zones/{zone_id}            — Update zone
  DELETE /facilities/{id}/zones/{zone_id}            — Delete zone
  POST   /facilities/{id}/zones/{zone_id}/equipment  — Assign equipment to zone
  DELETE /facilities/{id}/zones/{zone_id}/equipment/{assignment_id} — Unassign
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility, Equipment
from app.models.zone import Zone, ZoneEquipment
from app.schemas.zone import (
    ZoneCreate, ZoneUpdate, ZoneResponse, ZoneListResponse,
    ZoneEquipmentCreate, ZoneEquipmentResponse,
)

router = APIRouter(prefix="/facilities/{facility_id}/zones", tags=["zones"])


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


async def _get_zone(zone_id: UUID, facility_id: UUID, db: AsyncSession) -> Zone:
    result = await db.execute(
        select(Zone).where(Zone.id == zone_id, Zone.facility_id == facility_id)
    )
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.post("", response_model=ZoneResponse, status_code=status.HTTP_201_CREATED)
async def create_zone(
    facility_id: UUID,
    data: ZoneCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new thermal zone in a facility."""
    await _get_facility(facility_id, current_user, db)
    zone = Zone(facility_id=facility_id, **data.model_dump())
    db.add(zone)
    await db.flush()
    await db.refresh(zone)
    return zone


@router.get("", response_model=ZoneListResponse)
async def list_zones(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all thermal zones for a facility."""
    await _get_facility(facility_id, current_user, db)
    count_result = await db.execute(
        select(func.count(Zone.id)).where(Zone.facility_id == facility_id)
    )
    total = count_result.scalar()
    result = await db.execute(
        select(Zone).where(Zone.facility_id == facility_id).order_by(Zone.name)
    )
    zones = result.scalars().all()
    return ZoneListResponse(zones=zones, total=total)


@router.get("/{zone_id}", response_model=ZoneResponse)
async def get_zone(
    facility_id: UUID,
    zone_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific thermal zone."""
    await _get_facility(facility_id, current_user, db)
    return await _get_zone(zone_id, facility_id, db)


@router.patch("/{zone_id}", response_model=ZoneResponse)
async def update_zone(
    facility_id: UUID,
    zone_id: UUID,
    data: ZoneUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a thermal zone's configuration."""
    await _get_facility(facility_id, current_user, db)
    zone = await _get_zone(zone_id, facility_id, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(zone, field, value)
    await db.flush()
    await db.refresh(zone)
    return zone


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(
    facility_id: UUID,
    zone_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a thermal zone."""
    await _get_facility(facility_id, current_user, db)
    zone = await _get_zone(zone_id, facility_id, db)
    await db.delete(zone)
    await db.commit()


@router.post("/{zone_id}/equipment", response_model=ZoneEquipmentResponse,
             status_code=status.HTTP_201_CREATED)
async def assign_equipment(
    facility_id: UUID,
    zone_id: UUID,
    data: ZoneEquipmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a piece of equipment to a zone."""
    await _get_facility(facility_id, current_user, db)
    await _get_zone(zone_id, facility_id, db)
    # Verify equipment belongs to same facility
    eq_result = await db.execute(
        select(Equipment).where(
            Equipment.id == data.equipment_id, Equipment.facility_id == facility_id
        )
    )
    if not eq_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Equipment not found in this facility")

    assignment = ZoneEquipment(
        zone_id=zone_id, equipment_id=data.equipment_id, role=data.role
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)
    return assignment


@router.delete("/{zone_id}/equipment/{assignment_id}",
               status_code=status.HTTP_204_NO_CONTENT)
async def unassign_equipment(
    facility_id: UUID,
    zone_id: UUID,
    assignment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an equipment assignment from a zone."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(ZoneEquipment).where(
            ZoneEquipment.id == assignment_id, ZoneEquipment.zone_id == zone_id
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await db.delete(assignment)
    await db.commit()
