"""
Auth endpoint tests — register, login, refresh, me.
"""
import pytest
from httpx import AsyncClient
from app.models.user import User


class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "new@coldgrid.io",
            "password": "SecurePass123!",
            "full_name": "New User",
            "org_name": "New Org",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_duplicate_email(self, client: AsyncClient, user: User):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "test@coldgrid.io",  # Same as fixture user
            "password": "AnotherPass123!",
            "full_name": "Duplicate",
            "org_name": "Dup Org",
        })
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "Pass123!",
            "full_name": "Bad Email",
            "org_name": "Org",
        })
        assert resp.status_code == 422

    async def test_register_missing_fields(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "partial@test.io",
        })
        assert resp.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient, user: User):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "test@coldgrid.io",
            "password": "TestPass123!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_login_wrong_password(self, client: AsyncClient, user: User):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "test@coldgrid.io",
            "password": "WrongPassword",
        })
        assert resp.status_code == 401
        assert "Invalid email or password" in resp.json()["detail"]

    async def test_login_nonexistent_user(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "Whatever123",
        })
        assert resp.status_code == 401

    async def test_login_inactive_user(self, client: AsyncClient, user: User):
        """Inactive users should not be able to log in."""
        # Deactivate user directly
        from tests.conftest import TestSessionLocal
        from sqlalchemy import update
        async with TestSessionLocal() as db:
            await db.execute(
                update(User).where(User.id == user.id).values(is_active=False)
            )
            await db.commit()

        resp = await client.post("/api/v1/auth/login", json={
            "email": "test@coldgrid.io",
            "password": "TestPass123!",
        })
        assert resp.status_code == 400
        assert "inactive" in resp.json()["detail"].lower()


class TestRefreshToken:
    async def test_refresh_success(self, client: AsyncClient, user: User):
        # First login to get tokens
        login = await client.post("/api/v1/auth/login", json={
            "email": "test@coldgrid.io",
            "password": "TestPass123!",
        })
        refresh_token = login.json()["refresh_token"]

        # Use refresh token
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        # Both tokens should be valid JWTs
        assert data["access_token"].count(".") == 2

    async def test_refresh_invalid_token(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": "garbage.token.here",
        })
        assert resp.status_code == 401

    async def test_refresh_with_access_token(self, client: AsyncClient, user: User, user_token: str):
        """Access tokens should not work as refresh tokens."""
        resp = await client.post("/api/v1/auth/refresh", json={
            "refresh_token": user_token,  # This is an access token, not refresh
        })
        assert resp.status_code == 401


class TestGetMe:
    async def test_get_me_success(self, client: AsyncClient, user: User, auth_headers: dict):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test@coldgrid.io"
        assert data["full_name"] == "Test User"
        assert data["is_admin"] is True
        assert "hashed_password" not in data

    async def test_get_me_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_get_me_invalid_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer invalid.jwt.token"
        })
        assert resp.status_code == 401


class TestAuthRateLimit:
    @pytest.mark.skip(reason="Requires Redis with per-test key isolation — not yet set up")
    async def test_auth_endpoint_rate_limited(self, client: AsyncClient, auth_headers: dict):
        pass
