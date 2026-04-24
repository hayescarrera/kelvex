"""
Tests for background engines: schedule_engine, rule_engine, polling_engine.

Focuses on:
  - Pure computation functions (compute_next_run, evaluate_conditions)
  - Engine tick logic with real DB fixtures
  - Edge cases: cooldowns, disabled rules, missing agents
"""
import uuid
from datetime import datetime, time as dt_time, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from tests.conftest import TestSessionLocal
from app.models.control import ControlSequence, Schedule, AutomationRule, CommandQueue
from app.models.agent import EdgeAgent
from app.models.zone import Zone
from app.models.alert import Alert
from app.models.facility import Facility, Equipment
from app.models.user import Organization

from app.services.schedule_engine import (
    _next_cron_run,
    _next_daily_run,
    _next_weekly_run,
    compute_next_run,
    ScheduleEngine,
)
from app.services.rule_engine import (
    _get_metric_value,
    evaluate_conditions,
    execute_rule_actions,
    RuleEngine,
)


# ── Schedule Engine: Pure Functions ─────────────────────


class TestNextCronRun:
    def test_simple_cron_pattern(self):
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        result = _next_cron_run("30 14 * * *", base)
        assert result is not None
        assert result > base
        assert result.hour == 14
        assert result.minute == 30

    def test_cron_past_today_goes_tomorrow(self):
        base = datetime(2025, 6, 15, 15, 0, tzinfo=timezone.utc)
        result = _next_cron_run("30 14 * * *", base)
        assert result is not None
        assert result > base

    def test_invalid_cron_returns_none(self):
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        result = _next_cron_run("invalid", base)
        assert result is None

    def test_too_few_fields(self):
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        result = _next_cron_run("30 14 *", base)
        assert result is None


class TestNextDailyRun:
    def test_future_time_today(self):
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        result = _next_daily_run(dt_time(14, 30), "UTC", base)
        assert result is not None
        assert result > base
        assert result.hour == 14
        assert result.minute == 30

    def test_past_time_goes_tomorrow(self):
        base = datetime(2025, 6, 15, 15, 0, tzinfo=timezone.utc)
        result = _next_daily_run(dt_time(10, 0), "UTC", base)
        assert result is not None
        assert result.day == 16

    def test_none_start_time(self):
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        assert _next_daily_run(None, "UTC", base) is None

    def test_invalid_timezone_falls_back(self):
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        result = _next_daily_run(dt_time(14, 0), "Not/A/TZ", base)
        assert result is not None


class TestNextWeeklyRun:
    def test_next_weekday(self):
        # 2025-06-15 is a Sunday (weekday=6)
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        result = _next_weekly_run(dt_time(9, 0), [0], "UTC", base)  # Monday
        assert result is not None
        assert result.weekday() == 0

    def test_no_days_returns_none(self):
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        assert _next_weekly_run(dt_time(9, 0), None, "UTC", base) is None
        assert _next_weekly_run(dt_time(9, 0), [], "UTC", base) is None

    def test_none_start_time(self):
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        assert _next_weekly_run(None, [0, 2, 4], "UTC", base) is None


class TestComputeNextRun:
    """Test compute_next_run dispatch with a mock Schedule-like object."""

    def _make_schedule(self, **kw):
        """Create a simple namespace that quacks like a Schedule."""
        class FakeSchedule:
            schedule_type = kw.get("schedule_type", "daily")
            cron_expression = kw.get("cron_expression", None)
            start_time = kw.get("start_time", dt_time(14, 0))
            timezone = kw.get("timezone", "UTC")
            days_of_week = kw.get("days_of_week", None)
            last_run_at = kw.get("last_run_at", None)
            next_run_at = kw.get("next_run_at", None)
        return FakeSchedule()

    def test_daily_schedule(self):
        s = self._make_schedule(schedule_type="daily")
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        result = compute_next_run(s, base)
        assert result is not None

    def test_cron_schedule(self):
        s = self._make_schedule(schedule_type="cron", cron_expression="0 8 * * *")
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        result = compute_next_run(s, base)
        assert result is not None

    def test_weekly_schedule(self):
        s = self._make_schedule(schedule_type="weekly", days_of_week=[0, 2, 4])
        base = datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc)
        result = compute_next_run(s, base)
        assert result is not None

    def test_one_time_not_yet_run(self):
        future = datetime(2025, 7, 1, 12, 0, tzinfo=timezone.utc)
        s = self._make_schedule(schedule_type="one_time", next_run_at=future, last_run_at=None)
        result = compute_next_run(s, datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc))
        assert result == future

    def test_one_time_already_run(self):
        s = self._make_schedule(
            schedule_type="one_time",
            last_run_at=datetime(2025, 6, 10, tzinfo=timezone.utc),
        )
        result = compute_next_run(s, datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc))
        assert result is None

    def test_unknown_type(self):
        s = self._make_schedule(schedule_type="unknown")
        result = compute_next_run(s, datetime(2025, 6, 15, 10, 0, tzinfo=timezone.utc))
        assert result is None


# ── Rule Engine: Condition Evaluation ───────────────────


@pytest_asyncio.fixture
async def engine_org():
    async with TestSessionLocal() as db:
        o = Organization(id=uuid.uuid4(), name="Engine Org", slug="engine-org")
        db.add(o)
        await db.commit()
        await db.refresh(o)
        return o


@pytest_asyncio.fixture
async def engine_facility(engine_org):
    async with TestSessionLocal() as db:
        f = Facility(
            id=uuid.uuid4(), org_id=engine_org.id, name="Engine Facility",
            city="Chicago", state="IL", sqft=40000,
        )
        db.add(f)
        await db.commit()
        await db.refresh(f)
        return f


@pytest_asyncio.fixture
async def engine_zone(engine_facility):
    async with TestSessionLocal() as db:
        z = Zone(
            id=uuid.uuid4(), facility_id=engine_facility.id,
            name="Freezer 1", zone_type="freezer",
            temp_setpoint=-10.0, temp_unit="F",
            current_temp=5.0, current_humidity=65.0,
        )
        db.add(z)
        await db.commit()
        await db.refresh(z)
        return z


@pytest_asyncio.fixture
async def engine_agent(engine_facility):
    async with TestSessionLocal() as db:
        a = EdgeAgent(
            id=uuid.uuid4(), facility_id=engine_facility.id,
            name="Agent Test", agent_key="test_key_engine",
            enabled=True, connection_state="connected",
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return a


@pytest.mark.asyncio
class TestGetMetricValue:
    async def test_zone_temp(self, engine_facility, engine_zone):
        async with TestSessionLocal() as db:
            val = await _get_metric_value(db, engine_facility.id, {
                "source": f"zone:{engine_zone.id}", "metric": "temp",
            })
            assert val == 5.0

    async def test_zone_humidity(self, engine_facility, engine_zone):
        async with TestSessionLocal() as db:
            val = await _get_metric_value(db, engine_facility.id, {
                "source": f"zone:{engine_zone.id}", "metric": "humidity",
            })
            assert val == 65.0

    async def test_zone_invalid_uuid(self, engine_facility):
        async with TestSessionLocal() as db:
            val = await _get_metric_value(db, engine_facility.id, {
                "source": "zone:not-a-uuid", "metric": "temp",
            })
            assert val is None

    async def test_zone_not_found(self, engine_facility):
        async with TestSessionLocal() as db:
            val = await _get_metric_value(db, engine_facility.id, {
                "source": f"zone:{uuid.uuid4()}", "metric": "temp",
            })
            assert val is None

    async def test_unknown_source(self, engine_facility):
        async with TestSessionLocal() as db:
            val = await _get_metric_value(db, engine_facility.id, {
                "source": "unknown:123", "metric": "temp",
            })
            assert val is None

    async def test_facility_avg_temp(self, engine_facility, engine_zone):
        async with TestSessionLocal() as db:
            val = await _get_metric_value(db, engine_facility.id, {
                "source": "facility", "metric": "avg_temp",
            })
            assert val is not None


@pytest.mark.asyncio
class TestEvaluateConditions:
    async def test_all_conditions_met(self, engine_facility, engine_zone):
        async with TestSessionLocal() as db:
            result = await evaluate_conditions(db, engine_facility.id, {
                "all": [
                    {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": ">", "value": 0},
                ],
            })
            assert result is True

    async def test_all_conditions_not_met(self, engine_facility, engine_zone):
        async with TestSessionLocal() as db:
            result = await evaluate_conditions(db, engine_facility.id, {
                "all": [
                    {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": "<", "value": 0},
                ],
            })
            assert result is False

    async def test_any_conditions(self, engine_facility, engine_zone):
        async with TestSessionLocal() as db:
            result = await evaluate_conditions(db, engine_facility.id, {
                "any": [
                    {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": ">", "value": 100},
                    {"source": f"zone:{engine_zone.id}", "metric": "humidity", "operator": ">", "value": 50},
                ],
            })
            assert result is True

    async def test_any_conditions_none_met(self, engine_facility, engine_zone):
        async with TestSessionLocal() as db:
            result = await evaluate_conditions(db, engine_facility.id, {
                "any": [
                    {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": ">", "value": 100},
                    {"source": f"zone:{engine_zone.id}", "metric": "humidity", "operator": ">", "value": 100},
                ],
            })
            assert result is False

    async def test_empty_conditions(self, engine_facility):
        async with TestSessionLocal() as db:
            result = await evaluate_conditions(db, engine_facility.id, {})
            assert result is False

    async def test_all_and_any_combined(self, engine_facility, engine_zone):
        async with TestSessionLocal() as db:
            result = await evaluate_conditions(db, engine_facility.id, {
                "all": [
                    {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": ">", "value": 0},
                ],
                "any": [
                    {"source": f"zone:{engine_zone.id}", "metric": "humidity", "operator": ">", "value": 50},
                ],
            })
            assert result is True

    async def test_invalid_operator(self, engine_facility, engine_zone):
        async with TestSessionLocal() as db:
            result = await evaluate_conditions(db, engine_facility.id, {
                "all": [
                    {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": "~", "value": 0},
                ],
            })
            assert result is False

    async def test_missing_value_returns_false(self, engine_facility):
        async with TestSessionLocal() as db:
            result = await evaluate_conditions(db, engine_facility.id, {
                "all": [
                    {"source": f"zone:{uuid.uuid4()}", "metric": "temp", "operator": ">", "value": 0},
                ],
            })
            assert result is False


# ── Rule Engine: Action Execution ────────────────────────


@pytest.mark.asyncio
class TestExecuteRuleActions:
    async def test_create_alert_action(self, engine_facility, engine_agent):
        async with TestSessionLocal() as db:
            rule = AutomationRule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Test Alert Rule", enabled=True,
                trigger_conditions={"all": []},
                actions=[{
                    "type": "create_alert",
                    "message": "Test alert",
                    "severity": "high",
                }],
                cooldown_minutes=5, max_executions_per_day=10,
            )
            db.add(rule)
            await db.flush()

            now = datetime.now(timezone.utc)
            await execute_rule_actions(db, rule, now)
            await db.flush()

            result = await db.execute(
                select(Alert).where(Alert.facility_id == engine_facility.id)
            )
            alerts = result.scalars().all()
            assert len(alerts) == 1
            assert alerts[0].severity == "high"
            assert "Test alert" in alerts[0].title

    async def test_execute_sequence_action(self, engine_facility, engine_zone, engine_agent):
        async with TestSessionLocal() as db:
            seq = ControlSequence(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Test Sequence", sequence_type="custom", enabled=True, priority=5,
                steps=[
                    {"order": 1, "action": "set_setpoint", "target": str(engine_zone.id), "params": {"value": -5}},
                    {"order": 2, "action": "wait"},
                ],
            )
            db.add(seq)
            await db.flush()

            rule = AutomationRule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Seq Rule", enabled=True,
                trigger_conditions={"all": []},
                actions=[{"type": "execute_sequence", "target": str(seq.id)}],
                cooldown_minutes=5, max_executions_per_day=10,
            )
            db.add(rule)
            await db.flush()

            now = datetime.now(timezone.utc)
            await execute_rule_actions(db, rule, now)
            await db.flush()

            result = await db.execute(
                select(CommandQueue).where(CommandQueue.facility_id == engine_facility.id)
            )
            commands = result.scalars().all()
            assert len(commands) == 1  # wait step is skipped
            assert commands[0].command_type == "set_setpoint"

    async def test_unknown_action_type(self, engine_facility, engine_agent):
        """Unknown action types should be silently logged, not crash."""
        async with TestSessionLocal() as db:
            rule = AutomationRule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Unknown Action Rule", enabled=True,
                trigger_conditions={"all": []},
                actions=[{"type": "bogus_action"}],
                cooldown_minutes=5, max_executions_per_day=10,
            )
            db.add(rule)
            await db.flush()

            now = datetime.now(timezone.utc)
            # Should not raise
            await execute_rule_actions(db, rule, now)


# ── Rule Engine: Tick Logic ──────────────────────────────


@pytest.mark.asyncio
class TestRuleEngineTick:
    async def test_rule_fires_and_updates_state(self, engine_facility, engine_zone, engine_agent):
        async with TestSessionLocal() as db:
            rule = AutomationRule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Temp Alert Rule", enabled=True,
                trigger_conditions={
                    "all": [
                        {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": ">", "value": 0},
                    ],
                },
                actions=[{"type": "create_alert", "message": "Temp high!", "severity": "critical"}],
                cooldown_minutes=5, max_executions_per_day=10,
                execution_count_today=0,
            )
            db.add(rule)
            await db.commit()

        engine = RuleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        await engine._tick()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(Alert).where(Alert.facility_id == engine_facility.id)
            )
            alerts = result.scalars().all()
            assert len(alerts) >= 1

            rule_result = await db.execute(
                select(AutomationRule).where(AutomationRule.name == "Temp Alert Rule")
            )
            updated_rule = rule_result.scalar_one()
            assert updated_rule.last_triggered_at is not None
            assert updated_rule.execution_count_today >= 1

    async def test_cooldown_prevents_re_fire(self, engine_facility, engine_zone, engine_agent):
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            rule = AutomationRule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Cooldown Rule", enabled=True,
                trigger_conditions={
                    "all": [
                        {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": ">", "value": 0},
                    ],
                },
                actions=[{"type": "create_alert", "message": "Should not fire again"}],
                cooldown_minutes=60, max_executions_per_day=10,
                execution_count_today=0,
                last_triggered_at=now - timedelta(minutes=5),  # Still in cooldown
            )
            db.add(rule)
            await db.commit()

        engine = RuleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        await engine._tick()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(Alert).where(Alert.facility_id == engine_facility.id)
            )
            alerts = result.scalars().all()
            assert len(alerts) == 0

    async def test_max_executions_prevents_fire(self, engine_facility, engine_zone, engine_agent):
        async with TestSessionLocal() as db:
            rule = AutomationRule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Max Exec Rule", enabled=True,
                trigger_conditions={
                    "all": [
                        {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": ">", "value": 0},
                    ],
                },
                actions=[{"type": "create_alert", "message": "Should not fire"}],
                cooldown_minutes=0, max_executions_per_day=5,
                execution_count_today=5,  # Already at max
            )
            db.add(rule)
            await db.commit()

        engine = RuleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        await engine._tick()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(Alert).where(Alert.facility_id == engine_facility.id)
            )
            assert len(result.scalars().all()) == 0

    async def test_disabled_rule_skipped(self, engine_facility, engine_zone, engine_agent):
        async with TestSessionLocal() as db:
            rule = AutomationRule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Disabled Rule", enabled=False,
                trigger_conditions={
                    "all": [
                        {"source": f"zone:{engine_zone.id}", "metric": "temp", "operator": ">", "value": 0},
                    ],
                },
                actions=[{"type": "create_alert", "message": "Should not fire"}],
                cooldown_minutes=0, max_executions_per_day=10,
            )
            db.add(rule)
            await db.commit()

        engine = RuleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        await engine._tick()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(Alert).where(Alert.facility_id == engine_facility.id)
            )
            assert len(result.scalars().all()) == 0


# ── Schedule Engine: Tick Logic ──────────────────────────


@pytest.mark.asyncio
class TestScheduleEngineTick:
    async def test_due_schedule_fires(self, engine_facility, engine_agent):
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            seq = ControlSequence(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Scheduled Seq", sequence_type="custom", enabled=True, priority=3,
                steps=[{"order": 1, "action": "power_off"}],
            )
            db.add(seq)
            await db.flush()

            sched = Schedule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Test Schedule", enabled=True,
                schedule_type="daily",
                start_time=dt_time(14, 0),
                timezone="UTC",
                control_sequence_id=seq.id,
                next_run_at=now - timedelta(minutes=1),  # Due
            )
            db.add(sched)
            await db.commit()

        engine = ScheduleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        await engine._tick()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(CommandQueue).where(CommandQueue.facility_id == engine_facility.id)
            )
            commands = result.scalars().all()
            assert len(commands) == 1

            sched_result = await db.execute(
                select(Schedule).where(Schedule.name == "Test Schedule")
            )
            updated = sched_result.scalar_one()
            assert updated.last_run_at is not None

    async def test_future_schedule_skipped(self, engine_facility, engine_agent):
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            seq = ControlSequence(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Future Seq", sequence_type="custom", enabled=True, priority=3,
                steps=[{"order": 1, "action": "power_on"}],
            )
            db.add(seq)
            await db.flush()

            sched = Schedule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Future Schedule", enabled=True,
                schedule_type="daily", start_time=dt_time(14, 0),
                timezone="UTC",
                control_sequence_id=seq.id,
                next_run_at=now + timedelta(hours=2),  # Not due
            )
            db.add(sched)
            await db.commit()

        engine = ScheduleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        await engine._tick()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(CommandQueue).where(CommandQueue.facility_id == engine_facility.id)
            )
            assert len(result.scalars().all()) == 0

    async def test_disabled_sequence_skipped(self, engine_facility, engine_agent):
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            seq = ControlSequence(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Disabled Seq", sequence_type="custom", enabled=False, priority=3,
                steps=[{"order": 1, "action": "power_off"}],
            )
            db.add(seq)
            await db.flush()

            sched = Schedule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="Disabled Seq Schedule", enabled=True,
                schedule_type="daily", start_time=dt_time(14, 0),
                timezone="UTC",
                control_sequence_id=seq.id,
                next_run_at=now - timedelta(minutes=1),
            )
            db.add(sched)
            await db.commit()

        engine = ScheduleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        await engine._tick()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(CommandQueue).where(CommandQueue.facility_id == engine_facility.id)
            )
            assert len(result.scalars().all()) == 0

    async def test_one_time_schedule_disables_after_run(self, engine_facility, engine_agent):
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            seq = ControlSequence(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="OneTime Seq", sequence_type="custom", enabled=True, priority=3,
                steps=[{"order": 1, "action": "power_cycle"}],
            )
            db.add(seq)
            await db.flush()

            sched = Schedule(
                id=uuid.uuid4(), facility_id=engine_facility.id,
                name="OneTime Schedule", enabled=True,
                schedule_type="one_time",
                start_time=dt_time(14, 0), timezone="UTC",
                control_sequence_id=seq.id,
                next_run_at=now - timedelta(minutes=1),
            )
            db.add(sched)
            await db.commit()

        engine = ScheduleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        await engine._tick()

        async with TestSessionLocal() as db:
            sched_result = await db.execute(
                select(Schedule).where(Schedule.name == "OneTime Schedule")
            )
            updated = sched_result.scalar_one()
            assert updated.enabled is False


# ── Engine Start/Stop ────────────────────────────────────


@pytest.mark.asyncio
class TestEngineLifecycle:
    async def test_rule_engine_stop(self):
        engine = RuleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        engine._running = True
        await engine.stop()
        assert engine._running is False

    async def test_schedule_engine_stop(self):
        engine = ScheduleEngine(session_factory=TestSessionLocal, tick_interval=9999)
        engine._running = True
        await engine.stop()
        assert engine._running is False
