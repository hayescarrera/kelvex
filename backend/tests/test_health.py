"""
Health check and basic app tests.
"""
import pytest
from httpx import AsyncClient


class TestHealth:
    async def test_health_check(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in {"healthy", "degraded"}
        assert data["service"] == "kelvex-api"
        assert "checks" in data
        assert data["checks"]["database"] in {"healthy", "unhealthy"}
        assert data["checks"]["redis"] in {"healthy", "unhealthy"}

    async def test_response_has_request_headers(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert "X-Request-Id" in resp.headers
        assert "X-Kelvex-Version" in resp.headers

    async def test_docs_available(self, client: AsyncClient):
        resp = await client.get("/docs")
        assert resp.status_code == 200

    async def test_redoc_available(self, client: AsyncClient):
        resp = await client.get("/redoc")
        assert resp.status_code == 200
