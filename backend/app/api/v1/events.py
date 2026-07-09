"""
Server-Sent Events (SSE) endpoint for real-time updates.

Streams events to the frontend:
  - alert:fired, alert:resolved
  - command:completed, command:failed
  - telemetry:spike
  - activity:new

Clients connect with:
    const es = new EventSource('/api/v1/events/stream?token=<jwt>')
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db, async_session
from app.core.security import require_permission
from app.models.user import User

logger = logging.getLogger("coldgrid.events")
settings = get_settings()

router = APIRouter(prefix="/events", tags=["events"])

# ── In-memory pub/sub ──────────────────────────────
# Maps org_id -> set of asyncio.Queue instances
_subscribers: dict[UUID, set[asyncio.Queue]] = {}


async def publish_event(org_id: UUID, event_type: str, data: dict):
    """Publish an event to all connected clients for an org."""
    queues = _subscribers.get(org_id, set())
    payload = json.dumps({
        "type": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    dead = set()
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.add(q)
    # Clean up dead queues
    for q in dead:
        queues.discard(q)


def subscribe(org_id: UUID) -> asyncio.Queue:
    """Create a subscription queue for an org."""
    if org_id not in _subscribers:
        _subscribers[org_id] = set()
    q = asyncio.Queue(maxsize=100)
    _subscribers[org_id].add(q)
    return q


def unsubscribe(org_id: UUID, q: asyncio.Queue):
    """Remove a subscription queue."""
    queues = _subscribers.get(org_id)
    if queues:
        queues.discard(q)
        if not queues:
            del _subscribers[org_id]


async def _authenticate_from_token(token: str) -> User | None:
    """Validate JWT token and return user (SSE can't use Authorization header)."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        token_type = payload.get("type")
        if not user_id or token_type != "access":
            return None
    except JWTError:
        return None

    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


@router.get("/stream")
async def event_stream(token: str = Query(..., description="JWT access token")):
    """SSE endpoint — streams real-time events for the authenticated user's org.

    Connect with: `new EventSource('/api/v1/events/stream?token=<jwt>')`
    """
    user = await _authenticate_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    org_id = user.org_id

    async def generate():
        q = subscribe(org_id)
        try:
            # Send initial connection event
            yield f"event: connected\ndata: {json.dumps({'user': user.email, 'org_id': str(org_id)})}\n\n"

            while True:
                try:
                    # Wait for events with a 30s heartbeat
                    payload = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield f": heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe(org_id, q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/subscribers")
async def subscriber_count(
    # "admin:read" was never defined in the PERMISSIONS matrix, so this
    # endpoint rejected everyone. audit:view (kelvex_admin/owner/admin) is
    # the intended audience for a debug endpoint.
    current_user: User = Depends(require_permission("audit:view")),
):
    """Admin debug endpoint: show connected SSE subscriber counts."""
    return {
        "total_orgs": len(_subscribers),
        "total_connections": sum(len(qs) for qs in _subscribers.values()),
    }
