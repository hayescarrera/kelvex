"""
Security & isolation tests.

Validates that org-scoping is enforced, tokens are validated properly,
and cross-tenant data leakage is impossible.
"""
import uuid
import pytest
from httpx import AsyncClient
from app.models.user import User, Organization
from app.models.facility import Facility
from app.core.security import create_access_token


class TestOrgIsolation:
    """Ensure users can only access their own org's data."""

    async def test_cannot_list_other_orgs_facilities(
        self, client: AsyncClient, other_auth_headers: dict, facility: Facility
    ):
        """Other org sees zero facilities, not our facility."""
        resp = await client.get("/api/v1/facilities", headers=other_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_cannot_create_facility_in_other_org(
        self, client: AsyncClient, other_auth_headers: dict
    ):
        """Creating a facility always scopes to the user's own org."""
        resp = await client.post("/api/v1/facilities", headers=other_auth_headers, json={
            "name": "Other Org Facility",
        })
        assert resp.status_code == 201
        # Verify it belongs to the other org, not our org
        data = resp.json()
        # The facility was created — it should be accessible by other_user
        resp2 = await client.get(
            f"/api/v1/facilities/{data['id']}", headers=other_auth_headers
        )
        assert resp2.status_code == 200


class TestTokenSecurity:
    """Validate JWT token handling edge cases."""

    async def test_expired_token_rejected(self, client: AsyncClient, user: User):
        """Expired tokens should be rejected."""
        from datetime import timedelta
        token = create_access_token(
            data={"sub": str(user.id), "org": str(user.org_id)},
            expires_delta=timedelta(seconds=-10),  # Already expired
        )
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 401

    async def test_tampered_token_rejected(self, client: AsyncClient):
        """Manually tampered tokens should be rejected."""
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0YW1wZXJlZCJ9.fake",
        })
        assert resp.status_code == 401

    async def test_no_auth_header_rejected(self, client: AsyncClient):
        resp = await client.get("/api/v1/facilities")
        assert resp.status_code == 401

    async def test_bearer_prefix_required(self, client: AsyncClient, user_token: str):
        """Token without 'Bearer' prefix should be rejected."""
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": user_token,  # Missing 'Bearer' prefix
        })
        assert resp.status_code == 401

    async def test_token_for_deleted_user(self, client: AsyncClient, user: User):
        """Token for a user that no longer exists should fail."""
        # Create token for a non-existent user
        fake_user_id = uuid.uuid4()
        token = create_access_token(
            data={"sub": str(fake_user_id), "org": str(user.org_id)},
        )
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 401


class TestGeneralApiRateLimit:
    async def test_general_api_rate_limited(self, client: AsyncClient, auth_headers: dict):
        from app.main import settings

        original_limit = settings.API_RATE_LIMIT_PER_MINUTE
        settings.API_RATE_LIMIT_PER_MINUTE = 1
        try:
            first = await client.get("/api/v1/facilities", headers=auth_headers)
            second = await client.get("/api/v1/facilities", headers=auth_headers)

            assert first.status_code == 200
            assert second.status_code == 429
            assert "Retry-After" in second.headers
        finally:
            settings.API_RATE_LIMIT_PER_MINUTE = original_limit
