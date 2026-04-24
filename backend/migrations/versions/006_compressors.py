"""Add compressors and compressor_readings tables

Revision ID: 006
Revises: 005
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compressors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        # Identity
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tag", sa.String(100), nullable=True),
        sa.Column("manufacturer", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("serial_number", sa.String(100), nullable=True),
        sa.Column("compressor_type", sa.String(50), nullable=False, server_default="screw"),
        # Refrigerant
        sa.Column("refrigerant", sa.String(20), nullable=False, server_default="NH3"),
        sa.Column("refrigerant_charge_lbs", sa.Float, nullable=True),
        # Ratings
        sa.Column("hp", sa.Float, nullable=True),
        sa.Column("capacity_tons", sa.Float, nullable=True),
        sa.Column("design_suction_psi", sa.Float, nullable=True),
        sa.Column("design_discharge_psi", sa.Float, nullable=True),
        sa.Column("max_discharge_temp_f", sa.Float, nullable=True),
        # Alarm thresholds
        sa.Column("alarm_discharge_psi_high", sa.Float, nullable=True),
        sa.Column("alarm_suction_psi_low", sa.Float, nullable=True),
        sa.Column("alarm_oil_temp_high", sa.Float, nullable=True),
        sa.Column("alarm_bearing_temp_high", sa.Float, nullable=True),
        sa.Column("alarm_vibration_high", sa.Float, nullable=True),
        sa.Column("alarm_amp_draw_high", sa.Float, nullable=True),
        # Maintenance
        sa.Column("commissioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_overhaul_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_hours", sa.Integer, nullable=True),
        sa.Column("next_maintenance_hours", sa.Integer, nullable=True),
        # State
        sa.Column("state", sa.String(30), nullable=False, server_default="offline"),
        sa.Column("health_score", sa.Float, nullable=True),
        sa.Column("last_reading_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rack_name", sa.String(100), nullable=True),
        sa.Column("metadata", JSONB, nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_compressor_facility", "compressors", ["facility_id"])

    op.create_table(
        "compressor_readings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("compressor_id", UUID(as_uuid=True), sa.ForeignKey("compressors.id", ondelete="CASCADE"), nullable=False),
        # Core operating parameters
        sa.Column("discharge_pressure_psi", sa.Float, nullable=True),
        sa.Column("suction_pressure_psi", sa.Float, nullable=True),
        sa.Column("discharge_temp_f", sa.Float, nullable=True),
        sa.Column("suction_temp_f", sa.Float, nullable=True),
        sa.Column("oil_pressure_psi", sa.Float, nullable=True),
        sa.Column("oil_temp_f", sa.Float, nullable=True),
        sa.Column("bearing_temp_f", sa.Float, nullable=True),
        # Electrical
        sa.Column("amp_draw", sa.Float, nullable=True),
        sa.Column("kw", sa.Float, nullable=True),
        sa.Column("power_factor", sa.Float, nullable=True),
        # Mechanical
        sa.Column("vibration_ips", sa.Float, nullable=True),
        sa.Column("slide_valve_pct", sa.Float, nullable=True),
        sa.Column("rpm", sa.Float, nullable=True),
        # Performance
        sa.Column("superheat_f", sa.Float, nullable=True),
        sa.Column("subcooling_f", sa.Float, nullable=True),
        sa.Column("compression_ratio", sa.Float, nullable=True),
        sa.Column("efficiency_pct", sa.Float, nullable=True),
        # Status
        sa.Column("running", sa.Boolean, nullable=True),
        sa.Column("alarm_active", sa.Boolean, server_default="false"),
        sa.Column("alarm_codes", JSONB, nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_reading_compressor_time", "compressor_readings", ["compressor_id", "recorded_at"])
    op.create_index("ix_reading_recorded_at", "compressor_readings", ["recorded_at"])


def downgrade() -> None:
    op.drop_table("compressor_readings")
    op.drop_table("compressors")
