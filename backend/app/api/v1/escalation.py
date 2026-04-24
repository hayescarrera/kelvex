"""
Alert Escalation API — policies, escalation events, and on-call configuration.

Endpoints:
  POST   /escalation/policies           — Create escalation policy
  GET    /escalation/policies           — List policies
  GET    /escalation/policies/{id}      — Get policy detail
  PATCH  /escalation/policies/{id}      — Update policy
  DELETE /escalation/policies/{id}      — Deactivate policy

  GET    /escalation/events             — List escalation events
  POST   /escalation/test/{policy_id}   — Test-fire an escalation
"""

from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.compliance import EscalationPolicy, EscalationEvent
from app.services.audit_service import log_activity

router = APIRouter(prefix="/escalation", tags=["escalation"])


# ── Schemas ──────────────────────────────────────

class EscalationLevel(BaseModel):
    level: int
    delay_minutes: int = 0
    notify: list[str]  # ["channel:<uuid>", "user:<uuid>"]
    label: str = ""


class PolicyCreate(BaseModel):
    name: str
    description: str | None = None
    levels: list[EscalationLevel]
    min_severity: str = "high"
    facility_ids: list[UUID] | None = None


class PolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    levels: list[EscalationLevel] | None = None
    min_severity: str | None = None
    facility_ids: list[UUID] | None = None
    is_active: bool | None = None


# ── Helpers ──────────────────────────────────────

def _policy_to_dict(p: EscalationPolicy) -> dict:
    return {
        "id": str(p.id),
        "org_id": str(p.org_id),
        "name": p.name,
        "description": p.description,
        "levels": p.levels,
        "min_severity": p.min_severity,
        "facility_ids": [str(f) for f in (p.facility_ids or [])],
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _event_to_dict(e: EscalationEvent) -> dict:
    return {
        "id": str(e.id),
        "alert_id": str(e.alert_id),
        "policy_id": str(e.policy_id),
        "level": e.level,
        "notified_targets": e.notified_targets,
        "escalated_at": e.escalated_at.isoformat() if e.escalated_at else None,
    }


# ── CRUD ─────────────────────────────────────────

@router.post("/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(
    data: PolicyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = EscalationPolicy(
        org_id=current_user.org_id,
        name=data.name,
        description=data.description,
        levels=[l.model_dump() for l in data.levels],
        min_severity=data.min_severity,
        facility_ids=[str(f) for f in data.facility_ids] if data.facility_ids else None,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    await log_activity(db, user=current_user, org_id=current_user.org_id, action="create",
                       resource_type="escalation_policy", resource_id=str(policy.id),
                       resource_name=policy.name,
                       summary=f"Created escalation policy: {policy.name} ({len(data.levels)} levels)")
    return _policy_to_dict(policy)


@router.get("/policies")
async def list_policies(
    active_only: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(EscalationPolicy).where(
        EscalationPolicy.org_id == current_user.org_id,
    )
    if active_only:
        q = q.where(EscalationPolicy.is_active == True)
    q = q.order_by(EscalationPolicy.name)
    result = await db.execute(q)
    policies = result.scalars().all()
    return {"policies": [_policy_to_dict(p) for p in policies], "total": len(policies)}


@router.get("/policies/{policy_id}")
async def get_policy(
    policy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EscalationPolicy).where(
            EscalationPolicy.id == policy_id,
            EscalationPolicy.org_id == current_user.org_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return _policy_to_dict(policy)


@router.patch("/policies/{policy_id}")
async def update_policy(
    policy_id: UUID,
    data: PolicyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EscalationPolicy).where(
            EscalationPolicy.id == policy_id,
            EscalationPolicy.org_id == current_user.org_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    updates = data.model_dump(exclude_unset=True)
    if "levels" in updates and updates["levels"] is not None:
        updates["levels"] = [l.model_dump() if hasattr(l, 'model_dump') else l for l in updates["levels"]]
    if "facility_ids" in updates and updates["facility_ids"] is not None:
        updates["facility_ids"] = [str(f) for f in updates["facility_ids"]]

    for k, v in updates.items():
        setattr(policy, k, v)
    await db.commit()
    await db.refresh(policy)
    return _policy_to_dict(policy)


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_policy(
    policy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EscalationPolicy).where(
            EscalationPolicy.id == policy_id,
            EscalationPolicy.org_id == current_user.org_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy.is_active = False
    await db.commit()


# ── Escalation Events ───────────────────────────

@router.get("/events")
async def list_escalation_events(
    alert_id: UUID | None = Query(None),
    policy_id: UUID | None = Query(None),
    limit: int = Query(100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(EscalationEvent)
        .join(EscalationPolicy, EscalationEvent.policy_id == EscalationPolicy.id)
        .where(EscalationPolicy.org_id == current_user.org_id)
    )
    if alert_id:
        q = q.where(EscalationEvent.alert_id == alert_id)
    if policy_id:
        q = q.where(EscalationEvent.policy_id == policy_id)
    q = q.order_by(EscalationEvent.escalated_at.desc()).limit(limit)
    result = await db.execute(q)
    events = result.scalars().all()
    return {"events": [_event_to_dict(e) for e in events], "total": len(events)}


@router.post("/test/{policy_id}")
async def test_escalation(
    policy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test-fire an escalation policy (no actual alert — dry run)."""
    result = await db.execute(
        select(EscalationPolicy).where(
            EscalationPolicy.id == policy_id,
            EscalationPolicy.org_id == current_user.org_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    # Return what would happen
    return {
        "policy": _policy_to_dict(policy),
        "test_result": {
            "would_fire_levels": len(policy.levels or []),
            "levels": [
                {
                    "level": l.get("level"),
                    "delay_minutes": l.get("delay_minutes"),
                    "notify_targets": l.get("notify", []),
                    "label": l.get("label", ""),
                }
                for l in (policy.levels or [])
            ],
        },
    }
