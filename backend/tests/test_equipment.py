"""
Equipment endpoint tests.
"""
import uuid
import pytest
from httpx import AsyncClient
from app.models.facility import Facility, Equipment
from app.models.user import User


class TestEquipmentCRUD:
    async def test_list_empty(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/equipment", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_create_equipment(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/equipment", headers=auth_headers,
            json={
                "name": "Evaporator B2",
                "equipment_type": "evaporator",
                "manufacturer": "Heatcraft",
                "model": "LCA 260",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Evaporator B2"
        assert data["equipment_type"] == "evaporator"
        assert data["manufacturer"] == "Heatcraft"

    async def test_get_equipment(self, client: AsyncClient, auth_headers: dict, equipment: Equipment, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/equipment/{equipment.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Compressor A1"

    async def test_update_equipment(self, client: AsyncClient, auth_headers: dict, equipment: Equipment, facility: Facility):
        resp = await client.patch(
            f"/api/v1/facilities/{facility.id}/equipment/{equipment.id}",
            headers=auth_headers,
            json={"name": "Compressor A1-Updated", "protocol": "modbus_tcp"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Compressor A1-Updated"
        assert data["protocol"] == "modbus_tcp"

    async def test_delete_equipment(self, client: AsyncClient, auth_headers: dict, equipment: Equipment, facility: Facility):
        resp = await client.delete(
            f"/api/v1/facilities/{facility.id}/equipment/{equipment.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

        # Verify deleted
        resp2 = await client.get(
            f"/api/v1/facilities/{facility.id}/equipment/{equipment.id}",
            headers=auth_headers,
        )
        assert resp2.status_code == 404

    async def test_equipment_wrong_facility(self, client: AsyncClient, auth_headers: dict, equipment: Equipment, user: User):
        """Equipment should not be accessible under a different facility."""
        fake_facility_id = uuid.uuid4()
        resp = await client.get(
            f"/api/v1/facilities/{fake_facility_id}/equipment/{equipment.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_equipment_cross_org(
        self, client: AsyncClient, other_auth_headers: dict, equipment: Equipment, facility: Facility
    ):
        """Other org should not see this equipment."""
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/equipment/{equipment.id}",
            headers=other_auth_headers,
        )
        assert resp.status_code == 404
