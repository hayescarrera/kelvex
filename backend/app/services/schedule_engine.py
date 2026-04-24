"""
Schedule Engine — background worker that evaluates schedules and triggers sequences.

Runs as an asyncio background task within the FastAPI app. Every tick:
  1. Loads all enabled schedules whose next_run_at <= now
  2. For each due schedule, triggers the linked control sequence
  3. Computes the next_run_at based on schedule_type/cron_expression
  4. Updates execution timestamps

Supports schedule types: cron, daily, weekly, one_time.
"""

import asyncio
import logging
from datetime import datetime, time as dt_time, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.control import ControlSequence, Schedule, AutomationRule, CommandQueue
from app.models.agent import EdgeAgent

logger = logging.getLogger("coldgrid.schedule_engine")


def _next_cron_run(cron_expr: str, after: datetime) -> datetime | None:
    """
    Compute the next run time from a cron expression.
    Supports standard 5-field cron: minute hour day_of_month month day_of_week.

    This is a simplified evaluator for common patterns. For production,
    consider using the `croniter` library for full cron spec support.
    """
    try:
        from croniter import croniter
        cron = croniter(cron_expr, after)
        return cron.get_next(datetime)
    except ImportError:
        # Fallback: simple parsing for common patterns
        pass
    except Exception as e:
        logger.warning(f"Failed to parse cron expression '{cron_expr}': {e}")
        return None

    # Basic fallback for simple patterns like "0 14 * * 1-5" (2pm weekdays)
    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return None
        minute, hour = int(parts[0]), int(parts[1])
        # Simple: next occurrence at that hour:minute, tomorrow if already past
        candidate = after.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= after:
            candidate += timedelta(days=1)
        return candidate
    except (ValueError, IndexError):
        return None


def _next_daily_run(
    start_time: dt_time | None, tz_name: str, after: datetime
) -> datetime | None:
    """Compute next daily run at the given start_time."""
    if not start_time:
        return None
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    local_now = after.astimezone(tz)
    candidate = local_now.replace(
        hour=start_time.hour, minute=start_time.minute,
        second=0, microsecond=0,
    )
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def _next_weekly_run(
    start_time: dt_time | None, days_of_week: list[int] | None,
    tz_name: str, after: datetime,
) -> datetime | None:
    """Compute next weekly run — only on specified days_of_week (0=Mon, 6=Sun)."""
    if not start_time or not days_of_week:
        return None
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    local_now = after.astimezone(tz)
    # Check up to 8 days ahead
    for offset in range(0, 8):
        candidate = (local_now + timedelta(days=offset)).replace(
            hour=start_time.hour, minute=start_time.minute,
            second=0, microsecond=0,
        )
        if candidate > local_now and candidate.weekday() in days_of_week:
            return candidate.astimezone(timezone.utc)
    return None


def compute_next_run(schedule: Schedule, after: datetime) -> datetime | None:
    """Compute the next run time for a schedule."""
    if schedule.schedule_type == "cron" and schedule.cron_expression:
        return _next_cron_run(schedule.cron_expression, after)
    elif schedule.schedule_type == "daily":
        return _next_daily_run(schedule.start_time, schedule.timezone, after)
    elif schedule.schedule_type == "weekly":
        return _next_weekly_run(
            schedule.start_time, schedule.days_of_week,
            schedule.timezone, after,
        )
    elif schedule.schedule_type == "one_time":
        # One-time schedules only run once — if already run, no next time
        if schedule.last_run_at:
            return None
        return schedule.next_run_at
    return None


class ScheduleEngine:
    """
    Evaluates schedules and triggers control sequences.

    Usage:
        engine = ScheduleEngine(session_factory=async_session)
        await engine.start()   # runs forever
        await engine.stop()    # graceful shutdown
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        tick_interval: int = 30,
    ):
        self._session_factory = session_factory
        self._tick_interval = tick_interval
        self._running = False

    async def start(self):
        """Start the schedule engine main loop."""
        logger.info("Schedule engine starting")
        self._running = True

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Schedule engine tick error: {e}", exc_info=True)
            await asyncio.sleep(self._tick_interval)

        logger.info("Schedule engine stopped")

    async def stop(self):
        """Graceful shutdown."""
        logger.info("Schedule engine shutting down")
        self._running = False

    async def _tick(self):
        """Check for due schedules and trigger their sequences."""
        now = datetime.now(timezone.utc)

        async with self._session_factory() as db:
            # Find all enabled schedules that are due
            result = await db.execute(
                select(Schedule).where(
                    Schedule.enabled == True,
                    Schedule.next_run_at != None,
                    Schedule.next_run_at <= now,
                )
            )
            due_schedules = result.scalars().all()

            for schedule in due_schedules:
                try:
                    await self._execute_schedule(db, schedule, now)
                except Exception as e:
                    logger.error(
                        f"Failed to execute schedule '{schedule.name}': {e}",
                        exc_info=True,
                    )

            if due_schedules:
                await db.commit()

    async def _execute_schedule(
        self, db: AsyncSession, schedule: Schedule, now: datetime
    ):
        """Execute a single schedule — trigger its linked sequence."""
        # Fetch the linked control sequence
        seq_result = await db.execute(
            select(ControlSequence).where(
                ControlSequence.id == schedule.control_sequence_id,
                ControlSequence.facility_id == schedule.facility_id,
            )
        )
        sequence = seq_result.scalar_one_or_none()
        if not sequence:
            logger.warning(
                f"Schedule '{schedule.name}' references missing sequence "
                f"{schedule.control_sequence_id}"
            )
            schedule.enabled = False
            return

        if not sequence.enabled:
            logger.info(
                f"Skipping schedule '{schedule.name}' — linked sequence is disabled"
            )
            # Still update next_run_at so we don't re-check every tick
            schedule.next_run_at = compute_next_run(schedule, now)
            return

        steps = sequence.steps or []
        if not steps:
            logger.warning(f"Sequence '{sequence.name}' has no steps — skipping")
            schedule.next_run_at = compute_next_run(schedule, now)
            schedule.last_run_at = now
            return

        # Find an agent for this facility
        agents_result = await db.execute(
            select(EdgeAgent).where(
                EdgeAgent.facility_id == schedule.facility_id,
                EdgeAgent.enabled == True,
            )
        )
        agents = agents_result.scalars().all()
        if not agents:
            logger.warning(
                f"No agents for facility {schedule.facility_id} — "
                f"cannot execute schedule '{schedule.name}'"
            )
            schedule.next_run_at = compute_next_run(schedule, now)
            return

        connected = [a for a in agents if a.connection_state == "connected"]
        agent = connected[0] if connected else agents[0]

        # Create commands from sequence steps
        sorted_steps = sorted(steps, key=lambda s: s.get("order", 0))
        commands_created = 0

        for step in sorted_steps:
            action = step.get("action")
            if not action or action == "wait":
                continue

            target_equipment_id = None
            target_zone_id = None
            target = step.get("target")

            if target:
                try:
                    from uuid import UUID as UUIDType
                    target_uuid = UUIDType(target)
                    zone_actions = {"set_setpoint", "adjust_setpoint", "set_humidity"}
                    if action in zone_actions:
                        target_zone_id = target_uuid
                    else:
                        target_equipment_id = target_uuid
                except (ValueError, AttributeError):
                    pass

            cmd = CommandQueue(
                facility_id=schedule.facility_id,
                agent_id=agent.id,
                command_type=action,
                target_equipment_id=target_equipment_id,
                target_zone_id=target_zone_id,
                parameters=step.get("params", {}),
                state="pending",
                priority=sequence.priority,
                issued_at=now,
                expires_at=now + timedelta(hours=1),
            )
            db.add(cmd)
            commands_created += 1

        # Update sequence state
        sequence.last_run_at = now
        sequence.run_count = (sequence.run_count or 0) + 1
        sequence.last_result = "pending"

        # Update agent pending count
        agent.pending_commands = (agent.pending_commands or 0) + commands_created

        # Update schedule timestamps and compute next run
        schedule.last_run_at = now
        schedule.next_run_at = compute_next_run(schedule, now)

        # Disable one-time schedules after execution
        if schedule.schedule_type == "one_time":
            schedule.enabled = False

        logger.info(
            f"Schedule '{schedule.name}' fired: {commands_created} commands "
            f"queued for sequence '{sequence.name}'. "
            f"Next run: {schedule.next_run_at}"
        )


# ── FastAPI Lifespan Integration ────────────────────────

_engine_instance: ScheduleEngine | None = None


async def start_schedule_engine(session_factory: async_sessionmaker):
    """Start the schedule engine as a background task."""
    global _engine_instance
    _engine_instance = ScheduleEngine(session_factory=session_factory)
    asyncio.create_task(_engine_instance.start())
    logger.info("Schedule engine background task started")


async def stop_schedule_engine():
    """Stop the schedule engine."""
    global _engine_instance
    if _engine_instance:
        await _engine_instance.stop()
        _engine_instance = None
