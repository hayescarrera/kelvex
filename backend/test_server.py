"""
Lightweight test server that runs ColdGrid with SQLite for local testing.
No PostgreSQL, Redis, or Docker required.

Usage: python test_server.py
"""
import os
import sys

# Override settings BEFORE any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/test_coldgrid.db"
os.environ["DATABASE_URL_SYNC"] = "sqlite:////tmp/test_coldgrid.db"
os.environ["REDIS_URL"] = ""
os.environ["SECRET_KEY"] = "test-secret-key-for-dev"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "true"
os.environ["CORS_ORIGINS"] = "http://localhost:5173,http://localhost:3000"

import asyncio
import uvicorn
from app.main import app
from app.core.database import engine, Base
from app.models import *  # noqa: ensure all models are registered

async def init_db():
    """Create all tables in SQLite."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created")

    # Seed a test user and org
    from app.core.database import async_session
    from app.models.user import Organization, User
    from app.core.security import get_password_hash
    import uuid

    async with async_session() as db:
        # Check if org exists
        from sqlalchemy import select
        result = await db.execute(select(Organization).limit(1))
        if result.scalar_one_or_none():
            print("Test data already exists")
            return

        org = Organization(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="ColdGrid Demo",
            slug="coldgrid-demo",
        )
        db.add(org)
        await db.flush()

        user = User(
            id=uuid.UUID("00000000-0000-0000-0000-000000000010"),
            org_id=org.id,
            email="admin@coldgrid.io",
            hashed_password=get_password_hash("admin123"),
            full_name="Admin User",
            role="owner",
        )
        db.add(user)

        # Seed a facility
        from app.models.facility import Facility
        fac = Facility(
            id=uuid.UUID("00000000-0000-0000-0000-000000000100"),
            org_id=org.id,
            name="Main Warehouse",
            city="Chicago",
            state="IL",
            sqft=50000,
            latitude=41.8781,
            longitude=-87.6298,
        )
        db.add(fac)

        # Seed zones
        from app.models.zone import Zone
        for i, (name, ztype, temp) in enumerate([
            ("Freezer A", "frozen", -10.0),
            ("Cooler B", "cooler", 34.0),
            ("Loading Dock", "dock", 45.0),
        ]):
            zone = Zone(
                facility_id=fac.id,
                name=name,
                zone_type=ztype,
                temp_setpoint=temp,
                temp_unit="degF",
                temp_tolerance=3.0,
                temp_alarm_high=temp + 10,
                temp_alarm_low=temp - 10,
                current_temp=temp + (i * 0.5 - 0.5),
                position_x=50 + i * 200,
                position_y=80,
                width=160,
                height=120,
            )
            db.add(zone)

        # Seed compressors
        from app.models.compressor import Compressor
        for i, name in enumerate(["Comp-1 (Mycom)", "Comp-2 (Bitzer)", "Comp-3 (Carrier)"]):
            comp = Compressor(
                facility_id=fac.id,
                name=name,
                compressor_type="screw",
                refrigerant="R-717",
                hp=150 + i * 50,
                state="running" if i < 2 else "idle",
                health_score=95 - i * 10,
            )
            db.add(comp)

        # Seed a second facility
        fac2 = Facility(
            id=uuid.UUID("00000000-0000-0000-0000-000000000200"),
            org_id=org.id,
            name="Distribution Center East",
            city="Newark",
            state="NJ",
            sqft=75000,
            latitude=40.7357,
            longitude=-74.1724,
        )
        db.add(fac2)

        await db.commit()
        print("Seeded test data: org, user (admin@coldgrid.io / admin123), 2 facilities, 3 zones, 3 compressors")


if __name__ == "__main__":
    asyncio.run(init_db())
    print("\nStarting ColdGrid API on http://localhost:8000")
    print("Login: admin@coldgrid.io / admin123\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
