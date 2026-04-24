"""
Edge Agent API — registration, heartbeat, telemetry ingestion, command polling.

Cloud-facing endpoints (for the UI):
  POST   /facilities/{id}/agents               — Register agent
  GET    /facilities/{id}/agents               — List agents
  GET    /facilities/{id}/agents/{agent_id}    — Get agent detail
  PATCH  /facilities/{id}/agents/{agent_id}    — Update agent config
  DELETE /facilities/{id}/agents/{agent_id}    — Decommission agent
  POST   /facilities/{id}/agents/{aid}/scan    — Trigger network scan
  GET    /facilities/{id}/agents/{aid}/discoveries — Get discovered devices
  POST   /facilities/{id}/agents/{aid}/approve-discovery — Auto-create from discovery

Agent-facing endpoints (called by the on-site edge agent):
  POST   /agents/{agent_key}/heartbeat         — Heartbeat + health metrics
  POST   /agents/{agent_key}/telemetry         — Batch telemetry upload
  GET    /agents/{agent_key}/commands           — Poll for pending commands
  POST   /agents/{agent_key}/commands/{cmd_id}/ack  — Acknowledge command
  POST   /agents/{agent_key}/logs              — Upload agent logs
  POST   /agents/{agent_key}/discoveries       — Report discovered devices
"""

import secrets
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.facility import Facility
from app.models.agent import EdgeAgent, AgentLog
from app.models.telemetry import Telemetry
from app.models.compressor import Compressor, CompressorReading
from app.models.device_profile import DeviceProfile, AgentDevice
from app.models.control import CommandQueue
from app.schemas.agent import (
    EdgeAgentCreate, EdgeAgentUpdate, EdgeAgentResponse, EdgeAgentListResponse,
    HeartbeatPayload, TelemetryBatch, AgentLogCreate, AgentLogResponse,
)

router = APIRouter(tags=["agents"])


async def _get_facility(facility_id: UUID, user: User, db: AsyncSession) -> Facility:
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.org_id == user.org_id,
            Facility.deleted_at == None,
        )
    )
    facility = result.scalar_one_or_none()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    return facility


async def _get_agent_by_key(agent_key: str, db: AsyncSession) -> EdgeAgent:
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.agent_key == agent_key, EdgeAgent.enabled == True)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or disabled agent key")
    return agent


# ── Cloud-facing (UI) endpoints ────────────────────

@router.post("/facilities/{facility_id}/agents", response_model=EdgeAgentResponse,
             status_code=status.HTTP_201_CREATED)
async def register_agent(
    facility_id: UUID,
    data: EdgeAgentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new edge agent for a facility."""
    await _get_facility(facility_id, current_user, db)
    agent_key = f"cg_{secrets.token_urlsafe(32)}"
    agent = EdgeAgent(
        facility_id=facility_id,
        agent_key=agent_key,
        **data.model_dump(),
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("/facilities/{facility_id}/agents", response_model=EdgeAgentListResponse)
async def list_agents(
    facility_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all edge agents for a facility."""
    await _get_facility(facility_id, current_user, db)
    total = (await db.execute(
        select(func.count(EdgeAgent.id)).where(EdgeAgent.facility_id == facility_id)
    )).scalar()
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.facility_id == facility_id)
    )
    return EdgeAgentListResponse(agents=result.scalars().all(), total=total)


@router.get("/facilities/{facility_id}/agents/{agent_id}", response_model=EdgeAgentResponse)
async def get_agent(
    facility_id: UUID, agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific edge agent by ID."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/facilities/{facility_id}/agents/{agent_id}", response_model=EdgeAgentResponse)
async def update_agent(
    facility_id: UUID, agent_id: UUID,
    data: EdgeAgentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an edge agent's configuration."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.delete("/facilities/{facility_id}/agents/{agent_id}",
               status_code=status.HTTP_204_NO_CONTENT)
async def decommission_agent(
    facility_id: UUID, agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Decommission an edge agent by disabling it."""
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.enabled = False
    agent.connection_state = "disconnected"
    await db.flush()


# ── Agent-facing endpoints ─────────────────────────

@router.post("/agents/{agent_key}/heartbeat")
async def agent_heartbeat(
    agent_key: str,
    data: HeartbeatPayload,
    db: AsyncSession = Depends(get_db),
):
    """Receive a heartbeat with health metrics from an edge agent."""
    agent = await _get_agent_by_key(agent_key, db)
    now = datetime.now(timezone.utc)
    agent.last_heartbeat = now
    agent.connection_state = "connected"
    if data.cpu_percent is not None:
        agent.cpu_percent = data.cpu_percent
    if data.memory_percent is not None:
        agent.memory_percent = data.memory_percent
    if data.disk_percent is not None:
        agent.disk_percent = data.disk_percent
    if data.uptime_seconds is not None:
        agent.uptime_seconds = data.uptime_seconds
    if data.version:
        agent.version = data.version
    if data.ip_address:
        agent.ip_address = data.ip_address
    await db.flush()

    # Return pending command count
    cmd_count = (await db.execute(
        select(func.count(CommandQueue.id)).where(
            CommandQueue.agent_id == agent.id, CommandQueue.state == "pending"
        )
    )).scalar()
    agent.pending_commands = cmd_count
    await db.flush()

    return {
        "status": "ok",
        "server_time": now.isoformat(),
        "pending_commands": cmd_count,
        "config_version": agent.config_version,
    }


@router.post("/agents/{agent_key}/telemetry")
async def ingest_telemetry(
    agent_key: str,
    data: TelemetryBatch,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a batch of telemetry readings from an edge agent."""
    agent = await _get_agent_by_key(agent_key, db)
    now = datetime.now(timezone.utc)
    inserted = 0

    for reading in data.readings:
        try:
            t = Telemetry(
                time=reading.get("time", now),
                equipment_id=reading["equipment_id"],
                metric_name=reading["metric_name"],
                value=reading["value"],
                unit=reading.get("unit", ""),
                quality=reading.get("quality", 0),
            )
            db.add(t)
            inserted += 1
        except (KeyError, ValueError):
            continue  # skip malformed readings

    agent.last_telemetry_at = now
    await db.flush()
    return {"status": "ok", "inserted": inserted, "total": len(data.readings)}


@router.get("/agents/{agent_key}/commands")
async def poll_commands(
    agent_key: str,
    db: AsyncSession = Depends(get_db),
):
    """Poll for pending commands assigned to an edge agent."""
    agent = await _get_agent_by_key(agent_key, db)
    result = await db.execute(
        select(CommandQueue)
        .where(CommandQueue.agent_id == agent.id, CommandQueue.state == "pending")
        .order_by(CommandQueue.priority, CommandQueue.issued_at)
        .limit(10)
    )
    commands = result.scalars().all()

    # Mark as sent
    now = datetime.now(timezone.utc)
    for cmd in commands:
        cmd.state = "sent"
        cmd.sent_at = now
    await db.flush()

    return {
        "commands": [
            {
                "id": str(cmd.id),
                "command_type": cmd.command_type,
                "target_equipment_id": str(cmd.target_equipment_id) if cmd.target_equipment_id else None,
                "target_zone_id": str(cmd.target_zone_id) if cmd.target_zone_id else None,
                "parameters": cmd.parameters,
                "priority": cmd.priority,
            }
            for cmd in commands
        ]
    }


@router.post("/agents/{agent_key}/commands/{command_id}/ack")
async def acknowledge_command(
    agent_key: str,
    command_id: UUID,
    body: dict,  # {"status": "completed"|"failed", "result": {...}, "error": "..."}
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge completion or failure of a command."""
    agent = await _get_agent_by_key(agent_key, db)
    result = await db.execute(
        select(CommandQueue).where(
            CommandQueue.id == command_id, CommandQueue.agent_id == agent.id
        )
    )
    cmd = result.scalar_one_or_none()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    now = datetime.now(timezone.utc)
    cmd.completed_at = now
    cmd.state = body.get("status", "completed")
    cmd.result = body.get("result")
    cmd.error_message = body.get("error")
    await db.flush()
    return {"status": "ok"}


@router.post("/agents/{agent_key}/logs")
async def upload_logs(
    agent_key: str,
    logs: list[AgentLogCreate],
    db: AsyncSession = Depends(get_db),
):
    """Upload log entries from an edge agent."""
    agent = await _get_agent_by_key(agent_key, db)
    for log_entry in logs:
        log = AgentLog(agent_id=agent.id, **log_entry.model_dump())
        db.add(log)
    await db.flush()
    return {"status": "ok", "count": len(logs)}


# ── Compressor telemetry ingest (from edge agent) ────

# Maps register names (from device profile) → CompressorReading column names
REGISTER_TO_COLUMN = {
    "discharge_pressure": "discharge_pressure_psi",
    "suction_pressure": "suction_pressure_psi",
    "discharge_temp": "discharge_temp_f",
    "suction_temp": "suction_temp_f",
    "oil_temp": "oil_temp_f",
    "bearing_temp": "bearing_temp_f",
    "oil_pressure": "oil_pressure_psi",
    "amp_draw": "amp_draw",
    "kw": "kw",
    "vibration": "vibration_ips",
    "slide_valve_pct": "slide_valve_pct",
    "rpm": "rpm",
    "running": "running",
    "superheat": "superheat_f",
    "subcooling": "subcooling_f",
    "power_factor": "power_factor",
    # Also accept direct column names
    "discharge_pressure_psi": "discharge_pressure_psi",
    "suction_pressure_psi": "suction_pressure_psi",
    "discharge_temp_f": "discharge_temp_f",
    "suction_temp_f": "suction_temp_f",
    "oil_temp_f": "oil_temp_f",
    "bearing_temp_f": "bearing_temp_f",
    "oil_pressure_psi": "oil_pressure_psi",
    "vibration_ips": "vibration_ips",
    "superheat_f": "superheat_f",
    "subcooling_f": "subcooling_f",
}


@router.post("/agents/{agent_key}/compressor-readings")
async def ingest_compressor_readings(
    agent_key: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest compressor readings mapped from register data.

    The edge agent reads Modbus registers, maps them via the device profile,
    and posts structured compressor readings here.

    Payload format:
    {
      "readings": [
        {
          "compressor_id": "uuid",
          "time": "2026-04-16T14:30:00Z",  // optional, defaults to now
          "values": {
            "discharge_pressure": 175.2,
            "suction_pressure": 28.5,
            "oil_temp": 145.0,
            "bearing_temp": 165.0,
            "amp_draw": 220.0,
            "kw": 185.5,
            "vibration": 0.12,
            "slide_valve_pct": 85,
            "rpm": 3550,
            "running": true
          }
        }
      ],
      "device_statuses": [  // optional — agent reports per-device connection state
        {"device_id": "uuid", "state": "online", "poll_count": 1234, "error_count": 2}
      ]
    }
    """
    agent = await _get_agent_by_key(agent_key, db)
    now = datetime.now(timezone.utc)
    inserted = 0
    errors = []

    readings = payload.get("readings", [])
    for r in readings:
        try:
            compressor_id = r["compressor_id"]
            values = r.get("values", {})
            ts = r.get("time", now)
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))

            # Build the CompressorReading from mapped values
            reading_data: dict = {
                "compressor_id": compressor_id,
                "recorded_at": ts,
            }
            for field, val in values.items():
                col = REGISTER_TO_COLUMN.get(field)
                if not col:
                    continue  # skip unmapped fields
                if col == "running":
                    reading_data["running"] = bool(val)
                else:
                    reading_data[col] = float(val) if val is not None else None

            # Compute derived fields if we have the data
            dp = reading_data.get("discharge_pressure_psi")
            sp = reading_data.get("suction_pressure_psi")
            if dp and sp and sp > 0:
                reading_data["compression_ratio"] = round(dp / sp, 2)

            kw_val = reading_data.get("kw")
            svp = reading_data.get("slide_valve_pct")
            if kw_val and svp and svp > 0:
                reading_data["efficiency_pct"] = round((svp / 100) / (kw_val / 100), 3)

            cr = CompressorReading(**reading_data)
            db.add(cr)
            inserted += 1
        except (KeyError, ValueError, TypeError) as e:
            errors.append(str(e))
            continue

    # Update device statuses if provided
    device_statuses = payload.get("device_statuses", [])
    for ds in device_statuses:
        try:
            device_id = ds["device_id"]
            result = await db.execute(
                select(AgentDevice).where(
                    AgentDevice.id == device_id,
                    AgentDevice.agent_id == agent.id,
                )
            )
            device = result.scalar_one_or_none()
            if device:
                device.connection_state = ds.get("state", "unknown")
                device.last_poll_at = now
                if ds.get("state") == "online":
                    device.last_success_at = now
                if "poll_count" in ds:
                    device.poll_count = ds["poll_count"]
                if "error_count" in ds:
                    device.error_count = ds["error_count"]
                if "last_error" in ds:
                    device.last_error = ds["last_error"]
        except (KeyError, ValueError):
            continue

    agent.last_telemetry_at = now
    await db.flush()

    return {
        "status": "ok",
        "inserted": inserted,
        "total": len(readings),
        "errors": errors[:5] if errors else [],
    }


# ── Network Discovery ────────────────────────────────

@router.post("/facilities/{facility_id}/agents/{agent_id}/scan")
async def trigger_network_scan(
    facility_id: UUID,
    agent_id: UUID,
    body: dict | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a network scan on the edge agent.

    The agent will scan the local subnet for Modbus TCP (port 502) and
    BACnet (port 47808) devices. Optional body:
    {
      "subnet": "192.168.1.0/24",   // defaults to agent's own subnet
      "protocols": ["modbus_tcp"],   // defaults to all
      "port_range": [502, 503]       // defaults to standard ports
    }
    """
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    scan_params = {
        "subnet": (body or {}).get("subnet"),  # None = agent auto-detects
        "protocols": (body or {}).get("protocols", ["modbus_tcp", "bacnet_ip"]),
        "port_range": (body or {}).get("port_range", [502, 47808]),
        "identify": True,  # try to read device identification registers
    }

    import uuid as _uuid
    cmd = CommandQueue(
        id=_uuid.uuid4(),
        facility_id=facility_id,
        agent_id=agent.id,
        command_type="network_scan",
        parameters=scan_params,
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
        "message": "Network scan queued — results will appear in discoveries when complete.",
    }


@router.get("/facilities/{facility_id}/agents/{agent_id}/discoveries")
async def get_discoveries(
    facility_id: UUID,
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the agent's discovered devices list.

    Returns devices found during network scans that haven't been provisioned yet.
    """
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get already-provisioned device hosts so we can flag them
    dev_result = await db.execute(
        select(AgentDevice.host).where(AgentDevice.agent_id == agent.id)
    )
    provisioned_hosts = {row[0] for row in dev_result.all()}

    discoveries = agent.discovered_devices or {}
    devices_list = discoveries.get("devices", [])

    # Annotate each discovery with whether it's already provisioned
    for d in devices_list:
        d["already_provisioned"] = d.get("host") in provisioned_hosts

    return {
        "agent_id": str(agent.id),
        "scan_timestamp": discoveries.get("scan_timestamp"),
        "subnet": discoveries.get("subnet"),
        "total_found": len(devices_list),
        "devices": devices_list,
    }


@router.post("/facilities/{facility_id}/agents/{agent_id}/approve-discovery")
async def approve_discovery(
    facility_id: UUID,
    agent_id: UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a discovered device — auto-creates the compressor and agent device.

    Body:
    {
      "host": "192.168.1.50",
      "port": 502,
      "slave_id": 1,
      "profile_id": "uuid",          // matched device profile
      "compressor_name": "Comp #1",  // name for the new compressor
      "tag": "COMP-A1",              // optional
      "manufacturer": "Frick",       // from profile or override
      "model": "Quantum HD",
      "refrigerant": "NH3",
      "hp": 350
    }
    """
    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    host = body.get("host")
    if not host:
        raise HTTPException(status_code=400, detail="host is required")

    # Check not already provisioned
    existing = await db.execute(
        select(AgentDevice).where(
            AgentDevice.agent_id == agent.id,
            AgentDevice.host == host,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Device at {host} is already provisioned")

    # Auto-create the compressor
    comp = Compressor(
        facility_id=facility_id,
        name=body.get("compressor_name", f"Compressor at {host}"),
        tag=body.get("tag"),
        manufacturer=body.get("manufacturer"),
        model=body.get("model"),
        compressor_type=body.get("compressor_type", "screw"),
        refrigerant=body.get("refrigerant", "NH3"),
        hp=body.get("hp"),
        capacity_tons=body.get("capacity_tons"),
    )
    db.add(comp)
    await db.flush()  # get comp.id

    # Auto-create the agent device
    device = AgentDevice(
        agent_id=agent.id,
        profile_id=body.get("profile_id"),
        compressor_id=comp.id,
        name=body.get("compressor_name", f"Controller at {host}"),
        host=host,
        port=body.get("port", 502),
        slave_id=body.get("slave_id", 1),
        poll_interval_sec=body.get("poll_interval_sec", 15),
    )
    db.add(device)

    # Mark as provisioned in discovered_devices
    discoveries = dict(agent.discovered_devices or {})
    devices_list = discoveries.get("devices", [])
    for d in devices_list:
        if d.get("host") == host:
            d["provisioned"] = True
            d["compressor_id"] = str(comp.id)
            d["device_id"] = str(device.id)
    discoveries["devices"] = devices_list
    agent.discovered_devices = discoveries

    await db.flush()

    return {
        "status": "ok",
        "compressor_id": str(comp.id),
        "device_id": str(device.id),
        "message": f"Created compressor '{comp.name}' and linked to controller at {host}",
    }


# ── Agent-facing: report discoveries ─────────────────

@router.post("/agents/{agent_key}/discoveries")
async def report_discoveries(
    agent_key: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Edge agent reports discovered devices after a network scan.

    Payload:
    {
      "scan_timestamp": "2026-04-16T14:30:00Z",
      "subnet": "192.168.1.0/24",
      "devices": [
        {
          "host": "192.168.1.50",
          "port": 502,
          "protocol": "modbus_tcp",
          "slave_id": 1,
          "responding": true,
          "device_info": {
            "vendor": "Johnson Controls",
            "product_code": "Quantum HD",
            "firmware_version": "4.2.1",
            "serial": "FRK-2024-00451"
          },
          "matched_profile": "Frick Quantum HD",
          "matched_profile_id": null,
          "sample_values": {
            "discharge_pressure": 172.5,
            "suction_pressure": 28.1,
            "oil_temp": 142.0
          }
        }
      ]
    }
    """
    agent = await _get_agent_by_key(agent_key, db)

    # Try to match discovered devices to profiles
    prof_result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.is_active == True)
    )
    profiles = list(prof_result.scalars().all())

    devices = payload.get("devices", [])
    for d in devices:
        # Try to auto-match profile based on vendor/product info
        device_info = d.get("device_info", {})
        vendor = (device_info.get("vendor") or "").lower()
        product = (device_info.get("product_code") or "").lower()

        for p in profiles:
            mfr = p.manufacturer.lower()
            model = p.model.lower()
            if mfr in vendor or mfr in product or model in vendor or model in product:
                d["matched_profile"] = p.display_name
                d["matched_profile_id"] = str(p.id)
                d["matched_manufacturer"] = p.manufacturer
                d["matched_refrigerants"] = p.refrigerant_types
                break

    agent.discovered_devices = {
        "scan_timestamp": payload.get("scan_timestamp", datetime.now(timezone.utc).isoformat()),
        "subnet": payload.get("subnet"),
        "devices": devices,
    }
    await db.flush()

    return {
        "status": "ok",
        "devices_received": len(devices),
        "profiles_matched": sum(1 for d in devices if d.get("matched_profile_id")),
    }
