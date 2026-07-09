"""
Integration endpoint tests — providers, CRUD, register maps.
"""
import uuid
import pytest
from httpx import AsyncClient
from app.models.facility import Facility


class TestProviders:
    async def test_list_providers(self, client: AsyncClient, auth_headers: dict, user=None):
        resp = await client.get("/api/v1/integrations/providers", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        # Should have our 7 providers
        provider_keys = [p["provider"] for p in data["providers"]]
        assert "danfoss_alsense" in provider_keys
        assert "bacnet_ip" in provider_keys
        assert "modbus_tcp" in provider_keys


class TestIntegrationCRUD:
    async def test_create_integration(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/integrations",
            headers=auth_headers,
            json={
                "provider": "modbus_tcp",
                "integration_type": "edge_protocol",
                "name": "Compressor Rack Modbus",
                "config": {"host": "192.168.1.100", "port": 502, "unit_id": 1},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Compressor Rack Modbus"
        assert data["provider"] == "modbus_tcp"
        assert data["connection_state"] == "disconnected"

    async def test_list_integrations(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        # Create one first
        await client.post(
            f"/api/v1/facilities/{facility.id}/integrations",
            headers=auth_headers,
            json={
                "provider": "bacnet_ip",
                "integration_type": "edge_protocol",
                "name": "BACnet Controller",
                "config": {"network": "192.168.1.0/24"},
            },
        )
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/integrations",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_get_integration(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        create = await client.post(
            f"/api/v1/facilities/{facility.id}/integrations",
            headers=auth_headers,
            json={
                "provider": "danfoss_alsense",
                "integration_type": "cloud_api",
                "name": "Danfoss Cloud",
                "config": {"api_url": "https://api.alsense.com"},
            },
        )
        int_id = create.json()["id"]

        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/integrations/{int_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["provider"] == "danfoss_alsense"

    async def test_delete_integration(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        create = await client.post(
            f"/api/v1/facilities/{facility.id}/integrations",
            headers=auth_headers,
            json={
                "provider": "emerson_oversight",
                "integration_type": "cloud_api",
                "name": "Emerson Oversight",
                "config": {},
            },
        )
        int_id = create.json()["id"]

        resp = await client.delete(
            f"/api/v1/facilities/{facility.id}/integrations/{int_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_cross_org_blocked(
        self, client: AsyncClient, auth_headers: dict, other_auth_headers: dict, facility: Facility
    ):
        create = await client.post(
            f"/api/v1/facilities/{facility.id}/integrations",
            headers=auth_headers,
            json={
                "provider": "modbus_tcp",
                "integration_type": "edge_protocol",
                "name": "Secret Integration",
                "config": {},
            },
        )
        int_id = create.json()["id"]

        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/integrations/{int_id}",
            headers=other_auth_headers,
        )
        assert resp.status_code == 404


class TestRegisterMaps:
    async def test_create_register_map_requires_kelvex_admin(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Register maps are global reference data shared across all tenants —
        org owners must not be able to create or modify them."""
        resp = await client.post(
            "/api/v1/register-maps",
            headers=auth_headers,
            json={"name": "nope", "protocol": "modbus_tcp", "registers": {}},
        )
        assert resp.status_code == 403

    async def test_create_register_map(self, client: AsyncClient, user):
        from tests.conftest import TestSessionLocal
        from app.core.security import get_password_hash, create_access_token
        from app.models.user import User

        async with TestSessionLocal() as db:
            admin = User(
                id=uuid.uuid4(),
                email="staff@kelvex.io",
                hashed_password=get_password_hash("TestPass123!"),
                full_name="Kelvex Staff",
                org_id=user.org_id,
                role="kelvex_admin",
                is_active=True,
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
        token = create_access_token(data={"sub": str(admin.id), "org": str(admin.org_id)})

        resp = await client.post(
            "/api/v1/register-maps",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "test_custom_map",
                "protocol": "modbus_tcp",
                "manufacturer": "Custom",
                "model": "Test Controller",
                "description": "Test register map",
                "registers": {
                    "suction_temp": {"address": 100, "data_type": "int16", "scale": 0.1, "unit": "F"},
                    "discharge_temp": {"address": 101, "data_type": "int16", "scale": 0.1, "unit": "F"},
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test_custom_map"
        assert len(data["registers"]) >= 2

    async def test_list_register_maps(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/register-maps", headers=auth_headers)
        assert resp.status_code == 200


class TestCredentials:
    async def test_store_credentials(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/credentials",
            headers=auth_headers,
            json={
                "provider": "danfoss_alsense",
                "auth_type": "api_key",
                "credentials": {"api_key": "sk-test-12345", "secret": "s3cret"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "danfoss_alsense"
        # Secrets should NOT be returned
        assert "credentials" not in data or "api_key" not in str(data.get("credentials", ""))

    async def test_list_credentials(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/credentials",
            headers=auth_headers,
        )
        assert resp.status_code == 200
