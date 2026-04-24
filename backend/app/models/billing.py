import uuid
from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy import String, Date, DateTime, ForeignKey, Numeric, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class UtilityBill(Base):
    __tablename__ = "utility_bills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    total_kwh: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    peak_demand_kw: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    demand_charge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    energy_charge: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    source_file: Mapped[str] = mapped_column(String(500), nullable=True)
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    facility: Mapped["Facility"] = relationship(back_populates="utility_bills")

    def __repr__(self):
        return f"<UtilityBill {self.period_start} - {self.period_end}>"


class DemandAnalysis(Base):
    __tablename__ = "demand_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    peak_demand_kw: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    peak_demand_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ratchet_demand_kw: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    demand_charge_actual: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    demand_charge_optimized: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    savings_potential: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    peak_events: Mapped[dict] = mapped_column(JSONB, nullable=True)
    load_profile: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    facility: Mapped["Facility"] = relationship(back_populates="demand_analyses")

    def __repr__(self):
        return f"<DemandAnalysis {self.period_start} - {self.period_end}>"


class SavingsScenario(Base):
    __tablename__ = "savings_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    scenario_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    annual_savings: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    demand_savings: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    energy_savings: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=True)
    payback_months: Mapped[int] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<SavingsScenario {self.scenario_name}>"


# Forward reference
from app.models.facility import Facility  # noqa: E402, F401
