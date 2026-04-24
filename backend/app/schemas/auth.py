from pydantic import BaseModel, EmailStr, field_validator
from uuid import UUID
from datetime import datetime


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    org_name: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name cannot be empty")
        return v.strip()

    @field_validator("org_name")
    @classmethod
    def org_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Organization name cannot be empty")
        return v.strip()


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class UserUpdate(BaseModel):
    full_name: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    role: str
    org_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Member Management ──────────────────────────────

VALID_ROLES = {"owner", "admin", "plant_manager", "technician", "operator", "viewer"}


class FacilityAccessResponse(BaseModel):
    facility_id: UUID
    facility_name: str | None = None


class OrgMemberResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    facility_access: list[FacilityAccessResponse] = []

    model_config = {"from_attributes": True}

    @classmethod
    def from_user(cls, user, facility_names: dict | None = None) -> "OrgMemberResponse":
        fac_access = []
        if hasattr(user, "facility_access") and user.facility_access:
            for ufa in user.facility_access:
                name = None
                if facility_names:
                    name = facility_names.get(str(ufa.facility_id))
                fac_access.append(FacilityAccessResponse(
                    facility_id=ufa.facility_id,
                    facility_name=name,
                ))
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            facility_access=fac_access,
        )


class OrgMemberListResponse(BaseModel):
    members: list[OrgMemberResponse]
    total: int


class InviteMemberRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "operator"
    password: str
    facility_ids: list[UUID] = []

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")
        return v


class UpdateMemberRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    full_name: str | None = None
    facility_ids: list[UUID] | None = None

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ROLES:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")
        return v
