"""Zone sensors, zone readings, and control extensions.

Adds:
  - zone_sensors: physical sensor hardware linked to zones (temp probes, door contacts, etc.)
  - zone_readings: time-series data from zone sensors
  - write_register_map on device_profiles for writable setpoints
  - defrost_config on compressors for defrost scheduling
  - rack assignment: compressor_rack table for staging/sequencing
  - condenser/evaporator equipment support in device profiles

Revision ID: 008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "008"
down_revision = "007"


def upgrade():
    # ── Zone Sensors ────────────────────────────────────
    op.create_table(
        "zone_sensors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("zone_id", UUID(as_uuid=True), sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_device_id", UUID(as_uuid=True), nullable=True),  # links to agent_devices if polled via Modbus
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sensor_type", sa.String(50), nullable=False),  # temperature, humidity, door_contact, ammonia, pressure_differential, glycol_temp
        sa.Column("unit", sa.String(20), nullable=True),  # °F, °C, %RH, ppm, psi
        sa.Column("location_desc", sa.String(500), nullable=True),  # "East wall, 8ft high"
        # Thresholds
        sa.Column("alarm_high", sa.Float, nullable=True),
        sa.Column("alarm_low", sa.Float, nullable=True),
        sa.Column("warn_high", sa.Float, nullable=True),
        sa.Column("warn_low", sa.Float, nullable=True),
        # Current state
        sa.Column("current_value", sa.Float, nullable=True),
        sa.Column("current_state", sa.String(20), server_default="normal"),  # normal, warning, alarm, offline
        sa.Column("last_reading_at", sa.DateTime(timezone=True), nullable=True),
        # Config
        sa.Column("poll_interval_sec", sa.Integer, server_default="30"),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_zone_sensors_zone", "zone_sensors", ["zone_id"])

    # ── Zone Readings (time-series) ─────────────────────
    op.create_table(
        "zone_readings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sensor_id", UUID(as_uuid=True), sa.ForeignKey("zone_sensors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_id", UUID(as_uuid=True), sa.ForeignKey("zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("quality", sa.Integer, server_default="0"),  # 0=good, 1=uncertain, 2=bad
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_zone_readings_sensor_time", "zone_readings", ["sensor_id", "recorded_at"])
    op.create_index("ix_zone_readings_zone_time", "zone_readings", ["zone_id", "recorded_at"])

    # ── Compressor Rack (for staging/sequencing) ────────
    op.create_table(
        "compressor_racks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),  # "Engine Room 1"
        sa.Column("suction_group", sa.String(100), nullable=True),  # low-temp, high-temp, booster
        sa.Column("design_suction_psi", sa.Float, nullable=True),
        sa.Column("design_discharge_psi", sa.Float, nullable=True),
        # Staging config
        sa.Column("staging_mode", sa.String(50), server_default="manual"),  # manual, efficiency, round_robin, load_balance
        sa.Column("staging_config", JSONB, nullable=True),
        # Demand response
        sa.Column("demand_response_enabled", sa.Boolean, server_default="false"),
        sa.Column("min_capacity_pct", sa.Float, server_default="25"),  # never go below this
        sa.Column("max_coast_minutes", sa.Integer, server_default="60"),  # max time to shed load
        sa.Column("thermal_mass_factor", sa.Float, server_default="1.0"),  # how much thermal mass (higher = more coasting)
        # State
        sa.Column("total_kw", sa.Float, nullable=True),
        sa.Column("active_compressors", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_racks_facility", "compressor_racks", ["facility_id"])

    # ── Add rack_id to compressors ──────────────────────
    op.add_column("compressors", sa.Column("rack_id", UUID(as_uuid=True), nullable=True))
    op.add_column("compressors", sa.Column("staging_priority", sa.Integer, nullable=True))  # 1=lead, 2=lag1, 3=lag2
    op.add_column("compressors", sa.Column("efficiency_kw_per_ton", sa.Float, nullable=True))

    # ── Defrost config on compressors ───────────────────
    op.add_column("compressors", sa.Column("defrost_config", JSONB, nullable=True))
    # defrost_config format:
    # {
    #   "method": "hot_gas",             // hot_gas, electric, air, off_cycle
    #   "max_duration_min": 30,
    #   "min_interval_hours": 4,
    #   "coil_dp_trigger_psi": 2.5,      // pressure differential trigger
    #   "time_trigger_hours": 6,          // fallback timer
    #   "terminate_temp_f": 45,           // end defrost when coil hits this
    #   "drip_time_min": 5,              // drain time after defrost
    #   "fan_delay_min": 3               // fan restart delay
    # }

    # ── Write register map on device profiles ───────────
    op.add_column("device_profiles", sa.Column("write_register_map", JSONB, nullable=True))
    # write_register_map format:
    # {
    #   "capacity_setpoint": {
    #     "register": 7060, "type": "holding", "data_type": "uint16",
    #     "scale": 1.0, "offset": 0, "unit": "%", "min": 25, "max": 100,
    #     "description": "Capacity setpoint (slide valve position)"
    #   },
    #   "suction_setpoint": {
    #     "register": 7062, "type": "holding", "data_type": "float32",
    #     "scale": 0.1, "offset": 0, "unit": "psi", "min": 10, "max": 60
    #   },
    #   "start_stop": {
    #     "register": 7100, "type": "holding", "data_type": "uint16",
    #     "scale": 1.0, "offset": 0, "description": "0=stop, 1=start"
    #   }
    # }

    # ── Expand device profiles equipment_type options ───
    # Already supports: compressor, condenser, evaporator, vessel
    # Add sensor support via the zone_sensors table instead

    # ── Control audit log ───────────────────────────────
    op.create_table(
        "control_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("command_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),  # set_capacity, start_compressor, trigger_defrost, etc.
        sa.Column("target_type", sa.String(50), nullable=False),  # compressor, zone, rack, sensor
        sa.Column("target_id", UUID(as_uuid=True), nullable=True),
        sa.Column("target_name", sa.String(200), nullable=True),
        sa.Column("parameters", JSONB, nullable=True),
        sa.Column("result", sa.String(20), nullable=True),  # success, failed, pending
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_control_audit_facility", "control_audit_log", ["facility_id", "created_at"])

    # ── Seed write_register_map for existing profiles ───
    from sqlalchemy.orm import Session
    bind = op.get_bind()
    session = Session(bind=bind)

    # Frick Quantum HD — writable setpoints per documentation (registers 7060+)
    session.execute(sa.text("""
        UPDATE device_profiles
        SET write_register_map = :wrm
        WHERE manufacturer = 'Frick' AND model = 'Quantum HD'
    """), {"wrm": '{"capacity_setpoint": {"register": 7060, "type": "holding", "data_type": "uint16", "scale": 1.0, "offset": 0, "unit": "%", "min": 25, "max": 100, "description": "Capacity setpoint (slide valve)"}, "suction_setpoint_psi": {"register": 7062, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "psi", "min": 10, "max": 55, "description": "Suction pressure setpoint"}, "start_stop": {"register": 7100, "type": "holding", "data_type": "uint16", "scale": 1.0, "offset": 0, "min": 0, "max": 1, "description": "0=stop 1=start"}}'})

    # Vilter VSM — writable
    session.execute(sa.text("""
        UPDATE device_profiles
        SET write_register_map = :wrm
        WHERE manufacturer = 'Vilter' AND model = 'VSM/VSSG'
    """), {"wrm": '{"capacity_setpoint": {"register": 30100, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "%", "min": 25, "max": 100, "description": "Capacity setpoint"}, "suction_setpoint_psi": {"register": 30102, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "psi", "min": 10, "max": 55, "description": "Suction pressure setpoint"}}'})

    # GEA Omni
    session.execute(sa.text("""
        UPDATE device_profiles
        SET write_register_map = :wrm
        WHERE manufacturer = 'GEA' AND model = 'Omni'
    """), {"wrm": '{"capacity_setpoint": {"register": 1100, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "%", "min": 25, "max": 100, "description": "Capacity setpoint"}, "start_stop": {"register": 1200, "type": "holding", "data_type": "uint16", "scale": 1.0, "offset": 0, "min": 0, "max": 1, "description": "0=stop 1=start"}}'})

    session.commit()


def downgrade():
    op.drop_table("control_audit_log")
    op.drop_column("device_profiles", "write_register_map")
    op.drop_column("compressors", "defrost_config")
    op.drop_column("compressors", "efficiency_kw_per_ton")
    op.drop_column("compressors", "staging_priority")
    op.drop_column("compressors", "rack_id")
    op.drop_table("compressor_racks")
    op.drop_table("zone_readings")
    op.drop_table("zone_sensors")
