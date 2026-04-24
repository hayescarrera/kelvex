"""
Telemetry model — this table becomes a TimescaleDB hypertable.

The hypertable conversion and continuous aggregates are handled in the
Alembic migration, not here, because SQLAlchemy doesn't natively support
TimescaleDB DDL. The model defines the schema; the migration adds the
time-series superpowers.
"""

import uuid
from datetime import datetime
from sqlalchemy import String, Float, SmallInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Telemetry(Base):
    __tablename__ = "telemetry"

    # TimescaleDB hypertables need a time column as part of the primary key
    # We use a composite key: (time, equipment_id) for uniqueness
    time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    equipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("equipment.id"),
        primary_key=True,
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(
        String(100), primary_key=True, nullable=False
    )  # e.g. 'suction_pressure', 'discharge_temp', 'kw_demand', 'zone_temp'
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # e.g. 'psi', 'degF', 'kW', 'degC'
    quality: Mapped[int] = mapped_column(
        SmallInteger, default=0
    )  # 0=good, 1=estimated, 2=suspect, 3=missing

    def __repr__(self):
        return f"<Telemetry {self.metric_name}={self.value} @ {self.time}>"
