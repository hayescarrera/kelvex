from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# ── Device Profiles ──────────────────────────────────

class DeviceProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    manufacturer: str
    model: str
    display_name: str
    description: str | None = None
    equipment_type: str
    refrigerant_types: list[str]
    protocol: str
    default_port: int
    default_slave_id: int
    register_map: dict
    bacnet_config: dict | None = None
    is_builtin: bool
    is_active: bool
    version: int
    created_at: datetime


class DeviceProfileListResponse(BaseModel):
    profiles: list[DeviceProfileResponse]
    total: int


# ── Agent Devices ────────────────────────────────────

class AgentDeviceCreate(BaseModel):
    """Add a device (controller) to an edge agent's poll list."""
    profile_id: UUID | None = None
    compressor_id: UUID | None = None
    name: str
    host: str
    port: int = 502
    slave_id: int = 1
    register_overrides: dict | None = None
    poll_interval_sec: int = 15


class AgentDeviceUpdate(BaseModel):
    compressor_id: UUID | None = None
    name: str | None = None
    host: str | None = None
    port: int | None = None
    slave_id: int | None = None
    register_overrides: dict | None = None
    poll_interval_sec: int | None = None
    enabled: bool | None = None


class AgentDeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    profile_id: UUID | None = None
    compressor_id: UUID | None = None
    name: str
    host: str
    port: int
    slave_id: int
    register_overrides: dict | None = None
    poll_interval_sec: int
    enabled: bool
    connection_state: str
    last_poll_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    poll_count: int
    error_count: int
    created_at: datetime


class AgentDeviceListResponse(BaseModel):
    devices: list[AgentDeviceResponse]
    total: int


# ── Config Bundle ────────────────────────────────────

class ConfigBundleResponse(BaseModel):
    """The YAML config blob the edge agent needs to connect and start polling."""
    agent_name: str
    agent_key: str
    platform_url: str
    heartbeat_interval_sec: int
    devices: list[dict]
    """
    Each device:
    {
      "name": "Compressor #1 Controller",
      "host": "192.168.1.50",
      "port": 502,
      "slave_id": 1,
      "poll_interval_sec": 15,
      "protocol": "modbus_tcp",
      "compressor_id": "uuid",
      "registers": { ... merged profile + overrides ... }
    }
    """
