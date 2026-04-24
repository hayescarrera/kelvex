# ColdGrid Edge Agent — Build System
#
# Targets:
#   make build          Build for current platform
#   make build-arm      Cross-compile for ARM64 (Raspberry Pi 4, etc.)
#   make build-arm7     Cross-compile for ARMv7 (older Pi, industrial SBCs)
#   make build-all      Build all platform targets
#   make docker          Build Docker image for ARM64
#   make clean           Remove build artifacts
#   make test            Run tests
#   make install         Install to /usr/local/bin

BINARY     := coldgrid-agent
MODULE     := github.com/coldgrid/edge-agent
VERSION    ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_TIME := $(shell date -u '+%Y-%m-%dT%H:%M:%SZ')

LDFLAGS := -s -w \
	-X main.Version=$(VERSION) \
	-X main.GitCommit=$(GIT_COMMIT) \
	-X main.BuildTime=$(BUILD_TIME)

BUILD_DIR := build

.PHONY: build build-arm build-arm7 build-all docker clean test install

build:
	@echo "Building $(BINARY) $(VERSION) for $$(go env GOOS)/$$(go env GOARCH)..."
	@mkdir -p $(BUILD_DIR)
	CGO_ENABLED=1 go build -ldflags "$(LDFLAGS)" -o $(BUILD_DIR)/$(BINARY) ./cmd/coldgrid-agent

build-arm:
	@echo "Cross-compiling $(BINARY) $(VERSION) for linux/arm64..."
	@mkdir -p $(BUILD_DIR)
	CGO_ENABLED=1 CC=aarch64-linux-gnu-gcc \
		GOOS=linux GOARCH=arm64 \
		go build -ldflags "$(LDFLAGS)" -o $(BUILD_DIR)/$(BINARY)-linux-arm64 ./cmd/coldgrid-agent

build-arm7:
	@echo "Cross-compiling $(BINARY) $(VERSION) for linux/arm (v7)..."
	@mkdir -p $(BUILD_DIR)
	CGO_ENABLED=1 CC=arm-linux-gnueabihf-gcc \
		GOOS=linux GOARCH=arm GOARM=7 \
		go build -ldflags "$(LDFLAGS)" -o $(BUILD_DIR)/$(BINARY)-linux-armv7 ./cmd/coldgrid-agent

build-amd64:
	@echo "Building $(BINARY) $(VERSION) for linux/amd64..."
	@mkdir -p $(BUILD_DIR)
	CGO_ENABLED=1 GOOS=linux GOARCH=amd64 \
		go build -ldflags "$(LDFLAGS)" -o $(BUILD_DIR)/$(BINARY)-linux-amd64 ./cmd/coldgrid-agent

build-all: build-amd64 build-arm build-arm7
	@echo "All builds complete."
	@ls -lh $(BUILD_DIR)/

docker:
	docker build --platform linux/arm64 -t coldgrid/edge-agent:$(VERSION) .
	docker tag coldgrid/edge-agent:$(VERSION) coldgrid/edge-agent:latest
	@echo "Docker image built: coldgrid/edge-agent:$(VERSION)"

test:
	go test -v ./...

clean:
	rm -rf $(BUILD_DIR)

install: build
	sudo cp $(BUILD_DIR)/$(BINARY) /usr/local/bin/$(BINARY)
	sudo chmod +x /usr/local/bin/$(BINARY)
	@echo "Installed to /usr/local/bin/$(BINARY)"

# Generate a sample config file for testing
sample-config:
	@cat > $(BUILD_DIR)/agent-sample.yaml <<'EOF'
agent:
  name: "warehouse-01"
  key: "ag_abc123def456"

platform:
  url: "https://app.coldgrid.io"
  heartbeat_interval_sec: 30

devices:
  - name: "comp-1"
    host: "192.168.1.10"
    port: 502
    slave_id: 1
    protocol: "modbus_tcp"
    poll_interval_sec: 15
    compressor_id: "cmp_uuid_here"
    registers:
      discharge_pressure:
        register: 40001
        type: holding
        data_type: float32
        scale: 1.0
        offset: 0
        unit: psi
      suction_pressure:
        register: 40003
        type: holding
        data_type: float32
        scale: 1.0
        offset: 0
        unit: psi
      oil_temp:
        register: 40009
        type: holding
        data_type: float32
        scale: 1.0
        offset: 0
        unit: "°F"
      amp_draw:
        register: 40015
        type: holding
        data_type: float32
        scale: 1.0
        offset: 0
        unit: A
      kw:
        register: 40017
        type: holding
        data_type: float32
        scale: 1.0
        offset: 0
        unit: kW
      slide_valve_pct:
        register: 40019
        type: holding
        data_type: float32
        scale: 1.0
        offset: 0
        unit: "%"
      running:
        register: 40021
        type: holding
        data_type: uint16
        scale: 1.0
        offset: 0
    write_registers:
      capacity_setpoint:
        register: 40100
        type: holding
        data_type: uint16
        scale: 1.0
        offset: 0
        unit: "%"

local:
  web_port: 8080
  web_enabled: true
  buffer_path: "/var/lib/coldgrid/buffer.db"
  buffer_max_mb: 500
  scan_subnet: "192.168.1.0/24"
EOF
	@echo "Sample config written to $(BUILD_DIR)/agent-sample.yaml"
