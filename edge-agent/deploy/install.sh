#!/bin/bash
# Kelvex Edge Agent — Quick Install Script
#
# Run on the gateway device (Raspberry Pi, Intel NUC, etc.):
#   curl -sL https://releases.kelvex.io/agent/latest/install.sh | sudo bash
#
# Or manually:
#   chmod +x install.sh && sudo ./install.sh

set -euo pipefail

BINARY_URL="${KELVEX_BINARY_URL:-https://releases.kelvex.io/agent/latest/kelvex-agent-linux-$(dpkg --print-architecture)}"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/kelvex"
DATA_DIR="/var/lib/kelvex"

echo "╔══════════════════════════════════════════╗"
echo "║     Kelvex Edge Agent — Installer        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Check root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./install.sh)"
  exit 1
fi

# Create user
if ! id -u kelvex &>/dev/null; then
  echo "→ Creating kelvex user..."
  useradd -r -s /bin/false -d /var/lib/kelvex kelvex
fi

# Create directories
echo "→ Creating directories..."
mkdir -p "$CONFIG_DIR" "$DATA_DIR"
chown kelvex:kelvex "$DATA_DIR"

# Download binary
echo "→ Downloading agent binary..."
if command -v curl &>/dev/null; then
  curl -sL "$BINARY_URL" -o "$INSTALL_DIR/kelvex-agent"
elif command -v wget &>/dev/null; then
  wget -q "$BINARY_URL" -O "$INSTALL_DIR/kelvex-agent"
else
  echo "ERROR: curl or wget required"
  exit 1
fi
chmod +x "$INSTALL_DIR/kelvex-agent"

# Verify
echo "→ Verifying binary..."
"$INSTALL_DIR/kelvex-agent" -version

# Install systemd service
echo "→ Installing systemd service..."
cat > /etc/systemd/system/kelvex-agent.service <<'EOF'
[Unit]
Description=Kelvex Edge Agent — Compressor Monitoring
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=kelvex
Group=kelvex
ExecStart=/usr/local/bin/kelvex-agent -config /etc/kelvex/agent.yaml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kelvex-agent
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/kelvex
ReadOnlyPaths=/etc/kelvex
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
  echo "  Or download your config from the Kelvex"
  echo "  platform and copy it to $CONFIG_DIR/agent.yaml"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

# Start
echo "→ Starting kelvex-agent..."
systemctl enable kelvex-agent
systemctl start kelvex-agent

echo ""
echo "✓ Kelvex Edge Agent installed and running!"
echo ""
echo "  Dashboard:  http://$(hostname -I | awk '{print $1}'):8080"
echo "  Logs:       journalctl -u kelvex-agent -f"
echo "  Config:     $CONFIG_DIR/agent.yaml"
echo "  Status:     systemctl status kelvex-agent"
echo ""
