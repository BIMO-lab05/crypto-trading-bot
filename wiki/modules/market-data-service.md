---
type: module
path: "services/market-data-service/"
status: active
language: python
port: 8002
purpose: "Candle + ticker ingest into TimescaleDB; HTTP query surface for downstream services"
maintainer: ""
last_updated: 2026-05-05
linked_issues: []
depends_on: [bybit-connector, timescaledb, redis]
used_by: [technical-analysis, trading-engine, portfolio-manager, risk-metrics-service, ml-prediction-service, api-gateway, ml-retraining-service, notification-service]
tags: [module, service, market-data, timescaledb]
created: 2026-05-05
updated: 2026-07-29
---

# market-data-service

**Port:** `8002`
**Path:** `services/market-data-service/`
**Purpose:** Pull candles + tickers from [[bybit-connector]] on a 5-min loop, persist to TimescaleDB hypertables, expose HTTP query routes for the rest of the stack.

## Overview

FastAPI app. Lifespan boots Timescale, runs hypertable + retention + `is_mainnet` migrations, opens an httpx pool against [[bybit-connector]], starts an in-process APScheduler. **TimescaleDB is the cache** — Redis is a thin 5–60 s TTL skin over two query routes only (`/ticker`, `/latest`). See [[../decisions/ADR-006-mainnet-prices-paper-orders]] for why prices are real even though orders are paper.

Feeds the [[../flows/Signal-Pipeline]]: `market-data → technical-analysis (TA + GRU) → trading-engine`.

## Endpoints

All routes carry `/api/v1/` prefix when called direct. Gateway strips it (see contradiction below).

**Data Collection** (`X-API-Key` required):
- `POST /api/v1/collect/kline/{symbol}` — `interval` (default `60`), `days` 1–30. 20/min.
- `POST /api/v1/collect/ticker/{symbol}` — force-refresh single ticker. 30/min. *This is the cache-bust hook called out in the project CLAUDE.md.*
- `POST /api/v1/collect/bulk` — body `symbols`, `interval`, `days`. Max 10 symbols. 5/min.

**Market Data** (no auth):
- `GET /api/v1/klines/{symbol}` — `interval`, `start_time`, `end_time`, `limit` (1–10000), `mainnet_only` (default `True`). 300/min. **Interval now validated against a whitelist → 400 on bad values** (`handlers/query.py:24–31`); a bad interval used to silently return an empty series.
- `GET /api/v1/ticker/{symbol}` — Redis-cached 5 s. 300/min.
- `GET /api/v1/latest/{symbol}` — most recent kline, Redis-cached 60 s. 300/min. **`get_latest_kline` now filters `is_mainnet` too** (`repository.py:151–178`) — previously only `get_klines` filtered, so `/latest` could surface a testnet-polluted row.

**Scheduler** (`X-API-Key` for mutation):
- `GET /api/v1/scheduler/status`
- `POST /api/v1/scheduler/start` / `stop`
- `POST /api/v1/scheduler/collect` — one-shot full sweep.

10 application routes total + `/health`, `/ready`, `/metrics`.

## Symbols handled

Two lists — they disagree. See [[../concepts/Validated-Symbols]].

`config.py default_symbols` (14): `BTC, ETH, BNB, SOL, ADA, AVAX, LINK, ARB, OP, SUI, APT, DOT, LTC, POL` (all `USDT`). Comment: "synchronized with trading-engine; XRP/DOGE excluded".

`scheduler.py TRADING_PAIRS` (7) — **what actually populates Timescale**: `BTC, ETH, BNB, SOL, XRP, ADA, DOGE`. Includes XRP/DOGE despite policy.

Repo-level CLAUDE.md says only 5 are active (BTC, ETH, SOL, BNB, ADA) — neither file matches. Real ingest is broader than policy.

## Storage

TimescaleDB database `market_data` (separate from app `cryptobot` DB). Engine pool 10–20, `pool_pre_ping`, recycle 1 h.

| Table | Hypertable chunk | Retention | PK |
|---|---|---|---|
| `klines` | 1 day | 90 d | `(timestamp, symbol, interval)` |
| `tickers` | 1 day | 30 d | `(timestamp, symbol)` |
| `orderbook_snapshots` | 1 day | 7 d | autoincr `id` |

`klines` columns: OHLCV `NUMERIC(20,8)` + `turnover` + `is_mainnet BOOLEAN DEFAULT true` (added 2026-04-29 audit) + `created_at`. Indexes on `(symbol, interval, timestamp)`, `(timestamp)`, `(is_mainnet)`.

`tickers` columns: `last_price`, `bid_price`, `ask_price`, `high_24h`, `low_24h`, `volume_24h`, `turnover_24h`, `price_change_24h`.

A `klines_1h` continuous aggregate is defined in raw SQL inside `models.py` but **never executed** by `create_hypertables()` — dead code. Don't query it.

## Scheduler

In-process `AsyncIOScheduler`. Three jobs, all `max_instances=1`:

1. **`ticker_collection`** — every 5 min. Iterates 7 pairs, hits `BybitDataFetcher.get_ticker`, upserts `tickers`.
2. **`kline_collection`** — every 5 min, +2 min offset. 7 pairs × 6 intervals (`1, 5, 15, 60, 240, D`) = 42 calls, last 200 candles each, `0.5 s` sleep between calls. **Still-forming (unclosed) candles are now dropped at ingest** (`scheduler.py:123–138`: keeps only `k["timestamp"] + interval_ms <= now_ms`) — no more repainting signals downstream.
3. **`hourly_full_collection`** — `CronTrigger(minute=0)`. Backup full sweep (ticker → 2 s → kline).

Hourly job overlaps the 5-min jobs at `:00` — same data fetched twice that minute.

## Internal deps

- [[bybit-connector]] — sole upstream. HTTP via `httpx.AsyncClient`, pool 100/20, 30 s timeout. Env: `BYBIT_CONNECTOR_URL` (compose: `http://bybit-connector:8001`; in-code default `http://localhost:8002` is wrong — would self-loop).
- TimescaleDB — `TIMESCALE_*` env vars, db `market_data`.
- Redis — `REDIS_*` env vars; ticker/latest TTL only.
- `BYBIT_TESTNET` env var mirrored from connector — drives `is_mainnet` flag on inserted rows. See [[../concepts/Trading-Mode-Flags]].

RabbitMQ env vars are declared but **no broker client code exists**. Service does not publish.

## Used by

`MARKET_DATA_URL=http://market-data:8002` set in compose for: api-gateway, [[trading-engine]], [[technical-analysis]], portfolio-manager, risk-metrics-service, ml-prediction-service, ml-retraining-service, notification-service. Frontend reaches it via gateway proxy.

## RabbitMQ

Not wired. CLAUDE.md hint of `market.data.{symbol}` topic is **not implemented** — consumers poll HTTP. Env vars present but unused.

## Key files

- `services/market-data-service/app/main.py` — FastAPI app, routes, lifespan.
- `services/market-data-service/app/scheduler.py` — APScheduler jobs, `TRADING_PAIRS`, `KLINE_INTERVALS`.
- `services/market-data-service/app/config.py` — Settings; `default_symbols`, `bybit_testnet` mirror.
- `services/market-data-service/app/models.py` — SQLAlchemy Kline / Ticker / OrderBook.
- `services/market-data-service/app/database.py` — `create_hypertables`, `is_mainnet` migration, per-stmt isolated transactions.
- `services/market-data-service/app/fetcher.py` — `BybitDataFetcher` HTTP client.
- `services/market-data-service/app/repository.py` — `KlineRepository.bulk_upsert`, `TickerRepository.save_ticker`.
- `services/market-data-service/app/cache.py` — Redis TTL helpers.
- `services/market-data-service/app/handlers/` — Phase-2 modular route logic.
- `services/market-data-service/app/circuit_breaker.py` — retry around bybit-connector calls.

## Gotchas

- **Mixed testnet/mainnet candle history before 2026-04-25 mid-day — REPAIRED 2026-07-28.** `is_mainnet` column added 2026-04-29 defaulted to `true`, so pre-flip testnet rows (BTC @ $1.76M) were mislabelled and the `mainnet_only=true` filter passed them through. Fixed by the one-time `scripts/repair_testnet_pollution.sql` (+ `.sh`): demotes pre-cutoff and price-outlier rows to `is_mainnet=false` (~118k rows demoted; **max mainnet BTC close now ~$82,791, was ~$1.76M**). Run it once before trusting any historical signal/backtest; after that the `is_mainnet` filter is authoritative. Note: the `tickers` table has no `is_mainnet` column, so the script demotes ticker rows by cutoff timestamp only.
- **Two symbol lists drift.** `config.default_symbols` (14) is referenced by Settings but `scheduler.TRADING_PAIRS` (7, includes XRP/DOGE) is what actually pulls data. DOGE/XRP candles arrive every 5 min despite the policy "still excluded" comment.
- **Stale `:8003` in older docs.** Several `.env.example` and READMEs show `MARKET_DATA_URL=http://localhost:8003`. Correct port is **8002**. Compose envs are right; READMEs lag.
- **`klines_1h` continuous aggregate is unbuilt.** SQL exists in `models.CREATE_HYPERTABLE_SQL` but `create_hypertables()` never runs it. Querying it errors.
- **`bybit_connector_url` default in code is `:8002`** — same as this service's own port. Self-loop on standalone (non-compose) runs.
- **Per-statement isolated transactions in `create_hypertables`.** History: monolithic transaction silently dropped the `is_mainnet` ALTER on first deploy because an earlier hypertable failure poisoned the txn. Don't refactor back.
- **Hourly + 5-min jobs collide at `:00`.** Same data fetched twice. APScheduler `max_instances=1` is per-job, not cross-job.
- **httpx pool leak fixed (2026-07-29).** Each scheduled run builds a fresh `BybitDataFetcher` (100-connection pool); the pool was never closed → socket/FD exhaustion over time. Now `try/finally: await fetcher.close()` in both collectors (`scheduler.py:88–93`, `168–170`).
- **Graceful-shutdown crash fixed (2026-07-29).** A bad `logger` kwarg raised `TypeError` during shutdown, aborting scheduler/fetcher/Redis/DB cleanup (resource leaks every shutdown). Shutdown logging now uses valid `extra=` (`main.py:111`).

## Contradictions vs project CLAUDE.md

1. **5-symbol claim**. Repo CLAUDE.md says BTC/ETH/SOL/BNB/ADA active 2026-05-03 with BTC+ETH re-added that day. Reality: `default_symbols` lists 14 (already had BTC/ETH); scheduler runs 7 (still pulls XRP/DOGE).
2. **No-`v1`-prefix rule**. Applies to api-gateway only. This service still uses `/api/v1/...` natively. Gateway rewrites — both layers coexist.
3. **`market.data.{symbol}` RabbitMQ topic**. CLAUDE.md hints at it; no publishing code exists. Pure HTTP poll.
4. **Cache-refresh hook path**. CLAUDE.md `POST /api/v1/collect/ticker/{symbol}` is correct, but the route requires `X-API-Key` — bare curl returns 401.

## Related

- [[../flows/Signal-Pipeline]]
- [[../concepts/Validated-Symbols]]
- [[../concepts/Trading-Mode-Flags]]
- [[../decisions/ADR-006-mainnet-prices-paper-orders]]
- [[../sources/SYSTEM_OVERVIEW]]
- [[bybit-connector]]
- [[technical-analysis]]
- [[trading-engine]]

## Corrections 2026-07-29

Reflects the 2026-07-28/29 data-integrity + audit campaign (verified in source):

- **`get_latest_kline` now filters `is_mainnet`** (`repository.py:151–178`) — was mainnet-blind, unlike `get_klines`.
- **Still-forming candles dropped at ingest** (`scheduler.py:123–138`).
- **httpx connection-pool leak fixed** in both scheduler collectors (`scheduler.py:88–93,168–170`, `try/finally` close).
- **Graceful-shutdown crash fixed** (bad logger kwarg → `TypeError`; `main.py:111`).
- **Interval validation on query endpoints** (`handlers/query.py:24–31`, whitelist → 400).
- **2026-04-25 testnet→mainnet DB pollution repaired** via `scripts/repair_testnet_pollution.sql` (~118k rows demoted; max mainnet BTC close ~$82,791, was ~$1.76M). See the pollution gotcha.
