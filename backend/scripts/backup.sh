#!/bin/sh
# Kelvex database backup loop.
#
# Runs inside the timescale/timescaledb image (so pg_dump matches the server
# version). Takes a compressed logical dump every BACKUP_INTERVAL_SECONDS,
# keeps BACKUP_RETENTION_DAYS of history, and optionally syncs off-site via
# rclone when BACKUP_RCLONE_REMOTE is set (e.g. "b2:kelvex-backups/db").
#
# Restore: see restore.sh next to this script. TimescaleDB logical restores
# must run SELECT timescaledb_pre_restore(); before and
# SELECT timescaledb_post_restore(); after pg_restore.
set -eu

: "${PGHOST:=db}"
: "${PGUSER:?PGUSER required}"
: "${PGPASSWORD:?PGPASSWORD required}"
: "${PGDATABASE:?PGDATABASE required}"
: "${BACKUP_DIR:=/backups}"
: "${BACKUP_RETENTION_DAYS:=14}"
: "${BACKUP_INTERVAL_SECONDS:=86400}"

export PGPASSWORD

mkdir -p "$BACKUP_DIR"

# Off-site tooling is optional; install once if a remote is configured.
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ] && ! command -v rclone >/dev/null 2>&1; then
    apk add --no-cache rclone >/dev/null 2>&1 || echo "[backup] WARNING: rclone install failed; off-site sync disabled"
fi

echo "[backup] starting: every ${BACKUP_INTERVAL_SECONDS}s, keep ${BACKUP_RETENTION_DAYS}d, dir ${BACKUP_DIR}"

while true; do
    ts=$(date -u +%Y%m%d-%H%M%S)
    f="$BACKUP_DIR/kelvex-$ts.dump"

    if pg_dump -Fc -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" -f "$f.tmp"; then
        mv "$f.tmp" "$f"
        echo "[backup] OK $f ($(du -h "$f" | cut -f1))"
    else
        echo "[backup] FAILED $ts — dump error, keeping previous backups"
        rm -f "$f.tmp"
    fi

    # Retention: prune old dumps (only ours; never touch anything else)
    find "$BACKUP_DIR" -name 'kelvex-*.dump' -mtime +"$BACKUP_RETENTION_DAYS" -delete 2>/dev/null || true

    if [ -n "${BACKUP_RCLONE_REMOTE:-}" ] && command -v rclone >/dev/null 2>&1; then
        if rclone copy "$BACKUP_DIR" "$BACKUP_RCLONE_REMOTE" --include 'kelvex-*.dump' 2>&1; then
            echo "[backup] off-site sync OK → $BACKUP_RCLONE_REMOTE"
        else
            echo "[backup] WARNING: off-site sync failed"
        fi
    fi

    sleep "$BACKUP_INTERVAL_SECONDS"
done
