"""
Base adapter — defines the interface all integration adapters must implement.

Every adapter (cloud API or edge protocol) follows the same contract:
  1. authenticate()  — obtain/refresh credentials
  2. discover()      — find devices on the system
  3. poll()          — read current values
  4. write()         — send a command/setpoint (optional)
  5. health_check()  — verify the connection is alive

The polling engine calls these methods on a schedule.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class TelemetryReading:
    """A single metric reading from a device."""
    equipment_id: UUID
    metric_name: str        # e.g. 'suction_temp', 'discharge_pressure', 'zone_temp'
    value: float
    unit: str               # e.g. 'degF', 'psi', 'kW', 'percent'
    timestamp: datetime
    quality: int = 0        # 0=good, 1=estimated, 2=suspect, 3=missing
    # Optional: set when this reading represents a zone sensor measurement.
    # The polling engine writes a ZoneReading and updates Zone.current_temp
    # in addition to the normal Telemetry record.
    zone_id: UUID | None = None
    sensor_id: UUID | None = None


@dataclass
class DiscoveredDevice:
    """A device found during auto-discovery."""
    external_id: str        # the ID in the external system
    name: str
    device_type: str        # compressor, evaporator, condenser, controller, sensor, meter
    manufacturer: str | None = None
    model: str | None = None
    protocol: str | None = None
    address: str | None = None  # IP, Modbus address, BACnet device ID
    metadata: dict = field(default_factory=dict)
    available_metrics: list[str] = field(default_factory=list)


@dataclass
class WriteCommand:
    """A command to write a value to a device."""
    equipment_id: UUID
    metric_name: str        # e.g. 'zone_setpoint'
    value: float
    unit: str


@dataclass
class WriteResult:
    """Result of a write command."""
    success: bool
    message: str | None = None
    previous_value: float | None = None
    new_value: float | None = None


@dataclass
class AdapterHealth:
    """Health status of an adapter."""
    connected: bool
    latency_ms: float | None = None
    last_poll_at: datetime | None = None
    error: str | None = None
    details: dict = field(default_factory=dict)


class BaseAdapter(ABC):
    """
    Abstract base class for all integration adapters.

    Subclasses must implement authenticate(), poll(), and health_check().
    discover() and write() are optional (not all systems support them).
    """

    provider: str = "unknown"
    integration_type: str = "unknown"  # cloud_api, edge_protocol, bas_middleware

    def __init__(self, config: dict, credentials: dict | None = None):
        """
        Args:
            config: Integration config from the database (base_url, poll_interval, etc.)
            credentials: Decrypted credential blob (client_id/secret, api_key, etc.)
        """
        self.config = config
        self.credentials = credentials or {}
        self._authenticated = False

    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with the external system.
        Returns True if successful. Should cache tokens for reuse.
        """
        ...

    @abstractmethod
    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        """
        Read current values from all mapped devices.

        Args:
            device_map: Maps external device IDs to ColdGrid equipment IDs
                        and metric name mappings.

        Returns:
            List of TelemetryReading objects.
        """
        ...

    @abstractmethod
    async def health_check(self) -> AdapterHealth:
        """Check if the connection is alive and responsive."""
        ...

    async def discover(self) -> list[DiscoveredDevice]:
        """
        Discover available devices on the external system.
        Override in subclasses that support discovery.
        """
        return []

    async def write(self, command: WriteCommand, device_map: dict) -> WriteResult:
        """
        Write a value to a device (e.g. change a setpoint).
        Override in subclasses that support write operations.
        """
        return WriteResult(success=False, message="Write not supported by this adapter")

    async def disconnect(self):
        """Clean up connections. Override if needed."""
        self._authenticated = False
