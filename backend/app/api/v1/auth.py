from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from slugify import slugify
import uuid

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
