"""
Equipment API

CRUD endpoints for equipment within a facility.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility, Equipment
from app.schemas.equipment import (
    EquipmentCreate, EquipmentUpdate, EquipmentResponse, EquipmentListResponse,
)

router = APIRouter(
    prefix="/facilities/{facility_id}/equipment",
    tags=["equipment"],
)


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


@router.get("", response_model=EquipmentListResponse)
async def list_equipment(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all equipment for a facility."""
    await _get_facility(facility_id, current_user, db)

    count_result = await db.execute(
        select(func.count(Equipment.id)).where(Equipment.facility_id == facility_id)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Equipment)
        .where(Equipment.facility_id == facility_id)
        .order_by(Equipment.name)
    )
    equipment = result.scalars().all()

    return EquipmentListResponse(equipment=equipment, total=total)


@router.post("", response_model=EquipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    facility_id: UUID,
    data: EquipmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add equipment to a facility."""
    await _get_facility(facility_id, current_user, db)

    equipment = Equipment(
        facility_id=facility_id,
        name=data.name,
        equipment_type=data.equipment_type,
        manufacturer=data.manufacturer,
        model=data.model,
        controller_type=data.controller_type,
        protocol=data.protocol,
    )
    db.add(equipment)
    await db.flush()
    await db.refresh(equipment)
    return equipment


@router.get("/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(
    facility_id: UUID,
    equipment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific piece of equipment."""
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.facility_id == facility_id,
        )
    )
    equipment = result.scalar_one_or_none()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return equipment


@router.patch("/{equipment_id}", response_model=EquipmentResponse)
async def update_equipment(
    facility_id: UUID,
    equipment_id: UUID,
    data: EquipmentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update equipment details."""
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.facility_id == facility_id,
        )
    )
    equipment = result.scalar_one_or_none()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(equipment, field, value)

    await db.flush()
    await db.refresh(equipment)
    return equipment


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment(
    facility_id: UUID,
    equipment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove equipment from a facility."""
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.facility_id == facility_id,
        )
    )
    equipment = result.scalar_one_or_none()
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    await db.delete(equipment)
    await db.commit()
