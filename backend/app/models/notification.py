"""Notification models for alert delivery (email, webhook, in-app)."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base

# Severity ranking for min_severity filtering
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class NotificationChannel(Base):
    """A configured notification destination (email, webhook, etc.)."""
    __tablename__ = "notification_channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False)  # email, webhook, slack
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    # email: {"recipients": ["a@b.com"]}
    # webhook: {"url": "https://...", "headers": {}}
    # slack: {"webhook_url": "https://hooks.slack.com/..."}
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Routing filters ─────────────────────────
    # null = no filter (all facilities/severities/categories)
    facility_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    min_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def matches_alert(self, facility_id: str | None, severity: str | None, category: str | None) -> bool:
        """Check if this channel should fire for the given alert attributes."""
        # Facility filter
        if self.facility_ids and facility_id:
            if str(facility_id) not in [str(f) for f in self.facility_ids]:
                return False
        # Severity filter
        if self.min_severity and severity:
            channel_rank = SEVERITY_RANK.get(self.min_severity, 4)
            alert_rank = SEVERITY_RANK.get(severity, 4)
            if alert_rank > channel_rank:
                return False  # Alert is less severe than minimum
        # Category filter
        if self.categories and category:
            if category not in self.categories:
                return False
        return True

    def __repr__(self):
        return f"<NotificationChannel {self.name} ({self.channel_type})>"


class NotificationLog(Base):
    """Record of a sent notification."""
    __tablename__ = "notification_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("notification_channels.id"), nullable=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="sent")  # sent, failed, pending
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<NotificationLog {self.subject[:30]} ({self.status})>"
