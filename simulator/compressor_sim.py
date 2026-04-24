#!/usr/bin/env python3
"""
Frigor Modbus Compressor Simulator — emulates Frick Quantum HD and GEA Omni
controllers with realistic ammonia screw compressor behavior.

Runs a Modbus TCP server on port 502 (or any port) that responds to reads
exactly like a real controller. The simulated data follows realistic patterns:
- Discharge pressure cycles with load
- Suction pressure tracks setpoint with small variance
- Oil temp rises gradually over operating hours
- Slide valve modulates with demand
- Occasional fault injection for testing alerts

Usage:
  pip install pymodbus
  python compressor_sim.py                          # Default: Frick on port 5020
  python compressor_sim.py --model gea --port 5021  # GEA on 5021
  python compressor_sim.py --model frick --port 5020 --fault-inject  # With random faults

The simulator is for demos and testing. Point the Frigor edge agent at
localhost:<port> instead of a real controller IP.
"""

import argparse
import asyncio
import math
import random
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("compressor-sim")

try:
    from pymodbus.server import StartAsyncTcpServer
    from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
    from pymodbus.datastore import ModbusSequentialDataBlock
except ImportError:
    print("Install pymodbus: pip install pymodbus")
    print("  pip install pymodbus --break-system-packages")
    exit(1)


# ── Frick Quantum HD Register Layout ────────────

FRICK_REGISTERS = {
    # address (0-based offset from 40001): (name, initial_value)
    300: ("suction_pressure", 280),        # 28.0 PSI (x10)
    301: ("discharge_pressure", 1680),      # 168.0 PSI (x10)
    302: ("oil_pressure", 580),             # 58.0 PSI (x10)
    303: ("oil_filter_dp", 85),             # 8.5 PSI (x10)
    304: ("economizer_pressure", 420),      # 42.0 PSI (x10)
    310: ("suction_temp", -225),            # -22.5 °F (x10, signed)
    311: ("discharge_temp", 1850),          # 185.0 °F (x10)
    312: ("oil_temp", 1420),               # 142.0 °F (x10)
    313: ("bearing_temp", 1560),           # 156.0 °F (x10)
    320: ("motor_amps", 2180),             # 218.0 A (x10)
    321: ("motor_kw", 1850),               # 185.0 kW (x10)
    322: ("compressor_rpm", 3560),         # 3560 RPM
    323: ("vibration", 15),                # 0.15 in/s (x100)
    330: ("slide_valve_pct", 75),          # 75%
    340: ("run_hours_hi", 0),              # uint32 high word
    341: ("run_hours_lo", 28450),          # uint32 low word = 28,450 hours
    350: ("compressor_status", 1),         # 1 = running
    351: ("active_fault", 0),              # 0 = no fault
    360: ("capacity_setpoint", 80),        # 80%
    361: ("suction_pressure_sp", 280),     # 28.0 PSI setpoint
}

# ── GEA Omni Register Layout ────────────────────

GEA_REGISTERS = {
    500: ("suction_pressure", 265),        # 26.5 PSI (x10)
    501: ("discharge_pressure", 1720),      # 172.0 PSI (x10)
    502: ("oil_pressure", 610),             # 61.0 PSI (x10)
    510: ("suction_temp", -245),            # -24.5 °F (x10, signed)
    511: ("discharge_temp", 1910),          # 191.0 °F (x10)
    512: ("oil_temp", 1380),               # 138.0 °F (x10)
    513: ("winding_temp", 1650),           # 165.0 °F (x10)
    520: ("motor_current", 1950),          # 195.0 A (x10)
    521: ("motor_power", 1620),            # 162.0 kW (x10)
    522: ("compressor_speed", 2950),       # 2950 RPM (VFD)
    523: ("slide_valve_pct", 70),          # 70% volume ratio
    540: ("run_hours_hi", 0),              # uint32 high
    541: ("run_hours_lo", 19200),          # 19,200 hours
    550: ("compressor_status", 1),         # 1 = running
    551: ("fault_code", 0),                # 0 = no fault
    552: ("oil_level", 82),                # 82%
    560: ("subcooling", 85),               # 8.5 °F (x10)
    561: ("superheat", 120),               # 12.0 °F (x10)
    570: ("capacity_setpoint", 75),        # 75%
}

# ── Fault codes ─────────────────────────────────

FRICK_FAULTS = {
    0: "No Fault",
    1: "High Discharge Pressure",
    2: "Low Suction Pressure",
    3: "High Oil Temperature",
    4: "Low Oil Pressure",
    5: "High Motor Amps",
    6: "High Vibration",
    7: "High Bearing Temperature",
    8: "Oil Filter Differential High",
    10: "Communication Fault",
    12: "Emergency Stop",
}

GEA_FAULTS = {
    0: "No Fault",
    1: "Discharge Pressure High",
    2: "Suction Pressure Low",
    3: "Oil Temperature High",
    4: "Oil Pressure Low",
    5: "Motor Overcurrent",
    6: "Winding Temperature High",
    7: "Oil Level Low",
    8: "VFD Fault",
    10: "Sensor Failure",
}


class CompressorSimulator:
    """Simulates realistic ammonia screw compressor behavior."""

    def __init__(self, model: str, fault_inject: bool = False):
        self.model = model
        self.fault_inject = fault_inject
        self.registers = dict(FRICK_REGISTERS if model == "frick" else GEA_REGISTERS)
        self.start_time = time.time()
        self.cycle = 0
        self._fault_active = False
        self._fault_start = 0

        # Operating parameters for realistic simulation
        self.load_demand = 0.75  # 0.0 to 1.0
        self.ambient_temp = 85.0  # °F outside

    def get_register_offset(self):
        """Base offset for this model's registers."""
        return 300 if self.model == "frick" else 500

    def update(self):
        """Update all register values with realistic behavior."""
        self.cycle += 1
        t = time.time() - self.start_time
        hour_of_day = (time.localtime().tm_hour + time.localtime().tm_min / 60)

        # Load demand varies with time of day (higher during business hours)
        base_load = 0.5 + 0.3 * math.sin((hour_of_day - 6) * math.pi / 12)
        self.load_demand = max(0.3, min(0.95, base_load + random.uniform(-0.05, 0.05)))

        # Slide valve tracks load demand
        slide_target = int(self.load_demand * 100)
        current_slide = self._get("slide_valve_pct") if self.model == "frick" else self._get("slide_valve_pct")
        new_slide = current_slide + int((slide_target - current_slide) * 0.1)
        self._set_by_name("slide_valve_pct", max(10, min(100, new_slide)))

        # Suction pressure — tracks setpoint with small variance
        sp_name = "suction_pressure_sp" if self.model == "frick" else "suction_pressure"
        base_suction = self._get(sp_name) if self.model == "frick" else 265
        suction = base_suction + random.randint(-8, 8)
        self._set_by_name("suction_pressure", suction)

        # Discharge pressure — function of load and ambient
        base_discharge = 1500 + int(self.load_demand * 300) + int(self.ambient_temp * 2)
        discharge = base_discharge + random.randint(-20, 20)
        self._set_by_name("discharge_pressure", discharge)

        # Oil pressure — tracks discharge with offset
        oil_p = discharge - 900 + random.randint(-10, 10)
        self._set_by_name("oil_pressure", max(300, oil_p))

        # Temperatures
        # Discharge temp correlates with pressure ratio
        ratio = discharge / max(suction, 100)
        discharge_temp = 1200 + int(ratio * 80) + random.randint(-15, 15)
        self._set_by_name("discharge_temp", discharge_temp)

        # Suction temp — low, correlates with suction pressure
        suction_temp = -300 + int(suction * 0.3) + random.randint(-10, 10)
        self._set_by_name("suction_temp", suction_temp)

        # Oil temp — rises slowly, affected by load
        oil_temp = 1300 + int(self.load_demand * 200) + random.randint(-10, 10)
        self._set_by_name("oil_temp", oil_temp)

        # Bearing/winding temp
        bearing_key = "bearing_temp" if self.model == "frick" else "winding_temp"
        bearing = 1400 + int(self.load_demand * 250) + random.randint(-15, 15)
        self._set_by_name(bearing_key, bearing)

        # Motor amps — proportional to load
        base_amps = 800 + int(self.load_demand * 1600)
        amps = base_amps + random.randint(-20, 20)
        amp_key = "motor_amps" if self.model == "frick" else "motor_current"
        self._set_by_name(amp_key, amps)

        # Power — derived from amps (rough)
        power = int(amps * 0.85)  # approximate power factor
        power_key = "motor_kw" if self.model == "frick" else "motor_power"
        self._set_by_name(power_key, power)

        # RPM — fixed for direct drive, variable for VFD (GEA)
        if self.model == "frick":
            self._set_by_name("compressor_rpm", 3560 + random.randint(-5, 5))
        else:
            target_rpm = 1800 + int(self.load_demand * 1400)
            self._set_by_name("compressor_speed", target_rpm + random.randint(-10, 10))

        # Vibration (Frick only)
        if self.model == "frick":
            base_vib = 10 + int(self.load_demand * 8)
            self._set_by_name("vibration", base_vib + random.randint(-2, 3))

        # Oil filter DP (Frick only)
        if self.model == "frick":
            self._set_by_name("oil_filter_dp", 80 + random.randint(-5, 10))

        # Economizer (Frick only)
        if self.model == "frick":
            econ = int(suction * 1.5) + random.randint(-5, 5)
            self._set_by_name("economizer_pressure", max(200, econ))

        # Oil level / subcooling / superheat (GEA only)
        if self.model == "gea":
            self._set_by_name("oil_level", 80 + random.randint(-3, 3))
            self._set_by_name("subcooling", 75 + random.randint(-10, 10))
            self._set_by_name("superheat", 100 + int(self.load_demand * 40) + random.randint(-8, 8))

        # Run hours — increment every 60 cycles (~60 seconds)
        if self.cycle % 60 == 0:
            lo_key = "run_hours_lo"
            lo = self._get(lo_key) + 1
            self._set_by_name(lo_key, lo)

        # Fault injection
        if self.fault_inject:
            self._maybe_inject_fault()

    def _maybe_inject_fault(self):
        """Randomly inject and clear faults for testing alerts."""
        fault_key = "active_fault" if self.model == "frick" else "fault_code"
        status_key = "compressor_status"
        faults = FRICK_FAULTS if self.model == "frick" else GEA_FAULTS

        if self._fault_active:
            # Clear fault after 30-120 seconds
            if time.time() - self._fault_start > random.randint(30, 120):
                self._set_by_name(fault_key, 0)
                self._set_by_name(status_key, 1)  # back to running
                self._fault_active = False
                logger.info("Fault cleared — compressor back to running")
        else:
            # 0.5% chance per update cycle to inject a fault
            if random.random() < 0.005:
                fault_code = random.choice([k for k in faults.keys() if k != 0])
                self._set_by_name(fault_key, fault_code)
                self._set_by_name(status_key, 2)  # fault state
                self._fault_active = True
                self._fault_start = time.time()
                logger.warning(f"FAULT INJECTED: code {fault_code} — {faults[fault_code]}")

    def _get(self, name_or_key):
        """Get register value by name."""
        for offset, (name, _) in self.registers.items():
            if name == name_or_key:
                return self.registers[offset][1]
        return 0

    def _set_by_name(self, name: str, value: int):
        """Set register value by name."""
        for offset, (n, _) in list(self.registers.items()):
            if n == name:
                self.registers[offset] = (n, value)
                return

    def get_datablock_values(self):
        """Get all register values as a list for the Modbus datablock."""
        base = self.get_register_offset()
        # Create a block large enough to cover all registers
        max_offset = max(self.registers.keys())
        size = max_offset - base + 10
        values = [0] * size
        for offset, (name, val) in self.registers.items():
            idx = offset - base
            if 0 <= idx < size:
                # Handle signed values — Modbus uses unsigned 16-bit
                if val < 0:
                    val = val + 65536
                values[idx] = val & 0xFFFF
        return values


async def run_updater(sim: CompressorSimulator, context: ModbusServerContext, interval: float = 1.0):
    """Background task that updates register values periodically."""
    base = sim.get_register_offset()
    while True:
        sim.update()
        values = sim.get_datablock_values()
        # Write values to the holding register datablock (function code 3)
        store = context[0]
        for i, val in enumerate(values):
            try:
                store.setValues(3, base + i + 1, [val])  # +1 because Modbus addresses are 1-indexed
            except Exception:
                pass
        await asyncio.sleep(interval)


async def main(model: str, port: int, fault_inject: bool):
    """Start the Modbus TCP server."""
    sim = CompressorSimulator(model=model, fault_inject=fault_inject)

    # Create initial datablock with enough space
    # Holding registers: function code 3, addresses 1-1000
    block = ModbusSequentialDataBlock(1, [0] * 1000)
    store = ModbusSlaveContext(hr=block)
    context = ModbusServerContext(slaves=store, single=True)

    # Set initial values
    base = sim.get_register_offset()
    values = sim.get_datablock_values()
    for i, val in enumerate(values):
        try:
            store.setValues(3, base + i + 1, [val])
        except Exception:
            pass

    model_name = "Frick Quantum HD" if model == "frick" else "GEA Omni"
    faults = FRICK_FAULTS if model == "frick" else GEA_FAULTS

    logger.info(f"Starting {model_name} Modbus simulator on port {port}")
    logger.info(f"  Registers: {base + 1} — {base + len(values)}")
    logger.info(f"  Fault injection: {'ON' if fault_inject else 'OFF'}")
    logger.info(f"  Connect your agent to: localhost:{port}")
    logger.info("")
    logger.info(f"  Fault codes for {model_name}:")
    for code, desc in faults.items():
        logger.info(f"    {code}: {desc}")

    # Start the update loop
    updater = asyncio.create_task(run_updater(sim, context, interval=1.0))

    # Start Modbus TCP server
    await StartAsyncTcpServer(
        context=context,
        address=("0.0.0.0", port),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Frigor Modbus Compressor Simulator")
    parser.add_argument("--model", choices=["frick", "gea"], default="frick",
                        help="Controller model to simulate (default: frick)")
    parser.add_argument("--port", type=int, default=5020,
                        help="Modbus TCP port (default: 5020)")
    parser.add_argument("--fault-inject", action="store_true",
                        help="Enable random fault injection for testing alerts")
    args = parser.parse_args()

    asyncio.run(main(args.model, args.port, args.fault_inject))
