#!/bin/bash
# Run against a live backend to verify seed data is working.
# Usage: BACKEND=http://localhost:8000 bash seed_demo_verify.sh

BACKEND=${BACKEND:-http://localhost:8000}
EMAIL="demo@kelvex.io"
PASS="demo123"

echo "── Health check ──────────────────────────────"
curl -sf "$BACKEND/health" | python3 -m json.tool || { echo "FAIL: backend not reachable"; exit 1; }

echo ""
echo "── Login as demo user ───────────────────────"
TOKEN=$(curl -sf -X POST "$BACKEND/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
  echo "FAIL: could not get token — seed data may not exist. Run: docker compose exec backend python -m app.seeds.demo_data"
  exit 1
fi
echo "OK: got token"

echo ""
echo "── Check facilities ─────────────────────────"
FCOUNT=$(curl -sf "$BACKEND/api/v1/facilities" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',len(d.get('facilities',[]))))")
echo "Facilities: $FCOUNT"
[ "$FCOUNT" -ge 1 ] || { echo "FAIL: no facilities in demo data"; exit 1; }

echo ""
echo "── Check alerts ─────────────────────────────"
ACOUNT=$(curl -sf "$BACKEND/api/v1/alerts" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))")
echo "Alerts: $ACOUNT"

echo ""
echo "── Check bills ──────────────────────────────"
FID=$(curl -sf "$BACKEND/api/v1/facilities" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['facilities'][0]['id'])")
BCOUNT=$(curl -sf "$BACKEND/api/v1/facilities/$FID/bills" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',len(d.get('bills',[]))))")
echo "Bills for first facility: $BCOUNT"
[ "$BCOUNT" -ge 1 ] || { echo "FAIL: no bills — seed data may be incomplete"; exit 1; }

echo ""
echo "── Check compressors ────────────────────────"
CCOUNT=$(curl -sf "$BACKEND/api/v1/facilities/$FID/compressors" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',len(d.get('compressors',[]))))")
echo "Compressors for first facility: $CCOUNT"

echo ""
echo "✓ Seed data looks good. Demo account is ready."
echo "  Portfolio: ~\$548k/year energy spend across 2 facilities"
echo "  Demo: demo@kelvex.io / demo123"
