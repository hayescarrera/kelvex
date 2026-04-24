// Package scanner discovers Modbus TCP and BACnet devices on the local network.
//
// It scans a /24 subnet by attempting TCP connections to port 502 (Modbus)
// and optionally 47808 (BACnet). For each responding host, it tries to read
// device identification and a few sample registers to help auto-match profiles.
package scanner

import (
	"encoding/binary"
	"fmt"
	"log/slog"
	"math"
	"net"
	"sync"
	"time"
)

type DiscoveredDevice struct {
	Host        string             `json:"host"`
	Port        int                `json:"port"`
	Protocol    string             `json:"protocol"`
	SlaveID     int                `json:"slave_id"`
	Responding  bool               `json:"responding"`
	DeviceInfo  DeviceInfo         `json:"device_info"`
	SampleValues map[string]float64 `json:"sample_values"`
}

type DeviceInfo struct {
	Vendor          string `json:"vendor,omitempty"`
	ProductCode     string `json:"product_code,omitempty"`
	FirmwareVersion string `json:"firmware_version,omitempty"`
	Serial          string `json:"serial,omitempty"`
}

type ScanResult struct {
	Subnet    string            `json:"subnet"`
	Timestamp time.Time         `json:"scan_timestamp"`
	Devices   []DiscoveredDevice `json:"devices"`
}

// ScanSubnet scans a /24 subnet for Modbus TCP devices.
// It parallelizes across 32 workers for speed.
func ScanSubnet(subnet string, ports []int, logger *slog.Logger) ScanResult {
	result := ScanResult{
		Subnet:    subnet,
		Timestamp: time.Now().UTC(),
	}

	if len(ports) == 0 {
		ports = []int{502}
	}

	// Parse base IP from CIDR
	ip, ipNet, err := net.ParseCIDR(subnet)
	if err != nil {
		logger.Error("invalid subnet", "subnet", subnet, "error", err)
		return result
	}

	// Generate all host IPs in the subnet
	var hosts []string
	for ip := ip.Mask(ipNet.Mask); ipNet.Contains(ip); incrementIP(ip) {
		hosts = append(hosts, ip.String())
	}
	// Skip network and broadcast addresses
	if len(hosts) > 2 {
		hosts = hosts[1 : len(hosts)-1]
	}

	logger.Info("starting network scan", "subnet", subnet, "hosts", len(hosts), "ports", ports)

	// Scan in parallel
	var wg sync.WaitGroup
	var mu sync.Mutex
	sem := make(chan struct{}, 64) // limit concurrency

	for _, host := range hosts {
		for _, port := range ports {
			wg.Add(1)
			go func(h string, p int) {
				defer wg.Done()
				sem <- struct{}{}
				defer func() { <-sem }()

				device := probeHost(h, p, logger)
				if device != nil {
					mu.Lock()
					result.Devices = append(result.Devices, *device)
					mu.Unlock()
				}
			}(host, port)
		}
	}

	wg.Wait()
	logger.Info("scan complete", "found", len(result.Devices))
	return result
}

// DetectSubnet returns the /24 subnet of the first non-loopback interface.
func DetectSubnet() (string, error) {
	ifaces, err := net.Interfaces()
	if err != nil {
		return "", err
	}

	for _, iface := range ifaces {
		if iface.Flags&net.FlagLoopback != 0 || iface.Flags&net.FlagUp == 0 {
			continue
		}
		addrs, err := iface.Addrs()
		if err != nil {
			continue
		}
		for _, addr := range addrs {
			ipNet, ok := addr.(*net.IPNet)
			if !ok || ipNet.IP.To4() == nil {
				continue
			}
			// Return as /24
			ip := ipNet.IP.To4()
			return fmt.Sprintf("%d.%d.%d.0/24", ip[0], ip[1], ip[2]), nil
		}
	}
	return "", fmt.Errorf("no suitable network interface found")
}

func probeHost(host string, port int, logger *slog.Logger) *DiscoveredDevice {
	addr := fmt.Sprintf("%s:%d", host, port)

	conn, err := net.DialTimeout("tcp", addr, 2*time.Second)
	if err != nil {
		return nil // Host not responding — normal
	}
	defer conn.Close()

	logger.Debug("host responding", "addr", addr)

	device := &DiscoveredDevice{
		Host:         host,
		Port:         port,
		Protocol:     "modbus_tcp",
		SlaveID:      1,
		Responding:   true,
		SampleValues: make(map[string]float64),
	}

	// Try reading device identification
	conn.SetDeadline(time.Now().Add(3 * time.Second))
	vendor, product, firmware := readDeviceID(conn)
	device.DeviceInfo = DeviceInfo{
		Vendor:          vendor,
		ProductCode:     product,
		FirmwareVersion: firmware,
	}

	// Try reading common compressor registers to get sample values.
	// We try a few well-known register addresses used by major manufacturers.
	sampleRegisters := []struct {
		name    string
		address uint16
	}{
		// Frick Quantum HD style (40001+)
		{"discharge_pressure", 40001},
		{"suction_pressure", 40003},
		{"oil_temp", 40009},
		// Vilter VSM style (30001+)
		{"discharge_pressure_v", 30001},
		// GEA Omni style (1000+)
		{"discharge_pressure_g", 1000},
		// Mycom N style (100+)
		{"discharge_pressure_m", 100},
	}

	for _, sr := range sampleRegisters {
		val, err := readHoldingRegisterFloat32(conn, 1, sr.address)
		if err == nil && val > 0 && val < 10000 { // sanity check
			device.SampleValues[sr.name] = math.Round(val*10) / 10
		}
	}

	return device
}

func readDeviceID(conn net.Conn) (vendor, product, firmware string) {
	req := make([]byte, 11)
	binary.BigEndian.PutUint16(req[0:2], 1) // txID
	binary.BigEndian.PutUint16(req[2:4], 0) // protocol
	binary.BigEndian.PutUint16(req[4:6], 5) // length
	req[6] = 1                               // unit ID
	req[7] = 0x2B                            // MEI
	req[8] = 0x0E                            // Read Device ID
	req[9] = 0x01                            // Basic
	req[10] = 0x00                           // Start at VendorName

	conn.Write(req)
	resp := make([]byte, 256)
	n, err := conn.Read(resp)
	if err != nil || n < 15 {
		return
	}
	if resp[7] == 0xAB { // exception
		return
	}

	// Parse objects
	pos := 13
	for i := 0; i < 3 && pos < n-2; i++ {
		objLen := int(resp[pos+1])
		pos += 2
		if pos+objLen > n {
			break
		}
		s := string(resp[pos : pos+objLen])
		switch i {
		case 0:
			vendor = s
		case 1:
			product = s
		case 2:
			firmware = s
		}
		pos += objLen
	}
	return
}

func readHoldingRegisterFloat32(conn net.Conn, slaveID byte, address uint16) (float64, error) {
	req := make([]byte, 12)
	binary.BigEndian.PutUint16(req[0:2], 2)       // txID
	binary.BigEndian.PutUint16(req[2:4], 0)       // protocol
	binary.BigEndian.PutUint16(req[4:6], 6)       // length
	req[6] = slaveID                               // unit ID
	req[7] = 0x03                                  // Read Holding Registers
	binary.BigEndian.PutUint16(req[8:10], address) // start address
	binary.BigEndian.PutUint16(req[10:12], 2)     // read 2 registers (float32)

	conn.Write(req)

	resp := make([]byte, 13)
	n, err := conn.Read(resp)
	if err != nil || n < 13 {
		return 0, fmt.Errorf("read failed")
	}
	if resp[7]&0x80 != 0 {
		return 0, fmt.Errorf("exception %d", resp[8])
	}

	bits := binary.BigEndian.Uint32(resp[9:13])
	val := float64(math.Float32frombits(bits))
	return val, nil
}

func incrementIP(ip net.IP) {
	for j := len(ip) - 1; j >= 0; j-- {
		ip[j]++
		if ip[j] > 0 {
			break
		}
	}
}
