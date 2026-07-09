"""Energy analytics foundation.

Adds: energy_system_config, energy_opportunities, savings_verification tables;
blended_usd_per_kwh / demand_usd_per_kw on facilities; telemetry_15m continuous
aggregate (TimescaleDB); system_15m pivot view; site_opportunity_rollup view.

Revision ID: 018
Revises: 017
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extend facilities with energy cost fields ──────────────
    op.add_column("facilities", sa.Column("blended_usd_per_kwh", sa.Float(), nullable=True))
    op.add_column("facilities", sa.Column("demand_usd_per_kw", sa.Float(), nullable=True))

    # ── Energy config per system (refrigerant, condenser type, etc.) ──
    op.create_table(
        "energy_system_config",
        sa.Column("system_id", sa.UUID(), nullable=False),
        sa.Column("refrigerant", sa.String(20), nullable=False, server_default="R448A"),
        sa.Column("condenser_type", sa.String(20), nullable=False, server_default="air_cooled"),
        sa.Column("sct_floor_f", sa.Float(), nullable=True, server_default="70.0"),
        sa.Column("design_approach_f", sa.Float(), nullable=True, server_default="15.0"),
        sa.Column("defrost_heater_kw", sa.Float(), nullable=True),
        sa.Column("rated_tons", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("system_id"),
    )

    # ── opp_type enum ──────────────────────────────────────────
    op.execute("""
        CREATE TYPE opp_type AS ENUM (
            'excess_lift',
            'defrost_overrun',
            'defrost_underrun',
            'compressor_degradation',
            'condenser_fouling',
            'charge_anomaly',
            'setpoint_drift'
        )
    """)

    # ── energy_opportunities ───────────────────────────────────
    op.create_table(
        "energy_opportunities",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", sa.UUID(), nullable=False),
        sa.Column("system_id", sa.UUID(), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("opp_type", postgresql.ENUM(
            "excess_lift", "defrost_overrun", "defrost_underrun",
            "compressor_degradation", "condenser_fouling", "charge_anomaly", "setpoint_drift",
            name="opp_type", create_type=False,
        ), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("estimated_kwh_year", sa.Float(), nullable=True),
        sa.Column("estimated_usd_year", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("work_order_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("system_id", "equipment_id", "opp_type", "window_start",
                            name="uq_opportunity_per_window"),
    )
    op.create_index("ix_energy_opp_facility", "energy_opportunities", ["facility_id"])
    op.create_index("ix_energy_opp_system", "energy_opportunities", ["system_id"])
    op.create_index("ix_energy_opp_status", "energy_opportunities", ["status"])
    op.create_index("ix_energy_opp_detected", "energy_opportunities", ["detected_at"])

    # ── savings_verification (M&V — IPMVP Option C) ───────────
    op.create_table(
        "savings_verification",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("opportunity_id", sa.UUID(), nullable=False),
        sa.Column("verified_kwh_year", sa.Float(), nullable=True),
        sa.Column("verified_usd_year", sa.Float(), nullable=True),
        sa.Column("method", sa.String(100), nullable=False, server_default="IPMVP-C weather-normalized"),
        sa.Column("baseline_kwh", sa.Float(), nullable=True),
        sa.Column("post_kwh", sa.Float(), nullable=True),
        sa.Column("baseline_period_days", sa.Integer(), nullable=True),
        sa.Column("post_period_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["opportunity_id"], ["energy_opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_savings_verification_opp", "savings_verification", ["opportunity_id"])

    # ── telemetry_15m continuous aggregate (TimescaleDB) ──────
    # Aggregates raw telemetry into 15-min buckets by equipment + metric.
    # No JOINs — continuous aggregates must reference only the hypertable.
    # system_15m view below joins this to get system-level context.
    op.execute("""
        CREATE MATERIALIZED VIEW telemetry_15m
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('15 minutes', time) AS bucket,
            equipment_id,
            metric_name,
            avg(value)         AS avg_value,
            max(value)         AS max_value,
            min(value)         AS min_value,
            last(value, time)  AS last_value,
            count(*)           AS sample_count
        FROM telemetry
        GROUP BY 1, equipment_id, metric_name
        WITH NO DATA
    """)

    op.execute("""
        SELECT add_continuous_aggregate_policy('telemetry_15m',
            start_offset => INTERVAL '3 days',
            end_offset   => INTERVAL '15 minutes',
            schedule_interval => INTERVAL '15 minutes')
    """)

    # ── system_15m pivot view ──────────────────────────────────
    # Regular view that joins telemetry_15m to equipment to produce
    # one row per (bucket, facility, system) with metrics as columns.
    op.execute("""
        CREATE VIEW system_15m AS
        SELECT
            t.bucket,
            e.facility_id,
            e.system_id,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'sst')                    AS sst,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'sct')                    AS sct,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'suction_pressure')       AS suction_psig,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'discharge_pressure')     AS discharge_psig,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'suction_temp')           AS suction_temp,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'liquid_temp')            AS liquid_temp,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'ambient_wet_bulb')       AS wet_bulb,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'ambient_dry_bulb')       AS dry_bulb,
            sum(t.avg_value) FILTER (WHERE t.metric_name = 'compressor_power')       AS comp_kw,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'box_temp')               AS box_temp,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'box_setpoint')           AS box_setpoint,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'head_pressure_setpoint') AS head_pressure_setpoint,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'suction_setpoint')       AS suction_setpoint,
            max(t.avg_value) FILTER (WHERE t.metric_name = 'defrost_state')          AS defrost_state
        FROM telemetry_15m t
        JOIN equipment e ON e.id = t.equipment_id
        GROUP BY t.bucket, e.facility_id, e.system_id
    """)

    # ── site_opportunity_rollup view ───────────────────────────
    op.execute("""
        CREATE VIEW site_opportunity_rollup AS
        SELECT
            facility_id,
            count(*)                                          AS total_count,
            count(*) FILTER (WHERE status = 'open')          AS open_count,
            sum(estimated_usd_year) FILTER (WHERE status = 'open') AS open_usd_year,
            sum(estimated_kwh_year) FILTER (WHERE status = 'open') AS open_kwh_year,
            max(detected_at) FILTER (WHERE status = 'open')  AS latest_detected_at
        FROM energy_opportunities
        GROUP BY facility_id
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS site_opportunity_rollup")
    op.execute("DROP VIEW IF EXISTS system_15m")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS telemetry_15m CASCADE")
    op.drop_index("ix_savings_verification_opp", "savings_verification")
    op.drop_table("savings_verification")
    op.drop_index("ix_energy_opp_detected", "energy_opportunities")
    op.drop_index("ix_energy_opp_status", "energy_opportunities")
    op.drop_index("ix_energy_opp_system", "energy_opportunities")
    op.drop_index("ix_energy_opp_facility", "energy_opportunities")
    op.drop_table("energy_opportunities")
    op.execute("DROP TYPE IF EXISTS opp_type")
    op.drop_table("energy_system_config")
    op.drop_column("facilities", "demand_usd_per_kw")
    op.drop_column("facilities", "blended_usd_per_kwh")
