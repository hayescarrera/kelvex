"""Link work orders to their source alert.

maintenance_tasks.source_alert_id lets the alert inbox show the work-order
lifecycle (open → in progress → completed) inline next to the alert that
spawned it, instead of a fire-and-forget WO button.

Revision ID: 021
Revises: 020
"""

from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "maintenance_tasks",
        sa.Column("source_alert_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_maintenance_tasks_source_alert",
        "maintenance_tasks", "alerts",
        ["source_alert_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_maintenance_tasks_source_alert", "maintenance_tasks", ["source_alert_id"])


def downgrade() -> None:
    op.drop_index("ix_maintenance_tasks_source_alert", table_name="maintenance_tasks")
    op.drop_constraint("fk_maintenance_tasks_source_alert", "maintenance_tasks", type_="foreignkey")
    op.drop_column("maintenance_tasks", "source_alert_id")
