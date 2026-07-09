"""
TunnelSession model — audit record for every controller tunnel session.

When an authorized user clicks "Access Controller," the tunnel broker signals
the edge agent to open a reverse tunnel to the controller's local web UI.
Every such session is logged here: who, which device, when, how long.

This is the sole inbound path to controls and must be immutable and complete.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class TunnelSession(Base):
    """Immutable audit record of a controller tunnel session."""

    __tablename__ = "tunnel_sessions"
    __table_args__ = (
        Index("ix_tunnel_sessions_org_started", "org_id", "started_at"),
        Index("ix_tunnel_sessions_agent", "agent_id"),
        Index("ix_tunnel_sessions_user", "user_id"),
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
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("edge_agents.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Denormalized for display without joins
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_device: Mapped[str | None] = mapped_column(String(255), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # How the session ended: timeout | user_close | revoked | error
    end_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    controller_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # copied from agent at session start

    def __repr__(self):
        return f"<TunnelSession user={self.user_email} agent={self.agent_id} started={self.started_at}>"
