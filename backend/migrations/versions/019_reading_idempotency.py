"""Reading idempotency — unique constraints for agent batch retries.

Edge agents buffer readings locally and retry batches after network
failures. Without a uniqueness guarantee, a retry whose first attempt
actually landed inserts silent duplicates, which skews leak detection
and compressor health analytics.

Dedupes any existing duplicates (keeping the first row per key), then
adds unique constraints on:
  - compressor_readings (compressor_id, recorded_at)
  - zone_readings      (sensor_id, recorded_at)

Ingestion endpoints switch to INSERT ... ON CONFLICT DO NOTHING.

Revision ID: 019
Revises: 018
"""

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # Remove duplicates before adding the constraints. ctid picks a
        # deterministic survivor per (key) group without needing a sort key.
        op.execute(
            """
            DELETE FROM compressor_readings a
            USING compressor_readings b
            WHERE a.compressor_id = b.compressor_id
              AND a.recorded_at = b.recorded_at
              AND a.ctid > b.ctid
            """
        )
        op.execute(
            """
            DELETE FROM zone_readings a
            USING zone_readings b
            WHERE a.sensor_id = b.sensor_id
              AND a.recorded_at = b.recorded_at
              AND a.ctid > b.ctid
            """
        )

    op.create_unique_constraint(
        "uq_reading_compressor_recorded_at",
        "compressor_readings",
        ["compressor_id", "recorded_at"],
    )
    op.create_unique_constraint(
        "uq_zone_reading_sensor_recorded_at",
        "zone_readings",
        ["sensor_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_reading_compressor_recorded_at", "compressor_readings", type_="unique"
    )
    op.drop_constraint(
        "uq_zone_reading_sensor_recorded_at", "zone_readings", type_="unique"
    )
