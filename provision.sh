#!/bin/bash
# Kelvex VPS provisioning — fresh Ubuntu 22.04/24.04 → running platform.
#
# Run as root on a brand-new server AFTER pointing DNS at it:
#   curl -fsSL https://raw.githubusercontent.com/hayescarrera/kelvex/main/provision.sh | bash
# or clone the repo and run ./provision.sh
#
# What it does:
#   1. Installs Docker + git, opens ports 22/80/443
#   2. Clones the repo to /opt/kelvex (or uses the existing checkout)
#   3. Generates .env.production with strong random secrets (SHOWN ONCE —
#      store them in a password manager; the encryption key is unrecoverable)
#   4. Bootstraps the Let's Encrypt cert (standalone, before nginx exists)
#   5. Runs deploy.sh
#
# Idempotent-ish: safe to re-run; it won't overwrite an existing
# .env.production or certificates.
set -euo pipefail

DOMAIN="${DOMAIN:-app.kelvex.io}"
GIT_URL="${GIT_URL:-https://github.com/hayescarrera/kelvex.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/kelvex}"
LE_EMAIL="${LE_EMAIL:-ben@thelinders.com}"

log() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }

[ "$(id -u)" = "0" ] || { echo "Run as root (sudo)."; exit 1; }

# ── 1. Base packages ──────────────────────────────────────────────────────
log "Installing Docker, git, ufw"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git ufw curl >/dev/null
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh >/dev/null
fi

ufw allow 22/tcp >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

# ── 2. Repo ───────────────────────────────────────────────────────────────
if [ ! -d "$INSTALL_DIR/.git" ]; then
    log "Cloning $GIT_URL → $INSTALL_DIR"
    git clone "$GIT_URL" "$INSTALL_DIR"
else
    log "Repo exists at $INSTALL_DIR — pulling latest"
    git -C "$INSTALL_DIR" pull origin main
fi
cd "$INSTALL_DIR"

# ── 3. Secrets / env ──────────────────────────────────────────────────────
if [ -f .env.production ]; then
    log ".env.production exists — keeping it"
else
    log "Generating .env.production with fresh secrets"
    SECRET_KEY=$(openssl rand -hex 32)
    CRED_KEY=$(openssl rand -hex 32)
    PG_PASS=$(openssl rand -hex 24)
    INVITE=$(openssl rand -hex 16)

    cat > .env.production <<EOF
SECRET_KEY=${SECRET_KEY}
CREDENTIAL_ENCRYPTION_KEY=${CRED_KEY}
POSTGRES_PASSWORD=${PG_PASS}
INVITE_SECRET=${INVITE}
CORS_ORIGINS=https://${DOMAIN}
OPS_ALERT_EMAIL=${OPS_ALERT_EMAIL:-}
SMTP_HOST=${SMTP_HOST:-}
SMTP_PORT=${SMTP_PORT:-587}
SMTP_USER=${SMTP_USER:-}
SMTP_PASSWORD=${SMTP_PASSWORD:-}
SMTP_FROM=${SMTP_FROM:-alerts@kelvex.io}
OPENEI_API_KEY=${OPENEI_API_KEY:-}
SENTRY_DSN=${SENTRY_DSN:-}
EOF
    chmod 600 .env.production

    printf '\n\033[1;33m════ SAVE THESE IN A PASSWORD MANAGER — SHOWN ONCE ════\033[0m\n'
    printf 'POSTGRES_PASSWORD:          %s\n' "$PG_PASS"
    printf 'SECRET_KEY:                 %s\n' "$SECRET_KEY"
    printf 'CREDENTIAL_ENCRYPTION_KEY:  %s\n' "$CRED_KEY"
    printf 'INVITE_SECRET:              %s\n' "$INVITE"
    printf '\033[1;33mIf CREDENTIAL_ENCRYPTION_KEY is lost, stored controller\n'
    printf 'credentials cannot be decrypted — ever.\033[0m\n\n'
fi

# ── 4. TLS bootstrap (before nginx exists) ────────────────────────────────
DC="docker compose -f docker-compose.prod.yml --env-file .env.production"

if $DC run --rm --entrypoint sh certbot -c "test -f /etc/letsencrypt/live/${DOMAIN}/fullchain.pem" 2>/dev/null; then
    log "Certificate for ${DOMAIN} already present"
else
    log "Checking DNS for ${DOMAIN}"
    SERVER_IP=$(curl -fsS4 https://ifconfig.me || true)
    DNS_IP=$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || true)
    if [ -n "$SERVER_IP" ] && [ "$DNS_IP" != "$SERVER_IP" ]; then
        echo "✗ ${DOMAIN} resolves to '${DNS_IP:-nothing}' but this server is ${SERVER_IP}."
        echo "  Point an A record at this server, wait for propagation, re-run."
        exit 1
    fi
    log "Issuing Let's Encrypt certificate (standalone on :80)"
    $DC run --rm -p 80:80 certbot certonly --standalone \
        -d "$DOMAIN" --email "$LE_EMAIL" --agree-tos --no-eff-email
fi

# ── 5. Deploy ─────────────────────────────────────────────────────────────
log "Deploying"
./deploy.sh

log "Done. Verify:"
echo "  curl -s https://${DOMAIN}/health"
echo "  $DC ps        # backend, worker, beat, backup, db, redis, nginx all up"
echo
echo "To enable CI auto-deploy, add GitHub repo secrets:"
echo "  DEPLOY_HOST=$(curl -fsS4 https://ifconfig.me 2>/dev/null || echo '<this server IP>')"
echo "  DEPLOY_USER=root   (or a deploy user)"
echo "  DEPLOY_KEY=<private key whose public half is in ~/.ssh/authorized_keys>"
