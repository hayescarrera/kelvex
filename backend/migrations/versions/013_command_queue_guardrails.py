"""Add source column to command_queue for autonomy loop guardrails.

Adds:
  - command_queue.source: tracks whether a command came from a user, automation rule,
    schedule, or system process — enables the pending_approval gate for automated commands
  - Indexes on state and issued_at for the command queue management endpoints

Revision ID: 013
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "0f5b44a26446"


def upgrade():
    op.add_column(
        "command_queue",
        sa.Column("source", sa.String(50), nullable=False, server_default="user"),
    )
    op.create_index("ix_command_queue_facility_state", "command_queue", ["facility_id", "state"])
    op.create_index("ix_command_queue_issued_at", "command_queue", ["issued_at"])


def downgrade():
    op.drop_index("ix_command_queue_issued_at", table_name="command_queue")
    op.drop_index("ix_command_queue_facility_state", table_name="command_queue")
    op.drop_column("command_queue", "source")
