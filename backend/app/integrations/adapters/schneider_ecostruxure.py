"""
Schneider Electric EcoStruxure Cloud Adapter

Best public API in the industrial space. OAuth2 with a real developer portal.
Primarily used for energy metering and BAS in cold storage, not direct
refrigeration control. Strong for demand monitoring and power quality.

Auth: OAuth2 (Authorization Code flow via Schneider Exchange)
Docs: https://developer.se.com (publicly browsable)
"""

import time
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.integrations.base import (
    BaseAdapter, TelemetryReading, DiscoveredDevice, AdapterHealth,
)


class SchneiderEcoStruxureAdapter(BaseAdapter):
    provider = "schneider_ecostruxure"
    integration_type = "cloud_api"

    DEFAULT_BASE_URL = "https://api.exchange.se.com"
    TOKEN_URL = "https://auth.exchange.se.com/oauth2/token"

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
                    "scope": self.credentials.get("scope", "read:data"),
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
            raise ConnectionError(f"Schneider auth failed: {e}")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}", "Accept": "application/json"}

    async def discover(self) -> list[DiscoveredDevice]:
        """Discover assets at the site — meters, panels, BAS controllers."""
        await self.authenticate()
        devices = []

        resp = await self._client.get(
            f"{self.base_url}/v1/sites/{self.site_id}/assets",
            headers=self._headers(),
        )
        resp.raise_for_status()

        for asset in resp.json().get("assets", []):
            devices.append(DiscoveredDevice(
                external_id=asset["id"],
                name=asset.get("name", asset["id"]),
                device_type=_classify_schneider_asset(asset),
                manufacturer="Schneider Electric",
                model=asset.get("model"),
                protocol="ecostruxure_api",
                address=f"site:{self.site_id}/asset:{asset['id']}",
                metadata={
                    "asset_type": asset.get("type"),
                    "category": asset.get("category"),
                },
                available_metrics=asset.get("available_measurements", []),
            ))

        return devices

    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        """Poll current measurements — strong for energy/power data."""
        await self.authenticate()
        readings = []
        now = datetime.now(timezone.utc)

        for ext_id, mapping in device_map.items():
            equipment_id = UUID(mapping["equipment_id"])
            metrics = mapping.get("metrics", {})

            try:
                resp = await self._client.get(
                    f"{self.base_url}/v1/assets/{ext_id}/measurements/latest",
                    headers=self._headers(),
                )
                resp.raise_for_status()

                for measurement in resp.json().get("measurements", []):
                    m_name = measurement.get("type", "")
                    if m_name in metrics:
                        cfg = metrics[m_name]
                        value = measurement.get("value")
                        if value is not None:
                            try:
                                readings.append(TelemetryReading(
                                    equipment_id=equipment_id,
                                    metric_name=cfg["metric_name"],
                                    value=float(value),
                                    unit=cfg.get("unit", measurement.get("unit", "")),
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


def _classify_schneider_asset(asset: dict) -> str:
    atype = (asset.get("type") or "").lower()
    if "meter" in atype or "power" in atype:
        return "meter"
    elif "panel" in atype:
        return "controller"
    elif "hvac" in atype or "ahu" in atype:
        return "controller"
    return "meter"
