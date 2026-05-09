---
name: start-system
description: Boot the crypto trading bot stack from cold. Verifies Docker daemon, brings up all 17 services (postgres, timescale, redis, rabbitmq, prometheus, grafana, 11 Python microservices + frontend), applies pending DB migrations, runs health probes, and optionally starts the auto-trader. Use when the user says "/start the system", "start the bot", "bring up the stack", or after a reboot.
disable-model-invocation: false
---

# Start System

Boot the trading stack from cold. Idempotent — safe to run when partially up.

## Prerequisites

1. **Docker Desktop must be running on Windows.** Daemon connects via `npipe:////./pipe/dockerDesktopLinuxEngine`. If `docker info` shows `Server: failed to connect`, ask user to start Docker Desktop manually (cannot launch from WSL — sandbox-denied). Wait for whale icon stable in tray before proceeding.
2. WSL2, working dir `/mnt/d/Bimo_max/crypto-trading-bot`.
3. `.env` exists at repo root (gitignored). All compose vars have `${VAR:-default}` fallbacks, so missing keys auto-default.

## Steps

### 1. Verify daemon

```bash
docker info 2>&1 | grep -E "Server Version|Server:" | head -3
```

If `Server:` line shows connection error → STOP, ask user to start Docker Desktop, return to step 1.

### 2. Bring up full stack

```bash
docker compose -f docker-compose.unified.yml up -d
```

If a service uses `build:` (ml-prediction, sentiment-analysis), this may take 5–30 min on first run. Sentiment-analysis pulls torch + transformers — historically slow.

**WSL2 buildkit gotcha:** if build hangs, retry with `DOCKER_BUILDKIT=0` prefix. Compose default builder works for crypto-bot images.

**WSL bind-mount race:** if a service crashes with `PermissionError /app/logs`, force-recreate it: `docker compose -f docker-compose.unified.yml up -d --force-recreate <service>`.

### 3. Wait for all healthchecks

```bash
until ! docker ps --format '{{.Status}}' | grep -q '(starting)'; do sleep 5; done
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Expected: 17 containers, all `Up X minutes (healthy)` for the 11 services with healthchecks. Prometheus and Grafana don't have healthchecks — they show plain `Up`.

### 4. Apply ORM-align migrations (idempotent)

If postgres volume already initialized (existed from previous boot), `/docker-entrypoint-initdb.d/` does NOT re-run. Apply manually:

```bash
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot < infrastructure/migrations/003_portfolios_orm_align.sql
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot < infrastructure/migrations/004_positions_orm_align.sql
```

Both are idempotent (`IF NOT EXISTS` everywhere). Skipping if portfolio-manager logs already clear of `column "realized_pnl" does not exist` / `column "entry_signal_confidence" does not exist`.

### 5. Health probe sweep

```bash
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 3000; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:$port/health 2>/dev/null || echo "ERR")
  printf "%-6s %s\n" "$port" "$code"
done
```

All 11 must return `200`. If any return `ERR` or `5xx`, run `docker logs --tail 50 <container>` and diagnose.

### 6. Sanity-check live data

```bash
curl -s --max-time 5 http://localhost:8000/api/market/ticker/BTCUSDT
curl -s http://localhost:8000/api/portfolio/balance
curl -s http://localhost:8000/api/trading/status | python3 -c "import json,sys; d=json.load(sys.stdin)['status']; print('running:', d['is_running'], '| symbols:', d['symbols'], '| emergency:', d['emergency_stop']['active'])"
```

Expected: BTC ticker has `last_price` near current market (~$80k as of May 2026). Balance JSON returns `cash_balance: "100.0"`. Trading status shows `running: False` (auto-trader gated off by default).

### 7. Start auto-trader (only if user explicitly asks)

Auto-trader is **off by default** — `AUTO_TRADING_ENABLED=false` per CLAUDE.md. To start it:

```bash
# Pre-check: emergency-stop file
ls -la EMERGENCY_STOP 2>/dev/null && cat EMERGENCY_STOP

# If EMERGENCY_STOP file exists and was set by test user / stale → confirm with user before deleting
rm EMERGENCY_STOP   # only after user confirms

curl -s -X POST http://localhost:8000/api/trading/start
```

Verify loop running:

```bash
sleep 5
curl -s http://localhost:8000/api/trading/status | python3 -c "import json,sys; d=json.load(sys.stdin)['status']; print('running:', d['is_running'], '| signals:', d['total_signals_checked'])"
```

Expected: `running: True`, `signals: ≥1` after 30s.

## Endpoints reference

| URL | Purpose |
|---|---|
| http://localhost:3000 | React frontend dashboard |
| http://localhost:8000/openapi.json | Live API surface (74+ routes) |
| http://localhost:9090 | Prometheus |
| http://localhost:3001 | Grafana (admin/admin) |
| http://localhost:15672 | RabbitMQ management |

## Stop

```bash
curl -X POST http://localhost:8000/api/trading/stop          # auto-trader only
docker compose -f docker-compose.unified.yml down            # whole stack
docker compose -f docker-compose.unified.yml down -v         # stack + volumes (destroys DB!)
```

## Known boot-time issues to watch

- **`column "entry_signal_confidence" does not exist`** in trading-engine → migration 004 not applied. Run step 4.
- **`column "realized_pnl" does not exist`** in portfolio-manager → migration 003 not applied. Run step 4.
- **`KellyPositionSizer object has no attribute 'max_position_pct'`** → fixed 2026-05-04 in `lifespan/strategy.py` (use `MAX_POSITION_PCT`). If recurs, image is stale — rebuild trading-engine.
- **`'str' object has no attribute 'value'`** in dynamic risk budget → fixed 2026-05-04 in `lifespan/risk.py` (drop `.value` on `budget.market_regime`).
- **`No module named 'app.predictor'`** in ml-prediction → fixed 2026-05-04 in `app/main.py` (import from `app.ml_models.gru_model`). LSTM module removed late 2025.
- **`EMERGENCY_STOP` file present** → auto-trader halts immediately on start. File at repo root is bind-mounted to `/app/EMERGENCY_STOP`. Delete only with user authorization.
- **Sentiment-analysis build PyPI timeout** → retry with `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build sentiment-analysis`. Other 10 service images cache fine; sentiment is the historically flaky one.
