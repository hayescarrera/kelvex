"""
Notification Policies API — create, list, update, delete per-user alert delivery rules.

Endpoints:
  GET    /notifications/policies              — List policies for org/user
  POST   /notifications/policies              — Create policy
  GET    /notifications/policies/{id}         — Get policy
  PATCH  /notifications/policies/{id}         — Update policy
  DELETE /notifications/policies/{id}         — Delete policy
  POST   /notifications/policies/{id}/test    — Send test notification via this policy
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.notification_policy import NotificationPolicy

router = APIRouter(prefix="/notifications/policies", tags=["notifications"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class PolicyCreate(BaseModel):
    name: str = "Default"
    # Scope
    facility_ids: list[str] | None = None
    categories: list[str] | None = None
    min_severity: str = "high"
    # Channels
    channel_ids: list[str] | None = None
    # Quiet hours
    quiet_hours_enabled: bool = False
    quiet_hours_start: int = Field(22, ge=0, le=23)
    quiet_hours_end: int = Field(7, ge=0, le=23)
    quiet_hours_bypass_severity: str | None = "critical"
    # Cooldown
    cooldown_minutes: int = Field(60, ge=0, le=10080)  # max 1 week
    # Digest
    digest_mode: bool = False
    digest_interval_hours: int = Field(4, ge=1, le=24)
    # Escalation
    escalation_enabled: bool = False
    escalation_delay_minutes: int = Field(30, ge=1, le=1440)
    escalation_channel_ids: list[str] | None = None
    escalation_min_severity: str = "critical"
    # For whom: null = self, explicit = set by admin for another user
    user_id: str | None = None


class PolicyUpdate(BaseModel):
    name: str | None = None
    facility_ids: list[str] | None = None
    categories: list[str] | None = None
    min_severity: str | None = None
    channel_ids: list[str] | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: int | None = None
    quiet_hours_end: int | None = None
    quiet_hours_bypass_severity: str | None = None
    cooldown_minutes: int | None = None
    digest_mode: bool | None = None
    digest_interval_hours: int | None = None
    escalation_enabled: bool | None = None
    escalation_delay_minutes: int | None = None
    escalation_channel_ids: list[str] | None = None
    escalation_min_severity: str | None = None
    enabled: bool | None = None


VALID_SEVERITIES = {"info", "low", "medium", "high", "critical"}
VALID_CATEGORIES = {"temperature", "pressure", "equipment", "power", "security", "compliance", "refrigerant", "connectivity"}


def _validate_severity(s: str | None, field: str) -> None:
    if s and s not in VALID_SEVERITIES:
        raise HTTPException(422, detail=f"{field} must be one of {sorted(VALID_SEVERITIES)}")


def _policy_to_dict(p: NotificationPolicy) -> dict:
    return {
        "id": str(p.id),
        "org_id": str(p.org_id),
        "user_id": str(p.user_id) if p.user_id else None,
        "name": p.name,
        "facility_ids": p.facility_ids,
        "categories": p.categories,
        "min_severity": p.min_severity,
        "channel_ids": p.channel_ids,
        "quiet_hours_enabled": p.quiet_hours_enabled,
        "quiet_hours_start": p.quiet_hours_start,
        "quiet_hours_end": p.quiet_hours_end,
        "quiet_hours_bypass_severity": p.quiet_hours_bypass_severity,
        "cooldown_minutes": p.cooldown_minutes,
        "digest_mode": p.digest_mode,
        "digest_interval_hours": p.digest_interval_hours,
        "escalation_enabled": p.escalation_enabled,
        "escalation_delay_minutes": p.escalation_delay_minutes,
        "escalation_channel_ids": p.escalation_channel_ids,
        "escalation_min_severity": p.escalation_min_severity,
        "enabled": p.enabled,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_policies(
    mine_only: bool = Query(True, description="If true, return only policies for current user"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(NotificationPolicy).where(NotificationPolicy.org_id == current_user.org_id)
    if mine_only:
        q = q.where(
            (NotificationPolicy.user_id == current_user.id) |
            (NotificationPolicy.user_id == None)
        )
    q = q.order_by(NotificationPolicy.created_at.asc())
    result = await db.execute(q)
    policies = result.scalars().all()
    return {"policies": [_policy_to_dict(p) for p in policies], "total": len(policies)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_policy(
    data: PolicyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_severity(data.min_severity, "min_severity")
    _validate_severity(data.quiet_hours_bypass_severity, "quiet_hours_bypass_severity")
    _validate_severity(data.escalation_min_severity, "escalation_min_severity")

    target_user_id = current_user.id
    if data.user_id and current_user.is_admin:
        target_user_id = UUID(data.user_id)

    policy = NotificationPolicy(
        org_id=current_user.org_id,
        user_id=target_user_id,
        name=data.name,
        facility_ids=data.facility_ids,
        categories=data.categories,
        min_severity=data.min_severity,
        channel_ids=data.channel_ids,
        quiet_hours_enabled=data.quiet_hours_enabled,
        quiet_hours_start=data.quiet_hours_start,
        quiet_hours_end=data.quiet_hours_end,
        quiet_hours_bypass_severity=data.quiet_hours_bypass_severity,
        cooldown_minutes=data.cooldown_minutes,
        digest_mode=data.digest_mode,
        digest_interval_hours=data.digest_interval_hours,
        escalation_enabled=data.escalation_enabled,
        escalation_delay_minutes=data.escalation_delay_minutes,
        escalation_channel_ids=data.escalation_channel_ids,
        escalation_min_severity=data.escalation_min_severity,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return _policy_to_dict(policy)


@router.get("/{policy_id}")
async def get_policy(
    policy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NotificationPolicy).where(
            NotificationPolicy.id == policy_id,
            NotificationPolicy.org_id == current_user.org_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, detail="Policy not found")
    return _policy_to_dict(policy)


@router.patch("/{policy_id}")
async def update_policy(
    policy_id: UUID,
    data: PolicyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_severity(data.min_severity, "min_severity")
    _validate_severity(data.quiet_hours_bypass_severity, "quiet_hours_bypass_severity")
    _validate_severity(data.escalation_min_severity, "escalation_min_severity")

    result = await db.execute(
        select(NotificationPolicy).where(
            NotificationPolicy.id == policy_id,
            NotificationPolicy.org_id == current_user.org_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, detail="Policy not found")

    updates = data.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(policy, k, v)

    await db.commit()
    await db.refresh(policy)
    return _policy_to_dict(policy)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NotificationPolicy).where(
            NotificationPolicy.id == policy_id,
            NotificationPolicy.org_id == current_user.org_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, detail="Policy not found")
    await db.delete(policy)
    await db.commit()


@router.post("/{policy_id}/test", status_code=status.HTTP_200_OK)
async def test_policy(
    policy_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test notification via this policy's channels."""
    result = await db.execute(
        select(NotificationPolicy).where(
            NotificationPolicy.id == policy_id,
            NotificationPolicy.org_id == current_user.org_id,
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(404, detail="Policy not found")

    from app.services.notification_service import send_notification
    subject = "Kelvex — Test notification"
    body = (
        f"This is a test from notification policy <strong>{policy.name}</strong>.<br>"
        f"Minimum severity: {policy.min_severity} | Cooldown: {policy.cooldown_minutes} min | "
        f"Quiet hours: {'enabled' if policy.quiet_hours_enabled else 'disabled'}"
    )

    channel_ids = policy.channel_ids
    if channel_ids:
        for cid in channel_ids:
            try:
                await send_notification(db, org_id=current_user.org_id, subject=subject,
                                        body=body, channel_id=UUID(cid))
            except Exception as e:
                pass
    else:
        await send_notification(db, org_id=current_user.org_id, subject=subject, body=body)

    return {"status": "sent", "policy_id": str(policy_id)}
