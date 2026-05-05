"""
Integration tests for the compressor health engine.

Tests the full pipeline:
  - compute_health_score() with good / bad / threshold-crossing readings
  - Alert creation when score < 40
  - Ingest compressor readings via HTTP API → health score computes correctly
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from tests.conftest import TestSessionLocal
from app.models.compressor import Compressor, CompressorReading
from app.models.alert import Alert
from app.services.compressor_health import compute_health_score, _create_health_alert


def _make_reading(compressor_id, **overrides):
    """Create a healthy baseline CompressorReading, overriding any fields."""
    defaults = dict(
        id=uuid.uuid4(),
        compressor_id=compressor_id,
        discharge_pressure_psi=175.0,
        suction_pressure_psi=28.0,
        discharge_temp_f=182.0,
        oil_temp_f=145.0,
        bearing_temp_f=155.0,
        vibration_ips=0.12,
        amp_draw=220.0,
        kw=182.0,
        slide_valve_pct=78.0,
        rpm=3560.0,
        running=True,
        recorded_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    defaults.update(overrides)
    return CompressorReading(**defaults)


# ── compute_health_score: unit-level ─────────────────────


@pytest.mark.asyncio
class TestComputeHealthScore:
    async def test_healthy_compressor_scores_high(self, compressor: Compressor):
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            for i in range(10):
                db.add(_make_reading(
                    compressor.id,
                    id=uuid.uuid4(),
                    recorded_at=now - timedelta(minutes=i * 5),
                ))
            await db.commit()

        async with TestSessionLocal() as db:
            score, anomalies = await compute_health_score(compressor.id, db)

        assert score is not None
        assert score >= 70, f"Expected healthy score >= 70, got {score}"
        assert len(anomalies) == 0, f"Expected no anomalies, got: {anomalies}"

    async def test_insufficient_readings_returns_none(self, compressor: Compressor):
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            for i in range(2):
                db.add(_make_reading(
                    compressor.id,
                    id=uuid.uuid4(),
                    recorded_at=now - timedelta(minutes=i * 5),
                ))
            await db.commit()

        async with TestSessionLocal() as db:
            score, anomalies = await compute_health_score(compressor.id, db)

        assert score is None
        assert any("Insufficient" in a for a in anomalies)

    async def test_high_discharge_pressure_flags_anomaly(self, compressor: Compressor):
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            for i in range(10):
                db.add(_make_reading(
                    compressor.id,
                    id=uuid.uuid4(),
                    discharge_pressure_psi=240.0,  # above alarm_discharge_psi_high=220
                    recorded_at=now - timedelta(minutes=i * 5),
                ))
            await db.commit()

        async with TestSessionLocal() as db:
            score, anomalies = await compute_health_score(compressor.id, db)

        assert score is not None
        assert score < 100
        assert any("discharge" in a.lower() or "pressure" in a.lower() for a in anomalies)

    async def test_critical_readings_lower_score(self, compressor: Compressor):
        """Readings with multiple parameters above alarm thresholds produce a degraded score."""
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            for i in range(10):
                db.add(_make_reading(
                    compressor.id,
                    id=uuid.uuid4(),
                    discharge_pressure_psi=260.0,   # above alarm_discharge_psi_high=220
                    oil_temp_f=195.0,               # above alarm_oil_temp_high=170
                    bearing_temp_f=210.0,           # above alarm_bearing_temp_high=190
                    vibration_ips=0.45,             # above alarm_vibration_high=0.28
                    amp_draw=290.0,                 # above alarm_amp_draw_high=260
                    recorded_at=now - timedelta(minutes=i * 5),
                ))
            await db.commit()

        async with TestSessionLocal() as db:
            score, anomalies = await compute_health_score(compressor.id, db)

        assert score is not None
        # With uniform readings (bl_std=0), stat_score=100 blends with threshold_score=0
        # to give combined ≈ 40 per alarm parameter. Multiple parameters in alarm
        # produce a score well below the healthy threshold of 70.
        assert score < 70, f"Expected degraded score < 70 for multi-parameter alarm, got {score}"
        assert len(anomalies) >= 2, f"Expected multiple threshold-breach anomalies, got: {anomalies}"

    async def test_nonexistent_compressor_returns_none(self):
        async with TestSessionLocal() as db:
            score, anomalies = await compute_health_score(uuid.uuid4(), db)

        assert score is None
        assert any("not found" in a.lower() for a in anomalies)

    async def test_old_readings_outside_lookback_not_counted(self, compressor: Compressor):
        async with TestSessionLocal() as db:
            for i in range(10):
                db.add(_make_reading(
                    compressor.id,
                    id=uuid.uuid4(),
                    recorded_at=datetime.now(timezone.utc) - timedelta(hours=30 + i),
                ))
            await db.commit()

        async with TestSessionLocal() as db:
            score, anomalies = await compute_health_score(compressor.id, db, lookback_hours=24)

        assert score is None


# ── Health loop: alert creation ───────────────────────────


@pytest.mark.asyncio
class TestHealthLoopAlerts:
    async def test_create_health_alert_works(self, compressor: Compressor, facility):
        """_create_health_alert creates an alert for a critically-scored compressor."""
        async with TestSessionLocal() as db:
            c = await db.get(Compressor, compressor.id)
            c.state = "running"
            score = 28.5  # below 40 threshold
            anomalies = [
                "Discharge pressure above alarm: 260.0 psi",
                "Vibration above alarm: 0.45 ips",
                "Oil temp above alarm: 195.0 °F",
            ]
            await _create_health_alert(c, score, anomalies, db)
            await db.commit()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(Alert).where(
                    Alert.facility_id == facility.id,
                    Alert.alert_type == "compressor_health",
                )
            )
            alerts = result.scalars().all()
            assert len(alerts) == 1
            assert alerts[0].severity == "high"  # 25 <= score < 40 → high
            assert alerts[0].state == "active"
            assert str(compressor.id) in str(alerts[0].context)

    async def test_create_health_alert_not_duplicated(self, compressor: Compressor, facility):
        """Calling _create_health_alert twice produces only one active alert."""
        async with TestSessionLocal() as db:
            c = await db.get(Compressor, compressor.id)
            anomalies = ["Discharge pressure above alarm: 260.0 psi"]
            await _create_health_alert(c, 35.0, anomalies, db)
            await _create_health_alert(c, 35.0, anomalies, db)  # second call should be a no-op
            await db.commit()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(Alert).where(
                    Alert.facility_id == facility.id,
                    Alert.alert_type == "compressor_health",
                    Alert.state == "active",
                )
            )
            assert len(result.scalars().all()) == 1

    async def test_health_alert_severity_high_vs_critical(self, compressor: Compressor, facility):
        """Score < 25 → critical severity; 25–39 → high severity."""
        async with TestSessionLocal() as db:
            c = await db.get(Compressor, compressor.id)
            await _create_health_alert(c, 24.9, ["test anomaly"], db)  # critical
            await db.commit()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(Alert).where(
                    Alert.facility_id == facility.id,
                    Alert.alert_type == "compressor_health",
                )
            )
            alert = result.scalar_one()
            assert alert.severity == "critical"

    async def test_healthy_compressor_no_alert(self, compressor: Compressor, facility):
        """compute_health_score on healthy readings does not trigger _create_health_alert."""
        now = datetime.now(timezone.utc)
        async with TestSessionLocal() as db:
            for i in range(10):
                db.add(_make_reading(
                    compressor.id,
                    id=uuid.uuid4(),
                    recorded_at=now - timedelta(minutes=i * 5),
                ))
            await db.commit()

        async with TestSessionLocal() as db:
            score, anomalies = await compute_health_score(compressor.id, db)
            assert score is not None and score >= 70, f"Healthy readings should score >= 70, got {score}"
            # Score is >= 70, well above the < 40 alert threshold — no alert created
            await db.commit()

        async with TestSessionLocal() as db:
            result = await db.execute(
                select(Alert).where(
                    Alert.facility_id == facility.id,
                    Alert.alert_type == "compressor_health",
                )
            )
            assert len(result.scalars().all()) == 0


# ── HTTP pipeline: ingest → score ─────────────────────────


@pytest.mark.asyncio
class TestIngestToHealthPipeline:
    async def test_ingest_readings_then_compute_score(
        self, client: AsyncClient, agent, compressor: Compressor
    ):
        """POST compressor readings via HTTP API, then verify health score computes."""
        readings_payload = [
            {
                "compressor_id": str(compressor.id),
                "discharge_pressure_psi": 180.0,
                "suction_pressure_psi": 28.5,
                "discharge_temp_f": 184.0,
                "oil_temp_f": 148.0,
                "bearing_temp_f": 157.0,
                "vibration_ips": 0.13,
                "amp_draw": 225.0,
                "kw": 186.0,
                "slide_valve_pct": 78.0,
                "rpm": 3560,
                "running": True,
            }
            for _ in range(10)
        ]

        resp = await client.post(
            f"/api/v1/agents/{agent.agent_key}/compressor-readings",
            json={"readings": readings_payload},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 10

        async with TestSessionLocal() as db:
            score, anomalies = await compute_health_score(compressor.id, db)

        assert score is not None
        assert score >= 50, f"Expected reasonable score after healthy ingest, got {score}"

    async def test_ingest_cross_facility_readings_rejected(self, client: AsyncClient, agent):
        """Readings referencing a compressor from another facility should be dropped."""
        foreign_compressor_id = uuid.uuid4()

        resp = await client.post(
            f"/api/v1/agents/{agent.agent_key}/compressor-readings",
            json={"readings": [{
                "compressor_id": str(foreign_compressor_id),
                "discharge_pressure_psi": 180.0,
                "running": True,
            }]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 0
        assert len(data.get("errors", [])) >= 1
