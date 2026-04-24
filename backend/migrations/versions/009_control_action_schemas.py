"""Add control_schemas to device profiles for parameterized operator actions.

Instead of simple boolean capabilities (can_set_capacity: true/false),
this gives each device profile a rich schema describing every control
action with its full parameter set.  The frontend reads this schema
and dynamically renders the correct input controls — sliders, number
fields, select dropdowns, toggles — with proper labels, units, ranges,
step sizes, and defaults.

This is what makes ColdGrid feel like Foreman: when a tech hits "Defrost"
they get method, duration, terminate temp, fan delay, drip time — all
specific to the controller model installed on the compressor.

Revision ID: 009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
import json

revision = "009"
down_revision = "008"


# ── Schema definitions per manufacturer ──────────────────

FRICK_SCHEMAS = {
    "capacity": {
        "label": "Capacity Control",
        "icon": "sliders",
        "description": "Adjust compressor slide valve position",
        "params": {
            "value": {
                "type": "slider",
                "label": "Slide Valve Position",
                "unit": "%",
                "min": 25,
                "max": 100,
                "step": 5,
                "default": 75,
                "register": "capacity_setpoint",
            },
            "ramp_rate": {
                "type": "number",
                "label": "Ramp Rate",
                "unit": "%/min",
                "min": 1,
                "max": 25,
                "step": 1,
                "default": 10,
                "description": "How fast to move the slide valve",
            },
        },
    },
    "suction_setpoint": {
        "label": "Suction Pressure",
        "icon": "gauge",
        "description": "Adjust suction pressure setpoint",
        "params": {
            "value": {
                "type": "slider",
                "label": "Suction Pressure",
                "unit": "PSI",
                "min": 10,
                "max": 55,
                "step": 0.5,
                "default": 28,
                "register": "suction_setpoint_psi",
            },
        },
    },
    "start_stop": {
        "label": "Start / Stop",
        "icon": "power",
        "description": "Start or stop the compressor",
        "params": {
            "action": {
                "type": "select",
                "label": "Command",
                "options": [
                    {"value": "start", "label": "Start Compressor"},
                    {"value": "stop", "label": "Stop Compressor"},
                ],
                "default": "start",
                "register": "start_stop",
            },
            "confirm": {
                "type": "toggle",
                "label": "Confirm this action",
                "default": False,
                "required": True,
                "description": "Toggle to confirm start/stop command",
            },
        },
    },
    "defrost": {
        "label": "Defrost Cycle",
        "icon": "snowflake",
        "description": "Initiate or configure evaporator defrost",
        "params": {
            "method": {
                "type": "select",
                "label": "Defrost Method",
                "options": [
                    {"value": "hot_gas", "label": "Hot Gas"},
                    {"value": "electric", "label": "Electric"},
                    {"value": "air", "label": "Air / Off-Cycle"},
                ],
                "default": "hot_gas",
            },
            "duration_min": {
                "type": "number",
                "label": "Duration",
                "unit": "min",
                "min": 5,
                "max": 90,
                "step": 5,
                "default": 30,
            },
            "terminate_temp_f": {
                "type": "number",
                "label": "Terminate Temperature",
                "unit": "°F",
                "min": 32,
                "max": 65,
                "step": 1,
                "default": 45,
                "description": "End defrost when coil reaches this temp",
            },
            "drip_time_min": {
                "type": "number",
                "label": "Drip Time",
                "unit": "min",
                "min": 0,
                "max": 15,
                "step": 1,
                "default": 5,
                "description": "Drain time after defrost ends",
            },
            "fan_delay_min": {
                "type": "number",
                "label": "Fan Restart Delay",
                "unit": "min",
                "min": 0,
                "max": 15,
                "step": 1,
                "default": 3,
                "description": "Wait before restarting evap fans",
            },
        },
    },
    "demand_response": {
        "label": "Demand Response",
        "icon": "zap",
        "description": "Shed compressor load during peak demand periods",
        "scope": "facility",
        "params": {
            "mode": {
                "type": "select",
                "label": "DR Mode",
                "options": [
                    {"value": "shed", "label": "Load Shed — reduce capacity"},
                    {"value": "precool", "label": "Pre-Cool — build thermal mass first"},
                    {"value": "coast", "label": "Coast — stop compressors, ride thermal mass"},
                ],
                "default": "shed",
            },
            "target_kw_reduction": {
                "type": "number",
                "label": "Target kW Reduction",
                "unit": "kW",
                "min": 10,
                "max": 2000,
                "step": 10,
                "default": 100,
                "description": "How much load to shed",
            },
            "duration_min": {
                "type": "number",
                "label": "Duration",
                "unit": "min",
                "min": 15,
                "max": 480,
                "step": 15,
                "default": 120,
            },
            "min_capacity_pct": {
                "type": "slider",
                "label": "Minimum Capacity Floor",
                "unit": "%",
                "min": 0,
                "max": 75,
                "step": 5,
                "default": 25,
                "description": "Never reduce compressors below this",
            },
            "precool_delta_f": {
                "type": "number",
                "label": "Pre-Cool Delta",
                "unit": "°F",
                "min": -15,
                "max": 0,
                "step": 1,
                "default": -5,
                "description": "How far below setpoint to pre-cool zones",
                "visible_when": {"mode": "precool"},
            },
            "precool_duration_min": {
                "type": "number",
                "label": "Pre-Cool Duration",
                "unit": "min",
                "min": 15,
                "max": 180,
                "step": 15,
                "default": 60,
                "description": "How long to pre-cool before shedding",
                "visible_when": {"mode": "precool"},
            },
            "max_coast_min": {
                "type": "number",
                "label": "Max Coast Time",
                "unit": "min",
                "min": 15,
                "max": 240,
                "step": 15,
                "default": 60,
                "description": "Maximum time compressors stay off",
                "visible_when": {"mode": "coast"},
            },
            "temp_ceiling_f": {
                "type": "number",
                "label": "Temperature Ceiling",
                "unit": "°F",
                "min": -20,
                "max": 50,
                "step": 1,
                "default": 5,
                "description": "Restart compressors if any zone exceeds this",
                "visible_when": {"mode": "coast"},
            },
        },
    },
}

VILTER_SCHEMAS = {
    "capacity": {
        "label": "Capacity Control",
        "icon": "sliders",
        "description": "Adjust compressor capacity via unloader",
        "params": {
            "value": {
                "type": "slider",
                "label": "Capacity Setpoint",
                "unit": "%",
                "min": 25,
                "max": 100,
                "step": 5,
                "default": 75,
                "register": "capacity_setpoint",
            },
            "ramp_rate": {
                "type": "number",
                "label": "Ramp Rate",
                "unit": "%/min",
                "min": 1,
                "max": 20,
                "step": 1,
                "default": 8,
            },
        },
    },
    "suction_setpoint": {
        "label": "Suction Pressure",
        "icon": "gauge",
        "description": "Adjust suction pressure setpoint",
        "params": {
            "value": {
                "type": "slider",
                "label": "Suction Pressure",
                "unit": "PSI",
                "min": 10,
                "max": 55,
                "step": 0.5,
                "default": 28,
                "register": "suction_setpoint_psi",
            },
        },
    },
    "defrost": {
        "label": "Defrost Cycle",
        "icon": "snowflake",
        "description": "Initiate evaporator defrost",
        "params": {
            "method": {
                "type": "select",
                "label": "Defrost Method",
                "options": [
                    {"value": "hot_gas", "label": "Hot Gas"},
                    {"value": "electric", "label": "Electric"},
                ],
                "default": "hot_gas",
            },
            "duration_min": {
                "type": "number",
                "label": "Duration",
                "unit": "min",
                "min": 5,
                "max": 60,
                "step": 5,
                "default": 25,
            },
            "terminate_temp_f": {
                "type": "number",
                "label": "Terminate Temp",
                "unit": "°F",
                "min": 32,
                "max": 60,
                "step": 1,
                "default": 42,
            },
            "fan_delay_min": {
                "type": "number",
                "label": "Fan Restart Delay",
                "unit": "min",
                "min": 0,
                "max": 10,
                "step": 1,
                "default": 2,
            },
        },
    },
    "demand_response": FRICK_SCHEMAS["demand_response"],
}

GEA_SCHEMAS = {
    "capacity": {
        "label": "Capacity Control",
        "icon": "sliders",
        "description": "Adjust compressor capacity",
        "params": {
            "value": {
                "type": "slider",
                "label": "Capacity Setpoint",
                "unit": "%",
                "min": 25,
                "max": 100,
                "step": 5,
                "default": 75,
                "register": "capacity_setpoint",
            },
            "ramp_rate": {
                "type": "number",
                "label": "Ramp Rate",
                "unit": "%/min",
                "min": 1,
                "max": 20,
                "step": 1,
                "default": 10,
            },
        },
    },
    "start_stop": {
        "label": "Start / Stop",
        "icon": "power",
        "description": "Start or stop the compressor",
        "params": {
            "action": {
                "type": "select",
                "label": "Command",
                "options": [
                    {"value": "start", "label": "Start"},
                    {"value": "stop", "label": "Stop"},
                ],
                "default": "start",
                "register": "start_stop",
            },
            "confirm": {
                "type": "toggle",
                "label": "Confirm this action",
                "default": False,
                "required": True,
            },
        },
    },
    "defrost": {
        "label": "Defrost Cycle",
        "icon": "snowflake",
        "description": "Initiate defrost cycle",
        "params": {
            "method": {
                "type": "select",
                "label": "Defrost Method",
                "options": [
                    {"value": "hot_gas", "label": "Hot Gas"},
                    {"value": "electric", "label": "Electric"},
                    {"value": "air", "label": "Air"},
                ],
                "default": "hot_gas",
            },
            "duration_min": {
                "type": "number",
                "label": "Duration",
                "unit": "min",
                "min": 5,
                "max": 60,
                "step": 5,
                "default": 30,
            },
            "terminate_temp_f": {
                "type": "number",
                "label": "Terminate Temp",
                "unit": "°F",
                "min": 32,
                "max": 60,
                "step": 1,
                "default": 45,
            },
        },
    },
    "demand_response": FRICK_SCHEMAS["demand_response"],
}


def upgrade():
    # Add control_schemas column
    op.add_column(
        "device_profiles",
        sa.Column("control_schemas", JSONB, nullable=True),
    )

    # Seed schemas for existing profiles
    from sqlalchemy.orm import Session
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute(
        sa.text("UPDATE device_profiles SET control_schemas = :cs WHERE manufacturer = 'Frick' AND model = 'Quantum HD'"),
        {"cs": json.dumps(FRICK_SCHEMAS)},
    )
    session.execute(
        sa.text("UPDATE device_profiles SET control_schemas = :cs WHERE manufacturer = 'Vilter' AND model = 'VSM/VSSG'"),
        {"cs": json.dumps(VILTER_SCHEMAS)},
    )
    session.execute(
        sa.text("UPDATE device_profiles SET control_schemas = :cs WHERE manufacturer = 'GEA' AND model = 'Omni'"),
        {"cs": json.dumps(GEA_SCHEMAS)},
    )

    session.commit()


def downgrade():
    op.drop_column("device_profiles", "control_schemas")
