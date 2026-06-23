"""
Maintenance Events API — append-only log of work performed.

Distinct from maintenance tasks (work orders). This is the permanent,
immutable record: what was done, by whom, when, and why.

Endpoints:
  GET    /maintenance-events         — List events (filterable by facility, equipment, type)
  POST   /maintenance-events         — Log a new maintenance event
  GET    /maintenance-events/{id}    — Get single event detail
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.maintenance_event import MaintenanceEvent
from app.services.audit_service import log_activity

router = APIRouter(prefix="/maintenance-events", tags=["maintenance_events"])

VALID_EVENT_TYPES = {
    "repair", "inspection", "service", "replacement",
    "refrigerant", "cleaning", "calibration", "pm", "other",
}


class MaintenanceEventCreate(BaseModel):
    facility_id: UUID
    equipment_id: UUID | None = None
    linked_alert_id: UUID | None = None
    linked_refrigerant_event_id: UUID | None = None
    event_type: str
    description: str
    technician_name: str | None = None
    technician_company: str | None = None
    occurred_at: datetime | None = None


def _event_to_dict(e: MaintenanceEvent) -> dict:
    return {
        "id": str(e.id),
        "org_id": str(e.org_id),
        "facility_id": str(e.facility_id) if e.facility_id else None,
        "equipment_id": str(e.equipment_id) if e.equipment_id else None,
        "linked_alert_id": str(e.linked_alert_id) if e.linked_alert_id else None,
        "linked_refrigerant_event_id": str(e.linked_refrigerant_event_id) if e.linked_refrigerant_event_id else None,
        "event_type": e.event_type,
        "description": e.description,
        "technician_name": e.technician_name,
        "technician_company": e.technician_company,
        "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
        "created_by": str(e.created_by) if e.created_by else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


async def _verify_facility(facility_id: UUID, user: User, db: AsyncSession) -> Facility:
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == user.org_id,
            Facility.deleted_at == None,
        )
    )
    fac = result.scalar_one_or_none()
    if not fac:
        raise HTTPException(status_code=404, detail="Facility not found")
    return fac


@router.get("")
async def list_maintenance_events(
    facility_id: UUID | None = Query(None),
    equipment_id: UUID | None = Query(None),
    event_type: str | None = Query(None),
    limit: int = Query(200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(MaintenanceEvent).where(MaintenanceEvent.org_id == current_user.org_id)
    if facility_id:
        q = q.where(MaintenanceEvent.facility_id == facility_id)
    if equipment_id:
        q = q.where(MaintenanceEvent.equipment_id == equipment_id)
    if event_type:
        q = q.where(MaintenanceEvent.event_type == event_type)
    q = q.order_by(MaintenanceEvent.occurred_at.desc()).limit(limit)
    result = await db.execute(q)
    events = result.scalars().all()
    return {"events": [_event_to_dict(e) for e in events], "total": len(events)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_maintenance_event(
    data: MaintenanceEventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.event_type not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid event_type. Allowed: {sorted(VALID_EVENT_TYPES)}",
        )

    await _verify_facility(data.facility_id, current_user, db)

    event = MaintenanceEvent(
        org_id=current_user.org_id,
        facility_id=data.facility_id,
        equipment_id=data.equipment_id,
        linked_alert_id=data.linked_alert_id,
        linked_refrigerant_event_id=data.linked_refrigerant_event_id,
        event_type=data.event_type,
        description=data.description,
        technician_name=data.technician_name,
        technician_company=data.technician_company,
        occurred_at=data.occurred_at or datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    await log_activity(
        db, user=current_user, org_id=current_user.org_id, action="create",
        resource_type="maintenance_event", resource_id=str(event.id),
        resource_name=f"{data.event_type} — {data.description[:60]}",
        facility_id=data.facility_id,
        summary=f"Logged {data.event_type} event by {data.technician_name or current_user.email}",
    )
    return _event_to_dict(event)


@router.get("/{event_id}")
async def get_maintenance_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MaintenanceEvent).where(
            MaintenanceEvent.id == event_id,
            MaintenanceEvent.org_id == current_user.org_id,
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Maintenance event not found")
    return _event_to_dict(event)
