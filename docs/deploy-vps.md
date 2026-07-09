# Deploying Kelvex to a VPS

Total time: ~15 minutes, most of it waiting on DNS.

## 1. Create the server (~5 min, Hetzner shown)

1. https://console.hetzner.com → New Project → Add Server
2. Location: US East (Ashburn) · Image: **Ubuntu 24.04** · Type: **CX32**
   (4 vCPU / 8 GB — TimescaleDB + 4 API workers + Celery want the headroom;
   CX22 works to start if you want to save €5/mo)
3. Add your SSH key (Mac: `cat ~/.ssh/id_ed25519.pub`, create with
   `ssh-keygen -t ed25519` if you don't have one)
4. Create → note the server IP

## 2. Point DNS (do this immediately — propagation takes minutes)

At your DNS provider for kelvex.io:

| Type | Name | Value      |
|------|------|------------|
| A    | app  | server IP  |

`provision.sh` refuses to run until `app.kelvex.io` resolves to the server,
because Let's Encrypt needs it.

## 3. Provision (one command)

```bash
ssh root@<server-ip>
curl -fsSL https://raw.githubusercontent.com/hayescarrera/kelvex/main/provision.sh | bash
```

If the repo is private, clone with a token first, then run it locally:

```bash
git clone https://<github-user>:<personal-access-token>@github.com/hayescarrera/kelvex.git /opt/kelvex
cd /opt/kelvex && ./provision.sh
```

The script installs Docker, generates production secrets (**save them when
they print — the encryption key is unrecoverable**), issues the TLS
certificate, and deploys the full stack: API (4 workers + engine leader
election), Celery worker + beat, TimescaleDB, Redis, nginx, and the nightly
backup service.

Optional: pass SMTP/ops-email at provision time so alert emails work day one:

```bash
OPS_ALERT_EMAIL=ben@thelinders.com SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... ./provision.sh
```

(Or edit `/opt/kelvex/.env.production` later and `./deploy.sh`.)

## 4. Verify

```bash
curl -s https://app.kelvex.io/health   # {"status":"healthy",...}
cd /opt/kelvex
docker compose -f docker-compose.prod.yml --env-file .env.production ps
# expect: backend, worker, beat, backup, db, redis, frontend, nginx — all Up
```

## 5. Enable CI auto-deploy (optional but recommended)

GitHub → hayescarrera/kelvex → Settings → Secrets and variables → Actions:

| Secret        | Value                                              |
|---------------|----------------------------------------------------|
| `DEPLOY_HOST` | server IP                                          |
| `DEPLOY_USER` | `root`                                             |
| `DEPLOY_KEY`  | a private key whose public half is on the server (`ssh-keygen -t ed25519 -f deploy_key`, append `deploy_key.pub` to `/root/.ssh/authorized_keys`, paste `deploy_key` contents) |

Every push to `main` then runs tests → builds → deploys. Until the secrets
exist, the deploy job skips with a notice (it does not fail).

## 6. TLS renewal (cron once)

```bash
crontab -e
# renew certs weekly; nginx reloads if anything changed
0 4 * * 1 cd /opt/kelvex && docker compose -f docker-compose.prod.yml --env-file .env.production run --rm certbot renew --webroot -w /var/www/certbot && docker compose -f docker-compose.prod.yml --env-file .env.production exec nginx nginx -s reload
```

## Disaster recovery

Nightly dumps land in the `backups` volume (14-day retention). To restore:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production exec db \
  sh /scripts/restore.sh /backups/kelvex-<TIMESTAMP>.dump
```

For off-site copies, create a Backblaze B2 bucket, configure rclone on the
server, and set `BACKUP_RCLONE_REMOTE` in `.env.production`. Do this before
onboarding the first paying customer — the compliance record must survive
losing the whole server.
