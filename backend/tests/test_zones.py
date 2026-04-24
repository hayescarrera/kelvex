"""
Zone endpoint tests.
"""
import uuid
import pytest
from httpx import AsyncClient
from app.models.facility import Facility, Equipment
from app.models.zone import Zone


class TestZoneCRUD:
    async def test_create_zone(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/zones", headers=auth_headers,
            json={
                "name": "Cooler 1",
                "zone_type": "cooler",
                "temp_setpoint": 35.0,
                "temp_unit": "F",
                "area_sqft": 8000,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Cooler 1"
        assert data["zone_type"] == "cooler"
        assert float(data["temp_setpoint"]) == 35.0

    async def test_list_zones(self, client: AsyncClient, auth_headers: dict, zone: Zone, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/zones", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["zones"][0]["name"] == "Freezer 1"

    async def test_get_zone(self, client: AsyncClient, auth_headers: dict, zone: Zone, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/zones/{zone.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["zone_type"] == "freezer"

    async def test_update_zone(self, client: AsyncClient, auth_headers: dict, zone: Zone, facility: Facility):
        resp = await client.patch(
            f"/api/v1/facilities/{facility.id}/zones/{zone.id}",
            headers=auth_headers,
            json={"temp_setpoint": -15.0, "name": "Freezer 1 - Deep"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Freezer 1 - Deep"
        assert float(data["temp_setpoint"]) == -15.0

    async def test_delete_zone(self, client: AsyncClient, auth_headers: dict, zone: Zone, facility: Facility):
        resp = await client.delete(
            f"/api/v1/facilities/{facility.id}/zones/{zone.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_zone_cross_org_blocked(
        self, client: AsyncClient, other_auth_headers: dict, zone: Zone, facility: Facility
    ):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/zones/{zone.id}",
            headers=other_auth_headers,
        )
        assert resp.status_code == 404


class TestZoneEquipmentAssignment:
    async def test_assign_equipment(
        self, client: AsyncClient, auth_headers: dict,
        zone: Zone, equipment: Equipment, facility: Facility,
    ):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/zones/{zone.id}/equipment",
            headers=auth_headers,
            json={"equipment_id": str(equipment.id), "role": "primary"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "primary"
        assert data["equipment_id"] == str(equipment.id)
