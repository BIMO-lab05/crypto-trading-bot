# Phase 4 Measurement — H3/H4 Kill-Test Harness

**Date:** 2026-08-05 · **Status:** approved design · **Source of criteria:** `AUDIT.md` §7 (rows H3, H4), §6
**Branch context:** `fix/audit-phase1`; H1/H2/H5/H7 instrument fixes committed 2026-08-05. Audit execution order (`AUDIT.md:267`) now reaches H3 → H4.

## 1. Purpose

Answer the two remaining Phase 0 audit hypotheses with evidence, using a permanent, re-runnable harness:

- **H3** — "2%/4% fixed brackets sit inside the noise band; exit design has ~zero expectancy before costs." Kill test: replay the *same historical entries* with ATR-derived stops, all else identical. **Accept: stop-out rate < 40% AND gross expectancy > 0 pre-fee.** If still ≤ 0 → the entry signal is uninformative → H4 is the answer.
- **H4** — "Ensemble signal carries no information; thresholds lowered until it fired." Kill test: every ensemble signal over ≥ 6 months of mainnet klines vs sign of 24h forward log-return. **Accept: directional accuracy > 50% AND DSR > 0.95, counting all ≥ 8 configurations tried.** Below that → no exit design can rescue it.

H4 runs only after H3's verdict is recorded (audit-prescribed order; H4 is the expensive test).

This is a **measurement** project. Non-goals in §9.

## 2. Decisions locked during brainstorm

| Decision | Choice |
|---|---|
| Scope | One spec covering H3 → gate → H4 |
| Form | Permanent module `backtesting/killtests/`, host-run |
| H4 data | Backfill 12 months mainnet klines direct from Bybit via bybit-connector; CSVs under `backtesting/data/`; prod DB untouched |
| H3 entries | Primary verdict from the 13 real closed entries; secondary run on regenerated entries once the offline ensemble exists |
| H4 signal generation | Approach A: full-fidelity offline reconstruction with ASGI seam + golden-sample cross-check against the running stack |

## 3. Architecture

### 3.1 The ASGI seam (H4 signal generation)

Run the deployed signal chain **unmodified**, faking only the market-data boundary:

```
backfilled CSVs ──► as-of candle feed (patched TA fetcher)
                          │
        real technical-analysis FastAPI app (in-process, httpx ASGITransport)
                          │  routes, Query defaults, rounding, envelopes — verbatim
        real SignalAggregator (httpx client → ASGITransport)
                          │  fetch_* glue, weights, MTF merge — verbatim
        real CoreAggregator + gatekeeper/validator/voter/regime
                          │
        real MultiStrategyEnsemble.generate_signal (pure Python)
                          │
        signal record per (symbol, 60m bar close)
```

- `SignalAggregator` (`services/trading-engine/app/signal_aggregator.py:29`) keeps its httpx client; the transport is swapped for `httpx.ASGITransport` wrapping the real TA app. Nothing in the client layer is reimplemented.
- The only faked component: TA's candle fetcher (`services/technical-analysis/app/fetcher.py`) patched to serve backfilled CSV bars **as-of** the replay timestamp — only bars whose close ≤ decision time, mirroring the live forming-candle drop (`fetcher.py:220-230`).
- Import shims for trading-engine/TA modules reuse the proven dual-namespace trick from `backtesting/run_walk_forward_ensemble.py:58-191` verbatim (includes the PHASE 1 TA-namespace load and PHASE 2 `sys.modules` purge that make the swap work — not just the PHASE 3 shims).

**Known risk + fallback:** `ASGITransport` does not run app lifespan. If TA handlers depend on lifespan-initialized state, fall back to `httpx.MockTransport` routing to TA's `indicator_service` functions plus envelope shaping per `main.py` routes. The golden-sample gate (§7) catches parity failure under either seam.

### 3.2 Determinism pins

| Hazard | Pin |
|---|---|
| `StrategyPerformanceWeights` EMA state (`multi_strategy_ensemble.py:54-133`, `/app/data/ensemble_weights.json`) | Fixed ⅓/⅓/⅓ (file absent in prod anyway — weights refit from scratch each restart per audit) |
| `MarketRegimeDetector._cache` 60s wall-clock TTL (`market_regime.py:141,188-209`) | Cache cleared per replayed bar |
| `time.time()` timestamps (`signal_aggregator.py:926,977`) | Timestamps sourced from bar time |
| Sizing settings (`ensemble_min_position_pct`, `ensemble_confidence_size_multiplier`, `max_risk_per_trade`) | Pinned to deployed values; recorded in run manifest |
| Capital constants | `from shared.account import ...` only — no literals (host-run convention) |

### 3.3 Deployed-path facts the replay MUST reproduce (not fix)

These are properties of the instrument under test, verified 2026-08-05:

- Ensemble entry path applies **no confidence gate** — `min_signal_confidence=0.40` never runs there (`auto_trader.py:4245-4470`).
- MTF consensus action is **never applied**; only `confidence *= modifier` — final action is always the 60m action (`signal_aggregator.py:1023-1035`).
- `indicators["ATR"]` is **always None** on the live path (`signal_aggregator.py:764-771`, no re-injection) → SimpleRSI leg uses hardcoded `atr_pct=0.02` (`simple_rsi_strategy.py:61`); MeanReversion's SMA-deviation branch never fires.
- `metadata["atr_stop_loss"/"atr_take_profit"]` has **no producer** (`aggregator_core.py:618` writes `metadata["atr"]`) → LEG_MULTI SL/TP always falls back to current price (`multi_strategy_ensemble.py:208-209`).
- Confidence can exceed 1.0 — MTF ×1.2 modifier bypasses the pydantic bound (`models/signal.py:39-58`, no `validate_assignment`).
- `current_price` comes from the first indicator carrying it in dict order — SMA, else EMA (`auto_trader.py:4265-4273`; producers `signal_aggregator.py:207,238`).
- Regime hard-block at `signal_aggregator.py:1060-1092` is dead on this path (`regime_analysis` not passed); regime applies per-timeframe inside `get_trading_signal`.

Preservation tests in §7 pin these so a future engine fix breaks the harness *loudly*.

### 3.4 Module layout

```
backtesting/killtests/
  __init__.py
  entries.py            # extract closed entries Postgres → committed JSON fixture (+ provenance block)
  candles.py            # backfilled-CSV loader: is_mainnet check, gap/dedupe validation, as-of slicing
  h3_atr_replay.py      # entries × ATR-stop variants → BacktestEngine intrabar resolution → verdict
  offline_ensemble.py   # ASGI-seam driver producing the signal series
  h4_information.py     # signal series → 24h forward log-return, dir-acc, DSR/CPCV → verdict
  report.py             # verdict file emission (.planning/evidence/killtests/)
backtesting/bybit_data_fetcher.py   # extended: batch 200→1000, 11-col CSV schema with is_mainnet
tests/killtests/                    # parity, golden-sample, preservation, unit tests (host-run)
```

Statistics kernels are imported, never reimplemented: `deflated_sharpe_ratio` (`services/risk-metrics-service/app/sharpe_metrics.py:223`), `CombinatorialPurgedCV` + `cpcv_to_dsr` (`services/risk-metrics-service/app/cpcv.py:63,232`). `run_walk_forward.py:200` already carries a third hand-rolled DSR — this module does not add a fourth.

## 4. Data foundation — backfill

- **Route:** extend `backtesting/bybit_data_fetcher.py` through bybit-connector `127.0.0.1:8001` (BC-02/D-04 forbids direct-Bybit scripts; connector route already exists and passes `min(limit, 1000)` to Bybit v5 `/v5/market/kline`, public, no auth).
- **Change:** lift `max_candles_per_request = 200` → 1000 (`bybit_data_fetcher.py:246`, plus both `limit: int = 200` defaults at `:119` and `:183`). 12 months × 5 symbols × {15m, 60m, 240m, D} ≈ **245 requests**, inside the connector's `200/minute` limiter (`bybit-connector/app/main.py:798`), ~minutes of wall-clock, $0.
- **CSV schema:** 11-column form carrying `is_mainnet` (`timestamp,symbol,interval,open,high,low,close,volume,turnover,is_mainnet,created_at`). The 6-col legacy schema silently no-ops the taint guard (`run_walk_forward_ensemble.py:568` guards conditionally). Filename keeps the `{symbol}_{interval}m_{days}d_bybit.csv` convention.
- **Preconditions asserted at runtime:** connector answers on `:8001` AND `MARKET_DATA_SOURCE=live` (tape mode would silently write frozen fixtures — `docker-compose.unified.yml:453`, `bybit-connector main.py:346-353`).
- **Open probe (settle during implementation, 1 request):** whether Bybit serves 365d of 15m linear klines. If not, 15m backfill shortens and H3 falls back to 60m resolution for affected windows (§5).
- Backfilled data is *fresh mainnet fetch* — the 2026-04-25 pollution rule concerns rows our own DB collected from testnet, not mainnet history retrieved now.

## 5. H3 — ATR-stop replay

- **Entries:** the 13 closed positions from Postgres (`docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot`; DB name is `cryptobot`, not `trading_engine`), fields: symbol, side, entry time, entry price, `entry_signal_confidence`, `Trade.signal_indicators` snapshot. Extracted once by `entries.py` into a committed JSON fixture with a provenance block (extraction date, SQL, row count) so replays are reproducible without DB.
- **Variants:** stop at **1.5×** and **2.5×** daily ATR(14) at entry — ATR computed point-in-time from backfilled D candles strictly before entry, via the unwired `ATRStopCalculator.calculate_atr` (`services/trading-engine/app/atr_stops.py:124`; pure Python, list inputs). TP = **2R** per variant. 48h max-hold retained ("all else identical" — engine rule).
- **Resolution:** `BacktestEngine` intrabar SL/TP (`backtesting/backtest_engine.py:322`) on 15m candles; 60m fallback where 15m unavailable, fallback noted per-entry in the report. Same-bar SL+TP ambiguity resolved **stop-first** (worst case); ambiguous-bar count reported.
- **Report:** stop-out rate, gross expectancy/trade (the criterion), net under both fee conventions (modelled 0.1%/side; Bybit est. 0.055%/side, from `shared.account.TAKER_FEE_PER_SIDE`), funding overlay estimate (~0.01%/8h × held intervals — funding is not modelled anywhere in the engine), per-symbol rows, per-variant verdict. **n=13 caveat printed on the report itself** — percentages describe these trades, not true rates.
- **Secondary run (staged):** once `offline_ensemble.py` exists, rerun H3 over regenerated entries for larger n. Same code path, different entry list; reported separately, never merged into the primary audit-faithful verdict.

## 6. H4 — signal information test

- **Signal series:** offline ensemble evaluated at every **60m bar close** over 12 months × 5 validated symbols (BTC, ETH, SOL, BNB, ADA), warmup ≥ 300 bars (200-EMA trend filter at `limit=300` + max lookback). HOLDs recorded but excluded from accuracy scoring; non-HOLD fire rate reported.
- **Label:** sign of 24h forward log-return (24 × 60m bars). Score: P(signal direction matches).
- **Returns series for DSR:** per-signal signed 24h log-return. Overlapping windows → serial correlation → **CPCV** with `label_horizon=24` bars + embargo (`cpcv.py:63` defaults `n_groups=10, k_test_groups=2, embargo_pct=0.01`); path Sharpe variance bridged into DSR via `cpcv_to_dsr` (`cpcv.py:232`). Gate: **DSR > 0.95**.
- **`num_trials`:** enumerated configuration history — confidence-threshold walk 0.65→0.40→0.30 (`config.py:402` history), `AGGREGATION_THRESHOLD=0.10`, `MIN_AGREEING_LEGS=1` relaxations (`multi_strategy_ensemble.py:150-153`), legacy walk-forward configs — **floored at 8** per the audit clause; enumeration may only raise it. The enumeration list is committed alongside the run manifest.
- **Profit-factor convention:** any PF figure is pooled `sum(wins)/sum(losses)` over all trades — never mean-of-folds (small folds with zero losses drag fold-mean PF to ≈1).
- **Order gate:** the H4 CLI refuses to run unless an H3 verdict file exists in `.planning/evidence/killtests/`; `--force` overrides with a logged warning.

## 7. Verification — parity gates and tests

All host-run (`from shared.account import ...`), `--no-cov`, under `tests/killtests/`.

1. **Golden-sample test (pre-verdict gate).** The same candle window driven through the running docker stack (live HTTP against TA `:8004`) and through the offline ASGI path; the resulting `TradingSignal` and ensemble output must match field-for-field. Minimum 3 windows: at least 2 symbols, at least one non-HOLD signal among them. **A mismatch invalidates any H4 run** — the verdict file is refused while this test fails.
2. **Weight/param parity test.** The offline path's effective indicator weights and parameters asserted against the live `fetch_*` metadata table (`signal_aggregator.py:96-695`) on stubbed responses. Rationale: the shipped `run_walk_forward_ensemble.py` harness silently diverges from live in six places (Ichimoku weight 0.9 vs 1.3, SMA 1.0 vs 0.8, MACD 8/17/9 vs 5/35/5, Ichimoku 9/26/52 vs 20/60/120, missing `current_price`, no MTF/ensemble). The weight table lives in client `fetch_*` functions, not `voter.py` — `RESEARCH_WEIGHTS` there is dead code.
3. **Known-bug preservation tests.** Assert the §3.3 facts (ATR entry None, `atr_stop_loss` absent, confidence > 1.0 possible, consensus action unapplied). A future engine fix flips these tests red → the replay is updated consciously, never silently.
4. **Unit tests** for: as-of feed look-ahead guard, CSV validation (gap, dedupe, `is_mainnet`), H3 stop/TP bracket math against hand-computed cases, verdict-file gating.

## 8. Data validation and error handling

Hard failures, no silent degradation:

- **Backfill:** per-symbol/interval contiguity assert; refuse rows with `is_mainnet` false or missing; dedupe the interval-mislabel pollution (5-min-spaced rows tagged `'D'`, e.g. 2026-05-06: 201 bad rows; same pattern in 240m May); expected-bar-count check.
- **As-of feed:** serves only bars with close ≤ decision time; enforces minimum warmup; refuses to start inside a gap.
- **H3:** every fixture entry must find its full candle window (entry → max-hold) or the run aborts naming the missing range.
- **H4:** refuses any candle earlier than 2026-04-26 unless it came from the backfill CSVs (which are mainnet by construction and validated as such).

## 9. Reporting and non-goals

**Reporting.** Each run emits a dated verdict file under `.planning/evidence/killtests/`: input-data hash, pinned config, metrics, **ACCEPT/REJECT against the audit criterion verbatim**, caveats (n, fee convention, funding overlay, resolution fallbacks). `AUDIT.md` §7 rows H3/H4 get a one-line status update pointing at the verdict file. No edge-claim language beyond the criterion — a passing H4 is *"signal carries information per this test"*, not *"strategy is profitable"*.

**Non-goals:**
- No live signal-persistence wiring (`trading_signals` table stays dead; separate task if wanted).
- No strategy or engine fixes — §3.3 bugs are preserved, not repaired.
- No full trade-lifecycle replay — entry decisions + bracket exits only; deployed exits (`atr_trailing_stop`, `partial_profit_taker`) are out of scope.
- No testnet-era data, ever.
- No new DSR/CPCV implementations.
- No changes to prod databases; Postgres is read once by `entries.py`, TimescaleDB not touched.
