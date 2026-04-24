// ColdGrid Edge Agent — main entry point.
//
// This binary runs on a mini PC (Raspberry Pi, Intel NUC, etc.) installed
// at each cold storage facility. It:
//
//  1. Connects to compressor controllers via Modbus TCP
//  2. Polls telemetry (pressures, temps, vibration, amps, kW, etc.)
//  3. Pushes data to the ColdGrid cloud platform
//  4. Buffers locally in SQLite when the cloud is unreachable
//  5. Serves a local web dashboard for on-site operators
//  6. Accepts control commands (setpoint changes, start/stop)
//  7. Auto-discovers new devices on the plant network
//
// Usage:
//
//	coldgrid-agent                          # uses /etc/coldgrid/agent.yaml
//	coldgrid-agent -config /path/to/yaml    # custom config path
//	coldgrid-agent -version                 # print version and exit
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"runtime"
	"sync"
	"syscall"
	"time"

	"github.com/coldgrid/edge-agent/internal/config"
	"github.com/coldgrid/edge-agent/internal/modbus"
	"github.com/coldgrid/edge-agent/internal/platform"
	"github.com/coldgrid/edge-agent/internal/scanner"
	"github.com/coldgrid/edge-agent/internal/storage"
	"github.com/coldgrid/edge-agent/internal/web"
)

var (
	Version   = "dev"
	BuildTime = "unknown"
	GitCommit = "unknown"
)

func main() {
	configPath := flag.String("config", "/etc/coldgrid/agent.yaml", "path to config file")
	version := flag.Bool("version", false, "print version and exit")
	flag.Parse()

	if *version {
		fmt.Printf("coldgrid-agent %s (%s) built %s\n", Version, GitCommit, BuildTime)
		os.Exit(0)
	}

	// ── Logger ──────────────────────────────────────
	logger := slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	logger.Info("ColdGrid Edge Agent starting",
		"version", Version,
		"go", runtime.Version(),
		"os", runtime.GOOS,
		"arch", runtime.GOARCH,
	)

	// ── Config ──────────────────────────────────────
	cfg, bootstrap, err := config.LoadOrBootstrap(*configPath)
	if err != nil {
		logger.Error("failed to load config", "error", err)
		os.Exit(1)
	}

	if bootstrap {
		logger.Warn("no config file found — running in bootstrap mode",
			"config_path", *configPath,
			"web_port", cfg.Local.WebPort,
		)
		logger.Info("open http://localhost:8080 in your browser to configure this agent")
	}

	// ── Context for graceful shutdown ───────────────
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		sig := <-sigCh
		logger.Info("received signal, shutting down", "signal", sig)
		cancel()
	}()

	// ── Storage buffer ──────────────────────────────
	buf, err := storage.NewBuffer(cfg.Local.BufferPath, cfg.Local.BufferMaxMB, logger)
	if err != nil {
		logger.Error("failed to open buffer", "error", err)
		os.Exit(1)
	}
	defer buf.Close()

	buf.LogEvent("system", "Agent starting", map[string]string{
		"version": Version,
		"mode":    modeString(bootstrap),
	})

	// ── Platform client ─────────────────────────────
	var client *platform.Client
	if cfg.Platform.URL != "" && cfg.Agent.Key != "" {
		client = platform.NewClient(cfg.Platform.URL, cfg.Agent.Key, logger)
		logger.Info("platform client configured", "url", cfg.Platform.URL)
	} else {
		logger.Warn("no platform URL or agent key — running in offline mode")
	}

	// ── Live data (shared state for web dashboard) ──
	liveData := web.NewLiveData(cfg.Agent)

	// ── Modbus clients ──────────────────────────────
	type deviceHandle struct {
		client *modbus.Client
		cfg    config.DeviceConfig
	}
	var devices []deviceHandle

	for _, devCfg := range cfg.Devices {
		mc := modbus.NewClient(devCfg, logger)
		devices = append(devices, deviceHandle{client: mc, cfg: devCfg})

		liveData.SetDeviceInfo(devCfg.Name, devCfg.Host, devCfg.Port, devCfg.CompressorID)

		if err := mc.Connect(); err != nil {
			logger.Warn("initial connection failed — will retry",
				"device", devCfg.Name,
				"host", devCfg.Host,
				"error", err,
			)
			buf.LogEvent("connection", fmt.Sprintf("Failed to connect to %s", devCfg.Name), nil)
		} else {
			buf.LogEvent("connection", fmt.Sprintf("Connected to %s at %s:%d", devCfg.Name, devCfg.Host, devCfg.Port), nil)
		}
	}

	// ── Web server ──────────────────────────────────
	webServer := web.NewServer(cfg.Local.WebPort, liveData, buf, logger)
	if client != nil {
		webServer.CloudURL = cfg.Platform.URL
	}

	// Wire up control callback
	deviceMap := make(map[string]*deviceHandle)
	for i := range devices {
		deviceMap[devices[i].cfg.Name] = &devices[i]
	}

	webServer.OnControl = func(deviceName, action string, params map[string]interface{}) error {
		dh, ok := deviceMap[deviceName]
		if !ok {
			return fmt.Errorf("unknown device: %s", deviceName)
		}

		switch action {
		case "read_all":
			// Force an immediate poll — just read and update dashboard
			reading := dh.client.Poll()
			liveData.UpdateDevice(deviceName, dh.client, reading)
			return nil

		case "write_register":
			regName, _ := params["register"].(string)
			value, _ := params["value"].(float64)
			reg, ok := dh.cfg.WriteRegisters[regName]
			if !ok {
				return fmt.Errorf("register %q not writable on %s", regName, deviceName)
			}
			logger.Info("control: writing register",
				"device", deviceName,
				"register", regName,
				"value", value,
			)
			return dh.client.WriteRegister(reg, value)

		case "set_capacity":
			// Convenience: set slide valve / capacity percentage
			reg, ok := dh.cfg.WriteRegisters["capacity_setpoint"]
			if !ok {
				return fmt.Errorf("capacity_setpoint not writable on %s", deviceName)
			}
			value, _ := params["percent"].(float64)
			if value < 0 || value > 100 {
				return fmt.Errorf("capacity must be 0-100, got %.1f", value)
			}
			return dh.client.WriteRegister(reg, value)

		default:
			return fmt.Errorf("unknown action: %s", action)
		}
	}

	// ── Start all background loops ──────────────────
	var wg sync.WaitGroup

	// 1. Web dashboard (runs in its own goroutine)
	if cfg.Local.WebEnabled {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := webServer.Start(); err != nil {
				logger.Error("web server error", "error", err)
			}
		}()
	}

	// 2. Per-device poll loops
	for i := range devices {
		dh := &devices[i]
		interval := time.Duration(dh.cfg.PollIntervalSec) * time.Second
		if interval == 0 {
			interval = 15 * time.Second
		}

		wg.Add(1)
		go func(dh *deviceHandle, interval time.Duration) {
			defer wg.Done()
			pollDevice(ctx, dh, interval, liveData, buf, logger)
		}(dh, interval)
	}

	// 3. Heartbeat loop
	if client != nil {
		heartbeatInterval := time.Duration(cfg.Platform.HeartbeatIntervalSec) * time.Second
		if heartbeatInterval == 0 {
			heartbeatInterval = 30 * time.Second
		}

		wg.Add(1)
		go func() {
			defer wg.Done()
			heartbeatLoop(ctx, client, webServer, heartbeatInterval, logger)
		}()
	}

	// 4. Cloud sync loop (flush buffered readings)
	if client != nil {
		wg.Add(1)
		go func() {
			defer wg.Done()
			syncLoop(ctx, client, buf, webServer, logger)
		}()
	}

	// 5. Command polling loop
	if client != nil {
		wg.Add(1)
		go func() {
			defer wg.Done()
			commandLoop(ctx, client, buf, cfg, deviceMap, liveData, logger)
		}()
	}

	// 6. Prune loop (clean up old synced data)
	wg.Add(1)
	go func() {
		defer wg.Done()
		pruneLoop(ctx, buf, logger)
	}()

	logger.Info("all systems running",
		"devices", len(devices),
		"web_port", cfg.Local.WebPort,
		"cloud", client != nil,
	)

	// Block until shutdown
	<-ctx.Done()
	logger.Info("shutting down...")

	// Give goroutines a moment to finish
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	// Close all modbus connections
	for _, dh := range devices {
		dh.client.Close()
	}

	buf.LogEvent("system", "Agent shutting down", nil)

	_ = shutdownCtx // used for timeout awareness
	logger.Info("goodbye")
}

// ── Poll loop ────────────────────────────────────────

func pollDevice(ctx context.Context, dh *deviceHandle, interval time.Duration, liveData *web.LiveData, buf *storage.Buffer, logger *slog.Logger) {
	log := logger.With("device", dh.cfg.Name)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	reconnectBackoff := 5 * time.Second
	const maxBackoff = 2 * time.Minute

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			// Reconnect if needed
			if !dh.client.Connected {
				if err := dh.client.Connect(); err != nil {
					log.Warn("reconnect failed", "error", err, "retry_in", reconnectBackoff)
					time.Sleep(reconnectBackoff)
					if reconnectBackoff < maxBackoff {
						reconnectBackoff *= 2
					}
					continue
				}
				reconnectBackoff = 5 * time.Second
				log.Info("reconnected")
				buf.LogEvent("connection", fmt.Sprintf("Reconnected to %s", dh.cfg.Name), nil)
			}

			// Poll
			reading := dh.client.Poll()

			// Update live dashboard data
			liveData.UpdateDevice(dh.cfg.Name, dh.client, reading)

			if reading.Error != nil {
				log.Warn("poll error", "error", reading.Error)
				// If we get consecutive errors, mark disconnected for reconnect
				if dh.client.ErrorCount > 3 {
					dh.client.Close()
					buf.LogEvent("connection", fmt.Sprintf("Lost connection to %s", dh.cfg.Name), nil)
				}
				continue
			}

			// Buffer locally
			if err := buf.Store(reading.CompressorID, reading.Timestamp, reading.Values); err != nil {
				log.Error("buffer store failed", "error", err)
			}

			log.Debug("poll ok",
				"values", len(reading.Values),
				"running", reading.Running,
			)
		}
	}
}

// ── Heartbeat loop ───────────────────────────────────

func heartbeatLoop(ctx context.Context, client *platform.Client, webServer *web.Server, interval time.Duration, logger *slog.Logger) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			payload := platform.HeartbeatPayload{
				Version: Version,
			}

			// Collect system metrics
			cpu, mem, disk := getSystemMetrics()
			if cpu >= 0 {
				payload.CPUPercent = &cpu
			}
			if mem >= 0 {
				payload.MemoryPercent = &mem
			}
			if disk >= 0 {
				payload.DiskPercent = &disk
			}
			uptime := getUptimeSeconds()
			if uptime > 0 {
				payload.UptimeSeconds = &uptime
			}

			resp, err := client.SendHeartbeat(payload)
			if err != nil {
				logger.Warn("heartbeat failed", "error", err)
				webServer.CloudConnected = false
				continue
			}

			webServer.CloudConnected = true
			logger.Debug("heartbeat ok",
				"pending_commands", resp.PendingCommands,
				"config_version", resp.ConfigVersion,
			)
		}
	}
}

// ── Sync loop (flush buffered readings to cloud) ─────

func syncLoop(ctx context.Context, client *platform.Client, buf *storage.Buffer, webServer *web.Server, logger *slog.Logger) {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			readings, err := buf.GetUnsynced(100)
			if err != nil {
				logger.Error("get unsynced failed", "error", err)
				continue
			}
			if len(readings) == 0 {
				continue
			}

			// Convert buffered readings to modbus.Reading format for the API
			var modbusReadings []modbus.Reading
			for _, r := range readings {
				modbusReadings = append(modbusReadings, modbus.Reading{
					CompressorID: r.CompressorID,
					Timestamp:    r.Timestamp,
					Values:       r.Values,
				})
			}

			resp, err := client.PushReadings(modbusReadings)
			if err != nil {
				logger.Warn("push readings failed", "error", err, "count", len(readings))
				webServer.CloudConnected = false
				continue
			}

			webServer.CloudConnected = true

			// Mark as synced
			var ids []int64
			for _, r := range readings {
				ids = append(ids, r.ID)
			}
			if err := buf.MarkSynced(ids); err != nil {
				logger.Error("mark synced failed", "error", err)
			}

			logger.Info("synced readings",
				"pushed", len(readings),
				"inserted", resp.Inserted,
			)
		}
	}
}

// ── Command polling loop ─────────────────────────────

func commandLoop(ctx context.Context, client *platform.Client, buf *storage.Buffer, cfg *config.Config, deviceMap map[string]*deviceHandle, liveData *web.LiveData, logger *slog.Logger) {
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			commands, err := client.PollCommands()
			if err != nil {
				logger.Warn("poll commands failed", "error", err)
				continue
			}

			for _, cmd := range commands {
				logger.Info("received command", "id", cmd.ID, "type", cmd.CommandType)
				buf.LogEvent("command", fmt.Sprintf("Received: %s", cmd.CommandType), cmd.Parameters)

				result, errMsg := executeCommand(ctx, cmd, client, buf, cfg, deviceMap, liveData, logger)

				status := "completed"
				if errMsg != "" {
					status = "failed"
				}

				if err := client.AckCommand(cmd.ID, status, result, errMsg); err != nil {
					logger.Error("ack command failed", "id", cmd.ID, "error", err)
				}
			}
		}
	}
}

func executeCommand(ctx context.Context, cmd platform.Command, client *platform.Client, buf *storage.Buffer, cfg *config.Config, deviceMap map[string]*deviceHandle, liveData *web.LiveData, logger *slog.Logger) (interface{}, string) {
	switch cmd.CommandType {
	case "network_scan":
		return executeNetworkScan(ctx, client, buf, cfg, logger)

	case "write_register":
		deviceName, _ := cmd.Parameters["device_name"].(string)
		regName, _ := cmd.Parameters["register"].(string)
		value, _ := cmd.Parameters["value"].(float64)

		dh, ok := deviceMap[deviceName]
		if !ok {
			return nil, fmt.Sprintf("unknown device: %s", deviceName)
		}
		reg, ok := dh.cfg.WriteRegisters[regName]
		if !ok {
			return nil, fmt.Sprintf("register %s not writable on %s", regName, deviceName)
		}
		if err := dh.client.WriteRegister(reg, value); err != nil {
			return nil, err.Error()
		}
		return map[string]interface{}{"written": true, "register": regName, "value": value}, ""

	case "set_capacity":
		deviceName, _ := cmd.Parameters["device_name"].(string)
		percent, _ := cmd.Parameters["percent"].(float64)

		dh, ok := deviceMap[deviceName]
		if !ok {
			return nil, fmt.Sprintf("unknown device: %s", deviceName)
		}
		reg, ok := dh.cfg.WriteRegisters["capacity_setpoint"]
		if !ok {
			return nil, fmt.Sprintf("capacity_setpoint not writable on %s", deviceName)
		}
		if err := dh.client.WriteRegister(reg, percent); err != nil {
			return nil, err.Error()
		}
		return map[string]interface{}{"capacity_set": percent}, ""

	case "restart_agent":
		logger.Info("restart requested — exiting (systemd will restart)")
		buf.LogEvent("system", "Restart requested from cloud", nil)
		os.Exit(0)
		return nil, ""

	default:
		return nil, fmt.Sprintf("unknown command type: %s", cmd.CommandType)
	}
}

func executeNetworkScan(ctx context.Context, client *platform.Client, buf *storage.Buffer, cfg *config.Config, logger *slog.Logger) (interface{}, string) {
	subnet := cfg.Local.ScanSubnet
	if subnet == "" {
		var err error
		subnet, err = scanner.DetectSubnet()
		if err != nil {
			return nil, fmt.Sprintf("subnet detection failed: %s", err)
		}
	}

	buf.LogEvent("scan", fmt.Sprintf("Network scan starting: %s", subnet), nil)

	result := scanner.ScanSubnet(subnet, []int{502, 47808}, logger)

	buf.LogEvent("scan", fmt.Sprintf("Scan complete: found %d devices", len(result.Devices)), nil)

	// Report discoveries to platform
	if client != nil {
		if err := client.ReportDiscoveries(result); err != nil {
			logger.Warn("failed to report discoveries", "error", err)
			return result, fmt.Sprintf("scan ok but report failed: %s", err)
		}
	}

	return map[string]interface{}{
		"subnet":  result.Subnet,
		"found":   len(result.Devices),
		"devices": result.Devices,
	}, ""
}

// ── Prune loop ───────────────────────────────────────

func pruneLoop(ctx context.Context, buf *storage.Buffer, logger *slog.Logger) {
	ticker := time.NewTicker(1 * time.Hour)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := buf.Prune(); err != nil {
				logger.Error("prune failed", "error", err)
			} else {
				logger.Debug("prune complete")
			}
		}
	}
}

// ── System metrics helpers ───────────────────────────

func getSystemMetrics() (cpu, mem, disk float64) {
	// CPU usage from /proc/stat (Linux only)
	cpu = -1
	mem = -1
	disk = -1

	if runtime.GOOS != "linux" {
		return
	}

	// Memory from /proc/meminfo
	data, err := os.ReadFile("/proc/meminfo")
	if err == nil {
		var total, available uint64
		fmt.Sscanf(string(data), "MemTotal: %d kB\nMemFree: %d", &total, &available)
		if total > 0 {
			// Rough approximation — for better accuracy, parse MemAvailable
			mem = float64(total-available) / float64(total) * 100
		}
	}

	return
}

func getUptimeSeconds() int64 {
	if runtime.GOOS != "linux" {
		return 0
	}

	data, err := os.ReadFile("/proc/uptime")
	if err != nil {
		return 0
	}

	var uptime float64
	fmt.Sscanf(string(data), "%f", &uptime)
	return int64(uptime)
}

func modeString(bootstrap bool) string {
	if bootstrap {
		return "bootstrap"
	}
	return "normal"
}
