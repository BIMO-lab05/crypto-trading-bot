# Full-System Diagnostic — 2026-07-31

Status: **IN PROGRESS** (live audit; sections filled as evidence lands)
Branch: `docs/vault-restructure` @ `9bb8a01`
Stack: 13 containers up and healthy at time of capture.

---

## 0. Scope note on the request premise

The request asserted the paper account "initializes with $10,000" and named
"Alpaca paper configuration" as a candidate source. This repo is **Bybit-only** —
there is no Alpaca integration anywhere in the tree. The $10,000 premise was
therefore checked empirically against four independent surfaces (config
defaults, compose/k8s env, live database rows, live API responses, and the
frontend) rather than assumed.

Result: **the premise is half true.** Backend *configuration* is already $100.
The **database row and the entire frontend are still $10,000.** Details in §1.

---

## 1. Paper-trading starting capital — root cause

### 1.1 What is already correct ($100)

| Surface | Value | Evidence |
|---|---|---|
| trading-engine setting | `100.0` (`ge=100.0`) | `services/trading-engine/app/config.py:557-561` |
| portfolio-manager setting | `100.0` | `services/portfolio-manager/app/config.py:51-55` |
| canonical compose | `PAPER_INITIAL_BALANCE=100.0` | `docker-compose.unified.yml:596` |
| legacy compose | `PAPER_INITIAL_BALANCE=100.0` | `docker-compose.yml:279` |
| headless compose | `${PAPER_INITIAL_BALANCE:-100.0}` | `docker-compose.headless.yml:297` |
| k8s prod | `"100"` | `infrastructure/kubernetes/trading-engine-deployment.yaml:579` |
| k8s staging | `"100"` | `infrastructure/kubernetes/staging/configmap.yaml:66,132` |
| **live API** | `initial_balance: "100.0"` | `GET :8005/api/v1/performance` |

Live API response, captured verbatim:

```json
{"success":true,"metrics":{"total_trades":2,"winning_trades":0,"losing_trades":2,
"total_pnl":"-4.301363408358","realized_pnl":"-2.57370004",
"unrealized_pnl":"-1.727663368358","win_rate":0.0,
"current_balance":"97.42629996","initial_balance":"100.0","roi":-2.57370004}}
```

### 1.2 What is still $10,000 — CONFIRMED DEFECTS

**D-1 (HIGH) — stale database row.** The single `portfolios` row still carries
`initial_balance = 10000`, written 2026-04-27, before the $100 default landed.
Config changes do not retroactively rewrite persisted rows.

```
$ docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot \
    -c "SELECT id,name,initial_balance,cash_balance,total_value,created_at FROM portfolios;"

 id |          name           | initial_balance | cash_balance | total_value  |         created_at
----+-------------------------+-----------------+--------------+--------------+----------------------------
  1 | Paper Trading Portfolio |  10000.00000000 |  80.70266802 | 100.00000000 | 2026-04-27 02:00:48.196184
```

Note the row is internally inconsistent three ways: `initial_balance` 10000,
`total_value` frozen at 100.00, and `cash_balance` 80.70 — while the live API
reports cash 97.43. The row has drifted from the runtime.

**D-2 (HIGH) — the frontend hardcodes $10,000 fallbacks on reachable pages.**
These use `||` rather than `??`, so all of `0`/`null`/`undefined`/`NaN` collapse
to the fallback — a legitimately-zero balance renders as $10,000.

Live (reachable) set:

| File:line | Code | Why it matters |
|---|---|---|
| `frontend/src/components/PortfolioCard.jsx:43` | `parseFloat(metrics.current_balance) \|\| 10000` | displayed as Cash Balance |
| `frontend/src/components/PortfolioCard.jsx:44` | `parseFloat(metrics.initial_balance) \|\| 10000` | **divisor** for `exposurePercentage` (`:64`) — a $100 position reads 1.0% |
| `frontend/src/components/KeyMetricsStrip.jsx:195` | `parseFloat(metrics.current_balance) \|\| 100` | same field as `:43`, 100× different fallback |
| `frontend/src/services/analyticsApi.js:203` | `calculateEquityCurve(trades, initialBalance = 10000)` | vs `:358` which defaults to 100 |
| `frontend/src/hooks/usePerformanceMetrics.js:119-128` | `portfolioData?.total_value ?? … ?? 100` | see F-1 — worse than a bad constant |

> **Correction.** An earlier pass of this report also listed
> `EquityCurveChart.jsx:211`, `PerformanceDashboard/PerformanceDashboard.jsx:302`,
> `useChartData.js:112`, and `usePerformanceMetrics.js:279` as live defects.
> Reachability analysis (§4.3) proved all four sit in **dead code** with zero
> importers. They move to the F-8 deletion list rather than the fix list.

This is the most likely surface on which $10,000 was actually observed.

**D-3 (HIGH — upgraded from MEDIUM) — `PerformanceTracker` is *always*
constructed at $10,000.** Not dormant. Verified:

```
$ grep -n "get_performance_tracker(" services/trading-engine/app/**/*.py
auto_trader.py:2955:                perf_tracker = get_performance_tracker()
auto_trader.py:3703:                    perf_tracker = get_performance_tracker()
handlers/orchestration.py:454/500/610:  tracker = get_performance_tracker()
```

**No production call site passes `initial_balance`.** The lazy singleton at
`performance_tracker.py:557-563` therefore always takes the
`balance = initial_balance or Decimal("10000")` branch at `:561`. Every metric
this tracker computes — `total_pnl_pct` (`:256`), drawdown against
`peak_balance` (`:137`) — is measured against a $10,000 base on a $100 account,
understating returns and drawdown by **100×**.

Related dormant defaults (genuinely unreached):

| File:line | Code |
|---|---|
| `services/trading-engine/app/repositories.py:358` | `initial_balance: Decimal = Decimal("10000")` — **not** the writer of the stale DB row; see §4.4, migration 001 seeded it |
| `services/trading-engine/app/performance_tracker.py:128` | `def __init__(self, initial_balance: Decimal = Decimal("10000"))` |

**Which of these is actually on screen today?** None of them. Verified live:
`/api/trading/performance` returns `initial_balance "100.0"` and
`current_balance "97.42629996"` — both finite and non-zero, so the
`PortfolioCard` / `KeyMetricsStrip` fallbacks never fire. Those are
**latent-on-zero**: they surface the instant a balance legitimately reaches 0 or
the field goes missing during a background refetch. The `PerformanceTracker`
$10,000 base *is* unconditional, but its consumers are either internal to
`auto_trader` or the orchestrator endpoints, which currently return
`strategy_count: 0`. So the honest statement is: **no surface renders $10,000
right now; four latent paths and one unconditional metric distortion were
fixed.**

**D-5 (HIGH) — three disagreeing "current balance" numbers are served at the same
instant.** The `/performance` endpoint is correct in isolation, but it is not the
only balance the system publishes — see **T-1** in §4.2 for the full table
(97.43 vs 83.48 vs 80.70) and the root cause.

### 1.3 Explicitly OUT of scope for the $100 change

`services/risk-metrics-service/app/backtest_models.py:16` and
`app/backtesting.py:126` default `initial_capital = Decimal("10000")`. That is a
**research parameter**, not the paper account. Forcing it to $100 would push most
backtests under Bybit min-notional and produce garbage results. Left unchanged
deliberately.

---

## 2. Live-state observations (captured before any change)

3 OPEN positions on a $100 account:

| Symbol | Side | Notional | Unrealized |
|---|---|---|---|
| BTCUSDT | SHORT | ~$48.3 | -0.859 |
| BNBUSDT | LONG | ~$65.4 | -0.255 |
| ADAUSDT | LONG | ~$49.7 | -0.614 |

**Gross notional ≈ $163.5 on a $100 account (163%).** Under investigation as to
whether any aggregate-exposure cap exists, or only per-trade risk sizing.

`portfolio-manager` reports `total_value` 95.70 = initial − pnl, while
`cash_balance` 97.43 + holdings 163.5 = 261. The two accounting formulas do not
reconcile — under investigation.

---

## 3. Baseline before changes

Working tree was already dirty at session start (9 modified files, 3 untracked
dirs). A baseline `pytest` run was captured **before** any edit so that
pre-existing failures are not attributed to this work. Results below.

```
$ cd services/trading-engine && python3 -m pytest tests/ -q
=========== 36 failed, 1449 passed, 842 skipped in 410.39s (0:06:50) ===========
```

This is worse than the "9 known failures" recorded in `wiki/hot.md` — the real
number is **36 failing**. Failure clusters:

- `tests/unit/test_repositories.py` — 19 failures (the entire repository layer)
- `tests/strategies/test_pairs_trading.py` — 11 failures
- `tests/integration/test_connector_contract.py` — 2 failures
- `tests/test_handler_endpoints.py::test_get_performance_endpoint` — 1
- `tests/test_main.py::TestLifespan::test_lifespan_startup` — 1 (`ValueError`)

**D-4 (HIGH) — safety-critical modules have their unit tests blanket-disabled.**
`services/trading-engine/tests/unit/test_risk_manager.py:15` sets a module-wide
`pytestmark = pytest.mark.skip(...)`, silently disabling **32 risk-manager
tests**. `tests/unit/test_paper_trading.py` is skipped the same way (16 tests).
Both were suppressed during a "PR #86 CI fix-up" rather than rewritten. The risk
manager and the paper-trading ledger are the two modules whose correctness the
`$100` capital guarantee depends on, and neither has live unit coverage.

842 total skips across the suite means the green-looking runs are not evidence
of much.

**Kill switch verified correct** — the config default
(`config.py:200`, `/app/EMERGENCY_STOP`) disagrees with the documented mount
path, but the container env overrides it correctly:

```
$ docker exec crypto-bot-trading printenv | grep EMERGENCY
EMERGENCY_STOP_FILE=/app/safety/EMERGENCY_STOP
EMERGENCY_STOP_LOSS=0.05
```

The stale default is still a latent trap for any deployment that does not set
the env var (e.g. a bare `docker run`, or the k8s manifests if they omit it).

**`.env` does not override the balance.** Live container env confirms:

```
$ docker exec crypto-bot-trading printenv | grep -iE "BALANCE|PAPER|AUTO_TRADING|MAX_"
MAX_POSITION_SIZE_PCT=10.0
MAX_RISK_PER_TRADE=0.10
MAX_LEVERAGE=20.0
PAPER_TRADING_MODE=true
PAPER_INITIAL_BALANCE=100.0
AUTO_TRADING_ENABLED=true
```

Note `TRADING_MODE` and `BYBIT_TESTNET` are **absent** from the container
environment entirely — the service falls back to code defaults
(`trading_mode` default `"PAPER"`, `config.py:193-195`, which is fail-closed and
correct). `MAX_RISK_PER_TRADE=0.10` vs `MAX_POSITION_SIZE_PCT=10.0` use
inconsistent units (fraction vs percent) in the same env block — flagged for
the pipeline audit.

---

## 4. Findings by domain

### 4.1 Injection / deserialization sweep (verified)

**S-1 (HIGH, latent) — request-controlled path feeds `keras.models.load_model`
and `pickle.load` in ml-prediction-service.**

`services/ml-prediction-service/app/ml_models/gru_model.py:95` builds the model
path by interpolating `self.symbol` and `self.interval` straight into a filename;
`:119` loads it via `keras.models.load_model`, and `:140-144` builds a
`_gru_scalers.pkl` path the same way and `pickle.load`s it. Both `symbol` and
`interval` arrive from HTTP with **no coercion or allowlist** —
`app/main.py:686-687` types `interval` as a plain `str` query param, and
`main.py:1345-1354` (`GET /api/v1/models/{symbol}`) reaches `get_predictor()`
before doing any other work. Query params may contain `/`, so `interval` is a
traversal vector; `symbol` is weaker because a path segment cannot hold a literal
slash. Both loads are gated on `.exists()`, so this is
*arbitrary-existing-file load*, not upload-then-load — but unpickling any
attacker-chosen existing file is arbitrary code execution, and
`docker-compose.yml:442` bind-mounts a host directory into `/app/models`.

Mitigating and load-bearing: **ml-prediction-service is not running.** It sits
behind the compose `ml` profile and is absent from the 13 live containers. The
service also carries no auth dependency and `docker-compose.yml:434` publishes
`8007:8007`, so the exposure becomes real the moment anyone enables the profile.
Fix is a one-line `int(interval)` coercion plus a symbol allowlist at the
handler boundary.

**S-2 (LOW) — `shell=True` in a backup test script.**
`scripts/testing/test_backup_restore.py:59-61` runs `subprocess.run(command,
shell=True)`, and `:106` interpolates `backup_file` — derived from `ls -t`
output — into the command. Filesystem-derived, not HTTP-derived; exploitation
requires an attacker-named file in `/backups/postgres/`.

**Cleared (checked, no finding):** no SQL injection anywhere — every raw-SQL site
uses bound parameters or module-level constants
(`repositories.py:301`, `performance_history.py` asyncpg `$1` binds,
`market-data-service/app/database.py:189` iterating literal statement lists,
`tournament-harness/app/leaderboard/queries.py:246` gated by an `ALLOWED_ORDER_BY`
allowlist). No `eval`, `exec`, `yaml.load`, `torch.load`, `dill`, or `marshal`
under `services/` or `scripts/`. No SSRF —
`api-gateway/app/services/service_proxy.py:82` composes URLs only from a
hardcoded service dict, and `main.py:2571` places user path after a literal `/`,
so no userinfo/protocol-relative override. `api-gateway/app/main.py:1373` is
correctly guarded by both a `^[A-Za-z0-9_\-]+$` regex and an `is_relative_to`
containment check.

### 4.2 Trading pipeline

**Which code path is actually live.** `docker-compose.unified.yml:571-634` sets
`STRATEGY_MODE=ensemble`, `LEVERAGE_ENABLED=true`, `DEFAULT_LEVERAGE=10.0`.
`get_auto_trader()` (`auto_trader.py:4407-4423`) maps that to
`StrategyMode.ENSEMBLE`, so the executing path is
**`AutoTrader._check_and_trade_ensemble` (`auto_trader.py:4158-4300`)** — *not*
`_execute_trade_with_setup` and *not* `_execute_trade`, which is where most of
the risk gates live. Every finding below turns on that fact. Verified by reading
lines 4185-4264 directly.

**T-1 (CRITICAL) — three different "current balance" numbers are served
simultaneously.** Verified live, same instant:

| Source | Value | Formula |
|---|---|---|
| `GET :8005/api/v1/performance` | **97.43** | `initial + realized_pnl` (`handlers/performance.py:78-79`) |
| kill-switch metrics in `/api/v1/trading/status` | **83.48** | equity via `get_total_equity()` |
| `portfolios.cash_balance` in postgres | **80.70** | engine `self.balance` after margin+commission debit |

Root cause: `paper_trading.py:118-123` defines
`get_total_equity() = self.balance + unrealized_pnl`, but `self.balance` already
had the posted margin deducted at open (`paper_trading.py:346`) and it is never
added back. Margin is a balance-sheet transfer, not an expense. Meanwhile
`handlers/performance.py:79` ignores the engine balance entirely and recomputes
`initial + realized`. Every downstream consumer — kill switch
(`auto_trader.py:2093-2103`, `2941-2949`), portfolio heat, `/performance`, the
dashboard — reads a different number. With the live book the omitted margin is
`163.3/10 = $16.33`.

**T-2 (CRITICAL) — the deployed path enforces no per-trade cap.**
`_execute_trade_with_setup:1989-1996` and `_execute_trade:3784-3786` both apply
`cap_fraction = min(max_risk_per_trade, 0.02)` in LIVE.
`_check_and_trade_ensemble` has **no equivalent** — I read `auto_trader.py:4226-4234`
and the only sizing is `margin_value = balance × ens_signal.position_size_pct`,
`position_value = margin_value × leverage`. It trusts the ensemble's internal
cascade, which caps *margin* at `max_risk_per_trade`. Flipping
`TRADING_MODE=LIVE` today leaves the ADR-010 hard 2% cap **entirely unenforced on
the only path that trades**. Worse, even where the clamp does exist it clamps the
margin fraction, so at `DEFAULT_LEVERAGE=10` a "2% LIVE cap" is 20% notional.

**T-3 (CRITICAL) — the ensemble path executes through the paper engine even in
LIVE mode.** `auto_trader.py:4197` calls `get_paper_engine()` and `:4255` calls
`paper_engine.execute_market_order(...)` **unconditionally** — no
`if trading_mode == "LIVE"` branch, unlike `:1853-1861`. Verified by reading the
block. With `TRADING_MODE=LIVE` + `STRATEGY_MODE=ensemble`, nothing reaches
Bybit while `total_trades_executed` increments and notifications fire.

> **Fix-ordering hazard.** Repairing T-3 alone converts a reporting bug into a
> real-money 20%-notional cap breach. **T-2 must land before T-3.**

**T-4 (CRITICAL) — restart resurrects already-exited quantity as cash.**
`position_manager.py:782-796` rebuilds `Position` without `remaining_quantity`
or `realized_pnl`; `models/position.py:83-84` then sets
`remaining_quantity = quantity`. A position that took TP1/TP2 before a restart
comes back full size, and its close credits
`margin_returned = entry × close_qty / leverage` on quantity whose margin was
never posted. Paper cash is created from nothing on every
restart-then-close of a partially exited position.

**T-5 (CRITICAL) — deployed path bypasses the dedup lock and most entry gates.**
Missing from `_check_and_trade_ensemble` versus the other two paths:
`_claim_open_slot` (`:1637`), `_check_daily_trade_limit`/`_record_trade`
(`:1408`, `:1494`), `_check_symbol_cooldown` (`:1431`), `allowed_trade_sides` /
`short_trading_enabled` (`:1784-1800`), and `_passes_min_notional` (`:1502`).
Confirmed live: `/api/v1/trading/status` reports `daily_trades.count: 0` with
`limit: 50` while 3 positions are open — the counter is dead, so
`max_daily_trades` and `min_time_between_trades_same_symbol` never bind.
`_record_sl_hit` *is* called on SL close (`:2930-2931`), filling
`_sl_cooldown_until`, but nothing in ensemble mode reads it — the 4-hour
whipsaw guard is armed and never consulted.

**T-6 (CRITICAL, latent) — no aggregate exposure cap is reachable.**
`max_total_exposure_pct=80.0` (`config.py:367-372`) is enforced only inside
`RiskManager.check_position_limits` (`risk_manager.py:239-242`), whose only
callers are `paper_trading.can_open_position:413` and
`live_trading.py:146,302`. `AutoTrader` calls none of them. This is why the live
book carries **163% gross notional on a $100 account** with nothing objecting.

**T-7 (HIGH) — daily-loss breaker base is the paper constant, static, and wrong
in LIVE.** `risk_manager.py:84`:
`max_loss = paper_initial_balance × max_daily_loss_pct/100`, with no
`trading_mode` branch. In LIVE the 5% cap is 5% of $100 regardless of real
account size. It is also a fixed base rather than current equity, so the cap
doesn't shrink as the account draws down. The breaker itself *is* wired in the
deployed path (`:4170` → `should_halt_trading`) — only the base is wrong.

**T-8 (HIGH) — max-hold timer resets on every restart.**
`position_manager.py:782-796` doesn't restore `opened_at`, so
`models/position.py:65` `default_factory=now()` applies. A 47h-old position that
survives a restart gets a fresh 48h. This is the exact 185h-SOLUSDT failure the
max-hold fix was written for. The same loader also drops
`take_profit_1/2/3` and `trailing_stop`, so the partial-exit ladder is gone for
restored positions.

**T-9 (HIGH) — startup sync discards all realized P&L.**
`paper_trading.py:104`: `self.balance = self.initial_balance - total_position_cost`.
Every restart erases cumulative realized P&L and rebases to $100 minus open cost.
With T-1, no reported equity figure survives a restart.

**T-10 (HIGH) — ensemble SL/TP are computed, reported, and discarded.**
The `OrderCreate` built at `auto_trader.py:4244-4254` carries **no
`stop_loss` and no `take_profit`** — verified by reading it. So
`position_manager.create_position` applies generic 2%/4% defaults
(`position_manager.py:78-82`), while `notify_trade_open` sends
`ens_signal.stop_loss` / `ens_signal.take_profit`. **The Telegram alert and the
position's actual stop are different numbers.**

**T-11 (HIGH) — LIVE partial exits and DCA route through the paper engine.**
`auto_trader.py:3446`/`3469` and `3533`/`3585` assign
`trading_mode = settings.trading_mode`, never use it, then call
`paper_engine.execute_market_order`. `_execute_partial_exit` at `:3345` *does*
guard LIVE correctly, which marks this as oversight rather than design.

**T-12 (HIGH) — LIVE market orders hardcode `reduce_only: False`.**
`live_trading.py:165` drops `order.reduce_only` from the request body and
`:215-225` unconditionally calls `create_position`. A reduce-only intent opens an
opposing position on Bybit instead of closing. The paper engine got this fixed
2026-07-28 (`paper_trading.py:277-285`); the live engine did not.

**T-13 (HIGH) — a SELL signal on an open SHORT doubles the short.**
`services/trading_service.py:176-187` picks `open_positions[0]` for the symbol
**regardless of side** and passes `position_id` without `reduce_only`. In
`execute_market_order`, SELL's `close_side` is LONG so the close branch at
`:209` misses; execution falls through to the scale-in branch at `:288` where
`pos.side == open_side (SHORT)` matches and `scale_in` fires.

**T-14 (HIGH) — the file kill switch orphans open positions.**
`auto_trader.py:887-896` sets `is_running = False` and `break`s on
`EMERGENCY_STOP`, so `_monitor_positions` never runs again — stops,
take-profits, trailing updates and max-hold force-close all stop being evaluated
until an operator restarts. Contrast the risk kill-switch branch at `:908-919`,
which deliberately keeps monitoring while blocking new entries. Positions with
live stops are not the same as flat positions.

**T-15 (MEDIUM) — kill-switch baseline and readings use different units.**
`auto_trader.py:853` seeds the baseline with `paper_engine.get_balance()`
(**cash**); every later `update_metrics` passes **equity** (`:2093-2097`,
`:2941-2944`). Drawdown and daily-loss thresholds are computed against a moving,
inconsistent reference.

**T-16 (MEDIUM) — the only genuine concurrency hazard is the HTTP path.**
`handlers/signals.py:409` → `services/trading_service.py:130-136`:
`execute_signal_trade` runs in a FastAPI request handler, interleaves with the
trading-loop task at every `await`, takes no `_opening_lock`, and `_execute_buy`
does no same-symbol existence check. Result: a duplicate position invisible to
the dedup machinery at `auto_trader.py:1637-1671`. To be precise about what is
*not* a race — the loop's `for symbol in self.symbols` (`:934`) is sequential
within one task, and `execute_market_order`'s check-and-debit
(`paper_trading.py:338-346`) contains no `await`, so it cannot lose an update.

**T-17 (MEDIUM) — unordered fire-and-forget DB persistence.**
`position_manager.py:130-132`, `321-328`, `404-408`, `457-461` — four
`asyncio.create_task` calls with no done-callback, no strong reference, no
ordering guarantee. Failures are silent, tasks can be GC'd mid-flight, a close
write can land before the create write for the same position, and pending tasks
are cancelled on shutdown. Contrast `_spawn_trade_log`
(`paper_trading.py:42-45`), which does it correctly.

**T-18 (MEDIUM) — a single fragile price source silently suspends exit checks.**
`auto_trader.py:2570-2574`, `2779-2806`: `_get_current_price` derives price from
indicator metadata on a full multi-timeframe aggregator call; on any failure it
returns `None` and the monitor loop `continue`s with only a WARNING. No fallback
source, no consecutive-miss counter. A degraded technical-analysis service
leaves every position unmanaged indefinitely while `/health` stays green.

**T-19 (MEDIUM) — `max_position_size_pct` is used with two different meanings.**
`risk_manager.py:127` treats it as max position *value*; `:141` treats the same
number as max *loss at the stop*. With a 2% stop the risk branch yields ~5× the
notional the first branch allows. The `min()` at `:145` currently rescues it, but
the semantics are inverted.

**T-20 (MEDIUM) — two different affordability models.**
`paper_trading.py:400-405` (`can_open_position`) reserves full notional +
commission; `:335-338` (`execute_market_order`) deducts margin + commission. At
10× these differ by an order of magnitude. Currently masked only because the
auto-trader never calls `can_open_position` — which is itself the gap in T-6.

**T-21 (MEDIUM) — exposure math ignores partial exits.**
`paper_trading.py:444-446` and `position_manager.py:469-472` compute exposure
from `quantity`, not `remaining_quantity`, overstating deployed capital after any
TP fill. This is the figure a future aggregate-exposure gate would consume.

**T-22 (MEDIUM) — daily counters roll on different days.**
`auto_trader.py:1416` uses `datetime.now().date()` (container-local);
`risk_manager.py:47` uses `datetime.now(timezone.utc).date()`. Under a non-UTC
container TZ the trade limit and the loss limit reset hours apart.

**T-23 (MEDIUM) — `scale_in` recomputes average entry but not the stop.**
`position_manager.py:442-447`. After a DCA fill the `stop_loss` still references
the original entry; for a LONG averaged down 5% the stale stop sits above the new
average entry, making the position immediately stop-eligible at larger size.
Currently unreachable (see T-25) and also blocked by check ordering, but it goes
live the moment ATR trailing widens the stop.

**T-24 (MEDIUM) — exit-overlay state is keyed by symbol and memory-only.**
`partial_profit_taker.positions`, `dca_manager`, `portfolio_heat_manager` are all
keyed on `position.symbol` (`auto_trader.py:2664`, `3999` region). Two positions
on one symbol collide onto one state object, and all of it is lost on restart
while DB-backed positions survive.

**T-25 (MEDIUM, partially corrected) — some exit overlays are never populated in
the deployed path.** The auditing agent claimed portfolio heat "reports ≈0%
permanently." **That is wrong** — live `/api/v1/trading/status` shows
`portfolio_heat_manager.total_heat_pct: 3.92` with all 3 positions tracked. The
claim holds for the others, confirmed live:
`dca_manager.active_dca_positions: 0`, `partial_profit_taker.positions_tracked: 0`,
`atr_trailing_stop.positions_tracked: 0`, `order_state_machine.total_orders: 0`,
`walk_forward_tester.trades_recorded: 0` — all with 3 open positions. The
Position-model TP1/2/3 ladder still works via
`position_manager.py:86-95` → `check_all_exit_conditions:626-630`.

**T-26 (LOW) — a Prometheus counter reports success for a no-op.**
`main.py:1154-1156` increments `trades_executed_total{status="success"}`
unconditionally, then `:1174` returns a body stating
`"actual execution not implemented yet"`.

**T-27 (LOW) — the UTC day roll clears operator halts.**
`risk_manager._roll_daily_window_if_needed` (`:44-57`) sets
`trading_halted = False` on any day change, including a halt set deliberately via
`halt_trading()`. A manual halt lifts itself at 00:00 UTC.

**T-28 (OBSERVATION) — the bot is currently trading nothing.**
`/api/v1/trading/status`: `total_signals_checked: 400`,
`total_trades_executed: 0`, `total_trades_rejected: 400`. Log inspection shows
the rejections are legitimate — 4 of 5 symbols return
`[ENSEMBLE] HOLD — no legs fired`, and ADAUSDT fires `BUY conf=10.50%
size=5.00%` every cycle but hits `Already have position on ADAUSDT, skipping`.
Two things worth noting: `agg_conf=1.00` co-occurring with
`HOLD — no legs fired` points at the ensemble leg-wiring work already in flight
(`.planning/quick/260730-vwn-fix-ensemble-legs-live-cap/`), and
`total_trades_rejected` conflates "no signal" with "blocked by risk," making the
metric useless for diagnosing whether risk gates are firing.

### 4.3 Frontend

**Reachability first — this changes the $10,000 fix scope.** Routes are
`App.jsx:302-320`; `/` → `components/Dashboard.jsx`, `/performance` →
`pages/PerformanceDashboard.jsx`. The directories
`components/PerformanceDashboard/` and `components/performance/` form a mutual
barrel cycle with **no importer outside themselves** — verified by grep, the only
hit is `App.jsx:33` importing the *different* file `pages/PerformanceDashboard`.
`hooks/useChartData.js` likewise has zero importers. So **most of the $10,000
sites listed in §1.2 are in dead code.** The corrected live set is below.

**F-1 (CRITICAL) — `usePerformanceMetrics.js:119-128` uses a *current* value as
the *starting* baseline.** This is the worst of the balance bugs and it is
disguised as the fixed one — it carries a `?? 100` guard and a comment naming the
paper default.

```js
const raw =
  portfolioData?.total_value ??   // <-- current value, not starting capital
  portfolioData?.cash_balance ?? ... ?? 100
```

It feeds `calculateEquityCurve` (`:133`) and `calculatePerformanceMetrics`
(`:151`) as the origin, and re-reads on a 30 s poll (`:52`), so **the equity
curve's origin translates vertically while the user watches**. `peakEquity`
(`analyticsApi.js:417`) then seeds from a number already containing realized
gains, inflating the `maxDrawdownPercent` denominator (`:426`). Live today
`total_value` is 95.70, not 100. Hook is reachable —
`pages/PerformanceDashboard.jsx:43,1005`.

**F-2 (HIGH) — two tiles on the landing page disagree about the same field.**
`PortfolioCard.jsx:43` → `parseFloat(metrics.current_balance) || 10000`;
`KeyMetricsStrip.jsx:195` → `parseFloat(metrics.current_balance) || 100`. Same
field, same `usePerformance()` query, 100× apart. Blow the paper account to
exactly $0 and the dashboard shows **Cash Balance $10,000.00** next to a strip
computing P&L% against $100. `PortfolioCard.jsx:44` is worse than cosmetic — the
`initialBalance` fallback is a **divisor** for `exposurePercentage` (`:64`), so a
$100 position reads **1.0%** instead of 100%.

Because these use `||` and not `??`, all four of `0`/`null`/`undefined`/`NaN`
collapse to the fallback — a legitimately-zero balance renders as $10,000.

**F-3 (HIGH) — `analyticsApi.js` is half-migrated.** `:203`
`calculateEquityCurve(trades, initialBalance = 10000)` vs `:358`
`calculatePerformanceMetrics(trades, initialBalance = 100)` — same file, same
concept. A $50 loss on a $100 account is 50% drawdown; against a 10000 baseline
`:426` reports **0.5%**, understating risk by 100×.

**F-4 (CRITICAL) — there is no login flow, and flipping to LIVE breaks the UI
kill switch.** `src/services/api.js:21-23` has the only auth code in the tree and
it is commented out. Meanwhile `api-gateway/app/auth_middleware.py:58-63` gates
auth on mode — in paper mode a tokenless request gets a synthetic **admin**
principal (`get_current_user_gated`, `:147`), which is the only reason the
dashboard works. Set `TRADING_MODE=LIVE` — one of the four documented steps to
real money — and `get_current_admin_user` starts demanding a bearer token on
`/api/trading/start` (`main.py:1434`), `/api/trading/stop` (`:1453`),
`/api/portfolio/emergency-stop` (`:1796`), `/api/portfolio/buy` (`:1713`),
`/api/portfolio/sell` (`:1759`). The frontend calls all of these
(`CommandPalette.jsx:80,97,116`, `api.js:82,236,239`) and **cannot produce a
token**. Failure scenario: real money at risk, operator hits Emergency Stop, gets
a silent 401, and the only remaining halt is `touch safety/EMERGENCY_STOP` on the
host. This belongs on the pre-live checklist as a blocker.

**F-5 (HIGH) — three endpoints 404 through the gateway.** `api.js:99`
`/market/orderbook/{symbol}`, `:174` `/ml/models/retrain/{symbol}`, `:226`
`/trading/signals/compare/{symbol}` — no matching gateway route. The code already
knows (`:96`, `:170`, `:224` carry "does not have … endpoint" comments) and ships
the callers anyway. Clean negative: the other 40 frontend paths resolve, and
**no `v1`-prefix misuse exists** — `baseURL: '/api'` (`api.js:10`) is correct.

**F-6 (HIGH) — failed ticker fetches render as `$0.0000` under a green "Live"
dot.** `useTicker.js:43-45` catches per-symbol failures and pushes `null`;
`:50-56` filters them out, so `queryFn` never rejects and `isError` is never
true. `PriceTickerGrid.jsx:61` then does `parseFloat(ticker.last_price) || 0`.
A partial market-data outage shows `$0.0000` beside the hardcoded pulsing "Live"
indicator (`:49-50`). A trader reads a zero as a quote.

**F-7 (HIGH) — `VITE_API_BASE_URL` is documented but never read.**
`vite.config.js:47` and two component docblocks promise it; the only
`import.meta.env` uses in `src/` are `useGatewayWebSocket.js:34,38` — which is
itself dead code, so the whole `VITE_WS_URL`/`VITE_ENABLE_WEBSOCKET` contract at
`vite.config.js:56-71` is wired to nothing. `baseURL` is hardcoded.

**F-8 (HIGH) — 33% of the frontend source tree is unreachable** — 25 files,
~10,028 lines. Orphans: `Test.jsx`, `utils/symbols.js`, `contexts/index.ts`,
`hooks/useChartData.js` (627 L), `hooks/useDateRange.js` (527 L),
`hooks/useGatewayWebSocket.js` (226 L), `hooks/usePhase3.js` (296 L). Dead by
transitivity: all 5 files in `components/PerformanceDashboard/`, all 11 in
`components/performance/`, plus `utils/formatters.js` and `utils/chartConfig.jsx`.
`__tests__/performance.test.jsx` and `__tests__/PerformanceDashboard.test.jsx`
are green tests over code that never ships.

**F-9 (HIGH) — the project's own URL regression gate isn't in CI.**
`package.json:15` defines `check-no-hardcoded-urls`; no workflow references it.

**F-10 (MEDIUM) — silent failure and fabricated freshness on the landing page.**
`PortfolioCard.jsx:37` — a failed `usePositions()` renders "No active positions"
(`:196`), indistinguishable from a flat book, because `TileState` receives only
`query={perfQuery}` (`:72`). And `:75` passes `lastUpdatedAt={undefined}`,
disabling the stale badge, while `:96` renders
`Last updated: {new Date().toLocaleTimeString()}` — a timestamp that ticks
forward while the data is frozen. Same at `KeyMetricsStrip.jsx:188,229`.

**F-11 (MEDIUM) — displayed risk config contradicts ADR-010.**
`Dashboard.jsx:224` hardcodes `<ConfigItem label="Position" value="2%" />`; paper
mode runs a 10% per-trade cap. Adjacent, `:254-257` renders a green pulsing
"Backend: Connected" as static markup reflecting no health state.

**F-12 (MEDIUM) — assorted correctness.** `TileState.jsx:244` has no branch for
a disabled query (in react-query v5 `enabled:false` gives
`isLoading===false, data===undefined`), so all branches fall through to
`children` — reachable at `Phase3Dashboard.jsx:180,357-364`.
`ThemeContext.tsx:293-299` always persists `theme`, so the `if (!storedTheme)`
guard at `:315-321` never passes and OS theme flips are ignored forever.
`Phase3Dashboard.jsx:83-86,146-149` leak `setTimeout` handles; `:116-136` runs a
4-model training loop with no `AbortController` or unmount flag.
`EmergencyStop.jsx:31` early-returns and unmounts the button `triggerRef` points
at (`:121-122`), so focus restoration lands a keyboard user on `document.body` —
on the dashboard whose most dangerous control they just used.
`ToastContext.jsx:93` recreates the context value every render;
`PriceChart.jsx:104` declares `CustomTooltip` in the render body, remounting the
tooltip subtree on every 60 s refetch.

### 4.4 Data layer

**Correction to §1.** The stale `initial_balance = 10000` row was **not** written
by `repositories.py:358`. Its only caller, `lifespan/data.py:47-51`, already
passes `initial_balance` explicitly from `settings.paper_initial_balance`
(verified by reading it). The real source is a seed INSERT in the migration:

```sql
-- infrastructure/migrations/001_initial_schema.sql:225-237
INSERT INTO portfolios (portfolio_id, name, initial_balance, cash_balance, total_value)
VALUES ('paper_trading', 'Paper Trading Portfolio', 10000.00, 10000.00, 10000.00)
ON CONFLICT (portfolio_id) DO NOTHING;
```

`ON CONFLICT DO NOTHING` plus the early return in `repositories.py:376-379`
makes `initial_balance` **write-once** — no config change can ever correct it.

**DL-1 (CRITICAL) — market-data ingest is dead and did not resume after
restart.** The single most operationally severe finding in this audit.
**Root-caused and fixed** — see §7.

```
market_data=# SELECT to_timestamp(max(created_at)/1000), count(*) FROM tickers;
     newest_ticker      | total
------------------------+-------
 2026-07-30 22:10:27+00 | 58312
```

The stack restarted **2026-07-31 14:26**. Zero rows have been written since
22:10 the previous day. Meanwhile the service happily *serves* reads — its logs
show a steady stream of `Retrieved 200 klines for ADAUSDT (240) mainnet_only=True`
and `200 OK`. Because CLAUDE.md's own design makes the DB the cache, **every
indicator, every signal, and every position mark is computed on 17-hour-old
candles while `/health` returns 200 and the dashboard shows a green "Live" dot.**
The trading engine's `current_price` for open positions is a stale close.

**DL-2 (CRITICAL) — every restart fabricates cash by erasing realized losses.**
`paper_trading.py:104` computes *initial minus currently-open margin* and never
applies realized P&L or any commission ever paid. Proof from the logs:

```
2026-07-30 20:12:38  ✓ SHORT closed: ETHUSDT ... Balance: $80.7027
2026-07-31 14:26:08  Adjusted balance: $83.48        <-- restart, zero trades between
2026-07-31 14:26:11  KillSwitch balance initialized: $83.48
```

Gap = **2.78133** = realized P&L 2.5737 + close commissions 0.10511 + open
commissions of the two closed legs 0.10254. Exact. An account bleeding toward
the 20% drawdown kill-switch threshold is reset toward par by any restart or
crash-loop, and the kill switch re-arms off the fabricated number. In LIVE this
silently disarms the drawdown circuit breaker.

Root cause is the same as DL-3: `portfolios.cash_balance` holds the correct
running ledger (80.70266802) but the value is fetched and discarded.

**DL-3 (CRITICAL) — two disjoint paper accounts that can never reconcile.**
trading-engine + Postgres use `portfolio_id='paper_trading'`.
portfolio-manager creates `portfolio_id='default'` **purely in memory**
(`portfolio_manager.py:54-62`) and never writes the `portfolios` table at all.

```
cryptobot=# SELECT portfolio_id FROM portfolios;                              -> paper_trading
cryptobot=# SELECT DISTINCT portfolio_id FROM portfolio.performance_history;  -> default
```

`performance_history` carries an orphan `portfolio_id` with no FK to enforce it.

**DL-4 (HIGH) — `portfolio-manager._fetch_current_price` always returns 0.**
`portfolio_manager.py:307` reads `data.get("last_price")` but the payload is
`{"success":true,"data":{"last_price":...}}` — the key is nested one level down.
Logs confirm three successful 200s followed by
`✓ Updated prices for 0 assets`. Consequence: `GET /api/v1/portfolio/balance`
reports `unrealized_pnl "0"` while `GET /api/v1/portfolio` reports `95.6986` —
same service, same portfolio, seconds apart.

**DL-5 (HIGH) — no mark-to-market writer; `positions.current_price` is frozen at
entry forever.** `position_manager.py:195 update_position_price` has **zero
callers** repo-wide.

```
 id | symbol  | entry_price    | current_price  | unrealized_pnl
 47 | BTCUSDT | 63556.10000000 | 63556.10000000 |     0.00000000
 49 | BNBUSDT |   593.60000000 |   593.60000000 |     0.00000000
 50 | ADAUSDT |     0.17230000 |     0.17230000 |     0.00000000
```

Mark-to-market exists only in memory, computed on read. The
`open_positions_summary` view therefore reports `total_unrealized_pnl = 0.00`
for every row.

**DL-6 (HIGH) — `remaining_quantity` has no DB column.** `\d positions` lacks
`remaining_quantity`, `tp1_hit/2/3`, `highest_price`, `lowest_price`. This is
the storage-level cause of T-4: after a TP1 partial close and a restart, the
position reloads at full original quantity while the cash from the partial exit
is also gone (DL-2).

**DL-7 (HIGH) — `portfolios.total_value` has no writer in any service.** The ORM
`Portfolio` class (`database/models.py:30-50`) has no `total_value` column at
all; `repositories.py:402-434 update_balance` writes only `cash_balance`,
`realized_pnl`, `updated_at`. The stored `100.00` is a fossil of a manual run of
the ad-hoc `sync_portfolio_pnl.sql`.

**DL-8 (HIGH) — the ORM `Trade` model is entirely incompatible with the live
table.** `database/models.py:180-215` declares `action`, `order_type`,
`total_cost`, `fee_currency`, `exchange_order_id`, `signal_indicators`,
`pnl_percentage`, `notes`, `created_at`, `position_id` — **none exist** live,
which uses `side`, `total_value`, `metadata`. Worked around by raw SQL at
`repositories.py:300-330`; the class stays loaded and any future ORM query
against it fails. `PortfolioSnapshot` (`models.py:267-270`) maps to
`portfolio_snapshots`, a table that does not exist.

**DL-9 (MEDIUM) — `tickers` has no `is_mainnet` column; 1690 pre-flip rows are
unfilterable.** Good news first — **`klines` is clean**, the documented repair
was applied and verified:

```
 is_mainnet | count  |        earliest        |         latest
 f          | 118574 | 2023-12-19 23:00:00+00 | 2026-04-25 23:59:00+00
 t          | 246497 | 2026-04-26 00:00:00+00 | 2026-07-30 22:21:00+00
 mainnet_rows_before_flip -> 0
```

`tickers` is the residual gap and no consumer can filter it.

**DL-10 (MEDIUM) — `performance_history` mixes two incompatible equity
formulas.** Row 10 (2026-05-22) uses the pre-fix spot formula and reports
`roi_percent -97.475`; row 11 (2026-07-30) uses the post-2026-07-29 margin
formula. The series is not comparable across the fix, so any Sharpe or drawdown
computed over it is garbage. The table also has a **69-day gap** despite a daily
scheduler.

**DL-11 (MEDIUM) — TimescaleDB has no compression and no retention policies.**
955 chunks on `klines`, `compression_enabled = f` on all. The
`add_retention_policy` calls in `database/schema.sql:537-541` target database
`crypto_trading_bot`, **which does not exist**.

### 4.5 Infrastructure and configuration

**I-1 (CRITICAL) — the canonical compose never passes `TRADING_MODE` to
trading-engine, so the documented LIVE procedure is a no-op for the engine.**
I verified this independently before the audit agent did:

```
$ docker exec crypto-bot-trading printenv | grep -E 'TRADING_MODE|PAPER'
PAPER_TRADING_MODE=true          # no TRADING_MODE line at all
```

`TRADING_MODE` appears in `docker-compose.unified.yml` only at `:290`, in the
**api-gateway** block. `PAPER_TRADING_MODE` is not a `Settings` field —
it appears in trading-engine only at `preflight/checks.py:144`, reachable only
when already LIVE. Order routing is gated **solely** on `settings.trading_mode`
(`auto_trader.py:1853, 1995, 2870, 3112`), which falls back to its `"PAPER"`
default.

Failure scenario, and the direction matters: the operator follows the four-step
procedure and sets `TRADING_MODE=LIVE`. api-gateway *does* receive it, flips into
LIVE-hardened auth, and reports LIVE via `/api/config/safety-state`. The trading
engine never sees the variable and silently stays in PAPER. **The operator
believes they are trading real money and are not.** Combined with T-3 (the
ensemble path routes through the paper engine regardless), there are now two
independent reasons a "LIVE" flip does not reach the exchange.

**I-2 (HIGH) — Kubernetes "production" gets a 10% per-trade cap, not 2%.**
`MAX_RISK_PER_TRADE` has **zero occurrences** anywhere under
`infrastructure/kubernetes/`. The deployment's four `envFrom` sources
(`trading-engine-deployment.yaml:187-193`) do not define it, so pydantic's
`default=0.10` (`config.py:321`) applies — in a namespace stamped
`ENVIRONMENT: "production"` (`:546`). That is 5× the non-negotiable LIVE cap,
with no code path that would reject it. Compounding this,
`trading-engine-deployment.yaml:590-600` embeds a `config.yaml` blob declaring
`risk_per_trade_pct: 2.0` that **nothing reads** — `grep -rn "config.yaml"
services/trading-engine/app/` returns nothing. An auditor reading the manifest
concludes the cap is enforced. It is not.

**I-3 (HIGH) — the headless deploy ships a permanently disengaged kill switch.**

```
docker-compose.headless.yml:293  EMERGENCY_STOP_FILE=${EMERGENCY_STOP_FILE:-/app/EMERGENCY_STOP}
docker-compose.headless.yml:322  - ./EMERGENCY_STOP:/app/EMERGENCY_STOP:ro
$ ls -la EMERGENCY_STOP  ->  No such file or directory
```

This is exactly the file-to-file bind CLAUDE.md says was replaced by the
`./safety/` directory mount. With the host file absent, Docker creates a
**directory** at the mount point, and the halt check is
`auto_trader.py:886  if self.emergency_stop_file.is_file()` — always False for a
directory. The broken-mount detector at `:860` logs `critical` once and does not
stop trading. Headless is the Cloudflare-tunnel remote deploy: an operator
touches the kill switch from a phone, sees no error, and the bot keeps trading.

**I-4 (HIGH) — a fresh volume cannot boot.** Only `01-init.sql`, `03`, and `04`
are mounted into `/docker-entrypoint-initdb.d` (`unified:46-48`); migrations
`001` and `002` are not. `infrastructure/scripts/init-db.sql` creates only
schemas and two audit tables — no `public.portfolios`. `003` then opens with an
unguarded `ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS` (`003:13`) — the
`IF EXISTS` guard is on the *column*, not the table — and the entrypoint runs
with `ON_ERROR_STOP=1`. On an empty volume the init aborts, postgres never
reaches healthy, and every service with `depends_on: service_healthy` never
starts. The live DB works only because 001/002 were applied by hand.

There is also **no migration tracking table** of any kind, so nothing can answer
"which migrations has this database seen."

**I-5 (HIGH) — ~2.3 GB of unrotated logs, still growing.** No rotation exists on
the unified/headless path (`logging:` appears only in `docker-compose.prod.yml`),
and `grep -rn "RotatingFileHandler|TimedRotating" services/*/app/` returns zero
hits. Measured now, both **larger** than the figures in `wiki/hot.md`:

```
crypto-bot-api-gateway    896M  /app/logs   (service.log 939,170,094 B, mtime Jul 31 15:35)
crypto-bot-portfolio      1.1G  /app/logs   (service.log 1,110,588,776 B, mtime Jul 31 15:36)
crypto-bot-risk-metrics   150M  /app/logs
crypto-bot-market-data    117M  /app/logs
crypto-bot-trading         12K  /app/logs
```

**I-6 (MEDIUM) — trading-engine writes no log file at all.**
`main.py:181` is a bare `logging.basicConfig(level, format)` with no handlers, so
everything goes to stdout, and `docker inspect` shows `json-file` with an **empty
config map** — no `max-size`, no `max-file`. The one service whose logs matter
for reconstructing why a trade fired keeps its entire history in an unbounded
Docker json log that `docker rm` / `up --force-recreate` destroys — and
`--force-recreate` is the WSL bind-mount fix CLAUDE.md prescribes as routine.

**I-7 (HIGH) — the test suite exists only in the container's writable layer; the
next rebuild deletes it.** This confirms operator item OP-15 and sharpens it.
`services/trading-engine/Dockerfile:71` copies `app/` only — there is no
`COPY tests/`. Yet the running container has `/app/tests` and `pytest.ini`,
**root-owned and post-dating the image** (image created 2026-07-29T03:16:35Z;
tests mtime Jul 30 22:21), and present in no mount. They were `docker cp`'d in by
hand. So the `.dockerignore` `tests/standalone/` entry is moot — nothing under
`tests/` reaches the image by *either* mechanism. The next
`docker compose build trading-engine` silently produces a container with no
`test_accounting_fixes.py` and no build error, making any prior "verified in
container" claim unreproducible.

**I-8 (MEDIUM) — three-way config drift across the compose files.**

| var | unified | docker-compose.yml | headless |
|---|---|---|---|
| MAX_RISK_PER_TRADE | `0.10` | `0.05` | `0.02` |
| MAX_POSITION_SIZE_PCT | `10.0` | `8.0` | unset → 10.0 |
| STRATEGY_MODE | `ensemble` | `hybrid` | `ensemble` |
| LEVERAGE_ENABLED | `true` | `true` | unset → **False** |
| DEFAULT_LEVERAGE | `10.0` | `10.0` | unset → **1.0** |
| EMERGENCY_STOP_FILE | `/app/safety/…` | (env_file) | `/app/EMERGENCY_STOP` |
| USE_DATABASE (portfolio-mgr) | `true` | **`false`** | `true` |

A "reproduce the bug" run started with the wrong file sizes positions 2–5×
differently and runs a different strategy stack, with nothing warning of it.
Headless silently disables leverage, dropping notional 10× to ~$2 — below Bybit
min-notional, so the remote deploy looks *idle* rather than misconfigured. And
`docker-compose.yml` runs portfolio-manager with the database off entirely.

### 4.6 Coverage gaps in this audit — stated honestly

Six parallel domain auditors were dispatched; **three died mid-run** on stream
stalls and were not retried a third time. Coverage is therefore uneven:

- **Complete:** trading pipeline, frontend, data layer, infra/config/migrations,
  injection/deserialization sweep.
- **Partial:** API auth/authorization — covered only via the injection sweep and
  the frontend agent's `auth_middleware.py` tracing (F-4). A route-by-route
  guard inventory was **not** completed.
- **Not done:** ML/AI subsystem (LSTM removal completeness, look-ahead leakage in
  feature construction, raw-R² consumers, model staleness) and the repo-wide
  dead-code/dependency/circular-import sweep. `sentiment-analysis-service`,
  `notification-service`, `bybit-connector`, and `technical-analysis` internals
  were not audited.

### 4.7 Documentation drift found incidentally

**DOC-1 — `services/` holds 12 services, not 11.** `tournament-harness` exists on
disk and is absent from the CLAUDE.md service table, which lists 11.

---

## 5. Files modified

All source edits routed through GSD quick task
`.planning/quick/260731-mxf-fix-paper-capital-reporting/`. **Nothing is
committed** — the project rule is to propose commit groupings and wait for
approval, and no approval was given.

| File | Change | Finding |
|---|---|---|
| `services/trading-engine/app/performance_tracker.py` | added `_default_initial_balance()` reading `get_settings().paper_initial_balance`; `__init__` default `Decimal("10000")` → `None`; singleton factory `or` → `is not None` | D-3 |
| `services/trading-engine/app/repositories.py` | `get_or_create(initial_balance=Decimal("10000"))` → `None`, resolved from config at call time | D-3 (defensive) |
| `frontend/src/utils/balance.js` | **new** — `toFiniteNumber()` + `PAPER_DEFAULT_BALANCE`, single source of truth | F-2/F-3 |
| `frontend/src/components/PortfolioCard.jsx` | `\|\| 10000` → `toFiniteNumber(...)`; `cashBalance` now falls back to the served `initial_balance` | F-2 |
| `frontend/src/components/KeyMetricsStrip.jsx` | `\|\| 100` → same shared helper, so the two tiles cannot disagree | F-2 |
| `frontend/src/hooks/usePerformanceMetrics.js` | baseline switched from `portfolioData.total_value` (current) to `performanceSummary.metrics.initial_balance` (starting) | F-1 |
| `frontend/src/services/analyticsApi.js` | `calculateEquityCurve` default `10000` → `100`, matching `:358` | F-3 |

**Why `is not None` rather than `or`:** the previous `or` meant an explicitly
passed `Decimal(0)` was silently replaced by the fallback. Verified fixed:
`PerformanceTracker(Decimal(0)).initial_balance` now returns `0`.

Not mine — already dirty at session start: `main.py`, `models/signal.py`,
`preflight/checks.py`, the three `strategies/*.py` files, and their tests.

### Verification

```
Backend  before: 36 failed, 1449 passed, 842 skipped
Backend  after:  36 failed, 1449 passed, 842 skipped     -> no regression

Frontend before: 51 failed, 134 passed (5 files)   [measured by stashing my changes]
Frontend after:  51 failed, 134 passed (5 files)   -> no regression
```

All 5 failing frontend files live in the dead-code tree (F-8). Backend defaults
verified directly:

```
config paper_initial_balance = 100.0
singleton (bare call)        = 100.0
bare PerformanceTracker()    = 100.0
explicit Decimal(0) honored  = 0
```

**Not deployed.** The frontend container was deliberately not rebuilt and the
trading engine was deliberately not restarted — see §6.

---

## 6. Remaining risks and recommendations

### 6.1 Why the trading engine was not restarted

A restart is itself a state-corrupting operation on the exact accounting this
audit measured:

- **DL-2 / T-9** — `paper_trading.py:104` rebases the balance, erasing realized
  P&L (proven: an unexplained +2.78133 across the 14:26 restart).
- **T-8 / DL-5** — `opened_at` is not restored, so all three open positions get a
  fresh 48h max-hold clock.
- **T-4 / DL-6** — `remaining_quantity` resurrection on partially exited
  positions.

Deploying the backend change requires an engine restart, which would destroy the
evidence above and mutate the live book. **That is the operator's call.** If you
want it deployed: `touch safety/EMERGENCY_STOP`, snapshot
`portfolios`/`positions`/`trades` first, and be aware that the file kill switch
stops position monitoring entirely (T-14) — so keep the window short or close the
three positions deliberately first.

The frontend change is independent and can ship with
`docker compose -f docker-compose.unified.yml up -d --build frontend`.

### 6.2 Found, deliberately NOT fixed — pre-live blockers

These are real CRITICALs. They are latent because the system is in paper mode,
and each is a risk-cap or auth change that should not be patched mid-audit on a
running engine. **Do not read the list in §4 as "addressed."**

| ID | Blocker | Why not now |
|---|---|---|
| **T-2** | Deployed ensemble path enforces no per-trade cap; the 2% LIVE cap is unreachable, and where it does exist it clamps *margin*, so at 10× it is 20% notional | risk-cap change on a live engine |
| **T-3** | Ensemble path routes through the paper engine even in LIVE | **must land after T-2** — fixing it alone converts a reporting bug into a real-money 20%-notional breach |
| **I-1** | `TRADING_MODE` never reaches trading-engine; a LIVE flip silently stays PAPER while the gateway reports LIVE | compose change with LIVE-path blast radius |
| **I-2** | k8s "production" runs a 10% cap because `MAX_RISK_PER_TRADE` is absent | k8s manifest change, unverifiable from here |
| **T-7** | Daily-loss breaker uses the $100 paper constant as its base in LIVE | risk-cap change |
| **F-4** | No login flow; flipping to LIVE makes the UI kill switch return 401 | needs an auth design decision |
| **I-3** | Headless kill switch is permanently disengaged (dir-vs-file bind) | affects the remote deploy |

**Required ordering: T-2 → T-3.** Nothing else should be flipped to LIVE until
all seven clear.

### 6.3 Fix next, in this order

1. **DL-1 — market-data ingest is dead.** Highest operational priority. As of
   15:35 on 2026-07-31, every signal was being computed on candles ~17 hours
   stale (newest row 2026-07-30 22:22) with all health checks green — and that
   gap grows with wall-clock until ingest restarts.
   Add a staleness guard that fails `/health` (or at minimum
   refuses to serve a stale row as current) rather than only fixing the
   scheduler — the silent-success mode is the real defect.
2. **DL-2 — restart rebases the balance.** Read `portfolios.cash_balance`
   instead of recomputing from `initial_balance`. The correct ledger is already
   in the DB and is being discarded.
3. **T-1 / DL-3 — collapse the three balance formulas to one.** Decide whether
   equity includes posted margin, implement it once, and have
   `handlers/performance.py:79` and portfolio-manager both consume it.
4. **DL-5 — wire up `update_position_price`;** it has zero callers, so
   `positions.current_price` is frozen at entry in the DB forever.
5. **I-4 — make a fresh volume bootable** and add a migration-tracking table.
   Right now disaster recovery does not work.
6. **D-4 — un-skip the risk-manager and paper-trading unit tests** (48 tests).
   These cover exactly the modules everything above depends on.
7. **I-5 / I-6 — log rotation**, and give trading-engine a real file handler.

### 6.4 Standing risks

- **Strategy profitability is still unproven**, and this audit found nothing to
  change that. The bot executed **0 trades in 400 signal checks** during the
  observation window (T-28). Any DSR/CPCV evaluation must wait for clean paper
  data — which cannot begin until DL-1 and DL-2 are fixed, since the current
  price feed is stale and the balance resets on every restart.
- **Gross exposure is uncapped** (T-6): 163% notional on a $100 account today,
  with `max_total_exposure_pct=80.0` configured but unreachable.
- **The audit's own coverage is incomplete** — see §4.6. ML/AI and the dead-code
  sweep were not done.

### 6.5 Documentation corrections needed

- CLAUDE.md lists **11 services**; there are **12** (`tournament-harness`).
- `wiki/hot.md` says **9** trading-engine test failures; the real number is **36**.
- `wiki/hot.md` log sizes (834 MB / 941 MB) understate the current
  939 MB / 1.11 GB.
- CLAUDE.md's four-step LIVE procedure is **wrong as written** — step 2
  (`TRADING_MODE=LIVE`) does not reach the trading engine at all (I-1).

---

## 7. DL-1 root cause and fix (market-data ingest)

Quick task: `.planning/quick/260731-nx4-fix-market-data-ingest/`

### 7.1 Why it looked healthy

`/api/v1/scheduler/status` reported `"running": true` with all three jobs
registered and future `next_run` times. `/health` returned 200. The service was
visibly serving reads. Nothing in any status surface indicated a problem —
which is why 17 hours of dead ingest went unnoticed.

### 7.2 Root cause A (the actual blocker) — every run silently discarded

`scheduler.py:216-245` registered all three jobs with **no
`misfire_grace_time`**. APScheduler's default is **1 second**. This service
serves heavy kline read traffic from technical-analysis, so every fire slipped
past its 1-second deadline and APScheduler *dropped the run* rather than
executing it:

```
Run time of job "Ticker Data Collection ..."      was missed by 0:00:16.899979
Run time of job "Kline Data Collection ..."       was missed by 0:00:02.107381
Run time of job "Hourly Full Data Collection ..." was missed by 0:00:14.086112
```

Every fire, indefinitely. This is a silent-success failure mode: the scheduler
is genuinely running and genuinely healthy; it simply never executes anything.

### 7.3 Root cause B — two schedulers, one per uvicorn worker

```
$ docker inspect crypto-bot-market-data --format '{{.Config.Cmd}}'
[python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --workers 2]
```

`--workers 2` forks two processes, each running `start_scheduler()` in its own
lifespan. The `if _scheduler is not None` guard at `scheduler.py:206` is
per-process and cannot see its sibling, so all three jobs were registered twice
(confirmed: paired log lines with distinct `taskName`, and 6
"Scheduler started successfully" across 3 boots). Not corrupting — klines use
`on_conflict_do_update` (`repository.py:71`) — but it doubled Bybit API load,
duplicated ticker rows, and worsened the event-loop contention driving A.

### 7.4 Proof the collection code was never the problem

```
$ curl -X POST http://localhost:8002/api/v1/collect/ticker/BTCUSDT
{"success":true,"message":"Ticker data saved","data":{"symbol":"BTCUSDT","last_price":"62848.40",...}}

market_data=# SELECT symbol, last_price, to_timestamp(created_at/1000) FROM tickers ORDER BY created_at DESC LIMIT 2;
 BTCUSDT | 62848.40000000 | 2026-07-31 16:11:55+00
 POLUSDT |     0.07125000 | 2026-07-30 22:10:27+00   <- previous newest row
```

Note the live price **62,848.40** against the **64,706.6** the trading engine
was marking BTC positions at — a **~2.9% divergence on a live book**, and the
unrealized P&L reported for all three open positions was computed against the
stale figure.

### 7.5 Fix

`services/market-data-service/app/scheduler.py`:

1. `misfire_grace_time` + `coalesce=True` on all three jobs (240 s for the
   5-minute jobs, 1800 s for the hourly backup). A busy loop now *delays* a
   collection instead of cancelling it; `coalesce` collapses a backlog into one
   run rather than firing N catch-ups.
2. `_claim_scheduler_ownership()` — an `flock` on a shared path elects exactly
   one scheduler owner regardless of worker count. Chosen over dropping to
   `--workers 1` because this service is read-heavy and the second worker
   carries real traffic. The lock releases on process death, so a crashed owner
   is replaced on the next boot rather than leaving ingest permanently dead.
3. `get_scheduler_status()` now reports `scheduler_owner` and `pid`, so a
   non-owner worker answering the round-robin probe cannot be misread as
   "ingest is down".

One bug found in my own fix during verification: re-claiming from the same
process opened a second fd, and `flock` is per open-file-description, so a
`start → stop → start` cycle via the `/api/v1/scheduler/*` endpoints would have
locked the service out of its own scheduler. Guarded by an early return when
`_owner_lock_fd` is already held.

### 7.6 Verification

```
Baseline: 9 failed, 186 passed, 278 skipped
After:    9 failed, 186 passed, 278 skipped        -> no regression
```

Deployed with `docker compose -f docker-compose.unified.yml up -d --build
market-data`. **The trading engine was not restarted.** Post-deploy:

```
$ docker logs crypto-bot-market-data | grep -c "Scheduler started successfully"
1                                    # was 2 per boot

$ curl -s http://localhost:8002/api/v1/scheduler/status
{"running":false,"jobs":[],"job_count":0,"scheduler_owner":false,"pid":9,
 "detail":"This worker does not own the scheduler; another worker runs collection."}
                                     # pid 9 correctly declines; pid 8 owns it
```

### 7.7 Still outstanding for this defect

The staleness guard remains **unfixed**: market-data will still serve an
arbitrarily old row as current with `"source":"database"` and a green `/health`.
The scheduler is repaired, but the *silent-success* property that hid it for 17
hours is intact. Until a freshness assertion exists, this class of failure
remains undetectable. Recommended as the next change on this service.

### 7.8 Confirmed working — real data, not an HTTP 200

The scheduled 5-minute jobs fired on their own and wrote to both tables:

```
market_data=# SELECT symbol, last_price, to_timestamp(created_at/1000) AS written
              FROM tickers ORDER BY created_at DESC LIMIT 5;
 symbol  | last_price  |        written
---------+-------------+------------------------
 POLUSDT |  0.07061000 | 2026-07-31 16:28:26+00
 LTCUSDT | 44.73000000 | 2026-07-31 16:28:26+00
 DOTUSDT |  0.75850000 | 2026-07-31 16:28:26+00
 APTUSDT |  0.56250000 | 2026-07-31 16:28:26+00
 SUIUSDT |  0.68500000 | 2026-07-31 16:28:25+00

market_data=# SELECT to_timestamp(max(created_at)/1000), count(*) FILTER (...) FROM klines;
   newest_kline_write   | new_rows
------------------------+----------
 2026-07-31 16:28:42+00 |     6915
```

Misfire count since the fix:

```
$ docker logs crypto-bot-market-data | grep -ci "missed by"
0
```

Previously **every** fire was missed. Ingest is live again after ~18 hours dead.
The price feed the trading engine reads is now current.

**Sustained, not a one-off.** Two consecutive scheduled cycles fired 5 minutes
apart, with the misfire count still at zero:

```
        batch        | count
---------------------+-------
 2026-07-31 16:33:2x |    14      <- second cycle, on schedule
 2026-07-31 16:28:2x |    14      <- first cycle after the fix

$ docker logs crypto-bot-market-data | grep -ci "missed by"
0
```

Owner election stable across both cycles: pid 8 reports `scheduler_owner: true`
with future `next_run` times; pid 9 declines cleanly.

---

## 8. DL-2 / T-8 root cause and fix (restart cash fabrication)

Quick task: `.planning/quick/260731-ooe-fix-restart-balance-rebase/`

### 8.1 Why "just read cash_balance" was the wrong fix

The obvious repair — seed from the persisted `portfolios.cash_balance` — is
incomplete. That column is written **only on position close**
(`position_manager.py:348`, inside `close_position`), never on open. So it is
accurate as of `portfolios.updated_at`; any position opened after that write has
had its margin debited in memory but never persisted. Seeding blindly from it
would have *under*-counted instead of over-counting.

Correct reconstruction:

```
balance = portfolios.cash_balance
          - (margin + commission) for positions opened AFTER portfolios.updated_at
```

### 8.2 That made T-8 a prerequisite, not a separate nicety

The reconstruction needs a real `Position.opened_at`, and
`position_manager.py:782-792` never restored it — the model's
`default_factory=now()` won, so every position reported the restart time:

```
DB:  826f5b17... opened_at 2026-07-29 20:00:42.322091
API: "opened_at": "2026-07-31T14:26:08.069372Z"     <- restart time
```

Both `opened_at` and `realized_pnl` exist in the live schema and were simply not
read. Independently of DL-2 this defeats the 48h max-hold force-close
(`auto_trader.py:2429-2430`): a position survives indefinitely as long as the
service restarts inside each window — the 185h SOLUSDT failure the Jan 2026 fix
(`380a674`) was written for.

### 8.3 Changes

1. `position_manager.load_positions_from_db` — restore `opened_at` and
   `realized_pnl`. Added `_as_utc()` because both columns are
   `timestamp without time zone`, so SQLAlchemy returns naive datetimes and
   comparing them against `datetime.now(timezone.utc)` raises `TypeError`.
2. `paper_trading.sync_balance_with_positions` — now `async`; seeds from the
   persisted ledger and deducts only post-write positions. Retains the old
   reconstruction as a fallback when the portfolio row is unreadable, but logs
   it at ERROR — that path fabricates cash and must never be silent.
3. `lifespan/data.py:61` — `await` the now-async call.

### 8.4 Magnitude

For the live book's shape, the two formulas differ by **$14.25 on a $100
account**:

```
OLD formula (initial - cost)   = 94.95
NEW formula (persisted ledger) = 80.70266802
cash invented by OLD           = 14.24733198
```

### 8.5 Verification

Added `tests/unit/test_restart_balance_restore.py` — 7 tests covering: restore
from the persisted ledger, deduct only post-write positions, loud fallback when
the ledger is unreadable, naive-timestamp handling, and `_as_utc` itself. The
first test pins `94.95` explicitly so a regression to the par-based
reconstruction fails rather than passing on a near-miss.

One defect found in my own test during review: the guard assertion used `5.005`
where the real cost is `5.05`, which made it vacuous. Corrected.

**Not deployed.** Deploying needs a trading-engine restart, which mutates the
live paper book. The fix makes future restarts safe, and the restart that
deploys it will already run the new logic — but it remains the operator's call.

### 8.6 Still outstanding

`remaining_quantity`, `tp1_hit/2/3`, `highest_price` and `lowest_price` are
**not columns in the live `positions` table** (DL-6), so partial-exit state
still cannot survive a restart — T-4 (resurrected quantity crediting margin that
was never posted) is therefore **not** fixed by this change. It needs a
migration.

---

## 9. Market-data staleness guard (DL-1 §7.7 follow-up)

Quick task: `.planning/quick/260731-ps1-market-data-staleness-guard/`

`66779e2` fixed *why* ingest stopped. This fixes *why nobody noticed for 17
hours*.

### 9.1 The deeper bug: a stale row blocked its own repair

`handlers/query.py` only reached its live-fetch fallback when there was **no
row at all**:

```python
ticker = await TickerRepository.get_latest_ticker(symbol)
if not ticker:
    ticker_data = await fetcher.get_ticker(symbol)   # live fallback
    ...
return {"data": ticker.to_dict(), "source": "database"}
```

Any row — however ancient — short-circuited it. The stale row was therefore both
the wrong answer *and* the reason the right answer was never fetched. Had age
been checked, the 17-hour outage would have **self-healed on the first read**.

### 9.2 Changes

1. **A stale stored row is now a cache miss.** It falls through to the live
   fetch and is persisted, exactly as a missing row would be. Self-healing.
2. **No age is served without being disclosed.** Ticker responses carry
   `age_seconds` and `is_stale`. If the live re-fetch also fails, the stale row
   is still served — better than a 500 — but flagged in the payload and logged
   at ERROR.
3. **`/ready` reports data freshness**, 503-ing when ingest has stalled, via a
   new `TickerRepository.get_newest_row_age_seconds()` (one indexed `MAX`).
4. Budget is `MARKET_DATA_STALENESS_SECONDS`, default **900 s** — three missed
   5-minute cycles, i.e. unambiguous failure rather than jitter.

### 9.3 Why `/ready` and deliberately NOT `/health`

`docker-compose.unified.yml:459` wires the container healthcheck to `/health`,
and `:552-554` declares **trading-engine `depends_on: market-data:
service_healthy`** (ml-prediction likewise at `:757`). Failing `/health` on
stale data would stop the trading engine from *booting* — the wrong failure
mode. Stale prices should make a consumer refuse to **trade**, not refuse to
**start**; and a process that is answering requests is, by definition, live.

Nothing in any compose file consumes `/ready`, so this carries no boot-ordering
blast radius while still giving Prometheus and operators a real signal.

### 9.4 Verification

```
Baseline: 9 failed, 186 passed, 278 skipped
After:    9 failed, 197 passed, 278 skipped     -> same failures, +11 new tests
```

Deployed (market-data only; trading engine untouched and still `Up 3 hours
(healthy)`):

```
$ curl -s localhost:8002/ready
{"status":"ready","bybit_connector":"ok",
 "data_freshness":{"ok":true,"newest_row_age_seconds":148.1,"budget_seconds":900}}   HTTP 200

$ curl -s localhost:8002/health
{"status":"healthy",...}                                                             HTTP 200

$ curl -s localhost:8002/api/v1/ticker/BTCUSDT
{... "last_price":63017.6, "source":"database",
     "age_seconds":190.5, "is_stale":false}

$ docker inspect crypto-bot-market-data --format '{{.State.Health.Status}}'
healthy
```

### 9.5 Still outstanding

The **consumer side**: the trading engine does not yet refuse to trade on stale
prices. It can now *see* staleness (`is_stale` on every ticker read) but nothing
acts on it. That belongs in trading-engine and interacts with the open-position
marking path — filed, not done here. Klines carry the same defect shape but a
different cache contract; also deferred to keep this change reviewable.

---

## 10. D-4 — restoring risk-manager and paper-trading coverage

Quick task: `.planning/quick/260731-d4-restore-risk-test-coverage/`

### 10.1 Why this before T-1 or T-4

Two reasons, both about ordering rather than tidiness:

1. `22285ae` changed `paper_trading.sync_balance_with_positions` — accounting
   logic — **in a module whose unit tests were switched off**. Shipping into an
   untested module is how the original defects got in.
2. **T-2 is the largest money risk in this audit** (deployed ensemble path
   enforces no per-trade cap). Changing risk caps with zero risk-manager
   coverage is not defensible. This is its prerequisite.

Zero deployment risk — no production file was touched.

### 10.2 What the blanket skip was actually hiding

Removing both `pytestmark` markers and running gave **36 passed / 11 failed**.
The skip was disabling **36 working tests to hide 11 broken ones**, and not one
of the 11 was a bug in production code:

| Cause | Count |
|---|---|
| Stale $10,000 scaling | 6 |
| Fixture predating leverage (`Decimal(str(Mock))` → `InvalidOperation`) | 4 |
| Obsolete long-only assertion | 1 |

The sharpest example is `test_calculate_position_size_basic`: it passes
`account_balance=Decimal("100.00")` and asserted `0.02 BTC` — the answer for a
$10,000 account. The risk manager correctly returned `0.0002`. Likewise the
daily-loss tests fed a **$200 loss to a $100 account** (a 200% loss) and then
asserted the 5% breaker had *not* fired. The risk manager was right every time;
the expectations were stranded by the same $10,000 → $100 migration that this
whole audit keeps rediscovering.

### 10.3 One test rewritten rather than rescaled

`test_execute_sell_order_no_position` asserted that a SELL with no open position
fails with "No open LONG position" — long-only behaviour that SHORT enforcement
(`380a674`) made obsolete. Replaced with two tests covering current intent:

- a plain SELL with no position **opens a SHORT**;
- a `reduce_only` SELL with no position is **rejected** — the property that stops
  a stop-loss exit flipping into a brand-new counter-trade (the bug the
  2026-07-28 overhaul fixed).

### 10.4 Verification

```
Baseline: 36 failed, 1456 passed, 842 skipped
After:    37 failed, 1503 passed, 795 skipped
```

Passed **+47**, skipped **−47** — exactly the restored tests.

The extra failure is `test_signal_cache.py::test_cache_entries_isolated`, and it
is **pre-existing flakiness, not a regression**: a wall-clock test with
`ttl_seconds=2` and a 0.1 s margin, so `sleep()` overshoot under load can age
`key2` past its TTL. It passes 3/3 in isolation. This change adds ~90 s of
runtime, which raises the odds of tripping it. Filed, not fixed — a timing test
with that margin should use a fake clock.

### 10.5 What this unblocks

T-2 can now be attempted with the risk manager under test. That remains an
operator decision (it is a risk-cap change on a running engine, and **T-2 must
land before T-3**), but the precondition that made it irresponsible is gone.
