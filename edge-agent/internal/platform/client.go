// Package platform handles communication with the ColdGrid cloud API.
//
// It posts heartbeats, pushes compressor telemetry, polls for commands,
// and reports network scan discoveries. All operations are resilient to
// network failures — data is buffered locally when the cloud is unreachable.
package platform

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"time"

	"github.com/coldgrid/edge-agent/internal/modbus"
	"github.com/coldgrid/edge-agent/internal/scanner"
)

type Client struct {
	baseURL  string
	agentKey string
	http     *http.Client
	logger   *slog.Logger
}

func NewClient(baseURL, agentKey string, logger *slog.Logger) *Client {
	return &Client{
		baseURL:  baseURL + "/api/v1",
		agentKey: agentKey,
		http: &http.Client{
			Timeout: 30 * time.Second,
		},
		logger: logger.With("component", "platform"),
	}
}

// ── Heartbeat ──────────────────────────────────────

type HeartbeatPayload struct {
	CPUPercent    *float64 `json:"cpu_percent,omitempty"`
	MemoryPercent *float64 `json:"memory_percent,omitempty"`
	DiskPercent   *float64 `json:"disk_percent,omitempty"`
	UptimeSeconds *int64   `json:"uptime_seconds,omitempty"`
	Version       string   `json:"version,omitempty"`
	IPAddress     string   `json:"ip_address,omitempty"`
}

type HeartbeatResponse struct {
	Status          string `json:"status"`
	ServerTime      string `json:"server_time"`
	PendingCommands int    `json:"pending_commands"`
	ConfigVersion   int    `json:"config_version"`
}

func (c *Client) SendHeartbeat(payload HeartbeatPayload) (*HeartbeatResponse, error) {
	var resp HeartbeatResponse
	err := c.post(fmt.Sprintf("/agents/%s/heartbeat", c.agentKey), payload, &resp)
	return &resp, err
}

// ── Telemetry ──────────────────────────────────────

type CompressorReadingPayload struct {
	Readings      []CompressorReading `json:"readings"`
	DeviceStatuses []DeviceStatus     `json:"device_statuses,omitempty"`
}

type CompressorReading struct {
	CompressorID string             `json:"compressor_id"`
	Time         string             `json:"time"`
	Values       map[string]float64 `json:"values"`
}

type DeviceStatus struct {
	DeviceID   string `json:"device_id"`
	State      string `json:"state"`
	PollCount  int64  `json:"poll_count"`
	ErrorCount int64  `json:"error_count"`
	LastError  string `json:"last_error,omitempty"`
}

type IngestResponse struct {
	Status   string   `json:"status"`
	Inserted int      `json:"inserted"`
	Total    int      `json:"total"`
	Errors   []string `json:"errors,omitempty"`
}

func (c *Client) PushReadings(readings []modbus.Reading) (*IngestResponse, error) {
	payload := CompressorReadingPayload{}

	for _, r := range readings {
		if r.Error != nil || r.CompressorID == "" {
			continue
		}
		cr := CompressorReading{
			CompressorID: r.CompressorID,
			Time:         r.Timestamp.Format(time.RFC3339),
			Values:       r.Values,
		}
		payload.Readings = append(payload.Readings, cr)
	}

	if len(payload.Readings) == 0 {
		return &IngestResponse{Status: "ok", Inserted: 0}, nil
	}

	var resp IngestResponse
	err := c.post(fmt.Sprintf("/agents/%s/compressor-readings", c.agentKey), payload, &resp)
	return &resp, err
}

// ── Commands ───────────────────────────────────────

type Command struct {
	ID               string                 `json:"id"`
	CommandType      string                 `json:"command_type"`
	TargetEquipmentID string                `json:"target_equipment_id,omitempty"`
	Parameters       map[string]interface{} `json:"parameters,omitempty"`
	Priority         int                    `json:"priority"`
}

type CommandsResponse struct {
	Commands []Command `json:"commands"`
}

func (c *Client) PollCommands() ([]Command, error) {
	var resp CommandsResponse
	err := c.get(fmt.Sprintf("/agents/%s/commands", c.agentKey), &resp)
	if err != nil {
		return nil, err
	}
	return resp.Commands, nil
}

func (c *Client) AckCommand(commandID string, status string, result interface{}, errMsg string) error {
	body := map[string]interface{}{
		"status": status,
		"result": result,
		"error":  errMsg,
	}
	return c.post(fmt.Sprintf("/agents/%s/commands/%s/ack", c.agentKey, commandID), body, nil)
}

// ── Discovery ──────────────────────────────────────

func (c *Client) ReportDiscoveries(result scanner.ScanResult) error {
	payload := map[string]interface{}{
		"scan_timestamp": result.Timestamp.Format(time.RFC3339),
		"subnet":         result.Subnet,
		"devices":        result.Devices,
	}
	return c.post(fmt.Sprintf("/agents/%s/discoveries", c.agentKey), payload, nil)
}

// ── HTTP helpers ───────────────────────────────────

func (c *Client) post(path string, body interface{}, result interface{}) error {
	data, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("marshal: %w", err)
	}

	req, err := http.NewRequest("POST", c.baseURL+path, bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	if result != nil {
		return json.NewDecoder(resp.Body).Decode(result)
	}
	return nil
}

func (c *Client) get(path string, result interface{}) error {
	req, err := http.NewRequest("GET", c.baseURL+path, nil)
	if err != nil {
		return fmt.Errorf("new request: %w", err)
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("HTTP %d: %s", resp.StatusCode, string(body))
	}

	return json.NewDecoder(resp.Body).Decode(result)
}
