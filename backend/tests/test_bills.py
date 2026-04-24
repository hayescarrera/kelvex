"""
Utility bills endpoint tests.
"""
import uuid
import io
import pytest
from httpx import AsyncClient
from app.models.facility import Facility
from app.models.billing import UtilityBill


class TestBillsCRUD:
    async def test_create_bill(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/bills", headers=auth_headers,
            json={
                "period_start": "2025-02-01",
                "period_end": "2025-02-28",
                "total_kwh": 130000,
                "total_cost": 19200.50,
                "peak_demand_kw": 480,
                "demand_charge": 5600,
                "energy_charge": 13600.50,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["period_start"] == "2025-02-01"
        assert float(data["total_cost"]) == 19200.50

    async def test_list_bills(self, client: AsyncClient, auth_headers: dict, bill: UtilityBill, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/bills", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["bills"][0]["period_start"] == "2025-01-01"

    async def test_get_bill(self, client: AsyncClient, auth_headers: dict, bill: UtilityBill, facility: Facility):
        resp = await client.get(
            f"/api/v1/facilities/{facility.id}/bills/{bill.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert float(resp.json()["peak_demand_kw"]) == 450.0

    async def test_delete_bill(self, client: AsyncClient, auth_headers: dict, bill: UtilityBill, facility: Facility):
        resp = await client.delete(
            f"/api/v1/facilities/{facility.id}/bills/{bill.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204


class TestBillUpload:
    async def test_upload_csv(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        csv_content = (
            "period_start,period_end,total_kwh,total_cost,peak_demand_kw,demand_charge,energy_charge\n"
            "2025-03-01,2025-03-31,140000,20100,500,5800,14300\n"
            "2025-04-01,2025-04-30,135000,19500,470,5400,14100\n"
        )
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/bills/upload",
            headers=auth_headers,
            files={"file": ("bills.csv", csv_content.encode(), "text/csv")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 2

    async def test_upload_bad_format(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/bills/upload",
            headers=auth_headers,
            files={"file": ("data.xlsx", b"not a csv", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "CSV" in resp.json()["detail"]

    async def test_upload_missing_columns(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        csv_content = "foo,bar,baz\n1,2,3\n"
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/bills/upload",
            headers=auth_headers,
            files={"file": ("bills.csv", csv_content.encode(), "text/csv")},
        )
        assert resp.status_code == 400


class TestBillAnalysis:
    async def test_analyze_bill(self, client: AsyncClient, auth_headers: dict, bill: UtilityBill, facility: Facility):
        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/bills/{bill.id}/analyze",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "peak_demand_kw" in data
        assert "savings_potential" in data

    async def test_analyze_bill_missing_data(self, client: AsyncClient, auth_headers: dict, facility: Facility):
        """Bill without demand data should fail analysis."""
        # Create a bill without peak_demand_kw
        create = await client.post(
            f"/api/v1/facilities/{facility.id}/bills", headers=auth_headers,
            json={
                "period_start": "2025-05-01",
                "period_end": "2025-05-31",
                "total_kwh": 100000,
                "total_cost": 15000,
            },
        )
        bill_id = create.json()["id"]

        resp = await client.post(
            f"/api/v1/facilities/{facility.id}/bills/{bill_id}/analyze",
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "peak_demand_kw" in resp.json()["detail"]
