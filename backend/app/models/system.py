"""
System model — a refrigeration rack, circuit, walk-in, or blast freezer unit.

Sits between Facility and Equipment in the hierarchy:
  Facility (Site) → System (rack/circuit/walk-in) → Equipment (asset/case)

A System is the physical grouping that a RefrigerantCircuit runs through.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


SYSTEM_TYPE_RACK = "rack"
SYSTEM_TYPE_CIRCUIT = "circuit"
SYSTEM_TYPE_WALK_IN = "walk_in"
SYSTEM_TYPE_BLAST = "blast"
SYSTEM_TYPE_OTHER = "other"

ALL_SYSTEM_TYPES = (
    SYSTEM_TYPE_RACK,
    SYSTEM_TYPE_CIRCUIT,
    SYSTEM_TYPE_WALK_IN,
    SYSTEM_TYPE_BLAST,
    SYSTEM_TYPE_OTHER,
)


class System(Base):
    """A refrigeration system grouping equipment within a site."""

    __tablename__ = "systems"
    __table_args__ = (
        Index("ix_systems_facility", "facility_id"),
        Index("ix_systems_org", "org_id"),
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

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    system_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default=SYSTEM_TYPE_RACK
    )  # rack | circuit | walk_in | blast | other

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    equipment: Mapped[list["Equipment"]] = relationship(  # type: ignore[name-defined]
        back_populates="system", foreign_keys="Equipment.system_id"
    )

    def __repr__(self):
        return f"<System {self.name} [{self.system_type}]>"


from app.models.facility import Equipment  # noqa: E402, F401
