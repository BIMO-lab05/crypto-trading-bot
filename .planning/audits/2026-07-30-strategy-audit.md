# Strategy Audit — 2026-07-30

Mode: `/trading-strategy-dev` audit branch (verify existing strategies; no code changed).
Stack state: 13 containers up ~6h, `STRATEGY_MODE=ensemble`, `AUTO_TRADING_ENABLED=true`, `PAPER_TRADING_MODE=true`, no `safety/EMERGENCY_STOP`.
Code provenance: `md5sum` on `coordinator.py`, `aggregator.py`, `base.py` — container `/app/app/strategies/` **matches** the worktree. File lists identical (27 entries). All `file:line` citations below are valid against the running image.

---

## Verdict per check

| # | Check | Result |
|---|---|---|
| 1 | Dispatch set identified from 3 independent sources | PASS |
| 2 | Coordinator / aggregator wiring reachable | **FAIL** — dead infra, not in live path |
| 3 | Unit test sweep — trading-engine (in-container) | **FAIL** — 28 failed / 1386 passed / 628 skipped, + 4 collection aborts |
| 3b | Unit test sweep — technical-analysis (host; image ships no tests) | **FAIL** — 3 failed / 453 passed |
| 4 | Backtest on validated symbols | **N/A** — no harness exercises the live ensemble path |
| 5 | Live engine sanity (loop, signals, risk) | PASS with defect (see F-1) |
| 6 | Risk caps bind | PARTIAL — paper binds; **LIVE path breaks** (F-2, F-3) |

No aggregation to "working". F-1 and F-2 are blocking.

---

## F-1 — HIGH — Two of three ensemble legs are permanently dead; live bot took BUYs where a working ensemble fires SELL

**What.** `MultiStrategyEnsemble` is documented and logged as a 3-leg performance-weighted vote (`simple_rsi`, `multi_indicator`, `mean_reversion`). In practice only `multi_indicator` — a passthrough of the CoreAggregator output — ever votes.

**Evidence — 6h of live logs, zero exceptions:**

```
$ docker compose -f docker-compose.unified.yml logs --since 6h trading-engine \
    | grep -oE "legs=\{[^}]*\}" | sort | uniq -c
    126 legs={'multi_indicator': 'BUY'}
```

126/126 fired signals, one leg, all BUY. `simple_rsi` and `mean_reversion` appear zero times.

**Root cause — a field-vs-metadata contract mismatch.**

`services/trading-engine/app/signal_aggregator.py:90-97` builds the RSI indicator with the numeric value in the **`value` field**, and a metadata dict that does not contain it:

```python
return IndicatorSignal(
    name="RSI",
    signal=SignalAction(data["signal"]),
    confidence=data["confidence"],
    value=data["rsi"],                      # <-- value lives here
    metadata={"period": period, "weight": 1.0},   # <-- and NOT here
)
```

Both dead legs read it from `metadata`:

- `app/strategies/simple_rsi_strategy.py:53-56` — `rsi = rsi_sig.metadata.get("value")`; `if rsi is None: return None`. Hard bail, every call.
- `app/strategies/mean_reversion_strategy.py:125` — `rsi_value = rsi_signal.metadata.get('value', 50.0)`. **Silently defaults to 50.0** (perfectly neutral RSI), so the leg never sees oversold/overbought. Same pattern at line 139: Bollinger reads `metadata.get('position', 0.5)`, and BB metadata carries `upper_band/middle_band/lower_band` — no `position` key — so that defaults to dead-neutral too. The leg computes from all-neutral inputs and never clears its threshold.

The `mean_reversion` case is the worse of the two: it fails open into a neutral vote rather than erroring.

**Proven live, 3 symbols, from inside the running container:**

```
RSI:             .value=77.95   .metadata.get('value')=None
BOLLINGER_BANDS: .value=0.1727  .metadata.get('position')=None
SMA:             .value=0.1659  .metadata.get('value')=None
-> simple_rsi leg: None
-> mean_rev  leg: None      (identical for ADAUSDT, BNBUSDT, SOLUSDT)
```

**Trading impact — sign inversion, with positions open right now.** Live RSI(9) @1h at audit time, against what the ensemble actually did:

| Symbol | RSI(9) | RSI leg *would* vote | multi_indicator voted | weighted_score | With RSI leg restored | Live bot did |
|---|---|---|---|---|---|---|
| ADAUSDT | 77.95 | SELL @ conf 0.6885 | BUY @ 0.174 | **−0.1715** | **SELL** | **BUY** |
| BNBUSDT | 79.34 | SELL @ conf 0.7302 | BUY @ 0.2014 | **−0.1763** | **SELL** | **BUY** |

Arithmetic uses the shipped constants: equal weights 1/3 (both dead legs sit at `DEFAULT_WIN_RATE` forever — they never trade, so their performance weights never update), `AGGREGATION_THRESHOLD=0.10`, `MIN_AGREEING_LEGS=1`, and the real overbought confidence ramp at `simple_rsi_strategy.py:81-83`. Both scores clear the threshold, so the restored ensemble *fires*, in the opposite direction.

Scope of that counterfactual: it restores the **RSI leg only** — `mean_reversion` is left dead, exactly as it runs today. A full three-leg simulation was not run. The direction is conservative: at RSI 78–79 a working mean-reversion leg would also lean SELL, pushing the score further negative, not back toward BUY.

Both symbols have open positions from those BUYs (`trades` rows 2026-07-30 17:38 BNB, 19:33 ADA).

**Secondary consequence.** `StrategyPerformanceWeights` (weights persisted to `/app/data/ensemble_weights.json`) can only ever learn about `multi_indicator`. The performance-weighting machinery is inert.

---

## F-2 — HIGH — LIVE-mode per-trade cap is breached by the ensemble sizing floor; boot preflight does not catch it

`app/strategies/multi_strategy_ensemble.py:296-299`:

```python
cap   = self.MAX_POSITION_PCT              # = settings.max_risk_per_trade
floor = _settings.ensemble_min_position_pct
scaled = confidence * cap * _settings.ensemble_confidence_size_multiplier
position_size_pct = max(floor, min(cap, scaled))
```

`max(floor, ...)` is applied **after** the cap clamp, so whenever `floor > cap` the floor wins and the cap is discarded. Today `ensemble_min_position_pct` defaults to **0.05** (`app/config.py:341`) and the LIVE-strict cap is **0.02**.

Simulated in-container across the confidence range:

```
LIVE conf=0.05  scaled=0.0037 -> size=0.0500 (5.0%)  BREACH=True
LIVE conf=0.15  scaled=0.0111 -> size=0.0500 (5.0%)  BREACH=True
LIVE conf=0.27  scaled=0.0200 -> size=0.0500 (5.0%)  BREACH=True
LIVE conf=0.50  scaled=0.0370 -> size=0.0500 (5.0%)  BREACH=True
LIVE conf=1.00  scaled=0.0740 -> size=0.0500 (5.0%)  BREACH=True
```

Every LIVE ensemble trade would size at 5% — 2.5× the non-negotiable 2% cap — at *any* confidence.

**The gate does not catch it.** Both the boot refusal (`app/main.py:284-292`) and `app/preflight/checks.py:73-101` (`check_cap`) validate only `settings.max_risk_per_trade <= 0.02`. Neither inspects `ensemble_min_position_pct`. A LIVE flip with correct `MAX_RISK_PER_TRADE=0.02` boots clean, logs `LIVE preflight cap check passed`, and then trades at 5%.

**Leverage compounds it.** `LEVERAGE_ENABLED=true`, `DEFAULT_LEVERAGE=10.0`. `app/auto_trader.py:4236-4237` computes `position_value = balance * position_size_pct * leverage`. The cap governs *margin*, not notional. Verified against the DB — ADA margin 6.44% of ~$78 → `total_value = 50.35` notional, i.e. 10×. In LIVE, the 5% floor would become ~50% notional exposure per trade.

Paper mode is currently safe on this axis: cap 0.10 > floor 0.05, and live log sizes were 6.44% / 7.45%, under cap.

---

## F-3 — MEDIUM — Daily-loss circuit breaker is measured against `paper_initial_balance` in every mode

`app/risk_manager.py:84`:

```python
max_loss = Decimal(str(self.settings.paper_initial_balance)) * Decimal(str(self.settings.max_daily_loss_pct / 100))
```

No `trading_mode` branch. CLAUDE.md states the 5% daily-loss breaker binds *always*. In LIVE this halts at 5% of the hardcoded paper balance ($100 → $5), not 5% of real equity — the breaker would trip almost immediately on a funded account, or, with a larger `PAPER_INITIAL_BALANCE` left in the env, far too late. Same failure class as F-2: preflight passes, LIVE behavior is wrong.

The breaker *does* bind in paper: `auto_trader.py:4170` calls `risk_mgr.should_halt_trading()` inside `_check_and_trade_ensemble`, and `position_manager.py:309,394,585` feed realized P&L via `update_daily_pnl`. Observed live: `app.risk_manager - INFO - Daily P&L updated: -1.2550000068874400`. The 2026-07-28 UTC-day-rollover fix (`_roll_daily_window_if_needed`, lines 44-57) is present and correct.

**Config divergence, related:** the `portfolios` DB row carries `risk_per_trade = 0.0200` / `max_daily_loss = 0.0500` while the engine runs `max_risk_per_trade = 0.10`. The engine ignores the DB values. Two sources of truth, disagreeing.

---

## F-4 — MEDIUM — `app/strategies/coordinator.py` + `aggregator.py` are dead infrastructure (1,862 lines)

The skill runbook assumes the coordinator is the dispatch point. It is not. `coordinator.py` imports only `base` and `aggregator` — no concrete strategy. Its `register_strategy` is called from a docstring example (`coordinator.py:223-224`), from tests, and from the *separate* `app/orchestration/` subsystem — never from the live path.

Both files were checked for importers independently. Across all of `app/`, the only references are the barrel: `app/strategies/__init__.py:140` (`from .aggregator import ...`) and `:152` (`from .coordinator import ...`). `aggregator.py`'s sole non-barrel importer is `coordinator.py:29` — itself dead. Nothing in the live path reaches either. (Do not confuse `app/strategies/aggregator.py` with `app/aggregation/aggregator_core.py`, which *is* live and supplies the `multi_indicator` leg.)

Actual live dispatch: `app/auto_trader.py:952-957` switches on `StrategyMode`, and with `STRATEGY_MODE=ensemble` calls `_check_and_trade_ensemble` (`auto_trader.py:4158`), which lazily imports `multi_strategy_ensemble` at line 4165.

**Never imported anywhere in `app/`** — not even by the `app/strategies/__init__.py` barrel:

- `enhanced_breakout_strategy.py`
- `enhanced_grid_trading_v2.py`
- `multi_indicator_strategy.py`

Reachable only via the barrel (`__init__.py`), no runtime caller: `breakout.py`, `mean_reversion.py`, `trend_following.py`, `arbitrage.py`, `grid_trading_strategy_v2.py`, `momentum_breakout_strategy.py`, `support_resistance_strategy.py`, `trend_following_strategy.py`. Note the duplicate pairs — `mean_reversion.py` vs `mean_reversion_strategy.py`, `trend_following.py` vs `trend_following_strategy.py` — where only the `_strategy` variant is live.

---

## F-5 — MEDIUM — Test suite cannot run as documented; 28 failures are pollution/env, not defects

CLAUDE.md documents `pytest tests/`. In-container that aborts at collection:

```
tests/integration/conftest.py:47: ModuleNotFoundError: No module named 'database'
```

The `database/` package sits at the repo root and is not shipped into the trading-engine image. Excluding `tests/integration` surfaces three more collection aborts: `test_bybit_adapter_wr01_wr04.py` and `test_exchanges.py` (`ModuleNotFoundError: No module named 'jwt'` via `app/exchanges/coinbase.py:33`), and `test_config_default_on_gate.py` (`IndexError: 3` at collection).

With those four excluded: **28 failed, 1386 passed, 628 skipped**. All 28 categorized, none a strategy-logic defect:

- **21 × `tests/unit/test_repositories.py`** — all 21 pass when the file runs alone (`pytest tests/unit/test_repositories.py` → 21 passed in 0.73s). Order-dependent suite pollution, not a defect in the code under test.
- **5 × `test_run_extended_backtest_divergence_warning.py`** — `FileNotFoundError: /app/run_extended_backtest.py`. Repo-root script not in the image.
- **2 × `test_bybit_adapter_contract.py`** — hardcoded absolute path `/services/trading-engine/app/exchanges/bybit_adapter.py`, invalid inside the container.

Targeted sweep of the strategy + risk suites is clean: `tests/strategies tests/risk` → **253 passed, 42 skipped**. The 42 skips are `test_kelly_persistence.py` (4) and `test_kelly_position_sizing.py` (38), both marked *"stale tests after PR #86 refactor; needs rewrite"* — Kelly sizing currently has no live test coverage. `tests/unit/test_risk_manager.py` (32) carries the same stale-skip marker.

### technical-analysis suite

Runbook step 3 also names `services/technical-analysis/tests/`. Two things there:

**The TA image ships almost no tests.** `docker exec crypto-bot-ta ls /app/tests/` returns a single entry, `standalone/`, and `pytest tests/` inside the container collects **zero** tests. The host tree has 22 test files (`tests/unit/`, `tests/integration/`, and 12 top-level modules). The TA suite therefore cannot be run in-container at all — unlike api-gateway, where in-container is *mandatory* per CLAUDE.md.

**Run on host: 3 failed, 453 passed** (`python3 -m pytest tests/ -q`). The three:

- `test_comprehensive_80.py::TestMarketDataFetcherDataFrame::test_get_klines_as_dataframe_success` and `::_empty` — `app/fetcher.py:176,234` now *raises* on insufficient/empty klines (`"refusing to compute indicators on insufficient data"`). The tests still expect the older lenient return. Stale tests trailing a deliberate hardening.
- `test_signal_aggregator_confidence_zero.py::test_empty_signal_list_returns_neutral_fallback` — `AssertionError: Expected neutral-fallback confidence=0.5; got 0.0`. Not classified: this is either a stale expectation or a real regression in the neutral-fallback path. Worth a look on its own merits — it sits on the same aggregator surface as F-1.

---

## F-6 — LOW — Dead ADR reference in `run_extended_backtest.py`

`services/trading-engine/run_extended_backtest.py:25,76,633` cite `docs/decisions/ADR-012-extended-backtest-disposition.md`. That directory no longer exists; the ADR was renumbered into the wiki as `wiki/decisions/ADR-027-extended-backtest-disposition.md` on 2026-07-30. The five `test_run_extended_backtest_divergence_warning.py` tests assert the stale `ADR-012` string, so they pin the broken reference.

---

## Backtest — N/A, not a strategy result

`backtesting/run_phase1_backtest.py` has no `--strategy` flag; it runs a fixed baseline-vs-Phase-1 comparison and **does not exercise the live ensemble path**. The alternative, `services/trading-engine/run_extended_backtest.py`, opens with its own banner: *"PERMANENT DIVERGENCE — signal logic diverges from live CoreAggregator … do NOT treat output as live-PnL forecast"* (ADR-027). **No harness in this repo validates the live ensemble.**

Ran anyway for coverage. Window 2026-04-26 → 2026-07-30 (95 days, entirely post testnet-flip — clean, no `--ack-mixed-data` needed):

| Symbol | Baseline trades | Phase-1 trades |
|---|---|---|
| SOLUSDT | 1 | 0 |
| BNBUSDT | 1 | 0 |
| ADAUSDT | 2 | 1 |
| BTCUSDT | 2 | 1 |
| ETHUSDT | 1 | 1 |

0–2 trades per symbol over 95 days. No usable sample — the printed win-rate / Sharpe / profit-factor figures are noise on n≤2 and should not be read as evidence in either direction. This is a harness observation, not alpha.

---

## What is genuinely healthy

- Auto-trader loop ticks on schedule; circuit breaker present; `[ENSEMBLE] Already have position on X, skipping` dedupe works.
- Paper-mode sizing respects the 10% cap (observed 6.44%, 7.45%); notional matches the documented `margin × leverage` model exactly (ADA: 6.44% × $78 × 10 = $50.35, DB `total_value` 50.35).
- `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` boot gate present and correct (`app/main.py:264-271`).
- LIVE per-trade cap gate on `max_risk_per_trade` present and correct (`app/main.py:284-292`) — it is the *floor* that escapes it, not the cap.
- Daily-P&L UTC rollover fix (2026-07-28) present and wired.
- Strategy + risk unit suites: 253 passed.
- TA service healthy — all indicator endpoints HTTP 200 on the numeric intervals the engine actually uses (`60`, `15`, `240`).

> Note for future audits: `market-data:8002/api/v1/klines` rejects string intervals (`15m` → `400 Invalid interval`) and requires Bybit-native numeric (`15`, `60`, `240`, `D`). An early probe of this audit used `15m` and produced a cascade of TA 500s that looked like a live outage. It was not — the live engine uses numeric intervals throughout.

---

## Recommended order of work (not applied — audit mode)

1. **F-1** — one-line class fix. Either populate `metadata["value"]` in `signal_aggregator.py`, or (better) change both legs to read `rsi_sig.value`. Then delete the silent `, 50.0` / `, 0.5` defaults in `mean_reversion_strategy.py` so a missing input fails loud instead of voting neutral. Add a regression test asserting a non-`None` `simple_rsi` leg from a realistic indicator payload.
2. **F-2** — reorder to `min(cap, max(floor, scaled))`, and extend `check_cap` to reject `ensemble_min_position_pct > _LIVE_STRICT_CAP` in LIVE. Consider whether the LIVE cap should bound notional rather than margin given 10× default leverage.
3. **F-3** — base the daily-loss cap on live equity, not `paper_initial_balance`.
4. **F-5** — ship `database/` into the image (or move the integration conftest import behind a skip guard) so `pytest tests/` runs as documented; fix the ordering pollution in `test_repositories.py`; ship the TA tests into the TA image. Triage `test_signal_aggregator_confidence_zero` separately — it may not be stale.
5. **F-4 / F-6** — dead-code sweep and ADR reference fix; cosmetic, no runtime risk.

Do not re-enable any claim of ensemble alpha until F-1 is fixed — every trade in the DB was taken by a single-leg strategy wearing an ensemble's name.
