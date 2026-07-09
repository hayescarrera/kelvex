"""
AIM Act audit export package — the artifact behind the marketing claim.
"""
import io
import uuid
import zipfile
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient

from tests.conftest import TestSessionLocal
from app.models.facility import Facility
from app.models.user import User
from app.models.refrigerant import (
    RefrigerantCircuit, RefrigerantAdd, LeakEvent, RepairRecord,
)


@pytest.fixture
def _now():
    return datetime.now(timezone.utc)


async def _seed_circuit_history(user: User, facility: Facility, now):
    """One circuit at 25% leak rate with an add, an event, and a repair."""
    async with TestSessionLocal() as db:
        circuit = RefrigerantCircuit(
            id=uuid.uuid4(),
            org_id=user.org_id,
            facility_id=facility.id,
            name="Rack B — Dairy",
            refrigerant_type="R-448A",
            full_charge_lbs=100.0,
            is_active=True,
        )
        db.add(circuit)
        await db.flush()

        event = LeakEvent(
            id=uuid.uuid4(),
            org_id=user.org_id,
            facility_id=facility.id,
            circuit_id=circuit.id,
            rack_name="Rack B",
            detection_method="pressure_drift",
            confidence="high",
            status="repaired",
            detected_at=now - timedelta(days=40),
            repaired_at=now - timedelta(days=30),
            estimated_loss_lbs=20.0,
        )
        db.add(event)
        await db.flush()

        db.add(RefrigerantAdd(
            id=uuid.uuid4(),
            org_id=user.org_id,
            facility_id=facility.id,
            circuit_id=circuit.id,
            leak_event_id=event.id,
            rack_name="Rack B",
            refrigerant_type="R-448A",
            amount_lbs=25.0,
            technician_name="Pat Doe",
            technician_epa_cert="EPA-608-12345",
            added_at=now - timedelta(days=35),
        ))
        db.add(RepairRecord(
            id=uuid.uuid4(),
            org_id=user.org_id,
            facility_id=facility.id,
            circuit_id=circuit.id,
            leak_event_id=event.id,
            rack_name="Rack B",
            description="Replaced suction line schrader valve",
            technician_name="Pat Doe",
            repaired_at=now - timedelta(days=30),
            verified_leak_free=True,
            verification_method="electronic_detector",
            refrigerant_recovered_lbs=1.5,
        ))
        await db.commit()
        return circuit


@pytest.mark.asyncio
class TestAimActExport:
    async def test_export_package_contents(
        self, client: AsyncClient, auth_headers: dict, user: User, facility: Facility, _now
    ):
        await _seed_circuit_history(user, facility, _now)

        resp = await client.get("/api/v1/refrigerant/aim-act/export", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        assert "kelvex-aim-act-package-" in resp.headers["content-disposition"]

        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = set(zf.namelist())
        assert names == {
            "README.txt", "leak_rate_summary.csv", "refrigerant_additions.csv",
            "leak_events.csv", "repair_records.csv",
        }

        summary = zf.read("leak_rate_summary.csv").decode()
        assert "Rack B — Dairy" in summary
        assert "25.0" in summary            # 25 lbs added on 100 lb charge
        assert "EXCEEDS THRESHOLD" in summary  # 25% >= 20%

        readme = zf.read("README.txt").decode()
        assert "20%" in readme
        assert "40 CFR Part 84" in readme

        adds = zf.read("refrigerant_additions.csv").decode()
        assert "Pat Doe" in adds and "EPA-608-12345" in adds

        repairs = zf.read("repair_records.csv").decode()
        assert "electronic_detector" in repairs and "yes" in repairs

    async def test_export_requires_reports_permission(
        self, client: AsyncClient, user: User, facility: Facility
    ):
        from app.core.security import get_password_hash, create_access_token
        async with TestSessionLocal() as db:
            viewer = User(
                id=uuid.uuid4(),
                email="viewer-export@coldgrid.io",
                hashed_password=get_password_hash("TestPass123!"),
                full_name="Viewer",
                org_id=user.org_id,
                role="viewer",
                is_active=True,
            )
            db.add(viewer)
            await db.commit()
            await db.refresh(viewer)
        token = create_access_token(data={"sub": str(viewer.id), "org": str(viewer.org_id)})
        resp = await client.get(
            "/api/v1/refrigerant/aim-act/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
