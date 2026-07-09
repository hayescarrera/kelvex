// Package integration provides plug-and-play integrations for common
// cold storage controllers and sensor systems beyond basic Modbus polling.
package integration

import (
	"bytes"
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/kelvex/edge-agent/internal/config"
	"github.com/kelvex/edge-agent/internal/platform"
)

// AKSMIntegration polls a Danfoss AK-SM 800 / AK-SM 800A system manager's
// built-in HTTP XML interface and pushes zone temperatures to the Kelvex cloud.
//
// The AK-SM XML interface aggregates data from all connected downstream case
// controllers (AK-CC 550, AK-CC 210, etc.) over the DANBUSS/LON bus —
// giving you zone temps for every display case without extra wiring.
//
// Required config:
//   host:     "192.168.1.100"
//   username: "admin"
//   password: "admin"
//
// Optional zone_mappings link AK-SM controller names/IDs to Kelvex zone UUIDs.
// Without mappings the agent still polls; readings show as "unlinked" in the platform.
type AKSMIntegration struct {
	cfg    config.AKSMConfig
	cloud  *platform.Client
	http   *http.Client
	logger *slog.Logger
}

func NewAKSMIntegration(cfg config.AKSMConfig, cloud *platform.Client, logger *slog.Logger) *AKSMIntegration {
	return &AKSMIntegration{
		cfg:   cfg,
		cloud: cloud,
		http:  &http.Client{Timeout: 15 * time.Second},
		logger: logger.With(
			"integration", "danfoss_aksm",
			"host", cfg.Host,
		),
	}
}

// Run polls the AK-SM on the configured interval until ctx is cancelled.
func (a *AKSMIntegration) Run(ctx context.Context) {
	interval := time.Duration(a.cfg.PollIntervalSec) * time.Second
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	a.logger.Info("Danfoss AK-SM integration started",
		"host", a.cfg.Host,
		"interval_sec", a.cfg.PollIntervalSec,
		"zone_mappings", len(a.cfg.ZoneMappings),
	)

	// First poll immediately
	a.pollAndPush(ctx)

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			a.pollAndPush(ctx)
		}
	}
}

func (a *AKSMIntegration) pollAndPush(ctx context.Context) {
	readings, err := a.poll(ctx)
	if err != nil {
		a.logger.Warn("AK-SM poll failed", "error", err)
		return
	}
	if len(readings) == 0 {
		return
	}
	if _, err := a.cloud.PushZoneReadings(readings); err != nil {
		a.logger.Warn("push AK-SM readings failed", "error", err, "count", len(readings))
	} else {
		a.logger.Debug("AK-SM readings pushed", "count", len(readings))
	}
}

// ── AK-SM XML protocol ───────────────────────────────
//
// The AK-SM HTTP XML interface accepts POST requests at /XML/request.
// Firmware 3.x: credentials embedded in each XML request.
// Firmware 4.0+: session token obtained via LOGIN command, reused per session.
//
// We use the embedded-credential method which works on all firmware versions.
// The getdevicelist command returns all downstream case controllers with their
// current sensor readings in one round-trip.

type aksmRequest struct {
	XMLName xml.Name    `xml:"PACKET"`
	Login   aksmLogin   `xml:"LOGIN"`
	Command aksmCommand `xml:"COMMAND"`
}

type aksmLogin struct {
	User     string `xml:"user,attr"`
	Password string `xml:"password,attr"`
}

type aksmCommand struct {
	Type string `xml:"type,attr"`
	ID   string `xml:"id,attr"`
}

type aksmPacket struct {
	XMLName xml.Name    `xml:"PACKET"`
	Answers []aksmAnswer `xml:"ANSWER"`
}

type aksmAnswer struct {
	ID      string       `xml:"id,attr"`
	Devices []aksmDevice `xml:"DEVICE"`
}

type aksmDevice struct {
	ID     string      `xml:"id,attr"`
	Name   string      `xml:"name,attr"`
	Type   string      `xml:"type,attr"`
	Online string      `xml:"online,attr"`
	Points []aksmPoint `xml:"POINT"`
}

type aksmPoint struct {
	ID      string `xml:"id,attr"`
	Value   string `xml:"value,attr"`
	Unit    string `xml:"unit,attr"`
	Quality string `xml:"quality,attr"`
}

func (a *AKSMIntegration) poll(ctx context.Context) ([]platform.ZoneSensorReading, error) {
	reqBody, err := xml.Marshal(aksmRequest{
		Login:   aksmLogin{User: a.cfg.Username, Password: a.cfg.Password},
		Command: aksmCommand{Type: "getdevicelist", ID: "1"},
	})
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	url := fmt.Sprintf("http://%s/XML/request", a.cfg.Host)
	req, err := http.NewRequestWithContext(ctx, "POST", url,
		bytes.NewReader(append([]byte(xml.Header), reqBody...)))
	if err != nil {
		return nil, fmt.Errorf("build request: %w", err)
	}
	req.Header.Set("Content-Type", "text/xml; charset=utf-8")

	resp, err := a.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("HTTP: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("HTTP %d from AK-SM", resp.StatusCode)
	}

	raw, err := io.ReadAll(io.LimitReader(resp.Body, 2<<20))
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	var packet aksmPacket
	if err := xml.Unmarshal(raw, &packet); err != nil {
		return nil, fmt.Errorf("parse XML: %w", err)
	}

	now := time.Now().UTC().Format(time.RFC3339)
	var readings []platform.ZoneSensorReading

	for _, answer := range packet.Answers {
		for _, device := range answer.Devices {
			if device.Online == "false" || device.Online == "0" {
				continue // skip offline devices
			}

			mapping := a.resolveMapping(device.ID, device.Name)
			tempPoint := "S2" // air-off = best proxy for zone ambient temp
			if mapping != nil && mapping.TempPoint != "" {
				tempPoint = mapping.TempPoint
			}

			for _, pt := range device.Points {
				if !strings.EqualFold(pt.ID, tempPoint) {
					continue
				}
				val, err := strconv.ParseFloat(strings.TrimSpace(pt.Value), 64)
				if err != nil {
					continue
				}
				quality := 0
				if pt.Quality != "" && pt.Quality != "good" && pt.Quality != "1" {
					quality = 2
				}

				sensorID := ""
				zoneID := ""
				if mapping != nil {
					sensorID = mapping.SensorID
					zoneID = mapping.ZoneID
				}

				readings = append(readings, platform.ZoneSensorReading{
					SensorID: sensorID,
					ZoneID:   zoneID,
					Value:    val,
					Unit:     normalizeUnit(pt.Unit),
					Quality:  quality,
					Time:     now,
					// Tag source for the platform to identify unlinked readings
					SourceLabel: fmt.Sprintf("aksm:%s/%s/%s", a.cfg.Host, device.ID, pt.ID),
				})
			}
		}
	}

	return readings, nil
}

func (a *AKSMIntegration) resolveMapping(deviceID, deviceName string) *config.AKSMZoneMapping {
	for i := range a.cfg.ZoneMappings {
		m := &a.cfg.ZoneMappings[i]
		if strings.EqualFold(m.ControllerID, deviceID) ||
			strings.EqualFold(m.ControllerID, deviceName) {
			return m
		}
	}
	return nil
}

func normalizeUnit(u string) string {
	switch strings.TrimSpace(strings.ToLower(u)) {
	case "°f", "degf", "f":
		return "F"
	case "°c", "degc", "c":
		return "C"
	default:
		return u
	}
}
