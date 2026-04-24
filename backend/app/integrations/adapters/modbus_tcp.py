"""
Modbus TCP Edge Adapter

This runs on the edge agent, NOT in the cloud. It communicates directly
with controllers on the facility's local network via Modbus TCP.

Supports:
  - Emerson E2/E3 controllers (the most common)
  - Danfoss AK-PC 781, AK-SM 800A
  - Allen-Bradley PLCs via Modbus bridge
  - Bitzer IQ modules
  - Heatcraft Beacon II
  - Any Modbus TCP device with a register map

Uses pymodbus for the actual protocol communication.
Register maps define what addresses to read and how to interpret the data.

NOTE: This adapter is designed to be instantiated by the edge agent process,
not by the cloud backend. The cloud backend stores the config; the edge
agent downloads it and runs this adapter locally.
"""

import struct
from datetime import datetime, timezone
from uuid import UUID

from app.integrations.base import (
    BaseAdapter, TelemetryReading, DiscoveredDevice,
    WriteCommand, WriteResult, AdapterHealth,
)


class ModbusTCPAdapter(BaseAdapter):
    """
    Modbus TCP adapter for direct device communication.

    Requires pymodbus to be installed on the edge agent:
      pip install pymodbus

    The register_map in config defines which registers to read.
    """
    provider = "modbus_tcp"
    integration_type = "edge_protocol"

    def __init__(self, config: dict, credentials: dict | None = None):
        super().__init__(config, credentials)
        self.host = config["host"]
        self.port = config.get("port", 502)
        self.slave_id = config.get("slave_id", 1)
        self.timeout = config.get("timeout_sec", 3)
        self.register_map = config.get("register_map_data", {})
        self._client = None  # pymodbus ModbusTcpClient

    async def authenticate(self) -> bool:
        """Modbus has no auth — just connect."""
        try:
            # Lazy import — pymodbus only available on edge agent
            from pymodbus.client import AsyncModbusTcpClient
            self._client = AsyncModbusTcpClient(
                host=self.host,
                port=self.port,
                timeout=self.timeout,
            )
            connected = await self._client.connect()
            self._authenticated = connected
            return connected
        except ImportError:
            raise RuntimeError(
                "pymodbus not installed. This adapter runs on the edge agent. "
                "Install with: pip install pymodbus"
            )
        except Exception as e:
            self._authenticated = False
            raise ConnectionError(f"Modbus TCP connection to {self.host}:{self.port} failed: {e}")

    async def discover(self) -> list[DiscoveredDevice]:
        """
        Modbus doesn't have a native discovery mechanism.
        We scan a range of slave IDs and try to read a holding register.
        """
        if not self._client:
            await self.authenticate()

        devices = []
        scan_range = self.config.get("scan_slave_ids", range(1, 11))

        for slave_id in scan_range:
            try:
                result = await self._client.read_holding_registers(
                    address=0, count=1, slave=slave_id
                )
                if not result.isError():
                    devices.append(DiscoveredDevice(
                        external_id=f"modbus:{self.host}:{self.port}:{slave_id}",
                        name=f"Modbus Device (Slave {slave_id})",
                        device_type="controller",
                        manufacturer="Unknown",
                        protocol="modbus_tcp",
                        address=f"{self.host}:{self.port} slave={slave_id}",
                        metadata={"slave_id": slave_id},
                        available_metrics=[],
                    ))
            except Exception:
                continue

        return devices

    async def poll(self, device_map: dict) -> list[TelemetryReading]:
        """
        Read registers according to the register map.

        The register map defines:
          - address: Modbus register address
          - function_code: 3 (holding) or 4 (input)
          - data_type: int16, uint16, int32, uint32, float32
          - scale: multiply raw value by this
          - offset: add this after scaling
          - unit: engineering unit
        """
        if not self._client or not self._client.connected:
            await self.authenticate()

        readings = []
        now = datetime.now(timezone.utc)
        registers = self.register_map.get("registers", [])

        for ext_id, mapping in device_map.items():
            equipment_id = UUID(mapping["equipment_id"])
            metrics = mapping.get("metrics", {})
            slave_id = mapping.get("slave_id", self.slave_id)

            for reg in registers:
                reg_name = reg.get("name", "")
                if reg_name not in metrics:
                    continue

                cfg = metrics[reg_name]
                address = reg["address"]
                func_code = reg.get("function_code", 3)
                data_type = reg.get("data_type", "int16")
                scale = reg.get("scale", 1.0)
                offset = reg.get("offset", 0.0)
                count = 2 if data_type in ("int32", "uint32", "float32") else 1

                try:
                    if func_code == 3:
                        result = await self._client.read_holding_registers(
                            address=address, count=count, slave=slave_id
                        )
                    elif func_code == 4:
                        result = await self._client.read_input_registers(
                            address=address, count=count, slave=slave_id
                        )
                    else:
                        continue

                    if result.isError():
                        continue

                    raw_value = _decode_registers(result.registers, data_type,
                                                  reg.get("byte_order", "big"))
                    value = raw_value * scale + offset

                    readings.append(TelemetryReading(
                        equipment_id=equipment_id,
                        metric_name=cfg["metric_name"],
                        value=value,
                        unit=cfg.get("unit", reg.get("unit", "")),
                        timestamp=now,
                        quality=0,
                    ))
                except Exception:
                    continue

        return readings

    async def write(self, command: WriteCommand, device_map: dict) -> WriteResult:
        """Write a value to a Modbus register."""
        if not self._client or not self._client.connected:
            await self.authenticate()

        ext_id = None
        reg_def = None
        for eid, mapping in device_map.items():
            if UUID(mapping["equipment_id"]) == command.equipment_id:
                ext_id = eid
                for reg in self.register_map.get("registers", []):
                    for ext_name, cfg in mapping.get("metrics", {}).items():
                        if (cfg["metric_name"] == command.metric_name
                                and reg.get("name") == ext_name
                                and reg.get("access") == "read_write"):
                            reg_def = reg
                            break
                break

        if not ext_id or not reg_def:
            return WriteResult(success=False, message="Register not found or not writable")

        # Safety check
        if reg_def.get("safety_lock"):
            min_val = reg_def.get("min_value")
            max_val = reg_def.get("max_value")
            if min_val is not None and command.value < min_val:
                return WriteResult(success=False, message=f"Value {command.value} below safety minimum {min_val}")
            if max_val is not None and command.value > max_val:
                return WriteResult(success=False, message=f"Value {command.value} above safety maximum {max_val}")

        try:
            scale = reg_def.get("scale", 1.0)
            offset = reg_def.get("offset", 0.0)
            raw_value = int((command.value - offset) / scale)
            slave_id = device_map[ext_id].get("slave_id", self.slave_id)
            write_fc = reg_def.get("write_function_code", 6)

            if write_fc == 6:
                result = await self._client.write_register(
                    address=reg_def["address"], value=raw_value, slave=slave_id
                )
            elif write_fc == 16:
                result = await self._client.write_registers(
                    address=reg_def["address"], values=[raw_value], slave=slave_id
                )
            else:
                return WriteResult(success=False, message=f"Unsupported write function code: {write_fc}")

            if result.isError():
                return WriteResult(success=False, message=f"Modbus write error: {result}")

            return WriteResult(success=True, new_value=command.value)
        except Exception as e:
            return WriteResult(success=False, message=str(e))

    async def health_check(self) -> AdapterHealth:
        try:
            if not self._client or not self._client.connected:
                await self.authenticate()

            # Try reading a single register to verify communication
            import time as _time
            start = _time.time()
            result = await self._client.read_holding_registers(
                address=0, count=1, slave=self.slave_id
            )
            latency = (_time.time() - start) * 1000

            if result.isError():
                return AdapterHealth(connected=False, error=f"Read error: {result}")

            return AdapterHealth(
                connected=True, latency_ms=latency,
                details={"host": self.host, "port": self.port, "slave": self.slave_id},
            )
        except Exception as e:
            return AdapterHealth(connected=False, error=str(e))

    async def disconnect(self):
        if self._client:
            self._client.close()
        await super().disconnect()


def _decode_registers(registers: list[int], data_type: str, byte_order: str = "big") -> float:
    """Decode raw Modbus register values into a float."""
    bo = ">" if byte_order == "big" else "<"

    if data_type == "int16":
        return struct.unpack(f"{bo}h", struct.pack(f"{bo}H", registers[0]))[0]
    elif data_type == "uint16":
        return float(registers[0])
    elif data_type == "int32":
        raw = struct.pack(f"{bo}HH", registers[0], registers[1])
        return struct.unpack(f"{bo}i", raw)[0]
    elif data_type == "uint32":
        raw = struct.pack(f"{bo}HH", registers[0], registers[1])
        return struct.unpack(f"{bo}I", raw)[0]
    elif data_type == "float32":
        raw = struct.pack(f"{bo}HH", registers[0], registers[1])
        return struct.unpack(f"{bo}f", raw)[0]
    else:
        return float(registers[0])
