"""
Activity Log API — query the audit trail for an organization.

Endpoints:
    GET  /activity           — paginated activity log with filters
    GET  /activity/stats     — activity summary stats
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.audit_log import ActivityLog
from app.models.user import User

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
async def list_activity(
    resource_type: str | None = Query(None, description="Filter by resource type"),
    action: str | None = Query(None, description="Filter by action"),
    facility_id: UUID | None = Query(None, description="Filter by facility"),
    actor_id: UUID | None = Query(None, description="Filter by actor"),
    days: int = Query(30, ge=1, le=365, description="Lookback days"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List activity log entries for the current user's organization."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(ActivityLog)
        .where(
            ActivityLog.org_id == current_user.org_id,
            ActivityLog.created_at >= since,
        )
        .order_by(desc(ActivityLog.created_at))
    )

    if resource_type:
        q = q.where(ActivityLog.resource_type == resource_type)
    if action:
        q = q.where(ActivityLog.action == action)
    if facility_id:
        q = q.where(ActivityLog.facility_id == facility_id)
    if actor_id:
        q = q.where(ActivityLog.actor_id == actor_id)

    # Count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch page
    result = await db.execute(q.limit(limit).offset(offset))
    entries = result.scalars().all()

    return {
        "items": [
            {
                "id": str(e.id),
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "resource_name": e.resource_name,
                "facility_id": str(e.facility_id) if e.facility_id else None,
                "actor_id": str(e.actor_id) if e.actor_id else None,
                "actor_email": e.actor_email,
                "summary": e.summary,
                "changes": e.changes,
                "ip_address": e.ip_address,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
async def activity_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Summary stats for activity in the org."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = select(ActivityLog).where(
        ActivityLog.org_id == current_user.org_id,
        ActivityLog.created_at >= since,
    )

    # Total count
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0

    # By action
    action_result = await db.execute(
        select(ActivityLog.action, func.count())
        .where(
            ActivityLog.org_id == current_user.org_id,
            ActivityLog.created_at >= since,
        )
        .group_by(ActivityLog.action)
    )
    by_action = {r[0]: r[1] for r in action_result.all()}

    # By resource type
    resource_result = await db.execute(
        select(ActivityLog.resource_type, func.count())
        .where(
            ActivityLog.org_id == current_user.org_id,
            ActivityLog.created_at >= since,
        )
        .group_by(ActivityLog.resource_type)
    )
    by_resource = {r[0]: r[1] for r in resource_result.all()}

    # Unique actors
    actors = (await db.execute(
        select(func.count(func.distinct(ActivityLog.actor_id)))
        .where(
            ActivityLog.org_id == current_user.org_id,
            ActivityLog.created_at >= since,
        )
    )).scalar() or 0

    # Recent top actors
    top_actors_result = await db.execute(
        select(ActivityLog.actor_email, func.count().label("cnt"))
        .where(
            ActivityLog.org_id == current_user.org_id,
            ActivityLog.created_at >= since,
            ActivityLog.actor_email != None,
        )
        .group_by(ActivityLog.actor_email)
        .order_by(desc("cnt"))
        .limit(5)
    )
    top_actors = [{"email": r[0], "count": r[1]} for r in top_actors_result.all()]

    return {
        "total": total,
        "days": days,
        "by_action": by_action,
        "by_resource": by_resource,
        "unique_actors": actors,
        "top_actors": top_actors,
    }


@router.get("/resource-types")
async def resource_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all resource types that have activity logs."""
    result = await db.execute(
        select(ActivityLog.resource_type)
        .where(ActivityLog.org_id == current_user.org_id)
        .distinct()
    )
    return {"resource_types": [r[0] for r in result.all()]}
