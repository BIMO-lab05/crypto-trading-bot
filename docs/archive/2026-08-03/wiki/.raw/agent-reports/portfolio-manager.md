# portfolio-manager — raw report

Source: `services/portfolio-manager/app/` (main.py, config.py, handlers/, services/, models/, scheduler/, optimization/)
Compiled: 2026-05-05

## Endpoints

FastAPI app `app/main.py` (lifespan-based, `version="2.2.0"`). **Every application route carries `/api/v1/`** — the service does NOT honor ADR-007 internally. ADR-007 ("no /v1/ prefix") is an **api-gateway surface contract**: the gateway exposes `/api/portfolio/*` to the frontend and proxies them to portfolio-manager's `/api/v1/portfolio/*`. Direct calls (`http://portfolio-manager:8003/api/v1/...`) keep the v1 segment. This matches market-data-service.

Skipping `/health`, `/ready` (note: `/ready` not registered in main.py — only a `readiness_check()` defined in `handlers/health.py` is unwired; verify before relying on it), `/metrics`, `/`.

Portfolio (`Portfolio Endpoints`):
- `GET /api/v1/portfolio?portfolio_id=default` — full snapshot, refreshes prices first.
- `GET /api/v1/portfolios` — list all portfolios.
- `GET /api/v1/portfolio/balance?portfolio_id=default` — cash, total value, realized/unrealized/total P&L, return %.
- `GET /api/v1/portfolio/holdings?portfolio_id=default` — per-asset list.

Performance:
- `GET /api/v1/performance?portfolio_id=default&include_daily=false&include_periods=false` — metrics; `include_daily` / `include_periods` require DB.
- `GET /api/v1/performance/assets?portfolio_id=default` — per-asset performance + hold-duration days.

Allocation:
- `GET /api/v1/allocation?portfolio_id=default`
- `GET /api/v1/rebalance?portfolio_id=default` — drift-vs-target recommendations using `rebalance_threshold_pct` (default 5%).

Transactions:
- `POST /api/v1/transaction/buy?portfolio_id&symbol&quantity&price` — query-string params only, no JSON body.
- `POST /api/v1/transaction/sell?portfolio_id&symbol&quantity&price` — ditto.
- `GET /api/v1/transactions?portfolio_id=default&limit=&symbol=` — history.

Sync:
- `POST /api/v1/sync?portfolio_id=default` — pulls positions from trading-engine `GET /api/v1/positions?status=all` and reconciles into the in-memory portfolio.

Optimization (Modern Portfolio Theory; CVXPY/PyPortfolioOpt under the hood — see `app/optimization/`):
- `POST /api/v1/portfolio/optimize?portfolio_id=...&objective=&lookback_days=60&max_position_size=0.30&min_position_size=0.05&max_portfolio_volatility=`
- `GET /api/v1/portfolio/efficient-frontier?portfolio_id=...&num_points=50&lookback_days=60`
- `POST /api/v1/portfolio/rebalance?portfolio_id=...&target_weights=&execute=false`

Admin / scheduler:
- `POST /api/v1/admin/snapshot?portfolio_id=default` — manual performance snapshot (no-op if `use_database=false`).
- `GET /api/v1/admin/scheduler/status`

**Total application routes: ~17** (excluding /health, /ready, /metrics, /).

### Emergency-stop — NOT here

CLAUDE.md says "POST /api/portfolio/emergency-stop (admin-guarded)". That route is **defined in api-gateway**, not portfolio-manager (`services/api-gateway/app/main.py:1387`):

```python
@app.post("/api/portfolio/emergency-stop")
async def emergency_stop(current_user: User = Depends(get_current_admin_user)):
    stop_file = Path(os.getenv("EMERGENCY_STOP_FILE", "/app/EMERGENCY_STOP"))
    ...
    stop_file.write_text(f"Emergency stop activated at {activated_at_ms} by {current_user.username}\n")
```

Admin guard: `Depends(get_current_admin_user)` — confirmed. URL prefix is **bare `/api/portfolio/`** (no `v1`), per ADR-007, because it is on the gateway. The path namespace just *resembles* a portfolio-manager route; the file write happens in the api-gateway container against a bind-mounted host file shared with trading-engine. portfolio-manager itself has zero involvement in the emergency-stop flow.

## Position model / P&L logic

Domain models (`app/models/`):

- `Portfolio` (`portfolio.py`) — `portfolio_id`, `initial_capital`, `cash_balance`, `total_value`, `assets: Dict[str, Asset]`, `total_pnl`, `realized_pnl`, `unrealized_pnl`, `total_return_pct`, `allocation_strategy`. All money values are `Decimal`.
- `Asset` (`asset.py`) — symbol, quantity, `average_entry_price`, `current_price`, `total_cost`, `current_value`, `unrealized_pnl`, `unrealized_pnl_pct`, `current_allocation_pct`, optional `target_allocation_pct`.
- `Transaction` (`transaction.py`) — portfolio_id, symbol, action ("BUY"/"SELL"), quantity, price, total_amount, optional `realized_pnl` and `realized_pnl_pct` (only set on SELL).
- `PortfolioSnapshot`, `RebalanceRecommendation`, `AssetPerformance`.

P&L split:
- **Unrealized P&L** = sum over open assets of `(current_price - average_entry_price) * quantity`. Computed in `Portfolio.update_asset_prices(prices)` which is called from every read-path (`get_portfolio`, `get_balance`, `get_holdings`).
- **Realized P&L** = accumulated by `Portfolio.remove_asset(symbol, quantity, price)` — returns the realized P&L delta from the SELL leg, mutates `self.realized_pnl += delta` and adds proceeds to `cash_balance`. Records a `Transaction` with `realized_pnl` populated.
- **Total P&L** = `realized + unrealized`. `total_return_pct = (total_value - initial_capital) / initial_capital * 100`.

Mark price source: HTTP `GET {market_data_url}/api/v1/ticker/{symbol}` → `data["last_price"]` (Decimal). Fetched per-symbol in a loop in `update_prices()` — N HTTP calls per refresh, no batching. Falls back to `Decimal("0")` on failure (silently — could zero out a holding's value temporarily).

State is **all in-memory**. `PortfolioManager.portfolios: Dict[str, Portfolio]` and `transaction_history: Dict[str, List[Transaction]]` live on the singleton. There is **no persistence of positions or transactions** — only daily *performance snapshots* go to PostgreSQL when `use_database=true`. Restart wipes positions + cash balance; default portfolio recreated with `initial_capital=$100`.

Concurrency: per-portfolio `asyncio.Lock` (`PortfolioManager.get_transaction_lock(portfolio_id)`) added to serialize the read-await-write window between cash-balance check and price fetch — prevents concurrent BUY/SELL on the same portfolio from overdrawing cash. Caller-side: handlers (e.g. `transactions.py`) must wrap the await sequence in `async with manager.get_transaction_lock(pid):`.

## Internal deps

Outbound HTTP only (no message bus):

- **trading-engine** (`settings.trading_engine_url`, default `http://localhost:8005`, compose: `http://trading-engine:8005`) — `GET /api/v1/positions?status=all` from `sync_with_trading_engine()`. Reads positions, does NOT push back. Direction: **portfolio-manager pulls from trading-engine**, opposite to what CLAUDE.md hints with "trade.result" topics.
- **market-data-service** (`settings.market_data_url`, default `http://localhost:8002`) — `GET /api/v1/ticker/{symbol}` for mark prices.

Compose env (`docker-compose.unified.yml:437`+):
```
TRADING_ENGINE_URL=http://trading-engine:8005
MARKET_DATA_URL=http://market-data-service:8002
```
The compose comment notes "Without these two, portfolio-manager falls back to localhost:8005/8002" — inside Docker that = unreachable, so the env wiring is load-bearing.

Health checks (`handlers/health.py::health_check`) probe `trading_engine_url/health` and `market_data_url/health` plus optional database via `shared.database.connection.db_manager` (only loaded when `use_database=true`).

## Used by

- **api-gateway** (`services/api-gateway/app/main.py`) — proxies frontend requests:
  - `GET /api/portfolio` → `GET /api/v1/portfolio`
  - `GET /api/portfolio/balance` → `GET /api/v1/portfolio/balance`
  - `GET /api/portfolio/holdings` → `GET /api/v1/portfolio/holdings`
  - `GET /api/portfolio/performance` → forwarded to performance route
  - `GET /api/portfolio/trades` → transaction history
  - `POST /api/portfolio/buy`, `POST /api/portfolio/sell` → transaction routes
  - `POST /api/portfolio/emergency-stop` — local to gateway, not forwarded.
  - Routing config: `services/api-gateway/app/services/service_proxy.py:30` (`"portfolio-manager": settings.portfolio_manager_url`).
- **trading-engine** does NOT call portfolio-manager (one-way: portfolio-manager pulls from it).
- **risk-metrics-service** — no inbound code path found from portfolio-manager via grep (`portfolio_manager_url` only appears under api-gateway). CLAUDE.md guess "risk-metrics may consume P&L" is unsupported; if integration exists it's via direct DB read of the `portfolio.performance_history` table or via gateway proxy, not service-to-service.
- **frontend** — directly via `/api/portfolio/*` gateway routes.
- **bybit-connector** — no relationship.

## RabbitMQ

**None.** No `aio_pika` / `pika` / `amqp` import anywhere in `services/portfolio-manager/app/`. No `rabbitmq` config. No publisher, no consumer. CLAUDE.md task hint about "consumes `trade.result` to update positions / publishes `portfolio.update`" — **not implemented**. Sync is a manual HTTP pull triggered by `POST /api/v1/sync`, plus 30-second background price refresh in `app/scheduler/performance_snapshot.py`. Cross-reference `concepts/Message-Queue-Topics.md` if it claims otherwise — mismatch with code.

## DB tables

PostgreSQL (NOT TimescaleDB), schema `portfolio`. Only one table referenced from code:

- `portfolio.performance_history` — daily snapshots. Defined in `infrastructure/migrations/002_performance_history.sql` (`CREATE TABLE IF NOT EXISTS portfolio.performance_history`). Read/write in `app/services/performance_history.py:106` (INSERT), `:225` (`get_daily_performance`), `:377`, `:451`. Also calls a stored func `portfolio.get_period_stats($1, $2)` for week/month/year/all aggregations.
- `infrastructure/migrations/003_portfolios_orm_align.sql` exists but is not referenced by runtime code — likely an ORM-alignment scaffold for a future `portfolios` / `assets` / `transactions` persistence layer that hasn't been wired up.

There is **no `positions`, `balances`, `trades`, `holdings` table** consumed by this service. Live position state is RAM-only; transaction history is RAM-only; balances are RAM-only. The DB persists *aggregate daily performance* only, and that is gated by `settings.use_database` (default `false` in code; check compose env to see actual runtime state).

`asyncpg.Pool` created in `lifespan()` (`app/main.py:163`); `min_size=2`, `max_size=10`, `command_timeout=60`. If pool creation fails the service continues without DB and logs warning.

## Key files

1. `services/portfolio-manager/app/main.py` — FastAPI app, lifespan, prometheus metrics middleware, all route registrations.
2. `services/portfolio-manager/app/config.py` — `Settings` (`service_port=8003`, `trading_engine_url`, `market_data_url`, `initial_capital=100.0`, `rebalance_threshold_pct=5.0`, `risk_free_rate=0.02`, `use_database=false`).
3. `services/portfolio-manager/app/services/portfolio_manager.py` — `PortfolioManager` core: in-memory portfolio dict, transaction locks, `sync_with_trading_engine()`, `_fetch_current_price()`, `update_prices()`, `execute_transaction()`, `_record_transaction()`, `check_rebalancing_needed()`, `get_snapshot()`, `get_asset_performance()`.
4. `services/portfolio-manager/app/services/performance_history.py` — asyncpg DAO over `portfolio.performance_history`.
5. `services/portfolio-manager/app/services/performance_calculator.py` — Sharpe, drawdown, etc.
6. `services/portfolio-manager/app/scheduler/performance_snapshot.py` — daily snapshot scheduler + periodic price update loop (runs always, even without DB).
7. `services/portfolio-manager/app/models/portfolio.py` — `Portfolio`, `PortfolioSnapshot`, `RebalanceRecommendation`.
8. `services/portfolio-manager/app/handlers/portfolio.py` — get_portfolio / list / balance / holdings / sync_with_trading_engine handlers.
9. `services/portfolio-manager/app/handlers/transactions.py` — buy/sell endpoint logic (uses transaction lock).
10. `services/portfolio-manager/app/handlers/health.py` — recently modified per `git status M`. Adds `readiness_check()` (defined but not wired into main.py as `/ready`) and an `ImportError`-safe path for `shared.database.connection`. Worth verifying that `/ready` actually serves before relying on it.

## Gotchas

- **Emergency-stop has nothing to do with portfolio-manager** despite the route name. Patching `pathlib.Path.write_text` for that test belongs in api-gateway test suite, not here. See `[[../decisions/ADR-005-emergency-stop-file-flag]]` and `[[../concepts/Test-Setup-Gotchas]]` for the `mock.patch("builtins.open")` foot-gun (Path.write_text uses `_io.open`, bypassing `builtins.open`).
- All state is **RAM**. Restart wipes positions, balances, transaction history. Only `portfolio.performance_history` survives, and only when `use_database=true`. This is materially different from a "production portfolio system" expectation.
- `_fetch_current_price()` returns `Decimal("0")` on HTTP failure — feeds straight into `update_asset_prices({symbol: Decimal('0')})` which would zero out `current_value`, spike `unrealized_pnl` negative. No guard. Brief market-data outages will produce wild P&L numbers.
- `update_prices()` issues N sequential GETs (one per symbol) instead of a batch — slow on a wide portfolio.
- `/ready` route shape is suspect: `readiness_check()` exists in `handlers/health.py` but `main.py` only registers `@app.get("/health")`. If a `/ready` endpoint is needed by k8s / compose healthcheck it may be implicitly served by `/health` only.
- Transaction endpoints take parameters as **query string** (`Query(...)`), not JSON body — easy to mis-document in client code.
- `initial_capital` default is `$100` — laughably small; matches paper-trading sandbox, not anything else.
- `app/main.py.bak` still in tree — pre-refactor backup, not the live file. Don't read for ground truth.

## Contradictions vs CLAUDE.md

1. **Emergency-stop route ownership.** CLAUDE.md lists `POST /api/portfolio/emergency-stop` in the "portfolio" section and notes the `Path.write_text` testing gotcha as if portfolio-manager owned it. Both belong to **api-gateway**. portfolio-manager has no concept of EMERGENCY_STOP file.
2. **RabbitMQ topology.** Task spec asked whether portfolio-manager consumes `trade.result` and publishes `portfolio.update`. **Neither.** No AMQP code at all. Sync is HTTP pull from trading-engine via `POST /api/v1/sync`. If `concepts/Message-Queue-Topics.md` lists those topics for this service, they are aspirational, not implemented.
3. **DB tables.** CLAUDE.md task description listed "positions, balances, trades, snapshots". Only `portfolio.performance_history` (snapshots) is real. Positions / balances / trades live in RAM.
4. **ADR-007 (no /v1/ prefix).** Only enforced at the api-gateway boundary. portfolio-manager itself uses `/api/v1/` exclusively. This is consistent with market-data-service and is the convention for direct service-to-service calls — but a reader of ADR-007 alone would expect `/api/portfolio/*` directly on port 8003, which would 404.
5. **Used-by: risk-metrics.** No code reference found. CLAUDE.md hint "risk-metrics may consume P&L" is unsupported by grep — leave noted as "unverified" rather than asserting the link.
6. **Direction of trading-engine integration.** CLAUDE.md "Positions, balances, P&L" implies portfolio-manager owns position state. In reality trading-engine owns positions and portfolio-manager pulls a copy on demand via `/api/v1/sync`. The two stores can drift; there is no two-way reconciliation.
