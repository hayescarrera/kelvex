"""
Preventive Maintenance API — work orders, recurring tasks, checklists.

Endpoints:
  POST   /maintenance/tasks              — Create maintenance task
  GET    /maintenance/tasks              — List tasks (filterable)
  GET    /maintenance/tasks/{id}         — Get task detail
  PATCH  /maintenance/tasks/{id}         — Update task (status, notes, checklist)
  DELETE /maintenance/tasks/{id}         — Cancel task

  GET    /maintenance/dashboard          — Summary stats
  GET    /maintenance/overdue            — Overdue tasks
"""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user, require_permission, get_facility_scoped
from app.models.user import User
from app.models.facility import Facility
from app.models.compliance import MaintenanceTask
from app.models.alert import Alert
from app.models.refrigerant import LeakEvent
from app.models.maintenance_event import MaintenanceEvent
from app.services.audit_service import log_activity

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


# ── Schemas ──────────────────────────────────────

class TaskCreate(BaseModel):
    facility_id: UUID
    title: str
    description: str | None = None
    category: str = "preventive"
    priority: str = "medium"
    equipment_id: UUID | None = None
    compressor_id: UUID | None = None
    is_recurring: bool = False
    recurrence_days: int | None = None
    recurrence_hours: int | None = None
    due_date: datetime | None = None
    assigned_to: UUID | None = None
    checklist: list[dict] | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    priority: str | None = None
    state: str | None = None
    due_date: datetime | None = None
    assigned_to: UUID | None = None
    completion_notes: str | None = None
    parts_used: list[dict] | None = None
    labor_hours: float | None = None
    checklist: list[dict] | None = None


# ── Helpers ──────────────────────────────────────

async def _verify_facility(facility_id: UUID, user: User, db: AsyncSession):
    await get_facility_scoped(facility_id, user, db)


def _task_to_dict(t: MaintenanceTask) -> dict:
    return {
        "id": str(t.id),
        "facility_id": str(t.facility_id),
        "org_id": str(t.org_id),
        "title": t.title,
        "description": t.description,
        "category": t.category,
        "priority": t.priority,
        "equipment_id": str(t.equipment_id) if t.equipment_id else None,
        "compressor_id": str(t.compressor_id) if t.compressor_id else None,
        "is_recurring": t.is_recurring,
        "recurrence_days": t.recurrence_days,
        "recurrence_hours": t.recurrence_hours,
        "state": t.state,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "assigned_to": str(t.assigned_to) if t.assigned_to else None,
        "completion_notes": t.completion_notes,
        "parts_used": t.parts_used,
        "labor_hours": t.labor_hours,
        "checklist": t.checklist,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ── CRUD ─────────────────────────────────────────

@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    current_user: User = Depends(require_permission("maintenance:log")),
    db: AsyncSession = Depends(get_db),
):
    await _verify_facility(data.facility_id, current_user, db)
    task = MaintenanceTask(
        **data.model_dump(),
        org_id=current_user.org_id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await log_activity(db, user=current_user, org_id=current_user.org_id, action="create",
                       resource_type="maintenance_task", resource_id=str(task.id),
                       resource_name=task.title, facility_id=data.facility_id,
                       summary=f"Created maintenance task: {task.title} ({task.category})")
    return _task_to_dict(task)


@router.get("/tasks")
async def list_tasks(
    facility_id: UUID | None = Query(None),
    state: str | None = Query(None),
    category: str | None = Query(None),
    priority: str | None = Query(None),
    assigned_to: UUID | None = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(MaintenanceTask).where(
        MaintenanceTask.org_id == current_user.org_id,
    )
    if facility_id:
        q = q.where(MaintenanceTask.facility_id == facility_id)
    if state:
        q = q.where(MaintenanceTask.state == state)
    if category:
        q = q.where(MaintenanceTask.category == category)
    if priority:
        q = q.where(MaintenanceTask.priority == priority)
    if assigned_to:
        q = q.where(MaintenanceTask.assigned_to == assigned_to)

    # Count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(MaintenanceTask.due_date.asc().nullslast(), MaintenanceTask.created_at.desc())
    q = q.offset(offset).limit(limit)
    result = await db.execute(q)
    tasks = result.scalars().all()
    return {"tasks": [_task_to_dict(t) for t in tasks], "total": total}


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MaintenanceTask).where(
            MaintenanceTask.id == task_id,
            MaintenanceTask.org_id == current_user.org_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_dict(task)


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: UUID,
    data: TaskUpdate,
    current_user: User = Depends(require_permission("maintenance:log")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MaintenanceTask).where(
            MaintenanceTask.id == task_id,
            MaintenanceTask.org_id == current_user.org_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    updates = data.model_dump(exclude_unset=True)

    # Handle state transitions
    if "state" in updates:
        new_state = updates["state"]
        if new_state == "in_progress" and not task.started_at:
            task.started_at = datetime.now(timezone.utc)
        elif new_state == "completed":
            task.completed_at = datetime.now(timezone.utc)
            # If recurring, spawn next occurrence
            if task.is_recurring and task.recurrence_days:
                next_due = (task.due_date or datetime.now(timezone.utc)) + timedelta(days=task.recurrence_days)
                next_task = MaintenanceTask(
                    facility_id=task.facility_id,
                    org_id=task.org_id,
                    title=task.title,
                    description=task.description,
                    category=task.category,
                    priority=task.priority,
                    equipment_id=task.equipment_id,
                    compressor_id=task.compressor_id,
                    is_recurring=True,
                    recurrence_days=task.recurrence_days,
                    recurrence_hours=task.recurrence_hours,
                    due_date=next_due,
                    assigned_to=task.assigned_to,
                    checklist=[{"item": c["item"], "done": False} for c in (task.checklist or [])],
                )
                db.add(next_task)

    for k, v in updates.items():
        setattr(task, k, v)

    await db.commit()
    await db.refresh(task)
    return _task_to_dict(task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(
    task_id: UUID,
    current_user: User = Depends(require_permission("maintenance:log")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MaintenanceTask).where(
            MaintenanceTask.id == task_id,
            MaintenanceTask.org_id == current_user.org_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.state = "cancelled"
    await db.commit()


# ── Auto Work-Order Generation ───────────────────

_SEVERITY_TO_PRIORITY = {"critical": "critical", "high": "high", "medium": "medium", "low": "low", "info": "low"}


@router.post("/tasks/from-alert", status_code=status.HTTP_201_CREATED)
async def create_task_from_alert(
    body: dict,
    current_user: User = Depends(require_permission("maintenance:log")),
    db: AsyncSession = Depends(get_db),
):
    """
    Auto-generate a corrective maintenance work order from an alert.

    Body: {"alert_id": "<uuid>"}

    Looks up the alert, maps severity → task priority, builds a title and
    description with full diagnostic context, and creates a scheduled task.
    """
    alert_id = body.get("alert_id")
    if not alert_id:
        raise HTTPException(status_code=400, detail="alert_id required")

    result = await db.execute(
        select(Alert).where(Alert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Verify org access via facility
    await _verify_facility(alert.facility_id, current_user, db)

    # Map alert context to task fields
    priority = _SEVERITY_TO_PRIORITY.get(alert.severity, "medium")
    category = "corrective"
    due_in_days = {"critical": 1, "high": 3, "medium": 7, "low": 14}.get(alert.severity, 7)
    due_date = datetime.now(timezone.utc) + timedelta(days=due_in_days)

    # Build description with context from alert
    ctx_lines = []
    if alert.context:
        for k, v in alert.context.items():
            ctx_lines.append(f"  {k}: {v}")
    ctx_str = "\n".join(ctx_lines) if ctx_lines else "  (no additional context)"

    description = (
        f"Auto-generated from {alert.severity.upper()} alert: {alert.title}\n\n"
        f"Alert message: {alert.message or 'N/A'}\n"
        f"Category: {alert.category}\n"
        f"Alert triggered at: {alert.triggered_at.strftime('%Y-%m-%d %H:%M UTC') if alert.triggered_at else 'unknown'}\n\n"
        f"Context:\n{ctx_str}"
    )

    task = MaintenanceTask(
        facility_id=alert.facility_id,
        org_id=current_user.org_id,
        title=f"Investigate: {alert.title}",
        description=description,
        category=category,
        priority=priority,
        due_date=due_date,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    await log_activity(
        db, user=current_user, org_id=current_user.org_id, action="create",
        resource_type="maintenance_task", resource_id=str(task.id),
        resource_name=task.title, facility_id=alert.facility_id,
        summary=f"Auto-generated work order from alert: {alert.title}",
    )

    return _task_to_dict(task)


@router.post("/tasks/from-leak-event", status_code=status.HTTP_201_CREATED)
async def create_task_from_leak_event(
    body: dict,
    current_user: User = Depends(require_permission("maintenance:log")),
    db: AsyncSession = Depends(get_db),
):
    """
    Auto-generate a corrective maintenance work order from a refrigerant leak event.

    Body: {"leak_event_id": "<uuid>"}

    Creates a high-priority corrective task with leak diagnostic context.
    """
    leak_event_id = body.get("leak_event_id")
    if not leak_event_id:
        raise HTTPException(status_code=400, detail="leak_event_id required")

    result = await db.execute(
        select(LeakEvent).where(LeakEvent.id == leak_event_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Leak event not found")

    await _verify_facility(event.facility_id, current_user, db)

    # Leak severity → priority mapping
    severity = getattr(event, "severity", None) or "medium"
    priority = _SEVERITY_TO_PRIORITY.get(severity, "high")
    due_date = datetime.now(timezone.utc) + timedelta(days=3)

    description = (
        f"Auto-generated from refrigerant leak event on {event.rack_name}\n\n"
        f"Detected: {event.detected_at.strftime('%Y-%m-%d') if event.detected_at else 'unknown'}\n"
        f"Status: {event.status}\n"
        f"Estimated loss: {f'{event.estimated_loss_lbs:.1f} lbs' if event.estimated_loss_lbs else 'unknown'}\n"
        f"Detection method: {event.detection_method or 'manual'}\n\n"
        f"Action required: Inspect circuit, identify leak source, repair and verify leak-free."
    )

    task = MaintenanceTask(
        facility_id=event.facility_id,
        org_id=current_user.org_id,
        title=f"Repair refrigerant leak — {event.rack_name}",
        description=description,
        category="corrective",
        priority=priority,
        due_date=due_date,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    await log_activity(
        db, user=current_user, org_id=current_user.org_id, action="create",
        resource_type="maintenance_task", resource_id=str(task.id),
        resource_name=task.title, facility_id=event.facility_id,
        summary=f"Auto-generated work order from leak event on {event.rack_name}",
    )

    return _task_to_dict(task)


# ── Dashboard & Overdue ──────────────────────────

@router.get("/dashboard")
async def maintenance_dashboard(
    facility_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    base = select(MaintenanceTask).where(MaintenanceTask.org_id == current_user.org_id)
    if facility_id:
        base = base.where(MaintenanceTask.facility_id == facility_id)

    # Counts by state
    states = {}
    for s in ["scheduled", "in_progress", "completed", "overdue", "cancelled"]:
        q = select(func.count()).select_from(
            base.where(MaintenanceTask.state == s).subquery()
        )
        states[s] = (await db.execute(q)).scalar() or 0

    # Overdue (scheduled + past due)
    overdue_q = select(func.count()).select_from(
        base.where(
            MaintenanceTask.state == "scheduled",
            MaintenanceTask.due_date < now,
        ).subquery()
    )
    overdue_count = (await db.execute(overdue_q)).scalar() or 0

    # Due this week
    week_end = now + timedelta(days=7)
    due_week_q = select(func.count()).select_from(
        base.where(
            MaintenanceTask.state.in_(["scheduled", "in_progress"]),
            MaintenanceTask.due_date <= week_end,
        ).subquery()
    )
    due_this_week = (await db.execute(due_week_q)).scalar() or 0

    # Completed last 30 days
    month_ago = now - timedelta(days=30)
    completed_q = select(func.count()).select_from(
        base.where(
            MaintenanceTask.state == "completed",
            MaintenanceTask.completed_at >= month_ago,
        ).subquery()
    )
    completed_30d = (await db.execute(completed_q)).scalar() or 0

    return {
        "by_state": states,
        "overdue": overdue_count,
        "due_this_week": due_this_week,
        "completed_30d": completed_30d,
    }


@router.get("/overdue")
async def list_overdue(
    facility_id: UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    q = select(MaintenanceTask).where(
        MaintenanceTask.org_id == current_user.org_id,
        MaintenanceTask.state == "scheduled",
        MaintenanceTask.due_date < now,
    )
    if facility_id:
        q = q.where(MaintenanceTask.facility_id == facility_id)
    q = q.order_by(MaintenanceTask.due_date.asc())
    result = await db.execute(q)
    tasks = result.scalars().all()
    return {"tasks": [_task_to_dict(t) for t in tasks], "total": len(tasks)}


# ── Maintenance Events (append-only log) ─────────

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


@router.get("/events")
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


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_maintenance_event(
    data: MaintenanceEventCreate,
    current_user: User = Depends(require_permission("maintenance:log")),
    db: AsyncSession = Depends(get_db),
):
    if data.event_type not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid event_type. Allowed: {sorted(VALID_EVENT_TYPES)}",
        )
    await get_facility_scoped(data.facility_id, current_user, db)

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
        summary=f"Logged {data.event_type} by {data.technician_name or current_user.email}",
    )
    return _event_to_dict(event)
