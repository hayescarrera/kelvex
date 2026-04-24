// Package web serves the local on-site dashboard.
//
// This runs on the gateway device (e.g. http://192.168.1.100:8080) and gives
// the plant operator real-time visibility into every compressor without needing
// cloud connectivity. It also enables local control — setpoint changes, start/stop.
//
// Think of this as the Foreman.mn equivalent for cold storage compressors.
package web

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/coldgrid/edge-agent/internal/config"
	"github.com/coldgrid/edge-agent/internal/modbus"
	"github.com/coldgrid/edge-agent/internal/storage"
)

// LiveData holds the latest readings from all devices.
type LiveData struct {
	mu       sync.RWMutex
	devices  map[string]*DeviceState
	agentCfg config.AgentConfig
}

type DeviceState struct {
	Name           string             `json:"name"`
	CompressorID   string             `json:"compressor_id"`
	Host           string             `json:"host"`
	Port           int                `json:"port"`
	Connected      bool               `json:"connected"`
	Running        bool               `json:"running"`
	Values         map[string]float64 `json:"values"`
	LastUpdate     time.Time          `json:"last_update"`
	PollCount      int64              `json:"poll_count"`
	ErrorCount     int64              `json:"error_count"`
	LastError      string             `json:"last_error,omitempty"`
	History        []HistoryPoint     `json:"history"` // last 60 data points (~15min at 15s poll)
}

type HistoryPoint struct {
	Time   time.Time          `json:"time"`
	Values map[string]float64 `json:"values"`
}

func NewLiveData(cfg config.AgentConfig) *LiveData {
	return &LiveData{
		devices:  make(map[string]*DeviceState),
		agentCfg: cfg,
	}
}

func (ld *LiveData) UpdateDevice(name string, client *modbus.Client, reading modbus.Reading) {
	ld.mu.Lock()
	defer ld.mu.Unlock()

	state, ok := ld.devices[name]
	if !ok {
		state = &DeviceState{
			Name:    name,
			History: make([]HistoryPoint, 0, 120),
		}
		ld.devices[name] = state
	}

	state.CompressorID = reading.CompressorID
	state.Connected = client.Connected
	state.Running = reading.Running
	state.Values = reading.Values
	state.LastUpdate = reading.Timestamp
	state.PollCount = client.PollCount
	state.ErrorCount = client.ErrorCount
	state.LastError = client.LastError
	// Host/port are set via SetDeviceInfo — don't overwrite here

	// Add to history ring buffer
	state.History = append(state.History, HistoryPoint{
		Time:   reading.Timestamp,
		Values: copyMap(reading.Values),
	})
	// Keep last 120 points (~30min at 15s intervals)
	if len(state.History) > 120 {
		state.History = state.History[len(state.History)-120:]
	}
}

func (ld *LiveData) SetDeviceInfo(name, host string, port int, compressorID string) {
	ld.mu.Lock()
	defer ld.mu.Unlock()

	state, ok := ld.devices[name]
	if !ok {
		state = &DeviceState{
			Name:    name,
			History: make([]HistoryPoint, 0, 120),
		}
		ld.devices[name] = state
	}
	state.Host = host
	state.Port = port
	state.CompressorID = compressorID
}

func (ld *LiveData) GetSnapshot() map[string]*DeviceState {
	ld.mu.RLock()
	defer ld.mu.RUnlock()

	snapshot := make(map[string]*DeviceState, len(ld.devices))
	for k, v := range ld.devices {
		snapshot[k] = v
	}
	return snapshot
}

// Server runs the local web dashboard.
type Server struct {
	port     int
	liveData *LiveData
	buffer   *storage.Buffer
	logger   *slog.Logger
	// Control callback — called when the operator issues a command from the UI
	OnControl func(deviceName, action string, params map[string]interface{}) error
	// Cloud connectivity status
	CloudConnected bool
	CloudURL       string
}

func NewServer(port int, liveData *LiveData, buffer *storage.Buffer, logger *slog.Logger) *Server {
	return &Server{
		port:     port,
		liveData: liveData,
		buffer:   buffer,
		logger:   logger.With("component", "web"),
	}
}

func (s *Server) Start() error {
	mux := http.NewServeMux()

	// API endpoints
	mux.HandleFunc("/api/status", s.handleStatus)
	mux.HandleFunc("/api/devices", s.handleDevices)
	mux.HandleFunc("/api/device/", s.handleDevice)
	mux.HandleFunc("/api/events", s.handleEvents)
	mux.HandleFunc("/api/control", s.handleControl)

	// Serve embedded static files (dashboard HTML/JS/CSS)
	mux.HandleFunc("/", s.handleDashboard)

	addr := fmt.Sprintf(":%d", s.port)
	s.logger.Info("local dashboard starting", "addr", addr)
	return http.ListenAndServe(addr, mux)
}

func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	devices := s.liveData.GetSnapshot()

	totalDevices := len(devices)
	connected := 0
	running := 0
	var totalKW float64

	for _, d := range devices {
		if d.Connected {
			connected++
		}
		if d.Running {
			running++
		}
		if kw, ok := d.Values["kw"]; ok {
			totalKW += kw
		}
	}

	bufTotal, bufUnsynced, _ := s.buffer.Stats()

	status := map[string]interface{}{
		"agent_name":      s.liveData.agentCfg.Name,
		"cloud_connected": s.CloudConnected,
		"cloud_url":       s.CloudURL,
		"total_devices":   totalDevices,
		"connected":       connected,
		"running":         running,
		"total_kw":        totalKW,
		"buffer_total":    bufTotal,
		"buffer_unsynced": bufUnsynced,
		"uptime":          time.Now().Format(time.RFC3339),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

func (s *Server) handleDevices(w http.ResponseWriter, r *http.Request) {
	devices := s.liveData.GetSnapshot()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(devices)
}

func (s *Server) handleDevice(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Path[len("/api/device/"):]
	devices := s.liveData.GetSnapshot()

	device, ok := devices[name]
	if !ok {
		http.NotFound(w, r)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(device)
}

func (s *Server) handleEvents(w http.ResponseWriter, r *http.Request) {
	events, _ := s.buffer.RecentEvents(50)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(events)
}

func (s *Server) handleControl(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		http.Error(w, "method not allowed", 405)
		return
	}

	var req struct {
		Device string                 `json:"device"`
		Action string                 `json:"action"`
		Params map[string]interface{} `json:"params"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "bad request", 400)
		return
	}

	if s.OnControl == nil {
		http.Error(w, "control not configured", 500)
		return
	}

	if err := s.OnControl(req.Device, req.Action, req.Params); err != nil {
		s.logger.Error("control action failed", "device", req.Device, "action", req.Action, "error", err)
		http.Error(w, err.Error(), 500)
		return
	}

	s.buffer.LogEvent("control", fmt.Sprintf("Action '%s' on '%s'", req.Action, req.Device), req.Params)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func (s *Server) handleDashboard(w http.ResponseWriter, r *http.Request) {
	// Serve the embedded single-page dashboard
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Write([]byte(dashboardHTML))
}

func copyMap(m map[string]float64) map[string]float64 {
	out := make(map[string]float64, len(m))
	for k, v := range m {
		out[k] = v
	}
	return out
}

// dashboardHTML is the complete on-site dashboard — single HTML file with inline JS/CSS.
// This runs locally on the gateway at port 8080.
var dashboardHTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ColdGrid Edge — Local Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0e17; color: #e2e8f0; min-height: 100vh; }
  .header { background: #111827; border-bottom: 1px solid #1e293b; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 1.1rem; font-weight: 600; display: flex; align-items: center; gap: 8px; }
  .header h1 span { color: #3b82f6; }
  .cloud-badge { padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
  .cloud-badge.online { background: rgba(34,197,94,0.15); color: #22c55e; }
  .cloud-badge.offline { background: rgba(239,68,68,0.15); color: #ef4444; }
  .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; padding: 20px 24px; }
  .stat-card { background: #111827; border: 1px solid #1e293b; border-radius: 10px; padding: 16px; }
  .stat-card .label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px; color: #64748b; margin-bottom: 4px; }
  .stat-card .value { font-size: 1.5rem; font-weight: 700; }
  .stat-card .value.green { color: #22c55e; }
  .stat-card .value.blue { color: #3b82f6; }
  .stat-card .value.orange { color: #f59e0b; }
  .devices-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 16px; padding: 0 24px 24px; }
  .device-card { background: #111827; border: 1px solid #1e293b; border-radius: 10px; overflow: hidden; }
  .device-card.alarm { border-color: #ef4444; }
  .device-header { padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; }
  .device-name { font-weight: 600; font-size: 0.9rem; display: flex; align-items: center; gap: 8px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; }
  .dot.online { background: #22c55e; }
  .dot.offline { background: #64748b; }
  .dot.running { background: #22c55e; animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
  .device-status { font-size: 0.75rem; padding: 3px 8px; border-radius: 10px; }
  .device-status.running { background: rgba(34,197,94,0.15); color: #22c55e; }
  .device-status.stopped { background: rgba(100,116,139,0.15); color: #94a3b8; }
  .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: #1e293b; }
  .metric { background: #111827; padding: 10px 12px; }
  .metric .label { font-size: 0.68rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.3px; }
  .metric .val { font-size: 1.05rem; font-weight: 600; margin-top: 2px; font-variant-numeric: tabular-nums; }
  .metric .unit { font-size: 0.7rem; color: #64748b; margin-left: 2px; }
  .metric.warn .val { color: #f59e0b; }
  .metric.danger .val { color: #ef4444; }
  .device-footer { padding: 10px 16px; display: flex; justify-content: space-between; align-items: center; font-size: 0.72rem; color: #64748b; }
  .ctrl-btn { background: #1e293b; color: #e2e8f0; border: 1px solid #334155; padding: 5px 12px; border-radius: 6px; font-size: 0.75rem; cursor: pointer; }
  .ctrl-btn:hover { background: #334155; }
  .ctrl-btn.danger { border-color: #7f1d1d; color: #fca5a5; }
  .ctrl-btn.danger:hover { background: #7f1d1d; }
  .events-panel { margin: 0 24px 24px; background: #111827; border: 1px solid #1e293b; border-radius: 10px; padding: 16px; max-height: 200px; overflow-y: auto; }
  .events-panel h3 { font-size: 0.82rem; margin-bottom: 10px; color: #94a3b8; }
  .event-row { font-size: 0.78rem; padding: 4px 0; border-bottom: 1px solid #1e293b; display: flex; gap: 12px; }
  .event-time { color: #64748b; min-width: 70px; }
</style>
</head>
<body>
<div class="header">
  <h1><span>❄</span> ColdGrid Edge — <span id="agent-name">Loading...</span></h1>
  <div>
    <span id="cloud-badge" class="cloud-badge offline">Cloud: Offline</span>
  </div>
</div>

<div class="stats-row">
  <div class="stat-card"><div class="label">Compressors</div><div class="value blue" id="stat-total">—</div></div>
  <div class="stat-card"><div class="label">Running</div><div class="value green" id="stat-running">—</div></div>
  <div class="stat-card"><div class="label">Total Power</div><div class="value orange" id="stat-kw">— kW</div></div>
  <div class="stat-card"><div class="label">Buffered</div><div class="value" id="stat-buffer">—</div></div>
</div>

<div class="devices-grid" id="devices"></div>

<div class="events-panel">
  <h3>Recent Events</h3>
  <div id="events">Loading...</div>
</div>

<script>
const METRICS = [
  { key: 'discharge_pressure', label: 'Discharge', unit: 'psi', warn: 200, danger: 250 },
  { key: 'suction_pressure', label: 'Suction', unit: 'psi', warnLow: 15 },
  { key: 'oil_temp', label: 'Oil Temp', unit: '°F', warn: 160, danger: 180 },
  { key: 'bearing_temp', label: 'Bearing', unit: '°F', warn: 180, danger: 200 },
  { key: 'vibration', label: 'Vibration', unit: 'in/s', warn: 0.2, danger: 0.35 },
  { key: 'amp_draw', label: 'Amps', unit: 'A' },
  { key: 'kw', label: 'Power', unit: 'kW' },
  { key: 'slide_valve_pct', label: 'Load', unit: '%' },
  { key: 'rpm', label: 'Speed', unit: 'RPM' },
];

function metricClass(m, val) {
  if (m.danger && val >= m.danger) return 'danger';
  if (m.warn && val >= m.warn) return 'warn';
  if (m.warnLow && val <= m.warnLow) return 'warn';
  return '';
}

function renderDevices(devices) {
  const grid = document.getElementById('devices');
  grid.innerHTML = '';
  for (const [name, d] of Object.entries(devices)) {
    const card = document.createElement('div');
    card.className = 'device-card' + (d.error_count > 10 ? ' alarm' : '');
    const metrics = METRICS.map(m => {
      const val = d.values[m.key];
      if (val == null) return '';
      const cls = metricClass(m, val);
      return '<div class="metric ' + cls + '"><div class="label">' + m.label +
        '</div><div class="val">' + val.toFixed(1) + '<span class="unit">' + m.unit + '</span></div></div>';
    }).join('');

    const ago = d.last_update ? Math.round((Date.now() - new Date(d.last_update).getTime()) / 1000) + 's ago' : 'never';

    card.innerHTML =
      '<div class="device-header">' +
        '<div class="device-name"><span class="dot ' + (d.connected ? (d.running ? 'running' : 'online') : 'offline') + '"></span>' + d.name + '</div>' +
        '<span class="device-status ' + (d.running ? 'running' : 'stopped') + '">' + (d.running ? 'Running' : 'Stopped') + '</span>' +
      '</div>' +
      '<div class="metrics-grid">' + metrics + '</div>' +
      '<div class="device-footer">' +
        '<span>' + d.host + ':' + d.port + ' · ' + d.poll_count + ' polls · ' + ago + '</span>' +
        '<div><button class="ctrl-btn" onclick="sendControl(\'' + name + '\', \'read_all\')">Refresh</button></div>' +
      '</div>';
    grid.appendChild(card);
  }
}

function sendControl(device, action, params) {
  fetch('/api/control', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device, action, params: params || {} }),
  });
}

async function poll() {
  try {
    const [status, devices, events] = await Promise.all([
      fetch('/api/status').then(r => r.json()),
      fetch('/api/devices').then(r => r.json()),
      fetch('/api/events').then(r => r.json()),
    ]);

    document.getElementById('agent-name').textContent = status.agent_name;
    document.getElementById('stat-total').textContent = status.total_devices;
    document.getElementById('stat-running').textContent = status.running;
    document.getElementById('stat-kw').textContent = status.total_kw.toFixed(1) + ' kW';
    document.getElementById('stat-buffer').textContent = status.buffer_unsynced > 0 ? status.buffer_unsynced + ' queued' : 'Synced';

    const badge = document.getElementById('cloud-badge');
    badge.className = 'cloud-badge ' + (status.cloud_connected ? 'online' : 'offline');
    badge.textContent = 'Cloud: ' + (status.cloud_connected ? 'Connected' : 'Offline');

    renderDevices(devices);

    const eventsDiv = document.getElementById('events');
    if (events && events.length > 0) {
      eventsDiv.innerHTML = events.slice(0, 20).map(e =>
        '<div class="event-row"><span class="event-time">' + (e.created_at || '').slice(11, 19) + '</span><span>' + e.message + '</span></div>'
      ).join('');
    } else {
      eventsDiv.innerHTML = '<div style="color:#64748b">No recent events</div>';
    }
  } catch (e) {
    console.error('Poll error:', e);
  }
}

poll();
setInterval(poll, 3000);
</script>
</body>
</html>
`
