#!/bin/sh
# Restore a Kelvex backup produced by backup.sh into the running db container.
#
# Usage (from the repo root, with the stack running):
#   docker compose exec -T db sh /scripts/restore.sh /backups/kelvex-YYYYMMDD-HHMMSS.dump
#
# This OVERWRITES the current database. TimescaleDB requires the pre/post
# restore functions around pg_restore or hypertable internals break.
set -eu

DUMP="${1:?usage: restore.sh /backups/kelvex-....dump}"
: "${PGUSER:=${POSTGRES_USER:?}}"
: "${PGDATABASE:=${POSTGRES_DB:?}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:?}}"

[ -f "$DUMP" ] || { echo "dump not found: $DUMP"; exit 1; }

echo ">> Preparing TimescaleDB for restore"
psql -U "$PGUSER" -d "$PGDATABASE" -c "SELECT timescaledb_pre_restore();"

echo ">> Restoring $DUMP (clean, if-exists)"
pg_restore -U "$PGUSER" -d "$PGDATABASE" --clean --if-exists --no-owner "$DUMP"

echo ">> Finalizing TimescaleDB"
psql -U "$PGUSER" -d "$PGDATABASE" -c "SELECT timescaledb_post_restore();"

echo ">> Done. Restart the backend so pooled connections re-establish:"
echo "   docker compose restart backend worker beat"
