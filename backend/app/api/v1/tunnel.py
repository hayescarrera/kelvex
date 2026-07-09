"""
Tunnel Sessions API — audit log for controller access sessions.

Every time an authorized user opens a controller tunnel, a session record
is created. This is append-only from the outside: sessions are started and
ended, never edited.

Endpoints:
  GET    /tunnel/sessions              — List tunnel sessions
  POST   /tunnel/sessions              — Start a new tunnel session
  PATCH  /tunnel/sessions/{id}/end     — End an active session
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user, get_facility_scoped, require_permission
from app.models.user import User
from app.models.facility import Facility
from app.models.tunnel import TunnelSession
from app.models.agent import EdgeAgent
from app.services.audit_service import log_activity

router = APIRouter(prefix="/tunnel", tags=["tunnel"])


class StartSessionRequest(BaseModel):
    facility_id: UUID
    target_device: str | None = None
    agent_id: UUID | None = None
    notes: str | None = None


class EndSessionRequest(BaseModel):
    end_reason: str = "user_close"  # user_close | timeout | revoked | error


def _session_to_dict(s: TunnelSession) -> dict:
    duration_seconds = None
    if s.started_at and s.ended_at:
        duration_seconds = int((s.ended_at - s.started_at).total_seconds())

    return {
        "id": str(s.id),
        "org_id": str(s.org_id),
        "facility_id": str(s.facility_id) if s.facility_id else None,
        "agent_id": str(s.agent_id) if s.agent_id else None,
        "user_id": str(s.user_id) if s.user_id else None,
        "user_email": s.user_email,
        "target_device": s.target_device,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "end_reason": s.end_reason,
        "ip_address": s.ip_address,
        "notes": s.notes,
        "controller_url": s.controller_url,
        "duration_seconds": duration_seconds,
    }


async def _verify_facility(facility_id: UUID, user: User, db: AsyncSession):
    return await get_facility_scoped(facility_id, user, db)


@router.get("/sessions")
async def list_sessions(
    facility_id: UUID | None = Query(None),
    active_only: bool = Query(False),
    limit: int = Query(100),
    current_user: User = Depends(require_permission("tunnel:access")),
    db: AsyncSession = Depends(get_db),
):
    q = select(TunnelSession).where(TunnelSession.org_id == current_user.org_id)
    if facility_id:
        q = q.where(TunnelSession.facility_id == facility_id)
    if active_only:
        q = q.where(TunnelSession.ended_at == None)
    q = q.order_by(TunnelSession.started_at.desc()).limit(limit)
    result = await db.execute(q)
    sessions = result.scalars().all()
    return {"sessions": [_session_to_dict(s) for s in sessions], "total": len(sessions)}


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(
    data: StartSessionRequest,
    request: Request,
    current_user: User = Depends(require_permission("tunnel:access")),
    db: AsyncSession = Depends(get_db),
):
    await _verify_facility(data.facility_id, current_user, db)

    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
    if ip:
        ip = ip.split(",")[0].strip()

    # Copy controller_url from the agent record so the session is self-contained
    controller_url = None
    if data.agent_id:
        agent_result = await db.execute(
            select(EdgeAgent).where(
                EdgeAgent.id == data.agent_id,
                EdgeAgent.facility_id == data.facility_id,
            )
        )
        agent = agent_result.scalar_one_or_none()
        if agent:
            controller_url = agent.controller_url

    session = TunnelSession(
        org_id=current_user.org_id,
        facility_id=data.facility_id,
        agent_id=data.agent_id,
        user_id=current_user.id,
        user_email=current_user.email,
        target_device=data.target_device,
        ip_address=ip,
        notes=data.notes,
        controller_url=controller_url,
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    await log_activity(
        db, user=current_user, org_id=current_user.org_id, action="create",
        resource_type="tunnel_session", resource_id=str(session.id),
        resource_name=data.target_device or "controller",
        facility_id=data.facility_id,
        summary=f"Opened tunnel session to {data.target_device or 'controller'} from {ip}",
    )
    return _session_to_dict(session)


@router.post("/sessions/{session_id}/end")
async def end_session(
    session_id: UUID,
    data: EndSessionRequest,
    current_user: User = Depends(require_permission("tunnel:access")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TunnelSession).where(
            TunnelSession.id == session_id,
            TunnelSession.org_id == current_user.org_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.ended_at:
        raise HTTPException(status_code=409, detail="Session already ended")

    session.ended_at = datetime.now(timezone.utc)
    session.end_reason = data.end_reason
    await db.commit()
    await db.refresh(session)

    duration = int((session.ended_at - session.started_at).total_seconds())
    await log_activity(
        db, user=current_user, org_id=current_user.org_id, action="update",
        resource_type="tunnel_session", resource_id=str(session.id),
        resource_name=session.target_device or "controller",
        summary=f"Ended tunnel session ({duration}s, reason: {data.end_reason})",
    )
    return _session_to_dict(session)
