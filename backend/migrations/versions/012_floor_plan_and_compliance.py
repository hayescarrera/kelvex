"""Add floor_plan JSONB to facilities, create compliance/maintenance/escalation tables.

Revision ID: 012
Revises: 011
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Activity Logs (audit trail) — was missing from previous migrations
    op.create_table(
        "activity_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("resource_name", sa.String(255), nullable=True),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("changes", JSONB, nullable=True),
        sa.Column("metadata_extra", JSONB, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_activity_logs_org_created", "activity_logs", ["org_id", "created_at"])
    op.create_index("ix_activity_logs_resource", "activity_logs", ["resource_type", "resource_id"])
    op.create_index("ix_activity_logs_actor", "activity_logs", ["actor_id"])

    # Floor plan layout on facilities
    op.add_column("facilities", sa.Column("floor_plan", JSONB, nullable=True))

    # Critical Control Points (HACCP)
    op.create_table(
        "critical_control_points",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("zone_id", UUID(as_uuid=True), sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metric_name", sa.String(50), server_default="temperature"),
        sa.Column("temp_min", sa.Float, nullable=False),
        sa.Column("temp_max", sa.Float, nullable=False),
        sa.Column("temp_unit", sa.String(10), server_default="degF"),
        sa.Column("warning_offset", sa.Float, server_default="2.0"),
        sa.Column("check_interval_min", sa.Integer, server_default="15"),
        sa.Column("excursion_threshold_min", sa.Integer, server_default="30"),
        sa.Column("hazard_type", sa.String(100), nullable=True),
        sa.Column("corrective_action", sa.Text, nullable=True),
        sa.Column("verification_method", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ccp_facility", "critical_control_points", ["facility_id"])

    # Compliance Logs
    op.create_table(
        "compliance_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ccp_id", UUID(as_uuid=True), sa.ForeignKey("critical_control_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("temperature", sa.Float, nullable=False),
        sa.Column("temp_unit", sa.String(10), server_default="degF"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("limit_min", sa.Float, nullable=False),
        sa.Column("limit_max", sa.Float, nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source", sa.String(50), server_default="auto"),
    )
    op.create_index("ix_compliance_log_ccp_time", "compliance_logs", ["ccp_id", "checked_at"])
    op.create_index("ix_compliance_log_facility_time", "compliance_logs", ["facility_id", "checked_at"])

    # Temp Excursions
    op.create_table(
        "temp_excursions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ccp_id", UUID(as_uuid=True), sa.ForeignKey("critical_control_points.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("peak_temp", sa.Float, nullable=False),
        sa.Column("avg_temp", sa.Float, nullable=True),
        sa.Column("limit_breached", sa.String(10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer, nullable=True),
        sa.Column("state", sa.String(20), server_default="active"),
        sa.Column("corrective_action_taken", sa.Text, nullable=True),
        sa.Column("resolved_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_excursion_facility_time", "temp_excursions", ["facility_id", "started_at"])

    # Compliance Reports
    op.create_table(
        "compliance_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_checks", sa.Integer, server_default="0"),
        sa.Column("passed_checks", sa.Integer, server_default="0"),
        sa.Column("failed_checks", sa.Integer, server_default="0"),
        sa.Column("excursion_count", sa.Integer, server_default="0"),
        sa.Column("compliance_pct", sa.Float, server_default="100.0"),
        sa.Column("report_data", JSONB, nullable=False, server_default="{}"),
        sa.Column("generated_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("signed_off_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sign_off_notes", sa.Text, nullable=True),
        sa.Column("state", sa.String(20), server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Maintenance Tasks
    op.create_table(
        "maintenance_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(50), server_default="preventive"),
        sa.Column("priority", sa.String(20), server_default="medium"),
        sa.Column("equipment_id", UUID(as_uuid=True), sa.ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True),
        sa.Column("compressor_id", UUID(as_uuid=True), sa.ForeignKey("compressors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_recurring", sa.Boolean, server_default="false"),
        sa.Column("recurrence_days", sa.Integer, nullable=True),
        sa.Column("recurrence_hours", sa.Integer, nullable=True),
        sa.Column("state", sa.String(20), server_default="scheduled"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("completion_notes", sa.Text, nullable=True),
        sa.Column("parts_used", JSONB, nullable=True),
        sa.Column("labor_hours", sa.Float, nullable=True),
        sa.Column("checklist", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_maintenance_facility", "maintenance_tasks", ["facility_id"])

    # Escalation Policies
    op.create_table(
        "escalation_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("levels", JSONB, nullable=False, server_default="[]"),
        sa.Column("min_severity", sa.String(20), server_default="high"),
        sa.Column("facility_ids", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Escalation Events
    op.create_table(
        "escalation_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_id", UUID(as_uuid=True), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("policy_id", UUID(as_uuid=True), sa.ForeignKey("escalation_policies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("notified_targets", JSONB, server_default="[]"),
        sa.Column("escalated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_escalation_alert", "escalation_events", ["alert_id"])


def downgrade() -> None:
    op.drop_table("escalation_events")
    op.drop_table("escalation_policies")
    op.drop_table("maintenance_tasks")
    op.drop_table("compliance_reports")
    op.drop_table("temp_excursions")
    op.drop_table("compliance_logs")
    op.drop_table("critical_control_points")
    op.drop_column("facilities", "floor_plan")
    op.drop_index("ix_activity_logs_actor")
    op.drop_index("ix_activity_logs_resource")
    op.drop_index("ix_activity_logs_org_created")
    op.drop_table("activity_logs")
