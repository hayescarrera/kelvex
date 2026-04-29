# Kelvex Edge Agent — On-Site Installation Guide

The edge agent is a lightweight Go binary that runs on a gateway device at your facility and streams compressor telemetry to the Kelvex platform over HTTPS. It supports Modbus TCP out of the box, with BACnet and EtherNet/IP support available on request.

---

## Requirements

| | Minimum |
|---|---|
| Hardware | Raspberry Pi 4 (4 GB), Intel NUC, or any x86-64 Linux box |
| OS | Raspberry Pi OS (64-bit) or Ubuntu Server 22.04+ |
| Network | HTTPS outbound to `app.kelvex.io` on port 443 |
| LAN access | Must reach controller IPs over Modbus TCP (default port 502) |

---

## Step 1 — Register the agent in the Kelvex UI

1. Log in → open your facility → **Settings → Edge Agents → + Add Agent**
2. Enter a name (e.g., `warehouse-01`) and click **Register**
3. Copy the **Agent Key** shown — you will need it in the next step (`ag_xxxxxxxxxxxx`)

The agent key is the credential the binary uses to authenticate to the platform. Keep it secure; it can be rotated from the same settings panel.

---

## Step 2 — Install on the gateway device

SSH into the device, then run:

```bash
curl -sL https://releases.kelvex.io/agent/latest/install.sh | sudo bash
```

The installer:
- Creates a `kelvex` system user
- Downloads the correct binary for your architecture (arm64 / armv7 / amd64)
- Installs a hardened systemd service with auto-restart
- Opens a local configuration UI at `http://<device-ip>:8080`

**Offline install:** Download the binary for your architecture from the releases page, copy it to the device, then run `sudo ./install.sh` from the `edge-agent/deploy/` directory.

---

## Step 3 — Configure the agent

Create `/etc/kelvex/agent.yaml`:

```yaml
agent:
  name: "warehouse-01"
  key: "ag_xxxxxxxxxxxx"          # paste key from Step 1

platform:
  url: "https://app.kelvex.io"
  heartbeat_interval_sec: 30

devices:
  - name: "comp-1"
    host: "192.168.1.10"          # controller IP on your LAN
    port: 502
    slave_id: 1
    protocol: "modbus_tcp"
    poll_interval_sec: 15
    compressor_id: "..."          # UUID from Kelvex UI (Settings → Compressors)
    registers:
      discharge_pressure: { register: 40001, type: holding, data_type: float32, unit: psi }
      suction_pressure:   { register: 40003, type: holding, data_type: float32, unit: psi }
      oil_temp:           { register: 40009, type: holding, data_type: float32, unit: "°F" }
      amp_draw:           { register: 40015, type: holding, data_type: float32, unit: A }
      kw:                 { register: 40017, type: holding, data_type: float32, unit: kW }
      slide_valve_pct:    { register: 40019, type: holding, data_type: float32, unit: "%" }
      running:            { register: 40021, type: holding, data_type: uint16, unit: bool }

local:
  web_port: 8080
  buffer_path: "/var/lib/kelvex/buffer.db"
  buffer_max_mb: 500              # up to 72 hours of offline buffering
```

Register file addresses vary by controller model. See the [Register Map Reference](./register-maps.md) for Frick Quantum HD, GEA Omni, and Johnson Controls defaults.

---

## Step 4 — Start the service

```bash
sudo systemctl restart kelvex-agent
sudo systemctl status kelvex-agent
```

Within 30 seconds the agent should appear **Online** in the Kelvex facility dashboard.

**View live logs:**
```bash
journalctl -u kelvex-agent -f
```

---

## Local web UI

The agent runs a lightweight dashboard at `http://<device-ip>:8080` that shows:
- Current telemetry readings and poll status
- Connectivity state to the platform
- Discovered devices on the local subnet
- Buffer fill level (used when offline)

Useful for on-site commissioning and troubleshooting without needing cloud access.

---

## Offline buffering

The agent writes all readings to a local SQLite database (`buffer.db`) before uploading. If the internet connection drops, readings continue locally and are uploaded automatically when connectivity is restored. Default buffer capacity is 500 MB (~72 hours at 15-second poll intervals for 6 compressors).

---

## Testing with the simulator

No physical controllers on hand? Run the Modbus simulator included with the platform:

```bash
cd kelvex/simulator
pip install pymodbus
python compressor_sim.py --model frick --port 5020
```

Then point `host: "127.0.0.1"` and `port: 5020` in your `agent.yaml`. This simulates a Frick Quantum HD with realistic pressure, temperature, and amp-draw patterns.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Agent shows Offline in UI | `journalctl -u kelvex-agent -f` — look for auth errors or DNS failures |
| No telemetry but Online | Verify controller IP and port 502 are reachable: `nc -zv 192.168.1.10 502` |
| Wrong readings | Confirm register addresses match your controller firmware version |
| Agent key rejected | Rotate the key in Settings → Edge Agents and update `agent.yaml` |

---

## Rotating the agent key

1. Kelvex UI → Facility → Settings → Edge Agents → **Rotate Key**
2. Copy the new key
3. Update `/etc/kelvex/agent.yaml`
4. `sudo systemctl restart kelvex-agent`

Old key is immediately invalidated upon rotation.
