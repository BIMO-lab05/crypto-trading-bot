# System Overview

**Status:** current · **Rewritten:** 2026-07-30 (previous version was 2025-10-30: 6 services, wrong ports, fictional event bus — archived knowledge preserved in `wiki/sources/SYSTEM_OVERVIEW.md`)
**Canonical living copy:** `wiki/modules/Architecture-Overview.md` — this file is its repo-facing mirror. Update both together.

Autonomous Bybit crypto trading bot: **11 Python 3.12 + FastAPI microservices** and a **React 18 + Vite frontend**, orchestrated with `docker-compose.unified.yml` (canonical per ADR-009). Paper-trading mode: real mainnet prices, simulated orders (ADR-006).

## Communication model

Services communicate via **synchronous REST only**. Gateway routes are `/api/<domain>/<resource>` with **no `/v1/` prefix** (ADR-007); service-to-service calls are direct HTTP. **There is no live RabbitMQ event bus** — AMQP settings exist in configs and older docs, but no service declares a publisher, consumer, or queue (ADR-016). Treat any "event topic" reference (`trade.execute`, `analysis.signal.*`, …) as aspirational.

## Services

| Service | Port | Purpose |
|---|---|---|
| api-gateway | 8000 | Frontend → backend routing, auth (mode-gated per ADR-022) |
| bybit-connector | 8001 | Bybit REST + WebSocket wrapper (HMAC signing per ADR-023) |
| market-data-service | 8002 | Candle ingest → TimescaleDB (DB is the cache; Redis unused here) |
| portfolio-manager | 8003 | Positions, balances, P&L — mirrors the engine (ADR-024) |
| technical-analysis | 8004 | TA indicators + GRU inference + signal aggregator (data-integrity gate per ADR-021) |
| trading-engine | 8005 | Strategy + risk + order execution (accounting per ADR-018, risk per ADR-010/019) |
| notification-service | 8006 | Telegram + email alerts (real delivery default per ADR-025) |
| ml-prediction-service | 8007 | Standalone ML inference — behind compose `ml` profile, off by default |
| sentiment-analysis-service | 8008 | News/social sentiment — behind compose `analytics` profile, off by default; leg removed from pipeline |
| risk-metrics-service | 8009 | Risk dashboards (paper-mode aligned per ADR-017) |
| ml-retraining-service | — | Cron-driven GRU retrain (no HTTP) |

Frontend `:3000` · Prometheus `:9090` · Grafana `:3001`. A `tournament-harness` compose service runs edge-measurement tournaments.

## Layered view

1. **Edge** — frontend ↔ api-gateway (auth, routing)
2. **Domain** — portfolio-manager, trading-engine, risk-metrics-service, notification-service
3. **Signal** — technical-analysis (+ ml-prediction, sentiment when profiles enabled)
4. **Data** — market-data-service, bybit-connector
5. **Background** — ml-retraining-service (cron)
6. **Observability** — Prometheus, Grafana

## State

- **PostgreSQL** — application state (positions, trades, users)
- **TimescaleDB** — candles/tickers time-series (`klines` hypertable, 90-day retention — see `DATA_PROFILE_KLINES.md`)
- **Redis** — ephemeral cache (largely idle; market-data caches in TimescaleDB)

## Safety model

Four deliberate steps to LIVE (`BYBIT_TESTNET`, `PAPER_TRADING_MODE`/`TRADING_MODE`, live-permission keys, `LIVE_TRADING_ACK`) — see `CLAUDE.md`. Operator kill switch: `safety/EMERGENCY_STOP` file (ADR-005); a file-halt exits the auto-trade loop and requires manual restart, while risk kill-switch halts (equity/streak, ADR-019) auto-resume when limits clear.

## Deeper references

- Signal path, order lifecycle, emergency stop: `wiki/flows/`
- Per-service detail: `wiki/modules/<service>.md`
- Decisions: `wiki/decisions/` (ADR-001 – ADR-027)
- Live API surface: `http://localhost:8000/openapi.json`
