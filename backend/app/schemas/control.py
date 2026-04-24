from datetime import datetime, time
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# ── Control Sequences ────────────────────────────
class ControlSequenceCreate(BaseModel):
    name: str
    description: str | None = None
    sequence_type: str  # demand_response, pre_cool, defrost, load_shed, setpoint_adjust, custom
    priority: int = 50
    steps: list[dict]
    conditions: dict | None = None


class ControlSequenceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    priority: int | None = None
    steps: list[dict] | None = None
    conditions: dict | None = None


class ControlSequenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    name: str
    description: str | None = None
    sequence_type: str
    enabled: bool
    priority: int
    steps: list[dict]
    conditions: dict | None = None
    last_run_at: datetime | None = None
    last_result: str | None = None
    run_count: int
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ControlSequenceListResponse(BaseModel):
    sequences: list[ControlSequenceResponse]
    total: int


# ── Schedules ────────────────────────────────────
class ScheduleCreate(BaseModel):
    control_sequence_id: UUID
    name: str
    schedule_type: str  # daily, weekly, monthly, cron, one_time
    cron_expression: str | None = None
    days_of_week: list[int] | None = None
    start_time: time | None = None
    end_time: time | None = None
    timezone: str = "America/Chicago"


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    control_sequence_id: UUID
    name: str
    enabled: bool
    schedule_type: str
    cron_expression: str | None = None
    days_of_week: list[int] | None = None
    start_time: time | None = None
    end_time: time | None = None
    timezone: str
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime


class ScheduleListResponse(BaseModel):
    schedules: list[ScheduleResponse]
    total: int


# ── Automation Rules ─────────────────────────────
class AutomationRuleCreate(BaseModel):
    name: str
    description: str | None = None
    trigger_conditions: dict
    actions: list[dict]
    cooldown_minutes: int = 30
    max_executions_per_day: int = 10


class AutomationRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    trigger_conditions: dict | None = None
    actions: list[dict] | None = None
    cooldown_minutes: int | None = None
    max_executions_per_day: int | None = None


class AutomationRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    name: str
    description: str | None = None
    enabled: bool
    trigger_conditions: dict
    actions: list[dict]
    cooldown_minutes: int
    max_executions_per_day: int
    execution_count_today: int
    last_triggered_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime


class AutomationRuleListResponse(BaseModel):
    rules: list[AutomationRuleResponse]
    total: int


# ── Command Queue ────────────────────────────────
class CommandCreate(BaseModel):
    agent_id: UUID
    command_type: str
    target_equipment_id: UUID | None = None
    target_zone_id: UUID | None = None
    parameters: dict = {}
    priority: int = 50
    expires_at: datetime | None = None


class CommandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    agent_id: UUID
    command_type: str
    target_equipment_id: UUID | None = None
    target_zone_id: UUID | None = None
    parameters: dict
    state: str
    priority: int
    issued_by: UUID | None = None
    issued_at: datetime
    sent_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict | None = None
    error_message: str | None = None
    expires_at: datetime | None = None


class CommandListResponse(BaseModel):
    commands: list[CommandResponse]
    total: int
