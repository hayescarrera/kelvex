"""Kelvex spec v1 — add missing tables and columns.

Adds: systems, documents, tunnel_sessions, maintenance_events, leak_rate_records.
Updates: equipment (system_id + refrigerant fields), activity_logs (hash chain),
         refrigerant_adds (epa cert), user_role enum (kelvex_admin, finance, ops_manager).

Revision ID: 015
Revises: 014
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── User role enum — add new roles ─────────────────────────────────────
    # Postgres enums only support ADD VALUE, not DROP VALUE, so we add safely.
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'kelvex_admin'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'finance'")
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'ops_manager'")

    # ── systems ────────────────────────────────────────────────────────────
    op.create_table(
        "systems",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("facility_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("system_type", sa.String(50), nullable=False, server_default="rack"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_systems_facility", "systems", ["facility_id"])
    op.create_index("ix_systems_org", "systems", ["org_id"])

    # ── equipment — add system_id and refrigerant fields ───────────────────
    op.add_column("equipment", sa.Column("system_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_equipment_system_id",
        "equipment", "systems",
        ["system_id"], ["id"],
        ondelete="SET NULL",
    )
    op.add_column("equipment", sa.Column("refrigerant_type", sa.String(50), nullable=True))
    op.add_column("equipment", sa.Column("gwp", sa.Float(), nullable=True))
    op.add_column("equipment", sa.Column("full_charge_lbs", sa.Float(), nullable=True))

    # ── documents ──────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("facility_id", sa.UUID(), nullable=True),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_org", "documents", ["org_id"])
    op.create_index("ix_documents_facility", "documents", ["facility_id"])
    op.create_index("ix_documents_equipment", "documents", ["equipment_id"])

    # ── tunnel_sessions ────────────────────────────────────────────────────
    op.create_table(
        "tunnel_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("facility_id", sa.UUID(), nullable=True),
        sa.Column("agent_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("target_device", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(50), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_id"], ["edge_agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tunnel_sessions_org_started", "tunnel_sessions", ["org_id", "started_at"])
    op.create_index("ix_tunnel_sessions_agent", "tunnel_sessions", ["agent_id"])
    op.create_index("ix_tunnel_sessions_user", "tunnel_sessions", ["user_id"])

    # ── maintenance_events ─────────────────────────────────────────────────
    op.create_table(
        "maintenance_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("facility_id", sa.UUID(), nullable=True),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("linked_alert_id", sa.UUID(), nullable=True),
        sa.Column("linked_refrigerant_event_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("technician_name", sa.String(255), nullable=True),
        sa.Column("technician_company", sa.String(255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_alert_id"], ["alerts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_refrigerant_event_id"], ["leak_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_events_org_occurred", "maintenance_events", ["org_id", "occurred_at"])
    op.create_index("ix_maintenance_events_equipment", "maintenance_events", ["equipment_id"])
    op.create_index("ix_maintenance_events_facility", "maintenance_events", ["facility_id"])

    # ── leak_rate_records ──────────────────────────────────────────────────
    op.create_table(
        "leak_rate_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("facility_id", sa.UUID(), nullable=False),
        sa.Column("circuit_id", sa.UUID(), nullable=True),
        sa.Column("refrigerant_add_id", sa.UUID(), nullable=True),
        sa.Column("lbs_added", sa.Float(), nullable=False),
        sa.Column("full_charge_lbs", sa.Float(), nullable=False),
        sa.Column("days_since_last_add", sa.Float(), nullable=True),
        sa.Column("refrigerant_type", sa.String(50), nullable=False),
        sa.Column("annualized_rate_pct", sa.Float(), nullable=False),
        sa.Column("triggered_repair_clock", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("compliance_status", sa.String(30), nullable=False, server_default="compliant"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["circuit_id"], ["refrigerant_circuits.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["refrigerant_add_id"], ["refrigerant_adds.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leak_rate_records_circuit_computed", "leak_rate_records", ["circuit_id", "computed_at"])
    op.create_index("ix_leak_rate_records_org", "leak_rate_records", ["org_id"])
    op.create_index("ix_leak_rate_records_facility", "leak_rate_records", ["facility_id"])

    # ── activity_logs — add hash-chain columns ─────────────────────────────
    op.add_column("activity_logs", sa.Column("prev_hash", sa.String(64), nullable=True))
    op.add_column("activity_logs", sa.Column("hash", sa.String(64), nullable=True))
    op.create_index("ix_activity_logs_hash", "activity_logs", ["hash"])

    # ── refrigerant_adds — add EPA cert column ─────────────────────────────
    op.add_column("refrigerant_adds", sa.Column("technician_epa_cert", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("refrigerant_adds", "technician_epa_cert")

    op.drop_index("ix_activity_logs_hash", table_name="activity_logs")
    op.drop_column("activity_logs", "hash")
    op.drop_column("activity_logs", "prev_hash")

    op.drop_index("ix_leak_rate_records_facility", table_name="leak_rate_records")
    op.drop_index("ix_leak_rate_records_org", table_name="leak_rate_records")
    op.drop_index("ix_leak_rate_records_circuit_computed", table_name="leak_rate_records")
    op.drop_table("leak_rate_records")

    op.drop_index("ix_maintenance_events_facility", table_name="maintenance_events")
    op.drop_index("ix_maintenance_events_equipment", table_name="maintenance_events")
    op.drop_index("ix_maintenance_events_org_occurred", table_name="maintenance_events")
    op.drop_table("maintenance_events")

    op.drop_index("ix_tunnel_sessions_user", table_name="tunnel_sessions")
    op.drop_index("ix_tunnel_sessions_agent", table_name="tunnel_sessions")
    op.drop_index("ix_tunnel_sessions_org_started", table_name="tunnel_sessions")
    op.drop_table("tunnel_sessions")

    op.drop_index("ix_documents_equipment", table_name="documents")
    op.drop_index("ix_documents_facility", table_name="documents")
    op.drop_index("ix_documents_org", table_name="documents")
    op.drop_table("documents")

    op.drop_constraint("fk_equipment_system_id", "equipment", type_="foreignkey")
    op.drop_column("equipment", "full_charge_lbs")
    op.drop_column("equipment", "gwp")
    op.drop_column("equipment", "refrigerant_type")
    op.drop_column("equipment", "system_id")

    op.drop_index("ix_systems_org", table_name="systems")
    op.drop_index("ix_systems_facility", table_name="systems")
    op.drop_table("systems")

    # Note: Postgres does not support removing enum values — new roles stay in the enum.
