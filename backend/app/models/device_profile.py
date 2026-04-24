"""
Device Profile — pre-built controller templates for common industrial refrigeration equipment.

A device profile contains:
  - Manufacturer + model identification
  - Default Modbus/BACnet register map (which registers map to which parameters)
  - Protocol settings (baud rate, slave address ranges, register types)
  - Compressor parameter mappings (register → ColdGrid compressor reading field)

When a technician sets up an edge agent, they pick a device profile and the system
auto-fills the entire point map.  No manual register entry needed for supported controllers.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class DeviceProfile(Base):
    """Pre-built controller template for a specific manufacturer/model."""
    __tablename__ = "device_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Identity
    manufacturer: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    equipment_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="compressor"
    )  # compressor, condenser, evaporator, vessel
    refrigerant_types: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # ["NH3", "R-404A", ...]

    # Protocol defaults
    protocol: Mapped[str] = mapped_column(
        String(20), nullable=False, default="modbus_tcp"
    )  # modbus_tcp, modbus_rtu, bacnet_ip, opcua
    default_port: Mapped[int] = mapped_column(Integer, default=502)
    default_slave_id: Mapped[int] = mapped_column(Integer, default=1)

    # Register map — the core value
    register_map: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    """
    Maps ColdGrid parameter names → Modbus register definitions.
    Format:
    {
      "discharge_pressure": {
        "register": 40001,
        "type": "holding",
        "data_type": "float32",
        "byte_order": "big",
        "scale": 0.1,
        "offset": 0,
        "unit": "psi",
        "description": "Compressor discharge pressure"
      },
      "suction_pressure": { ... },
      "discharge_temp": { ... },
      "oil_temp": { ... },
      "bearing_temp": { ... },
      "amp_draw": { ... },
      "kw": { ... },
      "vibration": { ... },
      "slide_valve_pct": { ... },
      "rpm": { ... },
      "running": { ... }
    }
    """

    # Writable register map (added by migration 008)
    write_register_map: Mapped[dict] = mapped_column(JSONB, nullable=True, default=None)

    # Control action schemas — defines parameterized actions for the frontend
    # Each key is an action name (capacity, defrost, demand_response, etc.)
    # Each value defines params with type, label, unit, min, max, step, default
    control_schemas: Mapped[dict] = mapped_column(JSONB, nullable=True, default=None)
    """
    {
      "capacity": {
        "label": "Capacity Control",
        "icon": "sliders",
        "params": {
          "value": {"type": "slider", "label": "Slide Valve", "unit": "%", "min": 25, "max": 100, "step": 5, "default": 75},
          "ramp_rate": {"type": "number", "label": "Ramp Rate", "unit": "%/min", "min": 1, "max": 25, "default": 10}
        }
      },
      "defrost": {
        "label": "Defrost Cycle",
        "icon": "snowflake",
        "params": {
          "method": {"type": "select", "label": "Method", "options": [...], "default": "hot_gas"},
          "duration_min": {"type": "number", "label": "Duration", "unit": "min", "min": 5, "max": 90, "default": 30},
          ...
        }
      }
    }
    """

    # BACnet-specific config (if protocol is bacnet)
    bacnet_config: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    """
    {
      "device_instance": 1234,
      "objects": {
        "discharge_pressure": {"type": "analog-input", "instance": 1},
        ...
      }
    }
    """

    # State
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<DeviceProfile {self.manufacturer} {self.model}>"


class AgentDevice(Base):
    """
    Links an edge agent to a specific device (controller) on the plant network.

    Each row represents one controller that the agent polls — with its network address,
    which device profile to use, which compressor it feeds data into, and any
    register overrides for that specific installation.
    """
    __tablename__ = "agent_devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )  # null = custom/manual mapping
    compressor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )  # links telemetry → compressor_readings

    # Network address
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)  # IP or hostname
    port: Mapped[int] = mapped_column(Integer, default=502)
    slave_id: Mapped[int] = mapped_column(Integer, default=1)

    # Register overrides (merged on top of profile defaults)
    register_overrides: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)

    # Polling config
    poll_interval_sec: Mapped[int] = mapped_column(Integer, default=15)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Status
    connection_state: Mapped[str] = mapped_column(
        String(20), default="unknown"
    )  # online, offline, error, unknown
    last_poll_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    poll_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<AgentDevice {self.name} @ {self.host}:{self.port}>"
