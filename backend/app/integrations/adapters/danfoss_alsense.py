"""
Danfoss Alsense Cloud Adapter

Connects to Danfoss Alsense IoT platform via OAuth2 REST API.
Reads temperatures, pressures, compressor status, alarms, and energy
from AK-series controllers (AK-PC 781, AK-SM 800A, AK-SC 255, etc.).

Auth: OAuth2 client credentials flow
Docs: Partner-gated — requires Danfoss API partner agreement
Base URL: https://api.alsense.danfoss.com (production)
"""

import time
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.integrations.base import (
    BaseAdapter, TelemetryReading, DiscoveredDevice,
    WriteCommand, WriteResult, AdapterHealth,
)


class DanfossAlsenseAdapter(BaseAdapter):
    provider = "danfoss_alsense"
    integration_type = "cloud_api"

    DEFAULT_BASE_URL = "https://api.alsense.danfoss.com"
    TOKEN_URL = "https://auth.alsense.danfoss.com/oauth2/token"

    def __init__(self, config: dict, credentials: dict | None = None):
        super().__init__(config, credentials)
        self.base_url = config.get("base_url", self.DEFAULT_BASE_URL)
        self.site_id = config.get("site_id")
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._client = httpx.AsyncClient(timeout=30.0)

    async def authenticate(self) -> bool:
        """OAuth2 client credentials flow."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return True  # token still valid

        try:
            token_url = self.credentials.get("token_url", self.TOKEN_URL)
            response = await self._client.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.credentials["client_id"],
                    "client_secret": self.credentials["client_secret"],
                    "scope": self.credentials.get("scope", "read"),
                },
            )
            response.raise_for_status()
            data = response.json()
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600)
            self._authenticated = True
            return True
        except Exception as e:
            self._authenticated = False
            raise ConnectionError(f"Danfoss Alsense auth failed: {e}")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def discover(self) -> list[DiscoveredDevice]:
        """Discover all controllers and devices at the configured site."""
        await self.authenticate()
        devices = []

        # List controllers at this site
        resp = await self._client.get(
            f"{self.base_url}/v1/sites/{self.site_id}/controllers",
            headers=self._headers(),
        )
        resp.raise_for_status()

        for controller in resp.json().get("data", []):
            ctrl_id = controller["id"]

            # Get points/parameters for each controller
            points_resp = await self._client.get(
                f"{self.base_url}/v1/controllers/{ctrl_id}/parameters",
                headers=self._headers(),
            )
            points_resp.raise_for_status()
            points = points_resp.json().get("data", [])
            metric_names = [p["name"] for p in points]

            devices.append(DiscoveredDevice(
                external_id=ctrl_id,
                name=controller.get("name", f"Controller {ctrl_id}"),
                device_type=_classify_danfoss_device(controller.get("type", "")),
                manufacturer="Danfoss",
                model=controller.get("model", controller.get("type")),
                protocol="alsense_api",
                address=f"site:{self.site_id}/ctrl:{ctrl_id}",
                metadata={
                    "firmware": controller.get("firmware_version"),
                    "serial": controller.get("serial_number"),
                    "online": controller.get("online", False),
                },
                available_metrics=metric_names,
            ))

        return devices

    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        """Poll current values from all mapped devices."""
        await self.authenticate()
        readings = []
        now = datetime.now(timezone.utc)

        for ext_id, mapping in device_map.items():
            equipment_id = UUID(mapping["equipment_id"])
            metrics = mapping.get("metrics", {})

            try:
                # Get current parameter values for this controller
                resp = await self._client.get(
                    f"{self.base_url}/v1/controllers/{ext_id}/parameters/values",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                values = resp.json().get("data", [])

                for param in values:
                    param_name = param.get("name", "")
                    if param_name in metrics:
                        metric_cfg = metrics[param_name]
                        value = param.get("value")
                        if value is not None:
                            try:
                                readings.append(TelemetryReading(
                                    equipment_id=equipment_id,
                                    metric_name=metric_cfg["metric_name"],
                                    value=float(value),
                                    unit=metric_cfg.get("unit", param.get("unit", "")),
                                    timestamp=now,
                                    quality=0 if param.get("quality") == "good" else 2,
                                ))
                            except (ValueError, TypeError):
                                continue

            except httpx.HTTPStatusError as e:
                # Log but continue — don't let one device failure kill the poll
                continue

        return readings

    async def write(self, command: WriteCommand, device_map: dict) -> WriteResult:
        """Write a setpoint value via Alsense API."""
        await self.authenticate()

        # Find the external device ID for this equipment
        ext_id = None
        param_name = None
        for eid, mapping in device_map.items():
            if UUID(mapping["equipment_id"]) == command.equipment_id:
                ext_id = eid
                # Reverse-lookup the external parameter name
                for ext_name, cfg in mapping.get("metrics", {}).items():
                    if cfg["metric_name"] == command.metric_name:
                        param_name = ext_name
                        break
                break

        if not ext_id or not param_name:
            return WriteResult(success=False, message="Device or parameter not found in device map")

        try:
            resp = await self._client.put(
                f"{self.base_url}/v1/controllers/{ext_id}/parameters/{param_name}",
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
            resp.raise_for_status()
            return AdapterHealth(connected=True, latency_ms=latency)
        except Exception as e:
            return AdapterHealth(connected=False, error=str(e))

    async def disconnect(self):
        await self._client.aclose()
        await super().disconnect()


def _classify_danfoss_device(device_type: str) -> str:
    """Map Danfoss controller types to ColdGrid equipment types."""
    dt = device_type.lower()
    if "pack" in dt or "pc" in dt:
        return "compressor"
    elif "case" in dt or "cc" in dt or "evap" in dt:
        return "evaporator"
    elif "cond" in dt:
        return "condenser"
    elif "sm" in dt or "sc" in dt or "system" in dt:
        return "controller"
    return "controller"
