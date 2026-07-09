"""
Agent Monitor — detects stale edge agents and creates connectivity alerts.

Runs every 60 seconds. Any agent that has sent at least one heartbeat but
hasn't heartbeated in STALE_THRESHOLD_MINUTES gets an 'agent_offline' alert.
The alert is auto-resolved by the heartbeat endpoint when the agent reconnects.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent import EdgeAgent
from app.models.alert import Alert
from app.models.control import CommandQueue
from app.models.facility import Facility

logger = logging.getLogger("kelvex.agent_monitor")

STALE_THRESHOLD_MINUTES = 5
# A command polled by an agent but never acknowledged is presumed lost after
# this long. It is marked failed (not re-queued: the agent may have executed
# it and only the ack was lost — re-running a control action unprompted is
# worse than asking the operator to re-issue it).
COMMAND_ACK_TIMEOUT_MINUTES = 15
_task: asyncio.Task | None = None


async def _run_monitor(session_factory: async_sessionmaker) -> None:
    while True:
        try:
            await asyncio.sleep(60)
            async with session_factory() as db:
                await _check_stale_agents(db)
                await _expire_unacked_commands(db)
                await db.commit()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Agent monitor error: {e}")


async def _expire_unacked_commands(db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=COMMAND_ACK_TIMEOUT_MINUTES)

    result = await db.execute(
        select(CommandQueue).where(
            CommandQueue.state == "sent",
            CommandQueue.sent_at.isnot(None),
            CommandQueue.sent_at < cutoff,
        )
    )
    stuck = result.scalars().all()

    for cmd in stuck:
        cmd.state = "failed"
        cmd.completed_at = now
        cmd.error_message = (
            f"No acknowledgment from edge agent within "
            f"{COMMAND_ACK_TIMEOUT_MINUTES} minutes of delivery. "
            "Verify the agent is online and re-issue the command if needed."
        )
        logger.warning(
            "command expired without ack",
            extra={"command_id": str(cmd.id), "command_type": cmd.command_type},
        )


async def _check_stale_agents(db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(minutes=STALE_THRESHOLD_MINUTES)

    result = await db.execute(
        select(EdgeAgent).where(
            EdgeAgent.enabled == True,
            EdgeAgent.last_heartbeat.isnot(None),
            EdgeAgent.last_heartbeat < stale_cutoff,
            EdgeAgent.connection_state != "disconnected",
        )
    )
    stale_agents = result.scalars().all()

    for agent in stale_agents:
        existing = await db.execute(
            select(Alert).where(
                Alert.agent_id == agent.id,
                Alert.alert_type == "agent_offline",
                Alert.state.in_(["active", "acknowledged"]),
            )
        )
        if existing.scalar_one_or_none():
            continue  # already alerted

        agent.connection_state = "stale"

        minutes_ago = int((now - agent.last_heartbeat).total_seconds() / 60)
        db.add(Alert(
            facility_id=agent.facility_id,
            agent_id=agent.id,
            severity="high",
            category="connectivity",
            alert_type="agent_offline",
            title=f"Edge Agent Offline: {agent.name}",
            message=(
                f"No heartbeat received for {minutes_ago} minutes. "
                "Zone temperature monitoring may be interrupted."
            ),
            trigger_value=agent.last_heartbeat.isoformat(),
            threshold_value=f"{STALE_THRESHOLD_MINUTES}m",
        ))
        logger.warning(
            "connectivity alert created",
            extra={"agent": agent.name, "agent_id": str(agent.id), "minutes_offline": minutes_ago},
        )


async def start_agent_monitor(session_factory: async_sessionmaker) -> None:
    global _task
    _task = asyncio.create_task(_run_monitor(session_factory))


async def stop_agent_monitor() -> None:
    global _task
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
