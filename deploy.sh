#!/bin/bash
# Kelvex production deploy script
# Run from the coldgrid project root on your VPS
set -euo pipefail

DC="docker compose -f docker-compose.prod.yml --env-file .env.production"

echo "▶ Pulling latest..."
git pull origin main

echo "▶ Building images..."
$DC build --no-cache

echo "▶ Running DB migrations..."
$DC run --rm backend alembic upgrade head

echo "▶ Starting services..."
$DC up -d

echo "▶ Waiting for health check..."
sleep 8
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "000")
if [ "$STATUS" != "200" ]; then
  echo "✗ Health check failed (got $STATUS). Check logs:"
  $DC logs --tail=50 backend
  exit 1
fi

echo "✓ Deploy complete. Backend healthy."
$DC ps
