"""
Integration Management API — CRUD for integrations, credentials, device mapping,
discovery, register maps, and polling control.

Cloud-facing endpoints (for the UI / admin):
  GET    /integrations/providers                        — List available providers
  POST   /facilities/{id}/integrations                  — Create integration
  GET    /facilities/{id}/integrations                  — List integrations
  GET    /facilities/{id}/integrations/{int_id}         — Get integration detail
  PATCH  /facilities/{id}/integrations/{int_id}         — Update integration
  DELETE /facilities/{id}/integrations/{int_id}         — Remove integration
  POST   /facilities/{id}/integrations/{int_id}/test    — Test connection
  POST   /facilities/{id}/integrations/{int_id}/discover — Run device discovery
  PUT    /facilities/{id}/integrations/{int_id}/device-map — Update device mappings
  POST   /facilities/{id}/integrations/{int_id}/poll    — Trigger immediate poll

Credential management:
  POST   /facilities/{id}/credentials                   — Store credentials
  GET    /facilities/{id}/credentials                   — List credentials (no secrets)
  DELETE /facilities/{id}/credentials/{cred_id}         — Remove credentials

Register maps:
  GET    /register-maps                                 — List all register maps
  GET    /register-maps/{map_id}                        — Get register map detail
  POST   /register-maps                                 — Create register map (admin)
"""

from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import get_current_user, get_facility_scoped, require_permission
from app.core.crypto import decrypt_json, encrypt_json
from app.models.user import User
from app.models.facility import Facility
from app.models.integration import Integration, IntegrationCredential, RegisterMap
from app.models.telemetry import Telemetry
from app.schemas.integration import (
    IntegrationCreate, IntegrationUpdate, IntegrationResponse, IntegrationListResponse,
    CredentialCreate, CredentialResponse, CredentialListResponse,
    DeviceMapUpdate,
    DiscoveryResponse, DiscoveredDeviceResponse,
    RegisterMapCreate, RegisterMapResponse, RegisterMapListResponse,
    ProviderListResponse, ProviderInfo,
)
from app.integrations.adapters import get_adapter_class, list_providers

router = APIRouter(tags=["integrations"])


# ── Helpers ─────────────────────────────────────────────

async def _get_facility(facility_id: UUID, user: User, db: AsyncSession):
    return await get_facility_scoped(facility_id, user, db)


async def _get_integration(
    facility_id: UUID, integration_id: UUID, db: AsyncSession
) -> Integration:
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.facility_id == facility_id,
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration


async def _get_credential(
    facility_id: UUID, credential_id: UUID, db: AsyncSession
) -> IntegrationCredential:
    result = await db.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.id == credential_id,
            IntegrationCredential.facility_id == facility_id,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")
    return cred


def _decrypt_credentials(encrypted: dict) -> dict:
    """Decrypt credential blob for runtime use."""
    return decrypt_json(encrypted)


def _encrypt_credentials(raw: dict) -> dict:
    """Encrypt credential blob for storage."""
    return encrypt_json(raw)


# ── Providers ───────────────────────────────────────────

@router.get("/integrations/providers", response_model=ProviderListResponse)
async def get_providers(user: User = Depends(get_current_user)):
    """List all available integration providers."""
    providers = list_providers()
    return ProviderListResponse(
        providers=[ProviderInfo(**p) for p in providers]
    )


# ── Integration CRUD ────────────────────────────────────

@router.post(
    "/facilities/{facility_id}/integrations",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    facility_id: UUID,
    payload: IntegrationCreate,
    user: User = Depends(require_permission("agents:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new integration for a facility."""
    await _get_facility(facility_id, user, db)

    # Validate provider exists
    try:
        get_adapter_class(payload.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    integration = Integration(
        facility_id=facility_id,
        provider=payload.provider,
        integration_type=payload.integration_type,
        name=payload.name,
        description=payload.description,
        config=payload.config,
        credential_id=payload.credential_id,
        enabled=payload.enabled,
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return integration


@router.get(
    "/facilities/{facility_id}/integrations",
    response_model=IntegrationListResponse,
)
async def list_integrations(
    facility_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all integrations for a facility."""
    await _get_facility(facility_id, user, db)

    result = await db.execute(
        select(Integration).where(Integration.facility_id == facility_id)
        .order_by(Integration.created_at.desc())
    )
    integrations = result.scalars().all()

    count_result = await db.execute(
        select(func.count(Integration.id)).where(Integration.facility_id == facility_id)
    )
    total = count_result.scalar() or 0

    return IntegrationListResponse(integrations=integrations, total=total)


@router.get(
    "/facilities/{facility_id}/integrations/{integration_id}",
    response_model=IntegrationResponse,
)
async def get_integration(
    facility_id: UUID,
    integration_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific integration by ID."""
    await _get_facility(facility_id, user, db)
    return await _get_integration(facility_id, integration_id, db)


@router.patch(
    "/facilities/{facility_id}/integrations/{integration_id}",
    response_model=IntegrationResponse,
)
async def update_integration(
    facility_id: UUID,
    integration_id: UUID,
    payload: IntegrationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an integration's configuration."""
    await _get_facility(facility_id, user, db)
    integration = await _get_integration(facility_id, integration_id, db)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(integration, field, value)

    integration.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(integration)
    return integration


@router.delete(
    "/facilities/{facility_id}/integrations/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_integration(
    facility_id: UUID,
    integration_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an integration from a facility."""
    await _get_facility(facility_id, user, db)
    integration = await _get_integration(facility_id, integration_id, db)
    await db.delete(integration)
    await db.commit()


# ── Connection Test ─────────────────────────────────────

@router.post(
    "/facilities/{facility_id}/integrations/{integration_id}/test",
)
async def test_integration(
    facility_id: UUID,
    integration_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test connectivity for an integration (authenticate + health check)."""
    await _get_facility(facility_id, user, db)
    integration = await _get_integration(facility_id, integration_id, db)

    # Get credentials if linked
    credentials = None
    if integration.credential_id:
        cred = await _get_credential(facility_id, integration.credential_id, db)
        credentials = _decrypt_credentials(cred.credentials_encrypted)

    try:
        adapter_cls = get_adapter_class(integration.provider)
        adapter = adapter_cls(config=integration.config, credentials=credentials)

        await adapter.authenticate()
        health = await adapter.health_check()
        await adapter.disconnect()

        # Update integration state
        integration.connection_state = "connected" if health.connected else "error"
        if not health.connected:
            integration.last_error = health.error
            integration.last_error_at = datetime.now(timezone.utc)
        integration.updated_at = datetime.now(timezone.utc)
        await db.commit()

        return {
            "success": health.connected,
            "latency_ms": health.latency_ms,
            "error": health.error,
            "details": health.details,
        }
    except Exception as e:
        integration.connection_state = "error"
        integration.last_error = str(e)
        integration.last_error_at = datetime.now(timezone.utc)
        integration.updated_at = datetime.now(timezone.utc)
        await db.commit()

        return {"success": False, "error": str(e)}


# ── Discovery ───────────────────────────────────────────

@router.post(
    "/facilities/{facility_id}/integrations/{integration_id}/discover",
    response_model=DiscoveryResponse,
)
async def discover_devices(
    facility_id: UUID,
    integration_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run device discovery on an integration."""
    await _get_facility(facility_id, user, db)
    integration = await _get_integration(facility_id, integration_id, db)

    credentials = None
    if integration.credential_id:
        cred = await _get_credential(facility_id, integration.credential_id, db)
        credentials = _decrypt_credentials(cred.credentials_encrypted)

    try:
        adapter_cls = get_adapter_class(integration.provider)
        adapter = adapter_cls(config=integration.config, credentials=credentials)

        await adapter.authenticate()
        discovered = await adapter.discover()
        await adapter.disconnect()

        devices = [
            DiscoveredDeviceResponse(
                external_id=d.external_id,
                name=d.name,
                device_type=d.device_type,
                manufacturer=d.manufacturer,
                model=d.model,
                protocol=d.protocol,
                address=d.address,
                metadata=d.metadata,
                available_metrics=d.available_metrics,
            )
            for d in discovered
        ]

        return DiscoveryResponse(devices=devices, total=len(devices))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Discovery failed: {e}")


# ── Device Mapping ──────────────────────────────────────

@router.put(
    "/facilities/{facility_id}/integrations/{integration_id}/device-map",
    response_model=IntegrationResponse,
)
async def update_device_map(
    facility_id: UUID,
    integration_id: UUID,
    payload: DeviceMapUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the device mapping for an integration."""
    await _get_facility(facility_id, user, db)
    integration = await _get_integration(facility_id, integration_id, db)

    device_map = {}
    for mapping in payload.mappings:
        device_map[mapping.external_id] = {
            "equipment_id": str(mapping.equipment_id),
            "metrics": mapping.metrics,
        }

    integration.device_map = device_map
    integration.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(integration)
    return integration


# ── Manual Poll ─────────────────────────────────────────

@router.post(
    "/facilities/{facility_id}/integrations/{integration_id}/poll",
)
async def trigger_poll(
    facility_id: UUID,
    integration_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an immediate poll on an integration."""
    await _get_facility(facility_id, user, db)
    integration = await _get_integration(facility_id, integration_id, db)

    if not integration.device_map:
        raise HTTPException(
            status_code=400,
            detail="No device mappings configured. Run discovery and map devices first."
        )

    credentials = None
    if integration.credential_id:
        cred = await _get_credential(facility_id, integration.credential_id, db)
        credentials = _decrypt_credentials(cred.credentials_encrypted)

    try:
        adapter_cls = get_adapter_class(integration.provider)
        adapter = adapter_cls(config=integration.config, credentials=credentials)

        await adapter.authenticate()
        readings = await adapter.poll(device_map=integration.device_map)
        await adapter.disconnect()

        now = datetime.now(timezone.utc)

        # Persist readings to TimescaleDB telemetry table
        ingested = 0
        for r in readings:
            try:
                telemetry = Telemetry(
                    time=getattr(r, "timestamp", None) or now,
                    equipment_id=r.equipment_id,
                    metric_name=r.metric_name,
                    value=r.value,
                    unit=r.unit,
                    quality=getattr(r, "quality", 0),
                )
                db.add(telemetry)
                ingested += 1
            except Exception:
                pass  # skip malformed readings

        integration.last_poll_at = now
        integration.last_success_at = now
        integration.total_polls = (integration.total_polls or 0) + 1
        integration.total_readings_ingested = (
            (integration.total_readings_ingested or 0) + ingested
        )
        integration.connection_state = "connected"
        integration.updated_at = now
        await db.commit()

        return {
            "success": True,
            "readings_count": ingested,
            "readings": [
                {
                    "equipment_id": str(r.equipment_id),
                    "metric_name": r.metric_name,
                    "value": r.value,
                    "unit": r.unit,
                    "quality": getattr(r, "quality", 0),
                }
                for r in readings
            ],
        }
    except Exception as e:
        now = datetime.now(timezone.utc)
        integration.last_poll_at = now
        integration.last_error = str(e)
        integration.last_error_at = now
        integration.total_polls = (integration.total_polls or 0) + 1
        integration.total_errors = (integration.total_errors or 0) + 1
        integration.connection_state = "error"
        integration.updated_at = now
        await db.commit()

        return {"success": False, "error": str(e), "readings_count": 0}


# ── Credential Management ──────────────────────────────

@router.post(
    "/facilities/{facility_id}/credentials",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    facility_id: UUID,
    payload: CredentialCreate,
    user: User = Depends(require_permission("agents:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Store encrypted credentials for a provider."""
    await _get_facility(facility_id, user, db)

    cred = IntegrationCredential(
        facility_id=facility_id,
        provider=payload.provider,
        auth_type=payload.auth_type,
        credentials_encrypted=_encrypt_credentials(payload.credentials),
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)
    return cred


@router.get(
    "/facilities/{facility_id}/credentials",
    response_model=CredentialListResponse,
)
async def list_credentials(
    facility_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List credentials for a facility (secrets NOT returned)."""
    await _get_facility(facility_id, user, db)

    result = await db.execute(
        select(IntegrationCredential)
        .where(IntegrationCredential.facility_id == facility_id)
        .order_by(IntegrationCredential.created_at.desc())
    )
    creds = result.scalars().all()

    return CredentialListResponse(credentials=creds, total=len(creds))


@router.delete(
    "/facilities/{facility_id}/credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_credential(
    facility_id: UUID,
    credential_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete credentials. Fails if any integration references them."""
    await _get_facility(facility_id, user, db)
    cred = await _get_credential(facility_id, credential_id, db)

    # Check if any integration is using these credentials
    result = await db.execute(
        select(func.count(Integration.id))
        .where(Integration.credential_id == credential_id)
    )
    in_use = result.scalar() or 0
    if in_use > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Credential is in use by {in_use} integration(s). Unlink them first."
        )

    await db.delete(cred)
    await db.commit()


# ── Register Maps ───────────────────────────────────────

@router.get("/register-maps", response_model=RegisterMapListResponse)
async def list_register_maps(
    protocol: str | None = None,
    manufacturer: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available register maps (predefined device profiles)."""
    query = select(RegisterMap)
    if protocol:
        query = query.where(RegisterMap.protocol == protocol)
    if manufacturer:
        query = query.where(RegisterMap.manufacturer.ilike(f"%{manufacturer}%"))
    query = query.order_by(RegisterMap.manufacturer, RegisterMap.name)

    result = await db.execute(query)
    maps = result.scalars().all()

    return RegisterMapListResponse(register_maps=maps, total=len(maps))


@router.get("/register-maps/{map_id}", response_model=RegisterMapResponse)
async def get_register_map(
    map_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific register map by ID."""
    result = await db.execute(select(RegisterMap).where(RegisterMap.id == map_id))
    reg_map = result.scalar_one_or_none()
    if not reg_map:
        raise HTTPException(status_code=404, detail="Register map not found")
    return reg_map


@router.post(
    "/register-maps",
    response_model=RegisterMapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_register_map(
    payload: RegisterMapCreate,
    user: User = Depends(require_permission("kelvex:provision")),
    db: AsyncSession = Depends(get_db),
):
    """Create a register map (typically admin/installer only)."""
    reg_map = RegisterMap(
        name=payload.name,
        protocol=payload.protocol,
        manufacturer=payload.manufacturer,
        model=payload.model,
        description=payload.description,
        version=payload.version,
        registers=payload.registers,
    )
    db.add(reg_map)
    await db.commit()
    await db.refresh(reg_map)
    return reg_map
