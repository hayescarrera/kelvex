"""
Honeywell / Tridium Niagara Adapter

Niagara is the most common BAS middleware in cold storage facilities.
It aggregates data from Danfoss, Emerson, Allen-Bradley, and everything
else on the facility network. If a facility has a Niagara supervisor,
it's often the single best integration point — one connection gets you
everything.

Auth: Session-based (username/password → session cookie or BAJA token)
Protocol: Niagara REST API (N4) or fox:// protocol
Docs: https://www.niagara-community.com (requires Tridium developer account)
"""

import time
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.integrations.base import (
    BaseAdapter, TelemetryReading, DiscoveredDevice,
    WriteCommand, WriteResult, AdapterHealth,
)


class HoneywellNiagaraAdapter(BaseAdapter):
    """Tridium Niagara 4 on-premises REST API."""
    provider = "honeywell_niagara"
    integration_type = "bas_middleware"

    def __init__(self, config: dict, credentials: dict | None = None):
        super().__init__(config, credentials)
        self.base_url = config.get("base_url", "https://192.168.1.50")
        self.station = config.get("station_name", "station")
        verify_ssl = config.get("verify_ssl", False)
        self._client = httpx.AsyncClient(timeout=30.0, verify=verify_ssl)
        self._session_token: str | None = None
        self._token_expires_at: float = 0

    async def authenticate(self) -> bool:
        if self._session_token and time.time() < self._token_expires_at - 60:
            return True

        try:
            resp = await self._client.post(
                f"{self.base_url}/login",
                data={
                    "username": self.credentials["username"],
                    "password": self.credentials["password"],
                },
            )
            resp.raise_for_status()
            # Niagara returns a session cookie or a BAJA token
            self._session_token = resp.cookies.get("niagara_session") or resp.json().get("token")
            self._token_expires_at = time.time() + 3600  # 1hr default
            self._authenticated = True
            return True
        except Exception as e:
            self._authenticated = False
            raise ConnectionError(f"Niagara auth failed: {e}")

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self._session_token:
            headers["Authorization"] = f"Bearer {self._session_token}"
        return headers

    async def discover(self) -> list[DiscoveredDevice]:
        """
        Discover all points in the Niagara station.
        Niagara uses a hierarchical point structure (slot path).
        """
        await self.authenticate()
        devices = []

        # Get the top-level network tree
        resp = await self._client.get(
            f"{self.base_url}/api/core/baja/station/{self.station}/network",
            headers=self._headers(),
        )
        resp.raise_for_status()

        for device in resp.json().get("children", []):
            device_path = device.get("slotPath", "")

            # Get points under this device
            points_resp = await self._client.get(
                f"{self.base_url}/api/core/baja/station/{self.station}/network/{device_path}/points",
                headers=self._headers(),
            )
            points = []
            if points_resp.status_code == 200:
                points = [p.get("name", "") for p in points_resp.json().get("children", [])]

            devices.append(DiscoveredDevice(
                external_id=device_path,
                name=device.get("displayName", device.get("name", device_path)),
                device_type="controller",
                manufacturer=device.get("vendor", "Unknown"),
                model=device.get("model"),
                protocol="niagara_api",
                address=device_path,
                metadata={
                    "driver": device.get("driver"),
                    "status": device.get("status"),
                    "protocol": device.get("protocol"),  # bacnet, modbus, etc.
                },
                available_metrics=points[:100],
            ))

        return devices

    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        await self.authenticate()
        readings = []
        now = datetime.now(timezone.utc)

        for ext_path, mapping in device_map.items():
            equipment_id = UUID(mapping["equipment_id"])
            metrics = mapping.get("metrics", {})

            for point_name, cfg in metrics.items():
                try:
                    # Read a single point value by slot path
                    slot_path = f"{ext_path}/{point_name}"
                    resp = await self._client.get(
                        f"{self.base_url}/api/core/baja/station/{self.station}/point/{slot_path}/value",
                        headers=self._headers(),
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        value = data.get("value")
                        if value is not None:
                            try:
                                readings.append(TelemetryReading(
                                    equipment_id=equipment_id,
                                    metric_name=cfg["metric_name"],
                                    value=float(value),
                                    unit=cfg.get("unit", data.get("unit", "")),
                                    timestamp=now,
                                    quality=0 if data.get("status") == "ok" else 2,
                                ))
                            except (ValueError, TypeError):
                                continue
                except Exception:
                    continue

        return readings

    async def write(self, command: WriteCommand, device_map: dict) -> WriteResult:
        """Write a value to a Niagara point."""
        await self.authenticate()

        ext_path = None
        point_name = None
        for epath, mapping in device_map.items():
            if UUID(mapping["equipment_id"]) == command.equipment_id:
                ext_path = epath
                for pname, cfg in mapping.get("metrics", {}).items():
                    if cfg["metric_name"] == command.metric_name:
                        point_name = pname
                        break
                break

        if not ext_path or not point_name:
            return WriteResult(success=False, message="Point not found")

        try:
            slot_path = f"{ext_path}/{point_name}"
            resp = await self._client.put(
                f"{self.base_url}/api/core/baja/station/{self.station}/point/{slot_path}/value",
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
                f"{self.base_url}/api/core/baja/station/{self.station}/status",
                headers=self._headers(),
            )
            latency = (time.time() - start) * 1000
            return AdapterHealth(
                connected=True, latency_ms=latency,
                details={"station": self.station},
            )
        except Exception as e:
            return AdapterHealth(connected=False, error=str(e))

    async def disconnect(self):
        await self._client.aclose()
        await super().disconnect()
