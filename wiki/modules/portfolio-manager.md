---
type: module
path: "services/portfolio-manager/"
status: active
language: python
port: 8003
purpose: "In-memory portfolio tracking, P&L computation, daily performance snapshots"
maintainer: ""
last_updated: 2026-05-05
linked_issues: []
depends_on: [trading-engine, market-data-service, postgres]
used_by: [api-gateway, frontend]
tags: [module, service, portfolio, pnl]
created: 2026-05-05
updated: 2026-07-29
---

# portfolio-manager

**Port:** `8003`
**Path:** `services/portfolio-manager/`
**Purpose:** In-memory portfolio tracking, realized/unrealized P&L, allocation + rebalance logic, optional daily performance snapshots to PostgreSQL.

## Overview

FastAPI service (lifespan-based, v2.2.0). State is RAM-only — `Portfolio` and `Transaction` objects live on a `PortfolioManager` singleton. Mark prices fetched from [[market-data-service]] over HTTP. Position state pulled on demand from [[trading-engine]] via `POST /api/v1/sync`. **No RabbitMQ.** Optional PostgreSQL persistence (`use_database=true`) records *only* daily aggregate snapshots in `portfolio.performance_history`. Default starting capital `$100` (paper sandbox).

## Endpoints

All application routes use `/api/v1/` (direct service surface). The frontend hits `/api/portfolio/*` on [[api-gateway]] which proxies here. See [[../decisions/ADR-007-no-v1-api-prefix]] — that ADR scopes "no v1" to the gateway boundary, not internal calls.

Portfolio:
- `GET /api/v1/portfolio?portfolio_id=default`
- `GET /api/v1/portfolios`
- `GET /api/v1/portfolio/balance` — cash, total, realized + unrealized + total P&L, return %.
- `GET /api/v1/portfolio/holdings`

Performance:
- `GET /api/v1/performance` — `include_daily`, `include_periods` flags need DB.
- `GET /api/v1/performance/assets`

Allocation:
- `GET /api/v1/allocation`
- `GET /api/v1/rebalance` — drift > `rebalance_threshold_pct` (default 5%).

Transactions (query-string params, not JSON):
- `POST /api/v1/transaction/buy?symbol&quantity&price`
- `POST /api/v1/transaction/sell?symbol&quantity&price`
- `GET /api/v1/transactions?limit&symbol`

Sync + admin:
- `POST /api/v1/sync` — pull positions from trading-engine.
- `POST /api/v1/admin/snapshot` — manual daily snapshot.
- `GET /api/v1/admin/scheduler/status`

Optimization (Modern Portfolio Theory):
- `POST /api/v1/portfolio/optimize`
- `GET /api/v1/portfolio/efficient-frontier`
- `POST /api/v1/portfolio/rebalance`

Total ~17 application routes (excluding `/health`, `/metrics`, `/`).

### Emergency-stop is not here

`POST /api/portfolio/emergency-stop` is defined on [[api-gateway]] (`app/main.py:1387`), guarded by `Depends(get_current_admin_user)`. It writes to `EMERGENCY_STOP_FILE` (default `/app/EMERGENCY_STOP`) — a host-bind-mounted file watched read-only by [[trading-engine]]. portfolio-manager has zero involvement. See [[../decisions/ADR-005-emergency-stop-file-flag]] and [[../flows/Emergency-Stop]].

## Position model / P&L

Domain: `Portfolio` → `Dict[str, Asset]`, all `Decimal`. Asset carries `average_entry_price`, `current_price`, `unrealized_pnl`, `current_allocation_pct`, optional `target_allocation_pct`, and — **new 2026-07-29** — a `side` field (`LONG`/`SHORT`, `models/asset.py:27`).

- **`GET /api/portfolio` and the snapshot scheduler now MIRROR the trading engine** via `sync_with_trading_engine()` (`handlers/portfolio.py:62`, `scheduler/performance_snapshot.py:258,311`) — the old `update_prices()` spot recompute is only a best-effort fallback when sync fails.
- **Unrealized P&L is side-aware** (`Asset.update_valuation`, `models/asset.py:49–71`): a SHORT gains as price falls (`unrealized_pnl = total_cost − current_value`, inverse of LONG). Previously long-only, which inverted the sign of every short.
- **Cash + realized P&L are pulled authoritatively from the engine** (`GET trading_engine_url/api/v1/performance` → `metrics.current_balance` / `realized_pnl`; `portfolio_manager.py:242–265`). **Equity = cash + unrealized** (`portfolio_manager.py:270`) — cash already reflects margin + realized.
- **Total P&L** = `realized + unrealized`. Return % vs `initial_capital`.
- Mark price source (fallback path only) = `GET market_data_url/api/v1/ticker/{symbol}` → `last_price`. Fetched per-symbol in a loop (no batch).

> **Fixed 2026-07-29:** the old `sync_with_trading_engine` reconstructed every position as a spot LONG via `add_asset()`, deducting full notional from cash and ignoring `side`. A $100 book with two leveraged shorts showed cash ≈ $15 and a **phantom −84% return** with inverted short P&L. Sync now copies the engine's numbers directly (`portfolio_manager.py:190–291`).

Concurrency: per-portfolio `asyncio.Lock` (`PortfolioManager.get_transaction_lock(pid)`) serializes the read-await-write window between cash check and price fetch — prevents concurrent BUY/SELL overdrawing cash.

## Internal deps

- [[trading-engine]] — outbound: `GET /api/v1/positions?status=all` **and `GET /api/v1/performance`** (for authoritative cash/realized P&L) from `sync_with_trading_engine()`. **Direction is portfolio-manager → trading-engine**, opposite of what a `trade.result` event flow would imply.
- [[market-data-service]] — outbound: `GET /api/v1/ticker/{symbol}`. N sequential calls per refresh.
- PostgreSQL (optional) — `asyncpg.Pool`, schema `portfolio`.

Compose env wiring:
```
TRADING_ENGINE_URL=http://trading-engine:8005
MARKET_DATA_URL=http://market-data-service:8002
```

## Used by

- [[api-gateway]] — proxies `/api/portfolio/*` (frontend-facing) → `/api/v1/portfolio/*` here. Routing in `app/services/service_proxy.py`.
- frontend — indirectly via gateway.
- [[risk-metrics-service]] — **not verified.** No `portfolio_manager_url` reference found via grep. Cross-service link is aspirational; if real it goes through the gateway or a direct DB read of `portfolio.performance_history`.
- [[bybit-connector]] — no relationship.
- [[notification-service]] — no relationship at the portfolio-manager boundary.

## RabbitMQ

**None.** No `aio_pika` / `pika` / `amqp` dependency. No publisher, no consumer. Sync is HTTP-pull. `concepts/Message-Queue-Topics.md` may list `trade.result` / `portfolio.update` for this service — those topics are not wired up in code.

## DB tables

PostgreSQL (NOT TimescaleDB), schema `portfolio`:

- **`portfolio.performance_history`** — daily snapshots. Migration `infrastructure/migrations/002_performance_history.sql`. Read/write in `app/services/performance_history.py`. Calls stored func `portfolio.get_period_stats($1, $2)` for week/month/year/all.
- `infrastructure/migrations/003_portfolios_orm_align.sql` — scaffold, **not referenced from runtime code** as of May 2026.

No `positions`, `balances`, `trades` tables consumed. Live position state is RAM-only — service restart wipes everything except daily snapshots.

## Key files

- `app/main.py` — FastAPI app, lifespan, prometheus middleware.
- `app/config.py` — `Settings` (port 8003, `initial_capital=100.0`, `rebalance_threshold_pct=5.0`).
- `app/services/portfolio_manager.py` — singleton, `sync_with_trading_engine()`, `update_prices()`, `execute_transaction()`, transaction locks.
- `app/services/performance_history.py` — asyncpg DAO over `portfolio.performance_history`.
- `app/services/performance_calculator.py` — Sharpe, drawdown.
- `app/scheduler/performance_snapshot.py` — daily snapshot + periodic price refresh.
- `app/models/portfolio.py` — `Portfolio`, `PortfolioSnapshot`, `RebalanceRecommendation`.
- `app/models/asset.py`, `app/models/transaction.py` — domain models.
- `app/handlers/portfolio.py`, `handlers/transactions.py` — HTTP layer.
- `app/handlers/health.py` — *recently modified* (git status `M`); adds `readiness_check()` and an `ImportError`-safe path for `shared.database.connection`. The new function is **not wired** into main.py as a `/ready` route — verify before depending on `/ready`.

## Gotchas

- Emergency-stop: route lives in api-gateway, not here. The `pathlib.Path.write_text` mocking trap from [[../concepts/Test-Setup-Gotchas]] applies to api-gateway tests, not portfolio-manager tests. See [[../decisions/ADR-005-emergency-stop-file-flag]].
- All position / cash / transaction state is RAM. Restart = clean slate (initial_capital recreated). Only daily snapshots survive.
- `_fetch_current_price()` returns `Decimal("0")` on HTTP failure — silently zeroes `current_value`. Brief market-data outage spikes unrealized_pnl negative.
- `update_prices()` is N sequential GETs.
- Transaction params are query string, not JSON body.
- Default `initial_capital=$100` — paper sandbox only.
- `app/main.py.bak` is a pre-refactor backup; ignore.

## Contradictions vs project CLAUDE.md

1. **Emergency-stop endpoint** is on api-gateway, not portfolio-manager.
2. **RabbitMQ "trade.result" / "portfolio.update"** topics — not implemented anywhere in this service. Sync is HTTP-pull.
3. **DB tables "positions, balances, trades, snapshots"** — only `portfolio.performance_history` (snapshots) is real. Rest is RAM.
4. Position ownership: trading-engine owns positions; portfolio-manager mirrors them on demand. The two stores can drift.

See raw report: `wiki/.raw/agent-reports/portfolio-manager.md`.

## Corrections 2026-07-29

Reflects the 2026-07-29 production audit (verified in source):

- **`sync_with_trading_engine` now faithfully mirrors the engine** (`portfolio_manager.py:190–291`): side-aware P&L via new `Asset.side` (`models/asset.py:27`) + sign-aware `update_valuation` (`models/asset.py:49–71`); pulls authoritative cash/realized/unrealized from the engine's `/api/v1/performance`; equity = cash + unrealized. Fixes the phantom −84% return and inverted short P&L from the old spot-LONG model that deducted full notional. See *Position model / P&L*.
- **`GET /api/portfolio` + the snapshot scheduler use sync, not `update_prices`** (`handlers/portfolio.py:62`, `scheduler/performance_snapshot.py:258,311`).
- **Optimization endpoints no longer mask 503/400 as 500** (`handlers/optimization.py:174–177`, `272–275`): `except HTTPException: raise` re-raises the intended status before the generic 500 handler — restores caller retry/backoff.

## Related

- [[../flows/Order-Lifecycle]]
- [[../flows/Emergency-Stop]]
- [[../concepts/Risk-Model]]
- [[../concepts/Auto-Trader]]
- [[../concepts/Test-Setup-Gotchas]]
- [[../decisions/ADR-005-emergency-stop-file-flag]]
- [[../decisions/ADR-007-no-v1-api-prefix]]
- Sibling services: [[market-data-service]], [[trading-engine]], [[bybit-connector]], [[api-gateway]], [[risk-metrics-service]], [[notification-service]]
