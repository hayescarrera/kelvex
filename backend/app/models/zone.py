"""
Zone model — thermal zones within a facility.

Each facility has one or more zones (Freezer, Cooler, Dock, Machine Room, etc.)
with defined setpoints, alarm thresholds, and real-time state tracking.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Float, Integer, Boolean, DateTime, ForeignKey, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # freezer, cooler, dock, machine_room, blast_freezer, staging
    # Physical layout
    area_sqft: Mapped[int] = mapped_column(Integer, nullable=True)
    position_x: Mapped[float] = mapped_column(Float, nullable=True)  # site map coord
    position_y: Mapped[float] = mapped_column(Float, nullable=True)
    width: Mapped[float] = mapped_column(Float, nullable=True)       # site map size
    height: Mapped[float] = mapped_column(Float, nullable=True)
    # Temperature setpoints
    temp_setpoint: Mapped[float] = mapped_column(Float, nullable=True)  # target temp
    temp_unit: Mapped[str] = mapped_column(String(5), default="F")      # F or C
    temp_tolerance: Mapped[float] = mapped_column(Float, default=2.0)   # +/- degrees
    # Alarm thresholds
    temp_alarm_high: Mapped[float] = mapped_column(Float, nullable=True)
    temp_alarm_low: Mapped[float] = mapped_column(Float, nullable=True)
    humidity_setpoint: Mapped[float] = mapped_column(Float, nullable=True)
    humidity_alarm_high: Mapped[float] = mapped_column(Float, nullable=True)
    # Current state (updated by edge agent)
    current_temp: Mapped[float] = mapped_column(Float, nullable=True)
    current_humidity: Mapped[float] = mapped_column(Float, nullable=True)
    door_open: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(
        String(20), default="normal"
    )  # normal, warning, alarm, offline
    last_reading_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Config
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    facility: Mapped["Facility"] = relationship(back_populates="zones")
    equipment_assignments: Mapped[list["ZoneEquipment"]] = relationship(
        back_populates="zone", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Zone {self.name} ({self.zone_type})>"


class ZoneEquipment(Base):
    """Many-to-many: which equipment serves which zone."""
    __tablename__ = "zone_equipment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id"), nullable=False
    )
    equipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=True
    )  # primary, backup, shared
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    zone: Mapped["Zone"] = relationship(back_populates="equipment_assignments")
    equipment: Mapped["Equipment"] = relationship()

    def __repr__(self):
        return f"<ZoneEquipment zone={self.zone_id} eq={self.equipment_id}>"


# Forward references
from app.models.facility import Facility, Equipment  # noqa: E402, F401
