import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, ForeignKey, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.system import System


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=True)
    city: Mapped[str] = mapped_column(String(100), nullable=True)
    state: Mapped[str] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str] = mapped_column(String(10), nullable=True)
    sqft: Mapped[int] = mapped_column(Integer, nullable=True)
    zone_types: Mapped[list] = mapped_column(
        ARRAY(String), nullable=True
    )  # e.g. ["frozen", "cooler", "dock"]
    utility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("utilities.id"), nullable=True
    )
    rate_schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rate_schedules.id"), nullable=True
    )
    iso_region: Mapped[str] = mapped_column(String(20), nullable=True)  # PJM, ERCOT, etc.
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    floor_plan: Mapped[dict] = mapped_column(JSONB, nullable=True, default=None)  # Floor plan layout data
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Relationships — cascade all children on delete
    organization: Mapped["Organization"] = relationship(back_populates="facilities")
    equipment: Mapped[list["Equipment"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )
    utility_bills: Mapped[list["UtilityBill"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )
    demand_analyses: Mapped[list["DemandAnalysis"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )
    zones: Mapped[list["Zone"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )
    rate_schedule: Mapped["RateSchedule"] = relationship()
    compressors: Mapped[list["Compressor"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def __repr__(self):
        return f"<Facility {self.name}>"


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False
    )
    # Optional grouping under a System (rack/circuit/walk-in)
    system_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("systems.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    equipment_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # compressor, evaporator, condenser, case, walk_in, blast_freezer, etc.
    manufacturer: Mapped[str] = mapped_column(String(100), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=True)
    controller_type: Mapped[str] = mapped_column(
        String(100), nullable=True
    )  # copeland, danfoss, allen_bradley
    protocol: Mapped[str] = mapped_column(
        String(50), nullable=True
    )  # bacnet, modbus, ethernet_ip

    # Refrigerant tracking — required for AIM Act leak-rate thresholds
    refrigerant_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gwp: Mapped[float | None] = mapped_column(Float, nullable=True)  # Global Warming Potential
    full_charge_lbs: Mapped[float | None] = mapped_column(Float, nullable=True)

    commissioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    facility: Mapped["Facility"] = relationship(back_populates="equipment")
    system: Mapped["System | None"] = relationship(  # type: ignore[name-defined]
        back_populates="equipment", foreign_keys=[system_id]
    )

    def __repr__(self):
        return f"<Equipment {self.name} ({self.equipment_type})>"


# Forward references
from app.models.user import Organization  # noqa: E402, F401
from app.models.tariff import RateSchedule  # noqa: E402, F401
from app.models.billing import UtilityBill, DemandAnalysis  # noqa: E402, F401
from app.models.zone import Zone  # noqa: E402, F401
from app.models.compressor import Compressor  # noqa: E402, F401
from app.models.system import System  # noqa: E402, F401
