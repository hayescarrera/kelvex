from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from slugify import slugify
import uuid
import logging

from app.core.database import get_db
from app.services.audit_service import log_activity
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    get_current_user,
    require_permission,
)
from app.models.user import (
    User, Organization, UserFacilityAccess,
    ROLE_OWNER, ROLE_ADMIN, GLOBAL_ACCESS_ROLES, ALL_ROLES,
    get_role_permissions,
)
from app.models.facility import Facility
from sqlalchemy import func
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    TokenRefresh,
    UserResponse,
    UserUpdate,
    OrgMemberResponse,
    OrgMemberListResponse,
    InviteMemberRequest,
    UpdateMemberRequest,
)
from jose import JWTError, jwt
from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


# ── Role hierarchy for permission checks ─────────
ROLE_RANK = {role: i for i, role in enumerate(ALL_ROLES)}


def _can_manage_role(actor_role: str, target_role: str) -> bool:
    """An actor can only assign/modify roles below their own rank."""
    return ROLE_RANK.get(actor_role, 99) < ROLE_RANK.get(target_role, 99)


# ── Public endpoints ─────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
    invite: str | None = Query(None, description="Invite token — required when REGISTRATION_OPEN=false"),
):
    """Register a new user and organization."""
    if not settings.REGISTRATION_OPEN:
        if not invite or invite != settings.INVITE_SECRET:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Registration is by invitation only. Contact ben@kelvex.io to request access.",
            )

    data.email = data.email.lower()
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    org_slug = slugify(data.org_name)
    result = await db.execute(select(Organization).where(Organization.slug == org_slug))
    if result.scalar_one_or_none():
        org_slug = f"{org_slug}-{str(uuid.uuid4())[:8]}"

    org = Organization(name=data.org_name, slug=org_slug)
    db.add(org)
    await db.flush()

    user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        org_id=org.id,
        is_admin=True,
        role=ROLE_OWNER,  # First user is always owner
    )
    db.add(user)
    await db.flush()

    access_token = create_access_token(data={"sub": str(user.id), "org": str(org.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id), "org": str(org.id)})

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate and return tokens."""
    data.email = data.email.lower()
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is inactive",
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "org": str(user.org_id)}
    )
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "org": str(user.org_id)}
    )

    await log_activity(db, user=user, action="login", resource_type="session",
                       resource_id=str(user.id), resource_name=user.email,
                       summary=f"User '{user.email}' logged in")

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    """Refresh an access token."""
    try:
        payload = jwt.decode(
            data.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        token_type = payload.get("type")
        if user_id is None or token_type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")

    token_org = payload.get("org")
    if token_org is None or str(user.org_id) != str(token_org):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = create_access_token(
        data={"sub": str(user.id), "org": str(user.org_id)}
    )
    new_refresh_token = create_refresh_token(
        data={"sub": str(user.id), "org": str(user.org_id)}
    )

    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


# ── Current user endpoints ────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return current_user


@router.get("/me/permissions")
async def get_my_permissions(current_user: User = Depends(get_current_user)):
    """Return the current user's role and all permissions."""
    return {
        "role": current_user.role,
        "permissions": get_role_permissions(current_user.role),
        "has_global_access": current_user.has_global_access,
    }


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile."""
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.flush()
    await db.refresh(current_user)
    return current_user


# ── Member Management ──────────────────────────────

async def _get_facility_name_map(db: AsyncSession, org_id) -> dict:
    """Build {str(facility_id): facility_name} for the org."""
    result = await db.execute(
        select(Facility.id, Facility.name).where(
            Facility.org_id == org_id,
            Facility.deleted_at == None,
        )
    )
    return {str(row[0]): row[1] for row in result.all()}


@router.get("/members", response_model=OrgMemberListResponse)
async def list_members(
    current_user: User = Depends(require_permission("users:view")),
    db: AsyncSession = Depends(get_db),
):
    """List all members in the current organization. Requires users:view permission."""
    total = (await db.execute(
        select(func.count(User.id)).where(User.org_id == current_user.org_id)
    )).scalar()

    result = await db.execute(
        select(User)
        .options(selectinload(User.facility_access))
        .where(User.org_id == current_user.org_id)
        .order_by(User.created_at)
    )
    users = result.scalars().all()

    fac_names = await _get_facility_name_map(db, current_user.org_id)

    return OrgMemberListResponse(
        members=[OrgMemberResponse.from_user(u, fac_names) for u in users],
        total=total or 0,
    )


@router.post("/invite", response_model=OrgMemberResponse, status_code=status.HTTP_201_CREATED)
async def invite_member(
    data: InviteMemberRequest,
    current_user: User = Depends(require_permission("users:invite")),
    db: AsyncSession = Depends(get_db),
):
    """Invite a new member to the organization. Requires users:invite permission."""
    # Can't assign a role equal to or higher than your own
    if not _can_manage_role(current_user.role, data.role):
        raise HTTPException(
            status_code=403,
            detail=f"Cannot assign role '{data.role}' — must be below your own role ({current_user.role})",
        )

    data.email = data.email.lower()
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate facility_ids belong to this org
    if data.facility_ids:
        fac_result = await db.execute(
            select(func.count(Facility.id)).where(
                Facility.id.in_(data.facility_ids),
                Facility.org_id == current_user.org_id,
                Facility.deleted_at == None,
            )
        )
        if fac_result.scalar() != len(data.facility_ids):
            raise HTTPException(status_code=400, detail="One or more facility IDs are invalid")

    new_user = User(
        email=data.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        org_id=current_user.org_id,
        role=data.role,
        is_admin=(data.role in {ROLE_OWNER, ROLE_ADMIN}),
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    # Add facility access for non-global roles
    if data.facility_ids and data.role not in GLOBAL_ACCESS_ROLES:
        for fid in data.facility_ids:
            db.add(UserFacilityAccess(user_id=new_user.id, facility_id=fid))
        await db.flush()

    # Reload with facility_access relationship
    result = await db.execute(
        select(User)
        .options(selectinload(User.facility_access))
        .where(User.id == new_user.id)
    )
    new_user = result.scalar_one()
    fac_names = await _get_facility_name_map(db, current_user.org_id)

    return OrgMemberResponse.from_user(new_user, fac_names)


@router.patch("/members/{user_id}", response_model=OrgMemberResponse)
async def update_member(
    user_id: uuid.UUID,
    data: UpdateMemberRequest,
    current_user: User = Depends(require_permission("users:edit_role")),
    db: AsyncSession = Depends(get_db),
):
    """Update a member's role, status, or facility access. Requires users:edit_role permission."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.facility_access))
        .where(User.id == user_id, User.org_id == current_user.org_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    # Can't edit someone with equal or higher rank
    if not _can_manage_role(current_user.role, target.role):
        raise HTTPException(
            status_code=403,
            detail="Cannot modify a user with equal or higher rank",
        )

    updates = data.model_dump(exclude_unset=True)

    if "role" in updates:
        new_role = updates["role"]
        if not _can_manage_role(current_user.role, new_role):
            raise HTTPException(
                status_code=403,
                detail=f"Cannot assign role '{new_role}'",
            )
        target.role = new_role
        target.is_admin = (new_role in {ROLE_OWNER, ROLE_ADMIN})

    if "is_active" in updates:
        target.is_active = updates["is_active"]

    if "full_name" in updates:
        target.full_name = updates["full_name"]

    # Update facility access
    if "facility_ids" in updates and updates["facility_ids"] is not None:
        effective_role = updates.get("role", target.role)
        if effective_role not in GLOBAL_ACCESS_ROLES:
            # Validate facility_ids
            fac_ids = updates["facility_ids"]
            if fac_ids:
                fac_result = await db.execute(
                    select(func.count(Facility.id)).where(
                        Facility.id.in_(fac_ids),
                        Facility.org_id == current_user.org_id,
                        Facility.deleted_at == None,
                    )
                )
                if fac_result.scalar() != len(fac_ids):
                    raise HTTPException(status_code=400, detail="One or more facility IDs are invalid")

            # Clear existing and re-add
            for ufa in list(target.facility_access):
                await db.delete(ufa)
            await db.flush()

            for fid in fac_ids:
                db.add(UserFacilityAccess(user_id=target.id, facility_id=fid))

    await db.flush()

    # Reload
    result = await db.execute(
        select(User)
        .options(selectinload(User.facility_access))
        .where(User.id == target.id)
    )
    target = result.scalar_one()
    fac_names = await _get_facility_name_map(db, current_user.org_id)

    return OrgMemberResponse.from_user(target, fac_names)


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    user_id: uuid.UUID,
    current_user: User = Depends(require_permission("users:remove")),
    db: AsyncSession = Depends(get_db),
):
    """Remove a member from the organization. Cannot remove self or higher-ranked users."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    result = await db.execute(
        select(User).where(User.id == user_id, User.org_id == current_user.org_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    if not _can_manage_role(current_user.role, target.role):
        raise HTTPException(status_code=403, detail="Cannot remove a user with equal or higher rank")

    await db.delete(target)
    await db.commit()


# ── Facility access management ────────────────────

@router.get("/members/{user_id}/facilities")
async def get_member_facilities(
    user_id: uuid.UUID,
    current_user: User = Depends(require_permission("users:view")),
    db: AsyncSession = Depends(get_db),
):
    """Get the facility access list for a specific member."""
    result = await db.execute(
        select(User)
        .options(selectinload(User.facility_access))
        .where(User.id == user_id, User.org_id == current_user.org_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Member not found")

    if target.has_global_access:
        return {"global_access": True, "facilities": []}

    fac_names = await _get_facility_name_map(db, current_user.org_id)
    return {
        "global_access": False,
        "facilities": [
            {"facility_id": str(ufa.facility_id), "facility_name": fac_names.get(str(ufa.facility_id))}
            for ufa in target.facility_access
        ],
    }


# ── Dashboard Preferences ────────────────────────

from app.models.audit_log import ActivityLog


@router.get("/me/dashboard")
async def get_dashboard_layout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's dashboard widget layout."""
    # Store in a lightweight JSON field — check if user has preferences
    result = await db.execute(
        select(ActivityLog.metadata_extra)
        .where(
            ActivityLog.org_id == current_user.org_id,
            ActivityLog.actor_id == current_user.id,
            ActivityLog.resource_type == "dashboard_layout",
            ActivityLog.action == "save",
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row and isinstance(row, dict):
        return row.get("layout", {"widgets": []})
    return {"widgets": _default_widgets()}


@router.put("/me/dashboard")
async def save_dashboard_layout(
    layout: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the current user's dashboard widget layout."""
    entry = ActivityLog(
        org_id=current_user.org_id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="save",
        resource_type="dashboard_layout",
        resource_id=str(current_user.id),
        summary="Updated dashboard layout",
        metadata_extra={"layout": layout},
    )
    db.add(entry)
    return layout


def _default_widgets() -> list[dict]:
    """Default dashboard widget configuration."""
    return [
        {"id": "alerts", "type": "alerts", "title": "Active Alerts", "size": "md"},
        {"id": "power", "type": "power", "title": "Power Demand", "size": "md"},
        {"id": "commands", "type": "commands", "title": "Recent Commands", "size": "sm"},
        {"id": "compressors", "type": "compressors", "title": "Compressor Health", "size": "md"},
        {"id": "zones", "type": "zones", "title": "Zone Temperatures", "size": "sm"},
        {"id": "savings", "type": "savings", "title": "Savings Potential", "size": "sm"},
    ]


# ── Email invite tokens ───────────────────────────────────────────────────

logger = logging.getLogger("kelvex.auth")

from pydantic import BaseModel as _BaseModel, EmailStr as _EmailStr, field_validator

class SendInviteRequest(_BaseModel):
    email: _EmailStr
    role: str = "operator"
    facility_ids: list[uuid.UUID] | None = None

class AcceptInviteRequest(_BaseModel):
    token: uuid.UUID
    full_name: str
    password: str


def _invite_to_dict(inv) -> dict:
    from app.models.invite_token import InviteToken
    return {
        "id": str(inv.id),
        "token": str(inv.token),
        "email": inv.email,
        "role": inv.role,
        "facility_ids": inv.facility_ids,
        "expires_at": inv.expires_at.isoformat(),
        "used_at": inv.used_at.isoformat() if inv.used_at else None,
        "created_at": inv.created_at.isoformat(),
        "is_valid": inv.is_valid,
    }


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def send_invite(
    data: SendInviteRequest,
    current_user: User = Depends(require_permission("users:invite")),
    db: AsyncSession = Depends(get_db),
):
    """Create a time-limited invite token and email it to the invitee."""
    from app.models.invite_token import InviteToken

    data.email = data.email.lower()

    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, detail="That email already has an account.")

    # Invalidate any existing unused invite for this email in this org
    old = await db.execute(
        select(InviteToken).where(
            InviteToken.org_id == current_user.org_id,
            InviteToken.email == data.email,
            InviteToken.used_at == None,
        )
    )
    for old_inv in old.scalars().all():
        old_inv.expires_at = datetime.now(timezone.utc)  # expire it immediately

    facility_ids_json = [str(f) for f in data.facility_ids] if data.facility_ids else None
    invite = InviteToken(
        org_id=current_user.org_id,
        invited_by=current_user.id,
        email=data.email,
        role=data.role,
        facility_ids=facility_ids_json,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    # Send invite email directly to the invitee
    invite_url = f"{settings.FRONTEND_URL}/accept-invite?token={invite.token}"
    try:
        from app.services.notification_service import send_transactional_email
        from app.models.user import Organization
        org_result = await db.execute(select(Organization).where(Organization.id == current_user.org_id))
        org = org_result.scalar_one_or_none()
        org_name = org.name if org else "your team"
        sender_name = current_user.full_name or current_user.email
        await send_transactional_email(
            to_email=data.email,
            subject=f"You've been invited to join {org_name} on Kelvex",
            html_body=(
                f"<p>Hi,</p>"
                f"<p>{sender_name} has invited you to join <strong>{org_name}</strong> on Kelvex as <strong>{data.role}</strong>.</p>"
                f"<p style='margin:24px 0'>"
                f"<a href='{invite_url}' style='background:#3BC9DB;color:#0E1116;padding:10px 24px;"
                f"border-radius:6px;text-decoration:none;font-weight:600'>Accept invitation</a></p>"
                f"<p style='color:#718096;font-size:13px'>This link expires in 7 days. If you didn't expect this invitation, you can ignore this email.</p>"
            ),
            text_body=f"You've been invited to join {org_name} on Kelvex.\n\nAccept your invitation: {invite_url}\n\nThis link expires in 7 days.",
        )
    except Exception as e:
        logger.warning("Could not send invite email to %s: %s", data.email, e)

    return _invite_to_dict(invite)


@router.get("/invites")
async def list_invites(
    current_user: User = Depends(require_permission("users:invite")),
    db: AsyncSession = Depends(get_db),
):
    """List pending (unused, unexpired) invites for this org."""
    from app.models.invite_token import InviteToken
    result = await db.execute(
        select(InviteToken).where(
            InviteToken.org_id == current_user.org_id,
        ).order_by(InviteToken.created_at.desc()).limit(100)
    )
    invites = result.scalars().all()
    return {"invites": [_invite_to_dict(i) for i in invites], "total": len(invites)}


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invite(
    invite_id: uuid.UUID,
    current_user: User = Depends(require_permission("users:invite")),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a pending invite."""
    from app.models.invite_token import InviteToken
    result = await db.execute(
        select(InviteToken).where(
            InviteToken.id == invite_id,
            InviteToken.org_id == current_user.org_id,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(404, detail="Invite not found")
    invite.expires_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/invites/verify")
async def verify_invite(
    token: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Public — validate an invite token. Returns email and org name for the accept-invite page."""
    from app.models.invite_token import InviteToken
    result = await db.execute(select(InviteToken).where(InviteToken.token == token))
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(404, detail="Invite not found or already used.")
    if invite.is_used:
        raise HTTPException(410, detail="This invite has already been used.")
    if invite.is_expired:
        raise HTTPException(410, detail="This invite has expired. Ask your admin to send a new one.")

    org_result = await db.execute(
        select(Organization).where(Organization.id == invite.org_id)
    )
    org = org_result.scalar_one_or_none()

    return {
        "email": invite.email,
        "role": invite.role,
        "org_name": org.name if org else "your organization",
        "expires_at": invite.expires_at.isoformat(),
    }


@router.post("/invites/accept", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def accept_invite(
    data: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Accept an invite: validate token, create user, return auth tokens."""
    from app.models.invite_token import InviteToken

    result = await db.execute(select(InviteToken).where(InviteToken.token == data.token))
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(404, detail="Invite not found.")
    if invite.is_used:
        raise HTTPException(410, detail="This invite has already been used.")
    if invite.is_expired:
        raise HTTPException(410, detail="This invite link has expired. Ask your admin to send a new one.")

    if len(data.password) < 8:
        raise HTTPException(422, detail="Password must be at least 8 characters.")

    existing = await db.execute(select(User).where(User.email == invite.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, detail="An account with this email already exists.")

    new_user = User(
        email=invite.email,
        hashed_password=get_password_hash(data.password),
        full_name=data.full_name,
        org_id=invite.org_id,
        role=invite.role,
        is_admin=(invite.role in {ROLE_OWNER, ROLE_ADMIN}),
        is_active=True,
    )
    db.add(new_user)
    await db.flush()

    if invite.facility_ids and invite.role not in GLOBAL_ACCESS_ROLES:
        for fid_str in invite.facility_ids:
            db.add(UserFacilityAccess(user_id=new_user.id, facility_id=uuid.UUID(fid_str)))
        await db.flush()

    invite.used_at = datetime.now(timezone.utc)
    invite.used_by = new_user.id

    await db.commit()

    access_token = create_access_token(data={"sub": str(new_user.id), "org": str(new_user.org_id)})
    refresh_token = create_refresh_token(data={"sub": str(new_user.id), "org": str(new_user.org_id)})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# ── Password Reset ────────────────────────────────

_RESET_TTL = 3600  # 1 hour


class PasswordResetRequestBody(_BaseModel):
    email: str


class PasswordResetConfirmBody(_BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


@router.post("/password-reset/request", status_code=200)
async def request_password_reset(
    body: PasswordResetRequestBody,
    db: AsyncSession = Depends(get_db),
):
    """Send a password reset link. Always returns 200 to prevent email enumeration."""
    from app.services.cache import get_redis
    from app.services.notification_service import send_notification, NotificationPayload

    email = body.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return {"message": "If that email exists you will receive a reset link."}

    reset_token = str(uuid.uuid4())
    redis = await get_redis()
    if redis:
        await redis.setex(f"pwreset:{reset_token}", _RESET_TTL, str(user.id))

    frontend_url = getattr(settings, "FRONTEND_URL", "https://app.kelvex.io")
    reset_link = f"{frontend_url}/reset-password?token={reset_token}"

    try:
        from app.services.notification_service import send_transactional_email
        await send_transactional_email(
            to_email=email,
            subject="Reset your Kelvex password",
            html_body=(
                f"<p>Hi {user.full_name},</p>"
                f"<p>Click the link below to reset your password. This link expires in 1 hour.</p>"
                f"<p style='margin:24px 0'>"
                f"<a href='{reset_link}' style='background:#3BC9DB;color:#0E1116;padding:10px 24px;"
                f"border-radius:6px;text-decoration:none;font-weight:600'>Reset password</a></p>"
                f"<p style='color:#718096;font-size:13px'>If you didn't request this, you can ignore this email.</p>"
            ),
            text_body=f"Reset your Kelvex password: {reset_link}\n\nThis link expires in 1 hour.",
        )
    except Exception as e:
        logger.warning("Could not send password reset email to %s: %s", email, e)

    return {"message": "If that email exists you will receive a reset link."}


@router.post("/password-reset/confirm", status_code=200)
async def confirm_password_reset(
    body: PasswordResetConfirmBody,
    db: AsyncSession = Depends(get_db),
):
    """Validate reset token and update password."""
    from app.services.cache import get_redis

    redis = await get_redis()
    if not redis:
        raise HTTPException(503, detail="Password reset service is temporarily unavailable.")

    user_id = await redis.get(f"pwreset:{body.token}")
    if not user_id:
        raise HTTPException(400, detail="This reset link is invalid or has expired.")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(400, detail="This reset link is invalid or has expired.")

    user.hashed_password = get_password_hash(body.password)
    await redis.delete(f"pwreset:{body.token}")
    await db.commit()

    return {"message": "Password updated. You can now sign in."}
