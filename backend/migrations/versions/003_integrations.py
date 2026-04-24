"""Add integrations, credentials, and register maps

Revision ID: 003
Revises: 002
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Integration Credentials ─────────────────────────
    # Must be created before integrations (FK reference)
    op.create_table(
        "integration_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True),
                  sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("credentials_encrypted", JSONB, nullable=False),
        sa.Column("auth_type", sa.String(20), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_intcred_facility", "integration_credentials", ["facility_id"])
    op.create_index("ix_intcred_provider", "integration_credentials", ["provider"])

    # ── Integrations ────────────────────────────────────
    op.create_table(
        "integrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", UUID(as_uuid=True),
                  sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("integration_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("credential_id", UUID(as_uuid=True),
                  sa.ForeignKey("integration_credentials.id")),
        sa.Column("enabled", sa.Boolean, server_default=sa.text("true")),
        sa.Column("connection_state", sa.String(20),
                  server_default="disconnected"),
        sa.Column("last_poll_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("total_polls", sa.Integer, server_default="0"),
        sa.Column("total_errors", sa.Integer, server_default="0"),
        sa.Column("total_readings_ingested", sa.Integer, server_default="0"),
        sa.Column("device_map", JSONB, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_integration_facility", "integrations", ["facility_id"])
    op.create_index("ix_integration_provider", "integrations", ["provider"])
    op.create_index("ix_integration_enabled", "integrations", ["enabled"])
    op.create_index("ix_integration_state", "integrations", ["connection_state"])

    # ── Register Maps ───────────────────────────────────
    op.create_table(
        "register_maps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("protocol", sa.String(20), nullable=False),
        sa.Column("manufacturer", sa.String(100), nullable=False),
        sa.Column("model", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("version", sa.String(20), server_default="1.0"),
        sa.Column("registers", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_regmap_protocol", "register_maps", ["protocol"])
    op.create_index("ix_regmap_manufacturer", "register_maps", ["manufacturer"])


def downgrade() -> None:
    op.drop_table("integrations")
    op.drop_table("integration_credentials")
    op.drop_table("register_maps")
