import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

# ── Role definitions ──────────────────────────────
# Keep in sync with migration 010 and frontend ROLES constant.
ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_PLANT_MANAGER = "plant_manager"
ROLE_TECHNICIAN = "technician"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"

ALL_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER, ROLE_TECHNICIAN, ROLE_OPERATOR, ROLE_VIEWER)

# Roles that automatically see ALL facilities in the org
GLOBAL_ACCESS_ROLES = {ROLE_OWNER, ROLE_ADMIN}

# ── Permission matrix ─────────────────────────────
# Each key is a permission; the value is the set of roles that have it.
PERMISSIONS = {
    # Organization management
    "org:manage":           {ROLE_OWNER},
    "org:billing":          {ROLE_OWNER, ROLE_ADMIN},

    # User management
    "users:invite":         {ROLE_OWNER, ROLE_ADMIN},
    "users:edit_role":      {ROLE_OWNER, ROLE_ADMIN},
    "users:remove":         {ROLE_OWNER, ROLE_ADMIN},
    "users:view":           {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER},

    # Facility management
    "facilities:create":    {ROLE_OWNER, ROLE_ADMIN},
    "facilities:edit":      {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER},
    "facilities:delete":    {ROLE_OWNER, ROLE_ADMIN},
    "facilities:view":      set(ALL_ROLES),

    # Compressor control
    "control:setpoint":     {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER, ROLE_TECHNICIAN},
    "control:start_stop":   {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER, ROLE_TECHNICIAN, ROLE_OPERATOR},
    "control:defrost":      {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER, ROLE_TECHNICIAN, ROLE_OPERATOR},
    "control:demand_response": {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER},

    # Automation
    "automation:create":    {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER},
    "automation:edit":      {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER},
    "automation:delete":    {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER},
    "automation:view":      {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER, ROLE_TECHNICIAN, ROLE_OPERATOR},

    # Agents
    "agents:manage":        {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER},
    "agents:view":          {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER, ROLE_TECHNICIAN},

    # Settings
    "settings:edit":        {ROLE_OWNER, ROLE_ADMIN},
    "settings:view":        set(ALL_ROLES),

    # Energy / billing data
    "energy:view":          {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER},
    "bills:manage":         {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER},
    "bills:view":           {ROLE_OWNER, ROLE_ADMIN, ROLE_PLANT_MANAGER, ROLE_TECHNICIAN},
}


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    return role in PERMISSIONS.get(permission, set())


def get_role_permissions(role: str) -> list[str]:
    """Return all permissions for a given role."""
    return [perm for perm, roles in PERMISSIONS.items() if role in roles]


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan_tier: Mapped[str] = mapped_column(String(50), default="free")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="organization")
    facilities: Mapped[list["Facility"]] = relationship(back_populates="organization")

    def __repr__(self):
        return f"<Organization {self.name}>"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # Legacy — use role instead
    role: Mapped[str] = mapped_column(
        Enum(*ALL_ROLES, name="user_role"),
        nullable=False,
        default=ROLE_OPERATOR,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="users")
    facility_access: Mapped[list["UserFacilityAccess"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def has_global_access(self) -> bool:
        """Owner and Admin roles see all facilities in the org."""
        return self.role in GLOBAL_ACCESS_ROLES

    def has_perm(self, permission: str) -> bool:
        """Check if this user has a specific permission."""
        return has_permission(self.role, permission)

    def __repr__(self):
        return f"<User {self.email} role={self.role}>"


class UserFacilityAccess(Base):
    """Join table: which facilities a user can access.
    Only used for non-global roles (plant_manager, technician, operator, viewer).
    Owner/Admin automatically see everything.
    """
    __tablename__ = "user_facility_access"
    __table_args__ = (
        UniqueConstraint("user_id", "facility_id", name="uq_user_facility"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="facility_access")
    facility: Mapped["Facility"] = relationship()

    def __repr__(self):
        return f"<UserFacilityAccess user={self.user_id} facility={self.facility_id}>"


# Forward reference for Facility relationship
from app.models.facility import Facility  # noqa: E402, F401
