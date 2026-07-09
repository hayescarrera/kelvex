"""
Device Profile & Agent Device API.

Device profiles (controller templates):
  GET    /device-profiles                             — List all active profiles
  GET    /device-profiles/{id}                        — Get single profile

Agent devices (controllers bound to agents):
  POST   /facilities/{fid}/agents/{aid}/devices       — Add device to agent
  GET    /facilities/{fid}/agents/{aid}/devices       — List agent's devices
  PATCH  /facilities/{fid}/agents/{aid}/devices/{did} — Update device config
  DELETE /facilities/{fid}/agents/{aid}/devices/{did} — Remove device
  GET    /facilities/{fid}/agents/{aid}/config        — Download config bundle
  POST   /facilities/{fid}/agents/{aid}/test          — Test connectivity (queues a ping command)
"""

import uuid as _uuid
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user, get_facility_scoped
from app.models.user import User
from app.models.facility import Facility
from app.models.agent import EdgeAgent
from app.models.device_profile import DeviceProfile, AgentDevice
from app.models.control import CommandQueue
from app.schemas.device_profile import (
    DeviceProfileResponse, DeviceProfileListResponse,
    AgentDeviceCreate, AgentDeviceUpdate, AgentDeviceResponse, AgentDeviceListResponse,
    ConfigBundleResponse,
)

profiles_router = APIRouter(tags=["device-profiles"])
agent_devices_router = APIRouter(tags=["agent-devices"])


# ── Helpers ──────────────────────────────────────────

async def _get_facility(facility_id: UUID, user: User, db: AsyncSession):
    return await get_facility_scoped(facility_id, user, db)


async def _get_agent(agent_id: UUID, facility_id: UUID, db: AsyncSession) -> EdgeAgent:
    result = await db.execute(
        select(EdgeAgent).where(
            EdgeAgent.id == agent_id,
            EdgeAgent.facility_id == facility_id,
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _merge_registers(profile: DeviceProfile | None, overrides: dict | None) -> dict:
    """Merge profile register map with per-device overrides."""
    base = dict(profile.register_map) if profile else {}
    if overrides:
        for key, val in overrides.items():
            if key in base and isinstance(val, dict):
                base[key] = {**base[key], **val}
            else:
                base[key] = val
    return base


# ── Device Profiles ──────────────────────────────────

@profiles_router.get("/device-profiles", response_model=DeviceProfileListResponse)
async def list_profiles(
    manufacturer: str | None = None,
    equipment_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all active device profiles. Optionally filter by manufacturer or equipment type."""
    q = select(DeviceProfile).where(DeviceProfile.is_active == True)
    if manufacturer:
        q = q.where(DeviceProfile.manufacturer == manufacturer)
    if equipment_type:
        q = q.where(DeviceProfile.equipment_type == equipment_type)
    q = q.order_by(DeviceProfile.manufacturer, DeviceProfile.model)

    result = await db.execute(q)
    profiles = result.scalars().all()
    return DeviceProfileListResponse(profiles=profiles, total=len(profiles))


@profiles_router.get("/device-profiles/{profile_id}", response_model=DeviceProfileResponse)
async def get_profile(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single device profile with its full register map."""
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


# ── Agent Devices ────────────────────────────────────

@agent_devices_router.post(
    "/facilities/{facility_id}/agents/{agent_id}/devices",
    response_model=AgentDeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_device(
    facility_id: UUID,
    agent_id: UUID,
    data: AgentDeviceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a controller/device to an edge agent's polling list."""
    await _get_facility(facility_id, current_user, db)
    await _get_agent(agent_id, facility_id, db)

    device = AgentDevice(
        agent_id=agent_id,
        **data.model_dump(),
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device


@agent_devices_router.get(
    "/facilities/{facility_id}/agents/{agent_id}/devices",
    response_model=AgentDeviceListResponse,
)
async def list_devices(
    facility_id: UUID,
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all devices bound to an edge agent."""
    await _get_facility(facility_id, current_user, db)
    await _get_agent(agent_id, facility_id, db)

    result = await db.execute(
        select(AgentDevice).where(AgentDevice.agent_id == agent_id)
    )
    devices = result.scalars().all()
    return AgentDeviceListResponse(devices=devices, total=len(devices))


@agent_devices_router.patch(
    "/facilities/{facility_id}/agents/{agent_id}/devices/{device_id}",
    response_model=AgentDeviceResponse,
)
async def update_device(
    facility_id: UUID,
    agent_id: UUID,
    device_id: UUID,
    data: AgentDeviceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a device's configuration (host, port, overrides, etc.)."""
    await _get_facility(facility_id, current_user, db)
    await _get_agent(agent_id, facility_id, db)

    result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.id == device_id, AgentDevice.agent_id == agent_id
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    await db.flush()
    await db.refresh(device)
    return device


@agent_devices_router.delete(
    "/facilities/{facility_id}/agents/{agent_id}/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_device(
    facility_id: UUID,
    agent_id: UUID,
    device_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a device from the agent's polling list."""
    await _get_facility(facility_id, current_user, db)
    await _get_agent(agent_id, facility_id, db)

    result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.id == device_id, AgentDevice.agent_id == agent_id
        )
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    await db.delete(device)
    await db.flush()


# ── Config Bundle ────────────────────────────────────

@agent_devices_router.get(
    "/facilities/{facility_id}/agents/{agent_id}/config",
    response_model=ConfigBundleResponse,
)
async def get_config_bundle(
    facility_id: UUID,
    agent_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate the complete config bundle for an edge agent.
    The tech downloads this and drops it on the gateway — that's the entire setup.
    """
    await _get_facility(facility_id, current_user, db)
    agent = await _get_agent(agent_id, facility_id, db)

    # Get all devices for this agent
    result = await db.execute(
        select(AgentDevice).where(
            AgentDevice.agent_id == agent_id, AgentDevice.enabled == True
        )
    )
    devices = result.scalars().all()

    # Batch-load profiles
    profile_ids = [d.profile_id for d in devices if d.profile_id]
    profiles_by_id = {}
    if profile_ids:
        prof_result = await db.execute(
            select(DeviceProfile).where(DeviceProfile.id.in_(profile_ids))
        )
        for p in prof_result.scalars().all():
            profiles_by_id[p.id] = p

    # Build device configs
    device_configs = []
    for d in devices:
        profile = profiles_by_id.get(d.profile_id) if d.profile_id else None
        merged_registers = _merge_registers(profile, d.register_overrides)

        device_configs.append({
            "name": d.name,
            "host": d.host,
            "port": d.port,
            "slave_id": d.slave_id,
            "poll_interval_sec": d.poll_interval_sec,
            "protocol": profile.protocol if profile else "modbus_tcp",
            "compressor_id": str(d.compressor_id) if d.compressor_id else None,
            "registers": merged_registers,
        })

    # Derive platform URL from request
    platform_url = str(request.base_url).rstrip("/")

    return ConfigBundleResponse(
        agent_name=agent.name,
        agent_key=agent.agent_key,
        platform_url=platform_url,
        heartbeat_interval_sec=agent.heartbeat_interval_sec,
        devices=device_configs,
    )


# ── Test Connectivity ────────────────────────────────

@agent_devices_router.post(
    "/facilities/{facility_id}/agents/{agent_id}/test",
)
async def test_agent_connectivity(
    facility_id: UUID,
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Queue a 'test_connection' command for the agent.
    The agent will attempt to read one register from each device and report back.
    """
    await _get_facility(facility_id, current_user, db)
    agent = await _get_agent(agent_id, facility_id, db)

    cmd = CommandQueue(
        id=_uuid.uuid4(),
        facility_id=facility_id,
        agent_id=agent.id,
        command_type="test_connection",
        parameters={"mode": "read_one_register_per_device"},
        priority=1,
        source="user",
        issued_by=current_user.id,
    )
    db.add(cmd)
    agent.pending_commands = (agent.pending_commands or 0) + 1
    await db.flush()

    return {
        "status": "queued",
        "command_id": str(cmd.id),
        "message": "Test command queued — agent will report results on next heartbeat.",
    }
