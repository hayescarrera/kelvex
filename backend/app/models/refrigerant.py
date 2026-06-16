"""
Refrigerant Tracking Models — circuits, leak events, refrigerant additions,
and repair records for AIM Act compliance and fleet-level leak rate tracking.

Cold storage operators must comply with:
  - AIM Act (American Innovation and Manufacturing Act) — HFC leak rate limits
  - EPA Section 608 — refrigerant handling and recordkeeping
  - CARB regulations (California) — stricter thresholds for large systems

Key concepts:
  - RefrigerantCircuit: a discrete rack/circuit with a known refrigerant charge
  - LeakEvent: a detected or confirmed refrigerant leak on a circuit
  - RefrigerantAdd: a logged refrigerant addition (required by law >= 50 lbs systems)
  - RepairRecord: completed repair with leak-free verification
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class RefrigerantCircuit(Base):
    """A refrigerant circuit (rack/system) with a known full charge capacity."""
    __tablename__ = "refrigerant_circuits"
    __table_args__ = (
        Index("ix_refrigerant_circuit_facility", "facility_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "Rack B — Dairy"
    refrigerant_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # R-404A, R-448A, R-410A, R-22, R-134a, Other

    # Charge capacity — required for AIM Act leak rate calculation
    full_charge_lbs: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Link to the physical compressor rack this circuit runs on
    rack_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compressor_racks.id", ondelete="SET NULL"), nullable=True
    )

    # Optional links to equipment / zone
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("zones.id", ondelete="SET NULL"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<RefrigerantCircuit {self.name} [{self.refrigerant_type}]>"


class LeakEvent(Base):
    """A detected or confirmed refrigerant leak event on a circuit."""
    __tablename__ = "leak_events"
    __table_args__ = (
        Index("ix_leak_event_facility_detected", "facility_id", "detected_at"),
        Index("ix_leak_event_circuit", "circuit_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    circuit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refrigerant_circuits.id", ondelete="SET NULL"), nullable=True
    )

    # Denormalized for display without joins
    rack_name: Mapped[str] = mapped_column(String(255), nullable=False)
    zone_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Detection details
    detection_method: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # pressure_trend | manual | refrigerant_add_pattern | technician_reported
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # suspected | likely | confirmed

    # Lifecycle status
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open | investigating | repaired | closed | false_positive

    # Key timestamps
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repaired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Impact
    estimated_loss_lbs: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Attribution
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<LeakEvent {self.rack_name} [{self.status}] detected={self.detected_at}>"


class RefrigerantAdd(Base):
    """A logged refrigerant addition — legally required recordkeeping for Section 608."""
    __tablename__ = "refrigerant_adds"
    __table_args__ = (
        Index("ix_refrigerant_add_facility_added", "facility_id", "added_at"),
        Index("ix_refrigerant_add_leak_event", "leak_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    circuit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refrigerant_circuits.id", ondelete="SET NULL"), nullable=True
    )
    leak_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leak_events.id", ondelete="SET NULL"), nullable=True
    )

    # Denormalized for display
    rack_name: Mapped[str] = mapped_column(String(255), nullable=False)
    refrigerant_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Quantity and cost
    amount_lbs: Mapped[float] = mapped_column(Float, nullable=False)
    cost_per_lb: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Who did it and when
    technician_name: Mapped[str] = mapped_column(String(255), nullable=False)
    technician_epa_cert: Mapped[str | None] = mapped_column(String(100), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<RefrigerantAdd {self.rack_name} {self.amount_lbs}lbs {self.added_at}>"


class RepairRecord(Base):
    """A completed refrigerant leak repair with verification details."""
    __tablename__ = "repair_records"
    __table_args__ = (
        Index("ix_repair_record_facility_repaired", "facility_id", "repaired_at"),
        Index("ix_repair_record_leak_event", "leak_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    circuit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refrigerant_circuits.id", ondelete="SET NULL"), nullable=True
    )
    leak_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leak_events.id", ondelete="SET NULL"), nullable=True
    )

    # Denormalized for display
    rack_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Who performed the repair
    technician_name: Mapped[str] = mapped_column(String(255), nullable=False)
    technician_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    repaired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Repair details
    parts_replaced: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_leak_free: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_method: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # pressure_test | electronic_detector | visual | dye_test

    # Refrigerant recovered during repair (EPA Section 608 requirement)
    refrigerant_recovered_lbs: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Callback detection — did the repair hold? Did the circuit leak again?
    # Populated by POST /refrigerant/repairs/{id}/detect-callback or nightly sweep
    callback_detected: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    callback_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    callback_lbs_within_30d: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<RepairRecord {self.rack_name} repaired={self.repaired_at} verified={self.verified_leak_free}>"
