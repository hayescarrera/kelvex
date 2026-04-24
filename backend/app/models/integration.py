"""
Integration model — tracks connections to external control systems.

Each facility can have one or more integrations:
  - Cloud connectors (Danfoss Alsense, Emerson Oversight, etc.)
  - Edge protocol adapters (Modbus TCP, BACnet/IP via edge agent)
  - BAS middleware (Niagara, Metasys)

Credentials are stored encrypted. The polling engine reads these
records to know what to poll and how to authenticate.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, Boolean, DateTime, ForeignKey, Text, Float,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class Integration(Base):
    """A connection to an external control system or cloud platform."""
    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    # What type of integration
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # danfoss_alsense, emerson_oversight, schneider_ecostruxure,
       # jci_openblue, jci_metasys, honeywell_niagara, honeywell_forge,
       # carrier_ivu, modbus_tcp, bacnet_ip, opc_ua, mqtt_broker
    integration_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # cloud_api, edge_protocol, bas_middleware
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    # Connection config
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    """
    Cloud API example (Danfoss Alsense):
    {
      "base_url": "https://api.alsense.danfoss.com",
      "site_id": "abc123",
      "poll_interval_sec": 60,
      "metrics": ["temperature", "pressure", "compressor_status", "energy"],
      "write_enabled": false
    }

    Edge protocol example (Modbus TCP):
    {
      "host": "192.168.1.100",
      "port": 502,
      "slave_id": 1,
      "poll_interval_sec": 5,
      "timeout_sec": 3,
      "register_map": "emerson_e2_v4"
    }

    BAS middleware example (Niagara):
    {
      "base_url": "https://192.168.1.50:443",
      "station_name": "MainStation",
      "poll_interval_sec": 30,
      "verify_ssl": false
    }
    """
    # Credentials (encrypted at rest — see IntegrationCredential)
    # We don't store raw creds in this table — they go in a separate
    # table with encryption. This just references the credential set.
    credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_credentials.id"), nullable=True
    )
    # State
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    connection_state: Mapped[str] = mapped_column(
        String(20), default="disconnected"
    )  # connected, disconnected, error, authenticating
    last_poll_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Stats
    total_polls: Mapped[int] = mapped_column(Integer, default=0)
    total_errors: Mapped[int] = mapped_column(Integer, default=0)
    total_readings_ingested: Mapped[int] = mapped_column(Integer, default=0)
    # Device mapping — maps external device IDs to ColdGrid equipment IDs
    device_map: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)
    """
    Format:
    {
      "external_device_123": {
        "equipment_id": "uuid",
        "metrics": {
          "SuctTemp": {"metric_name": "suction_temp", "unit": "degF", "transform": null},
          "DischPres": {"metric_name": "discharge_pressure", "unit": "psi", "transform": "psi_to_bar"},
        }
      }
    }
    """
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<Integration {self.provider} [{self.connection_state}]>"


class IntegrationCredential(Base):
    """Encrypted credential storage for integrations."""
    __tablename__ = "integration_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # Encrypted credential blob
    # In production: encrypted with Fernet (symmetric) using a key from env/vault
    # For now: stored as JSONB (dev mode)
    credentials_encrypted: Mapped[dict] = mapped_column(JSONB, nullable=False)
    """
    Decrypted format varies by provider:

    OAuth2 (Danfoss, Schneider, JCI):
    {
      "client_id": "...",
      "client_secret": "...",
      "token_url": "...",
      "access_token": "...",      // cached
      "refresh_token": "...",     // if available
      "expires_at": "2026-04-16T..."  // token expiry
    }

    API Key (Emerson, some others):
    {
      "api_key": "...",
      "api_secret": "..."
    }

    Basic Auth (Niagara, Metasys on-prem):
    {
      "username": "...",
      "password": "..."
    }
    """
    auth_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # oauth2, api_key, basic, bearer_token, certificate
    # Token management
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<IntegrationCredential {self.provider} ({self.auth_type})>"


class RegisterMap(Base):
    """
    Predefined register maps for Modbus/BACnet devices.

    Maps raw register addresses or BACnet object IDs to meaningful
    metric names. One map per controller model (e.g. 'emerson_e2_v4',
    'danfoss_ak_pc_781', 'ab_compactlogix_ammonia').
    """
    __tablename__ = "register_maps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    protocol: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # modbus_tcp, modbus_rtu, bacnet_ip, ethernet_ip
    manufacturer: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    # The actual register/point definitions
    registers: Mapped[dict] = mapped_column(JSONB, nullable=False)
    """
    Modbus format:
    {
      "registers": [
        {
          "address": 40001,
          "name": "suction_temp",
          "description": "Suction line temperature",
          "data_type": "int16",
          "scale": 0.1,
          "offset": 0,
          "unit": "degF",
          "function_code": 3,
          "byte_order": "big",
          "access": "read"
        },
        {
          "address": 40010,
          "name": "zone_setpoint",
          "data_type": "int16",
          "scale": 0.1,
          "unit": "degF",
          "function_code": 3,
          "access": "read_write",
          "write_function_code": 6,
          "min_value": -40,
          "max_value": 60,
          "safety_lock": true
        }
      ]
    }

    BACnet format:
    {
      "objects": [
        {
          "object_type": "analog-input",
          "instance": 1,
          "name": "suction_temp",
          "description": "Suction line temperature",
          "unit": "degF",
          "property": "present-value"
        },
        {
          "object_type": "analog-value",
          "instance": 100,
          "name": "zone_setpoint",
          "unit": "degF",
          "property": "present-value",
          "access": "read_write",
          "min_value": -40,
          "max_value": 60
        }
      ]
    }
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<RegisterMap {self.name} ({self.protocol})>"
