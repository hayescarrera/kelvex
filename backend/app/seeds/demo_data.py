"""
Demo data seed for Kelvex sales demos.

Creates a realistic cold storage environment:
  - Demo user account (demo@kelvex.io / demo123)
  - 2 facilities with real-world details
  - Zones with realistic temperatures
  - Compressors with health scores and readings
  - Active + resolved alerts
  - HACCP compliance CCPs, logs, and excursions
  - Maintenance tasks (scheduled, in progress, overdue)
  - Telemetry data for charts (48h of readings)

Usage:
  python -m app.seeds.demo_data
  Or call seed_demo_data(db) from startup
"""

import uuid
import asyncio
import random
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Stable UUIDs for demo data
DEMO_ORG_ID = uuid.UUID("d0000000-0000-0000-0000-000000000001")
DEMO_USER_ID = uuid.UUID("d0000000-0000-0000-0000-000000000010")
FAC_CHICAGO_ID = uuid.UUID("d0000000-0000-0000-0000-000000000100")
FAC_DALLAS_ID = uuid.UUID("d0000000-0000-0000-0000-000000000200")


async def seed_demo_data(db: AsyncSession):
    """Seed full demo environment. Idempotent — skips if demo org exists."""
    from app.models.user import Organization, User
    from app.models.facility import Facility
    from app.models.zone import Zone
    from app.models.compressor import Compressor, CompressorReading
    from app.models.alert import Alert
    from app.models.compliance import (
        CriticalControlPoint, ComplianceLog, TempExcursion,
        MaintenanceTask, ComplianceReport,
    )
    from app.models.telemetry import Telemetry
    from app.models.billing import UtilityBill
    from app.core.security import get_password_hash

    # Check if already seeded
    result = await db.execute(select(Organization).where(Organization.id == DEMO_ORG_ID))
    if result.scalar_one_or_none():
        print("Demo data already exists, skipping seed")
        return

    now = datetime.now(timezone.utc)

    # ── Organization & User ─────────────────────
    org = Organization(id=DEMO_ORG_ID, name="Kelvex Demo", slug="kelvex-demo")
    db.add(org)
    await db.flush()

    user = User(
        id=DEMO_USER_ID,
        org_id=DEMO_ORG_ID,
        email="demo@kelvex.io",
        hashed_password=get_password_hash("demo123"),
        full_name="Ben Linder",
        role="owner",
        is_active=True,
    )
    db.add(user)

    # ── Facilities ──────────────────────────────
    fac_chicago = Facility(
        id=FAC_CHICAGO_ID,
        org_id=DEMO_ORG_ID,
        name="Midwest Distribution Center",
        address="4200 S Ashland Ave",
        city="Chicago",
        state="IL",
        zip_code="60609",
        sqft=120000,
        latitude=41.8165,
        longitude=-87.6648,
        zone_types=["frozen", "cooler", "dock"],
    )
    db.add(fac_chicago)

    fac_dallas = Facility(
        id=FAC_DALLAS_ID,
        org_id=DEMO_ORG_ID,
        name="Southwest Cold Storage",
        address="1800 Irving Blvd",
        city="Dallas",
        state="TX",
        zip_code="75207",
        sqft=85000,
        latitude=32.7942,
        longitude=-96.8197,
        zone_types=["frozen", "cooler"],
    )
    db.add(fac_dallas)
    await db.flush()

    # ── Zones (Chicago) ─────────────────────────
    zones_chicago = [
        {"name": "Freezer A — Proteins", "zone_type": "frozen", "temp_setpoint": -10.0,
         "temp_alarm_high": 0.0, "temp_alarm_low": -25.0, "current_temp": -8.2,
         "area_sqft": 25000, "position_x": 50, "position_y": 50, "width": 200, "height": 150},

        {"name": "Freezer B — Seafood", "zone_type": "frozen", "temp_setpoint": -15.0,
         "temp_alarm_high": -5.0, "temp_alarm_low": -30.0, "current_temp": -14.1,
         "area_sqft": 18000, "position_x": 280, "position_y": 50, "width": 180, "height": 150},

        {"name": "Cooler 1 — Dairy/Produce", "zone_type": "cooler", "temp_setpoint": 34.0,
         "temp_alarm_high": 41.0, "temp_alarm_low": 28.0, "current_temp": 35.2,
         "area_sqft": 30000, "position_x": 50, "position_y": 230, "width": 220, "height": 130},

        {"name": "Cooler 2 — Beverages", "zone_type": "cooler", "temp_setpoint": 36.0,
         "temp_alarm_high": 42.0, "temp_alarm_low": 30.0, "current_temp": 36.8,
         "area_sqft": 15000, "position_x": 300, "position_y": 230, "width": 160, "height": 130},

        {"name": "Loading Dock A", "zone_type": "dock", "temp_setpoint": 45.0,
         "temp_alarm_high": 55.0, "temp_alarm_low": 35.0, "current_temp": 48.3,
         "area_sqft": 8000, "position_x": 50, "position_y": 400, "width": 410, "height": 80},
    ]

    zone_ids_chi = []
    for z in zones_chicago:
        zone = Zone(
            facility_id=FAC_CHICAGO_ID,
            name=z["name"], zone_type=z["zone_type"],
            temp_setpoint=z["temp_setpoint"], temp_unit="degF",
            temp_tolerance=3.0,
            temp_alarm_high=z["temp_alarm_high"], temp_alarm_low=z["temp_alarm_low"],
            current_temp=z["current_temp"],
            area_sqft=z.get("area_sqft"),
            position_x=z.get("position_x"), position_y=z.get("position_y"),
            width=z.get("width"), height=z.get("height"),
            last_reading_at=now - timedelta(minutes=random.randint(1, 5)),
        )
        db.add(zone)
        await db.flush()
        zone_ids_chi.append(zone.id)

    # ── Zones (Dallas) ──────────────────────────
    zones_dallas = [
        {"name": "Freezer — Main", "zone_type": "frozen", "temp_setpoint": -12.0,
         "temp_alarm_high": -2.0, "temp_alarm_low": -25.0, "current_temp": -11.5,
         "area_sqft": 35000},

        {"name": "Cooler — Pharma", "zone_type": "cooler", "temp_setpoint": 38.0,
         "temp_alarm_high": 46.0, "temp_alarm_low": 33.0, "current_temp": 37.1,
         "area_sqft": 12000},
    ]

    zone_ids_dal = []
    for z in zones_dallas:
        zone = Zone(
            facility_id=FAC_DALLAS_ID,
            name=z["name"], zone_type=z["zone_type"],
            temp_setpoint=z["temp_setpoint"], temp_unit="degF",
            temp_tolerance=3.0,
            temp_alarm_high=z["temp_alarm_high"], temp_alarm_low=z["temp_alarm_low"],
            current_temp=z["current_temp"],
            area_sqft=z.get("area_sqft"),
            last_reading_at=now - timedelta(minutes=random.randint(1, 5)),
        )
        db.add(zone)
        await db.flush()
        zone_ids_dal.append(zone.id)

    # ── Compressors (Chicago — 4 units) ─────────
    compressors_chi_data = [
        {"name": "Comp-A1", "tag": "COMP-A1", "manufacturer": "Frick", "model": "RWF II 480",
         "hp": 350, "capacity_tons": 280, "refrigerant": "NH3", "state": "running", "health_score": 94,
         "design_suction_psi": 28.0, "design_discharge_psi": 180.0},

        {"name": "Comp-A2", "tag": "COMP-A2", "manufacturer": "Frick", "model": "RWF II 480",
         "hp": 350, "capacity_tons": 280, "refrigerant": "NH3", "state": "running", "health_score": 87,
         "design_suction_psi": 28.0, "design_discharge_psi": 180.0},

        {"name": "Comp-B1", "tag": "COMP-B1", "manufacturer": "Mycom", "model": "N8WB",
         "hp": 200, "capacity_tons": 160, "refrigerant": "NH3", "state": "running", "health_score": 91,
         "design_suction_psi": 25.0, "design_discharge_psi": 175.0},

        {"name": "Comp-B2", "tag": "COMP-B2", "manufacturer": "Mycom", "model": "N8WB",
         "hp": 200, "capacity_tons": 160, "refrigerant": "NH3", "state": "idle", "health_score": 72,
         "design_suction_psi": 25.0, "design_discharge_psi": 175.0},
    ]

    comp_ids_chi = []
    for c in compressors_chi_data:
        comp = Compressor(
            facility_id=FAC_CHICAGO_ID,
            name=c["name"], tag=c["tag"],
            manufacturer=c["manufacturer"], model=c["model"],
            compressor_type="screw", refrigerant=c["refrigerant"],
            hp=c["hp"], capacity_tons=c["capacity_tons"],
            design_suction_psi=c["design_suction_psi"],
            design_discharge_psi=c["design_discharge_psi"],
            max_discharge_temp_f=220.0,
            alarm_discharge_psi_high=220.0, alarm_suction_psi_low=15.0,
            alarm_oil_temp_high=170.0, alarm_bearing_temp_high=190.0,
            alarm_vibration_high=0.3, alarm_amp_draw_high=280.0,
            state=c["state"], health_score=c["health_score"],
            run_hours=random.randint(12000, 45000),
            last_reading_at=now - timedelta(minutes=random.randint(1, 3)),
        )
        db.add(comp)
        await db.flush()
        comp_ids_chi.append(comp.id)

    # ── Compressors (Dallas — 2 units) ──────────
    compressors_dal_data = [
        {"name": "Comp-1", "tag": "COMP-1", "manufacturer": "Vilter", "model": "VSG 601",
         "hp": 250, "capacity_tons": 200, "refrigerant": "NH3", "state": "running", "health_score": 96},

        {"name": "Comp-2", "tag": "COMP-2", "manufacturer": "GEA", "model": "Grasso SP1",
         "hp": 150, "capacity_tons": 120, "refrigerant": "R-717", "state": "running", "health_score": 88},
    ]

    for c in compressors_dal_data:
        comp = Compressor(
            facility_id=FAC_DALLAS_ID,
            name=c["name"], tag=c["tag"],
            manufacturer=c["manufacturer"], model=c["model"],
            compressor_type="screw", refrigerant=c["refrigerant"],
            hp=c["hp"], capacity_tons=c["capacity_tons"],
            design_suction_psi=28.0, design_discharge_psi=180.0,
            max_discharge_temp_f=220.0,
            state=c["state"], health_score=c["health_score"],
            run_hours=random.randint(8000, 30000),
            last_reading_at=now - timedelta(minutes=random.randint(1, 3)),
        )
        db.add(comp)

    # ── Alerts ──────────────────────────────────
    # Some resolved, some active
    alerts_data = [
        {"facility_id": FAC_CHICAGO_ID, "zone_id": zone_ids_chi[0], "severity": "high",
         "category": "temperature", "title": "Freezer A temp rising — approaching critical limit",
         "state": "resolved", "created_at": now - timedelta(hours=18),
         "resolved_at": now - timedelta(hours=16)},

        {"facility_id": FAC_CHICAGO_ID, "zone_id": zone_ids_chi[4], "severity": "medium",
         "category": "door", "title": "Loading Dock A — door open > 15 minutes",
         "state": "resolved", "created_at": now - timedelta(hours=6),
         "resolved_at": now - timedelta(hours=5, minutes=40)},

        {"facility_id": FAC_CHICAGO_ID, "severity": "low",
         "category": "equipment", "title": "Comp-B2 vibration trending upward — 0.22 in/s",
         "state": "active", "created_at": now - timedelta(hours=2)},

        {"facility_id": FAC_DALLAS_ID, "zone_id": zone_ids_dal[1], "severity": "medium",
         "category": "temperature", "title": "Pharma cooler temp 39.4°F — above setpoint",
         "state": "acknowledged", "created_at": now - timedelta(hours=4)},

        {"facility_id": FAC_CHICAGO_ID, "severity": "high",
         "category": "equipment", "title": "Comp-A2 discharge pressure 198 PSI — approaching alarm",
         "state": "active", "created_at": now - timedelta(minutes=45)},
    ]

    for a in alerts_data:
        alert = Alert(
            facility_id=a["facility_id"],
            zone_id=a.get("zone_id"),
            severity=a["severity"],
            category=a["category"],
            title=a["title"],
            state=a["state"],
            created_at=a["created_at"],
            resolved_at=a.get("resolved_at"),
        )
        db.add(alert)

    # ── HACCP CCPs ──────────────────────────────
    ccp_data = [
        {"facility_id": FAC_CHICAGO_ID, "name": "Freezer A — Protein Storage",
         "zone_id": zone_ids_chi[0], "temp_min": -25.0, "temp_max": 0.0,
         "hazard_type": "biological", "corrective_action": "Move product to backup freezer. Notify QA manager. Document incident."},

        {"facility_id": FAC_CHICAGO_ID, "name": "Cooler 1 — Dairy Receiving",
         "zone_id": zone_ids_chi[2], "temp_min": 28.0, "temp_max": 41.0,
         "hazard_type": "biological", "corrective_action": "Check evaporator coils. Verify door seals. Move perishables if temp exceeds 41°F for >30min."},

        {"facility_id": FAC_DALLAS_ID, "name": "Pharma Cold Chain",
         "zone_id": zone_ids_dal[1], "temp_min": 33.0, "temp_max": 46.0,
         "hazard_type": "chemical", "corrective_action": "Quarantine affected product. Contact pharma client. File deviation report."},
    ]

    ccp_ids = []
    for c in ccp_data:
        ccp = CriticalControlPoint(
            facility_id=c["facility_id"], org_id=DEMO_ORG_ID,
            name=c["name"], zone_id=c.get("zone_id"),
            temp_min=c["temp_min"], temp_max=c["temp_max"],
            temp_unit="degF", warning_offset=2.0,
            check_interval_min=15, excursion_threshold_min=30,
            hazard_type=c["hazard_type"],
            corrective_action=c["corrective_action"],
        )
        db.add(ccp)
        await db.flush()
        ccp_ids.append(ccp.id)

    # Compliance logs — last 24h of checks for first CCP
    for i in range(96):  # every 15 min for 24h
        check_time = now - timedelta(minutes=15 * i)
        temp = -8.0 + random.uniform(-3.0, 3.0)
        status = "pass" if -25.0 < temp < 0.0 else "critical"
        log = ComplianceLog(
            ccp_id=ccp_ids[0], facility_id=FAC_CHICAGO_ID,
            temperature=round(temp, 1), temp_unit="degF",
            status=status, limit_min=-25.0, limit_max=0.0,
            checked_at=check_time, source="auto",
        )
        db.add(log)

    # One resolved excursion from yesterday
    exc = TempExcursion(
        ccp_id=ccp_ids[0], facility_id=FAC_CHICAGO_ID, org_id=DEMO_ORG_ID,
        severity="warning", peak_temp=2.1, avg_temp=0.8,
        limit_breached="high",
        started_at=now - timedelta(hours=22),
        ended_at=now - timedelta(hours=21, minutes=15),
        duration_minutes=45,
        state="resolved",
        corrective_action_taken="Identified defrost cycle overlap. Adjusted defrost schedule to stagger between zones.",
        resolved_by=DEMO_USER_ID,
        resolved_at=now - timedelta(hours=20),
        notes="Root cause: defrost cycles on evap coils A and B overlapping. Fixed by offsetting 30 min.",
    )
    db.add(exc)

    # Compliance report
    report = ComplianceReport(
        facility_id=FAC_CHICAGO_ID, org_id=DEMO_ORG_ID,
        report_type="weekly", title="Weekly Compliance Report — Midwest Distribution Center",
        period_start=now - timedelta(days=7), period_end=now,
        total_checks=672, passed_checks=668, failed_checks=4,
        excursion_count=1, compliance_pct=99.4,
        report_data={
            "facility_name": "Midwest Distribution Center",
            "period": {"start": (now - timedelta(days=7)).isoformat(), "end": now.isoformat()},
            "checks": {"total": 672, "passed": 668, "warning": 3, "critical": 1},
            "compliance_pct": 99.4,
            "excursions": [{"severity": "warning", "peak_temp": 2.1, "duration_minutes": 45, "state": "resolved"}],
        },
        generated_by=DEMO_USER_ID,
        signed_off_by=DEMO_USER_ID,
        signed_off_at=now - timedelta(days=1),
        sign_off_notes="Reviewed. Single excursion was addressed — defrost schedule corrected.",
        state="signed_off",
    )
    db.add(report)

    # ── Maintenance Tasks ───────────────────────
    maintenance_data = [
        {"facility_id": FAC_CHICAGO_ID, "title": "Comp-A1 oil filter replacement",
         "category": "preventive", "priority": "medium", "state": "completed",
         "due_date": now - timedelta(days=3), "completed_at": now - timedelta(days=2),
         "is_recurring": True, "recurrence_days": 90,
         "completion_notes": "Replaced oil filter and topped off oil. Oil pressure normal at 55 PSI.",
         "labor_hours": 1.5, "parts_used": [{"part": "Oil filter 3F-284", "qty": 1}, {"part": "Compressor oil 5gal", "qty": 1}]},

        {"facility_id": FAC_CHICAGO_ID, "title": "Evaporator coil inspection — Freezer B",
         "category": "inspection", "priority": "medium", "state": "scheduled",
         "due_date": now + timedelta(days=2), "is_recurring": True, "recurrence_days": 30},

        {"facility_id": FAC_CHICAGO_ID, "title": "Comp-B2 vibration analysis — bearing check",
         "category": "corrective", "priority": "high", "state": "in_progress",
         "due_date": now + timedelta(days=1),
         "checklist": [
             {"item": "Take vibration readings at drive end", "done": True},
             {"item": "Take vibration readings at non-drive end", "done": True},
             {"item": "Compare to baseline", "done": False},
             {"item": "Inspect coupling alignment", "done": False},
             {"item": "Document findings", "done": False},
         ]},

        {"facility_id": FAC_CHICAGO_ID, "title": "Ammonia leak detector calibration",
         "category": "calibration", "priority": "high", "state": "scheduled",
         "due_date": now - timedelta(days=1)},  # Overdue!

        {"facility_id": FAC_DALLAS_ID, "title": "Condenser coil cleaning",
         "category": "preventive", "priority": "low", "state": "scheduled",
         "due_date": now + timedelta(days=14), "is_recurring": True, "recurrence_days": 60},
    ]

    for m in maintenance_data:
        task = MaintenanceTask(
            facility_id=m["facility_id"], org_id=DEMO_ORG_ID,
            title=m["title"], category=m["category"],
            priority=m["priority"], state=m["state"],
            due_date=m.get("due_date"),
            completed_at=m.get("completed_at"),
            is_recurring=m.get("is_recurring", False),
            recurrence_days=m.get("recurrence_days"),
            assigned_to=DEMO_USER_ID,
            completion_notes=m.get("completion_notes"),
            labor_hours=m.get("labor_hours"),
            parts_used=m.get("parts_used"),
            checklist=m.get("checklist"),
        )
        db.add(task)

    # ── Utility Bills (12 months) ────────────────
    # Chicago: 120,000 sqft distribution center, ComEd TOU rate
    #   base peak ~430 kW, ~240,000 kWh/mo, demand rate $18/kW, energy $0.085/kWh
    # Dallas: 85,000 sqft frozen warehouse, Oncor rate
    #   base peak ~280 kW, ~145,000 kWh/mo, demand rate $14/kW, energy $0.095/kWh
    chicago_bills = [
        # (period_start, period_end, peak_kw, kwh, demand_$, energy_$)
        (date(2025, 5, 1),  date(2025, 6, 1),  451, 252000, 8118,  21420),
        (date(2025, 6, 1),  date(2025, 7, 1),  507, 276000, 9126,  23460),
        (date(2025, 7, 1),  date(2025, 8, 1),  529, 288000, 9522,  24480),
        (date(2025, 8, 1),  date(2025, 9, 1),  516, 283200, 9288,  24072),
        (date(2025, 9, 1),  date(2025, 10, 1), 473, 264000, 8514,  22440),
        (date(2025, 10, 1), date(2025, 11, 1), 430, 240000, 7740,  20400),
        (date(2025, 11, 1), date(2025, 12, 1), 404, 228000, 7272,  19380),
        (date(2025, 12, 1), date(2026, 1, 1),  391, 223200, 7038,  18972),
        (date(2026, 1, 1),  date(2026, 2, 1),  396, 225600, 7128,  19176),
        (date(2026, 2, 1),  date(2026, 3, 1),  387, 220800, 6966,  18768),
        (date(2026, 3, 1),  date(2026, 4, 1),  408, 230400, 7344,  19584),
        (date(2026, 4, 1),  date(2026, 5, 1),  421, 235200, 7578,  19992),
    ]
    dallas_bills = [
        (date(2025, 5, 1),  date(2025, 6, 1),  308, 159500, 4312,  15153),
        (date(2025, 6, 1),  date(2025, 7, 1),  336, 174000, 4704,  16530),
        (date(2025, 7, 1),  date(2025, 8, 1),  350, 181250, 4900,  17219),
        (date(2025, 8, 1),  date(2025, 9, 1),  342, 176900, 4788,  16806),
        (date(2025, 9, 1),  date(2025, 10, 1), 322, 166750, 4508,  15841),
        (date(2025, 10, 1), date(2025, 11, 1), 286, 148900, 4004,  14146),
        (date(2025, 11, 1), date(2025, 12, 1), 261, 134850, 3654,  12811),
        (date(2025, 12, 1), date(2026, 1, 1),  246, 127600, 3444,  12122),
        (date(2026, 1, 1),  date(2026, 2, 1),  247, 127600, 3458,  12122),
        (date(2026, 2, 1),  date(2026, 3, 1),  252, 130500, 3528,  12398),
        (date(2026, 3, 1),  date(2026, 4, 1),  266, 137750, 3724,  13086),
        (date(2026, 4, 1),  date(2026, 5, 1),  280, 145000, 3920,  13775),
    ]
    for fac_id, rows in ((FAC_CHICAGO_ID, chicago_bills), (FAC_DALLAS_ID, dallas_bills)):
        for (ps, pe, peak_kw, kwh, demand_c, energy_c) in rows:
            bill = UtilityBill(
                facility_id=fac_id,
                period_start=ps,
                period_end=pe,
                peak_demand_kw=peak_kw,
                total_kwh=kwh,
                demand_charge=Decimal(str(demand_c)),
                energy_charge=Decimal(str(energy_c)),
                total_cost=Decimal(str(demand_c + energy_c)),
                parsed_at=now,
            )
            db.add(bill)

    await db.commit()
    print("Demo data seeded successfully!")
    print("  Login: demo@kelvex.io / demo123")
    print("  Facilities: Midwest Distribution Center (Chicago), Southwest Cold Storage (Dallas)")
    print("  Zones: 7 total (5 Chicago, 2 Dallas)")
    print("  Compressors: 6 total (4 Chicago, 2 Dallas)")
    print("  Alerts: 5 (2 active, 1 acknowledged, 2 resolved)")
    print("  CCPs: 3, Compliance logs: 96, Excursions: 1 (resolved)")
    print("  Maintenance tasks: 5 (1 completed, 1 in progress, 2 scheduled, 1 overdue)")
    print("  Utility bills: 24 months (Chicago: ~$348k/yr, Dallas: ~$201k/yr)")


async def main():
    """Run seed as standalone script."""
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    from app.core.database import async_session
    async with async_session() as db:
        await seed_demo_data(db)


if __name__ == "__main__":
    asyncio.run(main())
