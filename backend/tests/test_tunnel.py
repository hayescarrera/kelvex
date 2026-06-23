"""
Tunnel sessions endpoint tests.
"""
import uuid
import pytest
from httpx import AsyncClient

from app.models.facility import Facility
from app.models.user import User


class TestTunnelSessionsList:
    async def test_list_empty(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get("/api/v1/tunnel/sessions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["sessions"] == []

    async def test_list_own_sessions_only(
        self, client: AsyncClient, auth_headers: dict,
        other_auth_headers: dict, facility: Facility,
    ):
        await client.post(
            "/api/v1/tunnel/sessions",
            headers=auth_headers,
            json={"facility_id": str(facility.id), "target_device": "Danfoss AK-SM"},
        )
        resp = await client.get("/api/v1/tunnel/sessions", headers=other_auth_headers)
        assert resp.json()["total"] == 0


class TestTunnelSessionStart:
    async def test_start_session(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            "/api/v1/tunnel/sessions",
            headers=auth_headers,
            json={"facility_id": str(facility.id), "target_device": "Copeland E3", "notes": "Checking suction pressure"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["facility_id"] == str(facility.id)
        assert data["target_device"] == "Copeland E3"
        assert data["notes"] == "Checking suction pressure"
        assert data["started_at"] is not None
        assert data["ended_at"] is None
        assert data["end_reason"] is None

    async def test_start_unknown_facility(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/tunnel/sessions",
            headers=auth_headers,
            json={"facility_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    async def test_start_unauthenticated(self, client: AsyncClient, facility: Facility):
        resp = await client.post(
            "/api/v1/tunnel/sessions",
            json={"facility_id": str(facility.id)},
        )
        assert resp.status_code == 401


class TestTunnelSessionEnd:
    async def test_end_session(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        create_resp = await client.post(
            "/api/v1/tunnel/sessions",
            headers=auth_headers,
            json={"facility_id": str(facility.id)},
        )
        session_id = create_resp.json()["id"]

        end_resp = await client.post(
            f"/api/v1/tunnel/sessions/{session_id}/end",
            headers=auth_headers,
            json={"end_reason": "user_close"},
        )
        assert end_resp.status_code == 200
        data = end_resp.json()
        assert data["ended_at"] is not None
        assert data["end_reason"] == "user_close"
        assert data["duration_seconds"] is not None
        assert data["duration_seconds"] >= 0

    async def test_end_already_ended(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        create_resp = await client.post(
            "/api/v1/tunnel/sessions",
            headers=auth_headers,
            json={"facility_id": str(facility.id)},
        )
        session_id = create_resp.json()["id"]

        await client.post(
            f"/api/v1/tunnel/sessions/{session_id}/end",
            headers=auth_headers,
            json={"end_reason": "user_close"},
        )
        resp2 = await client.post(
            f"/api/v1/tunnel/sessions/{session_id}/end",
            headers=auth_headers,
            json={"end_reason": "user_close"},
        )
        assert resp2.status_code == 409

    async def test_end_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            f"/api/v1/tunnel/sessions/{uuid.uuid4()}/end",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 404

    async def test_end_cross_org_blocked(
        self, client: AsyncClient, auth_headers: dict,
        other_auth_headers: dict, facility: Facility,
    ):
        create_resp = await client.post(
            "/api/v1/tunnel/sessions",
            headers=auth_headers,
            json={"facility_id": str(facility.id)},
        )
        session_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/tunnel/sessions/{session_id}/end",
            headers=other_auth_headers,
            json={},
        )
        assert resp.status_code == 404
