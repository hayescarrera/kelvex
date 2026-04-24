"""
Facility CRUD endpoint tests.
"""
import pytest
from httpx import AsyncClient
from app.models.facility import Facility
from app.models.user import User, Organization


class TestListFacilities:
    async def test_list_empty(self, client: AsyncClient, auth_headers: dict, user: User):
        resp = await client.get("/api/v1/facilities", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["facilities"] == []

    async def test_list_with_data(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get("/api/v1/facilities", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["facilities"][0]["name"] == "Warehouse Alpha"

    async def test_list_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/facilities")
        assert resp.status_code == 401


class TestCreateFacility:
    async def test_create_success(self, client: AsyncClient, auth_headers: dict, user: User):
        resp = await client.post("/api/v1/facilities", headers=auth_headers, json={
            "name": "New Warehouse",
            "city": "Dallas",
            "state": "TX",
            "sqft": 75000,
            "zone_types": ["freezer", "cooler"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "New Warehouse"
        assert data["city"] == "Dallas"
        assert data["sqft"] == 75000
        assert "id" in data
        assert "org_id" in data

    async def test_create_minimal(self, client: AsyncClient, auth_headers: dict, user: User):
        """Only name is required."""
        resp = await client.post("/api/v1/facilities", headers=auth_headers, json={
            "name": "Minimal Facility",
        })
        assert resp.status_code == 201
        assert resp.json()["name"] == "Minimal Facility"

    async def test_create_missing_name(self, client: AsyncClient, auth_headers: dict, user: User):
        resp = await client.post("/api/v1/facilities", headers=auth_headers, json={
            "city": "Nowhere",
        })
        assert resp.status_code == 422


class TestGetFacility:
    async def test_get_success(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get(f"/api/v1/facilities/{facility.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Warehouse Alpha"

    async def test_get_not_found(self, client: AsyncClient, auth_headers: dict, user: User):
        import uuid
        resp = await client.get(
            f"/api/v1/facilities/{uuid.uuid4()}", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_get_cross_org_blocked(
        self, client: AsyncClient, other_auth_headers: dict, facility: Facility
    ):
        """Users from another org should not access this facility."""
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}", headers=other_auth_headers
        )
        assert resp.status_code == 404


class TestUpdateFacility:
    async def test_update_success(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.patch(
            f"/api/v1/facilities/{facility.id}", headers=auth_headers,
            json={"name": "Updated Warehouse", "sqft": 60000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Warehouse"
        assert data["sqft"] == 60000
        # Unchanged fields should persist
        assert data["city"] == "Chicago"

    async def test_update_partial(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        """PATCH should only update provided fields."""
        resp = await client.patch(
            f"/api/v1/facilities/{facility.id}", headers=auth_headers,
            json={"city": "Milwaukee"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["city"] == "Milwaukee"
        assert data["name"] == "Warehouse Alpha"  # Unchanged


class TestDeleteFacility:
    async def test_delete_success(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.delete(
            f"/api/v1/facilities/{facility.id}", headers=auth_headers
        )
        assert resp.status_code == 204

        # Verify it's gone
        resp2 = await client.get(
            f"/api/v1/facilities/{facility.id}", headers=auth_headers
        )
        assert resp2.status_code == 404

    async def test_delete_cross_org_blocked(
        self, client: AsyncClient, other_auth_headers: dict, facility: Facility
    ):
        resp = await client.delete(
            f"/api/v1/facilities/{facility.id}", headers=other_auth_headers
        )
        assert resp.status_code == 404
