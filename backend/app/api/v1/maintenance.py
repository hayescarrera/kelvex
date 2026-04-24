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
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.compliance import MaintenanceTask
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
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == user.org_id,
            Facility.deleted_at == None,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Facility not found")


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
    current_user: User = Depends(get_current_user),
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
    task.state = "cancelled"
    await db.commit()


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
