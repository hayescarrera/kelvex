"""Add controller_url to edge_agents and tunnel_sessions.

The columns were added to the models (tunnel WIP) without a migration, so
every EdgeAgent/TunnelSession query 500'd against a migrated database while
tests passed on metadata-created sqlite. Found during the 2026-07 audit.

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("edge_agents", sa.Column("controller_url", sa.String(500), nullable=True))
    op.add_column("tunnel_sessions", sa.Column("controller_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("tunnel_sessions", "controller_url")
    op.drop_column("edge_agents", "controller_url")
