import uuid
from datetime import datetime, date, timezone
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class Utility(Base):
    __tablename__ = "utilities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    openei_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=True)
    eia_id: Mapped[str] = mapped_column(String(20), nullable=True)  # EIA utility ID
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=True)
    iso_region: Mapped[str] = mapped_column(String(20), nullable=True)
    regulated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    rate_schedules: Mapped[list["RateSchedule"]] = relationship(back_populates="utility")

    def __repr__(self):
        return f"<Utility {self.name} ({self.state})>"


class RateSchedule(Base):
    __tablename__ = "rate_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    utility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("utilities.id"), nullable=False
    )
    openei_rate_id: Mapped[str] = mapped_column(String(100), nullable=True)
    schedule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=True)
    sector: Mapped[str] = mapped_column(String(50), default="commercial")
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=True)

    # Demand charge structure — flexible JSONB for varying tariff types
    # Example:
    # {
    #   "flat": {"rate": 18.50, "unit": "$/kW"},
    #   "tou": [
    #     {"period": "on_peak", "rate": 23.40, "months": [6,7,8,9], "hours": [12,20]},
    #     {"period": "off_peak", "rate": 0}
    #   ],
    #   "ratchet": {"pct": 0.80, "lookback_months": 11},
    #   "minimum_demand_kw": 50
    # }
    demand_rates: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Energy rate structure
    # Example:
    # {
    #   "tou": [
    #     {"period": "on_peak", "rate": 0.1842, "months": [6,7,8,9], "hours": [12,20]},
    #     {"period": "off_peak", "rate": 0.0923}
    #   ]
    # }
    energy_rates: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Fixed monthly charges
    # Example: {"monthly_service": 450.00, "meter_charge": 12.50}
    fixed_charges: Mapped[dict] = mapped_column(JSONB, nullable=True, default=dict)

    # Raw data from OpenEI or manual entry
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=True, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    utility: Mapped["Utility"] = relationship(back_populates="rate_schedules")

    def __repr__(self):
        return f"<RateSchedule {self.schedule_name}>"
