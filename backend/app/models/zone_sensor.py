"""
Zone sensor models — physical sensors monitoring cold storage environments.

Covers temperature probes, door contacts, humidity sensors, ammonia detectors,
pressure differential sensors (for defrost triggers), and glycol loop temps.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Float, Integer, Boolean, DateTime, ForeignKey, Text, Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class ZoneSensor(Base):
    """A physical sensor deployed in a zone."""
    __tablename__ = "zone_sensors"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False,
    )
    agent_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )  # links to agent_devices if polled via Modbus/BACnet
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sensor_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )  # temperature, humidity, door_contact, ammonia, pressure_differential, glycol_temp

    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)  # °F, %RH, ppm, psi
    location_desc: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Thresholds
    alarm_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    alarm_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    warn_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    warn_low: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Current state
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_state: Mapped[str] = mapped_column(String(20), default="normal")
    last_reading_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Config
    poll_interval_sec: Mapped[int] = mapped_column(Integer, default=30)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )


class ZoneReading(Base):
    """Time-series reading from a zone sensor."""
    __tablename__ = "zone_readings"
    __table_args__ = (
        Index("ix_zone_readings_sensor_time", "sensor_id", "recorded_at"),
        Index("ix_zone_readings_zone_time", "zone_id", "recorded_at"),
        # Idempotency: edge agents retry batches after network failures —
        # one reading per sensor per timestamp, duplicates dropped on insert
        UniqueConstraint("sensor_id", "recorded_at", name="uq_zone_reading_sensor_recorded_at"),
        {"extend_existing": True},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    sensor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zone_sensors.id", ondelete="CASCADE"), nullable=False,
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id", ondelete="CASCADE"), nullable=False,
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quality: Mapped[int] = mapped_column(Integer, default=0)  # 0=good, 1=uncertain, 2=bad
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompressorRack(Base):
    """A rack (group) of compressors sharing suction/discharge headers."""
    __tablename__ = "compressor_racks"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    suction_group: Mapped[str | None] = mapped_column(String(100), nullable=True)
    design_suction_psi: Mapped[float | None] = mapped_column(Float, nullable=True)
    design_discharge_psi: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Staging
    staging_mode: Mapped[str] = mapped_column(String(50), default="manual")
    staging_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Demand response
    demand_response_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    min_capacity_pct: Mapped[float] = mapped_column(Float, default=25)
    max_coast_minutes: Mapped[int] = mapped_column(Integer, default=60)
    thermal_mass_factor: Mapped[float] = mapped_column(Float, default=1.0)

    # State
    total_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_compressors: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )


class ControlAuditLog(Base):
    """Audit trail for every control action taken on the plant."""
    __tablename__ = "control_audit_log"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False,
    )
    command_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
