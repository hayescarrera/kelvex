"""Add callback detection fields to repair_records.

Adds three nullable columns to repair_records so the system can track whether
a repair actually fixed the root cause (i.e., the circuit leaked again within 30 days).

Revision ID: 014
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "014"
down_revision = "013"


def upgrade():
    op.add_column(
        "repair_records",
        sa.Column("callback_detected", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "repair_records",
        sa.Column("callback_detected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "repair_records",
        sa.Column("callback_lbs_within_30d", sa.Float(), nullable=True),
    )


def downgrade():
    op.drop_column("repair_records", "callback_lbs_within_30d")
    op.drop_column("repair_records", "callback_detected_at")
    op.drop_column("repair_records", "callback_detected")
