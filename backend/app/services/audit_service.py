"""
Activity Audit Service — helper functions for recording audit trail entries.

Usage in endpoints:
    from app.services.audit_service import log_activity
    await log_activity(db, user=current_user, action="create", resource_type="facility",
                       resource_id=str(fac.id), resource_name=fac.name, facility_id=fac.id,
                       summary="Created facility 'Warehouse A'")

For automatic change tracking on updates:
    changes = diff_changes(old_data, new_data)
    await log_activity(db, ..., changes=changes)
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import ActivityLog

logger = logging.getLogger("coldgrid.audit")


async def log_activity(
    db: AsyncSession,
    *,
    user: Any = None,
    org_id: UUID | None = None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    resource_name: str | None = None,
    facility_id: UUID | None = None,
    summary: str | None = None,
    changes: dict | None = None,
    metadata_extra: dict | None = None,
    request: Request | None = None,
) -> ActivityLog:
    """Record an activity log entry."""
    # Resolve org_id from user if not provided
    if org_id is None and user is not None:
        org_id = user.org_id

    if org_id is None:
        logger.warning(f"Cannot log activity without org_id: {action} {resource_type}")
        return None

    # Extract request context
    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

    entry = ActivityLog(
        org_id=org_id,
        actor_id=user.id if user else None,
        actor_email=user.email if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        facility_id=facility_id,
        summary=summary,
        changes=changes,
        metadata_extra=metadata_extra,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.add(entry)
    # Don't commit — the caller's transaction will handle it
    logger.debug(f"Activity logged: {action} {resource_type} {resource_id} by {user.email if user else 'system'}")
    return entry


def diff_changes(old: dict, new: dict, exclude_keys: set | None = None) -> dict | None:
    """Compare two dicts and return a changes dict: {"field": {"old": x, "new": y}}.
    Returns None if no differences.
    """
    exclude = exclude_keys or {"updated_at", "created_at", "hashed_password"}
    changes = {}
    all_keys = set(old.keys()) | set(new.keys())

    for key in all_keys:
        if key in exclude:
            continue
        old_val = old.get(key)
        new_val = new.get(key)
        # Normalize UUIDs to strings for comparison
        if hasattr(old_val, 'hex'):
            old_val = str(old_val)
        if hasattr(new_val, 'hex'):
            new_val = str(new_val)
        if old_val != new_val:
            changes[key] = {"old": old_val, "new": new_val}

    return changes if changes else None
