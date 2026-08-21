# FINDINGS — things found while repairing the Hybrid Strategy Routing pipeline

**Date:** 2026-08-21 · **Branch:** `feature/edge-search-v2` · **Engine SHA at start:** `2d45be2`

Everything here was found while tracing the routing pipeline. Items marked **NOT TOUCHED** were
deliberately left alone — they are outside the mission's scope, are risk controls the mission
forbids adjusting, or need a decision that is not mine. Each carries the evidence to act on it later.

Companion documents: `docs/PIPELINE_MAP.md` (the trace), `docs/FUNNEL_REPORT.md` (the measurements).

---

## A. Money-path defects

### A-1. Mean-reversion routing branch sizes positions at up to 20 % of capital — **NOT TOUCHED**

`services/trading-engine/app/strategies/hybrid_strategy_router.py:232-234`

```python
position_size_pct = 0.10 + (mr_signal.confidence * 0.10)  # 10-20%
position_value = capital * position_size_pct
```

On a $100 account that is **$10–$20 per trade** against the ADR-010 paper cap of **10 % = $10**, and
against `max_position_size_pct = 10.0`. The `.claude/rules/money.md` sizing contract says notional
above `equity * max_position_size_pct / 100` must be **clamped down**; this code has no clamp.

**Why it has not bitten:** the branch is unreachable in the deployed configuration — the router has
never executed (see PIPELINE_MAP §0), and it stays unreachable under the advisory design shipped
today. **It becomes live the moment anyone sets `STRATEGY_MODE=hybrid` or promotes the router to an
executing one.** Downstream clamps in `_execute_trade_with_setup` may or may not catch it; that was
not verified because the path cannot currently be exercised end to end.

**Blocking condition:** fix this before any promotion of the router from advisory to executing.

### A-2. `AutoTrader` has three different silent defaults for `strategy_mode`

| Source | Value | Location |
|---|---|---|
| pydantic `Settings` | `"standard"` | `app/config.py:310-313` |
| compose | `"ensemble"` | `docker-compose.unified.yml:686` |
| `AutoTrader.__init__` keyword | `StrategyMode.HYBRID` | `app/auto_trader.py:191` |
| `get_auto_trader()` fallback for an unrecognised string | `StrategyMode.HYBRID` | `app/auto_trader.py:5142` |

A typo in `STRATEGY_MODE` silently selects **HYBRID** — a different strategy, a different risk
profile, and (per A-1) an above-cap position sizer. `GRID_TRADING` already raises at construction
for exactly this class of bug (`auto_trader.py:289-295`); the unknown-string case does not.
**Suggested:** raise on an unrecognised mode instead of falling back. **NOT TOUCHED** — outside the
routing repair, and changing boot behaviour deserves its own change.

---

## B. Configuration reachability

### B-1. Six Settings fields could never be set — **FIXED**

`services/trading-engine` has **no `env_file:` directive** in `docker-compose.unified.yml`, and the
Dockerfile copies `app/` only. The container environment is exactly the `environment:` whitelist.
`MIN_SIGNAL_CONFIDENCE`, `SHORT_MIN_CONFIDENCE`, `MIN_CONSENSUS_INDICATORS`,
`MIN_INDICATOR_CONFIDENCE`, `ML_CONFIDENCE_FLOOR`, `ENSEMBLE_*` were **absent from that list**, so
any operator who "retuned" them in `.env` was editing a file the engine never reads.

Whitelisted the routing/filter subset in this change (`MIN_SIGNAL_CONFIDENCE`,
`SHORT_MIN_CONFIDENCE`, `MIN_CONSENSUS_INDICATORS`, `GATEKEEPER_*`, `ADX_TRENDING_THRESHOLD`,
`STRATEGY_ROUTING_MODE`). **`MIN_INDICATOR_CONFIDENCE` and `ML_CONFIDENCE_FLOOR` remain unreachable**
— they are outside this pipeline and were left alone.

### B-2. Primary filter thresholds are bare literals in code — **PARTIALLY FIXED**

Fixed (now Settings-backed): `ADX_TRENDING_THRESHOLD`, `gatekeeper_block_threshold`,
`gatekeeper_block_penalty`, `gatekeeper_counter_trend_penalty`.

**Still hardcoded — NOT TOUCHED:**

| Knob | Value | Location |
|---|---|---|
| voter `aggregation_threshold` | `0.15` | `aggregation/aggregator_core.py:115` |
| `min_consensus` | `3` | `aggregator_core.py:151` |
| `min_confidence` | `0.30` | `aggregator_core.py:152` |
| `min_category_consensus` | `2` | `aggregator_core.py:153` |
| all 8 validator multipliers | `1.0`–`0.5` | `aggregation/validator.py:121-181` |
| indicator weights (0.8 / 1.0 / 1.3 / 1.4) | — | `signal_aggregator.py:96,139,178,209,240,407,614,695` |
| ensemble `AGGREGATION_THRESHOLD` | `0.10` | `strategies/multi_strategy_ensemble.py:207` |
| ensemble `MIN_AGREEING_LEGS` | `1` | `multi_strategy_ensemble.py:210` |
| ATR volatility bands | `1.0 / 2.0 / 4.0 %` | `technical-analysis/app/indicators/atr.py:94-105` |

The replay harness (`backtesting/replay/`) parameterises all of these, so they can be swept without
editing code; making them env-configurable in the service is a separate change.

---

## C. Structural reachability of the gates

### C-1. The ensemble confidence ceiling is set by the leg weights, not by conviction

`multi_strategy_ensemble.py:353-390` computes `confidence = |Σ sign × leg_conf × weight|` with
weights normalised across three legs. With the frozen ⅓ weights currently in force
(`/app/data/ensemble_weights.json` does not exist, so `normalized_weights()` returns 0.333 each):

| Agreeing legs | Max reachable ensemble confidence |
|---|---|
| 1 | 0.333 |
| 2 | 0.667 |
| 3 | 1.000 |

Clearing `min_signal_confidence = 0.30` therefore needs `Σ leg_conf ≥ 0.90` across agreeing legs —
**a single leg must reach conviction ≥ 0.90**, two legs need a mean of ≥ 0.45. This is the same
shape of defect recorded in `ABANDONED.md` for `short_min_confidence = 0.70` against a structural
SELL ceiling of 0.60. Quantified against the real distribution in `docs/FUNNEL_REPORT.md`.

### C-2. The gatekeeper's blocking branch is close to unreachable

`TrendFilter` confidence is `min(abs(spread_pct) / 0.05, 1.0)` where `spread_pct` is the EMA50/EMA200
gap (`technical-analysis/app/indicators/trend_filter.py:75`). Reaching the block threshold of
**0.95 requires a 4.75 % EMA50/EMA200 spread**. In practice the ×0.95 *penalty* branch is what fires,
not the block. The gatekeeper's headline behaviour ("blocks counter-trend trades") therefore
describes a branch that almost never executes.

### C-3. There is **no ATR filter** in the trading path

The mission's funnel spec includes `passed_atr_filter`. Tracing it: `aggregator_core.py` references
`atr_data` only for metadata and stop construction (`:174`, `:364`, `:433`, `:557`, `:616-622`) —
it never appears in the `meets_requirements` expression. ATR feeds **stops, position sizing and a
confidence input**, and rejects nothing.

The stage is therefore declared in the funnel and **labelled `advisory`**, with the ATR distribution
recorded. Reporting it as a 100 %-pass gate without that label would manufacture a filter that does
not exist. Introducing a real ATR gate is a strategy change and was not done.

### C-4. Two ATR implementations disagree on smoothing — **NOT TOUCHED**

- `technical-analysis/app/indicators/atr.py:90` — `df['tr'].ewm(span=14, adjust=False).mean()`, i.e.
  α = 2/15 ≈ 0.133. That is a **standard EMA, not Wilder** (Wilder is α = 1/14 ≈ 0.071). It matches
  its own docstring, but not the conventional definition of ATR.
- `trading-engine/app/atr_stops.py:160` — `sum(true_ranges[-14:]) / 14`, a **simple mean**.

So the ATR used for the volatility label and the ATR used for stop distances are computed by two
different methods on the same data. Neither is Wilder. Threshold comparisons *are* normalised
(`atr_pct = atr / price * 100`, `atr.py:91`), so the cross-instrument scaling trap the mission warns
about does not apply here.

### C-5. `_check_and_trade_ensemble` ignores the aggregator's own verdict

`_check_and_trade:1218-1220` and `_check_and_trade_hybrid:1054,1099` both gate on
`signal.metadata["meets_requirements"]`. The **ensemble path does not.** The multi-indicator leg
self-excludes when the aggregator forced HOLD (`multi_strategy_ensemble.py:314-317`), but the
`simple_rsi` and `mean_reversion` legs read the raw indicator dict and vote regardless — and with
`MIN_AGREEING_LEGS = 1`, a single leg can carry a trade past a pipeline that just said no.

**NOT TOUCHED** — closing this would reduce trade count, which is a strategy change requiring
replay evidence.

---

## D. Indicator-level issues

### D-1. `RSI_DIVERGENCE` never votes

`signal_aggregator.py:745` — the fetch is commented out, so the leg (weight 1.2,
role `REVERSAL_DETECTOR`) is never present. Nine of the eleven documented indicators vote.
This is deliberate and documented in `voter.py:8`; recorded here so the "an indicator that never
votes" question the mission raises has an answer.

### D-2. `SQZMOM_ENHANCED` carries the largest weight (1.4) and is near-constant

Live observations show `signal=HOLD, confidence=0.25, squeeze_on=false, firing=false` on essentially
every sample taken. A leg that never fires but carries the largest weight dilutes the denominator in
`compute_agreement_confidence` (`voter.py:350` divides by `total_weight`, which includes non-agreeing
legs), mechanically depressing every confidence the system can produce. Quantified in
`docs/FUNNEL_REPORT.md`. **NOT TOUCHED** — re-weighting is a strategy change.

### D-3. ADX is verified correct

The service ADX matches `ta.trend.ADXIndicator(window=14)` to **0.01** on both a synthetic trending
and a synthetic ranging series (`services/technical-analysis/tests/test_adx_reference_parity.py`).
The "wrong or always-NaN ADX" hypothesis is dead: live values span 16.4 – 61.6, straddling the 25.0
routing threshold in both directions.

### D-4. Replay fidelity is confirmed against the live system

The Stage-1 replay reproduces the running system's indicator payload for the latest bar **exactly**
— 11/11 confidences identical, 10/11 signals identical. The single difference is
`VOLUME_CONFIRMATION`, where the calculator emits `REJECT` and the engine maps it to `HOLD`
(`signal_aggregator.py:302-308`); the replay now mirrors that mapping. Captured evidence is in
`docs/FUNNEL_REPORT.md`.

---

## E. Observability

### E-1. Funnel counters do not survive a restart — **KNOWN LIMITATION (FUNNEL-01)**

`SignalFunnel` is a process-local singleton, the same lifetime model as `Phase1MetricsProvider` and
`MarketRegimeDetector`. A container restart zeroes it. `started_at` in the payload reports the epoch
the counters cover, so a reader can always tell — but a long-horizon rejection history needs
persistence (Postgres or the existing windowed-bucket approach in `phase1_metrics.py`).

### E-2. `regime_distribution` in the status payload is empty in ensemble mode

`auto_trader.py:4409-4413` builds `regime_distribution` from `self.regime_counts`, which is
incremented **only** at `:1148` — inside `_check_and_trade` (the standard path). The ensemble path
never touches it. `regime_detector_stats.regime_distribution` *is* populated and is what the
dashboard tile reads. **NOT TOUCHED** — the tile has a correct source; deduplicating the two
counters is cleanup, not a fix.

### E-3. Two dashboard tiles poll `/api/trading/status` on the same 5 s cycle

`HybridStrategyPanel` (key `['trading-status']`) and `RegimeIndicator` (key
`['trading-status-regime']`) issue separate requests for the identical payload — the endpoint is
fetched twice per cycle for no benefit. Sharing one query key would halve it. **NOT TOUCHED.**

### E-4. `TileState`'s empty-state branch was unreachable for this tile

`isEmpty={(d) => !d || !d.status}` (`HybridStrategyPanel.jsx:103` before this change), but
`trading_control.py:97` always returns a `status` key — so "No data yet" could never render no
matter how much of the payload was missing. Now keyed on `hybrid_strategy_stats` as well.

---

## F. Documentation vs code contradictions found in passing — **NOT TOUCHED**

| # | Claim | Reality |
|---|---|---|
| 1 | `gatekeeper.py:25` docstring: blocking threshold "0.9" | code applied `0.95` (now `settings.gatekeeper_block_threshold`) |
| 2 | `aggregator_core.py:66-68` docstring: `min_consensus 2`, `min_confidence 0.12`, `aggregation_threshold 0.12` | code: `3`, `0.30`, `0.15` |
| 3 | `aggregator_core.py:131` comment: "min_category_consensus: 3 categories (maintained)" | code: `2` |
| 4 | `aggregator_core.py:16` comment: cascade "gatekeeper 0.85x × validator 0.75x = 0.6375x" | gatekeeper's non-block penalty is `0.95x` |
| 5 | `signal_aggregator.py:1060` comment: per-timeframe signals "do NOT receive regime_analysis" | `get_trading_signal:939` fetches and passes it; the *post-MTF* block is what does not run on the ensemble path |
| 6 | `multi_strategy_ensemble` comment references `config.py:408` for `min_signal_confidence` | the field is at `config.py:434` |
| 7 | `auto_trader.py:658-660` logs "Hybrid Strategy: TREND-FOLLOWING + MEAN REVERSION (ADX threshold: 25.0)" at boot | printed unconditionally, regardless of `strategy_mode` — it advertised a subsystem that had never executed |

Item 7 is the most consequential: combined with the hardcoded `[Live]` dot in the dashboard, the
system asserted an active subsystem in two places while it had made zero decisions in seven months.

---

## G. Operational

### G-1. Isolation run `20260821T165830Z` abandoned

Recorded at `.planning/evidence/forward_paper_test/prefer_maker_orders/20260821T165830Z/ABANDONED.md`.
Zero fills in 3.4 h; 84 of 84 emitted signals rejected at `min_signal_confidence 0.30` with
confidence 0.2761. Operator authorised the mid-window redeploy. `complete-run` must not be run
against that window, and must not be forced past its container-Created refusal.

A fresh isolation run should be relaunched **after** the recalibration decision, not before —
relaunching against an unchanged `min_signal_confidence` reproduces the same empty window.

### G-2. `ensemble_weights.json` does not exist on the host

`multi_strategy_ensemble.py:84` persists learned leg weights to `/app/data/ensemble_weights.json`.
No such file exists, so the ⅓ weights are defaults that have never been updated by outcomes — which
is consistent with the account having taken very few closed trades. Everything in C-1 assumes those
frozen weights; if the learning loop ever starts moving them, the reachability arithmetic changes.
