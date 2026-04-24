"""
Johnson Controls OpenBlue / Metasys Adapter

Two integration paths:
  1. OpenBlue Cloud API — enterprise-tier, OAuth2
  2. Metasys REST API — on-premises server (Metasys 11.0+), basic/bearer auth

JCI is common in large cold storage through York/Frick industrial
compressor packages and Metasys BAS for facility management.

Auth: OAuth2 (OpenBlue) or Basic Auth (Metasys on-prem)
"""

import time
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.integrations.base import (
    BaseAdapter, TelemetryReading, DiscoveredDevice,
    WriteCommand, WriteResult, AdapterHealth,
)


class JCIOpenBlueAdapter(BaseAdapter):
    provider = "jci_openblue"
    integration_type = "cloud_api"

    DEFAULT_BASE_URL = "https://api.openblue.johnsoncontrols.com"
    TOKEN_URL = "https://auth.openblue.johnsoncontrols.com/oauth2/token"

    def __init__(self, config: dict, credentials: dict | None = None):
        super().__init__(config, credentials)
        self.base_url = config.get("base_url", self.DEFAULT_BASE_URL)
        self.site_id = config.get("site_id")
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._client = httpx.AsyncClient(timeout=30.0)

    async def authenticate(self) -> bool:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return True

        try:
            resp = await self._client.post(
                self.credentials.get("token_url", self.TOKEN_URL),
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.credentials["client_id"],
                    "client_secret": self.credentials["client_secret"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600)
            self._authenticated = True
            return True
        except Exception as e:
            self._authenticated = False
            raise ConnectionError(f"JCI OpenBlue auth failed: {e}")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}", "Accept": "application/json"}

    async def discover(self) -> list[DiscoveredDevice]:
        await self.authenticate()
        devices = []

        resp = await self._client.get(
            f"{self.base_url}/v1/sites/{self.site_id}/equipment",
            headers=self._headers(),
        )
        resp.raise_for_status()

        for equip in resp.json().get("equipment", []):
            points_resp = await self._client.get(
                f"{self.base_url}/v1/equipment/{equip['id']}/points",
                headers=self._headers(),
            )
            points = []
            if points_resp.status_code == 200:
                points = [p["name"] for p in points_resp.json().get("points", [])]

            devices.append(DiscoveredDevice(
                external_id=equip["id"],
                name=equip.get("name", equip["id"]),
                device_type=_classify_jci_equipment(equip),
                manufacturer="Johnson Controls",
                model=equip.get("model"),
                protocol="openblue_api",
                address=f"site:{self.site_id}/equip:{equip['id']}",
                metadata={
                    "equipment_type": equip.get("type"),
                    "space": equip.get("space_name"),
                },
                available_metrics=points,
            ))

        return devices

    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        await self.authenticate()
        readings = []
        now = datetime.now(timezone.utc)

        for ext_id, mapping in device_map.items():
            equipment_id = UUID(mapping["equipment_id"])
            metrics = mapping.get("metrics", {})

            try:
                resp = await self._client.get(
                    f"{self.base_url}/v1/equipment/{ext_id}/points/values",
                    headers=self._headers(),
                )
                resp.raise_for_status()

                for point in resp.json().get("values", []):
                    p_name = point.get("name", "")
                    if p_name in metrics:
                        cfg = metrics[p_name]
                        value = point.get("value")
                        if value is not None:
                            try:
                                readings.append(TelemetryReading(
                                    equipment_id=equipment_id,
                                    metric_name=cfg["metric_name"],
                                    value=float(value),
                                    unit=cfg.get("unit", ""),
                                    timestamp=now,
                                    quality=0,
                                ))
                            except (ValueError, TypeError):
                                continue
            except Exception:
                continue

        return readings

    async def write(self, command: WriteCommand, device_map: dict) -> WriteResult:
        await self.authenticate()
        ext_id = None
        param_name = None
        for eid, mapping in device_map.items():
            if UUID(mapping["equipment_id"]) == command.equipment_id:
                ext_id = eid
                for ext_name, cfg in mapping.get("metrics", {}).items():
                    if cfg["metric_name"] == command.metric_name:
                        param_name = ext_name
                        break
                break

        if not ext_id or not param_name:
            return WriteResult(success=False, message="Not found or not writable")

        try:
            resp = await self._client.put(
                f"{self.base_url}/v1/equipment/{ext_id}/points/{param_name}",
                headers=self._headers(),
                json={"value": command.value},
            )
            resp.raise_for_status()
            return WriteResult(success=True, new_value=command.value)
        except Exception as e:
            return WriteResult(success=False, message=str(e))

    async def health_check(self) -> AdapterHealth:
        try:
            await self.authenticate()
            start = time.time()
            resp = await self._client.get(
                f"{self.base_url}/v1/sites/{self.site_id}",
                headers=self._headers(),
            )
            latency = (time.time() - start) * 1000
            return AdapterHealth(connected=True, latency_ms=latency)
        except Exception as e:
            return AdapterHealth(connected=False, error=str(e))

    async def disconnect(self):
        await self._client.aclose()
        await super().disconnect()


class JCIMetasysAdapter(BaseAdapter):
    """On-premises Metasys REST API (Metasys Server 11.0+)."""
    provider = "jci_metasys"
    integration_type = "bas_middleware"

    def __init__(self, config: dict, credentials: dict | None = None):
        super().__init__(config, credentials)
        self.base_url = config.get("base_url", "https://192.168.1.50")
        verify_ssl = config.get("verify_ssl", False)
        self._client = httpx.AsyncClient(timeout=30.0, verify=verify_ssl)
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    async def authenticate(self) -> bool:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return True

        try:
            resp = await self._client.post(
                f"{self.base_url}/api/v3/login",
                json={
                    "username": self.credentials["username"],
                    "password": self.credentials["password"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data.get("accessToken")
            self._token_expires_at = time.time() + data.get("expires", 3600)
            self._authenticated = True
            return True
        except Exception as e:
            self._authenticated = False
            raise ConnectionError(f"Metasys auth failed: {e}")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}", "Accept": "application/json"}

    async def discover(self) -> list[DiscoveredDevice]:
        """Discover all network devices in Metasys."""
        await self.authenticate()
        devices = []

        resp = await self._client.get(
            f"{self.base_url}/api/v3/networkDevices",
            headers=self._headers(),
        )
        resp.raise_for_status()

        for dev in resp.json().get("items", []):
            # Get objects (points) for each device
            obj_resp = await self._client.get(
                f"{self.base_url}/api/v3/networkDevices/{dev['id']}/objects",
                headers=self._headers(),
                params={"pageSize": 100},
            )
            points = []
            if obj_resp.status_code == 200:
                points = [o.get("name", "") for o in obj_resp.json().get("items", [])]

            devices.append(DiscoveredDevice(
                external_id=dev["id"],
                name=dev.get("name", dev["id"]),
                device_type="controller",
                manufacturer="Johnson Controls",
                model=dev.get("type", "Metasys"),
                protocol="metasys_api",
                address=dev.get("ipAddress", ""),
                metadata={"firmware": dev.get("firmwareVersion")},
                available_metrics=points[:50],  # cap at 50 for discovery
            ))

        return devices

    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        await self.authenticate()
        readings = []
        now = datetime.now(timezone.utc)

        for ext_id, mapping in device_map.items():
            equipment_id = UUID(mapping["equipment_id"])
            metrics = mapping.get("metrics", {})

            try:
                resp = await self._client.get(
                    f"{self.base_url}/api/v3/objects/{ext_id}/attributes/presentValue",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for attr_name, cfg in metrics.items():
                        value = data.get(attr_name, {}).get("value")
                        if value is not None:
                            try:
                                readings.append(TelemetryReading(
                                    equipment_id=equipment_id,
                                    metric_name=cfg["metric_name"],
                                    value=float(value),
                                    unit=cfg.get("unit", ""),
                                    timestamp=now,
                                    quality=0,
                                ))
                            except (ValueError, TypeError):
                                continue
            except Exception:
                continue

        return readings

    async def health_check(self) -> AdapterHealth:
        try:
            await self.authenticate()
            start = time.time()
            resp = await self._client.get(
                f"{self.base_url}/api/v3/serverStatus",
                headers=self._headers(),
            )
            latency = (time.time() - start) * 1000
            return AdapterHealth(connected=True, latency_ms=latency)
        except Exception as e:
            return AdapterHealth(connected=False, error=str(e))

    async def disconnect(self):
        await self._client.aclose()
        await super().disconnect()


def _classify_jci_equipment(equip: dict) -> str:
    etype = (equip.get("type") or "").lower()
    if "compressor" in etype or "chiller" in etype or "york" in etype or "frick" in etype:
        return "compressor"
    elif "ahu" in etype or "air" in etype:
        return "controller"
    elif "vav" in etype or "zone" in etype:
        return "controller"
    elif "condenser" in etype or "cooling" in etype:
        return "condenser"
    return "controller"
