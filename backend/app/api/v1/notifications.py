"""
Notifications API — manage notification channels and view delivery logs.

Endpoints:
  POST   /notifications/channels          — Create channel
  GET    /notifications/channels          — List channels
  PATCH  /notifications/channels/{id}     — Update channel
  DELETE /notifications/channels/{id}     — Delete channel
  POST   /notifications/channels/{id}/test — Send test notification
  GET    /notifications/logs              — List notification logs
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.notification import NotificationChannel, NotificationLog
from app.schemas.notification import (
    NotificationChannelCreate, NotificationChannelUpdate,
    NotificationChannelResponse, NotificationChannelListResponse,
    NotificationLogResponse, NotificationLogListResponse,
    NotificationTestRequest,
)
from app.services.notification_service import send_notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Channels ──────────────────────────────────

@router.post("/channels", response_model=NotificationChannelResponse,
             status_code=status.HTTP_201_CREATED)
async def create_channel(
    data: NotificationChannelCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new notification channel (email, webhook, or Slack)."""
    if data.channel_type not in ("email", "webhook", "slack", "sms"):
        raise HTTPException(status_code=400, detail="channel_type must be email, webhook, slack, or sms")
    channel = NotificationChannel(
        org_id=current_user.org_id,
        name=data.name,
        channel_type=data.channel_type,
        config=data.config,
        enabled=data.enabled,
        facility_ids=[str(f) for f in data.facility_ids] if data.facility_ids else None,
        min_severity=data.min_severity,
        categories=data.categories,
    )
    db.add(channel)
    await db.flush()
    await db.refresh(channel)
    return channel


@router.get("/channels", response_model=NotificationChannelListResponse)
async def list_channels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all notification channels for the current organization."""
    total = (await db.execute(
        select(func.count(NotificationChannel.id)).where(
            NotificationChannel.org_id == current_user.org_id
        )
    )).scalar()
    result = await db.execute(
        select(NotificationChannel)
        .where(NotificationChannel.org_id == current_user.org_id)
        .order_by(NotificationChannel.name)
    )
    return NotificationChannelListResponse(channels=result.scalars().all(), total=total)


@router.patch("/channels/{channel_id}", response_model=NotificationChannelResponse)
async def update_channel(
    channel_id: UUID,
    data: NotificationChannelUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a notification channel's configuration."""
    channel = await _get_channel(channel_id, current_user, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(channel, field, value)
    await db.flush()
    await db.refresh(channel)
    return channel


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a notification channel."""
    channel = await _get_channel(channel_id, current_user, db)
    await db.delete(channel)
    await db.commit()


@router.post("/channels/{channel_id}/test")
async def test_channel(
    channel_id: UUID,
    data: NotificationTestRequest = NotificationTestRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test notification through a specific channel."""
    channel = await _get_channel(channel_id, current_user, db)
    logs = await send_notification(
        db, current_user.org_id, data.subject, data.body, channel_id=channel.id
    )
    await db.commit()
    if logs and logs[0].status == "failed":
        return {"success": False, "error": logs[0].error_message}
    return {"success": True}


# ── Logs ──────────────────────────────────────

@router.get("/logs", response_model=NotificationLogListResponse)
async def list_logs(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent notification delivery logs."""
    total = (await db.execute(
        select(func.count(NotificationLog.id)).where(
            NotificationLog.org_id == current_user.org_id
        )
    )).scalar()
    result = await db.execute(
        select(NotificationLog)
        .where(NotificationLog.org_id == current_user.org_id)
        .order_by(NotificationLog.sent_at.desc())
        .limit(limit)
    )
    return NotificationLogListResponse(logs=result.scalars().all(), total=total)


# ── Helpers ───────────────────────────────────

async def _get_channel(channel_id: UUID, user: User, db: AsyncSession) -> NotificationChannel:
    result = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.org_id == user.org_id,
        )
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Notification channel not found")
    return channel
