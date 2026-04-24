from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class AlertCreate(BaseModel):
    zone_id: UUID | None = None
    equipment_id: UUID | None = None
    severity: str  # critical, high, medium, low, info
    category: str  # temperature, pressure, equipment, power, security, compliance
    alert_type: str
    title: str
    message: str | None = None
    trigger_value: float | None = None
    threshold_value: float | None = None
    context: dict | None = None


class AlertUpdate(BaseModel):
    state: str | None = None  # acknowledged, resolved, suppressed
    resolution_note: str | None = None


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    zone_id: UUID | None = None
    equipment_id: UUID | None = None
    agent_id: UUID | None = None
    severity: str
    category: str
    alert_type: str
    title: str
    message: str | None = None
    state: str
    acknowledged_by: UUID | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by: UUID | None = None
    resolution_note: str | None = None
    trigger_value: float | None = None
    threshold_value: float | None = None
    context: dict | None = None
    triggered_at: datetime
    created_at: datetime


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse]
    total: int


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    event_type: str
    source: str
    zone_id: UUID | None = None
    equipment_id: UUID | None = None
    user_id: UUID | None = None
    alert_id: UUID | None = None
    description: str
    data: dict | None = None
    occurred_at: datetime


class EventListResponse(BaseModel):
    events: list[EventResponse]
    total: int
