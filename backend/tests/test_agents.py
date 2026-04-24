"""
Edge agent endpoint tests — cloud-facing and agent-facing.
"""
import uuid
import pytest
from httpx import AsyncClient
from app.models.facility import Facility
from app.models.agent import EdgeAgent


class TestAgentCloudFacing:
    """Cloud-facing endpoints (require user JWT)."""

    async def test_register_agent(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/agents", headers=auth_headers,
            json={"name": "Agent RPi-02", "hardware_type": "raspberry_pi_4"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Agent RPi-02"
        assert data["agent_key"].startswith("cg_")
        assert data["connection_state"] == "disconnected"

    async def test_list_agents(self, client: AsyncClient, auth_headers: dict, agent: EdgeAgent, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/agents", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["agents"][0]["name"] == "Agent Pi-01"

    async def test_get_agent(self, client: AsyncClient, auth_headers: dict, agent: EdgeAgent, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/agents/{agent.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["hardware_type"] == "raspberry_pi_4"

    async def test_update_agent(self, client: AsyncClient, auth_headers: dict, agent: EdgeAgent, facility: Facility):
        resp = await client.patch(
            f"/api/v1/facilities/{facility.id}/agents/{agent.id}",
            headers=auth_headers,
            json={"name": "Agent Pi-01-v2"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Agent Pi-01-v2"

    async def test_decommission_agent(self, client: AsyncClient, auth_headers: dict, agent: EdgeAgent, facility: Facility):
        resp = await client.delete(
            f"/api/v1/facilities/{facility.id}/agents/{agent.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

    async def test_cross_org_agent_blocked(
        self, client: AsyncClient, other_auth_headers: dict, agent: EdgeAgent, facility: Facility
    ):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/agents/{agent.id}",
            headers=other_auth_headers,
        )
        assert resp.status_code == 404


class TestAgentFacing:
    """Agent-facing endpoints (use agent_key, no JWT)."""

    async def test_heartbeat(self, client: AsyncClient, agent: EdgeAgent):
        resp = await client.post(
            f"/api/v1/agents/{agent.agent_key}/heartbeat",
            json={
                "cpu_percent": 42.5,
                "memory_percent": 68.0,
                "disk_percent": 31.2,
                "uptime_seconds": 86400,
                "version": "0.3.0",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "server_time" in data
        assert "pending_commands" in data

    async def test_heartbeat_invalid_key(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/agents/cg_invalid_key_999/heartbeat",
            json={"cpu_percent": 10.0},
        )
        assert resp.status_code == 401

    async def test_telemetry_ingest(self, client: AsyncClient, agent: EdgeAgent, equipment):
        resp = await client.post(
            f"/api/v1/agents/{agent.agent_key}/telemetry",
            json={
                "readings": [
                    {
                        "equipment_id": str(equipment.id),
                        "metric_name": "suction_pressure",
                        "value": 28.5,
                        "unit": "psi",
                    },
                    {
                        "equipment_id": str(equipment.id),
                        "metric_name": "discharge_temp",
                        "value": 185.2,
                        "unit": "F",
                    },
                ]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["inserted"] == 2

    async def test_poll_commands_empty(self, client: AsyncClient, agent: EdgeAgent):
        resp = await client.get(f"/api/v1/agents/{agent.agent_key}/commands")
        assert resp.status_code == 200
        assert resp.json()["commands"] == []

    async def test_upload_logs(self, client: AsyncClient, agent: EdgeAgent):
        resp = await client.post(
            f"/api/v1/agents/{agent.agent_key}/logs",
            json=[
                {"level": "info", "message": "Agent started"},
                {"level": "warning", "message": "High CPU detected", "context": {"cpu": 95.1}},
            ],
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 2
