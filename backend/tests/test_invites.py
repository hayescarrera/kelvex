"""
Invite token flow tests.
"""
import uuid
from unittest.mock import patch, AsyncMock

import pytest
from httpx import AsyncClient

from app.models.user import User, Organization


class TestSendInvite:
    async def test_send_invite_creates_token(self, client: AsyncClient, auth_headers: dict):
        with patch("app.services.notification_service.send_notification", new_callable=AsyncMock):
            resp = await client.post(
                "/api/v1/auth/invites",
                headers=auth_headers,
                json={"email": "newperson@example.com", "role": "operator"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newperson@example.com"
        assert data["role"] == "operator"
        assert "token" in data
        assert data["is_valid"] is True

    async def test_send_invite_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/invites",
            json={"email": "x@example.com", "role": "operator"},
        )
        assert resp.status_code == 401

    async def test_list_invites(self, client: AsyncClient, auth_headers: dict):
        with patch("app.services.notification_service.send_notification", new_callable=AsyncMock):
            await client.post("/api/v1/auth/invites", headers=auth_headers, json={"email": "a@example.com"})
        resp = await client.get("/api/v1/auth/invites", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_revoke_invite(self, client: AsyncClient, auth_headers: dict):
        with patch("app.services.notification_service.send_notification", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/v1/auth/invites", headers=auth_headers,
                json={"email": "revoke@example.com"},
            )
        invite_id = create_resp.json()["id"]
        revoke_resp = await client.delete(f"/api/v1/auth/invites/{invite_id}", headers=auth_headers)
        assert revoke_resp.status_code == 204


class TestVerifyAndAcceptInvite:
    async def test_verify_valid_token(self, client: AsyncClient, auth_headers: dict):
        with patch("app.services.notification_service.send_notification", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/v1/auth/invites", headers=auth_headers,
                json={"email": "verify@example.com", "role": "technician"},
            )
        token = create_resp.json()["token"]

        resp = await client.get(f"/api/v1/auth/invites/verify?token={token}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "verify@example.com"
        assert data["role"] == "technician"
        assert "org_name" in data

    async def test_verify_invalid_token(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/auth/invites/verify?token={uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_accept_invite_creates_user(self, client: AsyncClient, auth_headers: dict):
        with patch("app.services.notification_service.send_notification", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/v1/auth/invites", headers=auth_headers,
                json={"email": "accepted@example.com", "role": "operator"},
            )
        token = create_resp.json()["token"]

        accept_resp = await client.post(
            "/api/v1/auth/invites/accept",
            json={"token": token, "full_name": "New Person", "password": "SecurePass123!"},
        )
        assert accept_resp.status_code == 201
        data = accept_resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_accept_invite_cannot_reuse(self, client: AsyncClient, auth_headers: dict):
        with patch("app.services.notification_service.send_notification", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/v1/auth/invites", headers=auth_headers,
                json={"email": "reuse@example.com"},
            )
        token = create_resp.json()["token"]

        await client.post(
            "/api/v1/auth/invites/accept",
            json={"token": token, "full_name": "Person", "password": "SecurePass123!"},
        )
        resp2 = await client.post(
            "/api/v1/auth/invites/accept",
            json={"token": token, "full_name": "Person", "password": "SecurePass123!"},
        )
        assert resp2.status_code == 410

    async def test_accept_invite_weak_password(self, client: AsyncClient, auth_headers: dict):
        with patch("app.services.notification_service.send_notification", new_callable=AsyncMock):
            create_resp = await client.post(
                "/api/v1/auth/invites", headers=auth_headers,
                json={"email": "weakpw@example.com"},
            )
        token = create_resp.json()["token"]

        resp = await client.post(
            "/api/v1/auth/invites/accept",
            json={"token": token, "full_name": "Person", "password": "short"},
        )
        assert resp.status_code == 422
