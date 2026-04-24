#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting ColdGrid API..."
if [ "${UVICORN_RELOAD:-false}" = "true" ]; then
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
  uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
