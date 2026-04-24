"""Add routing fields to notification channels.

Channels can now be scoped to:
  - specific facilities (facility_ids JSONB array, null = all)
  - minimum severity level (min_severity, null = all)
  - alert categories (categories JSONB array, null = all)

This lets operators route equipment alerts to technicians
and cost/demand alerts to plant managers.

Revision ID: 011
Revises: 010
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # facility_ids: JSON array of facility UUIDs, null = all facilities
    op.add_column(
        "notification_channels",
        sa.Column("facility_ids", JSONB, nullable=True),
    )
    # min_severity: only fire for alerts at this severity or above
    # null = all severities. Values: critical, high, medium, low, info
    op.add_column(
        "notification_channels",
        sa.Column("min_severity", sa.String(20), nullable=True),
    )
    # categories: JSON array of alert categories to match, null = all
    op.add_column(
        "notification_channels",
        sa.Column("categories", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_channels", "categories")
    op.drop_column("notification_channels", "min_severity")
    op.drop_column("notification_channels", "facility_ids")
