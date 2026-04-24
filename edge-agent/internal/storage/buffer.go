// Package storage provides local SQLite buffering for offline operation.
//
// When the ColdGrid cloud is unreachable, readings are stored locally.
// When connectivity returns, buffered readings are flushed to the platform.
// This ensures zero data loss during network outages.
package storage

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

type Buffer struct {
	db     *sql.DB
	logger *slog.Logger
	maxMB  int
}

type BufferedReading struct {
	ID           int64
	CompressorID string
	Timestamp    time.Time
	Values       map[string]float64
}

func NewBuffer(path string, maxMB int, logger *slog.Logger) (*Buffer, error) {
	// Ensure directory exists
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, fmt.Errorf("create buffer dir: %w", err)
	}

	db, err := sql.Open("sqlite3", path+"?journal_mode=WAL&busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("open buffer db: %w", err)
	}

	// Create tables
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS readings (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			compressor_id TEXT NOT NULL,
			timestamp TEXT NOT NULL,
			values_json TEXT NOT NULL,
			synced INTEGER DEFAULT 0,
			created_at TEXT DEFAULT (datetime('now'))
		);
		CREATE INDEX IF NOT EXISTS idx_readings_synced ON readings(synced);

		CREATE TABLE IF NOT EXISTS events (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			event_type TEXT NOT NULL,
			message TEXT NOT NULL,
			data_json TEXT,
			created_at TEXT DEFAULT (datetime('now'))
		);
	`)
	if err != nil {
		return nil, fmt.Errorf("create tables: %w", err)
	}

	return &Buffer{db: db, logger: logger.With("component", "buffer"), maxMB: maxMB}, nil
}

func (b *Buffer) Close() error {
	return b.db.Close()
}

// Store saves a reading to the local buffer.
func (b *Buffer) Store(compressorID string, ts time.Time, values map[string]float64) error {
	data, err := json.Marshal(values)
	if err != nil {
		return err
	}

	_, err = b.db.Exec(
		"INSERT INTO readings (compressor_id, timestamp, values_json) VALUES (?, ?, ?)",
		compressorID, ts.Format(time.RFC3339), string(data),
	)
	return err
}

// GetUnsynced returns up to `limit` readings that haven't been pushed to the platform.
func (b *Buffer) GetUnsynced(limit int) ([]BufferedReading, error) {
	rows, err := b.db.Query(
		"SELECT id, compressor_id, timestamp, values_json FROM readings WHERE synced = 0 ORDER BY id LIMIT ?",
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var readings []BufferedReading
	for rows.Next() {
		var r BufferedReading
		var tsStr, valJSON string
		if err := rows.Scan(&r.ID, &r.CompressorID, &tsStr, &valJSON); err != nil {
			continue
		}
		r.Timestamp, _ = time.Parse(time.RFC3339, tsStr)
		json.Unmarshal([]byte(valJSON), &r.Values)
		readings = append(readings, r)
	}
	return readings, nil
}

// MarkSynced marks readings as successfully pushed to the platform.
func (b *Buffer) MarkSynced(ids []int64) error {
	if len(ids) == 0 {
		return nil
	}

	tx, err := b.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()

	stmt, err := tx.Prepare("UPDATE readings SET synced = 1 WHERE id = ?")
	if err != nil {
		return err
	}
	defer stmt.Close()

	for _, id := range ids {
		stmt.Exec(id)
	}
	return tx.Commit()
}

// Prune removes old synced readings to keep the database size under maxMB.
func (b *Buffer) Prune() error {
	// Delete synced readings older than 7 days
	_, err := b.db.Exec(
		"DELETE FROM readings WHERE synced = 1 AND created_at < datetime('now', '-7 days')",
	)
	return err
}

// LogEvent stores a local event (for the on-site dashboard).
func (b *Buffer) LogEvent(eventType, message string, data interface{}) error {
	var dataJSON string
	if data != nil {
		d, _ := json.Marshal(data)
		dataJSON = string(d)
	}
	_, err := b.db.Exec(
		"INSERT INTO events (event_type, message, data_json) VALUES (?, ?, ?)",
		eventType, message, dataJSON,
	)
	return err
}

// RecentEvents returns the last N events for the dashboard.
func (b *Buffer) RecentEvents(limit int) ([]map[string]interface{}, error) {
	rows, err := b.db.Query(
		"SELECT event_type, message, data_json, created_at FROM events ORDER BY id DESC LIMIT ?",
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []map[string]interface{}
	for rows.Next() {
		var evType, msg, createdAt string
		var dataJSON sql.NullString
		if err := rows.Scan(&evType, &msg, &dataJSON, &createdAt); err != nil {
			continue
		}
		ev := map[string]interface{}{
			"type":       evType,
			"message":    msg,
			"created_at": createdAt,
		}
		if dataJSON.Valid {
			var d interface{}
			json.Unmarshal([]byte(dataJSON.String), &d)
			ev["data"] = d
		}
		events = append(events, ev)
	}
	return events, nil
}

// Stats returns buffer statistics for the dashboard.
func (b *Buffer) Stats() (total, unsynced int64, err error) {
	b.db.QueryRow("SELECT COUNT(*) FROM readings").Scan(&total)
	b.db.QueryRow("SELECT COUNT(*) FROM readings WHERE synced = 0").Scan(&unsynced)
	return total, unsynced, nil
}
