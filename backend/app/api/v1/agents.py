"""
Edge Agent API — registration, heartbeat, telemetry ingestion, command polling.

Cloud-facing endpoints (for the UI):
  POST   /facilities/{id}/agents               — Register agent
  GET    /facilities/{id}/agents               — List agents
  GET    /facilities/{id}/agents/{agent_id}    — Get agent detail
  PATCH  /facilities/{id}/agents/{agent_id}    — Update agent config
  DELETE /facilities/{id}/agents/{agent_id}    — Decommission agent
  GET    /facilities/{id}/agents/{aid}/config  — Download agent.yaml config
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
from app.core.security import get_current_user, get_facility_scoped, require_permission
from app.models.user import User
from app.models.facility import Facility, Equipment
from app.models.agent import EdgeAgent, AgentLog
from app.models.telemetry import Telemetry
from app.models.compressor import Compressor, CompressorReading
from app.models.device_profile import DeviceProfile, AgentDevice
from app.models.control import CommandQueue
from app.models.zone import Zone
from app.models.zone_sensor import ZoneSensor, ZoneReading
from app.models.alert import Alert
from app.schemas.agent import (
    EdgeAgentCreate, EdgeAgentUpdate, EdgeAgentResponse, EdgeAgentListResponse,
    HeartbeatPayload, TelemetryBatch, AgentLogCreate, AgentLogResponse,
)

router = APIRouter(tags=["agents"])


async def _get_facility(facility_id: UUID, user: User, db: AsyncSession):
    return await get_facility_scoped(facility_id, user, db)


async def _get_agent_by_key(agent_key: str, db: AsyncSession) -> EdgeAgent:
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.agent_key == agent_key, EdgeAgent.enabled == True)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid or disabled agent key")
    return agent


async def _insert_ignore_conflicts(db: AsyncSession, model, rows: list[dict]) -> int:
    """Bulk insert that silently drops rows violating a unique constraint.

    Agents retry batches after network failures, so re-delivery of
    already-stored readings must be a no-op, not an error. Returns the
    number of rows actually inserted.
    """
    if not rows:
        return 0
    # Multi-row VALUES requires identical keys in every dict; readings vary
    # by which registers each device reports, so pad the gaps with None.
    all_keys = set().union(*(r.keys() for r in rows))
    rows = [{k: r.get(k) for k in all_keys} for r in rows]
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _insert
    else:  # sqlite (tests)
        from sqlalchemy.dialects.sqlite import insert as _insert
    stmt = _insert(model).values(rows).on_conflict_do_nothing()
    result = await db.execute(stmt)
    return result.rowcount if result.rowcount and result.rowcount > 0 else 0


# ── Cloud-facing (UI) endpoints ────────────────────

@router.post("/facilities/{facility_id}/agents", response_model=EdgeAgentResponse,
             status_code=status.HTTP_201_CREATED)
async def register_agent(
    facility_id: UUID,
    data: EdgeAgentCreate,
    current_user: User = Depends(require_permission("agents:manage")),
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
    current_user: User = Depends(require_permission("agents:manage")),
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
    current_user: User = Depends(require_permission("agents:manage")),
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


@router.get("/facilities/{facility_id}/agents/{agent_id}/config")
async def get_agent_config(
    facility_id: UUID,
    agent_id: UUID,
    current_user: User = Depends(require_permission("agents:manage")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a ready-to-deploy agent.yaml config for this agent.

    The frontend uses this to generate a downloadable config file the
    installer drops onto the gateway device at /etc/kelvex/agent.yaml.
    """
    from app.core.config import settings

    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    devices_result = await db.execute(
        select(AgentDevice, DeviceProfile)
        .outerjoin(DeviceProfile, AgentDevice.profile_id == DeviceProfile.id)
        .where(AgentDevice.agent_id == agent_id, AgentDevice.enabled == True)
        .order_by(AgentDevice.created_at)
    )
    rows = devices_result.all()

    devices = []
    for device, profile in rows:
        registers: dict = {}
        if profile and profile.register_map:
            registers.update(profile.register_map)
        if device.register_overrides:
            registers.update(device.register_overrides)

        write_registers: dict = {}
        if profile and profile.write_register_map:
            write_registers.update(profile.write_register_map)

        entry = {
            "name": device.name,
            "host": device.host,
            "port": device.port,
            "slave_id": device.slave_id,
            "protocol": "modbus_tcp",
            "poll_interval_sec": device.poll_interval_sec,
            "compressor_id": str(device.compressor_id) if device.compressor_id else "",
            "registers": registers,
        }
        if write_registers:
            entry["write_registers"] = write_registers
        devices.append(entry)

    platform_url = getattr(settings, "PLATFORM_URL", None) or "https://app.kelvex.io"

    # Build zone sensor configs for sensors that have Modbus register info
    zone_sensor_result = await db.execute(
        select(ZoneSensor, Zone, AgentDevice)
        .join(Zone, ZoneSensor.zone_id == Zone.id)
        .outerjoin(AgentDevice, ZoneSensor.agent_device_id == AgentDevice.id)
        .where(Zone.facility_id == facility_id, ZoneSensor.enabled == True)
    )
    zone_sensors = []
    for sensor, zone, agent_device in zone_sensor_result.all():
        meta = sensor.metadata_ or {}
        if "register_address" not in meta:
            continue  # no register config — sensor not yet wired to Modbus
        host = meta.get("host") or (agent_device.host if agent_device else None)
        port = meta.get("port") or (agent_device.port if agent_device else 502)
        slave_id = meta.get("slave_id") or (agent_device.slave_id if agent_device else 1)
        if not host:
            continue
        zone_sensors.append({
            "sensor_id": str(sensor.id),
            "zone_id": str(sensor.zone_id),
            "name": sensor.name,
            "sensor_type": sensor.sensor_type,
            "unit": sensor.unit or "F",
            "host": host,
            "port": port,
            "slave_id": slave_id,
            "register_address": meta["register_address"],
            "register_type": meta.get("register_type", "holding"),
            "data_type": meta.get("data_type", "uint16"),
            "scale": meta.get("scale", 1.0),
            "offset": meta.get("offset", 0.0),
            "poll_interval_sec": sensor.poll_interval_sec,
        })

    return {
        "agent_name": agent.name,
        "agent_key": agent.agent_key,
        "platform_url": platform_url,
        "heartbeat_interval_sec": 30,
        "devices": devices,
        "zone_sensors": zone_sensors,
    }


# ── Setup script generation ───────────────────────
#
# Flow:
#   1. UI calls POST .../setup-token  → gets a 60-min one-time token
#   2. UI shows:  curl -fsSL https://api.kelvex.io/v1/setup/{token} | sudo bash
#   3. Tech pastes that into the Pi terminal — no file transfer needed
#   4. GET /setup/{token}  is public (no JWT) but validates the token via Redis

SETUP_TOKEN_TTL = 3600  # 60 minutes


@router.post("/facilities/{facility_id}/agents/{agent_id}/setup-token")
async def create_setup_token(
    facility_id: UUID,
    agent_id: UUID,
    current_user: User = Depends(require_permission("agents:manage")),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a short-lived (60 min) token for the setup script.

    Returns the full `curl | sudo bash` command the tech pastes into
    the terminal on the gateway device. No file download or SCP needed.
    """
    import secrets as _secrets
    from app.services.cache import get_redis
    from app.core.config import settings

    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    token = _secrets.token_urlsafe(32)
    redis = await get_redis()
    if not redis:
        # Without Redis the token can't be stored, so the install command
        # would 404 — fail loudly instead of handing out a dead link.
        raise HTTPException(
            status_code=503,
            detail="Setup tokens are temporarily unavailable. Try again shortly.",
        )
    import json as _json
    await redis.set(
        f"setup:{token}",
        _json.dumps({"facility_id": str(facility_id), "agent_id": str(agent_id)}),
        ex=SETUP_TOKEN_TTL,
    )

    api_url = getattr(settings, "PLATFORM_URL", None) or "https://api.kelvex.io"
    # Strip trailing /api/v1 if present — we want the root
    api_url = api_url.rstrip("/")
    script_url = f"{api_url}/api/v1/setup/{token}"

    return {
        "token": token,
        "expires_in": SETUP_TOKEN_TTL,
        "install_command": f"curl -fsSL '{script_url}' | sudo bash",
        "script_url": script_url,
    }


@router.get("/setup/{token}", include_in_schema=False)
async def get_setup_script_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint — returns the setup script for a valid token.
    No JWT required; the token itself is the credential (60-min TTL).
    """
    from fastapi.responses import Response
    from app.services.cache import get_redis
    import json as _json

    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Setup service unavailable")

    raw = await redis.get(f"setup:{token}")
    if not raw:
        raise HTTPException(status_code=404, detail="Token expired or invalid")

    data = _json.loads(raw)
    facility_id = UUID(data["facility_id"])
    agent_id = UUID(data["agent_id"])

    # Fetch agent directly (no user auth — token is the credential)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Build config bundle (reuse the core logic, no user scoping needed)
    script = await _build_setup_script(facility_id, agent_id, agent, db)

    # Consume token — one use only
    await redis.delete(f"setup:{token}")

    filename = f"kelvex-setup-{agent.name.replace(' ', '-').lower()}.sh"
    return Response(
        content=script,
        media_type="text/plain",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


async def _build_setup_script(facility_id: UUID, agent_id: UUID, agent: EdgeAgent, db: AsyncSession) -> str:
    """Build the full setup shell script with config embedded."""
    import yaml as _yaml
    from app.core.config import settings

    # Reuse config bundle query
    devices_result = await db.execute(
        select(AgentDevice, DeviceProfile)
        .outerjoin(DeviceProfile, AgentDevice.profile_id == DeviceProfile.id)
        .where(AgentDevice.agent_id == agent_id, AgentDevice.enabled == True)
        .order_by(AgentDevice.created_at)
    )
    devices = []
    for device, profile in devices_result.all():
        registers: dict = {}
        if profile and profile.register_map:
            registers.update(profile.register_map)
        if device.register_overrides:
            registers.update(device.register_overrides)
        entry: dict = {
            "name": device.name,
            "host": device.host,
            "port": device.port,
            "slave_id": device.slave_id,
            "protocol": "modbus_tcp",
            "poll_interval_sec": device.poll_interval_sec,
            "compressor_id": str(device.compressor_id) if device.compressor_id else "",
            "registers": registers,
        }
        devices.append(entry)

    platform_url = getattr(settings, "PLATFORM_URL", None) or "https://app.kelvex.io"

    yaml_cfg: dict = {
        "agent": {"name": agent.name, "key": agent.agent_key},
        "platform": {"url": platform_url, "heartbeat_interval_sec": 30},
        "local": {
            "web_port": 8080,
            "web_enabled": True,
            "buffer_path": "/var/lib/kelvex/buffer.db",
            "buffer_max_mb": 500,
        },
        "devices": devices if devices else [],
    }

    yaml_str = _yaml.dump(yaml_cfg, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return f"""#!/usr/bin/env bash
# Kelvex Edge Agent — Setup Script
# Agent: {agent.name}
# This script installs the Kelvex edge agent on a Linux gateway device.
# Supports: Raspberry Pi (ARM64/ARMv7), Intel NUC / any x86-64 Linux
#
# Run with: sudo bash <(curl -fsSL '<this_url>')
set -euo pipefail

INSTALL_DIR=/usr/local/bin
CONFIG_DIR=/etc/kelvex
DATA_DIR=/var/lib/kelvex
SERVICE=kelvex-agent
BASE=https://get.kelvex.io/agent

echo ""
echo "  Kelvex Edge Agent — {agent.name}"
echo "  ──────────────────────────────────────────────"
echo ""

[ "$EUID" -ne 0 ] && {{ echo "Error: run with sudo"; exit 1; }}

ARCH=$(uname -m)
case "$ARCH" in
  x86_64)        BIN="$BASE/kelvex-agent-linux-amd64"  ;;
  aarch64|arm64) BIN="$BASE/kelvex-agent-linux-arm64"  ;;
  armv7l)        BIN="$BASE/kelvex-agent-linux-armv7"  ;;
  *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

echo "  [1/4] Downloading agent ($ARCH)..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$DATA_DIR"
curl -fsSL --progress-bar "$BIN" -o "$INSTALL_DIR/$SERVICE"
chmod +x "$INSTALL_DIR/$SERVICE"

echo "  [2/4] Writing config..."
cat > "$CONFIG_DIR/agent.yaml" << 'EOF'
{yaml_str}
EOF

echo "  [3/4] Installing systemd service..."
cat > /etc/systemd/system/$SERVICE.service << 'EOF'
[Unit]
Description=Kelvex Edge Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/kelvex-agent -config /etc/kelvex/agent.yaml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --quiet $SERVICE
systemctl restart $SERVICE

echo "  [4/4] Checking status..."
sleep 2
STATUS=$(systemctl is-active $SERVICE 2>/dev/null || echo "unknown")

echo ""
if [ "$STATUS" = "active" ]; then
  echo "  ✓  Agent is running"
else
  echo "  ⚠  Agent status: $STATUS"
  echo "     Check logs: journalctl -u $SERVICE -n 50 --no-pager"
fi

echo ""
echo "  Platform:  {platform_url}"
echo "  Logs:      journalctl -u $SERVICE -f"
echo "  Config:    nano $CONFIG_DIR/agent.yaml"
echo ""
"""


@router.get("/facilities/{facility_id}/agents/{agent_id}/setup-script")
async def get_setup_script(
    facility_id: UUID,
    agent_id: UUID,
    current_user: User = Depends(require_permission("agents:manage")),
    db: AsyncSession = Depends(get_db),
):
    """
    Direct download of the setup script (requires JWT — for browser download).
    Use POST .../setup-token + the returned install_command for terminal use.
    """
    from fastapi.responses import Response

    await _get_facility(facility_id, current_user, db)
    result = await db.execute(
        select(EdgeAgent).where(EdgeAgent.id == agent_id, EdgeAgent.facility_id == facility_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    script = await _build_setup_script(facility_id, agent_id, agent, db)
    filename = f"kelvex-setup-{agent.name.replace(' ', '-').lower()}.sh"
    return Response(
        content=script,
        media_type="text/x-sh",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

    # Build YAML inline
    yaml_cfg = {
        "agent": {"name": cfg_response["agent_name"], "key": cfg_response["agent_key"]},
        "platform": {
            "url": cfg_response["platform_url"],
            "heartbeat_interval_sec": cfg_response["heartbeat_interval_sec"],
        },
        "local": {
            "web_port": 8080,
            "web_enabled": True,
            "buffer_path": "/var/lib/kelvex/buffer.db",
            "buffer_max_mb": 500,
        },
        "devices": cfg_response.get("devices", []),
    }
    if cfg_response.get("zone_sensors"):
        yaml_cfg["zone_sensors"] = cfg_response["zone_sensors"]

    yaml_str = _yaml.dump(yaml_cfg, default_flow_style=False, sort_keys=False, allow_unicode=True)
    agent_name = cfg_response["agent_name"].replace(" ", "-").lower()

    script = f"""#!/usr/bin/env bash
# Kelvex Edge Agent — Setup Script
# Agent:   {cfg_response["agent_name"]}
# Facility: {facility_id}
# Generated: $(date -u)
#
# Usage: sudo bash kelvex-setup.sh
set -euo pipefail

INSTALL_DIR=/usr/local/bin
CONFIG_DIR=/etc/kelvex
DATA_DIR=/var/lib/kelvex
SERVICE_NAME=kelvex-agent
BASE_URL=https://get.kelvex.io/agent

echo "==> Kelvex Edge Agent Installer"
echo ""

if [ "$EUID" -ne 0 ]; then
  echo "Error: please run with sudo"
  exit 1
fi

# Detect architecture
ARCH=$(uname -m)
case "$ARCH" in
  x86_64)          BINARY="kelvex-agent-linux-amd64" ;;
  aarch64|arm64)   BINARY="kelvex-agent-linux-arm64" ;;
  armv7l)          BINARY="kelvex-agent-linux-armv7" ;;
  *)
    echo "Unsupported architecture: $ARCH"
    exit 1
    ;;
esac

echo "    Architecture: $ARCH ($BINARY)"
echo ""

# Create directories
mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$INSTALL_DIR"

# Download binary
echo "==> Downloading agent binary..."
curl -fsSL --progress-bar "$BASE_URL/$BINARY" -o "$INSTALL_DIR/$SERVICE_NAME"
chmod +x "$INSTALL_DIR/$SERVICE_NAME"
echo "    Installed to $INSTALL_DIR/$SERVICE_NAME"
echo ""

# Write config
echo "==> Writing configuration..."
cat > "$CONFIG_DIR/agent.yaml" << 'KELVEX_YAML'
{yaml_str}
KELVEX_YAML
echo "    Config written to $CONFIG_DIR/agent.yaml"
echo ""

# Install systemd service
echo "==> Installing systemd service..."
cat > /etc/systemd/system/$SERVICE_NAME.service << 'KELVEX_SERVICE'
[Unit]
Description=Kelvex Edge Agent
Documentation=https://docs.kelvex.io/edge-agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={INSTALL_DIR}/{SERVICE_NAME} -config {CONFIG_DIR}/agent.yaml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kelvex-agent
User=root
WorkingDirectory={DATA_DIR}
# Give the agent time to flush its buffer on shutdown
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
KELVEX_SERVICE

systemctl daemon-reload
systemctl enable --quiet $SERVICE_NAME
systemctl restart $SERVICE_NAME
echo "    Service enabled and started"
echo ""

# Wait a moment and check status
sleep 2
STATUS=$(systemctl is-active $SERVICE_NAME 2>/dev/null || echo "unknown")

if [ "$STATUS" = "active" ]; then
  echo "==> Agent is running"
else
  echo "==> Warning: agent status is '$STATUS'"
  echo "    Check logs: journalctl -u $SERVICE_NAME -n 50"
fi

echo ""
echo "    Agent name:  {cfg_response["agent_name"]}"
echo "    Platform:    {cfg_response["platform_url"]}"
echo ""
echo "    Useful commands:"
echo "      Status:  systemctl status $SERVICE_NAME"
echo "      Logs:    journalctl -u $SERVICE_NAME -f"
echo "      Restart: systemctl restart $SERVICE_NAME"
echo "      Config:  nano $CONFIG_DIR/agent.yaml"
"""

    filename = f"kelvex-setup-{agent_name}.sh"
    return Response(
        content=script,
        media_type="text/x-sh",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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

    # Resolve any active connectivity alert if the agent is reconnecting
    if agent.connection_state in ("stale", "disconnected"):
        offline_alert_result = await db.execute(
            select(Alert).where(
                Alert.agent_id == agent.id,
                Alert.alert_type == "agent_offline",
                Alert.state.in_(["active", "acknowledged"]),
            )
        )
        offline_alert = offline_alert_result.scalar_one_or_none()
        if offline_alert:
            offline_alert.state = "resolved"
            offline_alert.resolved_at = now
            offline_alert.resolution_note = "Agent reconnected"

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

    # Cache valid equipment IDs for this agent's facility to prevent cross-org writes
    valid_equipment_result = await db.execute(
        select(Equipment.id).where(Equipment.facility_id == agent.facility_id)
    )
    valid_equipment_ids = {str(row[0]) for row in valid_equipment_result.all()}

    rows: list[dict] = []
    seen_keys: set = set()
    for reading in data.readings:
        try:
            eq_id = str(reading["equipment_id"])
            if eq_id not in valid_equipment_ids:
                continue  # silently drop — agent may have stale config
            ts = reading.get("time", now)
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            key = (ts, eq_id, reading["metric_name"])
            if key in seen_keys:
                continue  # in-batch duplicate
            seen_keys.add(key)
            rows.append({
                "time": ts,
                "equipment_id": reading["equipment_id"],
                "metric_name": reading["metric_name"],
                "value": reading["value"],
                "unit": reading.get("unit", ""),
                "quality": reading.get("quality", 0),
            })
        except (KeyError, ValueError):
            continue  # skip malformed readings

    inserted = await _insert_ignore_conflicts(db, Telemetry, rows)

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

    ack_state = body.get("status", "completed")
    if ack_state not in ("completed", "failed"):
        raise HTTPException(
            status_code=400,
            detail="status must be 'completed' or 'failed'",
        )

    now = datetime.now(timezone.utc)
    cmd.completed_at = now
    cmd.state = ack_state
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
    errors = []

    # Load valid compressor IDs for this agent's facility to prevent cross-org writes
    valid_compressors_result = await db.execute(
        select(Compressor.id).where(Compressor.facility_id == agent.facility_id)
    )
    valid_compressor_ids = {str(row[0]) for row in valid_compressors_result.all()}

    readings = payload.get("readings", [])
    rows: list[dict] = []
    seen_keys: set = set()
    for r in readings:
        try:
            compressor_id = r["compressor_id"]
            if str(compressor_id) not in valid_compressor_ids:
                errors.append(f"compressor {compressor_id} not in agent facility")
                continue
            values = r.get("values", {})
            ts = r.get("time", now)
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))

            key = (str(compressor_id), ts)
            if key in seen_keys:
                continue  # in-batch duplicate
            seen_keys.add(key)

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

            rows.append(reading_data)
        except (KeyError, ValueError, TypeError) as e:
            errors.append(str(e))
            continue

    inserted = await _insert_ignore_conflicts(db, CompressorReading, rows)

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


# ── Zone sensor telemetry ingest (from edge agent) ──

@router.post("/agents/{agent_key}/zone-readings")
async def ingest_zone_readings(
    agent_key: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest zone sensor readings from an edge agent.

    Payload format:
    {
      "readings": [
        {
          "sensor_id": "uuid",
          "zone_id": "uuid",
          "value": 38.5,
          "unit": "F",
          "quality": 0,   // 0=good, 1=uncertain, 2=bad
          "time": "2026-06-23T10:00:00Z"
        }
      ]
    }
    """
    agent = await _get_agent_by_key(agent_key, db)
    now = datetime.now(timezone.utc)
    errors = []

    # Load all enabled zone sensors for this agent's facility
    sensor_result = await db.execute(
        select(ZoneSensor)
        .join(Zone, ZoneSensor.zone_id == Zone.id)
        .where(Zone.facility_id == agent.facility_id, ZoneSensor.enabled == True)
    )
    sensors_by_id = {str(s.id): s for s in sensor_result.scalars().all()}

    # Cache zones for bulk state update
    zone_ids_to_refresh: set = set()

    readings = payload.get("readings", [])
    rows: list[dict] = []
    seen_keys: set = set()
    for r in readings:
        try:
            sensor_id = str(r["sensor_id"])
            sensor = sensors_by_id.get(sensor_id)
            if not sensor:
                errors.append(f"sensor {sensor_id} not in facility")
                continue

            value = float(r["value"])
            ts = r.get("time", now)
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            unit = r.get("unit") or sensor.unit
            quality = int(r.get("quality", 0))

            key = (sensor_id, ts)
            if key not in seen_keys:
                seen_keys.add(key)
                rows.append(dict(
                    sensor_id=sensor.id,
                    zone_id=sensor.zone_id,
                    value=value,
                    unit=unit,
                    quality=quality,
                    recorded_at=ts,
                ))

            # Determine new sensor state based on thresholds
            new_state = "normal"
            if quality == 2:
                new_state = "bad_quality"
            elif sensor.alarm_high is not None and value >= sensor.alarm_high:
                new_state = "alarm_high"
            elif sensor.alarm_low is not None and value <= sensor.alarm_low:
                new_state = "alarm_low"
            elif sensor.warn_high is not None and value >= sensor.warn_high:
                new_state = "warning_high"
            elif sensor.warn_low is not None and value <= sensor.warn_low:
                new_state = "warning_low"

            old_state = sensor.current_state
            sensor.current_value = value
            sensor.current_state = new_state
            sensor.last_reading_at = ts
            zone_ids_to_refresh.add(sensor.zone_id)

            # Fire a zone alert if crossing into alarm/warning
            if new_state not in ("normal", "bad_quality") and old_state in ("normal", None, ""):
                await _maybe_fire_zone_alert(db, agent.facility_id, sensor, value, new_state, now)

        except (KeyError, ValueError, TypeError) as e:
            errors.append(str(e))
            continue

    inserted = await _insert_ignore_conflicts(db, ZoneReading, rows)

    # Update zone-level current values from freshest sensor reading per type
    for zone_id in zone_ids_to_refresh:
        await _refresh_zone_state(db, zone_id)

    agent.last_telemetry_at = now
    await db.flush()

    return {
        "status": "ok",
        "inserted": inserted,
        "total": len(readings),
        "errors": errors[:5] if errors else [],
    }


async def _maybe_fire_zone_alert(
    db: AsyncSession,
    facility_id,
    sensor: ZoneSensor,
    value: float,
    state: str,
    now: datetime,
) -> None:
    """Create a zone temperature alert if one isn't already active for this zone/type."""
    direction = "high" if "high" in state else "low"
    is_alarm = "alarm" in state
    alert_type = f"zone_temp_{direction}" if is_alarm else f"zone_temp_warn_{direction}"
    severity = "critical" if is_alarm else "medium"
    threshold = (
        (sensor.alarm_high if direction == "high" else sensor.alarm_low)
        if is_alarm
        else (sensor.warn_high if direction == "high" else sensor.warn_low)
    )

    # Dedup: skip if active alert already exists for this zone and direction
    existing = await db.execute(
        select(Alert).where(
            Alert.facility_id == facility_id,
            Alert.zone_id == sensor.zone_id,
            Alert.alert_type == alert_type,
            Alert.state.in_(["active", "acknowledged"]),
        )
    )
    if existing.scalar_one_or_none():
        return

    zone_result = await db.execute(select(Zone).where(Zone.id == sensor.zone_id))
    zone = zone_result.scalar_one_or_none()
    zone_name = zone.name if zone else "Unknown Zone"
    unit = sensor.unit or ""

    db.add(Alert(
        facility_id=facility_id,
        zone_id=sensor.zone_id,
        severity=severity,
        category="temperature",
        alert_type=alert_type,
        title=f"{zone_name}: Temp {'ALARM' if is_alarm else 'WARNING'} — {'High' if direction == 'high' else 'Low'}",
        message=(
            f"{sensor.name} reading {value:.1f}{unit} "
            f"({'≥' if direction == 'high' else '≤'} threshold {threshold}{unit})"
        ),
        trigger_value=str(round(value, 2)),
        threshold_value=str(threshold),
        triggered_at=now,
    ))


async def _refresh_zone_state(db: AsyncSession, zone_id) -> None:
    """Update zone.current_temp/humidity/door_open from latest sensor values."""
    result = await db.execute(
        select(Zone).where(Zone.id == zone_id)
    )
    zone = result.scalar_one_or_none()
    if not zone:
        return

    sensor_result = await db.execute(
        select(ZoneSensor).where(
            ZoneSensor.zone_id == zone_id,
            ZoneSensor.enabled == True,
            ZoneSensor.last_reading_at.isnot(None),
        )
    )
    sensors = sensor_result.scalars().all()

    worst_state = "normal"
    state_order = ["alarm_high", "alarm_low", "warning_high", "warning_low", "bad_quality", "normal"]

    for sensor in sensors:
        if sensor.current_value is None:
            continue
        if sensor.sensor_type in ("temperature", "glycol_temp"):
            zone.current_temp = sensor.current_value
            zone.last_reading_at = sensor.last_reading_at
        elif sensor.sensor_type == "humidity":
            zone.current_humidity = sensor.current_value
        elif sensor.sensor_type == "door_contact":
            zone.door_open = sensor.current_value > 0.5

        # Track worst state across all sensors
        s = sensor.current_state or "normal"
        if state_order.index(s) < state_order.index(worst_state):
            worst_state = s

    # Map sensor state to zone state
    if worst_state in ("alarm_high", "alarm_low"):
        zone.state = "alarm"
    elif worst_state in ("warning_high", "warning_low"):
        zone.state = "warning"
    elif worst_state == "bad_quality":
        zone.state = "offline"
    else:
        zone.state = "normal"


# ── Network Discovery ────────────────────────────────

@router.post("/facilities/{facility_id}/agents/{agent_id}/scan")
async def trigger_network_scan(
    facility_id: UUID,
    agent_id: UUID,
    body: dict | None = None,
    current_user: User = Depends(require_permission("agents:manage")),
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
    current_user: User = Depends(require_permission("agents:manage")),
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


# ── Header-authenticated agent routes (v2) ─────────────────────────────────
#
# The original agent-facing routes carry the agent key in the URL path, which
# writes credentials into every access log. These parallel routes take the
# key from "Authorization: Bearer cg_..." instead. Path-key routes remain for
# the deployed fleet; new/updated agents should use these. Handlers delegate
# to the originals, so behavior is identical.

from fastapi import Header  # noqa: E402


async def _agent_key_from_header(
    authorization: str = Header(..., description="Bearer <agent_key>"),
) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Expected 'Authorization: Bearer <agent_key>'")
    key = authorization[7:].strip()
    if not key.startswith("cg_"):
        raise HTTPException(status_code=401, detail="Invalid agent key")
    return key


@router.post("/agent/heartbeat")
async def agent_heartbeat_v2(
    data: HeartbeatPayload,
    agent_key: str = Depends(_agent_key_from_header),
    db: AsyncSession = Depends(get_db),
):
    return await agent_heartbeat(agent_key, data, db)


@router.post("/agent/telemetry")
async def ingest_telemetry_v2(
    data: TelemetryBatch,
    agent_key: str = Depends(_agent_key_from_header),
    db: AsyncSession = Depends(get_db),
):
    return await ingest_telemetry(agent_key, data, db)


@router.get("/agent/commands")
async def poll_commands_v2(
    agent_key: str = Depends(_agent_key_from_header),
    db: AsyncSession = Depends(get_db),
):
    return await poll_commands(agent_key, db)


@router.post("/agent/commands/{command_id}/ack")
async def acknowledge_command_v2(
    command_id: UUID,
    body: dict,
    agent_key: str = Depends(_agent_key_from_header),
    db: AsyncSession = Depends(get_db),
):
    return await acknowledge_command(agent_key, command_id, body, db)


@router.post("/agent/logs")
async def upload_logs_v2(
    logs: list[AgentLogCreate],
    agent_key: str = Depends(_agent_key_from_header),
    db: AsyncSession = Depends(get_db),
):
    return await upload_logs(agent_key, logs, db)


@router.post("/agent/compressor-readings")
async def ingest_compressor_readings_v2(
    payload: dict,
    agent_key: str = Depends(_agent_key_from_header),
    db: AsyncSession = Depends(get_db),
):
    return await ingest_compressor_readings(agent_key, payload, db)


@router.post("/agent/zone-readings")
async def ingest_zone_readings_v2(
    payload: dict,
    agent_key: str = Depends(_agent_key_from_header),
    db: AsyncSession = Depends(get_db),
):
    return await ingest_zone_readings(agent_key, payload, db)


@router.post("/agent/discoveries")
async def report_discoveries_v2(
    payload: dict,
    agent_key: str = Depends(_agent_key_from_header),
    db: AsyncSession = Depends(get_db),
):
    return await report_discoveries(agent_key, payload, db)
