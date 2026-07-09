"""
Dickson DicksonOne Cloud Adapter

Connects to Dickson's DicksonOne cloud platform for wireless temperature
and humidity data loggers used in cold storage, pharma, and food facilities.

Auth: API key (Bearer token) — created under Manage > API Keys in DicksonOne
Docs: https://www.dicksonone.com/api/rest/docs
Note: Requires a yearly compliance plan (not monthly Stripe plans)

We use the V2 API for polling since it returns current channel values inline,
and the REST API for discovery and health checks.
"""

import time
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.integrations.base import (
    BaseAdapter, TelemetryReading, DiscoveredDevice,
    WriteCommand, WriteResult, AdapterHealth,
)

REST_BASE = "https://www.dicksonone.com/api/rest"
V2_BASE = "https://www.dicksonone.com/api/v2"

UNIT_MAP = {
    "f": "degF",
    "c": "degC",
    "%rh": "%RH",
    "rh": "%RH",
    "ppm": "ppm",
    "psi": "psi",
}


class DicksonDicksonOneAdapter(BaseAdapter):
    provider = "dickson_dicksonone"
    integration_type = "cloud_api"

    def __init__(self, config: dict, credentials: dict | None = None):
        super().__init__(config, credentials)
        self._api_key: str = (credentials or {}).get("api_key", "")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def authenticate(self) -> bool:
        if not self._api_key:
            raise ConnectionError("DicksonOne API key not configured")
        self._authenticated = True
        return True

    def _rest_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    def _v2_headers(self) -> dict:
        return {
            "X-API-KEY": self._api_key,
            "Accept": "application/json",
        }

    async def discover(self) -> list[DiscoveredDevice]:
        """Discover all devices and their sensor channels."""
        await self.authenticate()
        devices = []
        page = 1

        while True:
            resp = await self._client.get(
                f"{REST_BASE}/devices",
                headers=self._rest_headers(),
                params={"page[number]": page, "page[size]": 100},
            )
            resp.raise_for_status()
            body = resp.json()

            for item in body.get("data", []):
                attrs = item.get("attributes", {})
                token = attrs.get("token", item.get("id"))
                device_name = attrs.get("name", f"Device {token}")

                # Fetch channels for this device via V2 (includes current value)
                try:
                    v2_resp = await self._client.get(
                        f"{V2_BASE}/devices/{token}",
                        headers=self._v2_headers(),
                    )
                    v2_resp.raise_for_status()
                    v2_device = v2_resp.json()
                    channels = v2_device.get("channels", [])
                except Exception:
                    channels = []

                available_metrics = [
                    f"ch{ch.get('channel', i+1)}_{ch.get('name', 'unknown').lower().replace(' ', '_')}"
                    for i, ch in enumerate(channels)
                ]

                devices.append(DiscoveredDevice(
                    external_id=token,
                    name=device_name,
                    device_type=_classify_dickson_device(channels),
                    manufacturer="Dickson",
                    model=attrs.get("model_number", ""),
                    protocol="dicksonone_api",
                    address=f"token:{token}",
                    metadata={
                        "serial_number": attrs.get("serial_number"),
                        "last_datapoint_at": attrs.get("last_datapoint_at"),
                        "channel_count": len(channels),
                    },
                    available_metrics=available_metrics,
                ))

            pagination = body.get("meta", {}).get("pagination", {})
            if not pagination.get("next_page"):
                break
            page += 1

        return devices

    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        """Poll current values from DicksonOne loggers.

        device_map entry format:
          {
            "<device_token>": {
              "equipment_id": "<uuid>",
              "metrics": {
                "1": {"metric_name": "zone_temp", "unit": "degF"},  // channel number as key
                "2": {"metric_name": "humidity", "unit": "%RH"},
              },
              // Optional zone sensor linking:
              "zone_id": "<uuid>",
              "sensor_id": "<uuid>",
              "zone_channel": "1",  // which channel number is zone temp
            }
          }
        """
        await self.authenticate()
        readings = []
        now = datetime.now(timezone.utc)

        for token, mapping in device_map.items():
            equipment_id = UUID(mapping["equipment_id"])
            metrics = mapping.get("metrics", {})
            zone_id_str = mapping.get("zone_id")
            sensor_id_str = mapping.get("sensor_id")
            zone_channel = str(mapping.get("zone_channel", "1"))

            try:
                resp = await self._client.get(
                    f"{V2_BASE}/devices/{token}",
                    headers=self._v2_headers(),
                )
                resp.raise_for_status()
                device = resp.json()

                for ch in device.get("channels", []):
                    ch_num = str(ch.get("channel", ""))
                    value = ch.get("value")
                    if value is None:
                        continue

                    raw_unit = ch.get("channel_unit", "f")
                    unit = UNIT_MAP.get(raw_unit.lower(), raw_unit)

                    if ch_num in metrics:
                        metric_cfg = metrics[ch_num]
                        try:
                            readings.append(TelemetryReading(
                                equipment_id=equipment_id,
                                metric_name=metric_cfg["metric_name"],
                                value=float(value),
                                unit=metric_cfg.get("unit", unit),
                                timestamp=now,
                                quality=0,
                            ))
                        except (ValueError, TypeError):
                            continue

                    if zone_id_str and ch_num == zone_channel:
                        try:
                            readings.append(TelemetryReading(
                                equipment_id=equipment_id,
                                metric_name="zone_temp",
                                value=float(value),
                                unit=unit,
                                timestamp=now,
                                quality=0,
                                zone_id=UUID(zone_id_str),
                                sensor_id=UUID(sensor_id_str) if sensor_id_str else None,
                            ))
                        except (ValueError, TypeError):
                            continue

            except httpx.HTTPStatusError:
                continue

        return readings

    async def health_check(self) -> AdapterHealth:
        try:
            await self.authenticate()
            start = time.time()
            resp = await self._client.get(
                f"{REST_BASE}/devices",
                headers=self._rest_headers(),
                params={"page[size]": 1},
            )
            latency = (time.time() - start) * 1000
            resp.raise_for_status()
            return AdapterHealth(connected=True, latency_ms=latency)
        except Exception as e:
            return AdapterHealth(connected=False, error=str(e))

    async def disconnect(self):
        await self._client.aclose()
        await super().disconnect()


def _classify_dickson_device(channels: list) -> str:
    for ch in channels:
        name = (ch.get("name") or ch.get("type") or "").lower()
        if "temp" in name:
            return "temperature_logger"
        if "humid" in name or "rh" in name:
            return "humidity_logger"
    return "data_logger"
