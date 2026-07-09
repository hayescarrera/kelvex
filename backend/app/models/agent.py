"""
Edge Agent model — the on-site software that connects to SCADA/PLC/controllers.

Each facility has one (or more) edge agents that:
  - Discover and poll equipment via BACnet/Modbus/EtherNet/IP
  - Stream telemetry to ColdGrid cloud (via MQTT or gRPC)
  - Execute commands from the cloud (setpoint changes, staging, etc.)
  - Buffer data locally during network outages
  - Run local safety logic (never override safety limits)
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey, Text, Float,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class EdgeAgent(Base):
    __tablename__ = "edge_agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # registration key for auth
    version: Mapped[str] = mapped_column(String(20), nullable=True)  # agent software version
    # Hardware
    hardware_type: Mapped[str] = mapped_column(
        String(50), nullable=True
    )  # raspberry_pi, industrial_pc, vm, docker
    hostname: Mapped[str] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)  # supports IPv6
    mac_address: Mapped[str] = mapped_column(String(17), nullable=True)
    controller_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # local controller web UI (e.g. http://192.168.1.50)
    # Connectivity
    connection_state: Mapped[str] = mapped_column(
        String(20), default="disconnected"
    )  # connected, disconnected, degraded
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_telemetry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_interval_sec: Mapped[int] = mapped_column(Integer, default=30)
    # Protocol config
    protocols_config: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    """
    Format:
    {
      "bacnet": {"enabled": true, "device_id": 1234, "port": 47808},
      "modbus": {"enabled": true, "port": 502, "devices": [
        {"address": 1, "name": "Compressor 1", "equipment_id": "..."}
      ]},
      "ethernet_ip": {"enabled": false}
    }
    """
    # Capabilities
    capabilities: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    """
    Format:
    {
      "read_telemetry": true,
      "write_setpoints": true,
      "local_buffering": true,
      "buffer_capacity_hours": 72,
      "firmware_update": true,
      "max_poll_rate_ms": 1000
    }
    """
    # Discovered devices
    discovered_devices: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    """
    Auto-discovered BACnet/Modbus devices on the local network.
    Updated during agent scan cycles.
    """
    # Health
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int] = mapped_column(Integer, nullable=True)
    # State
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    pending_commands: Mapped[int] = mapped_column(Integer, default=0)
    # Timestamps
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_config_push: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<EdgeAgent {self.name} [{self.connection_state}]>"


class AgentLog(Base):
    """Logs from the edge agent — errors, warnings, info."""
    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("edge_agents.id"), nullable=False
    )
    level: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # debug, info, warning, error, critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<AgentLog [{self.level}] {self.message[:50]}>"
