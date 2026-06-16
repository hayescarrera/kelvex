"""
Controls & Automation models.

ControlSequence — a named automation recipe (e.g. "Pre-cool before TOU peak")
ControlAction   — a single step in a sequence (set compressor to X, adjust setpoint, etc.)
Schedule        — time-based triggers for control sequences
AutomationRule  — condition-based triggers (if temp > X and time in peak, then...)
CommandQueue    — outbound commands to edge agents
"""

import uuid
from datetime import datetime, time, timezone
from sqlalchemy import (
    String, Float, Integer, Boolean, DateTime, Time, ForeignKey, Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class ControlSequence(Base):
    """A named automation recipe — the building block of the controls layer."""
    __tablename__ = "control_sequences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    sequence_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # demand_response, pre_cool, defrost, load_shed, setpoint_adjust, custom
    # Execution
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)  # 1=highest, 99=lowest
    # The steps to execute (ordered list)
    steps: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    """
    steps format:
    [
      {"order": 1, "action": "set_setpoint", "target": "<zone_id>", "params": {"temp": -5, "unit": "F"}},
      {"order": 2, "action": "stage_compressor", "target": "<equip_id>", "params": {"stage": 2}},
      {"order": 3, "action": "wait", "params": {"minutes": 15}},
      {"order": 4, "action": "set_setpoint", "target": "<zone_id>", "params": {"temp": 0, "unit": "F"}},
    ]
    """
    # Conditions for execution (optional — if set, auto-triggers)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    """
    conditions format:
    {
      "all": [
        {"metric": "facility.demand_kw", "operator": ">", "value": 900},
        {"metric": "time.tou_period", "operator": "==", "value": "on_peak"},
      ]
    }
    """
    # Execution state
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[str] = mapped_column(String(20), nullable=True)  # success, partial, failed
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    # Audit
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<ControlSequence {self.name} ({self.sequence_type})>"


class Schedule(Base):
    """Time-based triggers for control sequences."""
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    control_sequence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control_sequences.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Schedule definition
    schedule_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # daily, weekly, monthly, cron, one_time
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=True)  # "0 14 * * 1-5"
    days_of_week: Mapped[dict] = mapped_column(JSONB, nullable=True)  # [0,1,2,3,4] = Mon-Fri
    start_time: Mapped[time] = mapped_column(Time, nullable=True)
    end_time: Mapped[time] = mapped_column(Time, nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Chicago")
    # Next execution
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<Schedule {self.name} ({self.schedule_type})>"


class AutomationRule(Base):
    """Condition-based triggers — the rules engine."""
    __tablename__ = "automation_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Trigger conditions
    trigger_conditions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    """
    Format:
    {
      "all": [
        {"source": "zone:<id>", "metric": "temp", "operator": ">", "value": 5},
        {"source": "facility", "metric": "demand_kw", "operator": ">", "value": 900},
      ],
      "any": [
        {"source": "equipment:<id>", "metric": "discharge_pressure", "operator": ">", "value": 280},
      ]
    }
    """
    # Actions to take when triggered
    actions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    """
    Format:
    [
      {"type": "execute_sequence", "target": "<sequence_id>"},
      {"type": "create_alert", "severity": "high", "message": "..."},
      {"type": "send_notification", "channel": "email", "recipients": ["operator@site.com"]},
    ]
    """
    # Execution control
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=30)  # don't re-fire for N min
    max_executions_per_day: Mapped[int] = mapped_column(Integer, default=10)
    execution_count_today: Mapped[int] = mapped_column(Integer, default=0)
    last_triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Audit
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<AutomationRule {self.name}>"


class CommandQueue(Base):
    """Outbound commands to edge agents."""
    __tablename__ = "command_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("edge_agents.id"), nullable=False
    )
    # Command
    command_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # set_setpoint, stage_compressor, start_defrost, emergency_stop, read_register
    target_equipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.id"), nullable=True
    )
    target_zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True
    )
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # State
    state: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, pending_approval, sent, acknowledged, completed, failed, expired, cancelled
    priority: Mapped[int] = mapped_column(Integer, default=50)
    source: Mapped[str] = mapped_column(
        String(50), default="user"
    )  # user, automation, schedule, system
    # Execution
    issued_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    # Expiry
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Command {self.command_type} [{self.state}]>"
