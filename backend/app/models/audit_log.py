"""
General Activity Audit Log — tracks who changed what across the platform.

Every significant mutation (create, update, delete) on a resource is recorded
with the actor, action, resource type/id, a JSON diff of changes, and optional
facility scope.  This is separate from ControlAuditLog which tracks device
commands specifically.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class ActivityLog(Base):
    """Immutable audit trail for platform-level changes."""

    __tablename__ = "activity_logs"
    __table_args__ = (
        Index("ix_activity_logs_org_created", "org_id", "created_at"),
        Index("ix_activity_logs_resource", "resource_type", "resource_id"),
        Index("ix_activity_logs_actor", "actor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # What happened
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # create, update, delete, login, invite, etc.
    resource_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # facility, zone, equipment, user, rule, sequence, etc.
    resource_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # UUID of the affected resource
    resource_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Human-readable name

    # Optional facility scope (for facility-level changes)
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True
    )

    # Change details
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # Human-readable description
    changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"field": {"old": x, "new": y}}
    metadata_extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Extra context

    # Request context
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self):
        return f"<ActivityLog {self.action} {self.resource_type} by {self.actor_email}>"
