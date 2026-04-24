"""Add device_profiles and agent_devices tables for IoT platform.

Revision ID: 007
Revises: 006
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Device profiles (pre-built controller templates) ──
    op.create_table(
        "device_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("manufacturer", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("equipment_type", sa.String(50), nullable=False, server_default="compressor"),
        sa.Column("refrigerant_types", JSONB, server_default="[]"),
        sa.Column("protocol", sa.String(20), nullable=False, server_default="modbus_tcp"),
        sa.Column("default_port", sa.Integer, server_default="502"),
        sa.Column("default_slave_id", sa.Integer, server_default="1"),
        sa.Column("register_map", JSONB, nullable=False, server_default="{}"),
        sa.Column("bacnet_config", JSONB, nullable=True),
        sa.Column("is_builtin", sa.Boolean, server_default="false"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_device_profiles_manufacturer", "device_profiles", ["manufacturer"])

    # ── Agent devices (links agent → controller → compressor) ──
    op.create_table(
        "agent_devices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", UUID(as_uuid=True), nullable=True),
        sa.Column("compressor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer, server_default="502"),
        sa.Column("slave_id", sa.Integer, server_default="1"),
        sa.Column("register_overrides", JSONB, nullable=True, server_default="{}"),
        sa.Column("poll_interval_sec", sa.Integer, server_default="15"),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("connection_state", sa.String(20), server_default="'unknown'"),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("poll_count", sa.Integer, server_default="0"),
        sa.Column("error_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_devices_agent_id", "agent_devices", ["agent_id"])
    op.create_index("ix_agent_devices_compressor_id", "agent_devices", ["compressor_id"])

    # ── Seed built-in device profiles ──
    op.execute("""
    INSERT INTO device_profiles (id, manufacturer, model, display_name, description, equipment_type, refrigerant_types, protocol, default_port, default_slave_id, register_map, is_builtin, is_active)
    VALUES
    (
        gen_random_uuid(), 'Frick', 'Quantum HD',
        'Frick Quantum HD Compressor Controller',
        'Johnson Controls / Frick Quantum HD micro-panel for screw compressors. Modbus TCP interface. Covers all standard operating parameters for single-screw and twin-screw NH3 compressors.',
        'compressor', '["NH3", "R-717"]'::jsonb, 'modbus_tcp', 502, 1,
        '{
          "discharge_pressure":  {"register": 40001, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "psi", "description": "Discharge pressure"},
          "suction_pressure":    {"register": 40003, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "psi", "description": "Suction pressure"},
          "discharge_temp":      {"register": 40005, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Discharge temperature"},
          "suction_temp":        {"register": 40007, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Suction temperature"},
          "oil_temp":            {"register": 40009, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Oil temperature"},
          "bearing_temp":        {"register": 40011, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Bearing temperature"},
          "amp_draw":            {"register": 40013, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "A", "description": "Motor amperage"},
          "kw":                  {"register": 40015, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "kW", "description": "Power consumption"},
          "vibration":           {"register": 40017, "type": "holding", "data_type": "float32", "scale": 0.01, "offset": 0, "unit": "in/s", "description": "Vibration velocity"},
          "slide_valve_pct":     {"register": 40019, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "%", "description": "Slide valve position"},
          "rpm":                 {"register": 40020, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "RPM", "description": "Shaft speed"},
          "oil_pressure":        {"register": 40021, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "psi", "description": "Oil pressure"},
          "running":             {"register": 40023, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "bool", "description": "Running status (1=on)"}
        }'::jsonb,
        true, true
    ),
    (
        gen_random_uuid(), 'Vilter', 'VSM / VSSG',
        'Vilter VSM Single Screw Controller',
        'Emerson / Vilter single-screw compressor controller with Modbus TCP. Standard on VSSG and VSM series ammonia compressors.',
        'compressor', '["NH3", "R-717"]'::jsonb, 'modbus_tcp', 502, 1,
        '{
          "discharge_pressure":  {"register": 30001, "type": "input", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "psi", "description": "Discharge pressure"},
          "suction_pressure":    {"register": 30003, "type": "input", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "psi", "description": "Suction pressure"},
          "discharge_temp":      {"register": 30005, "type": "input", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Discharge temperature"},
          "suction_temp":        {"register": 30007, "type": "input", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Suction temperature"},
          "oil_temp":            {"register": 30009, "type": "input", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Oil injection temperature"},
          "bearing_temp":        {"register": 30011, "type": "input", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Bearing temperature"},
          "amp_draw":            {"register": 30013, "type": "input", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "A", "description": "Motor amperage"},
          "kw":                  {"register": 30015, "type": "input", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "kW", "description": "Power draw"},
          "vibration":           {"register": 30017, "type": "input", "data_type": "float32", "scale": 0.01, "offset": 0, "unit": "in/s", "description": "Vibration"},
          "slide_valve_pct":     {"register": 30019, "type": "input", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "%", "description": "Capacity control position"},
          "rpm":                 {"register": 30020, "type": "input", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "RPM", "description": "Motor speed"},
          "oil_pressure":        {"register": 30021, "type": "input", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "psi", "description": "Oil supply pressure"},
          "running":             {"register": 30023, "type": "input", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "bool", "description": "Compressor running"}
        }'::jsonb,
        true, true
    ),
    (
        gen_random_uuid(), 'Mycom', 'N Series',
        'Mycom N Series Screw Compressor',
        'Mayekawa Mycom N-series industrial screw compressor. Modbus TCP via optional communications card. Common in large cold storage and food processing.',
        'compressor', '["NH3", "R-717", "CO2"]'::jsonb, 'modbus_tcp', 502, 2,
        '{
          "discharge_pressure":  {"register": 100, "type": "holding", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "psi", "description": "Discharge pressure"},
          "suction_pressure":    {"register": 101, "type": "holding", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "psi", "description": "Suction pressure"},
          "discharge_temp":      {"register": 102, "type": "holding", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Discharge temp"},
          "suction_temp":        {"register": 103, "type": "holding", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Suction temp"},
          "oil_temp":            {"register": 104, "type": "holding", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Oil temperature"},
          "bearing_temp":        {"register": 105, "type": "holding", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Bearing temperature"},
          "amp_draw":            {"register": 106, "type": "holding", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "A", "description": "Motor current"},
          "kw":                  {"register": 107, "type": "holding", "data_type": "int16", "scale": 0.1, "offset": 0, "unit": "kW", "description": "Power"},
          "vibration":           {"register": 108, "type": "holding", "data_type": "int16", "scale": 0.01, "offset": 0, "unit": "in/s", "description": "Vibration"},
          "slide_valve_pct":     {"register": 109, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "%", "description": "Slide valve"},
          "rpm":                 {"register": 110, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "RPM", "description": "Shaft RPM"},
          "running":             {"register": 111, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "bool", "description": "Running"}
        }'::jsonb,
        true, true
    ),
    (
        gen_random_uuid(), 'GEA', 'Omni',
        'GEA Omni Compressor Panel',
        'GEA Grasso / GEA Omni control panel for screw compressors. Modbus TCP or BACnet/IP. Supports NH3 and CO2 cascade systems.',
        'compressor', '["NH3", "R-717", "CO2"]'::jsonb, 'modbus_tcp', 502, 1,
        '{
          "discharge_pressure":  {"register": 1000, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "psi", "description": "HP discharge pressure"},
          "suction_pressure":    {"register": 1002, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "psi", "description": "LP suction pressure"},
          "discharge_temp":      {"register": 1004, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "°F", "description": "Discharge gas temp"},
          "suction_temp":        {"register": 1006, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "°F", "description": "Suction gas temp"},
          "oil_temp":            {"register": 1008, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "°F", "description": "Oil sump temperature"},
          "bearing_temp":        {"register": 1010, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "°F", "description": "Drive-end bearing temp"},
          "amp_draw":            {"register": 1012, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "A", "description": "Motor current"},
          "kw":                  {"register": 1014, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "kW", "description": "Electrical power"},
          "vibration":           {"register": 1016, "type": "holding", "data_type": "float32", "scale": 1.0, "offset": 0, "unit": "in/s", "description": "Vibration"},
          "slide_valve_pct":     {"register": 1018, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "%", "description": "Capacity slide valve"},
          "rpm":                 {"register": 1019, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "RPM", "description": "Motor speed"},
          "running":             {"register": 1020, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "bool", "description": "Running status"}
        }'::jsonb,
        true, true
    ),
    (
        gen_random_uuid(), 'Bitzer', 'BEST',
        'Bitzer BEST Controller',
        'Bitzer Electronic Screw-compressor Tool. Modbus TCP for OS series screw compressors. Common in R-404A and CO2 applications.',
        'compressor', '["R-404A", "R-448A", "CO2", "R-407C"]'::jsonb, 'modbus_tcp', 502, 1,
        '{
          "discharge_pressure":  {"register": 200, "type": "holding", "data_type": "float32", "scale": 0.01, "offset": 0, "unit": "psi", "description": "HP pressure"},
          "suction_pressure":    {"register": 202, "type": "holding", "data_type": "float32", "scale": 0.01, "offset": 0, "unit": "psi", "description": "LP pressure"},
          "discharge_temp":      {"register": 204, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Discharge temp"},
          "suction_temp":        {"register": 206, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Suction temp"},
          "oil_temp":            {"register": 208, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "°F", "description": "Oil temp"},
          "amp_draw":            {"register": 210, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "A", "description": "Current draw"},
          "kw":                  {"register": 212, "type": "holding", "data_type": "float32", "scale": 0.1, "offset": 0, "unit": "kW", "description": "Power"},
          "slide_valve_pct":     {"register": 214, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "%", "description": "Capacity"},
          "rpm":                 {"register": 215, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "RPM", "description": "Speed"},
          "running":             {"register": 216, "type": "holding", "data_type": "uint16", "scale": 1, "offset": 0, "unit": "bool", "description": "Status"}
        }'::jsonb,
        true, true
    );
    """)


def downgrade() -> None:
    op.drop_table("agent_devices")
    op.drop_table("device_profiles")
