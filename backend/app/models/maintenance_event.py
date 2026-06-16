"""
MaintenanceEvent — immutable record of work performed on a site or piece of equipment.

Distinct from MaintenanceTask (a planning/work-order object). This is the
append-only event log: what was done, by whom, when, on what, and why.
Links optionally to the alert or refrigerant event that triggered the work.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class MaintenanceEvent(Base):
    """Append-only record of maintenance work performed."""

    __tablename__ = "maintenance_events"
    __table_args__ = (
        Index("ix_maintenance_events_org_occurred", "org_id", "occurred_at"),
        Index("ix_maintenance_events_equipment", "equipment_id"),
        Index("ix_maintenance_events_facility", "facility_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True
    )

    # What triggered this work
    linked_alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True
    )
    linked_refrigerant_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leak_events.id", ondelete="SET NULL"), nullable=True
    )

    # Work details
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # repair | inspection | service | replacement | refrigerant | other
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Who did it
    technician_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    technician_company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self):
        return f"<MaintenanceEvent {self.event_type} on equipment={self.equipment_id} at={self.occurred_at}>"
