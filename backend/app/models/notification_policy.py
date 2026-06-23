"""
NotificationPolicy — per-user or org-wide alert notification rules.

Each policy defines:
  - Which alerts to watch (by category, severity, facility)
  - Which channels to use for delivery
  - When NOT to notify (quiet hours)
  - How often to re-notify (cooldown)
  - Whether to batch into a digest
  - Whether and how to escalate unacknowledged alerts
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class NotificationPolicy(Base):
    __tablename__ = "notification_policies"
    __table_args__ = (
        Index("ix_notif_policies_org", "org_id"),
        Index("ix_notif_policies_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    # null = org-wide default; set = this user's personal preferences
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Default")

    # ── Scope filters ───────────────────────────────
    # null = all facilities; list = only these facilities
    facility_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # null = all categories; list e.g. ["temperature", "refrigerant", "equipment"]
    categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Minimum severity to notify on: info < low < medium < high < critical
    min_severity: Mapped[str] = mapped_column(String(20), nullable=False, default="high")

    # ── Channel selection ───────────────────────────
    # null = use all org channels matching scope; list = only these channel UUIDs
    channel_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # ── Quiet hours (UTC) ───────────────────────────
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quiet_hours_start: Mapped[int] = mapped_column(Integer, nullable=False, default=22)  # 0–23
    quiet_hours_end: Mapped[int] = mapped_column(Integer, nullable=False, default=7)    # 0–23
    # Severity that punches through quiet hours even when enabled (null = nothing bypasses)
    quiet_hours_bypass_severity: Mapped[str | None] = mapped_column(String(20), nullable=True, default="critical")

    # ── Deduplication / cooldown ────────────────────
    # Don't re-notify for the same (facility, alert_type) within this window
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # ── Digest ─────────────────────────────────────
    # If True, batch alerts into a single digest email instead of per-alert messages
    digest_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    digest_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=4)

    # ── Escalation ──────────────────────────────────
    # If True and alert is not acknowledged within escalation_delay_minutes, escalate
    escalation_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # Channels for escalation (null = same as primary channels)
    escalation_channel_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Minimum severity to escalate (usually critical only)
    escalation_min_severity: Mapped[str] = mapped_column(String(20), nullable=False, default="critical")

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def matches_alert(self, facility_id: uuid.UUID, severity: str, category: str) -> bool:
        """Return True if this policy should fire for the given alert."""
        if not self.enabled:
            return False
        if self.facility_ids and str(facility_id) not in self.facility_ids:
            return False
        if self.categories and category not in self.categories:
            return False
        if SEVERITY_RANK.get(severity, 0) < SEVERITY_RANK.get(self.min_severity, 3):
            return False
        return True

    def is_quiet_hour(self, now_utc_hour: int) -> bool:
        """Return True if we're currently in the quiet window (UTC)."""
        if not self.quiet_hours_enabled:
            return False
        s, e = self.quiet_hours_start, self.quiet_hours_end
        if s <= e:
            return s <= now_utc_hour < e
        # Wraps midnight e.g. 22–07
        return now_utc_hour >= s or now_utc_hour < e

    def bypasses_quiet_hours(self, severity: str) -> bool:
        """Return True if this severity punches through quiet hours."""
        if not self.quiet_hours_bypass_severity:
            return False
        return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(self.quiet_hours_bypass_severity, 4)
