"""
Alerts & Events API — alarm management and audit log.

Endpoints:
  POST   /facilities/{id}/alerts              — Create alert
  GET    /facilities/{id}/alerts              — List alerts (filterable)
  GET    /facilities/{id}/alerts/{alert_id}   — Get alert
  PATCH  /facilities/{id}/alerts/{alert_id}   — Acknowledge / resolve alert
  GET    /facilities/{id}/events              — List events (audit log)
  GET    /alerts/summary                      — Cross-facility alert counts
"""

from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.alert import Alert, Event
from app.schemas.alert import (
    AlertCreate, AlertUpdate, AlertResponse, AlertListResponse,
    EventResponse, EventListResponse,
)
from app.api.v1.events import publish_event
from app.services.alert_dispatch import dispatch_alert_notifications, cancel_escalation

router = APIRouter(tags=["alerts"])


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


# ── Alerts ─────────────────────────────────────────

@router.post("/facilities/{facility_id}/alerts", response_model=AlertResponse,
             status_code=status.HTTP_201_CREATED)
async def create_alert(
    facility_id: UUID,
    data: AlertCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new alert for a facility."""
    await _get_facility(facility_id, current_user, db)
    facility = await _get_facility(facility_id, current_user, db)
    alert = Alert(facility_id=facility_id, **data.model_dump())
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    await publish_event(current_user.org_id, "alert:fired", {
        "id": str(alert.id), "severity": alert.severity,
        "title": alert.title, "facility_id": str(facility_id),
    })
    # Fire notifications — non-blocking, errors logged internally
    try:
        await dispatch_alert_notifications(db, alert, facility)
    except Exception:
        pass
    return alert


@router.get("/facilities/{facility_id}/alerts", response_model=AlertListResponse)
async def list_alerts(
    facility_id: UUID,
    state: str | None = Query(None, description="Filter by state: active, acknowledged, resolved"),
    severity: str | None = Query(None, description="Filter by severity: critical, high, medium, low"),
    category: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List alerts for a facility with optional state, severity, and category filters."""
    await _get_facility(facility_id, current_user, db)

    query = select(Alert).where(Alert.facility_id == facility_id)
    count_query = select(func.count(Alert.id)).where(Alert.facility_id == facility_id)

    if state:
        query = query.where(Alert.state == state)
        count_query = count_query.where(Alert.state == state)
    if severity:
        query = query.where(Alert.severity == severity)
        count_query = count_query.where(Alert.severity == severity)
    if category:
        query = query.where(Alert.category == category)
        count_query = count_query.where(Alert.category == category)

    total = (await db.execute(count_query)).scalar()
    result = await db.execute(
        query.order_by(Alert.triggered_at.desc()).offset(offset).limit(limit)
    )
    alerts = result.scalars().all()
    return AlertListResponse(alerts=alerts, total=total)


@router.get("/facilities/{facility_id}/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(
    facility_id: UUID,
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific alert by ID."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.facility_id == facility_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.patch("/facilities/{facility_id}/alerts/{alert_id}", response_model=AlertResponse)
async def update_alert(
    facility_id: UUID,
    alert_id: UUID,
    data: AlertUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge or resolve an alert."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.facility_id == facility_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    now = datetime.now(timezone.utc)
    transitioning_out = False
    if data.state == "acknowledged" and alert.state == "active":
        alert.state = "acknowledged"
        alert.acknowledged_by = current_user.id
        alert.acknowledged_at = now
        transitioning_out = True
    elif data.state == "resolved":
        alert.state = "resolved"
        alert.resolved_by = current_user.id
        alert.resolved_at = now
        if data.resolution_note:
            alert.resolution_note = data.resolution_note
        transitioning_out = True
    elif data.state == "suppressed":
        alert.state = "suppressed"
        transitioning_out = True
    elif data.state:
        raise HTTPException(status_code=400, detail=f"Invalid state transition to {data.state}")

    await db.flush()
    await db.refresh(alert)

    # Cancel pending escalation tasks when alert is no longer active
    if transitioning_out:
        try:
            await cancel_escalation(alert.id)
        except Exception:
            pass

    return alert


# ── Cross-facility alert summary ───────────────────

@router.get("/alerts/summary")
async def alert_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get active alert counts grouped by severity across all user's facilities."""
    result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .join(Facility, Alert.facility_id == Facility.id)
        .where(Facility.org_id == current_user.org_id, Alert.state == "active")
        .group_by(Alert.severity)
    )
    counts = {row[0]: row[1] for row in result.all()}
    total = sum(counts.values())
    return {
        "total_active": total,
        "by_severity": {
            "critical": counts.get("critical", 0),
            "high": counts.get("high", 0),
            "medium": counts.get("medium", 0),
            "low": counts.get("low", 0),
            "info": counts.get("info", 0),
        }
    }


# ── Org-wide alert list ────────────────────────────

@router.get("/alerts")
async def list_all_alerts(
    state: str | None = Query(None),
    severity: str | None = Query(None),
    facility_id: UUID | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List alerts across all org facilities, optionally filtered."""
    query = (
        select(Alert, Facility.name.label("facility_name"))
        .join(Facility, Alert.facility_id == Facility.id)
        .where(Facility.org_id == current_user.org_id)
    )
    count_query = (
        select(func.count(Alert.id))
        .join(Facility, Alert.facility_id == Facility.id)
        .where(Facility.org_id == current_user.org_id)
    )

    if state:
        query = query.where(Alert.state == state)
        count_query = count_query.where(Alert.state == state)
    if severity:
        query = query.where(Alert.severity == severity)
        count_query = count_query.where(Alert.severity == severity)
    if facility_id:
        query = query.where(Alert.facility_id == facility_id)
        count_query = count_query.where(Alert.facility_id == facility_id)

    total = (await db.execute(count_query)).scalar()
    result = await db.execute(
        query.order_by(Alert.triggered_at.desc()).offset(offset).limit(limit)
    )
    rows = result.all()
    alerts = []
    for row in rows:
        alert = row[0]
        d = {
            "id": str(alert.id),
            "facility_id": str(alert.facility_id),
            "facility_name": row[1],
            "title": alert.title,
            "category": alert.category,
            "severity": alert.severity,
            "state": alert.state,
            "triggered_at": alert.triggered_at.isoformat() if alert.triggered_at else None,
            "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "message": getattr(alert, "message", None),
            "measured_value": getattr(alert, "measured_value", None),
            "threshold_value": getattr(alert, "threshold_value", None),
        }
        alerts.append(d)
    return {"alerts": alerts, "total": total}


# ── Events (audit log) ────────────────────────────

@router.get("/facilities/{facility_id}/events", response_model=EventListResponse)
async def list_events(
    facility_id: UUID,
    event_type: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List audit-log events for a facility."""
    await _get_facility(facility_id, current_user, db)

    query = select(Event).where(Event.facility_id == facility_id)
    count_query = select(func.count(Event.id)).where(Event.facility_id == facility_id)

    if event_type:
        query = query.where(Event.event_type == event_type)
        count_query = count_query.where(Event.event_type == event_type)
    if source:
        query = query.where(Event.source == source)
        count_query = count_query.where(Event.source == source)

    total = (await db.execute(count_query)).scalar()
    result = await db.execute(
        query.order_by(Event.occurred_at.desc()).offset(offset).limit(limit)
    )
    events = result.scalars().all()
    return EventListResponse(events=events, total=total)
