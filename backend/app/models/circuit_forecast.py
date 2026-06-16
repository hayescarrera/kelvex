"""
Cached forecast results per refrigerant circuit.

One row per circuit (unique constraint on circuit_id). Updated by the
daily Celery forecasting task. Consumers read this table directly —
they never need to re-run the forecast on every request.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class CircuitForecast(Base):
    """Cached refrigerant consumption forecast for a circuit."""
    __tablename__ = "circuit_forecasts"
    __table_args__ = (
        Index("ix_circuit_forecasts_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # One forecast row per circuit — upserted by the forecasting task
    circuit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("refrigerant_circuits.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )

    # Which model produced this forecast
    method: Mapped[str] = mapped_column(String(50), nullable=False)

    # Forecast outputs
    projected_adds_lbs: Mapped[float | None] = mapped_column(Float, nullable=True)
    projected_adds_lbs_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    projected_adds_lbs_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    lbs_per_day: Mapped[float | None] = mapped_column(Float, nullable=True)
    days_to_aim_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days_to_aim_warning: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_annual_leak_rate_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)

    # When was this computed
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
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
        return f"<CircuitForecast circuit={self.circuit_id} method={self.method} computed={self.computed_at}>"
