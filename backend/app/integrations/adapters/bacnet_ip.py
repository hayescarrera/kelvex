"""
BACnet/IP Edge Adapter

Companion to the Modbus TCP adapter — both run on the edge agent.
BACnet (Building Automation and Control Networks) is the dominant
protocol in commercial/industrial HVAC and building automation.

In cold storage, BACnet is used by:
  - Honeywell Spyder controllers
  - JCI FEC (Field Equipment Controllers)
  - Schneider SmartX controllers
  - Danfoss AK-SM 800 (newer models)
  - Carrier i-Vu controllers
  - Many generic DDC controllers

BACnet/IP operates over UDP port 47808 (0xBAC0).

Uses BAC0 library for the actual protocol communication.
Object definitions in the register map define what BACnet objects
to read and how to interpret the data.

NOTE: Like Modbus TCP, this adapter runs on the edge agent, NOT
in the cloud. The cloud backend stores the config; the edge agent
downloads it and runs this adapter locally.
"""

import time as _time
from datetime import datetime, timezone
from uuid import UUID

from app.integrations.base import (
    BaseAdapter, TelemetryReading, DiscoveredDevice,
    WriteCommand, WriteResult, AdapterHealth,
)


# BACnet object type constants
OBJECT_TYPES = {
    "analog-input": 0,
    "analog-output": 1,
    "analog-value": 2,
    "binary-input": 3,
    "binary-output": 4,
    "binary-value": 5,
    "multi-state-input": 13,
    "multi-state-output": 14,
    "multi-state-value": 19,
}

# BACnet engineering units (subset relevant to cold storage)
BACNET_UNITS = {
    62: "degF",
    64: "degC",
    31: "psi",
    53: "percent",
    18: "kW",
    19: "kWh",
    95: "cfm",     # cubic feet per minute
    85: "inH2O",   # inches of water
}


class BACnetIPAdapter(BaseAdapter):
    """
    BACnet/IP adapter for direct device communication.

    Requires BAC0 to be installed on the edge agent:
      pip install BAC0

    The object_map in config defines which BACnet objects to read.
    """
    provider = "bacnet_ip"
    integration_type = "edge_protocol"

    def __init__(self, config: dict, credentials: dict | None = None):
        super().__init__(config, credentials)
        self.target_address = config["address"]  # e.g. "192.168.1.100"
        self.target_device_id = config.get("device_id")  # BACnet device instance
        self.port = config.get("port", 47808)
        self.timeout = config.get("timeout_sec", 10)
        self.network_interface = config.get("network_interface")  # bind to specific NIC
        self.object_map_data = config.get("object_map_data", {})
        self._bacnet = None   # BAC0 lite network
        self._device = None   # BAC0 device handle

    async def authenticate(self) -> bool:
        """BACnet has no auth — just connect to the network."""
        try:
            # Lazy import — BAC0 only available on edge agent
            import BAC0

            # BAC0 runs in its own thread — start a 'lite' instance
            # which is lighter than a full BACnet device
            if self._bacnet is None:
                kwargs = {"port": self.port}
                if self.network_interface:
                    kwargs["ip"] = self.network_interface

                self._bacnet = BAC0.lite(**kwargs)

            self._authenticated = True
            return True
        except ImportError:
            raise RuntimeError(
                "BAC0 not installed. This adapter runs on the edge agent. "
                "Install with: pip install BAC0"
            )
        except Exception as e:
            self._authenticated = False
            raise ConnectionError(f"BACnet/IP network init failed: {e}")

    async def discover(self) -> list[DiscoveredDevice]:
        """
        Discover BACnet devices on the network.

        BACnet has native Who-Is/I-Am discovery — much better than
        Modbus's blind scanning.
        """
        if not self._bacnet:
            await self.authenticate()

        devices = []

        try:
            # Who-Is broadcast — discovers all BACnet devices on the network
            self._bacnet.discover()

            # BAC0 stores discovered devices
            discovered = getattr(self._bacnet, 'discoveredDevices', None) or {}

            for device_id, device_info in discovered.items():
                address = device_info if isinstance(device_info, str) else str(device_info)

                # Try to read device properties for richer metadata
                device_name = f"BACnet Device {device_id}"
                vendor = "Unknown"
                model = None

                try:
                    device_name = self._read_property(
                        address, "device", device_id, "objectName"
                    ) or device_name
                    vendor = self._read_property(
                        address, "device", device_id, "vendorName"
                    ) or vendor
                    model = self._read_property(
                        address, "device", device_id, "modelName"
                    )
                except Exception:
                    pass  # Some devices don't support all properties

                # Get object list to know what points are available
                available_metrics = []
                try:
                    obj_list = self._read_property(
                        address, "device", device_id, "objectList"
                    )
                    if obj_list:
                        for obj_type, obj_instance in obj_list[:200]:
                            type_name = _bacnet_type_to_str(obj_type)
                            if type_name:
                                available_metrics.append(
                                    f"{type_name}:{obj_instance}"
                                )
                except Exception:
                    pass

                devices.append(DiscoveredDevice(
                    external_id=f"bacnet:{address}:{device_id}",
                    name=device_name,
                    device_type="controller",
                    manufacturer=vendor,
                    model=model,
                    protocol="bacnet_ip",
                    address=f"{address} device={device_id}",
                    metadata={
                        "device_instance": device_id,
                        "bacnet_address": address,
                    },
                    available_metrics=available_metrics[:100],
                ))
        except Exception:
            # If broadcast discovery fails, try direct connection
            if self.target_address and self.target_device_id:
                devices.append(DiscoveredDevice(
                    external_id=f"bacnet:{self.target_address}:{self.target_device_id}",
                    name=f"BACnet Device {self.target_device_id}",
                    device_type="controller",
                    manufacturer="Unknown",
                    protocol="bacnet_ip",
                    address=f"{self.target_address} device={self.target_device_id}",
                    metadata={
                        "device_instance": self.target_device_id,
                        "discovery": "direct",
                    },
                    available_metrics=[],
                ))

        return devices

    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        """
        Read BACnet object values according to the object map.

        The object map defines:
          - object_type: analog-input, analog-output, analog-value,
                         binary-input, binary-output, binary-value,
                         multi-state-input, multi-state-output, multi-state-value
          - instance: BACnet object instance number
          - property: usually 'present-value' (default)
          - name: ColdGrid metric name mapping
          - unit: engineering unit override
        """
        if not self._bacnet:
            await self.authenticate()

        readings = []
        now = datetime.now(timezone.utc)
        objects = self.object_map_data.get("objects", [])

        for ext_id, mapping in device_map.items():
            equipment_id = UUID(mapping["equipment_id"])
            metrics = mapping.get("metrics", {})
            # Parse address from ext_id: "bacnet:192.168.1.100:12345"
            parts = ext_id.split(":")
            if len(parts) >= 3:
                device_address = parts[1]
                device_instance = int(parts[2])
            else:
                device_address = self.target_address
                device_instance = self.target_device_id

            for obj in objects:
                obj_name = obj.get("name", "")
                if obj_name not in metrics:
                    continue

                cfg = metrics[obj_name]
                obj_type = obj["object_type"]
                instance = obj["instance"]
                prop = obj.get("property", "present-value")

                try:
                    # Read the BACnet object property
                    # BAC0 format: "address objectType instance property"
                    read_str = (
                        f"{device_address} "
                        f"{obj_type} {instance} "
                        f"{prop}"
                    )
                    raw_value = self._bacnet.read(read_str)

                    if raw_value is None:
                        continue

                    # Apply scale/offset if specified
                    value = float(raw_value)
                    scale = obj.get("scale", 1.0)
                    offset = obj.get("offset", 0.0)
                    value = value * scale + offset

                    # Determine quality from BACnet status flags
                    quality = 0
                    try:
                        status_str = (
                            f"{device_address} "
                            f"{obj_type} {instance} statusFlags"
                        )
                        status = self._bacnet.read(status_str)
                        if status and hasattr(status, '__iter__'):
                            # BACnet status flags: [in-alarm, fault, overridden, out-of-service]
                            if status[1]:  # fault
                                quality = 2
                            elif status[3]:  # out-of-service
                                quality = 3
                    except Exception:
                        pass  # Status flags not always available

                    readings.append(TelemetryReading(
                        equipment_id=equipment_id,
                        metric_name=cfg["metric_name"],
                        value=value,
                        unit=cfg.get("unit", obj.get("unit", "")),
                        timestamp=now,
                        quality=quality,
                    ))
                except Exception:
                    continue

        return readings

    async def write(self, command: WriteCommand, device_map: dict) -> WriteResult:
        """Write a value to a BACnet object (setpoint change, override, etc.)."""
        if not self._bacnet:
            await self.authenticate()

        ext_id = None
        obj_def = None
        for eid, mapping in device_map.items():
            if UUID(mapping["equipment_id"]) == command.equipment_id:
                ext_id = eid
                for obj in self.object_map_data.get("objects", []):
                    for ext_name, cfg in mapping.get("metrics", {}).items():
                        if (cfg["metric_name"] == command.metric_name
                                and obj.get("name") == ext_name
                                and obj.get("access") == "read_write"):
                            obj_def = obj
                            break
                break

        if not ext_id or not obj_def:
            return WriteResult(success=False, message="Object not found or not writable")

        # Safety check
        min_val = obj_def.get("min_value")
        max_val = obj_def.get("max_value")
        if min_val is not None and command.value < min_val:
            return WriteResult(
                success=False,
                message=f"Value {command.value} below safety minimum {min_val}"
            )
        if max_val is not None and command.value > max_val:
            return WriteResult(
                success=False,
                message=f"Value {command.value} above safety maximum {max_val}"
            )

        try:
            # Parse address
            parts = ext_id.split(":")
            if len(parts) >= 3:
                device_address = parts[1]
            else:
                device_address = self.target_address

            # Reverse scale/offset to get raw value
            scale = obj_def.get("scale", 1.0)
            offset = obj_def.get("offset", 0.0)
            raw_value = (command.value - offset) / scale

            obj_type = obj_def["object_type"]
            instance = obj_def["instance"]
            prop = obj_def.get("property", "present-value")

            # BACnet write with priority (default 16 = manual operator)
            priority = obj_def.get("write_priority", 16)
            write_str = (
                f"{device_address} "
                f"{obj_type} {instance} "
                f"{prop} {raw_value} "
                f"- {priority}"
            )
            self._bacnet.write(write_str)

            return WriteResult(success=True, new_value=command.value)
        except Exception as e:
            return WriteResult(success=False, message=str(e))

    async def health_check(self) -> AdapterHealth:
        try:
            if not self._bacnet:
                await self.authenticate()

            start = _time.time()

            # Try reading the device object name as a connectivity check
            if self.target_address and self.target_device_id:
                read_str = (
                    f"{self.target_address} "
                    f"device {self.target_device_id} objectName"
                )
                result = self._bacnet.read(read_str)
                latency = (_time.time() - start) * 1000

                if result is None:
                    return AdapterHealth(connected=False, error="No response from device")

                return AdapterHealth(
                    connected=True, latency_ms=latency,
                    details={
                        "address": self.target_address,
                        "device_id": self.target_device_id,
                        "device_name": str(result),
                    },
                )
            else:
                # No specific target — just check network is up
                latency = (_time.time() - start) * 1000
                return AdapterHealth(
                    connected=True, latency_ms=latency,
                    details={"network_only": True},
                )
        except Exception as e:
            return AdapterHealth(connected=False, error=str(e))

    async def disconnect(self):
        if self._bacnet:
            try:
                self._bacnet.disconnect()
            except Exception:
                pass
            self._bacnet = None
        await super().disconnect()

    def _read_property(self, address: str, obj_type: str,
                       instance: int, prop: str):
        """Helper to read a single BACnet property."""
        return self._bacnet.read(f"{address} {obj_type} {instance} {prop}")


def _bacnet_type_to_str(type_num: int) -> str | None:
    """Convert BACnet object type number to string."""
    reverse_map = {v: k for k, v in OBJECT_TYPES.items()}
    return reverse_map.get(type_num)
