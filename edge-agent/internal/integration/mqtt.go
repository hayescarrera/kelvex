package integration

// MQTTIntegration connects to an MQTT broker and routes incoming JSON payloads
// to zone sensor readings. Works with:
//   - Chirpstack (LoRaWAN gateway) — Dragino LHT65N, Milesight TS201, etc.
//   - ControlByWeb X-405/X-406
//   - Monnit wireless sensors (when gateway publishes locally)
//   - Any broker publishing JSON with a numeric temperature field
//
// This uses a minimal hand-rolled MQTT 3.1.1 client to avoid external
// dependencies. It supports QoS 0 and 1 subscriptions, clean sessions,
// and automatic reconnect.

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net"
	"strings"
	"sync"
	"time"

	"github.com/kelvex/edge-agent/internal/config"
	"github.com/kelvex/edge-agent/internal/platform"
)

type MQTTIntegration struct {
	cfg    config.MQTTConfig
	cloud  *platform.Client
	logger *slog.Logger
}

func NewMQTTIntegration(cfg config.MQTTConfig, cloud *platform.Client, logger *slog.Logger) *MQTTIntegration {
	return &MQTTIntegration{
		cfg:    cfg,
		cloud:  cloud,
		logger: logger.With("integration", "mqtt", "broker", cfg.Broker),
	}
}

func (m *MQTTIntegration) Run(ctx context.Context) {
	m.logger.Info("MQTT integration starting", "broker", m.cfg.Broker, "sensors", len(m.cfg.Sensors))
	for {
		if err := m.runSession(ctx); err != nil {
			m.logger.Warn("MQTT session ended", "error", err)
		}
		select {
		case <-ctx.Done():
			return
		case <-time.After(10 * time.Second):
			m.logger.Info("MQTT reconnecting")
		}
	}
}

func (m *MQTTIntegration) runSession(ctx context.Context) error {
	conn, err := net.DialTimeout("tcp", m.cfg.Broker, 10*time.Second)
	if err != nil {
		return fmt.Errorf("connect: %w", err)
	}
	defer conn.Close()

	mc := &mqttConn{conn: conn, logger: m.logger}

	if err := mc.connect(m.cfg.ClientID, m.cfg.Username, m.cfg.Password); err != nil {
		return fmt.Errorf("MQTT CONNECT: %w", err)
	}

	for _, s := range m.cfg.Sensors {
		if err := mc.subscribe(s.Topic, 1); err != nil {
			m.logger.Warn("subscribe failed", "topic", s.Topic, "error", err)
		} else {
			m.logger.Info("subscribed", "topic", s.Topic)
		}
	}

	m.logger.Info("MQTT session established")

	// Ping loop — keep-alive every 30s
	pingStop := make(chan struct{})
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		t := time.NewTicker(30 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-pingStop:
				return
			case <-t.C:
				_ = mc.ping()
			}
		}
	}()
	defer func() {
		close(pingStop)
		wg.Wait()
	}()

	for {
		select {
		case <-ctx.Done():
			return nil
		default:
		}

		conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		pkt, payload, err := mc.readPacket()
		if err != nil {
			return fmt.Errorf("read: %w", err)
		}

		switch pkt {
		case mqttPublish:
			topic, msg, err := mc.decodePublish(payload)
			if err != nil {
				m.logger.Warn("decode publish failed", "error", err)
				continue
			}
			m.handleMessage(topic, msg)
		case mqttPingResp:
			// keep-alive ack, no action needed
		}
	}
}

func (m *MQTTIntegration) handleMessage(topic string, payload []byte) {
	sensor := m.matchSensor(topic)
	if sensor == nil {
		return
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(payload, &raw); err != nil {
		m.logger.Warn("JSON parse failed", "topic", topic, "error", err)
		return
	}

	val, ok := extractJSONValue(raw, sensor.ValueKey)
	if !ok {
		m.logger.Warn("value not found in payload",
			"topic", topic, "key", sensor.ValueKey)
		return
	}

	reading := platform.ZoneSensorReading{
		SensorID:    sensor.SensorID,
		ZoneID:      sensor.ZoneID,
		Value:       val,
		Unit:        sensor.Unit,
		Quality:     0,
		Time:        time.Now().UTC().Format(time.RFC3339),
		SourceLabel: fmt.Sprintf("mqtt:%s", topic),
	}

	if _, err := m.cloud.PushZoneReadings([]platform.ZoneSensorReading{reading}); err != nil {
		m.logger.Warn("push MQTT reading failed", "error", err, "topic", topic)
	}
}

func (m *MQTTIntegration) matchSensor(topic string) *config.MQTTSensorConfig {
	for i := range m.cfg.Sensors {
		s := &m.cfg.Sensors[i]
		if mqttTopicMatch(s.Topic, topic) {
			return s
		}
	}
	return nil
}

// mqttTopicMatch matches MQTT topic patterns with + and # wildcards.
func mqttTopicMatch(pattern, topic string) bool {
	pp := strings.Split(pattern, "/")
	tp := strings.Split(topic, "/")

	for i, p := range pp {
		if p == "#" {
			return true
		}
		if i >= len(tp) {
			return false
		}
		if p != "+" && p != tp[i] {
			return false
		}
	}
	return len(pp) == len(tp)
}

// extractJSONValue follows a dot-notation path into a JSON object.
// e.g. "object.TempC_DS18B20" → data["object"]["TempC_DS18B20"]
func extractJSONValue(data map[string]interface{}, path string) (float64, bool) {
	parts := strings.SplitN(path, ".", 2)
	v, ok := data[parts[0]]
	if !ok {
		return 0, false
	}
	if len(parts) == 1 {
		switch n := v.(type) {
		case float64:
			return n, true
		case int:
			return float64(n), true
		case string:
			var f float64
			if _, err := fmt.Sscanf(n, "%f", &f); err == nil {
				return f, true
			}
		}
		return 0, false
	}
	sub, ok := v.(map[string]interface{})
	if !ok {
		return 0, false
	}
	return extractJSONValue(sub, parts[1])
}

// ── Minimal MQTT 3.1.1 client ────────────────────────
// Supports CONNECT, SUBSCRIBE, PUBLISH (receive), PINGREQ/PINGRESP.

const (
	mqttConnect  = 0x10
	mqttConnAck  = 0x20
	mqttPublish  = 0x30
	mqttSubAck   = 0x90
	mqttPingReq  = 0xC0
	mqttPingResp = 0xD0
	mqttSubscribe = 0x82
)

type mqttConn struct {
	conn   net.Conn
	mu     sync.Mutex
	pkgID  uint16
	logger *slog.Logger
}

func (c *mqttConn) connect(clientID, username, password string) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	// Variable header: protocol name + level + connect flags + keepalive
	proto := encodeMQTTString("MQTT")
	level := []byte{0x04} // MQTT 3.1.1

	flags := byte(0x02) // clean session
	if username != "" {
		flags |= 0x80
		if password != "" {
			flags |= 0x40
		}
	}

	keepalive := []byte{0x00, 0x3C} // 60s

	varHeader := append(proto, level...)
	varHeader = append(varHeader, flags)
	varHeader = append(varHeader, keepalive...)

	// Payload: client ID, username, password
	payload := encodeMQTTString(clientID)
	if username != "" {
		payload = append(payload, encodeMQTTString(username)...)
		if password != "" {
			payload = append(payload, encodeMQTTString(password)...)
		}
	}

	pkt := buildPacket(mqttConnect, append(varHeader, payload...))
	if _, err := c.conn.Write(pkt); err != nil {
		return err
	}

	c.conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	hdr := make([]byte, 4)
	if _, err := io.ReadFull(c.conn, hdr); err != nil {
		return fmt.Errorf("read connack: %w", err)
	}
	if hdr[0] != mqttConnAck {
		return fmt.Errorf("expected CONNACK (0x%02X), got 0x%02X", mqttConnAck, hdr[0])
	}
	if hdr[3] != 0 {
		codes := map[byte]string{
			1: "unacceptable protocol version",
			2: "identifier rejected",
			3: "server unavailable",
			4: "bad credentials",
			5: "not authorized",
		}
		msg := codes[hdr[3]]
		if msg == "" {
			msg = fmt.Sprintf("code 0x%02X", hdr[3])
		}
		return fmt.Errorf("CONNACK refused: %s", msg)
	}
	return nil
}

func (c *mqttConn) subscribe(topic string, qos byte) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.pkgID++
	id := c.pkgID

	payload := []byte{byte(id >> 8), byte(id)}
	payload = append(payload, encodeMQTTString(topic)...)
	payload = append(payload, qos)

	pkt := buildPacket(mqttSubscribe, payload)
	_, err := c.conn.Write(pkt)
	return err
}

func (c *mqttConn) ping() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	_, err := c.conn.Write([]byte{mqttPingReq, 0x00})
	return err
}

func (c *mqttConn) readPacket() (byte, []byte, error) {
	// Read fixed header
	hdrByte := make([]byte, 1)
	if _, err := io.ReadFull(c.conn, hdrByte); err != nil {
		return 0, nil, err
	}
	pktType := hdrByte[0] & 0xF0

	// Read remaining length (variable encoding)
	remaining, err := readVarInt(c.conn)
	if err != nil {
		return 0, nil, err
	}

	payload := make([]byte, remaining)
	if remaining > 0 {
		if _, err := io.ReadFull(c.conn, payload); err != nil {
			return 0, nil, err
		}
	}
	return pktType, payload, nil
}

func (c *mqttConn) decodePublish(payload []byte) (string, []byte, error) {
	if len(payload) < 2 {
		return "", nil, fmt.Errorf("publish too short")
	}
	topicLen := int(binary.BigEndian.Uint16(payload[0:2]))
	if len(payload) < 2+topicLen {
		return "", nil, fmt.Errorf("publish truncated")
	}
	topic := string(payload[2 : 2+topicLen])
	msg := payload[2+topicLen:]
	return topic, msg, nil
}

// ── MQTT framing helpers ─────────────────────────────

func buildPacket(pktType byte, payload []byte) []byte {
	pkt := []byte{pktType}
	pkt = append(pkt, encodeVarInt(len(payload))...)
	pkt = append(pkt, payload...)
	return pkt
}

func encodeMQTTString(s string) []byte {
	b := []byte(s)
	return append([]byte{byte(len(b) >> 8), byte(len(b))}, b...)
}

func encodeVarInt(n int) []byte {
	var buf []byte
	for {
		b := byte(n & 0x7F)
		n >>= 7
		if n > 0 {
			b |= 0x80
		}
		buf = append(buf, b)
		if n == 0 {
			break
		}
	}
	return buf
}

func readVarInt(r io.Reader) (int, error) {
	var result, shift int
	for {
		b := make([]byte, 1)
		if _, err := io.ReadFull(r, b); err != nil {
			return 0, err
		}
		result |= int(b[0]&0x7F) << shift
		if b[0]&0x80 == 0 {
			return result, nil
		}
		shift += 7
		if shift > 28 {
			return 0, fmt.Errorf("malformed variable-length integer")
		}
	}
}
