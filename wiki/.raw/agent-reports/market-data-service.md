# market-data-service — raw report

Source: `services/market-data-service/app/` (main.py, config.py, scheduler.py, models.py, database.py, fetcher.py, handlers/)
Compiled: 2026-05-05

## Endpoints

FastAPI app `app/main.py` (lifespan-based). All non-health routes carry the `/api/v1/` prefix. CLAUDE.md note "no v1 prefix in current API" applies to the **api-gateway** surface, not direct service calls — `POST /api/v1/collect/ticker/{symbol}` is correct here. See contradictions section.

Data Collection (`tags=["Data Collection"]`):
- `POST /api/v1/collect/kline/{symbol}` — `interval` (default `60`), `days` (1–30, default 7). Rate 20/min. Auth: `X-API-Key`.
- `POST /api/v1/collect/ticker/{symbol}` — force-refresh ticker. Rate 30/min. Auth: `X-API-Key`. (Confirms CLAUDE.md cache-refresh hook.)
- `POST /api/v1/collect/bulk` — body `symbols: List[str] | None`, `interval`, `days`. Max 10 symbols. Rate 5/min. Auth: `X-API-Key`.

Market Data query (`tags=["Market Data"]`):
- `GET /api/v1/klines/{symbol}` — `interval`, `start_time`, `end_time`, `limit` (1–10000, default 100), `mainnet_only` (default `True`). Rate 300/min. No auth.
- `GET /api/v1/ticker/{symbol}` — Redis-cached. Rate 300/min. No auth.
- `GET /api/v1/latest/{symbol}` — most recent kline, Redis-cached. Rate 300/min.

Scheduler control (`tags=["Scheduler"]`):
- `GET /api/v1/scheduler/status` — job list + next run times. Rate 30/min.
- `POST /api/v1/scheduler/start` — manual start. Auth: `X-API-Key`. Rate 10/min.
- `POST /api/v1/scheduler/stop` — manual stop. Auth: `X-API-Key`. Rate 10/min.
- `POST /api/v1/scheduler/collect` — trigger one-shot full collection cycle. Auth: `X-API-Key`. Rate 5/min.

Total: **10 application routes** + `/health`, `/ready`, `/metrics`.

## Symbols handled

Two distinct symbol lists exist — they disagree.

`app/config.py` `Settings.default_symbols` (used by `symbols_list` property; consumers: query/collection paths via Settings):
```
BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, ADAUSDT, AVAXUSDT, LINKUSDT,
ARBUSDT, OPUSDT, SUIUSDT,
APTUSDT, DOTUSDT, LTCUSDT, POLUSDT
```
14 pairs. Comment says "SYNCHRONIZED with trading-engine config.py" + "ETH re-added 2026-05-03" + "Still excluded: XRP, DOGE".

`app/scheduler.py` hard-codes its own list (`TRADING_PAIRS`, used by the APScheduler jobs):
```
BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT
```
7 pairs — **includes XRPUSDT and DOGEUSDT** despite config.py marking them "Still excluded" with negative-PnL annotations.

CLAUDE.md says "5 active 2026-05-03: BTC, ETH, SOL, BNB, ADA. XRP/DOGE excluded." Neither file matches this exactly.

## Storage

TimescaleDB (separate `market_data` database — distinct from `cryptobot` postgres). Connection via `Settings.timescale_url` → `postgresql+asyncpg://...@timescale-host:5432/market_data`. Engine pool: 10–20 conns, `pool_pre_ping`, recycle 1h.

Hypertables created at startup (`create_hypertables()` in `app/database.py`), each in its own transaction (autocommit-style — earlier monolithic transaction lost the `is_mainnet` migration on first deploy 2026-04-29):

| Table | Purpose | Hypertable chunk | Retention |
|---|---|---|---|
| `klines` | OHLCV candles | 1 day (`86_400_000` ms) | 90 days |
| `tickers` | last/bid/ask, 24h stats | 1 day | 30 days |
| `orderbook_snapshots` | JSON snapshot blobs | 1 day | 7 days |

Schema sketches (`app/models.py`):

`klines` PK `(timestamp, symbol, interval)`:
- `timestamp BIGINT` (ms), `symbol VARCHAR(20)`, `interval VARCHAR(10)`
- `open, high, low, close, volume NUMERIC(20,8)`, `turnover NUMERIC(30,8) NULL`
- `is_mainnet BOOLEAN NOT NULL DEFAULT true` (added 2026-04-29)
- `created_at BIGINT`
- Indexes: `(symbol, interval, timestamp)`, `(timestamp)`, `(is_mainnet)`

`tickers` PK `(timestamp, symbol)`:
- `last_price` (NOT NULL), `bid_price`, `ask_price` (NUMERIC 20,8 NULLABLE)
- `high_24h, low_24h, volume_24h, turnover_24h, price_change_24h`
- Index `(symbol, timestamp)`

`orderbook_snapshots` PK auto-incr `id`, `snapshot_data VARCHAR` (JSON-as-string).

A continuous-aggregate `klines_1h` is defined in raw SQL (`models.py CREATE_HYPERTABLE_SQL`) but **not** invoked by `create_hypertables()` — only the bare `create_hypertable` + retention + `is_mainnet` ALTER run. The 1h cont-agg is dead code.

**TimescaleDB IS the cache** (CLAUDE.md). Confirmed at code level:
- Redis is wired (`app/cache.py`, `close_redis` in lifespan), used as a thin TTL layer for `/api/v1/ticker/{symbol}` (`cache_ttl_ticker=5s`) and `/api/v1/latest/{symbol}` (`cache_ttl_kline=60s`).
- All scheduler-driven persistence goes to Timescale; no Redis-only state. If Redis is empty/cold, queries fall back to Timescale.

## Scheduler

In-process `apscheduler.schedulers.asyncio.AsyncIOScheduler` (`app/scheduler.py`). Started from FastAPI `lifespan` after database init. **No external cron**.

Three jobs registered:
1. `ticker_collection` — `IntervalTrigger(minutes=5)`. Iterates `TRADING_PAIRS`, calls fetcher → `TickerRepository.save_ticker`.
2. `kline_collection` — `IntervalTrigger(minutes=5, start_date='2024-01-01 00:02:00')` (offset +2 min). Iterates `TRADING_PAIRS × KLINE_INTERVALS = ['1','5','15','60','240','D']`, fetches last 200 candles each, bulk-upserts. `asyncio.sleep(0.5)` between calls.
3. `hourly_full_collection` — `CronTrigger(minute=0)`. Runs `collect_all_data()` (ticker then 2s gap then kline) — backup full sweep.

All `max_instances=1`, `replace_existing=True`. CLAUDE.md "5 min cadence" matches jobs 1 & 2.

## Internal deps

Sole upstream: **bybit-connector** via HTTP. `app/fetcher.py BybitDataFetcher` uses `httpx.AsyncClient` against `Settings.bybit_connector_url` (env: `BYBIT_CONNECTOR_URL`, default `http://localhost:8002` in code — but compose sets it to `http://bybit-connector:8001`). Connection pool: 100 max / 20 keep-alive / 30s expiry, 30s timeout. Wrapped by `app/circuit_breaker.py bybit_connector_retry`.

Own infra deps:
- TimescaleDB (`TIMESCALE_*` env vars; default db `market_data`).
- Redis (`REDIS_*` env vars) — caching only, optional.
- RabbitMQ env vars present in `Settings` (`rabbitmq_host`, `_port`, `_user`, `_password`, `_vhost`) — **but no client code uses them**. Dead config.
- Mirrored `BYBIT_TESTNET` flag — drives `is_mainnet` value on inserted rows. Operator must keep this in sync with bybit-connector.

## Used by

Grep of `MARKET_DATA_URL` across `services/`:
- **technical-analysis** (`services/technical-analysis/.env`) → `http://market-data:8002`. Primary consumer (klines for indicators / GRU input).
- **portfolio-manager** (`services/portfolio-manager/.env`) → `http://market-data:8002`. Live prices for P&L / mark-to-market.
- **risk-metrics-service** (`services/risk-metrics-service/.env`) → `http://localhost:8002`. Klines for VaR / drawdown calc.
- **ml-prediction-service** (`services/ml-prediction-service/app/config.py`) → env `MARKET_DATA_URL`, default `http://localhost:8003` (stale default, but compose overrides).
- **api-gateway** + **trading-engine** + **frontend** + **ml-retraining** + **notification-service**: `MARKET_DATA_URL=http://market-data:8002` in compose.

Older `.env.example` and README files still show `localhost:8003` — stale (from when 8003 was the in-code default before the port collision fix). Live configs all use 8002.

## RabbitMQ

**No publishing.** `grep -rn "publish\|aio_pika\|exchange_declare\|queue_declare"` against `services/market-data-service/app/` returns zero matches. Only the env-var declarations in `config.py`. Consumers must poll `/api/v1/klines` / `/ticker`. CLAUDE.md hint of `market.data.{symbol}` topic is **not implemented**.

## Key files

1. `services/market-data-service/app/main.py` — FastAPI app, route table, lifespan (DB init → hypertables → fetcher → scheduler).
2. `services/market-data-service/app/scheduler.py` — APScheduler jobs (ticker / kline / hourly), `TRADING_PAIRS`, `KLINE_INTERVALS`.
3. `services/market-data-service/app/config.py` — Settings; `default_symbols` (14-pair string), `bybit_testnet` mirror flag, port 8002.
4. `services/market-data-service/app/models.py` — SQLAlchemy `Kline`, `Ticker`, `OrderBook` + dead `klines_1h` cont-agg SQL.
5. `services/market-data-service/app/database.py` — engine, `init_database` (retry/backoff), `create_hypertables` (per-stmt isolated transactions), `is_mainnet` migration.
6. `services/market-data-service/app/fetcher.py` — `BybitDataFetcher` HTTP client, pagination logic.
7. `services/market-data-service/app/repository.py` — `KlineRepository` (bulk_upsert), `TickerRepository`.
8. `services/market-data-service/app/cache.py` — Redis layer.
9. `services/market-data-service/app/handlers/{collection,query,scheduler,health}.py` — route business logic (Phase 2 modular split).
10. `services/market-data-service/app/circuit_breaker.py` — retry decorator for bybit-connector calls.

## Gotchas

- **Mixed testnet/mainnet history before 2026-04-25 mid-day** (CLAUDE.md). `is_mainnet` column added 2026-04-29 with default `true`, so pre-flip rows are marked mainnet but may actually be testnet. Operators must wipe old `klines`/`tickers` rows manually for clean backtest. `mainnet_only=True` query filter does NOT save you for pre-flip rows.
- **Two symbol lists out of sync**: `config.default_symbols` (14 pairs incl. ADA, no DOGE/XRP) vs `scheduler.TRADING_PAIRS` (7 pairs incl. DOGE/XRP). Scheduler is what actually fills Timescale, so DOGE/XRP candles still arrive every 5 min despite config saying "excluded".
- **Stale port 8003 in older docs** — `services/api-gateway/.env.example`, `services/portfolio-manager/README.md`, `services/risk-metrics-service/README_PERFORMANCE.md`, `services/technical-analysis/README.md`, ml-prediction config default. Live compose uses 8002. Don't trust the READMEs.
- **`klines_1h` continuous aggregate is dead code** — defined in `models.CREATE_HYPERTABLE_SQL` block but never run by `create_hypertables()`. Anyone expecting hourly-rollup view will get a missing-relation error.
- **Per-statement isolated transactions** in `create_hypertables` — failure mode where PostgreSQL aborts the whole transaction on first failure and silently skips the rest is the reason `is_mainnet` ALTER didn't apply on first deploy 2026-04-29. Don't refactor back into one transaction.
- **`bybit_connector_url` default points to port 8002** in code (collides with this service's own port). Compose env `BYBIT_CONNECTOR_URL=http://bybit-connector:8001` saves standalone runs; debugging local-only could mis-target.
- **Hourly job double-runs** within the same 5-min window when minute-0 ticker/kline jobs and hourly-full job collide. APScheduler `max_instances=1` per job prevents intra-job overlap but doesn't coordinate across jobs. Ticker collection at :00 happens twice (once via 5-min job, once via hourly).
- **`api/v1/` prefix** kept on this service's direct routes despite repo-wide REST docs saying "no v1 prefix". Gateway re-routes drop the prefix when proxying — direct curl from inside the docker network must use `/api/v1/...`, gateway-mediated curl uses `/api/market/...`.

## Contradictions vs CLAUDE.md

1. **Symbol list**. CLAUDE.md says "5 validated symbols (BTC, ETH, SOL, BNB, ADA)" and "BTC + ETH re-added 2026-05-03; market-data `default_symbols` did not [have BTC+ETH] until this date". Reality:
   - `config.py default_symbols` lists **14** pairs (BTC, ETH, BNB, SOL, ADA, AVAX, LINK, ARB, OP, SUI, APT, DOT, LTC, POL) — strict superset of the 5.
   - `scheduler.TRADING_PAIRS` lists **7** pairs including XRP and DOGE — which CLAUDE.md says are excluded by paper-trading data.
   - The scheduler is the actual data source. Either the CLAUDE.md "5 active" claim is stale, or the scheduler config drifted past policy.
2. **REST prefix**. CLAUDE.md: "gateway routes are `/api/<domain>/<resource>` (no `v1` prefix despite older docs)." This service's own surface still uses `/api/v1/...`. Both can coexist (gateway rewrites), but caller documentation should distinguish the two layers.
3. **`POST /api/v1/collect/ticker/{symbol}` cache-refresh hint**. CLAUDE.md: "hit `POST /api/v1/collect/ticker/{symbol}` on market-data-service (port 8002) to force-refresh." Path verified. Note: the route is `X-API-Key`-protected — operators need to pass the key, not bare curl.
4. **RabbitMQ `market.data.{symbol}` topic**. Task brief speculates a publish; service has env vars but no broker client code. Topic does not exist. Consumers poll HTTP.
5. **TimescaleDB-as-cache**. Confirmed. Redis is a thin TTL skin on two query routes; the persistent ground truth is Timescale.
