# Crypto Trading Bot

Autonomous Bybit crypto trading bot. 11 Python microservices + React frontend. **Paper-trading mode** (no real orders). Market data feeds from **Bybit mainnet** (`BYBIT_TESTNET=false`) for real prices; orders are simulated internally via `PAPER_TRADING_MODE=true`. Last active Jan 2026 — currently resuming after dormancy.

## Stack

- **Python 3.12** + FastAPI + asyncio per service. **React 18 + Vite** frontend.
- **TimescaleDB** (candles), **PostgreSQL** (app state), **Redis** (cache), **RabbitMQ** (events).
- **Docker Compose** for local. Kubernetes manifests + Helm in `infrastructure/` for prod.
- **ML**: 16 GRU price-prediction models (avg R²=0.92). Replaced LSTM in late 2025.

## Services (`services/<name>/`)

| Service | Port | Purpose |
|---|---|---|
| api-gateway | 8000 | Frontend → backend routing, auth |
| bybit-connector | 8001 | Bybit REST + WebSocket wrapper |
| market-data-service | 8002 | Candle ingest → TimescaleDB |
| portfolio-manager | 8003 | Positions, balances, P&L |
| technical-analysis | 8004 | TA indicators + GRU inference + signal aggregator |
| trading-engine | 8005 | Strategy + risk + order execution |
| notification-service | 8006 | Telegram + email alerts |
| ml-prediction-service | 8007 | Standalone ML inference endpoints |
| sentiment-analysis-service | 8008 | News / social sentiment |
| risk-metrics-service | 8009 | Risk dashboards |
| ml-retraining-service | — | Cron-driven GRU retrain (no HTTP) |

Frontend `:3000`. Prometheus `:9090`. Grafana `:3001`.

## Commands

Stack up/down (use `docker-compose.unified.yml` — `docker-compose.yml` is incomplete, missing DBs):
```
docker compose -f docker-compose.unified.yml up -d
docker compose -f docker-compose.unified.yml logs -f <service>
docker compose -f docker-compose.unified.yml down
```

Tests:
```
pytest tests/                       # repo-level integration + e2e
pytest services/<svc>/tests/        # service unit tests
pytest --cov=services --cov-report=term
```

Health: every service exposes `GET /health` and `GET /ready`.

Useful scripts at repo root: `health_check.sh`, `monitor_paper_trading.sh`, `check_services.sh`, `build-all.sh`.

## Project rules (load-bearing)

- **Risk caps are wired into trading-engine**: max 2% capital per trade, 5% daily-loss circuit-breaker. Don't relax without explicit approval.
- **Two independent flags** — don't confuse them: `BYBIT_TESTNET` selects price source (testnet=fake prices, mainnet=real). `PAPER_TRADING_MODE` / `TRADING_MODE` selects whether orders are simulated. Current state: mainnet prices + simulated orders. Real-money trading requires `PAPER_TRADING_MODE=false` *and* `TRADING_MODE=LIVE` *and* mainnet API keys with trading permissions — three deliberate steps.
- **Validated symbols**: SOL, BNB, ADA only. ETH / BTC / XRP / DOGE were excluded by paper-trading data — do not silently re-add.
- **Never commit `.env`** (already gitignored). Secrets via env vars or Vault. Bybit testnet keys only in repo.
- **REST**: gateway routes are `/api/<domain>/<resource>` (no `v1` prefix despite older docs). Domains: `portfolio`, `trading`, `risk`, `market`, `analysis`, `ml`, `sentiment`, `dashboard`, `performance`. See `http://localhost:8000/openapi.json` for the live surface. Async handlers throughout.
- **Commits**: conventional (`feat(service): ...`, `fix(service): ...`); branches `feature/<service>-<desc>`, `fix/<desc>`.

## Gotchas

- **Two compose files**: `docker-compose.unified.yml` is canonical (16 services incl. DBs). `docker-compose.yml` is missing postgres/timescaledb/redis/rabbitmq.
- **Sentiment-analysis-service image** has historically failed to build via pip (PyPI read timeouts). Other 10 service images cache fine. If a full `compose up` fails, retry the build of just that one or `--no-deps` skip it.
- **GRU models are 4+ months stale** (trained Dec 10, 2025). Retrain before relying on predictions.
- **`.claude/agents/` is empty** — older CLAUDE.md versions referenced custom subagents that were never created. Use Claude Code's built-in subagents (Explore, Plan, general-purpose, etc.).
- **Jan 2026 fixes** (commit `380a674`): SHORT enforcement, 48h max-hold, stop-loss limit-orders. These addressed an inverted R/R ratio bug. Don't regress them.
- **TimescaleDB has mixed testnet/mainnet history** as of 2026-04-25 (the flip from testnet→mainnet was mid-day). Any backtest or TA over candles from before that point will be polluted by testnet prices. Wipe `klines` / `tickers` tables if running historical analysis; live forward-going data is fine.
- **Market-data-service caches in TimescaleDB**, not Redis (Redis was empty in testing). The DB *is* the cache. If prices look stuck, hit `POST /api/v1/collect/ticker/{symbol}` on market-data-service (port 8002) to force-refresh, or wait up to 5 min for the scheduler.
- **`progress.md`** at repo root is the running session log — append at end of session; don't put architecture decisions there (those go in `docs/architecture/DECISIONS.md`).

## Deeper docs

- Architecture: `docs/architecture/SYSTEM_OVERVIEW.md`, `docs/architecture/DECISIONS.md`
- API spec: `docs/api/openapi.yaml`
- Dev setup: `docs/development/SETUP.md`, `docs/development/TROUBLESHOOTING.md`
- Recent forensics: `DEEP_INVESTIGATION_REPORT_2026-01-16.md`, `ALL_FIXES_COMPLETE_2026-01-16.md`
- Strategy reference: `STRATEGY_QUICK_REFERENCE.md`
