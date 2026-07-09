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
from app.core.security import get_current_user, get_facility_scoped
from app.models.user import User
from app.models.facility import Facility, Equipment
from app.models.zone import Zone, ZoneEquipment
from app.models.zone_sensor import ZoneSensor
from app.schemas.zone import (
    ZoneCreate, ZoneUpdate, ZoneResponse, ZoneListResponse,
    ZoneEquipmentCreate, ZoneEquipmentResponse,
    ZoneSensorCreate, ZoneSensorUpdate, ZoneSensorResponse, ZoneSensorListResponse,
)

router = APIRouter(prefix="/facilities/{facility_id}/zones", tags=["zones"])


async def _get_facility(facility_id: UUID, user: User, db: AsyncSession):
    return await get_facility_scoped(facility_id, user, db)


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


# ── Zone Sensor CRUD ─────────────────────────────────────────────────────────

def _sensor_to_response(s: ZoneSensor) -> ZoneSensorResponse:
    m = s.metadata_ or {}
    return ZoneSensorResponse(
        id=s.id,
        zone_id=s.zone_id,
        name=s.name,
        sensor_type=s.sensor_type,
        unit=s.unit,
        location_desc=s.location_desc,
        alarm_high=s.alarm_high,
        alarm_low=s.alarm_low,
        warn_high=s.warn_high,
        warn_low=s.warn_low,
        current_value=s.current_value,
        current_state=s.current_state or "normal",
        last_reading_at=s.last_reading_at,
        poll_interval_sec=s.poll_interval_sec,
        enabled=s.enabled,
        created_at=s.created_at,
        host=m.get("host"),
        port=m.get("port", 502),
        slave_id=m.get("slave_id", 1),
        register_address=m.get("register_address"),
        register_type=m.get("register_type", "holding"),
        data_type=m.get("data_type", "uint16"),
        scale=m.get("scale", 1.0),
        offset=m.get("offset", 0.0),
    )


@router.post("/{zone_id}/sensors", response_model=ZoneSensorResponse,
             status_code=status.HTTP_201_CREATED)
async def create_zone_sensor(
    facility_id: UUID,
    zone_id: UUID,
    data: ZoneSensorCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_facility(facility_id, current_user, db)
    await _get_zone(zone_id, facility_id, db)

    modbus_meta = {
        "host": data.host,
        "port": data.port,
        "slave_id": data.slave_id,
        "register_address": data.register_address,
        "register_type": data.register_type,
        "data_type": data.data_type,
        "scale": data.scale,
        "offset": data.offset,
    }
    sensor = ZoneSensor(
        zone_id=zone_id,
        name=data.name,
        sensor_type=data.sensor_type,
        unit=data.unit,
        location_desc=data.location_desc,
        alarm_high=data.alarm_high,
        alarm_low=data.alarm_low,
        warn_high=data.warn_high,
        warn_low=data.warn_low,
        poll_interval_sec=data.poll_interval_sec,
        enabled=data.enabled,
        metadata_=modbus_meta,
    )
    db.add(sensor)
    await db.flush()
    await db.refresh(sensor)
    return _sensor_to_response(sensor)


@router.get("/{zone_id}/sensors", response_model=ZoneSensorListResponse)
async def list_zone_sensors(
    facility_id: UUID,
    zone_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_facility(facility_id, current_user, db)
    await _get_zone(zone_id, facility_id, db)
    result = await db.execute(
        select(ZoneSensor).where(ZoneSensor.zone_id == zone_id).order_by(ZoneSensor.name)
    )
    sensors = result.scalars().all()
    return ZoneSensorListResponse(
        sensors=[_sensor_to_response(s) for s in sensors],
        total=len(sensors),
    )


@router.patch("/{zone_id}/sensors/{sensor_id}", response_model=ZoneSensorResponse)
async def update_zone_sensor(
    facility_id: UUID,
    zone_id: UUID,
    sensor_id: UUID,
    data: ZoneSensorUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_facility(facility_id, current_user, db)
    await _get_zone(zone_id, facility_id, db)
    result = await db.execute(
        select(ZoneSensor).where(ZoneSensor.id == sensor_id, ZoneSensor.zone_id == zone_id)
    )
    sensor = result.scalar_one_or_none()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    direct_fields = {"name", "sensor_type", "unit", "location_desc",
                     "alarm_high", "alarm_low", "warn_high", "warn_low",
                     "poll_interval_sec", "enabled"}
    modbus_fields = {"host", "port", "slave_id", "register_address",
                     "register_type", "data_type", "scale", "offset"}

    update = data.model_dump(exclude_unset=True)
    for field in direct_fields:
        if field in update:
            setattr(sensor, field, update[field])

    modbus_updates = {k: v for k, v in update.items() if k in modbus_fields}
    if modbus_updates:
        sensor.metadata_ = {**(sensor.metadata_ or {}), **modbus_updates}

    await db.flush()
    await db.refresh(sensor)
    return _sensor_to_response(sensor)


@router.delete("/{zone_id}/sensors/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone_sensor(
    facility_id: UUID,
    zone_id: UUID,
    sensor_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(ZoneSensor).where(ZoneSensor.id == sensor_id, ZoneSensor.zone_id == zone_id)
    )
    sensor = result.scalar_one_or_none()
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    await db.delete(sensor)
    await db.commit()
