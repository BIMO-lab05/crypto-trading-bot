---
service: trading-engine
port: 8005
generated: 2026-05-05
scope: top-level orchestration only (296 Python files, full enum skipped)
---

# trading-engine — raw agent report

Repo path: `services/trading-engine/`
Stated purpose (CLAUDE.md): "Strategy + risk + order execution".
FastAPI title (`app/main.py:317`): "Trading Engine Service" — VERSION = `3.7.0`.
Image: `python:3.12-slim`, 2 uvicorn workers, runs as `appuser`.

## Endpoints

Two emission paths: routes defined directly in `main.py` (48 `@app.<verb>` decorators) and 9 routers `app.include_router(...)` mounted from `handlers/` (102 `@router.<verb>` decorators across handler modules). Total exposed surface ≈ 150 routes — large because the service absorbs strategy / risk-budget / execution-routing / attribution / backtesting endpoints rather than splitting them out.

Route families inline in `main.py`:
- `GET /health`, `GET /health/detailed`, `GET /status`, `GET /metrics` (Prometheus), `GET /` (banner with `endpoints` map).
- Signals: `GET /api/v1/signals/{symbol}`, `GET /api/v1/signals/enhanced/{symbol}`, `POST /api/v1/signals/{symbol}/analyze`.
- Positions: `GET /api/v1/positions`, `GET /api/v1/positions/{position_id}`, `POST /api/v1/positions/update-tp-levels`.
- Performance: `GET /api/v1/performance`.
- Trades: `GET /api/v1/trades/history`.
- Trading control: `POST /api/v1/trading/start`, `POST /api/v1/trading/stop`, `GET /api/v1/trading/status`. **No `/api/trading/auto/stop` route exists — see Contradictions.**
- Phase 1 metrics: `/api/v1/phase1/{metrics,health,latest}`.
- Correlation: `/api/v1/risk/correlation/*` (matrix, status, score, pair, alerts, check-position, update).
- SQZMOM: `/api/v1/strategies/sqzmom/*` (info, config, enable, disable, signals, signal/{symbol}, trade/{symbol}, symbols/{symbol}/config).
- Backtesting: `/api/v1/backtest/*`.
- Statistical arbitrage: `/api/v1/statistical-arbitrage/*` (initialize, pairs/add, pairs/calibrate, funding/add, triangular/setup, signals/generate, performance, status, reset).

Routers mounted (`main.py:403–432`):
- `grid_trading_router` (Phase 2.3)
- `orchestration_router` (Phase 9 — only mounted 2026-04-29; previously dead code; emergency-stop, risk/utilization, strategies/* live here)
- `kelly_router` (Phase 3.2)
- `risk_budget_router` (Phase 3.3)
- `execution_router` (Phase 4.1 smart routing)
- `twap_vwap_router` (Phase 4.2)
- `attribution_router` (Phase 5.1)
- `analytics_router` + `analytics_report_router` (Phase 5.2)
- `performance_dashboard_router` (Phase 5.3 — equity-curve, drawdown, returns-distribution, correlations, statistics; mounted 2026-05-01, also formerly dead).

Orchestration router exposes the **real** emergency-stop endpoint: `POST /emergency-stop` (handlers/orchestration.py:573) plus `/strategies`, `/strategy/register`, `/strategy/{id}/enable|disable`, `/allocation`, `/signals/active|conflicts|resolve|submit`, `/performance/by-strategy|comparison`, `/rebalance`, `/risk/utilization`, `/status`. Note it does **not** carry a `/api/v1/...` prefix in the file (router prefix likely set inside `orchestration.py` — not read).

## Lifespan composition

Refactor 2026-05-01 (ADR-002) split a fat 200-line `lifespan` into 4 phases living under `app/lifespan/`:

1. `init_data` (`lifespan/data.py`) — `db_manager.init_async_engine()`, portfolio repo `get_or_create("paper_trading", initial_balance=settings.paper_initial_balance)`, position load from DB, `paper_engine.sync_balance_with_positions()`. Errors during init are caught and logged; service continues without DB persistence (matches pre-refactor tolerance).
2. `init_ml` (`lifespan/ml.py`) — TA aggregator health probe (`ta_service_health` gauge), `get_attribution_analyzer(initial_capital=settings.paper_initial_balance)`, log SQZMOM config block.
3. `init_strategy` (`lifespan/strategy.py`) — `correlation_manager.initialize(redis_url=settings.redis_url)`, `get_kelly_sizer()`.
4. `init_risk` (`lifespan/risk.py`) — `get_risk_budget_manager()` + `calculate_risk_budget()`, `get_smart_router()`, `get_execution_scheduler().start()`.

Composition in `main.py:257`:

```python
async with init_data(), init_ml(), init_strategy(), init_risk():
    ... auto-trader gate ...
    yield
```

**Exit order verified**: `async with` is a stack — exit runs in reverse of enter. Order on shutdown:
1. `init_risk` finally → `execution_scheduler.stop(wait_for_completion=True)`.
2. `init_strategy` finally → `correlation_manager.close()`.
3. `init_ml` finally → `close_aggregator()`, `close_multi_timeframe_analyzer()`, `sqzmom_strategy.close()`.
4. `init_data` finally → `db_manager.close()`.

Auto-trader stop runs in the outer `try/finally` *inside* the four-phase `async with` block, so its `await auto_trader.stop()` fires **before** any phase exits.

## Strategies registered

`app/strategies/__init__.py` re-exports 9 strategy classes plus orchestration glue. Top-level names:

- Phase 9 (orchestration, 2025-12-11): `MeanReversionStrategy`, `TrendFollowingStrategyV2`, `BreakoutStrategy`, `ArbitrageStrategy`. Plus `SignalAggregator`, `StrategyCoordinator`, `StrategyBacktester`, `StrategyBase`.
- TA-based: `SQZMOMStrategy` (squeeze momentum, optimised for SOL/DOGE/BNB), `ResearchOptimizedStrategy` (RSI-6 + MACD + ADX + ATR stops, quarter-Kelly), `SupportResistanceStrategy`.
- Stat-arb (Phase 2.2): `PairsTradingStrategy`, `FundingRateArbitrageStrategy`, `TriangularArbitrageStrategy`.
- Grid (Phase 2.3): `GridTradingStrategy`, `GridTradingStrategyV2`.
- Momentum (Phase 2.4): `MomentumBreakoutStrategy`, `TrendFollowingStrategy` (the legacy v1, distinct from `TrendFollowingStrategyV2`).

`auto_trader.py` also imports `HybridStrategyRouter` (`app/strategies/hybrid_strategy_router.py`) — selected when `settings.strategy_mode == "hybrid"`. Default mode is `"standard"` (config.py:262).

## Risk gates

Hard caps are pydantic field defaults in `app/config.py`:

- `max_risk_per_trade = 0.02` → 2% of balance per trade (line 296). Stored as fraction not percent.
- `max_daily_loss_pct = 5.0` → 5% daily drawdown circuit-breaker (line 306).
- `max_position_hold_hours = 48` + `enable_max_hold_time = True` (line 370) → Jan 2026 fix `380a674`. Enforcement lives in `app/auto_trader.py` around line 1890–2057 (loop scans open positions every cycle and forces close past horizon).
- `max_total_exposure_pct = 80.0`, `max_position_size_pct = 5.0`.
- SHORT-specific tightenings: `short_stop_loss_pct = 1.5`, `short_min_confidence = 0.70`, `short_max_position_pct = 3.0`.
- Circuit breaker for SHORT: `circuit_breaker_enabled = True`, `circuit_breaker_max_consecutive_losses = 3`, `circuit_breaker_max_drawdown_pct = 10.0`, `circuit_breaker_min_win_rate_pct = 45.0` (auto-disable trigger after 30 SHORT trades).

Risk-budget recomputation on boot in `init_risk` (`risk_budget_manager.calculate_risk_budget()`); subsequent updates flow through `risk_budget_router` and `auto_trader` cycles.

## Auto-trader gate

Gate logic is **outside** the lifespan phases, in `main.py:266–300`, between phase enter and `yield`:

1. If `settings.auto_trading_enabled` is `False` → log warning, set `auto_trader_status` gauge to 0, leave `auto_trader = None`.
2. Else if `Path(settings.emergency_stop_file).is_file()` → log critical, set gauge 0, refuse to start. Uses `is_file()` (not `exists()`) to handle WSL bind-mount race where Docker mounts a directory at the path when host file is absent.
3. Else: `from app.auto_trader import get_auto_trader`, `await auto_trader.start()`, set gauge 1.

Inside the running auto-trader loop, `app/auto_trader.py:755` re-checks `self.emergency_stop_file.is_file()` every cycle and halts the loop when it appears mid-run. Operator pauses with `touch /app/EMERGENCY_STOP` (the file path is configurable via `emergency_stop_file`, default `/app/EMERGENCY_STOP`, RO bind-mount from repo root in compose). Manual stop endpoint: `POST /api/v1/trading/stop` (handlers/trading_control via `stop_trading`).

## Trading-mode flags

Code-level branching:

- `trading_mode: Literal["PAPER", "LIVE"]` (config.py:172) defaults to `"PAPER"`.
- LIVE-mode boot guard, `main.py:244–252`:
  ```python
  if settings.trading_mode == "LIVE":
      ack = os.environ.get("LIVE_TRADING_ACK", "")
      if ack != "I_UNDERSTAND_REAL_MONEY":
          raise RuntimeError(
              "Refusing to boot: TRADING_MODE=LIVE without "
              "LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY. ..."
          )
      logger.critical("LIVE trading mode acknowledged via LIVE_TRADING_ACK")
  ```
  Verified: the check runs before the four-phase `async with`. Boot aborts with `RuntimeError` if ack is missing or any other value. There is **no** `PAPER_TRADING_MODE` field in `Settings` — that env var is read in other services (compose-level), but trading-engine selects engines via `trading_mode` and then via `auto_trader.py` `from app.live_trading import get_live_engine` vs `from app.paper_trading import get_paper_engine`.
- `BYBIT_TESTNET` is a price-source flag enforced in `bybit-connector` / `market-data-service`, not here.

## Paper trading internals

`app/paper_trading.py` — `PaperTradingEngine` singleton (`get_paper_engine()`).

- Initial balance from `settings.paper_initial_balance` (default `100.0`). Commission `paper_commission_pct = 0.1%`.
- `sync_balance_with_positions()` runs at boot (in `init_data`) and deducts `entry_price * quantity + commission` for every open position the position-manager loaded from DB. This means a restart correctly preserves cash exposure — but also that the only persisted state is positions + portfolio rows, not a balance row.
- `execute_market_order` is a deterministic fill at the passed `current_price` with **zero slippage model**, **zero latency model**, **always FILLED**. The only failure mode is "Insufficient balance" (returns `OrderStatus.FAILED` + reason).
- BUY semantics: if any open SHORT exists for symbol → close it with `position_manager.close_position(...)` and add proceeds. Else open LONG with margin = `order_value / leverage` (per 2025-12-18 fix); deduct margin + commission.
- SELL semantics: mirror — if open LONG exists → close. Else open SHORT (auto-side-flipping was added 2025-12-03).
- Trade rows logged async via `asyncio.create_task(self.trade_repo.log_trade(...))` — fire-and-forget; failures only logged at WARN.
- `bybit_order_id` synthesized as `f"PAPER_{symbol}_{side}"` — collision-prone if multiple paper orders for same symbol+side persist with same id.

Slippage model is implemented elsewhere — `app/trading_enhancements/slippage_manager.py` (referenced from `auto_trader.py`) — but it is not invoked in `paper_trading.py`. The simulated fill assumes the caller already passes the realistic price.

## Internal deps

Service URLs in `app/config.py:24–46`:

- `technical_analysis_url` → `http://localhost:8004` — TA aggregator + signal aggregator client (`app.signal_aggregator.get_aggregator()`).
- `market_data_url` → `http://localhost:8002` — price source.
- `bybit_connector_url` → `http://bybit-connector:8001` — real order routing in LIVE mode.
- `portfolio_manager_url` → `http://localhost:8006` — position / balance reconciliation.
- `ml_prediction_url` → `http://localhost:8007` — used only when `enable_ml_predictions=True` (default False).
- `notification_service_url` → `http://localhost:8006` — **same port as portfolio_manager**, almost certainly a copy-paste bug (notification service is `:8006` per CLAUDE.md but portfolio-manager is `:8003`). See Contradictions.

`risk-metrics-service` (:8009) is **not** referenced by name in trading-engine config — risk metrics are kept in-process via `app/risk/*` modules.

## RabbitMQ

trading-engine **does not produce or consume** `analysis.signal.*` / `trade.execute` / `trade.result` topics. Grep across `app/` found only:

- `app/core/health.py:406` — optional `check_rabbitmq(rabbitmq_url)` connectivity probe via `aio_pika.connect_robust`. Imports `aio_pika` lazily; missing module just marks the check as "optional" without failing the service.

There is no publisher of `trade.execute`/`trade.result`, no consumer of `analysis.signal.*`, no `aio_pika.Channel.basic_publish`. The signal pipeline is **synchronous HTTP**: `auto_trader` calls `signal_aggregator` (which itself calls technical-analysis service via httpx), then directly invokes `paper_trading` / `live_trading`. This contradicts the "RabbitMQ event-driven" mental model the task brief implied — see Contradictions.

`pika==1.3.2` is in `requirements.txt` but unused at orchestration level (may be used inside specific stat-arb / execution modules — not read in this scope).

## Key files

Top 10 orchestration / wiring files (excluding the 290+ strategy / handler / service implementation files):

1. `services/trading-engine/app/main.py` — FastAPI app, lifespan composition, LIVE-ack guard, auto-trader gate, Prometheus metrics, ~150-route surface.
2. `services/trading-engine/app/config.py` — `Settings` (635 lines): risk caps, symbols, trading-mode flag, EMERGENCY_STOP path, leverage, MTF/ML/funding/vol-target feature flags.
3. `services/trading-engine/app/lifespan/__init__.py` — exports the 4 phase context managers.
4. `services/trading-engine/app/lifespan/data.py` — DB + portfolio + position load + paper-balance sync.
5. `services/trading-engine/app/lifespan/ml.py` — TA aggregator + attribution + SQZMOM banner.
6. `services/trading-engine/app/lifespan/strategy.py` — correlation manager + Kelly sizer.
7. `services/trading-engine/app/lifespan/risk.py` — risk budget + smart router + execution scheduler.
8. `services/trading-engine/app/paper_trading.py` — `PaperTradingEngine` (no slippage, deterministic fills).
9. `services/trading-engine/app/auto_trader.py` — main signal-poll → execute loop, EMERGENCY_STOP re-check, 48h max-hold sweep, hybrid/grid/research strategy switch.
10. `services/trading-engine/app/strategies/__init__.py` — 16+ strategy class re-exports across 4 phases.
11. `services/trading-engine/app/handlers/orchestration.py` — `POST /emergency-stop` lives here (mounted only since 2026-04-29).
12. `services/trading-engine/app/risk/__init__.py` — Kelly + correlation + sector + diversification + dynamic-budget-legacy + dynamic-budget-enhanced.
13. `services/trading-engine/Dockerfile` — multi-stage, 2 workers, healthcheck `curl /health`.
14. `services/trading-engine/requirements.txt` — fastapi 0.109, pandas 2.2, scipy 1.11, statsmodels 0.14, aio-pika absent, sklearn/tensorflow removed 2026-05-02.

## Gotchas

- **EMERGENCY_STOP file = read-only bind mount** from repo root. `is_file()` not `exists()` is mandatory because Docker on WSL silently creates a directory at the mount target when the host file is absent (CLAUDE.md "WSL bind-mount race").
- **Lifespan tear-down order is reverse-enter**, so `execution_scheduler.stop(wait_for_completion=True)` runs first and may block indefinitely if a TWAP/VWAP slice is mid-flight; downstream phases (correlation manager, aggregator, db) cannot close until scheduler returns.
- **autoflake will strip the F401 re-exports at top of `main.py`** (`db_manager`, `get_aggregator`, `get_portfolio_repository`, `get_paper_engine`) without the `# noqa: F401` markers. Tests monkeypatch `app.main.<symbol>` — removing the imports silently breaks dozens of tests (`feedback_main_imports_autoflake`, ADR-002 §6).
- **`Path.write_text`/`read_text`/`open` bypass `builtins.open`** (they go through `_io.open`). Tests for emergency-stop must `mock.patch("pathlib.Path.write_text")`, not `builtins.open`.
- **paper-engine `bybit_order_id`** is `f"PAPER_{symbol}_{side}"` — non-unique across orders. DB persistence relies on `position_id` PK, so this lands as a degraded-but-not-fatal collision.
- **performance_dashboard_router and orchestration_router were defined but unmounted** before 2026-04-29 / 2026-05-01 — every endpoint under those was dead. Pattern: handler module exists but missing `app.include_router(...)` line.
- **No PAPER_TRADING_MODE field** in trading-engine `Settings`. CLAUDE.md describes it as a flag — it is set at compose level and read by **other** services. Trading-engine internally branches on `trading_mode` only.
- **`notification_service_url` defaults to `:8006`** — same as portfolio_manager. Likely copy-paste; real notification-service is also :8006 in CLAUDE.md table, but portfolio-manager is :8003. Either CLAUDE.md or config.py is wrong; here config.py disagrees with itself.

## Contradictions vs CLAUDE.md

1. **`POST /api/trading/auto/stop`** — CLAUDE.md says "to stop fully: `POST /api/trading/auto/stop`". This route does **not exist**. The actual stop endpoint is `POST /api/v1/trading/stop` in `main.py:641`. The orchestration router exposes `POST /emergency-stop` (no `/auto/`), and the gateway-level path may rewrite, but the trading-engine surface has no `/auto/stop`.
2. **RabbitMQ event topics** — task brief says trading-engine consumes `analysis.signal.*` and publishes `trade.execute` / `trade.result`. No such code exists. Trading-engine talks to TA service over HTTP via `signal_aggregator`. Only `aio_pika.connect_robust` health probe is in the codebase, marked optional.
3. **Validated symbols** — CLAUDE.md says "BTC, ETH, SOL, BNB, ADA (5 active as of 2026-05-03)". `config.py:208–214` confirms exactly those five — consistent.
4. **`PAPER_TRADING_MODE` flag** — CLAUDE.md describes it; trading-engine doesn't have a field of that name. The four-flag deliberate-step model still works at the compose level, but inside this service only `trading_mode` and `LIVE_TRADING_ACK` enforce live trading.
5. **portfolio-manager port** — CLAUDE.md table lists portfolio-manager `:8003`. `config.py` has `portfolio_manager_url=http://localhost:8006`. One of the two is stale; the CLAUDE.md table is authoritative per the rest of the doc, so config.py is likely wrong.
6. **LIVE_TRADING_ACK enforcement** — confirmed and load-bearing. `RuntimeError` raised before any phase enters; cannot be bypassed without code change.
