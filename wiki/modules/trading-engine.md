---
type: module
path: "services/trading-engine/"
status: active
language: python
port: 8005
purpose: "Strategy + risk + order execution"
maintainer: ""
last_updated: 2026-05-05
linked_issues: []
depends_on:
  - bybit-connector
  - market-data-service
  - technical-analysis
  - portfolio-manager
  - risk-metrics-service
used_by:
  - api-gateway
tags: [module, service, trading, risk, orchestration]
created: 2026-05-05
updated: 2026-07-29
---

# trading-engine

**Port:** `8005`
**Path:** `services/trading-engine/`
**Purpose:** Strategy + risk + order execution
**Image:** `python:3.12-slim`, FastAPI 0.109, 2 uvicorn workers, runs as non-root `appuser`.
**Scale:** 296 Python files — largest service in the repo. This page covers orchestration only; strategy implementations and handlers live in their own files.

The trading-engine is the decision/execution centre. It pulls aggregated signals from [[technical-analysis]], applies risk gates, sizes positions (Kelly + correlation + risk-budget), and dispatches orders either to the [[../flows/Order-Lifecycle|paper engine]] (default) or [[bybit-connector]] in LIVE mode. Boot is gated by [[../decisions/ADR-004-paper-trading-default]] and [[../decisions/ADR-005-emergency-stop-file-flag]]; the four-phase startup is [[../decisions/ADR-002-trading-engine-lifespan-refactor]].

## Overview

Owns:
- The signal-poll loop ([[../flows/Signal-Pipeline]]) via `auto_trader.py`.
- The simulated order book in `paper_trading.py` ([[../decisions/ADR-006-mainnet-prices-paper-orders]]).
- All risk gates: per-trade cap (10 % paper default / hard 2 % floor in LIVE, **clamps** rather than rejects — fixed 2026-07-28), 5 % daily-loss (auto-rolls per UTC day), 48 h max-hold, SHORT circuit breaker. See [[../concepts/Risk-Model]].
- ~150 HTTP endpoints across 9 mounted routers + ~50 inline routes — strategy / risk-budget / execution-routing / attribution / backtesting all funnel through this one service.

Does **not** own:
- Real-money order placement (delegated to [[bybit-connector]]).
- Risk dashboards (delegated to [[risk-metrics-service]]).
- Live price feed (consumes from [[market-data-service]] over HTTP).
- RabbitMQ event publication — none. Communication is synchronous HTTP.

## Endpoints

Inline in `app/main.py` (48 `@app.<verb>` decorators):

- Health: `GET /health`, `GET /health/detailed`, `GET /status`, `GET /metrics`.
- Signals: `GET /api/v1/signals/{symbol}`, `GET /api/v1/signals/enhanced/{symbol}`, `POST /api/v1/signals/{symbol}/analyze`.
- Positions: `GET /api/v1/positions`, `GET /api/v1/positions/{position_id}`, `POST /api/v1/positions/update-tp-levels`.
- Performance: `GET /api/v1/performance`, `GET /api/v1/trades/history`.
- Trading control: `POST /api/v1/trading/start`, `POST /api/v1/trading/stop`, `GET /api/v1/trading/status`. (See contradictions — CLAUDE.md mentions `/api/trading/auto/stop` which does not exist here.)
- Phase 1 metrics: `/api/v1/phase1/{metrics,health,latest}`.
- Correlation: `/api/v1/risk/correlation/*`.
- SQZMOM: `/api/v1/strategies/sqzmom/*` (info, config, enable, disable, signals, signal/{symbol}, trade/{symbol}).
- Backtesting: `/api/v1/backtest/*`.
- Statistical arbitrage: `/api/v1/statistical-arbitrage/*`.

Mounted routers (`app.include_router`, `main.py:403–432`):

| Router | Phase | Notes |
|---|---|---|
| `grid_trading_router` | 2.3 | Grid signals + management |
| `orchestration_router` | 9 | **Mounted 2026-04-29** — was dead. Carries `POST /emergency-stop`, strategy register/enable/disable, allocation, signal conflicts, rebalance, risk/utilization. |
| `kelly_router` | 3.2 | Position sizing |
| `risk_budget_router` | 3.3 | Dynamic risk budget |
| `execution_router` | 4.1 | Smart order routing |
| `twap_vwap_router` | 4.2 | TWAP/VWAP slicing |
| `attribution_router` | 5.1 | P&L attribution |
| `analytics_router` + `analytics_report_router` | 5.2 | |
| `performance_dashboard_router` | 5.3 | **Mounted 2026-05-01** — also formerly dead. Feeds the [[frontend]] performance page. |

The "endpoints map" baked into `GET /` is verbose but useful for discovery.

## Lifespan composition (ADR-002)

`main.py:257`:

```python
async with init_data(), init_ml(), init_strategy(), init_risk():
    ...auto-trader gate...
    yield
```

Four phases live under `app/lifespan/`:

1. **`init_data`** — DB engine + portfolio repo `get_or_create("paper_trading")` + position load + `paper_engine.sync_balance_with_positions()`.
2. **`init_ml`** — TA aggregator health probe (`ta_service_health` gauge), attribution analyzer init, SQZMOM banner.
3. **`init_strategy`** — correlation manager (Phase 3.1) + Kelly sizer (Phase 3.2).
4. **`init_risk`** — dynamic risk budget (Phase 3.3) + smart router (Phase 4.1) + execution scheduler (Phase 4.2).

`async with` is a context-manager stack: on shutdown, exits run in **reverse** order — `init_risk` finally first (stops execution scheduler with `wait_for_completion=True`), then `init_strategy` (correlation manager close), then `init_ml` (aggregator + multi-timeframe + sqzmom close), then `init_data` (db_manager.close). Verified in source.

The four phases are intentionally fail-open: each `try/except` logs and continues so a flaky DB or TA service does not abort startup. See [[../decisions/ADR-002-trading-engine-lifespan-refactor]].

## Auto-trader gate

Lives **outside** the four phases (`main.py:266–300`), inside the `async with` block before `yield`. See [[../concepts/Auto-Trader]] and [[../flows/Emergency-Stop]].

Two off-switches in order:

1. `settings.auto_trading_enabled = False` → no auto-start. Manual `/start` endpoint still works.
2. `Path(settings.emergency_stop_file).is_file()` → refuse. Path is `/app/safety/EMERGENCY_STOP` (RO bind-mount of host `./safety/`). `is_file()` is required because of the WSL bind-mount race ([[../concepts/Test-Setup-Gotchas]]). Dir-to-dir mount (post-2026-05-19) prevents the auto-create-dir failure mode that the older file-to-file bind suffered.

If both pass, `await auto_trader.start()` and the loop polls signals every `check_frequency_seconds` (default 30 s). The loop **re-checks the file every cycle** (`auto_trader.py:886`), so `touch safety/EMERGENCY_STOP` mid-run halts execution within one tick.

## Trading-mode flags

Code-level enforcement, `main.py:244–252`:

```python
if settings.trading_mode == "LIVE":
    ack = os.environ.get("LIVE_TRADING_ACK", "")
    if ack != "I_UNDERSTAND_REAL_MONEY":
        raise RuntimeError("Refusing to boot: TRADING_MODE=LIVE without LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY...")
```

Verified: this guard runs before any phase enters; missing/wrong ack aborts the process. There is **no** `PAPER_TRADING_MODE` field on the `Settings` class — that variable is read at the compose level by other services. Inside trading-engine the only effective flags are `trading_mode` (`PAPER`/`LIVE`) and `LIVE_TRADING_ACK`. See [[../concepts/Trading-Mode-Flags]] and [[../decisions/ADR-004-paper-trading-default]].

## Strategies registered

`app/strategies/__init__.py` exports across four phases. Top-level names (no implementation read):

- **Phase 9 orchestration:** `MeanReversionStrategy`, `TrendFollowingStrategyV2`, `BreakoutStrategy`, `ArbitrageStrategy`, plus `SignalAggregator`, `StrategyCoordinator`, `StrategyBacktester`.
- **TA-based:** `SQZMOMStrategy` (SOL/DOGE/BNB-tuned), `ResearchOptimizedStrategy` (RSI-6 + ATR stops + quarter-Kelly), `SupportResistanceStrategy`.
- **Stat-arb (Phase 2.2):** `PairsTradingStrategy`, `FundingRateArbitrageStrategy`, `TriangularArbitrageStrategy`.
- **Grid (Phase 2.3):** `GridTradingStrategy`, `GridTradingStrategyV2`.
- **Momentum (Phase 2.4):** `MomentumBreakoutStrategy`, legacy `TrendFollowingStrategy`.
- Selected at runtime by `HybridStrategyRouter` (`app/strategies/hybrid_strategy_router.py`) when `strategy_mode = "hybrid"`. Default is `"standard"`.

## Risk gates ([[../concepts/Risk-Model]])

| Cap | Default | Source |
|---|---|---|
| Per-trade notional | **10 % paper / 2 % LIVE** | `config.py:321` `max_risk_per_trade=0.10` (bumped from 0.02 on 2026-05-06). LIVE clamps to 2 % (`auto_trader.py:1996`). Cap now **CLAMPS** position size instead of rejecting (`auto_trader.py:2003–2016`, `3782–3790`) — the old reject-and-skip starved the research/hybrid path (25–30 % allocations always exceeded the cap → 100 % rejects). |
| Daily loss | 5 % | `config.py:364` `max_daily_loss_pct=5.0`; **auto-rolls on UTC date change** (`risk_manager.py:32–65`) — was lifetime (`reset_daily_pnl` had no caller). |
| Total exposure | 80 % | `config.py:309` |
| Max position size | 5 % | `config.py:290` |
| Max hold time | 48 h | `config.py:449` `max_position_hold_hours=48`; force-close now **routes through `_close_position`** (`auto_trader.py:2410–2457`) — paper: engine reduce-only, LIVE: `live_engine.close_position`. Was a dead path that raised `TypeError` on every invocation and in LIVE would have opened an opposite position. |
| SHORT SL | 1.5 % | tighter than LONG (2 %) |
| SHORT min confidence | 70 % | higher than LONG (65 %) |
| SHORT max position | 3 % | smaller than LONG (5 %) |
| SHORT circuit-breaker | 3 consecutive losses, 10 % drawdown, < 45 % win rate | auto-disable after 30 SHORT trades |

Risk-budget recomputation happens in `init_risk` and on each auto-trader cycle through `risk_budget_manager.calculate_risk_budget()`.

## Paper trading internals (ADR-006)

`app/paper_trading.py` — singleton `PaperTradingEngine`:

- Initial balance from `paper_initial_balance` (default $100). Commission 0.1 %.
- Fills are deterministic at `current_price` — **no slippage model, no latency, no partial fill, always `OrderStatus.FILLED`**. The slippage manager (`app/trading_enhancements/slippage_manager.py`) is wired into `auto_trader` upstream but **not** invoked by `paper_trading.py` itself.
- **Accounting rewritten 2026-07-28** (`paper_trading.py:129–383`, `execute_market_order`). Behaviour now:
  - **Closes credit `margin_returned + realized_pnl − commission` on BOTH sides, any leverage** (`paper_trading.py:226–234`). Previously SHORT closes credited close-notional (a *winning* short REDUCED the balance — sign inverted) and leveraged LONG closes credited full notional while opens deducted margin only.
  - **`reduce_only` is honored** (`paper_trading.py:190–197`, `278–285`): a reduce-only order with no matching open position is **REJECTED**, not flipped into a full-size counter-position. This was turning every stop-loss / trailing exit into a stop + random counter-trade.
  - **`position_id` targets a specific position** (`paper_trading.py:186`) — no more `open_positions[0]` guesswork.
  - **Partial closes** (`paper_trading.py:236–250`): an order smaller than remaining qty reduces the position and credits proportional margin + P&L (`reduce_position`).
  - **Scale-in / DCA** (`paper_trading.py:287–332`): a same-side order with an explicit `position_id` averages into the SAME position (`scale_in`) instead of opening a duplicate.
- BUY: closes an open SHORT for the symbol (close path returns — no auto-flip to LONG in the same call); otherwise opens LONG with margin = `order_value / leverage`.
- SELL: mirror — closes an open LONG or opens SHORT.
- Trade rows logged async via `asyncio.create_task(self.trade_repo.log_trade(...))` — fire-and-forget, only WARN on failure.
- `bybit_order_id` synthesised as `f"PAPER_{symbol}_{side}"` — non-unique across orders.
- `sync_balance_with_positions()` runs at boot (called from `init_data`) to deduct entry cost of every position the position-manager loaded from DB. Persistence model: positions + portfolio rows are durable; cash balance is reconstructed on every boot.

## Internal deps

| Service | Used for | URL field |
|---|---|---|
| [[bybit-connector]] | LIVE order routing only | `bybit_connector_url` (`http://bybit-connector:8001`) |
| [[market-data-service]] | live price source | `market_data_url` (`http://localhost:8002`) |
| [[technical-analysis]] | aggregated signals (synchronous HTTP) | `technical_analysis_url` (`http://localhost:8004`) |
| [[portfolio-manager]] | position / balance reconciliation | `portfolio_manager_url` (`http://localhost:8006` — likely stale, see contradictions) |
| [[ml-prediction-service]] | optional ML predictions when `enable_ml_predictions=True` (default off) | `ml_prediction_url` (`http://localhost:8007`) |
| [[notification-service]] | trade alerts | `notification_service_url` (`http://localhost:8006`) |
| [[risk-metrics-service]] | not directly referenced — risk lives in-process under `app/risk/*` | — |

## RabbitMQ

trading-engine **does not produce or consume** message-broker topics. Grep confirmed:

- No publisher of `trade.execute` / `trade.result`.
- No consumer of `analysis.signal.*`.
- Only `aio_pika.connect_robust` health probe in `app/core/health.py:406` — marked optional, fails open.

The signal pipeline is fully synchronous HTTP: `auto_trader` → `signal_aggregator` (httpx → technical-analysis) → `paper_trading` / `live_trading`. `pika==1.3.2` is in `requirements.txt` but unused in orchestration code (may be used inside specific stat-arb modules — out of scope).

This contradicts the "event-driven" mental model in the task brief — see contradictions.

## Validated symbols ([[../concepts/Validated-Symbols]])

5 active in `config.py:208–214`: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `ADAUSDT`. Allocation defaults SOL 30 %, BTC 25 %, BNB 20 %, ADA 15 %, ETH 10 % (backtest-optimised 2026-01-19). XRP / DOGE excluded.

## Key files

1. `services/trading-engine/app/main.py` — FastAPI app, lifespan composition, LIVE-ack guard, auto-trader gate, ~150 routes.
2. `services/trading-engine/app/config.py` — 635-line `Settings` (risk caps, symbols, EMERGENCY_STOP path, leverage, feature flags).
3. `services/trading-engine/app/lifespan/__init__.py` — exports the four phase context managers.
4. `services/trading-engine/app/lifespan/data.py`, `ml.py`, `strategy.py`, `risk.py`.
5. `services/trading-engine/app/paper_trading.py` — deterministic-fill simulator.
6. `services/trading-engine/app/auto_trader.py` — main signal-poll loop, EMERGENCY_STOP re-check, 48 h max-hold sweep.
7. `services/trading-engine/app/strategies/__init__.py` — strategy registry.
8. `services/trading-engine/app/handlers/orchestration.py` — `POST /emergency-stop`, mounted only since 2026-04-29.
9. `services/trading-engine/app/risk/__init__.py` — Kelly + correlation + sector + diversification + dynamic-budget.
10. `services/trading-engine/Dockerfile` — multi-stage, 2 workers, healthcheck `curl /health`.
11. `services/trading-engine/requirements.txt` — fastapi 0.109, pandas 2.2, scipy 1.11, statsmodels 0.14; sklearn/tensorflow removed 2026-05-02.

## Gotchas ([[../concepts/Test-Setup-Gotchas]])

- **EMERGENCY_STOP file is RO bind-mount** from repo root. Always use `Path.is_file()`, not `exists()` — Docker on WSL silently creates a directory at the mount target when the host file is absent.
- **Lifespan tear-down is reverse-enter:** `execution_scheduler.stop(wait_for_completion=True)` runs first and can block downstream phase exits indefinitely if a TWAP/VWAP slice is mid-flight.
- **autoflake will strip the F401 re-exports at top of `main.py`** (`db_manager`, `get_aggregator`, `get_portfolio_repository`, `get_paper_engine`) without the `# noqa: F401` markers. Tests monkeypatch `app.main.<symbol>` — removing the imports silently breaks dozens of tests. See [[../decisions/ADR-002-trading-engine-lifespan-refactor]] §6.
- **`Path.write_text` / `read_text` / `open` bypass `builtins.open`.** Tests for emergency-stop must `mock.patch("pathlib.Path.write_text")`, not `builtins.open`.
- **paper-engine `bybit_order_id`** is non-unique (`PAPER_{symbol}_{side}`) — relies on `position_id` PK to disambiguate.
- **Two routers were dead until recently:** `orchestration_router` (mounted 2026-04-29) and `performance_dashboard_router` (mounted 2026-05-01). Pattern: handler module exists but missing `app.include_router(...)` in `main.py`.

## Contradictions vs CLAUDE.md

1. **`POST /api/trading/auto/stop`** in CLAUDE.md does not exist in this service. Real route: `POST /api/v1/trading/stop` (`main.py:641`). Closest match in orchestration router: `POST /emergency-stop`.
2. **RabbitMQ event topics** (`analysis.signal.*`, `trade.execute`, `trade.result`) — no producer or consumer. Pipeline is synchronous HTTP. CLAUDE.md / task brief overstates message-broker usage.
3. **`PAPER_TRADING_MODE` field** is not on the `Settings` class. The four-flag step-to-LIVE model still works at compose level but inside this service only `trading_mode` and `LIVE_TRADING_ACK` enforce live trading.
4. **`portfolio_manager_url` defaults to `:8006`**, but CLAUDE.md table puts portfolio-manager at `:8003`. One of the two is stale; defer to CLAUDE.md table — config.py likely wrong.
5. **`LIVE_TRADING_ACK` enforcement** — confirmed exactly as documented; cannot be bypassed without code change.

## Related

- Flows: [[../flows/Signal-Pipeline]], [[../flows/Order-Lifecycle]], [[../flows/Emergency-Stop]]
- Concepts: [[../concepts/Risk-Model]], [[../concepts/Trading-Mode-Flags]], [[../concepts/Auto-Trader]], [[../concepts/Validated-Symbols]], [[../concepts/Test-Setup-Gotchas]], [[../concepts/State-Persistence]], [[../concepts/Paper-Trading-Internals]]
- ADRs: [[../decisions/ADR-002-trading-engine-lifespan-refactor]], [[../decisions/ADR-004-paper-trading-default]], [[../decisions/ADR-005-emergency-stop-file-flag]], [[../decisions/ADR-006-mainnet-prices-paper-orders]], [[../decisions/ADR-011-paper-deterministic-execution]], [[../decisions/ADR-016-http-not-events]]
- Sibling services: [[bybit-connector]], [[market-data-service]], [[technical-analysis]], [[portfolio-manager]], [[risk-metrics-service]]

## Corrections 2026-07-29

Reflects the 2026-07-28 accounting/risk fix campaign (verified in source):

- **Paper accounting overhaul** (`paper_trading.py`): closes credit margin+P&L−commission on both sides; SHORT P&L sign fixed; `reduce_only` honored (rejects, never flips); `position_id` targeting; partial closes and scale-in/DCA. Details in *Paper trading internals* above.
- **Kill switch** (`trading_enhancements/kill_switch.py:151–204`): fed **equity** (cash + unrealized), not raw cash — opening a position no longer looks like an instant daily loss. Consecutive-loss streak updates **only on trade closes** (`is_trade_close=True`); position OPENs no longer reset the streak.
- **Per-trade cap CLAMPS** (10 % paper / hard 2 % LIVE floor) instead of rejecting; **daily-loss auto-rolls per UTC day** (`risk_manager.py:32–65`). See risk-gates table.
- **Consensus counts directional votes only** (`aggregation/aggregator_core.py:321–324`): a BUY's consensus = `buy_count`, not `max(buy,sell,hold)`. Previously 2 BUY + 3 HOLD passed a min-consensus-3 BUY gate.
- **Max-hold force-close routes through the engine** (`auto_trader.py:2410–2457`) — was a dead `TypeError` path.
- **VP mode** (`signal_aggregator.py:1145–1183`): `get_trading_signal_with_vp` now accepts `regime_analysis`; the volume-profile path previously raised `TypeError` on the kwarg and never traded.
