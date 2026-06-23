"""
Maintenance events endpoint tests.
"""
import uuid
import pytest
from httpx import AsyncClient

from app.models.facility import Facility


class TestMaintenanceEventsList:
    async def test_list_empty(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get("/api/v1/maintenance/events", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["events"] == []

    async def test_list_org_isolation(
        self, client: AsyncClient, auth_headers: dict,
        other_auth_headers: dict, facility: Facility,
    ):
        await client.post(
            "/api/v1/maintenance/events",
            headers=auth_headers,
            json={
                "facility_id": str(facility.id),
                "event_type": "inspection",
                "description": "Quarterly check",
            },
        )
        resp = await client.get("/api/v1/maintenance/events", headers=other_auth_headers)
        assert resp.json()["total"] == 0

    async def test_filter_by_event_type(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        for etype in ["repair", "inspection"]:
            await client.post(
                "/api/v1/maintenance/events",
                headers=auth_headers,
                json={"facility_id": str(facility.id), "event_type": etype, "description": f"Test {etype}"},
            )

        resp = await client.get(
            "/api/v1/maintenance/events?event_type=repair", headers=auth_headers
        )
        data = resp.json()
        assert data["total"] == 1
        assert data["events"][0]["event_type"] == "repair"


class TestMaintenanceEventCreate:
    async def test_create_minimal(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            "/api/v1/maintenance/events",
            headers=auth_headers,
            json={
                "facility_id": str(facility.id),
                "event_type": "repair",
                "description": "Replaced TXV on Rack B",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["event_type"] == "repair"
        assert data["description"] == "Replaced TXV on Rack B"
        assert data["facility_id"] == str(facility.id)
        assert data["occurred_at"] is not None
        assert data["created_at"] is not None

    async def test_create_with_technician(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            "/api/v1/maintenance/events",
            headers=auth_headers,
            json={
                "facility_id": str(facility.id),
                "event_type": "refrigerant",
                "description": "Added 8 lbs R-448A to Rack B",
                "technician_name": "J. Alvarez",
                "technician_company": "Arctic Service Co.",
                "occurred_at": "2026-06-01T10:30:00Z",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["technician_name"] == "J. Alvarez"
        assert data["technician_company"] == "Arctic Service Co."
        assert "2026-06-01" in data["occurred_at"]

    async def test_create_invalid_event_type(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            "/api/v1/maintenance/events",
            headers=auth_headers,
            json={
                "facility_id": str(facility.id),
                "event_type": "not_a_real_type",
                "description": "Test",
            },
        )
        assert resp.status_code == 422

    async def test_create_unknown_facility(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/maintenance/events",
            headers=auth_headers,
            json={
                "facility_id": str(uuid.uuid4()),
                "event_type": "repair",
                "description": "Test",
            },
        )
        assert resp.status_code == 404

    async def test_create_unauthenticated(self, client: AsyncClient, facility: Facility):
        resp = await client.post(
            "/api/v1/maintenance/events",
            json={"facility_id": str(facility.id), "event_type": "repair", "description": "Test"},
        )
        assert resp.status_code == 401

    async def test_all_valid_event_types(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        valid_types = ["repair", "inspection", "service", "replacement", "refrigerant", "cleaning", "calibration", "pm", "other"]
        for etype in valid_types:
            resp = await client.post(
                "/api/v1/maintenance/events",
                headers=auth_headers,
                json={"facility_id": str(facility.id), "event_type": etype, "description": f"Test {etype}"},
            )
            assert resp.status_code == 201, f"Failed for event_type={etype}: {resp.text}"
