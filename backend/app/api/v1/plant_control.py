"""
Plant Control API — remote control of compressors, zones, and equipment.

This is how operators at coldgrid.io control the physical plant.
Every action is audited, validated against device profile limits,
and queued as a command to the edge agent.

Endpoints:
  POST /facilities/{id}/control/compressor    — Capacity, start/stop, setpoints
  POST /facilities/{id}/control/defrost       — Trigger or schedule defrost
  POST /facilities/{id}/control/demand-response — Activate demand response mode
  POST /facilities/{id}/control/zone-setpoint — Adjust zone temperature setpoint
  GET  /facilities/{id}/control/audit-log     — Control action history
  GET  /facilities/{id}/control/capabilities  — What can be controlled at this site
"""

import uuid as _uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.database import get_db
from app.core.security import get_current_user, get_facility_scoped, require_permission
from app.models.user import User
from app.models.facility import Facility
from app.models.compressor import Compressor
from app.models.zone import Zone
from app.models.agent import EdgeAgent
from app.models.device_profile import DeviceProfile, AgentDevice
from app.models.control import CommandQueue
from app.models.zone_sensor import ControlAuditLog

router = APIRouter(prefix="/facilities/{facility_id}/control", tags=["plant-control"])


async def _get_facility(facility_id, user, db):
    return await get_facility_scoped(facility_id, user, db)


async def _get_agent_for_facility(facility_id, db):
    """Get the first connected agent for this facility."""
    result = await db.execute(
        select(EdgeAgent).where(
            EdgeAgent.facility_id == facility_id,
            EdgeAgent.enabled == True,
        ).order_by(desc(EdgeAgent.last_heartbeat))
    )
    agent = result.scalars().first()
    if not agent:
        raise HTTPException(status_code=409, detail="No active edge agent for this facility")
    return agent


async def _audit(db, facility_id, user_id, action, target_type, target_id, target_name, params, command_id=None):
    log = ControlAuditLog(
        facility_id=facility_id,
        command_id=command_id,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        parameters=params,
        result="queued",
    )
    db.add(log)
    return log


# ── Compressor Control ────────────────────────────────

@router.post("/compressor")
async def control_compressor(
    facility_id: _uuid.UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Issue a control command to a compressor.

    Actions:
      set_capacity   — {"compressor_id": "...", "action": "set_capacity", "percent": 75}
      set_suction    — {"compressor_id": "...", "action": "set_suction", "psi": 28.5}
      start          — {"compressor_id": "...", "action": "start"}
      stop           — {"compressor_id": "...", "action": "stop"}
      write_register — {"compressor_id": "...", "action": "write_register", "register": "capacity_setpoint", "value": 75}
    """
    await _get_facility(facility_id, current_user, db)

    compressor_id = body.get("compressor_id")
    action = body.get("action")
    if not compressor_id or not action:
        raise HTTPException(status_code=400, detail="compressor_id and action required")

    # Authorization before resource-state checks: start/stop is granted more
    # broadly (operators) than setpoint writes.
    needed_perm = "control:start_stop" if action in ("start", "stop") else "control:setpoint"
    if not current_user.has_perm(needed_perm):
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions: requires {needed_perm}",
        )

    agent = await _get_agent_for_facility(facility_id, db)

    # Get compressor
    result = await db.execute(
        select(Compressor).where(Compressor.id == compressor_id, Compressor.facility_id == facility_id)
    )
    comp = result.scalar_one_or_none()
    if not comp:
        raise HTTPException(status_code=404, detail="Compressor not found")

    # Get the agent device for this compressor to find writable registers
    dev_result = await db.execute(
        select(AgentDevice).where(AgentDevice.compressor_id == compressor_id)
    )
    agent_device = dev_result.scalar_one_or_none()

    # Build command parameters
    cmd_params = {"compressor_id": str(compressor_id), "compressor_name": comp.name}

    # Load device profile for validation
    profile = None
    if agent_device and agent_device.profile_id:
        profile = (await db.execute(
            select(DeviceProfile).where(DeviceProfile.id == agent_device.profile_id)
        )).scalar_one_or_none()

    if action == "set_capacity":
        percent = body.get("percent") or body.get("value")
        if percent is None or percent < 0 or percent > 100:
            raise HTTPException(status_code=400, detail="percent/value must be 0-100")
        cmd_params["action"] = "set_capacity"
        cmd_params["percent"] = percent
        # Optional ramp_rate parameter
        ramp_rate = body.get("ramp_rate")
        if ramp_rate is not None:
            cmd_params["ramp_rate"] = ramp_rate
        # Validate against profile limits
        if profile and profile.write_register_map:
            cap_reg = profile.write_register_map.get("capacity_setpoint", {})
            min_val = cap_reg.get("min", 0)
            max_val = cap_reg.get("max", 100)
            if percent < min_val:
                raise HTTPException(status_code=400, detail=f"Minimum capacity for {profile.display_name} is {min_val}%")
            if percent > max_val:
                raise HTTPException(status_code=400, detail=f"Maximum capacity for {profile.display_name} is {max_val}%")
        # Validate ramp_rate against schema if available
        if ramp_rate is not None and profile and profile.control_schemas:
            cap_schema = (profile.control_schemas or {}).get("capacity", {})
            ramp_def = cap_schema.get("params", {}).get("ramp_rate", {})
            ramp_min = ramp_def.get("min", 1)
            ramp_max = ramp_def.get("max", 25)
            if ramp_rate < ramp_min or ramp_rate > ramp_max:
                raise HTTPException(status_code=400, detail=f"Ramp rate must be {ramp_min}-{ramp_max} %/min")

        cmd_params["device_name"] = agent_device.name if agent_device else comp.name

    elif action == "set_suction":
        psi = body.get("psi") or body.get("value")
        if psi is None:
            raise HTTPException(status_code=400, detail="psi/value required")
        # Validate against profile limits
        if profile and profile.write_register_map:
            suc_reg = profile.write_register_map.get("suction_setpoint_psi", {})
            min_val = suc_reg.get("min", 0)
            max_val = suc_reg.get("max", 100)
            if psi < min_val or psi > max_val:
                raise HTTPException(status_code=400, detail=f"Suction setpoint must be {min_val}-{max_val} PSI")
        cmd_params["action"] = "write_register"
        cmd_params["register"] = "suction_setpoint_psi"
        cmd_params["value"] = psi
        cmd_params["device_name"] = agent_device.name if agent_device else comp.name

    elif action in ("start", "stop"):
        cmd_params["action"] = "write_register"
        cmd_params["register"] = "start_stop"
        cmd_params["value"] = 1 if action == "start" else 0
        cmd_params["device_name"] = agent_device.name if agent_device else comp.name

    elif action == "write_register":
        register = body.get("register")
        value = body.get("value")
        if not register or value is None:
            raise HTTPException(status_code=400, detail="register and value required")
        # Validate against write_register_map limits
        if profile and profile.write_register_map:
            reg_def = profile.write_register_map.get(register, {})
            if reg_def:
                min_val = reg_def.get("min")
                max_val = reg_def.get("max")
                if min_val is not None and value < min_val:
                    raise HTTPException(status_code=400, detail=f"{register} minimum is {min_val}")
                if max_val is not None and value > max_val:
                    raise HTTPException(status_code=400, detail=f"{register} maximum is {max_val}")
        cmd_params["action"] = "write_register"
        cmd_params["register"] = register
        cmd_params["value"] = value
        cmd_params["device_name"] = agent_device.name if agent_device else comp.name

    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    # Queue command
    cmd = CommandQueue(
        id=_uuid.uuid4(),
        facility_id=facility_id,
        agent_id=agent.id,
        command_type=cmd_params.get("action", action),
        target_equipment_id=None,
        parameters=cmd_params,
        priority=10,  # high priority for operator actions
        source="user",
        issued_by=current_user.id,
    )
    db.add(cmd)

    await _audit(db, facility_id, current_user.id, action, "compressor", comp.id, comp.name, cmd_params, cmd.id)
    await db.flush()

    return {
        "status": "queued",
        "command_id": str(cmd.id),
        "action": action,
        "compressor": comp.name,
        "message": f"Command '{action}' queued for {comp.name}",
    }


# ── Defrost Control ───────────────────────────────────

@router.post("/defrost")
async def trigger_defrost(
    facility_id: _uuid.UUID,
    body: dict,
    current_user: User = Depends(require_permission("control:defrost")),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger an immediate defrost cycle or update defrost schedule.

    Body:
      {"compressor_id": "...", "action": "trigger",
       "method": "hot_gas", "duration_min": 30, "terminate_temp_f": 45,
       "drip_time_min": 5, "fan_delay_min": 3}
      {"compressor_id": "...", "action": "skip_next"}
      {"compressor_id": "...", "action": "update_schedule", "interval_hours": 8}
    """
    await _get_facility(facility_id, current_user, db)
    agent = await _get_agent_for_facility(facility_id, db)

    compressor_id = body.get("compressor_id")
    action = body.get("action", "trigger")

    result = await db.execute(
        select(Compressor).where(Compressor.id == compressor_id, Compressor.facility_id == facility_id)
    )
    comp = result.scalar_one_or_none()
    if not comp:
        raise HTTPException(status_code=404, detail="Compressor not found")

    cmd_params = {
        "compressor_id": str(compressor_id),
        "compressor_name": comp.name,
        "defrost_action": action,
    }

    if action == "trigger":
        # Accept all defrost parameters from the control schema
        defrost_params = {}
        for key in ("method", "duration_min", "terminate_temp_f", "drip_time_min", "fan_delay_min"):
            if key in body:
                defrost_params[key] = body[key]
        cmd_params["defrost_params"] = defrost_params

        # Validate duration
        duration = defrost_params.get("duration_min")
        if duration is not None and (duration < 1 or duration > 120):
            raise HTTPException(status_code=400, detail="duration_min must be 1-120")

        # Validate terminate temp
        term_temp = defrost_params.get("terminate_temp_f")
        if term_temp is not None and (term_temp < 20 or term_temp > 80):
            raise HTTPException(status_code=400, detail="terminate_temp_f must be 20-80°F")

        # Validate method
        method = defrost_params.get("method")
        if method and method not in ("hot_gas", "electric", "air", "off_cycle"):
            raise HTTPException(status_code=400, detail="method must be hot_gas, electric, air, or off_cycle")

    elif action == "update_schedule":
        cmd_params["interval_hours"] = body.get("interval_hours")
    # skip_next needs no extra params

    cmd = CommandQueue(
        id=_uuid.uuid4(),
        facility_id=facility_id,
        agent_id=agent.id,
        command_type="start_defrost",
        parameters=cmd_params,
        priority=20,
        source="user",
        issued_by=current_user.id,
    )
    db.add(cmd)
    await _audit(db, facility_id, current_user.id, f"defrost_{action}", "compressor", comp.id, comp.name, cmd_params, cmd.id)
    await db.flush()

    return {"status": "queued", "command_id": str(cmd.id), "action": f"defrost_{action}", "compressor": comp.name}


# ── Demand Response ───────────────────────────────────

@router.post("/demand-response")
async def activate_demand_response(
    facility_id: _uuid.UUID,
    body: dict,
    current_user: User = Depends(require_permission("control:demand_response")),
    db: AsyncSession = Depends(get_db),
):
    """
    Activate or deactivate demand response mode for the facility.

    Body:
      {"action": "activate", "target_kw": 500, "duration_minutes": 120}
      {"action": "deactivate"}
      {"action": "precool", "zones": ["<zone_id>"], "target_delta_f": -5, "duration_minutes": 60}

    Demand response works by:
      1. Pre-cooling zones below setpoint (building thermal mass)
      2. Shedding compressor load during peak period
      3. Letting zones coast on thermal mass
      4. Restoring normal operation when DR event ends
    """
    await _get_facility(facility_id, current_user, db)
    agent = await _get_agent_for_facility(facility_id, db)

    # Accept mode-based DR from schema, or legacy action field
    mode = body.get("mode")  # shed, precool, coast (from control schema)
    action = body.get("action")  # legacy: activate, deactivate, precool

    # Map schema mode to action
    if mode and not action:
        action = "activate" if mode in ("shed", "coast") else mode
    if action not in ("activate", "deactivate", "precool"):
        raise HTTPException(status_code=400, detail="action/mode must be activate, deactivate, precool, shed, or coast")

    cmd_params = {
        "dr_action": action,
        "dr_mode": mode or ("shed" if action == "activate" else action),
        "target_kw_reduction": body.get("target_kw_reduction") or body.get("target_kw"),
        "duration_min": body.get("duration_min") or body.get("duration_minutes"),
        "min_capacity_pct": body.get("min_capacity_pct", 25),
    }

    # Precool parameters
    if action == "precool" or mode == "precool":
        cmd_params["zones"] = body.get("zones", [])
        cmd_params["precool_delta_f"] = body.get("precool_delta_f") or body.get("target_delta_f", -5)
        cmd_params["precool_duration_min"] = body.get("precool_duration_min", 60)

    # Coast parameters
    if mode == "coast":
        cmd_params["max_coast_min"] = body.get("max_coast_min", 60)
        cmd_params["temp_ceiling_f"] = body.get("temp_ceiling_f", 5)

    if action == "activate":
        # Get all compressors for this facility and compute staging plan
        comp_result = await db.execute(
            select(Compressor).where(Compressor.facility_id == facility_id, Compressor.state == "running")
        )
        running = list(comp_result.scalars().all())
        cmd_params["compressor_count"] = len(running)
        cmd_params["compressors"] = [{"id": str(c.id), "name": c.name, "hp": c.hp} for c in running]

    cmd = CommandQueue(
        id=_uuid.uuid4(),
        facility_id=facility_id,
        agent_id=agent.id,
        command_type="demand_response",
        parameters=cmd_params,
        priority=5,  # highest priority
        source="user",
        issued_by=current_user.id,
    )
    db.add(cmd)
    await _audit(db, facility_id, current_user.id, f"demand_response_{action}", "facility", facility_id, "Facility", cmd_params, cmd.id)
    await db.flush()

    return {"status": "queued", "command_id": str(cmd.id), "action": f"demand_response_{action}"}


# ── Zone Setpoint ─────────────────────────────────────

@router.post("/zone-setpoint")
async def adjust_zone_setpoint(
    facility_id: _uuid.UUID,
    body: dict,
    current_user: User = Depends(require_permission("control:setpoint")),
    db: AsyncSession = Depends(get_db),
):
    """
    Adjust a zone's temperature setpoint.

    Body:
      {"zone_id": "...", "temp_setpoint": -5, "unit": "F"}
    """
    await _get_facility(facility_id, current_user, db)

    zone_id = body.get("zone_id")
    new_setpoint = body.get("temp_setpoint")
    if zone_id is None or new_setpoint is None:
        raise HTTPException(status_code=400, detail="zone_id and temp_setpoint required")

    result = await db.execute(
        select(Zone).where(Zone.id == zone_id, Zone.facility_id == facility_id)
    )
    zone = result.scalar_one_or_none()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    old_setpoint = zone.temp_setpoint
    zone.temp_setpoint = new_setpoint

    await _audit(
        db, facility_id, current_user.id, "set_zone_temp",
        "zone", zone.id, zone.name,
        {"old_setpoint": old_setpoint, "new_setpoint": new_setpoint},
    )
    await db.flush()

    # If there's an agent, also send as a command so the edge agent can
    # propagate to the local controller
    try:
        agent = await _get_agent_for_facility(facility_id, db)
        cmd = CommandQueue(
            id=_uuid.uuid4(),
            facility_id=facility_id,
            agent_id=agent.id,
            command_type="set_setpoint",
            target_zone_id=zone.id,
            parameters={"zone_id": str(zone.id), "zone_name": zone.name, "temp_setpoint": new_setpoint},
            priority=15,
            source="user",
            issued_by=current_user.id,
        )
        db.add(cmd)
        await db.flush()
    except HTTPException:
        pass  # No agent — setpoint saved to DB but not pushed to edge

    return {
        "status": "ok",
        "zone": zone.name,
        "old_setpoint": old_setpoint,
        "new_setpoint": new_setpoint,
    }


# ── Capabilities ──────────────────────────────────────

@router.get("/capabilities")
async def get_control_capabilities(
    facility_id: _uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns what control actions are available at this facility.

    This lets the frontend know what buttons to show — e.g., if the device
    profile has writable registers for capacity, show the capacity slider.
    """
    await _get_facility(facility_id, current_user, db)

    # Get agents
    agent_result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.facility_id == facility_id, EdgeAgent.enabled == True)
    )
    agents = list(agent_result.scalars().all())
    has_agent = len(agents) > 0
    agent_connected = any(a.connection_state == "connected" for a in agents)

    # Get compressors and their device profiles
    comp_result = await db.execute(
        select(Compressor).where(Compressor.facility_id == facility_id)
    )
    compressors = list(comp_result.scalars().all())

    # Get device profiles with writable registers AND control schemas
    compressor_caps = []
    facility_control_schemas = {}  # merged from all profiles at this site

    for comp in compressors:
        dev_result = await db.execute(
            select(AgentDevice).where(AgentDevice.compressor_id == comp.id)
        )
        device = dev_result.scalar_one_or_none()

        writable = []
        control_schemas = {}
        if device and device.profile_id:
            prof_result = await db.execute(
                select(DeviceProfile).where(DeviceProfile.id == device.profile_id)
            )
            profile = prof_result.scalar_one_or_none()
            if profile:
                if profile.write_register_map:
                    writable = list(profile.write_register_map.keys())
                if profile.control_schemas:
                    control_schemas = profile.control_schemas
                    # Merge facility-level schemas (demand_response, etc.)
                    for key, schema in control_schemas.items():
                        if schema.get("scope") == "facility" and key not in facility_control_schemas:
                            facility_control_schemas[key] = schema

        # If compressor has defrost_config, merge those defaults into the defrost schema
        has_defrost = comp.defrost_config is not None if hasattr(comp, 'defrost_config') else False
        if has_defrost and "defrost" in control_schemas and comp.defrost_config:
            dc = comp.defrost_config
            defrost_params = control_schemas["defrost"].get("params", {})
            # Override defaults from the compressor's actual config
            if "method" in dc and "method" in defrost_params:
                defrost_params["method"]["default"] = dc["method"]
            if "max_duration_min" in dc and "duration_min" in defrost_params:
                defrost_params["duration_min"]["default"] = dc["max_duration_min"]
            if "terminate_temp_f" in dc and "terminate_temp_f" in defrost_params:
                defrost_params["terminate_temp_f"]["default"] = dc["terminate_temp_f"]
            if "fan_delay_min" in dc and "fan_delay_min" in defrost_params:
                defrost_params["fan_delay_min"]["default"] = dc["fan_delay_min"]
            if "drip_time_min" in dc and "drip_time_min" in defrost_params:
                defrost_params["drip_time_min"]["default"] = dc["drip_time_min"]
        elif has_defrost and "defrost" not in control_schemas:
            # Compressor has defrost_config but profile has no defrost schema — create a basic one
            control_schemas["defrost"] = {
                "label": "Defrost Cycle",
                "icon": "snowflake",
                "description": "Initiate evaporator defrost",
                "params": {
                    "method": {
                        "type": "select",
                        "label": "Method",
                        "options": [
                            {"value": "hot_gas", "label": "Hot Gas"},
                            {"value": "electric", "label": "Electric"},
                        ],
                        "default": (comp.defrost_config or {}).get("method", "hot_gas"),
                    },
                    "duration_min": {
                        "type": "number",
                        "label": "Duration",
                        "unit": "min",
                        "min": 5,
                        "max": 90,
                        "step": 5,
                        "default": (comp.defrost_config or {}).get("max_duration_min", 30),
                    },
                    "terminate_temp_f": {
                        "type": "number",
                        "label": "Terminate Temp",
                        "unit": "°F",
                        "min": 32,
                        "max": 65,
                        "step": 1,
                        "default": (comp.defrost_config or {}).get("terminate_temp_f", 45),
                    },
                },
            }

        compressor_caps.append({
            "compressor_id": str(comp.id),
            "name": comp.name,
            "state": comp.state,
            "writable_registers": writable,
            "can_set_capacity": "capacity_setpoint" in writable,
            "can_start_stop": "start_stop" in writable,
            "can_set_suction": "suction_setpoint_psi" in writable,
            "has_defrost_config": has_defrost,
            # Full control schemas for this compressor
            "control_schemas": {k: v for k, v in control_schemas.items() if v.get("scope") != "facility"},
        })

    # Get zones
    zone_result = await db.execute(
        select(Zone).where(Zone.facility_id == facility_id)
    )
    zones = list(zone_result.scalars().all())

    # Zone setpoint schema
    if zones:
        facility_control_schemas["zone_setpoint"] = {
            "label": "Zone Temperature",
            "icon": "thermometer",
            "scope": "facility",
            "description": "Adjust zone temperature setpoints",
            "params": {
                "zone_id": {
                    "type": "select",
                    "label": "Zone",
                    "options": [
                        {"value": str(z.id), "label": z.name} for z in zones
                    ],
                },
                "temp_setpoint": {
                    "type": "number",
                    "label": "Temperature Setpoint",
                    "unit": "°F",
                    "min": -40,
                    "max": 55,
                    "step": 1,
                    "default": 0,
                },
            },
        }

    return {
        "facility_id": str(facility_id),
        "has_agent": has_agent,
        "agent_connected": agent_connected,
        "compressors": compressor_caps,
        "zones": [{"zone_id": str(z.id), "name": z.name, "type": z.zone_type, "current_temp": z.current_temp, "setpoint": z.temp_setpoint} for z in zones],
        "facility_control_schemas": facility_control_schemas,
        "features": {
            "capacity_control": any(c["can_set_capacity"] for c in compressor_caps),
            "start_stop": any(c["can_start_stop"] for c in compressor_caps),
            "suction_setpoint": any(c["can_set_suction"] for c in compressor_caps),
            "defrost_control": any(c.get("has_defrost_config") for c in compressor_caps),
            "demand_response": has_agent and agent_connected,
            "zone_setpoint": len(zones) > 0,
        },
    }


# ── Command Queue Management ──────────────────────────

@router.get("/commands")
async def list_plant_commands(
    facility_id: _uuid.UUID,
    state: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent plant control commands with optional state filter."""
    await _get_facility(facility_id, current_user, db)
    query = select(CommandQueue).where(CommandQueue.facility_id == facility_id)
    if state:
        query = query.where(CommandQueue.state == state)
    result = await db.execute(query.order_by(desc(CommandQueue.issued_at)).limit(limit))
    commands = result.scalars().all()
    return {
        "commands": [
            {
                "id": str(c.id),
                "command_type": c.command_type,
                "parameters": c.parameters,
                "state": c.state,
                "priority": c.priority,
                "source": getattr(c, "source", "user"),
                "issued_at": c.issued_at.isoformat() if c.issued_at else None,
                "completed_at": c.completed_at.isoformat() if c.completed_at else None,
                "error_message": c.error_message,
            }
            for c in commands
        ],
        "total": len(commands),
    }


@router.post("/commands/{command_id}/cancel")
async def cancel_plant_command(
    facility_id: _uuid.UUID,
    command_id: _uuid.UUID,
    current_user: User = Depends(require_permission("control:setpoint")),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a pending or pending_approval command before it reaches the edge agent."""
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(CommandQueue).where(
            CommandQueue.id == command_id,
            CommandQueue.facility_id == facility_id,
        )
    )
    cmd = result.scalar_one_or_none()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    if cmd.state not in ("pending", "pending_approval"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel command in state '{cmd.state}' — only pending or pending_approval commands can be cancelled",
        )

    cmd.state = "cancelled"
    cmd.completed_at = datetime.now(timezone.utc)
    await db.flush()

    await _audit(
        db, facility_id, current_user.id,
        "cancel_command", "command", cmd.id,
        cmd.parameters.get("compressor_name") or cmd.parameters.get("zone_name") or "command",
        {"command_type": cmd.command_type, "cancelled_state": "pending"},
        cmd.id,
    )
    await db.flush()

    return {"status": "cancelled", "command_id": str(cmd.id)}


@router.post("/commands/{command_id}/approve")
async def approve_plant_command(
    facility_id: _uuid.UUID,
    command_id: _uuid.UUID,
    current_user: User = Depends(require_permission("control:setpoint")),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending_approval command, releasing it for execution by the edge agent."""
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(CommandQueue).where(
            CommandQueue.id == command_id,
            CommandQueue.facility_id == facility_id,
        )
    )
    cmd = result.scalar_one_or_none()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    if cmd.state != "pending_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Command is in state '{cmd.state}', not pending_approval",
        )

    cmd.state = "pending"
    await db.flush()

    await _audit(
        db, facility_id, current_user.id,
        "approve_command", "command", cmd.id,
        cmd.parameters.get("compressor_name") or cmd.parameters.get("zone_name") or "command",
        {"command_type": cmd.command_type},
        cmd.id,
    )
    await db.flush()

    return {"status": "approved", "command_id": str(cmd.id)}


# ── Audit Log ─────────────────────────────────────────

@router.get("/audit-log")
async def get_audit_log(
    facility_id: _uuid.UUID,
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent control actions for this facility."""
    await _get_facility(facility_id, current_user, db)

    result = await db.execute(
        select(ControlAuditLog)
        .where(ControlAuditLog.facility_id == facility_id)
        .order_by(desc(ControlAuditLog.created_at))
        .limit(limit)
    )
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": str(l.id),
                "action": l.action,
                "target_type": l.target_type,
                "target_name": l.target_name,
                "parameters": l.parameters,
                "result": l.result,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
        "total": len(logs),
    }
