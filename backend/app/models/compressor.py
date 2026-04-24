"""
Compressor asset and telemetry models for industrial refrigeration monitoring.

Covers ammonia (NH3) screw compressors (Frick, Vilter, Mycom, GEA) and
supporting equipment. Health scoring is computed from CompressorReading data.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Float, Integer, Boolean, DateTime, ForeignKey, Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class Compressor(Base):
    """
    An individual compressor asset within a facility's refrigeration plant.

    Typical ammonia cold-storage facilities have 2–8 screw compressors
    arranged in racks (a.k.a. engine rooms). Each compressor has a set of
    monitoring points that get captured in CompressorReading.
    """
    __tablename__ = "compressors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False,
    )
    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tag: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "COMP-A1"
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Frick, Vilter, Mycom, GEA
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "RWF II 480"
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    compressor_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="screw",
    )  # screw, reciprocating, scroll

    # Refrigerant
    refrigerant: Mapped[str] = mapped_column(String(20), nullable=False, default="NH3")  # NH3, R-404A, R-22, CO2
    refrigerant_charge_lbs: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Ratings
    hp: Mapped[float | None] = mapped_column(Float, nullable=True)  # nameplate horsepower
    capacity_tons: Mapped[float | None] = mapped_column(Float, nullable=True)  # refrigeration tons
    design_suction_psi: Mapped[float | None] = mapped_column(Float, nullable=True)
    design_discharge_psi: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_discharge_temp_f: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Operating thresholds (for anomaly detection)
    alarm_discharge_psi_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    alarm_suction_psi_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    alarm_oil_temp_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    alarm_bearing_temp_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    alarm_vibration_high: Mapped[float | None] = mapped_column(Float, nullable=True)  # in/s or mm/s
    alarm_amp_draw_high: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Maintenance
    commissioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_overhaul_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_maintenance_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # State
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="offline")  # running, standby, offline, alarm, maintenance
    health_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0–100
    last_reading_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Rack assignment
    rack_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "Engine Room 1"

    # Flexible metadata
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    facility: Mapped["Facility"] = relationship(back_populates="compressors")  # type: ignore[name-defined]
    readings: Mapped[list["CompressorReading"]] = relationship(
        back_populates="compressor", cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_compressor_facility", "facility_id"),
    )


class CompressorReading(Base):
    """
    A time-series snapshot of compressor operating parameters.

    These are captured at 1–15 minute intervals from the BAS, PLC, or
    edge agent. The health scoring engine processes these to detect
    anomalies and compute health_score on the parent Compressor.
    """
    __tablename__ = "compressor_readings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    compressor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compressors.id", ondelete="CASCADE"), nullable=False,
    )

    # Core operating parameters
    discharge_pressure_psi: Mapped[float | None] = mapped_column(Float, nullable=True)
    suction_pressure_psi: Mapped[float | None] = mapped_column(Float, nullable=True)
    discharge_temp_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    suction_temp_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    oil_pressure_psi: Mapped[float | None] = mapped_column(Float, nullable=True)
    oil_temp_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    bearing_temp_f: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Electrical
    amp_draw: Mapped[float | None] = mapped_column(Float, nullable=True)
    kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_factor: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Mechanical
    vibration_ips: Mapped[float | None] = mapped_column(Float, nullable=True)  # inches per second
    slide_valve_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0–100 capacity
    rpm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Performance
    superheat_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    subcooling_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    compression_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    efficiency_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # kW/ton

    # Status flags
    running: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    alarm_active: Mapped[bool] = mapped_column(Boolean, default=False)
    alarm_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    compressor: Mapped["Compressor"] = relationship(back_populates="readings")

    __table_args__ = (
        Index("ix_reading_compressor_time", "compressor_id", "recorded_at"),
        Index("ix_reading_recorded_at", "recorded_at"),
    )
