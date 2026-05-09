# Headless Free-Tier Deploy — Oracle Cloud Always Free

Move bot off laptop. Single VM, $0/month, 24/7 paper-trading. Laptop out of loop.

---

## TL;DR

- **Host**: Oracle Cloud Always Free, ARM Ampere A1, 4 OCPU / 16-24 GB RAM / 100 GB block storage. Forever free.
- **Stack**: 8 services (was 16). Drops rabbitmq, frontend, api-gateway, ml-prediction, ml-retraining, sentiment, notification, risk-metrics, prometheus, grafana.
- **Surface**: only `trading-engine:8005` exposed via Cloudflare Tunnel + Access (email-allowlist).
- **Cron**: ml-retraining moves to GitHub Actions weekly (Mon 02:00 UTC).
- **Cost**: $0. Fallback if A1 capacity unavailable: Hetzner CX22 €3.79/mo.

---

## 1. Why

Local Docker stack = 11 services + 4 stateful + monitoring. Heavy on laptop. Trading bot needs 24/7 uptime (paper-trades against live Bybit prices). Free tiers with idle-sleep / WebSocket-drop / hour-cap = disqualified for always-on. Oracle A1 = only viable single-host free option in 2026.

## 2. What was cut

| Service | Reason |
|---|---|
| rabbitmq | Zero real publishers/consumers in code. Probe dormant. |
| frontend | Observability only. Hit API directly via Cloudflare Tunnel. |
| api-gateway | Frontend dependency. Headless mode hits trading-engine directly. |
| prometheus, grafana | Replace with `docker logs` + Healthchecks.io free pings. |
| sentiment-analysis | Removed from signal weighting 2026-05-02 (no edge measured). |
| ml-prediction | TF + 16 GRU models = 2GB. Aggregator falls back gracefully. Models 4mo stale anyway. |
| ml-retraining | Weekly cron → GitHub Actions instead of always-on container. |
| notification-service | Auto-trader fails-soft if absent. Re-enable later if needed. |
| risk-metrics | Observability only. Off trading path. |

## 3. What stayed

| Service | Port | RAM cap | Role |
|---|---|---|---|
| postgres | 5432 (internal) | 1G | App state, trades, positions |
| timescaledb | 5432 (internal) | 2G | Candles, ticks, indicators |
| redis | 6379 (internal) | 512M | Price cache, signal cache |
| bybit-connector | 8001 (internal) | 512M | Bybit REST wrapper |
| market-data | 8002 (internal) | 1G | Candle scheduler (5min poll) |
| technical-analysis | 8004 (internal) | 1G | TA indicators + MTF aggregator |
| trading-engine | 8005 (host bound `127.0.0.1`) | 1G | Auto-trader loop, decision engine |
| portfolio-manager | 8003 (internal) | 512M | Positions, balance, P&L |

Total RAM ~7-8 GB committed; A1 24 GB has ~12 GB headroom.

## 4. Files in this deploy

| Path | Purpose |
|---|---|
| `docker-compose.headless.yml` | Trimmed 8-service stack |
| `headless.env.example` | Env template — copy to `.env` on VM |
| `scripts/oracle-bootstrap.sh` | Idempotent fresh-VM setup |
| `.github/workflows/ml-retrain.yml` | Weekly retrain via SSH from GH Actions |
| `infrastructure/scripts/init-timescale.sql` | Patched: tighter retention (ticks 14d, orderbook 7d, candles 90d) |
| `services/trading-engine/app/main.py` | Patched: `LIVE_TRADING_ACK` gate in lifespan |

## 5. Pre-deploy

### 5.1 Provision Oracle A1

1. Sign up `cloud.oracle.com/free` (credit card hold, no charge).
2. Create compute → VM.Standard.A1.Flex, Ubuntu 22.04 LTS.
3. Shape: 4 OCPU, 16-24 GB RAM. Boot volume 100 GB.
4. Paste SSH public key.
5. If region returns "Out of capacity": pick 3-AD region (Ashburn / Phoenix / London).
6. Note the public IP.

### 5.2 Cloudflare prep

1. Free Cloudflare account, add domain (Cloudflare DNS).
2. Zero Trust dashboard → Access → Applications (free for 50 users).

### 5.3 Edit bootstrap script

Update `scripts/oracle-bootstrap.sh:18` `REPO_URL` to your fork URL.

## 6. Deploy

### 6.1 Bootstrap VM

```bash
# On laptop
scp scripts/oracle-bootstrap.sh ubuntu@<vm-ip>:~/
ssh ubuntu@<vm-ip>
bash oracle-bootstrap.sh
exit  # log out and back in for docker group membership
```

### 6.2 Push secrets

```bash
# On laptop
cp headless.env.example .env.deploy
# Fill BYBIT_API_KEY, BYBIT_API_SECRET, *_PASSWORD values with real secrets
chmod 600 .env.deploy
scp .env.deploy ubuntu@<vm-ip>:~/bot/.env
ssh ubuntu@<vm-ip> 'chmod 600 ~/bot/.env'
rm .env.deploy  # Don't leave on laptop
```

Generate strong passwords:
```bash
openssl rand -base64 32   # use for POSTGRES_PASSWORD, TIMESCALE_PASSWORD, REDIS_PASSWORD
```

### 6.3 First start

```bash
ssh ubuntu@<vm-ip>
cd ~/bot
docker compose -f docker-compose.headless.yml pull
docker compose -f docker-compose.headless.yml up -d
docker compose -f docker-compose.headless.yml ps
```

All 8 services should reach `Up (healthy)` within 90 seconds.

### 6.4 Cloudflare Tunnel

```bash
# On VM
cloudflared tunnel login   # opens browser auth flow
cloudflared tunnel create bot-api
cloudflared tunnel route dns bot-api bot.<your-domain>

# Edit ~/.cloudflared/config.yml:
cat > ~/.cloudflared/config.yml <<'EOF'
tunnel: <tunnel-id-from-create>
credentials-file: /home/ubuntu/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: bot.<your-domain>
    service: http://localhost:8005
  - service: http_status:404
EOF

sudo cloudflared service install <tunnel-token>
sudo systemctl status cloudflared
```

In Cloudflare Zero Trust → Access → Applications:
1. Add Self-Hosted application.
2. Domain: `bot.<your-domain>`.
3. Identity provider: One-time PIN (email).
4. Policy: allow only your email.

### 6.5 GitHub Actions secrets (for ml-retrain)

GH repo → Settings → Secrets and variables → Actions:
- `ORACLE_HOST` — public IP
- `ORACLE_USER` — `ubuntu`
- `ORACLE_SSH_KEY` — private key for the VM (separate key, not the one on laptop)

Generate dedicated CI key:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/oracle_ci -C github-actions
cat ~/.ssh/oracle_ci.pub  # paste into VM ~/.ssh/authorized_keys
cat ~/.ssh/oracle_ci      # paste into ORACLE_SSH_KEY secret
```

Restrict the key in `~/.ssh/authorized_keys` on the VM:
```
command="cd ~/bot && docker compose -f docker-compose.headless.yml run --rm --build ml-retraining python -m app.main --once" ssh-ed25519 AAAA...
```

## 7. Verify

| When | Check | Pass |
|---|---|---|
| T+0 | `docker compose -f docker-compose.headless.yml ps` | All 8 `Up (healthy)` |
| T+2 min | `docker compose logs --tail=200 bybit-connector` | Bybit REST 200s, no auth errors |
| T+5 min | `docker compose logs --tail=200 trading-engine \| grep -iE "decision\|signal\|cycle"` | ≥1 cycle |
| T+10 min | From phone: `curl https://bot.<domain>/api/portfolio/positions` (CF Access OTP) | JSON, not 502 |
| T+1 h | `docker compose exec timescaledb psql -U cryptobot -d market_data -c "SELECT max(time) FROM market_data.candles;"` | Within last 5 min |
| T+1 h | `docker compose exec postgres psql -U cryptobot -d cryptobot -c "SELECT count(*) FROM signals WHERE created_at > now() - interval '1 hour';"` | ≥1 |
| T+24 h | OCI console: uptime 100%, CPU 5-15%, RAM 8-12 GB | Stable |
| T+24 h | `SELECT count(*) FROM paper_trades WHERE created_at > now() - interval '24 hours';` | ≥1 (depends on signal generation) |
| Laptop-out | Shut down Docker Desktop, close SSH, hit endpoint from phone hotspot | 200 OK |

If T+5 min shows no signals: check if ML fallback raised. `docker compose logs trading-engine | grep -i "ml prediction"`. Expected: warnings about ml-prediction unreachable, then signal cycle continues.

## 8. Operational

### 8.1 Daily

Free Healthchecks.io ping setup:
```bash
# VM crontab -e
*/10 * * * * curl -fsS --retry 3 https://localhost:8005/health > /dev/null && curl -fsS --retry 3 https://hc-ping.com/<your-uuid> > /dev/null
```

Email alerts if `/health` fails for 30 min.

### 8.2 Logs

```bash
ssh ubuntu@<vm-ip>
cd ~/bot
docker compose -f docker-compose.headless.yml logs -f trading-engine
docker compose -f docker-compose.headless.yml logs --since 24h --tail 1000 > /tmp/last24h.log
```

Rotate Docker logs (already configured via `restart: unless-stopped` + Docker default 10x rotation; verify with `docker info | grep -A3 "Logging Driver"`).

### 8.3 Backup

TimescaleDB nightly dump to local file (free) or S3 (~$0.02/mo for ~1GB):
```bash
# VM crontab -e
0 3 * * * docker compose -f /home/ubuntu/bot/docker-compose.headless.yml exec -T timescaledb pg_dump -U cryptobot market_data | gzip > /home/ubuntu/backups/timescale-$(date +\%Y\%m\%d).sql.gz
0 4 * * * find /home/ubuntu/backups/ -name "timescale-*.sql.gz" -mtime +7 -delete
```

### 8.4 Update bot

```bash
ssh ubuntu@<vm-ip>
cd ~/bot
git pull
docker compose -f docker-compose.headless.yml build
docker compose -f docker-compose.headless.yml up -d
```

### 8.5 Halt trading

File-based kill switch:
```bash
ssh ubuntu@<vm-ip> 'touch ~/bot/EMERGENCY_STOP'
docker compose -f docker-compose.headless.yml restart trading-engine
# Resume:
ssh ubuntu@<vm-ip> 'rm ~/bot/EMERGENCY_STOP'
docker compose -f docker-compose.headless.yml restart trading-engine
```

### 8.6 Re-enable dropped services

To bring `ml-prediction` back (always-on, +2GB RAM):
1. Copy ml-prediction block from `docker-compose.unified.yml:651-704` into headless.
2. Set `ENABLE_ML_PREDICTIONS=true` in `.env`.
3. `docker compose up -d`.

To bring `notification-service` back:
1. Copy block from `docker-compose.unified.yml:606-647`.
2. Add `NOTIFICATION_SERVICE_URL=http://notification-service:8006` to trading-engine env.
3. Provide Telegram/Slack/SMTP creds in `services/notification-service/.env`.

## 9. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Mainnet/paper invariant drift | Lifespan gate refuses LIVE without `LIVE_TRADING_ACK`. |
| Oracle ARM idle reclaim (<20% CPU 7d) | 5-min market-data poller + Healthchecks ping keep CPU above threshold. Verify week 1. |
| Stale GRU models (4 mo old) | ml-prediction off in headless; aggregator falls back to TA + MTF. Re-enable after first GH Actions retrain. |
| A1 capacity rationing | Try 3-AD regions first. Fallback: Hetzner CX22 €3.79/mo (same compose, x86 image variants). |
| Free-tier rule changes | Monitor Oracle Always Free terms quarterly. Migration path to Hetzner is identical compose file. |
| Secrets leak | `.env` gitignored, `chmod 600`, separate CI SSH key with `command=` restriction. Rotate `BYBIT_API_KEY` after first deploy. |
| Cloudflare Tunnel down | `trading-engine` keeps running. Direct SSH access still works for management. |
| TimescaleDB disk grows | Retention policies cap ticks 14d / orderbook 7d / candles+indicators 90d. Steady-state ~2 GB. |

## 10. Cost ledger

| Item | Cost |
|---|---|
| Oracle Cloud Always Free A1 VM | $0 |
| Cloudflare DNS + Tunnel + Access (50 users) | $0 |
| Healthchecks.io free (20 checks) | $0 |
| GitHub Actions (2000 min/mo private repo) | $0 (ml-retrain ~10 min/wk = ~40 min/mo) |
| Domain registration | varies (~$10/yr if not already owned) |
| **Total recurring** | **$0/mo** + domain |

Fallback if Oracle A1 unavailable: Hetzner CX22 €3.79/mo (no other changes).

## 11. Migration off

If outgrowing free tier:

- **Single bigger VM**: Hetzner CCX23 (4 vCPU dedicated / 16 GB) €15/mo. Same compose. Re-enable ml-prediction.
- **Managed split**: Neon Postgres ($19/mo Pro for TimescaleDB ext) + Upstash Redis ($10/mo) + Hetzner compute. ~$50/mo total.
- **Kubernetes**: existing Helm charts at `infrastructure/helm/crypto-trading-bot/` deploy to any k8s cluster. DigitalOcean K8s starts $12/mo control plane + nodes.

## 12. Out of scope

- Frontend hosting (skipped headless; later: Cloudflare Pages free static).
- Real-money trading flip — separate deliberate three-flag change (`PAPER_TRADING_MODE=false` + `TRADING_MODE=LIVE` + `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` + mainnet keys with trade permissions).
- Multi-region HA, blue/green deploys — overkill for paper-trading personal bot.

---

**See also:**
- `/home/moha/.claude/plans/crystalline-watching-sphinx.md` — original plan + Phase 1 research
- `CLAUDE.md` (repo root) — project rules, risk caps, Bybit flag matrix
- `docs/DEPLOYMENT_RUNBOOK.md` — full Kubernetes deploy (alternative to this headless setup)
