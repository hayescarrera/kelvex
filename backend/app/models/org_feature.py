"""
Per-org feature flags for enabling/disabling platform capabilities.

Feature keys:
  - 'auto_detection'  — automated leak detection via pressure trend & add pattern analysis
  - 'forecasting'     — refrigerant consumption forecasting (linear / exponential smoothing)
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class OrgFeature(Base):
    """A feature flag scoped to a specific organization."""
    __tablename__ = "org_features"
    __table_args__ = (
        UniqueConstraint("org_id", "feature_key", name="uq_org_feature_key"),
        Index("ix_org_features_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Reserved for future per-feature configuration (e.g. thresholds, schedules)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<OrgFeature org={self.org_id} key={self.feature_key} enabled={self.enabled}>"
