"""Pydantic schemas for integration management."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


# ── Integration Credentials ─────────────────────────────

class CredentialCreate(BaseModel):
    provider: str
    auth_type: str = Field(
        ..., description="oauth2 | api_key | basic | bearer_token | certificate"
    )
    credentials: dict = Field(
        ..., description="Raw credential fields (will be stored encrypted)"
    )


class CredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    provider: str
    auth_type: str
    token_expires_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    created_at: datetime
    # NOTE: credentials_encrypted is NEVER returned to the client


class CredentialListResponse(BaseModel):
    credentials: list[CredentialResponse]
    total: int


# ── Integrations ────────────────────────────────────────

class IntegrationCreate(BaseModel):
    provider: str = Field(
        ..., description=(
            "danfoss_alsense | emerson_oversight | schneider_ecostruxure | "
            "jci_openblue | jci_metasys | honeywell_niagara | "
            "modbus_tcp | bacnet_ip"
        )
    )
    integration_type: str = Field(
        ..., description="cloud_api | edge_protocol | bas_middleware"
    )
    name: str
    description: str | None = None
    config: dict = Field(default_factory=dict)
    credential_id: UUID | None = None
    enabled: bool = True


class IntegrationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict | None = None
    credential_id: UUID | None = None
    enabled: bool | None = None


class IntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    facility_id: UUID
    provider: str
    integration_type: str
    name: str
    description: str | None = None
    config: dict
    credential_id: UUID | None = None
    enabled: bool
    connection_state: str
    last_poll_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    total_polls: int
    total_errors: int
    total_readings_ingested: int
    device_map: dict | None = None
    created_at: datetime
    updated_at: datetime


class IntegrationListResponse(BaseModel):
    integrations: list[IntegrationResponse]
    total: int


# ── Device Mapping ──────────────────────────────────────

class DeviceMapping(BaseModel):
    """Map an external device ID to a ColdGrid equipment ID."""
    external_id: str
    equipment_id: UUID
    metrics: dict = Field(
        default_factory=dict,
        description=(
            "Map external metric names to ColdGrid metric names. "
            "Format: {ext_name: {metric_name: str, unit: str}}"
        ),
    )


class DeviceMapUpdate(BaseModel):
    """Batch update device mappings for an integration."""
    mappings: list[DeviceMapping]


# ── Discovery ───────────────────────────────────────────

class DiscoveredDeviceResponse(BaseModel):
    external_id: str
    name: str
    device_type: str
    manufacturer: str | None = None
    model: str | None = None
    protocol: str | None = None
    address: str | None = None
    metadata: dict = {}
    available_metrics: list[str] = []


class DiscoveryResponse(BaseModel):
    devices: list[DiscoveredDeviceResponse]
    total: int


# ── Register Maps ───────────────────────────────────────

class RegisterMapCreate(BaseModel):
    name: str
    protocol: str = Field(
        ..., description="modbus_tcp | modbus_rtu | bacnet_ip | ethernet_ip"
    )
    manufacturer: str
    model: str | None = None
    description: str | None = None
    version: str = "1.0"
    registers: dict = Field(
        ..., description="Register/object definitions (format depends on protocol)"
    )


class RegisterMapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    protocol: str
    manufacturer: str
    model: str | None = None
    description: str | None = None
    version: str
    registers: dict
    created_at: datetime


class RegisterMapListResponse(BaseModel):
    register_maps: list[RegisterMapResponse]
    total: int


# ── Provider Info ───────────────────────────────────────

class ProviderInfo(BaseModel):
    provider: str
    integration_type: str
    supports_write: bool


class ProviderListResponse(BaseModel):
    providers: list[ProviderInfo]
