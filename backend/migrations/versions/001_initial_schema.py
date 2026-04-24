"""Initial schema — all core tables + TimescaleDB hypertable

Revision ID: 001
Revises: None
Create Date: 2026-04-16

Note: TimescaleDB compression policies and continuous aggregates are
deferred to migration 002 — they require running outside a transaction
block and aren't needed until Phase 2 (live telemetry).
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Organizations ---
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("plan_tier", sa.String(50), server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- Users ---
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("is_admin", sa.Boolean, server_default=sa.text("false")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # --- Utilities ---
    op.create_table(
        "utilities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("openei_id", sa.String(100), unique=True, nullable=True),
        sa.Column("eia_id", sa.String(20), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("iso_region", sa.String(20), nullable=True),
        sa.Column("regulated", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- Rate Schedules ---
    op.create_table(
        "rate_schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("utility_id", UUID(as_uuid=True), sa.ForeignKey("utilities.id"), nullable=False),
        sa.Column("openei_rate_id", sa.String(100), nullable=True),
        sa.Column("schedule_name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("sector", sa.String(50), server_default="commercial"),
        sa.Column("effective_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("demand_rates", JSONB, nullable=False, server_default="{}"),
        sa.Column("energy_rates", JSONB, nullable=False, server_default="{}"),
        sa.Column("fixed_charges", JSONB, nullable=True, server_default="{}"),
        sa.Column("metadata", JSONB, nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- Facilities ---
    op.create_table(
        "facilities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("zip_code", sa.String(10), nullable=True),
        sa.Column("sqft", sa.Integer, nullable=True),
        sa.Column("zone_types", ARRAY(sa.String), nullable=True),
        sa.Column("utility_id", UUID(as_uuid=True), sa.ForeignKey("utilities.id"), nullable=True),
        sa.Column("rate_schedule_id", UUID(as_uuid=True), sa.ForeignKey("rate_schedules.id"), nullable=True),
        sa.Column("iso_region", sa.String(20), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- Equipment ---
    op.create_table(
        "equipment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("equipment_type", sa.String(100), nullable=False),
        sa.Column("manufacturer", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("controller_type", sa.String(100), nullable=True),
        sa.Column("protocol", sa.String(50), nullable=True),
        sa.Column("commissioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- Utility Bills ---
    op.create_table(
        "utility_bills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("total_kwh", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("peak_demand_kw", sa.Numeric(10, 2), nullable=True),
        sa.Column("demand_charge", sa.Numeric(10, 2), nullable=True),
        sa.Column("energy_charge", sa.Numeric(10, 2), nullable=True),
        sa.Column("source_file", sa.String(500), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- Demand Analyses ---
    op.create_table(
        "demand_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("peak_demand_kw", sa.Numeric(10, 2), nullable=True),
        sa.Column("peak_demand_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ratchet_demand_kw", sa.Numeric(10, 2), nullable=True),
        sa.Column("demand_charge_actual", sa.Numeric(10, 2), nullable=True),
        sa.Column("demand_charge_optimized", sa.Numeric(10, 2), nullable=True),
        sa.Column("savings_potential", sa.Numeric(10, 2), nullable=True),
        sa.Column("peak_events", JSONB, nullable=True),
        sa.Column("load_profile", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- Savings Scenarios ---
    op.create_table(
        "savings_scenarios",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("scenario_name", sa.String(255), nullable=False),
        sa.Column("parameters", JSONB, nullable=False),
        sa.Column("annual_savings", sa.Numeric(10, 2), nullable=True),
        sa.Column("demand_savings", sa.Numeric(10, 2), nullable=True),
        sa.Column("energy_savings", sa.Numeric(10, 2), nullable=True),
        sa.Column("payback_months", sa.SmallInteger, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # --- Telemetry (TimescaleDB hypertable) ---
    op.create_table(
        "telemetry",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("quality", sa.SmallInteger, server_default="0"),
        sa.PrimaryKeyConstraint("time", "equipment_id", "metric_name"),
    )

    # Convert to TimescaleDB hypertable
    op.execute("SELECT create_hypertable('telemetry', 'time');")

    # Index for typical queries: get readings for one piece of equipment
    op.create_index(
        "idx_telemetry_equip_metric_time",
        "telemetry",
        ["equipment_id", "metric_name", sa.text("time DESC")],
    )

    # NOTE: Compression policies and continuous aggregates (telemetry_15min,
    # telemetry_hourly) will be added in migration 002 when Phase 2 needs them.
    # They require running outside a transaction block which Alembic doesn't
    # support by default.


def downgrade() -> None:
    op.drop_table("telemetry")
    op.drop_table("savings_scenarios")
    op.drop_table("demand_analyses")
    op.drop_table("utility_bills")
    op.drop_table("equipment")
    op.drop_table("facilities")
    op.drop_table("rate_schedules")
    op.drop_table("utilities")
    op.drop_table("users")
    op.drop_table("organizations")
