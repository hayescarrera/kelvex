"""Notification policies — per-user granular alert delivery rules.

Adds: notification_policies table with quiet hours, cooldown, digest, and escalation config.

Revision ID: 016
Revises: 015
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False, server_default="Default"),
        # Scope
        sa.Column("facility_ids", postgresql.JSONB(), nullable=True),
        sa.Column("categories", postgresql.JSONB(), nullable=True),
        sa.Column("min_severity", sa.String(20), nullable=False, server_default="high"),
        # Channel selection
        sa.Column("channel_ids", postgresql.JSONB(), nullable=True),
        # Quiet hours (UTC)
        sa.Column("quiet_hours_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("quiet_hours_start", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("quiet_hours_end", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("quiet_hours_bypass_severity", sa.String(20), nullable=True, server_default="critical"),
        # Cooldown
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="60"),
        # Digest
        sa.Column("digest_mode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("digest_interval_hours", sa.Integer(), nullable=False, server_default="4"),
        # Escalation
        sa.Column("escalation_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("escalation_delay_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("escalation_channel_ids", postgresql.JSONB(), nullable=True),
        sa.Column("escalation_min_severity", sa.String(20), nullable=False, server_default="critical"),
        # Meta
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notif_policies_org", "notification_policies", ["org_id"])
    op.create_index("ix_notif_policies_user", "notification_policies", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notif_policies_user", "notification_policies")
    op.drop_index("ix_notif_policies_org", "notification_policies")
    op.drop_table("notification_policies")
