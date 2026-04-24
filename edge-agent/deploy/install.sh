#!/bin/bash
# ColdGrid Edge Agent — Quick Install Script
#
# Run on the gateway device (Raspberry Pi, Intel NUC, etc.):
#   curl -sL https://install.coldgrid.io/agent | bash
#
# Or manually:
#   chmod +x install.sh && sudo ./install.sh

set -euo pipefail

BINARY_URL="${COLDGRID_BINARY_URL:-https://releases.coldgrid.io/agent/latest/coldgrid-agent-linux-$(dpkg --print-architecture)}"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/coldgrid"
DATA_DIR="/var/lib/coldgrid"

echo "╔══════════════════════════════════════════╗"
echo "║    ColdGrid Edge Agent — Installer       ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./install.sh)"
  exit 1
fi

# Create user
if ! id -u coldgrid &>/dev/null; then
  echo "→ Creating coldgrid user..."
  useradd -r -s /bin/false -d /var/lib/coldgrid coldgrid
fi

# Create directories
echo "→ Creating directories..."
mkdir -p "$CONFIG_DIR" "$DATA_DIR"
chown coldgrid:coldgrid "$DATA_DIR"

# Download binary
echo "→ Downloading agent binary..."
if command -v curl &>/dev/null; then
  curl -sL "$BINARY_URL" -o "$INSTALL_DIR/coldgrid-agent"
elif command -v wget &>/dev/null; then
  wget -q "$BINARY_URL" -O "$INSTALL_DIR/coldgrid-agent"
else
  echo "ERROR: curl or wget required"
  exit 1
fi
chmod +x "$INSTALL_DIR/coldgrid-agent"

# Verify
echo "→ Verifying binary..."
"$INSTALL_DIR/coldgrid-agent" -version

# Install systemd service
echo "→ Installing systemd service..."
cat > /etc/systemd/system/coldgrid-agent.service <<'EOF'
[Unit]
Description=ColdGrid Edge Agent — Compressor Monitoring
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=coldgrid
Group=coldgrid
ExecStart=/usr/local/bin/coldgrid-agent -config /etc/coldgrid/agent.yaml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=coldgrid-agent
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/coldgrid
ReadOnlyPaths=/etc/coldgrid
MemoryMax=256M

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# Check for config
if [ ! -f "$CONFIG_DIR/agent.yaml" ]; then
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  No config found at $CONFIG_DIR/agent.yaml"
  echo ""
  echo "  The agent will start in bootstrap mode."
  echo "  Open http://$(hostname -I | awk '{print $1}'):8080"
  echo "  in your browser to configure."
  echo ""
  echo "  Or download your config from the ColdGrid"
  echo "  platform and copy it to $CONFIG_DIR/agent.yaml"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

# Start
echo "→ Starting coldgrid-agent..."
systemctl enable coldgrid-agent
systemctl start coldgrid-agent

echo ""
echo "✓ ColdGrid Edge Agent installed and running!"
echo ""
echo "  Dashboard:  http://$(hostname -I | awk '{print $1}'):8080"
echo "  Logs:       journalctl -u coldgrid-agent -f"
echo "  Config:     $CONFIG_DIR/agent.yaml"
echo "  Status:     systemctl status coldgrid-agent"
echo ""
