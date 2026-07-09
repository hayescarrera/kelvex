"""
Authorization enforcement tests — permission matrix + per-facility access.

The PERMISSIONS matrix in app/models/user.py is the contract; these tests
pin the two enforcement layers added in the 2026-07 audit:
  1. require_permission on control/tunnel/agent/billing mutations
  2. UserFacilityAccess grants for roles without global access
"""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import TestSessionLocal
from app.core.security import get_password_hash, create_access_token
from app.models.user import User, UserFacilityAccess
from app.models.facility import Facility


async def _make_user(org_id, role: str, email: str) -> User:
    async with TestSessionLocal() as db:
        u = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=get_password_hash("TestPass123!"),
            full_name=f"{role} user",
            org_id=org_id,
            role=role,
            is_active=True,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id), "org": str(user.org_id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestPermissionEnforcement:
    async def test_viewer_cannot_control_compressor(
        self, client: AsyncClient, user: User, facility: Facility
    ):
        viewer = await _make_user(user.org_id, "viewer", "viewer@coldgrid.io")
        # Grant facility access so the 403 (permission) layer is what fires,
        # not the 404 (facility grant) layer.
        async with TestSessionLocal() as db:
            db.add(UserFacilityAccess(user_id=viewer.id, facility_id=facility.id))
            await db.commit()
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/control/compressor",
            headers=_headers(viewer),
            json={"compressor_id": str(uuid.uuid4()), "action": "stop"},
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_trigger_defrost(
        self, client: AsyncClient, user: User, facility: Facility
    ):
        viewer = await _make_user(user.org_id, "viewer", "viewer2@coldgrid.io")
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/control/defrost",
            headers=_headers(viewer),
            json={"compressor_id": str(uuid.uuid4()), "action": "trigger"},
        )
        assert resp.status_code == 403

    async def test_finance_cannot_register_agent(
        self, client: AsyncClient, user: User, facility: Facility
    ):
        finance = await _make_user(user.org_id, "finance", "finance@coldgrid.io")
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/agents",
            headers=_headers(finance),
            json={"name": "Rogue Agent", "hardware_type": "raspberry_pi_4"},
        )
        assert resp.status_code == 403

    async def test_operator_can_start_stop_but_not_setpoint(
        self, client: AsyncClient, user: User, facility: Facility
    ):
        operator = await _make_user(user.org_id, "operator", "operator@coldgrid.io")
        async with TestSessionLocal() as db:
            db.add(UserFacilityAccess(user_id=operator.id, facility_id=facility.id))
            await db.commit()

        # setpoint write → 403 (operators lack control:setpoint)
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/control/compressor",
            headers=_headers(operator),
            json={"compressor_id": str(uuid.uuid4()), "action": "set_capacity", "percent": 50},
        )
        assert resp.status_code == 403

        # stop → allowed past the permission gate (404/409 later is fine:
        # the compressor/agent don't exist, but authorization passed)
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/control/compressor",
            headers=_headers(operator),
            json={"compressor_id": str(uuid.uuid4()), "action": "stop"},
        )
        assert resp.status_code in (404, 409)


@pytest.mark.asyncio
class TestFacilityAccessGrants:
    async def test_ungrantee_technician_gets_404(
        self, client: AsyncClient, user: User, facility: Facility
    ):
        tech = await _make_user(user.org_id, "technician", "tech@coldgrid.io")
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/alerts",
            headers=_headers(tech),
        )
        assert resp.status_code == 404

    async def test_granted_technician_gets_200(
        self, client: AsyncClient, user: User, facility: Facility
    ):
        tech = await _make_user(user.org_id, "technician", "tech2@coldgrid.io")
        async with TestSessionLocal() as db:
            db.add(UserFacilityAccess(user_id=tech.id, facility_id=facility.id))
            await db.commit()
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/alerts",
            headers=_headers(tech),
        )
        assert resp.status_code == 200

    async def test_owner_needs_no_grant(
        self, client: AsyncClient, auth_headers: dict, facility: Facility
    ):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/alerts",
            headers=auth_headers,
        )
        assert resp.status_code == 200
