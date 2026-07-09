"""
Energy analytics models.

EnergySystemConfig  — per-system refrigerant/condenser config needed by the analytics engine.
EnergyOpportunity   — quantified dollar-denominated savings finding (one row per detection run).
SavingsVerification — IPMVP Option C before/after verification of a resolved opportunity.
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import String, Float, Text, DateTime, Integer, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM

from app.core.database import Base

OPP_TYPE_ENUM = ENUM(
    "excess_lift",
    "defrost_overrun",
    "defrost_underrun",
    "compressor_degradation",
    "condenser_fouling",
    "charge_anomaly",
    "setpoint_drift",
    name="opp_type",
    create_type=False,  # created by migration
)

OPP_TYPES = (
    "excess_lift",
    "defrost_overrun",
    "defrost_underrun",
    "compressor_degradation",
    "condenser_fouling",
    "charge_anomaly",
    "setpoint_drift",
)

OPP_STATUS_OPEN = "open"
OPP_STATUS_ACKNOWLEDGED = "acknowledged"
OPP_STATUS_WORK_ORDERED = "work_ordered"
OPP_STATUS_RESOLVED = "resolved"
OPP_STATUS_DISMISSED = "dismissed"


class EnergySystemConfig(Base):
    """Per-system energy configuration required by the analytics engine."""

    __tablename__ = "energy_system_config"

    system_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("systems.id", ondelete="CASCADE"), primary_key=True
    )
    # e.g. 'R448A', 'R449A', 'R404A', 'R507A', 'R717', 'R744'
    refrigerant: Mapped[str] = mapped_column(String(20), nullable=False, default="R448A")
    # 'evaporative' | 'air_cooled'
    condenser_type: Mapped[str] = mapped_column(String(20), nullable=False, default="air_cooled")
    sct_floor_f: Mapped[float | None] = mapped_column(Float, nullable=True, default=70.0)
    design_approach_f: Mapped[float | None] = mapped_column(Float, nullable=True, default=15.0)
    defrost_heater_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    rated_tons: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class EnergyOpportunity(Base):
    """
    A quantified, dollar-denominated energy savings opportunity detected by the analytics engine.

    One row per (system, equipment, type, window_start) — the unique constraint makes every
    daily/hourly run idempotent. The React UI and work-order subsystem consume this table.
    """

    __tablename__ = "energy_opportunities"
    __table_args__ = (
        UniqueConstraint("system_id", "equipment_id", "opp_type", "window_start",
                         name="uq_opportunity_per_window"),
        Index("ix_energy_opp_facility", "facility_id"),
        Index("ix_energy_opp_system", "system_id"),
        Index("ix_energy_opp_status", "status"),
        Index("ix_energy_opp_detected", "detected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    system_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("systems.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable — system-level findings have no specific asset
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True
    )
    opp_type: Mapped[str] = mapped_column(OPP_TYPE_ENUM, nullable=False)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Diagnostic values — e.g. actual SCT vs achievable SCT for excess_lift
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    estimated_kwh_year: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_usd_year: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw numbers, sample series refs, baseline params used to produce this finding
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=OPP_STATUS_OPEN)
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    verifications: Mapped[list["SavingsVerification"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<EnergyOpportunity {self.opp_type} ${self.estimated_usd_year:.0f}/yr [{self.status}]>"


class SavingsVerification(Base):
    """
    IPMVP Option C before/after weather-normalized verification of a resolved opportunity.
    Stores realized vs estimated so finance sees a real number each month.
    """

    __tablename__ = "savings_verification"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("energy_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    verified_kwh_year: Mapped[float | None] = mapped_column(Float, nullable=True)
    verified_usd_year: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str] = mapped_column(
        String(100), nullable=False, default="IPMVP-C weather-normalized"
    )
    baseline_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    post_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    post_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    opportunity: Mapped["EnergyOpportunity"] = relationship(back_populates="verifications")

    def __repr__(self):
        return f"<SavingsVerification ${self.verified_usd_year:.0f}/yr verified>"
