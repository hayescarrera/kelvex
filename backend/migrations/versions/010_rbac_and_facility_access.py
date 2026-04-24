"""Add role-based access control and facility-level permissions.

Replaces the binary is_admin flag with a proper role enum:
  owner         – Full access, all facilities (org creator)
  admin         – Full access, all facilities
  plant_manager – Manage automation, view energy/costs, control compressors
  technician    – Control compressors, adjust setpoints, run sequences
  operator      – View dashboards, trigger basic controls (defrost, start/stop)
  viewer        – Read-only access

Adds user_facility_access join table so non-admin roles can be scoped
to specific facilities.  Owner and Admin roles automatically see all
facilities (enforced in application code, not in this table).

Revision ID: 010
Revises: 009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

ROLES = ("owner", "admin", "plant_manager", "technician", "operator", "viewer")


def upgrade() -> None:
    # 1. Create the role enum type
    role_enum = sa.Enum(*ROLES, name="user_role")
    role_enum.create(op.get_bind(), checkfirst=True)

    # 2. Add role column (nullable initially so we can backfill)
    op.add_column(
        "users",
        sa.Column("role", sa.Enum(*ROLES, name="user_role"), nullable=True),
    )

    # 3. Backfill: is_admin=true → 'owner', is_admin=false → 'operator'
    #    (First user who registered is typically the owner; existing admins
    #     get owner, everyone else gets operator as a safe default.)
    op.execute("UPDATE users SET role = 'owner' WHERE is_admin = true")
    op.execute("UPDATE users SET role = 'operator' WHERE is_admin = false OR is_admin IS NULL")

    # 4. Make role NOT NULL now that all rows have a value
    op.alter_column("users", "role", nullable=False)

    # 5. Create user_facility_access join table
    op.create_table(
        "user_facility_access",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", UUID(as_uuid=True), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "facility_id", name="uq_user_facility"),
    )
    op.create_index("ix_ufa_user", "user_facility_access", ["user_id"])
    op.create_index("ix_ufa_facility", "user_facility_access", ["facility_id"])


def downgrade() -> None:
    op.drop_index("ix_ufa_facility", table_name="user_facility_access")
    op.drop_index("ix_ufa_user", table_name="user_facility_access")
    op.drop_table("user_facility_access")
    op.drop_column("users", "role")
    sa.Enum(*ROLES, name="user_role").drop(op.get_bind(), checkfirst=True)
