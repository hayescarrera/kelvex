"""
Control sequences, automation rules, and alerts endpoint tests.
"""
import uuid
import pytest
from httpx import AsyncClient
from app.models.facility import Facility
from app.models.agent import EdgeAgent


class TestControlSequences:
    async def test_create_sequence(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/controls/sequences",
            headers=auth_headers,
            json={
                "name": "Pre-Cool Sequence",
                "sequence_type": "pre_cool",
                "steps": [
                    {"action": "lower_setpoint", "target": "all_freezers", "value": -5, "duration_min": 30},
                    {"action": "restore_setpoint", "target": "all_freezers"},
                ],
                "enabled": True,
                "priority": 30,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Pre-Cool Sequence"
        assert data["sequence_type"] == "pre_cool"
        assert len(data["steps"]) == 2

    async def test_list_sequences(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        # Create one first
        await client.post(
            f"/api/v1/facilities/{facility.id}/controls/sequences",
            headers=auth_headers,
            json={"name": "Test Seq", "sequence_type": "demand_response", "steps": []},
        )
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/controls/sequences",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    async def test_run_sequence(self, client: AsyncClient, auth_headers: dict, facility: Facility, agent: EdgeAgent, zone, equipment):
        """Run a sequence — should create CommandQueue entries for each step."""
        create = await client.post(
            f"/api/v1/facilities/{facility.id}/controls/sequences",
            headers=auth_headers,
            json={
                "name": "Runnable",
                "sequence_type": "load_shed",
                "steps": [
                    {"order": 1, "action": "set_setpoint", "target": str(zone.id), "params": {"temp": -5}},
                    {"order": 2, "action": "stage_compressor", "target": str(equipment.id), "params": {"stage": 2}},
                ],
            },
        )
        seq_id = create.json()["id"]

        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/controls/sequences/{seq_id}/run",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_count"] == 1
        assert data["last_result"] == "pending"

        # Verify commands were queued
        cmds = await client.get(
            f"/api/v1/facilities/{facility.id}/controls/commands?state=pending",
            headers=auth_headers,
        )
        assert cmds.status_code == 200
        assert cmds.json()["total"] >= 2

    async def test_run_sequence_no_steps_rejects(self, client: AsyncClient, auth_headers: dict, facility: Facility, agent: EdgeAgent):
        """Running a sequence with no steps returns 400."""
        create = await client.post(
            f"/api/v1/facilities/{facility.id}/controls/sequences",
            headers=auth_headers,
            json={"name": "Empty", "sequence_type": "load_shed", "steps": []},
        )
        seq_id = create.json()["id"]

        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/controls/sequences/{seq_id}/run",
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_run_sequence_no_agent_rejects(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        """Running a sequence without an agent returns 400."""
        create = await client.post(
            f"/api/v1/facilities/{facility.id}/controls/sequences",
            headers=auth_headers,
            json={
                "name": "No Agent",
                "sequence_type": "load_shed",
                "steps": [{"order": 1, "action": "set_setpoint", "params": {}}],
            },
        )
        seq_id = create.json()["id"]

        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/controls/sequences/{seq_id}/run",
            headers=auth_headers,
        )
        assert resp.status_code == 400


class TestAutomationRules:
    async def test_create_rule(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/controls/rules",
            headers=auth_headers,
            json={
                "name": "Peak Demand Shed",
                "trigger_conditions": {"metric": "demand_kw", "operator": ">", "value": 400},
                "actions": [{"type": "shed_load", "target": "non_critical", "amount_pct": 20}],
                "cooldown_minutes": 60,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Peak Demand Shed"
        assert data["enabled"] is True

    async def test_list_rules(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/controls/rules",
            headers=auth_headers,
        )
        assert resp.status_code == 200


class TestAlerts:
    async def test_create_alert(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/alerts",
            headers=auth_headers,
            json={
                "severity": "high",
                "category": "temperature",
                "alert_type": "temp_high",
                "title": "Freezer 1 temperature above threshold",
                "message": "Current temp: 5°F, threshold: 0°F",
                "trigger_value": 5.0,
                "threshold_value": 0.0,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["severity"] == "high"
        assert data["state"] == "active"

    async def test_list_alerts(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/alerts",
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_acknowledge_alert(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        # Create
        create = await client.post(
            f"/api/v1/facilities/{facility.id}/alerts",
            headers=auth_headers,
            json={
                "severity": "medium",
                "category": "equipment",
                "alert_type": "compressor_fault",
                "title": "Compressor A1 fault",
            },
        )
        alert_id = create.json()["id"]

        # Acknowledge
        resp = await client.patch(
            f"/api/v1/facilities/{facility.id}/alerts/{alert_id}",
            headers=auth_headers,
            json={"state": "acknowledged"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "acknowledged"

    async def test_alert_summary(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.get("/api/v1/alerts/summary", headers=auth_headers)
        assert resp.status_code == 200


class TestCommandQueue:
    async def test_queue_command(
        self, client: AsyncClient, auth_headers: dict, facility: Facility, agent: EdgeAgent
    ):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/controls/commands",
            headers=auth_headers,
            json={
                "agent_id": str(agent.id),
                "command_type": "set_setpoint",
                "parameters": {"zone": "freezer_1", "value": -12.0, "unit": "F"},
                "priority": 20,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["command_type"] == "set_setpoint"
        assert data["state"] == "pending"
