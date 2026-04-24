// Package modbus provides Modbus TCP client for polling compressor controllers.
//
// Each device gets its own persistent TCP connection with automatic reconnect.
// Register values are read according to the device profile's register map,
// with proper handling of data types (uint16, int16, float32) and scale/offset.
package modbus

import (
	"encoding/binary"
	"fmt"
	"log/slog"
	"math"
	"net"
	"sync"
	"time"

	"github.com/coldgrid/edge-agent/internal/config"
)

// Reading represents a single poll cycle's worth of data from one device.
type Reading struct {
	DeviceName   string
	CompressorID string
	Timestamp    time.Time
	Values       map[string]float64
	Running      bool
	Error        error
}

// Client manages a Modbus TCP connection to a single controller.
type Client struct {
	cfg      config.DeviceConfig
	conn     net.Conn
	mu       sync.Mutex
	txID     uint16
	logger   *slog.Logger

	// Stats
	PollCount  int64
	ErrorCount int64
	LastPollAt time.Time
	LastError  string
	Connected  bool
}

func NewClient(cfg config.DeviceConfig, logger *slog.Logger) *Client {
	return &Client{
		cfg:    cfg,
		logger: logger.With("device", cfg.Name, "host", cfg.Host),
	}
}

func (c *Client) Connect() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	addr := fmt.Sprintf("%s:%d", c.cfg.Host, c.cfg.Port)
	conn, err := net.DialTimeout("tcp", addr, 5*time.Second)
	if err != nil {
		c.Connected = false
		c.LastError = err.Error()
		return fmt.Errorf("connect to %s: %w", addr, err)
	}

	c.conn = conn
	c.Connected = true
	c.logger.Info("connected to controller")
	return nil
}

func (c *Client) Close() {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.conn != nil {
		c.conn.Close()
		c.conn = nil
	}
	c.Connected = false
}

// Poll reads all configured registers and returns a Reading.
func (c *Client) Poll() Reading {
	c.mu.Lock()
	defer c.mu.Unlock()

	r := Reading{
		DeviceName:   c.cfg.Name,
		CompressorID: c.cfg.CompressorID,
		Timestamp:    time.Now().UTC(),
		Values:       make(map[string]float64),
	}

	if c.conn == nil {
		r.Error = fmt.Errorf("not connected")
		c.ErrorCount++
		return r
	}

	c.conn.SetDeadline(time.Now().Add(10 * time.Second))

	for name, reg := range c.cfg.Registers {
		val, err := c.readRegister(reg)
		if err != nil {
			c.logger.Warn("register read failed", "register", name, "error", err)
			c.ErrorCount++
			c.LastError = fmt.Sprintf("%s: %s", name, err.Error())
			continue
		}

		if name == "running" {
			r.Running = val > 0
		}
		r.Values[name] = val
	}

	c.PollCount++
	c.LastPollAt = r.Timestamp
	return r
}

// WriteRegister writes a value to a holding register (for control operations).
func (c *Client) WriteRegister(reg config.Register, value float64) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.conn == nil {
		return fmt.Errorf("not connected")
	}

	// Reverse the scale/offset to get raw register value
	raw := (value - reg.Offset) / reg.Scale

	c.conn.SetDeadline(time.Now().Add(5 * time.Second))

	c.txID++
	addr := reg.Address
	// Modbus function code 0x06: Write Single Register
	req := buildWriteSingleRegister(c.txID, byte(c.cfg.SlaveID), addr, uint16(raw))

	if _, err := c.conn.Write(req); err != nil {
		return fmt.Errorf("write register %d: %w", addr, err)
	}

	resp := make([]byte, 12)
	if _, err := c.conn.Read(resp); err != nil {
		return fmt.Errorf("read write response: %w", err)
	}

	c.logger.Info("register written", "address", addr, "value", value, "raw", uint16(raw))
	return nil
}

func (c *Client) readRegister(reg config.Register) (float64, error) {
	c.txID++

	var funcCode byte
	switch reg.Type {
	case "holding":
		funcCode = 0x03 // Read Holding Registers
	case "input":
		funcCode = 0x04 // Read Input Registers
	default:
		funcCode = 0x03
	}

	// Determine how many registers to read based on data type
	regCount := uint16(1)
	if reg.DataType == "float32" || reg.DataType == "int32" || reg.DataType == "uint32" {
		regCount = 2
	}

	req := buildReadRequest(c.txID, byte(c.cfg.SlaveID), funcCode, reg.Address, regCount)

	if _, err := c.conn.Write(req); err != nil {
		return 0, fmt.Errorf("write request: %w", err)
	}

	// Response: 9 bytes header + 2*regCount data bytes
	respLen := 9 + 2*int(regCount)
	resp := make([]byte, respLen)
	n, err := c.conn.Read(resp)
	if err != nil {
		return 0, fmt.Errorf("read response: %w", err)
	}
	if n < respLen {
		return 0, fmt.Errorf("short response: got %d bytes, expected %d", n, respLen)
	}

	// Check for Modbus exception
	if resp[7]&0x80 != 0 {
		return 0, fmt.Errorf("modbus exception: code %d", resp[8])
	}

	// Extract raw data from response (starts at byte 9)
	data := resp[9:]

	var raw float64
	switch reg.DataType {
	case "uint16":
		raw = float64(binary.BigEndian.Uint16(data))
	case "int16":
		raw = float64(int16(binary.BigEndian.Uint16(data)))
	case "float32":
		bits := binary.BigEndian.Uint32(data)
		raw = float64(math.Float32frombits(bits))
	case "uint32":
		raw = float64(binary.BigEndian.Uint32(data))
	case "int32":
		raw = float64(int32(binary.BigEndian.Uint32(data)))
	default:
		raw = float64(binary.BigEndian.Uint16(data))
	}

	// Apply scale and offset
	return raw*reg.Scale + reg.Offset, nil
}

// ── Modbus TCP frame builders ────────────────────────

func buildReadRequest(txID uint16, slaveID, funcCode byte, address, count uint16) []byte {
	frame := make([]byte, 12)
	binary.BigEndian.PutUint16(frame[0:2], txID)         // Transaction ID
	binary.BigEndian.PutUint16(frame[2:4], 0)             // Protocol ID (Modbus = 0)
	binary.BigEndian.PutUint16(frame[4:6], 6)             // Length
	frame[6] = slaveID                                     // Unit ID
	frame[7] = funcCode                                    // Function code
	binary.BigEndian.PutUint16(frame[8:10], address)      // Start address
	binary.BigEndian.PutUint16(frame[10:12], count)       // Register count
	return frame
}

func buildWriteSingleRegister(txID uint16, slaveID byte, address, value uint16) []byte {
	frame := make([]byte, 12)
	binary.BigEndian.PutUint16(frame[0:2], txID)
	binary.BigEndian.PutUint16(frame[2:4], 0)
	binary.BigEndian.PutUint16(frame[4:6], 6)
	frame[6] = slaveID
	frame[7] = 0x06 // Write Single Register
	binary.BigEndian.PutUint16(frame[8:10], address)
	binary.BigEndian.PutUint16(frame[10:12], value)
	return frame
}

// ReadDeviceIdentification sends a Modbus device ID request (FC 0x2B/0x0E).
// Returns vendor, product code, and firmware version if the device supports it.
func (c *Client) ReadDeviceIdentification() (vendor, product, firmware string, err error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.conn == nil {
		return "", "", "", fmt.Errorf("not connected")
	}

	c.conn.SetDeadline(time.Now().Add(5 * time.Second))
	c.txID++

	// MEI (Modbus Encapsulated Interface) request for basic device ID
	req := make([]byte, 11)
	binary.BigEndian.PutUint16(req[0:2], c.txID)
	binary.BigEndian.PutUint16(req[2:4], 0)
	binary.BigEndian.PutUint16(req[4:6], 5)
	req[6] = byte(c.cfg.SlaveID)
	req[7] = 0x2B // MEI
	req[8] = 0x0E // Read Device Identification
	req[9] = 0x01 // Basic identification
	req[10] = 0x00 // Object ID 0 = VendorName

	if _, err := c.conn.Write(req); err != nil {
		return "", "", "", err
	}

	resp := make([]byte, 256)
	n, err := c.conn.Read(resp)
	if err != nil || n < 15 {
		// Many controllers don't support device ID — not an error
		return "", "", "", nil
	}

	// Parse objects from response
	if resp[7] == 0xAB { // Exception
		return "", "", "", nil
	}

	// Parse MEI response objects
	objects := parseMEIObjects(resp[13:n])
	vendor = objects[0]
	product = objects[1]
	firmware = objects[2]
	return vendor, product, firmware, nil
}

func parseMEIObjects(data []byte) map[int]string {
	objects := make(map[int]string)
	pos := 0
	for pos < len(data)-2 {
		objID := int(data[pos])
		objLen := int(data[pos+1])
		pos += 2
		if pos+objLen > len(data) {
			break
		}
		objects[objID] = string(data[pos : pos+objLen])
		pos += objLen
	}
	return objects
}
