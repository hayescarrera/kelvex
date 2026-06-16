"""
LeakRateRecord — EPA-method annualized leak rate for a refrigerant circuit.

Computed on each refrigerant addition using the EPA formula:
  annualized_rate_pct = (lbs_added / full_charge_lbs) * (365 / days_since_last_add) * 100

AIM Act thresholds (HFCs):
  >=35% annualized → commercial refrigeration repair clock triggered
  >=20% (CARB) for GWP >=150

Records are written by the ingestion service on each RefrigerantAdd and
kept permanently as part of the compliance record.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class LeakRateRecord(Base):
    """EPA-method annualized leak rate computed on each refrigerant addition."""

    __tablename__ = "leak_rate_records"
    __table_args__ = (
        Index("ix_leak_rate_records_circuit_computed", "circuit_id", "computed_at"),
        Index("ix_leak_rate_records_org", "org_id"),
        Index("ix_leak_rate_records_facility", "facility_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    circuit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refrigerant_circuits.id", ondelete="SET NULL"), nullable=True
    )
    # The refrigerant add that triggered this computation
    refrigerant_add_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("refrigerant_adds.id", ondelete="SET NULL"), nullable=True
    )

    # Inputs
    lbs_added: Mapped[float] = mapped_column(Float, nullable=False)
    full_charge_lbs: Mapped[float] = mapped_column(Float, nullable=False)
    days_since_last_add: Mapped[float | None] = mapped_column(Float, nullable=True)
    refrigerant_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Result
    annualized_rate_pct: Mapped[float] = mapped_column(Float, nullable=False)

    # Whether this record crossed the AIM Act repair clock threshold (default 35% for HFCs)
    triggered_repair_clock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Compliance status at time of calculation
    compliance_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="compliant"
    )  # compliant | marginal | non_compliant

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return (
            f"<LeakRateRecord circuit={self.circuit_id} "
            f"rate={self.annualized_rate_pct:.1f}% status={self.compliance_status}>"
        )
