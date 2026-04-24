"""Add zones, alerts, controls, automation, edge agents

Revision ID: 002
Revises: 001
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Edge Agents ──────────────────────────────────
    op.create_table(
        "edge_agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("agent_key", sa.String(64), unique=True, nullable=False),
        sa.Column("version", sa.String(20)),
        sa.Column("hardware_type", sa.String(50)),
        sa.Column("hostname", sa.String(255)),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("mac_address", sa.String(17)),
        sa.Column("connection_state", sa.String(20), server_default="disconnected"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True)),
        sa.Column("last_telemetry_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_interval_sec", sa.Integer, server_default="30"),
        sa.Column("protocols_config", JSONB, server_default="{}"),
        sa.Column("capabilities", JSONB, server_default="{}"),
        sa.Column("discovered_devices", JSONB, server_default="{}"),
        sa.Column("cpu_percent", sa.Float),
        sa.Column("memory_percent", sa.Float),
        sa.Column("disk_percent", sa.Float),
        sa.Column("uptime_seconds", sa.Integer),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("config_version", sa.Integer, server_default="1"),
        sa.Column("pending_commands", sa.Integer, server_default="0"),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_config_push", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_edge_agents_facility", "edge_agents", ["facility_id"])

    # ── Agent Logs ───────────────────────────────────
    op.create_table(
        "agent_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("edge_agents.id"), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("context", JSONB, server_default="{}"),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_agent_logs_agent_time", "agent_logs", ["agent_id", "logged_at"])

    # ── Zones ────────────────────────────────────────
    op.create_table(
        "zones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("zone_type", sa.String(50), nullable=False),
        sa.Column("area_sqft", sa.Integer),
        sa.Column("position_x", sa.Float),
        sa.Column("position_y", sa.Float),
        sa.Column("width", sa.Float),
        sa.Column("height", sa.Float),
        sa.Column("temp_setpoint", sa.Float),
        sa.Column("temp_unit", sa.String(5), server_default="F"),
        sa.Column("temp_tolerance", sa.Float, server_default="2.0"),
        sa.Column("temp_alarm_high", sa.Float),
        sa.Column("temp_alarm_low", sa.Float),
        sa.Column("humidity_setpoint", sa.Float),
        sa.Column("humidity_alarm_high", sa.Float),
        sa.Column("current_temp", sa.Float),
        sa.Column("current_humidity", sa.Float),
        sa.Column("door_open", sa.Boolean, server_default="false"),
        sa.Column("state", sa.String(20), server_default="normal"),
        sa.Column("last_reading_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_zones_facility", "zones", ["facility_id"])

    # ── Zone ↔ Equipment assignment ──────────────────
    op.create_table(
        "zone_equipment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("zone_id", UUID(as_uuid=True), sa.ForeignKey("zones.id"), nullable=False),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("role", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_zone_equip_zone", "zone_equipment", ["zone_id"])
    op.create_index("idx_zone_equip_equip", "zone_equipment", ["equipment_id"])

    # ── Alerts ───────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("zone_id", UUID(as_uuid=True), sa.ForeignKey("zones.id")),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id")),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("edge_agents.id")),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("alert_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text),
        sa.Column("state", sa.String(20), server_default="active"),
        sa.Column("acknowledged_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("resolution_note", sa.Text),
        sa.Column("trigger_value", sa.Float),
        sa.Column("threshold_value", sa.Float),
        sa.Column("context", JSONB, server_default="{}"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_alerts_facility_state", "alerts", ["facility_id", "state"])
    op.create_index("idx_alerts_severity", "alerts", ["severity", "triggered_at"])

    # ── Events (audit log) ───────────────────────────
    op.create_table(
        "events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("zone_id", UUID(as_uuid=True), sa.ForeignKey("zones.id")),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("alert_id", UUID(as_uuid=True), sa.ForeignKey("alerts.id")),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("data", JSONB, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_events_facility_time", "events", ["facility_id", "occurred_at"])
    op.create_index("idx_events_type", "events", ["event_type"])

    # ── Control Sequences ────────────────────────────
    op.create_table(
        "control_sequences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("sequence_type", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("priority", sa.Integer, server_default="50"),
        sa.Column("steps", JSONB, nullable=False, server_default="[]"),
        sa.Column("conditions", JSONB, server_default="{}"),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_result", sa.String(20)),
        sa.Column("run_count", sa.Integer, server_default="0"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_control_seq_facility", "control_sequences", ["facility_id"])

    # ── Schedules ────────────────────────────────────
    op.create_table(
        "schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("control_sequence_id", UUID(as_uuid=True), sa.ForeignKey("control_sequences.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("schedule_type", sa.String(20), nullable=False),
        sa.Column("cron_expression", sa.String(100)),
        sa.Column("days_of_week", JSONB),
        sa.Column("start_time", sa.Time),
        sa.Column("end_time", sa.Time),
        sa.Column("timezone", sa.String(50), server_default="America/Chicago"),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── Automation Rules ─────────────────────────────
    op.create_table(
        "automation_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("trigger_conditions", JSONB, nullable=False),
        sa.Column("actions", JSONB, nullable=False),
        sa.Column("cooldown_minutes", sa.Integer, server_default="30"),
        sa.Column("max_executions_per_day", sa.Integer, server_default="10"),
        sa.Column("execution_count_today", sa.Integer, server_default="0"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_automation_rules_facility", "automation_rules", ["facility_id"])

    # ── Command Queue ────────────────────────────────
    op.create_table(
        "command_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("edge_agents.id"), nullable=False),
        sa.Column("command_type", sa.String(50), nullable=False),
        sa.Column("target_equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id")),
        sa.Column("target_zone_id", UUID(as_uuid=True), sa.ForeignKey("zones.id")),
        sa.Column("parameters", JSONB, nullable=False, server_default="{}"),
        sa.Column("state", sa.String(20), server_default="pending"),
        sa.Column("priority", sa.Integer, server_default="50"),
        sa.Column("issued_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("result", JSONB),
        sa.Column("error_message", sa.Text),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_cmd_queue_agent_state", "command_queue", ["agent_id", "state"])
    op.create_index("idx_cmd_queue_facility", "command_queue", ["facility_id"])


def downgrade() -> None:
    op.drop_table("command_queue")
    op.drop_table("automation_rules")
    op.drop_table("schedules")
    op.drop_table("control_sequences")
    op.drop_table("events")
    op.drop_table("alerts")
    op.drop_table("zone_equipment")
    op.drop_table("zones")
    op.drop_table("agent_logs")
    op.drop_table("edge_agents")
