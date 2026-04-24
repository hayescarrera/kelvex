from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class EdgeAgentCreate(BaseModel):
    name: str
    hardware_type: str | None = None
    hostname: str | None = None
    heartbeat_interval_sec: int = 30
    protocols_config: dict | None = None
    capabilities: dict | None = None


class EdgeAgentUpdate(BaseModel):
    name: str | None = None
    version: str | None = None
    hostname: str | None = None
    ip_address: str | None = None
    connection_state: str | None = None
    heartbeat_interval_sec: int | None = None
    protocols_config: dict | None = None
    capabilities: dict | None = None
    enabled: bool | None = None


class EdgeAgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    name: str
    agent_key: str
    version: str | None = None
    hardware_type: str | None = None
    hostname: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    connection_state: str
    last_heartbeat: datetime | None = None
    last_telemetry_at: datetime | None = None
    heartbeat_interval_sec: int
    protocols_config: dict | None = None
    capabilities: dict | None = None
    discovered_devices: dict | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None
    uptime_seconds: int | None = None
    enabled: bool
    config_version: int
    pending_commands: int
    registered_at: datetime
    last_config_push: datetime | None = None


class EdgeAgentListResponse(BaseModel):
    agents: list[EdgeAgentResponse]
    total: int


class HeartbeatPayload(BaseModel):
    """Sent by the edge agent every N seconds."""
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None
    uptime_seconds: int | None = None
    version: str | None = None
    ip_address: str | None = None


class TelemetryBatch(BaseModel):
    """Batch of telemetry readings from the edge agent."""
    readings: list[dict]
    """
    Each reading:
    {
      "equipment_id": "uuid",
      "metric_name": "suction_pressure",
      "value": 28.5,
      "unit": "psi",
      "time": "2026-04-16T14:30:00Z",
      "quality": 0
    }
    """


class AgentLogCreate(BaseModel):
    level: str
    message: str
    context: dict | None = None


class AgentLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    level: str
    message: str
    context: dict | None = None
    logged_at: datetime
