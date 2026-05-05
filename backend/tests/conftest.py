"""
ColdGrid Test Infrastructure
=============================
Provides async SQLite DB, FastAPI test client, and auth fixtures.

Uses httpx.AsyncClient (not TestClient) for async endpoint testing.
All tests run against an in-memory SQLite database — no Postgres required.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, String, Text, TypeDecorator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB as PG_JSONB, ARRAY as PG_ARRAY

from app.core.database import Base, get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.user import User, Organization
from app.models.facility import Facility, Equipment
from app.models.billing import UtilityBill
from app.models.agent import EdgeAgent
from app.models.zone import Zone
from app.models.alert import Alert
from app.models.control import ControlSequence, AutomationRule, Schedule, CommandQueue
from app.models.integration import Integration, IntegrationCredential, RegisterMap
from app.models.telemetry import Telemetry
from app.models.compressor import Compressor, CompressorReading


# ── SQLite compatibility: compile PG types for SQLite ──
# This lets us use the same models without modification.
from sqlalchemy.ext.compiler import compiles

@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "VARCHAR(36)"

@compiles(PG_JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(PG_ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"


# Monkey-patch the UUID bind processor to handle string UUIDs in SQLite.
# On Postgres the asyncpg driver handles this natively; SQLite needs help.
_original_uuid_bind = PG_UUID.bind_processor

def _patched_uuid_bind(self, dialect):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            if isinstance(value, uuid.UUID):
                return str(value)
            return str(value)
        return process
    return _original_uuid_bind(self, dialect)

PG_UUID.bind_processor = _patched_uuid_bind

# Also patch result processor so UUIDs come back as uuid.UUID from SQLite
_original_uuid_result = PG_UUID.result_processor

def _patched_uuid_result(self, dialect, coltype):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            if isinstance(value, uuid.UUID):
                return value
            return uuid.UUID(str(value))
        return process
    return _original_uuid_result(self, dialect, coltype)

PG_UUID.result_processor = _patched_uuid_result

# Patch JSONB for SQLite: store as JSON text, parse on retrieval
_original_jsonb_bind = PG_JSONB.bind_processor

def _patched_jsonb_bind(self, dialect):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            return json.dumps(value)
        return process
    return _original_jsonb_bind(self, dialect)

PG_JSONB.bind_processor = _patched_jsonb_bind

_original_jsonb_result = PG_JSONB.result_processor

def _patched_jsonb_result(self, dialect, coltype):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            if isinstance(value, (dict, list)):
                return value
            return json.loads(value)
        return process
    return _original_jsonb_result(self, dialect, coltype)

PG_JSONB.result_processor = _patched_jsonb_result

# Patch ARRAY for SQLite: store as JSON text, parse on retrieval
_original_array_bind = PG_ARRAY.bind_processor

def _patched_array_bind(self, dialect):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            return json.dumps(value)
        return process
    return _original_array_bind(self, dialect)

PG_ARRAY.bind_processor = _patched_array_bind

_original_array_result = PG_ARRAY.result_processor

def _patched_array_result(self, dialect, coltype):
    if dialect.name == "sqlite":
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return value
            return json.loads(value)
        return process
    return _original_array_result(self, dialect, coltype)

PG_ARRAY.result_processor = _patched_array_result


# ── Async SQLite engine for tests ─────────────────────
# Use a named shared-cache memory database so all connections see the same data,
# even when pytest-asyncio creates new event loops between fixtures and test bodies.
TEST_DATABASE_URL = "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    json_serializer=json.dumps,
    json_deserializer=json.loads,
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Event listener to enable SQLite FK support ────────
@event.listens_for(test_engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ── Database setup/teardown ───────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Override get_db dependency ────────────────────────
async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


# ── Test client ───────────────────────────────────────
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Seed data fixtures ───────────────────────────────
@pytest_asyncio.fixture
async def org() -> Organization:
    """Create a test organization."""
    async with TestSessionLocal() as db:
        o = Organization(
            id=uuid.uuid4(),
            name="Test Org",
            slug="test-org",
            plan_tier="pro",
        )
        db.add(o)
        await db.commit()
        await db.refresh(o)
        return o


@pytest_asyncio.fixture
async def user(org: Organization) -> User:
    """Create a test user with hashed password."""
    async with TestSessionLocal() as db:
        u = User(
            id=uuid.uuid4(),
            email="test@coldgrid.io",
            hashed_password=get_password_hash("TestPass123!"),
            full_name="Test User",
            org_id=org.id,
            role="owner",
            is_admin=True,
            is_active=True,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


@pytest_asyncio.fixture
async def user_token(user: User) -> str:
    """JWT access token for the test user."""
    return create_access_token(data={"sub": str(user.id), "org": str(user.org_id)})


@pytest_asyncio.fixture
async def auth_headers(user_token: str) -> dict:
    """Authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest_asyncio.fixture
async def facility(user: User) -> Facility:
    """Create a test facility."""
    async with TestSessionLocal() as db:
        f = Facility(
            id=uuid.uuid4(),
            org_id=user.org_id,
            name="Warehouse Alpha",
            city="Chicago",
            state="IL",
            sqft=50000,
            zone_types=["freezer", "cooler", "dock"],
        )
        db.add(f)
        await db.commit()
        await db.refresh(f)
        return f


@pytest_asyncio.fixture
async def equipment(facility: Facility) -> Equipment:
    """Create test equipment."""
    async with TestSessionLocal() as db:
        eq = Equipment(
            id=uuid.uuid4(),
            facility_id=facility.id,
            name="Compressor A1",
            equipment_type="compressor",
            manufacturer="Bitzer",
            model="CSH 8573",
        )
        db.add(eq)
        await db.commit()
        await db.refresh(eq)
        return eq


@pytest_asyncio.fixture
async def zone(facility: Facility) -> Zone:
    """Create a test zone."""
    async with TestSessionLocal() as db:
        z = Zone(
            id=uuid.uuid4(),
            facility_id=facility.id,
            name="Freezer 1",
            zone_type="freezer",
            temp_setpoint=-10.0,
            temp_unit="F",
        )
        db.add(z)
        await db.commit()
        await db.refresh(z)
        return z


@pytest_asyncio.fixture
async def bill(facility: Facility) -> UtilityBill:
    """Create a test utility bill."""
    from datetime import date
    async with TestSessionLocal() as db:
        b = UtilityBill(
            id=uuid.uuid4(),
            facility_id=facility.id,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            total_kwh=125000.0,
            total_cost=18500.00,
            peak_demand_kw=450.0,
            demand_charge=5200.00,
            energy_charge=13300.00,
        )
        db.add(b)
        await db.commit()
        await db.refresh(b)
        return b


@pytest_asyncio.fixture
async def agent(facility: Facility) -> EdgeAgent:
    """Create a test edge agent."""
    async with TestSessionLocal() as db:
        a = EdgeAgent(
            id=uuid.uuid4(),
            facility_id=facility.id,
            name="Agent Pi-01",
            agent_key="cg_test_agent_key_12345",
            hardware_type="raspberry_pi_4",
            enabled=True,
            connection_state="connected",
        )
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return a


# ── Second org/user for isolation tests ───────────────
@pytest_asyncio.fixture
async def other_org() -> Organization:
    async with TestSessionLocal() as db:
        o = Organization(id=uuid.uuid4(), name="Other Org", slug="other-org")
        db.add(o)
        await db.commit()
        await db.refresh(o)
        return o


@pytest_asyncio.fixture
async def other_user(other_org: Organization) -> User:
    async with TestSessionLocal() as db:
        u = User(
            id=uuid.uuid4(),
            email="other@example.com",
            hashed_password=get_password_hash("OtherPass123!"),
            full_name="Other User",
            org_id=other_org.id,
            role="owner",
            is_admin=False,
            is_active=True,
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


@pytest_asyncio.fixture
async def other_auth_headers(other_user: User) -> dict:
    token = create_access_token(data={"sub": str(other_user.id), "org": str(other_user.org_id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def compressor(facility: Facility) -> Compressor:
    """Create a test compressor with alarm thresholds set."""
    async with TestSessionLocal() as db:
        c = Compressor(
            id=uuid.uuid4(),
            facility_id=facility.id,
            name="Test Comp A1",
            tag="COMP-A1",
            manufacturer="Frick",
            model="RWF II 480",
            state="running",
            alarm_discharge_psi_high=220.0,
            alarm_suction_psi_low=10.0,
            alarm_oil_temp_high=170.0,
            alarm_bearing_temp_high=190.0,
            alarm_vibration_high=0.28,
            alarm_amp_draw_high=260.0,
        )
        db.add(c)
        await db.commit()
        await db.refresh(c)
        return c
