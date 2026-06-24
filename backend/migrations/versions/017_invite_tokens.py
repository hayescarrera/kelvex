"""Invite tokens — time-limited email invitation links.

Adds: invite_tokens table for per-email invite links with role/facility scope.

Revision ID: 017
Revises: 016
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invite_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("token", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="operator"),
        sa.Column("facility_ids", postgresql.JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["used_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_invite_tokens_token", "invite_tokens", ["token"])
    op.create_index("ix_invite_tokens_email", "invite_tokens", ["email"])
    op.create_index("ix_invite_tokens_org", "invite_tokens", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_invite_tokens_org", "invite_tokens")
    op.drop_index("ix_invite_tokens_email", "invite_tokens")
    op.drop_index("ix_invite_tokens_token", "invite_tokens")
    op.drop_table("invite_tokens")
