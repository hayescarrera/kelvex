"""
Automation Rule Engine — evaluates trigger conditions against live data.

Runs as an asyncio background task. Every tick:
  1. Loads all enabled automation rules
  2. For each rule, evaluates trigger_conditions against latest telemetry/zone state
  3. If conditions met and cooldown elapsed, executes the rule's actions
  4. Actions can: execute a sequence, create an alert, or send a notification

Condition format:
  {
    "all": [{"source": "zone:<id>", "metric": "temp", "operator": ">", "value": 5}],
    "any": [{"source": "facility", "metric": "demand_kw", "operator": ">", "value": 900}]
  }

All conditions in "all" must be true AND at least one in "any" (if present).
"""

import asyncio
import logging
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.control import AutomationRule, ControlSequence, CommandQueue
from app.models.agent import EdgeAgent
from app.models.alert import Alert
from app.models.zone import Zone
from app.models.facility import Facility, Equipment
from app.models.telemetry import Telemetry

logger = logging.getLogger("coldgrid.rule_engine")


# ── Condition Evaluation ────────────────────────────────────

OPERATORS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


async def _get_metric_value(
    db: AsyncSession, facility_id: UUID, condition: dict
) -> float | str | None:
    """
    Resolve a metric value from the database.
    Source formats:
      - "zone:<uuid>" → reads from Zone model (current_temp, current_humidity, state)
      - "equipment:<uuid>" → reads latest telemetry for that equipment
      - "facility" → reads facility-level aggregates
    """
    source = condition.get("source", "")
    metric = condition.get("metric", "")

    if source.startswith("zone:"):
        zone_id_str = source.split(":", 1)[1]
        try:
            zone_id = UUID(zone_id_str)
        except ValueError:
            return None
        result = await db.execute(
            select(Zone).where(Zone.id == zone_id, Zone.facility_id == facility_id)
        )
        zone = result.scalar_one_or_none()
        if not zone:
            return None
        # Map metric names to zone attributes
        zone_metrics = {
            "temp": zone.current_temp,
            "temperature": zone.current_temp,
            "current_temp": zone.current_temp,
            "humidity": zone.current_humidity,
            "current_humidity": zone.current_humidity,
            "door_open": 1.0 if zone.door_open else 0.0,
            "state": zone.state,
        }
        return zone_metrics.get(metric)

    elif source.startswith("equipment:"):
        equip_id_str = source.split(":", 1)[1]
        try:
            equip_id = UUID(equip_id_str)
        except ValueError:
            return None
        # Get latest telemetry reading for this equipment + metric
        result = await db.execute(
            select(Telemetry.value)
            .where(
                Telemetry.equipment_id == equip_id,
                Telemetry.metric_name == metric,
            )
            .order_by(Telemetry.time.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    elif source == "facility":
        # Facility-level metrics from aggregated zone/equipment data
        if metric == "demand_kw":
            # Sum latest kw_demand from all equipment telemetry
            result = await db.execute(
                select(func.sum(Telemetry.value))
                .join(Equipment, Equipment.id == Telemetry.equipment_id)
                .where(
                    Equipment.facility_id == facility_id,
                    Telemetry.metric_name == "kw_demand",
                    Telemetry.time >= datetime.now(timezone.utc) - timedelta(minutes=5),
                )
            )
            return result.scalar_one_or_none() or 0.0
        elif metric in ("avg_temp", "max_temp", "min_temp"):
            agg_fn = {"avg_temp": func.avg, "max_temp": func.max, "min_temp": func.min}[metric]
            result = await db.execute(
                select(agg_fn(Zone.current_temp))
                .where(Zone.facility_id == facility_id, Zone.current_temp != None)
            )
            return result.scalar_one_or_none()

    return None


async def evaluate_conditions(
    db: AsyncSession, facility_id: UUID, trigger_conditions: dict
) -> bool:
    """Evaluate the trigger_conditions dict against current state."""
    all_conditions = trigger_conditions.get("all", [])
    any_conditions = trigger_conditions.get("any", [])

    # All conditions in "all" must be true
    for cond in all_conditions:
        value = await _get_metric_value(db, facility_id, cond)
        if value is None:
            return False  # can't evaluate = not triggered
        op = OPERATORS.get(cond.get("operator", ""))
        if not op:
            return False
        threshold = cond.get("value")
        try:
            if not op(float(value), float(threshold)):
                return False
        except (TypeError, ValueError):
            # String comparison for state fields
            if not op(str(value), str(threshold)):
                return False

    # At least one condition in "any" must be true (if any exist)
    if any_conditions:
        any_met = False
        for cond in any_conditions:
            value = await _get_metric_value(db, facility_id, cond)
            if value is None:
                continue
            op = OPERATORS.get(cond.get("operator", ""))
            if not op:
                continue
            threshold = cond.get("value")
            try:
                if op(float(value), float(threshold)):
                    any_met = True
                    break
            except (TypeError, ValueError):
                if op(str(value), str(threshold)):
                    any_met = True
                    break
        if not any_met:
            return False

    # If we have no conditions at all, don't trigger
    if not all_conditions and not any_conditions:
        return False

    return True


# ── Action Execution ────────────────────────────────────────

async def execute_rule_actions(
    db: AsyncSession, rule: AutomationRule, now: datetime
):
    """Execute all actions defined in the rule."""
    actions = rule.actions or []

    for action in actions:
        action_type = action.get("type")

        if action_type == "execute_sequence":
            await _action_execute_sequence(db, rule, action, now)
        elif action_type == "create_alert":
            await _action_create_alert(db, rule, action, now)
        elif action_type == "send_notification":
            await _action_send_notification(db, rule, action)
        else:
            logger.warning(f"Unknown action type '{action_type}' in rule '{rule.name}'")


async def _action_execute_sequence(
    db: AsyncSession, rule: AutomationRule, action: dict, now: datetime
):
    """Execute a control sequence as a rule action."""
    sequence_id_str = action.get("target")
    if not sequence_id_str:
        return
    try:
        sequence_id = UUID(sequence_id_str)
    except ValueError:
        return

    seq_result = await db.execute(
        select(ControlSequence).where(
            ControlSequence.id == sequence_id,
            ControlSequence.facility_id == rule.facility_id,
        )
    )
    sequence = seq_result.scalar_one_or_none()
    if not sequence or not sequence.enabled:
        return

    steps = sequence.steps or []
    if not steps:
        return

    # Find agent
    agents_result = await db.execute(
        select(EdgeAgent).where(
            EdgeAgent.facility_id == rule.facility_id,
            EdgeAgent.enabled == True,
        )
    )
    agents = agents_result.scalars().all()
    if not agents:
        return

    connected = [a for a in agents if a.connection_state == "connected"]
    agent = connected[0] if connected else agents[0]

    sorted_steps = sorted(steps, key=lambda s: s.get("order", 0))
    commands_created = 0

    for step in sorted_steps:
        step_action = step.get("action")
        if not step_action or step_action == "wait":
            continue

        target_equipment_id = None
        target_zone_id = None
        target = step.get("target")
        if target:
            try:
                target_uuid = UUID(target)
                zone_actions = {"set_setpoint", "adjust_setpoint", "set_humidity"}
                if step_action in zone_actions:
                    target_zone_id = target_uuid
                else:
                    target_equipment_id = target_uuid
            except (ValueError, AttributeError):
                pass

        cmd = CommandQueue(
            facility_id=rule.facility_id,
            agent_id=agent.id,
            command_type=step_action,
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

    sequence.last_run_at = now
    sequence.run_count = (sequence.run_count or 0) + 1
    sequence.last_result = "pending"
    agent.pending_commands = (agent.pending_commands or 0) + commands_created

    logger.info(
        f"Rule '{rule.name}' executed sequence '{sequence.name}': "
        f"{commands_created} commands queued"
    )


async def _action_create_alert(
    db: AsyncSession, rule: AutomationRule, action: dict, now: datetime
):
    """Create an alert as a rule action."""
    alert = Alert(
        facility_id=rule.facility_id,
        title=action.get("message", f"Rule triggered: {rule.name}"),
        message=action.get("details", f"Automation rule '{rule.name}' conditions met"),
        severity=action.get("severity", "medium"),
        category="automation",
        alert_type=f"rule_{rule.name.lower().replace(' ', '_')}",
        state="active",
        triggered_at=now,
        context={"rule_id": str(rule.id), "rule_name": rule.name},
    )
    db.add(alert)
    logger.info(f"Rule '{rule.name}' created alert: {alert.title}")


async def _action_send_notification(
    db: AsyncSession, rule: AutomationRule, action: dict
):
    """Send a notification via configured channels as a rule action."""
    from app.services.notification_service import send_notification
    from app.models.facility import Facility

    # Resolve org_id from facility
    fac_result = await db.execute(
        select(Facility.org_id).where(Facility.id == rule.facility_id)
    )
    org_id = fac_result.scalar_one_or_none()
    if not org_id:
        logger.warning(f"Rule '{rule.name}': facility not found, skipping notification")
        return

    subject = action.get("subject", f"Rule triggered: {rule.name}")
    body = action.get("body", f"Automation rule '{rule.name}' conditions were met.")
    channel_id = action.get("channel_id")

    # Pass severity and category so routing filters work.
    # These come from a sibling create_alert action if present,
    # or from the notification action itself.
    severity = action.get("severity")
    category = action.get("category")
    if not severity or not category:
        # Look at sibling actions for an alert's severity/category
        for sibling in (rule.actions or []):
            if sibling.get("type") == "create_alert":
                severity = severity or sibling.get("severity")
                category = category or sibling.get("category", "automation")
                break
        severity = severity or "medium"
        category = category or "automation"

    try:
        logs = await send_notification(
            db, org_id, subject, body,
            facility_id=rule.facility_id,
            channel_id=channel_id,
            severity=severity,
            category=category,
        )
        sent = sum(1 for l in logs if l.status == "sent")
        logger.info(f"Rule '{rule.name}' sent {sent}/{len(logs)} notifications")
    except Exception as e:
        logger.error(f"Rule '{rule.name}' notification error: {e}")


# ── Engine ──────────────────────────────────────────────────

class RuleEngine:
    """
    Evaluates automation rules against current state.

    Usage:
        engine = RuleEngine(session_factory=async_session)
        await engine.start()
        await engine.stop()
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        tick_interval: int = 60,
    ):
        self._session_factory = session_factory
        self._tick_interval = tick_interval
        self._running = False

    async def start(self):
        """Start the rule engine main loop."""
        logger.info("Rule engine starting")
        self._running = True

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Rule engine tick error: {e}", exc_info=True)
            await asyncio.sleep(self._tick_interval)

        logger.info("Rule engine stopped")

    async def stop(self):
        """Graceful shutdown."""
        logger.info("Rule engine shutting down")
        self._running = False

    async def _tick(self):
        """Evaluate all enabled rules."""
        now = datetime.now(timezone.utc)

        async with self._session_factory() as db:
            result = await db.execute(
                select(AutomationRule).where(AutomationRule.enabled == True)
            )
            rules = result.scalars().all()

            triggered_count = 0
            for rule in rules:
                try:
                    fired = await self._evaluate_rule(db, rule, now)
                    if fired:
                        triggered_count += 1
                except Exception as e:
                    logger.error(
                        f"Error evaluating rule '{rule.name}': {e}",
                        exc_info=True,
                    )

            if triggered_count > 0:
                await db.commit()
                logger.info(f"Rule engine tick: {triggered_count}/{len(rules)} rules fired")

    async def _evaluate_rule(
        self, db: AsyncSession, rule: AutomationRule, now: datetime
    ) -> bool:
        """Evaluate a single rule. Returns True if it fired."""
        # Check cooldown
        if rule.last_triggered_at:
            cooldown_end = rule.last_triggered_at + timedelta(minutes=rule.cooldown_minutes)
            if now < cooldown_end:
                return False

        # Check max executions per day
        if rule.execution_count_today >= rule.max_executions_per_day:
            return False

        # Evaluate conditions
        conditions_met = await evaluate_conditions(
            db, rule.facility_id, rule.trigger_conditions
        )
        if not conditions_met:
            return False

        # Conditions met — execute actions
        await execute_rule_actions(db, rule, now)

        # Update rule execution state
        rule.last_triggered_at = now
        rule.execution_count_today = (rule.execution_count_today or 0) + 1

        return True


# ── FastAPI Lifespan Integration ────────────────────────

_engine_instance: RuleEngine | None = None


async def start_rule_engine(session_factory: async_sessionmaker):
    """Start the rule engine as a background task."""
    global _engine_instance
    _engine_instance = RuleEngine(session_factory=session_factory)
    asyncio.create_task(_engine_instance.start())
    logger.info("Rule engine background task started")


async def stop_rule_engine():
    """Stop the rule engine."""
    global _engine_instance
    if _engine_instance:
        await _engine_instance.stop()
        _engine_instance = None
