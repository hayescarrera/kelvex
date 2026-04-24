"""
Emerson Oversight (formerly Facility IQ) Cloud Adapter

Connects to Emerson's cloud platform for E2/E3 controllers, CoreSense
diagnostics, and Vilter/ProAct industrial systems.

Auth: API key + bearer token (proprietary)
Docs: Partner-gated — requires Emerson Connected Services agreement

This is the #1 controller platform in US mid-market cold storage.
E2 controllers are in more cold warehouses than anything else.
"""

import time
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.integrations.base import (
    BaseAdapter, TelemetryReading, DiscoveredDevice,
    WriteCommand, WriteResult, AdapterHealth,
)


class EmersonOversightAdapter(BaseAdapter):
    provider = "emerson_oversight"
    integration_type = "cloud_api"

    DEFAULT_BASE_URL = "https://api.oversight.emerson.com"

    def __init__(self, config: dict, credentials: dict | None = None):
        super().__init__(config, credentials)
        self.base_url = config.get("base_url", self.DEFAULT_BASE_URL)
        self.site_id = config.get("site_id")
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._client = httpx.AsyncClient(timeout=30.0)

    async def authenticate(self) -> bool:
        """Emerson uses API key + secret to get a session token."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return True

        try:
            resp = await self._client.post(
                f"{self.base_url}/v1/auth/token",
                json={
                    "api_key": self.credentials["api_key"],
                    "api_secret": self.credentials["api_secret"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600)
            self._authenticated = True
            return True
        except Exception as e:
            self._authenticated = False
            raise ConnectionError(f"Emerson Oversight auth failed: {e}")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def discover(self) -> list[DiscoveredDevice]:
        """Discover E2/E3 controllers and their connected circuits/racks."""
        await self.authenticate()
        devices = []

        resp = await self._client.get(
            f"{self.base_url}/v1/sites/{self.site_id}/controllers",
            headers=self._headers(),
        )
        resp.raise_for_status()

        for ctrl in resp.json().get("controllers", []):
            ctrl_id = ctrl["id"]

            # Get available data points
            points_resp = await self._client.get(
                f"{self.base_url}/v1/controllers/{ctrl_id}/points",
                headers=self._headers(),
            )
            points_resp.raise_for_status()
            points = points_resp.json().get("points", [])

            devices.append(DiscoveredDevice(
                external_id=ctrl_id,
                name=ctrl.get("name", f"E2-{ctrl_id}"),
                device_type=_classify_emerson_device(ctrl),
                manufacturer="Emerson",
                model=ctrl.get("model", "E2"),
                protocol="emerson_api",
                address=f"site:{self.site_id}/ctrl:{ctrl_id}",
                metadata={
                    "firmware": ctrl.get("firmware"),
                    "serial": ctrl.get("serial_number"),
                    "controller_type": ctrl.get("type"),
                    "online": ctrl.get("status") == "online",
                },
                available_metrics=[p["name"] for p in points],
            ))

            # E2 controllers manage sub-devices (circuits, racks)
            # Discover those too
            circuits_resp = await self._client.get(
                f"{self.base_url}/v1/controllers/{ctrl_id}/circuits",
                headers=self._headers(),
            )
            if circuits_resp.status_code == 200:
                for circuit in circuits_resp.json().get("circuits", []):
                    devices.append(DiscoveredDevice(
                        external_id=f"{ctrl_id}:{circuit['id']}",
                        name=circuit.get("name", f"Circuit-{circuit['id']}"),
                        device_type=_classify_emerson_circuit(circuit),
                        manufacturer="Emerson",
                        model="E2 Circuit",
                        protocol="emerson_api",
                        address=f"ctrl:{ctrl_id}/circuit:{circuit['id']}",
                        metadata={"parent_controller": ctrl_id},
                        available_metrics=circuit.get("available_points", []),
                    ))

        return devices

    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        """Poll current values from E2/E3 controllers."""
        await self.authenticate()
        readings = []
        now = datetime.now(timezone.utc)

        for ext_id, mapping in device_map.items():
            equipment_id = UUID(mapping["equipment_id"])
            metrics = mapping.get("metrics", {})

            try:
                # Determine if this is a controller or circuit
                parts = ext_id.split(":")
                if len(parts) == 1:
                    # Direct controller
                    url = f"{self.base_url}/v1/controllers/{ext_id}/points/values"
                else:
                    # Circuit under a controller
                    ctrl_id, circuit_id = parts[0], parts[1]
                    url = f"{self.base_url}/v1/controllers/{ctrl_id}/circuits/{circuit_id}/values"

                resp = await self._client.get(url, headers=self._headers())
                resp.raise_for_status()

                for point in resp.json().get("values", []):
                    point_name = point.get("name", "")
                    if point_name in metrics:
                        metric_cfg = metrics[point_name]
                        value = point.get("value")
                        if value is not None:
                            try:
                                readings.append(TelemetryReading(
                                    equipment_id=equipment_id,
                                    metric_name=metric_cfg["metric_name"],
                                    value=float(value),
                                    unit=metric_cfg.get("unit", point.get("unit", "")),
                                    timestamp=now,
                                    quality=0,
                                ))
                            except (ValueError, TypeError):
                                continue
            except Exception:
                continue

        return readings

    async def write(self, command: WriteCommand, device_map: dict) -> WriteResult:
        """Write setpoints to E2 controllers (limited — most E2 setpoints are read-only via API)."""
        await self.authenticate()

        ext_id = None
        param_name = None
        for eid, mapping in device_map.items():
            if UUID(mapping["equipment_id"]) == command.equipment_id:
                ext_id = eid
                for ext_name, cfg in mapping.get("metrics", {}).items():
                    if cfg["metric_name"] == command.metric_name and cfg.get("access") == "read_write":
                        param_name = ext_name
                        break
                break

        if not ext_id or not param_name:
            return WriteResult(success=False, message="Device/parameter not found or not writable")

        try:
            resp = await self._client.post(
                f"{self.base_url}/v1/controllers/{ext_id}/commands",
                headers=self._headers(),
                json={"point": param_name, "value": command.value, "source": "coldgrid"},
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


def _classify_emerson_device(ctrl: dict) -> str:
    ctrl_type = (ctrl.get("type") or "").lower()
    if "rack" in ctrl_type or "compressor" in ctrl_type:
        return "compressor"
    elif "condenser" in ctrl_type:
        return "condenser"
    return "controller"


def _classify_emerson_circuit(circuit: dict) -> str:
    ctype = (circuit.get("type") or "").lower()
    if "suction" in ctype or "rack" in ctype:
        return "compressor"
    elif "case" in ctype or "evap" in ctype or "cooler" in ctype:
        return "evaporator"
    elif "cond" in ctype:
        return "condenser"
    return "controller"
