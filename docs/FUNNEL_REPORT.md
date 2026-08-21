# FUNNEL REPORT — where signals die, and whether any threshold should move

**Date:** 2026-08-21 · **Harness:** `backtesting/replay/` · **Window:** 2026-04-25 → 2026-08-21
**Symbols:** BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT (the validated set) · **Interval:** 60 m primary,
multi-timeframe 15 / 60 / 240 · **Bars per symbol:** 2,711 · **Evaluations:** 13,555

Companion documents: `docs/PIPELINE_MAP.md` (the trace), `docs/FINDINGS.md` (everything else found).

---

## Headline

**No threshold change is justified by this data.** Every configuration tested has negative
expectancy in-sample, and the in-sample and out-of-sample rankings **disagree for both parameters
swept** — the signature of noise, not of a threshold that is set wrong. The two configurations that
turn positive out-of-sample are the two the in-sample slice would not have selected. Details in §5.

The binding constraint is not a threshold at all. It is the **structural ceiling on ensemble
confidence**: over 2,748 emitted ensemble signals the maximum confidence ever produced was **0.4500**,
against entry gates of 0.30 (LONG) and 0.35 (SHORT). That is the same class of defect recorded in
`ABANDONED.md` for `short_min_confidence = 0.70` against a 0.60 ceiling — now measured rather than
inferred. §4.

---

## 0. Method, and what would invalidate it

The replay pushes historical bars through the **deployed objects** — `CoreAggregator`,
`MultiTimeframeAnalyzer`, `MultiStrategyEnsemble`, the entry gates — recording through the same
`SignalFunnel` the live engine writes to. Nothing on the path is reimplemented.

**Fidelity check (the reason to believe any of this).** Stage 1 recomputes the 11 indicator legs
from the live TA calculators and was compared against the running system's `/api/dashboard/BTCUSDT`
payload for the most recent closed bar. Captured verbatim, 2026-08-21 22:5x UTC, bar
`1787342400000` (close 77486.4):

```
indicator                          replay                 live
ADX                              BUY/0.74             BUY/0.74  ok
ATR                      (not a live leg)                    —
BOLLINGER_BANDS                 HOLD/0.27            HOLD/0.27  ok
EMA                              BUY/0.32             BUY/0.32  ok
ICHIMOKU                         BUY/1.00             BUY/1.00  ok
MACD                            SELL/1.00            SELL/1.00  ok
RSI                             HOLD/0.30            HOLD/0.30  ok
SMA                              BUY/0.25             BUY/0.25  ok
SQZMOM_ENHANCED                  BUY/0.61             BUY/0.61  ok
STOCHASTIC                      HOLD/0.30            HOLD/0.30  ok
TREND_FILTER                     BUY/1.00             BUY/1.00  ok
VOLUME_CONFIRMATION             HOLD/0.10            HOLD/0.10  ok
signal agreement: 11/11   confidence agreement: 11/11
```

The klines feeding the replay must be re-exported immediately before this check. An earlier run of
the same comparison against a 90-minute-old CSV showed 10/11 with four confidence mismatches —
entirely because the replay was evaluating a different (older) bar than the live system, not because
of any formula divergence. That is a trap worth naming: the check is only meaningful when both sides
see the same bar.

The voter filter also matches production exactly: **9 voting legs of 11**, verified on a real frame
against the live log line `Filtered voting indicators: 9/11`. ATR is deliberately absent from the
indicator dict — see §3 of `FINDINGS.md` and the commit that removed it.

**Data floor.** All bars are on or after **2026-04-25**, the mainnet flip. TimescaleDB holds mixed
testnet/mainnet history before that date, and Stage 1 refuses any earlier bar. A replay over "the
largest available window" would have silently poisoned every distribution below with testnet prices.

**Costs.** `app.costs.round_trip_cost_bps` with `FeeSchedule.bybit_linear_perp()` (taker 0.055 %,
maker 0.020 %, both charges), TAKER on both legs, plus one-way slippage per leg from the paper
engine's table. No figure in this document is gross of costs.

**Execution realism.** One open position per symbol at a time plus the 14,400 s post-exit cooldown;
per-symbol min-notional and min-qty from the real Bybit specs, **rejected not clamped**; a bar that
touches both stop and target counts as a **stop**. Every signal that did not become a trade is
counted by reason (§3).

**What would invalidate this.** A change to any deployed filter object, the indicator parameters, or
the ensemble leg weights. The replay imports them, so it tracks them — but a report is a snapshot.
Re-run before citing.

**Known sampling caveat.** The `adx` and `aggregator_confidence` distribution series are bounded
deques capped at 20,000 samples; with 39,170 aggregations they hold the most recent 20,000. The
routing ADX distribution (n = 13,555) is complete. The same cap applies to the live funnel, where
the ADX figures the dashboard shows are the most recent 20,000 routing decisions — roughly 33 hours
at the current 30 s loop over five symbols — and are labelled as such in the tile.

**One live-telemetry defect this exercise caught.** The first version of the live `atr_pct`
observation read `base_signal.indicators["ATR"]`, which is always absent for the same reason the
replay had to stop feeding ATR to the voter — ATR is not an indicator leg. The deployed funnel
reported `atr_pct: n=0` until it was repointed at `metadata["atr"]["atr_pct"]`, where the aggregator
actually stores it. The ATR distribution in §2 is from the replay and was always correct; the live
one was dead until 2026-08-21.

---

## 1. The rejection funnel

**Read the denominators before the percentages.** This cascade is **not monotonic**, by construction:

- **Per-evaluation stages** (13,555) — one per symbol per bar.
- **Per-aggregation stages** (39,170) — the aggregator runs once per timeframe, so ~2.9× the
  evaluations (a handful of early bars have no aligned 15 m or 240 m frame).
- **Post-ensemble stages** (2,748 → 525) — back to per-evaluation.

A reader who treats 13,555 → 39,170 → 2,748 as a conversion funnel will compute nonsense.

| Stage | Denominator | Evaluated | Passed | Rejected | Pass | Top rejection reason (count, observed vs threshold) |
|---|---|---:|---:|---:|---:|---|
| Evaluations | per-eval | 13,555 | 13,555 | 0 | 100.0 % | — |
| Risk-manager halt | per-eval | 13,555 | 13,555 | 0 | 100.0 % | — |
| Raw signals generated | per-eval | 13,555 | 13,555 | 0 | 100.0 % | — |
| Current price available | per-eval | 13,555 | 13,555 | 0 | 100.0 % | — |
| **Indicator agreement (vote)** | per-agg | 39,170 | 17,845 | **21,325** | 45.6 % | `vote_score_below_aggregation_threshold` — 21,325, observed 0.0000–0.1499 vs **0.15** |
| Gatekeeper (trend filter) | per-agg | 39,170 | 38,555 | 615 | 98.4 % | `counter_trend_blocked_by_trend_filter` — 615, trend conf 0.9500–1.0000 vs **0.95** |
| Validator (volume) | per-agg | 39,170 | 39,170 | 0 | 100.0 % | *never blocks*; applied a ×0.5–×0.9 confidence penalty **31,653 times (80.8 %)** |
| Regime filter (ADX hard-block) | per-agg | 39,170 | 39,147 | 23 | 99.9 % | `counter_trend_hard_blocked_by_regime` — 23, ADX 25.04–38.59 |
| Category diversity | per-agg | 39,170 | 37,843 | 1,327 | 96.6 % | `insufficient_category_diversity` — 1,327, 1 category vs **2** |
| Consensus count | per-agg | 39,170 | 39,089 | 81 | 99.8 % | `consensus_count_below_min_consensus` — 81, 2 vs **3** |
| **Aggregator confidence floor** | per-agg | 39,170 | 26,768 | **12,402** | 68.3 % | `confidence_below_aggregator_min_confidence` — 12,402, observed 0.0000–0.2999 vs **0.30** |
| ATR filter | per-eval | 13,555 | 13,555 | 0 | 100.0 % | **advisory — not a gate.** No ATR reject exists anywhere on this path |
| Routing decision made | per-eval | 13,555 | 13,555 | 0 | 100.0 % | — |
| **Ensemble signal emitted** | per-eval | 13,555 | 2,748 | **10,807** | 20.3 % | `ensemble_returned_hold` — 10,807 |
| No open position | post-ens | 2,748 | 2,748 | 0 | 100.0 % | enforced in the simulator, see §3 |
| Re-entry cooldown | post-ens | 2,748 | 2,748 | 0 | 100.0 % | enforced in the simulator, see §3 |
| Side permitted | post-ens | 2,748 | 2,748 | 0 | 100.0 % | — |
| **Entry confidence gate** | post-ens | 2,748 | 525 | **2,223** | 19.1 % | `short_confidence_below_short_min_confidence` — 1,266, observed 0.1020–0.3499 vs **0.35**; `confidence_below_min_signal_confidence` — 957, observed 0.1020–0.3000 vs **0.30** |
| Daily trade limit | post-ens | 525 | 525 | 0 | 100.0 % | — |
| Stop/target consistency | post-ens | 525 | 525 | 0 | 100.0 % | — |
| Portfolio heat | post-ens | 525 | 525 | 0 | 100.0 % | — |
| **Order intent emitted** | post-ens | 525 | 525 | 0 | 100.0 % | — |

### Which stage is the binding constraint

| Stage | Signals killed | Share of all rejections |
|---|---:|---:|
| Indicator agreement (vote ≥ 0.15) | 21,325 | 43.9 % |
| Aggregator confidence floor (≥ 0.30) | 12,402 | 25.5 % |
| Ensemble returned HOLD | 10,807 | 22.2 % |
| Entry confidence gate (0.30 / 0.35) | 2,223 | 4.6 % |
| Category diversity | 1,327 | 2.7 % |
| Gatekeeper | 615 | 1.3 % |
| Consensus count | 81 | 0.2 % |
| Regime hard-block | 23 | 0.05 % |

The Gatekeeper, the Validator, consensus count and the regime hard-block are **not** the constraint —
together they account for under 4 % of rejections. The three that matter are the vote threshold, the
aggregator confidence floor, and the ensemble's own HOLD.

---

## 2. Distributions — the data thresholds should be set from

### ATR (as a percentage of price — the pipeline normalises, so no cross-instrument scaling trap)

| n | min | p25 | median | p75 | max |
|---:|---:|---:|---:|---:|---:|
| 13,555 | 0.085 % | 0.465 % | **0.662 %** | 0.936 % | 3.656 % |

The TA service's volatility bands are **1.0 % / 2.0 % / 4.0 %** (`atr.py:94-105`). The **median bar
sits at 0.66 %, below the lowest band**, so roughly three quarters of all bars are labelled `LOW`
volatility and receive the same 0.8 confidence. The bands were not calibrated to this universe.
They feed a confidence input, not a gate, so this misclassification degrades signal quality rather
than blocking trades — but it means the ATR leg carries almost no information as configured.

**No ATR min/max band is proposed**, because there is no ATR gate to set one on (§1, and
`FINDINGS.md` C-3). Adding one would be introducing a filter, not recalibrating one.

### ADX (the routing input)

| n | min | p25 | median | p75 | max |
|---:|---:|---:|---:|---:|---:|
| 13,555 | 6.92 | 19.15 | **24.83** | 33.21 | 77.73 |

**The 25.0 routing threshold sits almost exactly on the median (24.83).** That is close to the best
possible placement for a binary regime split: the observed routing outcome is
**49.4 % trend-following / 50.6 % mean-reversion** over the window. No change proposed — the data
endorses the existing value rather than merely tolerating it.

### Aggregator confidence (post gatekeeper / validator / regime cascade)

| n | min | p25 | median | p75 | max |
|---:|---:|---:|---:|---:|---:|
| 20,000 (capped) | 0.0000 | 0.2334 | 0.4474 | 0.4932 | 0.9998 |

The 0.30 floor sits between p25 and the median, rejecting 31.7 % of aggregations. That is a filter
doing recognisable work, not one that is unreachable.

### Aggregated vote score (the ±0.15 threshold)

| n | min | p25 | median | p75 | max |
|---:|---:|---:|---:|---:|---:|
| 20,000 (capped) | −0.5863 | −0.1474 | −0.0147 | +0.1242 | +0.5958 |

±0.15 sits just outside the interquartile range, so it rejects ~54 % — consistent with the 21,325
measured. The score distribution is roughly symmetric and centred near zero, which is what a
weighted vote over mostly-uncorrelated legs should look like.

### Ensemble confidence — **the ceiling**

| n | min | p25 | median | p75 | **max** |
|---:|---:|---:|---:|---:|---:|
| 2,748 | 0.1020 | 0.1632 | 0.2448 | 0.3060 | **0.4500** |

See §4.

---

## 3. Signals that never became trades

525 order intents were emitted. 88 became trades. The 437 that did not:

| Reason | Count |
|---|---:|
| `blocked_position_open_or_cooldown` | 188 |
| `BTCUSDT:below_min_order_qty` | 126 |
| `ETHUSDT:below_min_order_qty` | 123 |

**BTCUSDT and ETHUSDT are structurally untradeable on a $100 account.** With a 10 % per-trade cap
the maximum notional is $10; BTC's minimum order quantity of 0.001 is ≈ **$77** at current prices
and ETH's 0.01 is ≈ **$24**. Per `.claude/rules/money.md` these must be **rejected, never clamped
up** — clamping is how a 10 % cap silently becomes a 40 % cap. Every BTC and ETH signal in this
window was therefore correctly refused.

The tradeable set at $100 is **SOL, BNB, ADA** — three symbols, not five. Every expectancy figure in
this report is computed on those three.

---

## 4. The binding constraint is structural, not a threshold

`multi_strategy_ensemble.py:353-390` computes `confidence = |Σ sign × leg_conf × weight|` over three
legs whose weights are frozen at ⅓ each (`/app/data/ensemble_weights.json` does not exist, so
`normalized_weights()` returns the defaults). The arithmetic ceiling is therefore:

| Agreeing legs | Max reachable ensemble confidence |
|---|---|
| 1 | 0.333 |
| 2 | 0.667 |
| 3 | 1.000 |

**Measured over 2,748 emitted signals, the maximum ever produced was 0.4500 and the median 0.2448.**

Consequences:

- The **LONG** gate at 0.30 sits between the p75 (0.3060) and the median. Roughly a quarter of
  emitted signals can clear it.
- The **SHORT** gate at 0.35 sits above the p75. Only ~12 % of emitted signals clear it, and it
  killed 1,266 signals — more than the LONG gate's 957.
- Clearing 0.30 requires `Σ leg_conf ≥ 0.90` across agreeing legs: **one leg alone must reach
  conviction ≥ 0.90**, or two legs must average ≥ 0.45.

This is the same shape as the defect in
`.planning/evidence/forward_paper_test/prefer_maker_orders/ABANDONED.md`, where
`short_min_confidence = 0.70` sat above a structural SELL ceiling of 0.60. It is less severe here —
0.30 and 0.35 are *reachable* — but the gates are calibrated against a quantity whose range is set
by the weight table, not by market conviction.

**Why the ceiling is low** (per-indicator distribution over 12,740 60 m bars, all five symbols):

| Indicator | Weight | HOLD % | median confidence |
|---|---:|---:|---:|
| SQZMOM_ENHANCED | 1.4 | 47.5 % | 0.480 |
| ICHIMOKU | 1.3 | 20.5 % | 0.800 |
| RSI | 1.0 | **69.1 %** | 0.300 |
| MACD | 1.0 | 0.0 % | 0.610 |
| BOLLINGER_BANDS | 1.0 | 35.5 % | 0.460 |
| EMA | 1.0 | 0.0 % | **0.100** |
| ADX | 1.0 | 37.8 % | 0.400 |
| SMA | 0.8 | 0.0 % | **0.120** |
| STOCHASTIC | 1.0 | 58.2 % | 0.300 |

`compute_agreement_confidence` (`voter.py:345-350`) divides agreeing weighted conviction by the
**total** voting weight (9.5), so every HOLD leg still occupies the denominator. RSI and STOCHASTIC
consume 2.0 of 9.5 while sitting out ~60–70 % of bars; EMA and SMA always vote but at median
conviction 0.10 and 0.12. The two legs with real conviction — ICHIMOKU (0.80) and MACD (0.61) —
carry 1.3 and 1.0.

**No indicator never votes.** An earlier draft claimed SQZMOM_ENHANCED never fires; it takes a
directional side on 52.5 % of bars. RSI_DIVERGENCE is absent entirely, but deliberately — its fetch
is commented out at `signal_aggregator.py:745`.

---

## 5. Threshold sweep — and why nothing changes

**Discipline.** Configurations are selected on the **in-sample** slice only
(2026-04-25 → 2026-07-10, 55 baseline trades); the out-of-sample slice
(2026-07-10 → 2026-08-21, 33 baseline trades) is looked at **once**, afterwards. Each configuration
ran in its own process — the funnel, the regime detector and the ensemble weight store are process
singletons, so two configs in one process pool their counters.

Sweeps were run on the four-symbol set (BTC excluded from trades by the venue floor, so effectively
SOL/BNB/ADA). Baseline is the deployed configuration.

### `min_signal_confidence` (deployed: 0.30)

| value | IS trades | IS win % | **IS expectancy %** | IS avg R | IS max DD % | IS PF | OOS trades | OOS expectancy % | OOS PF |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.20 | 68 | 39.7 | −0.9038 | −0.226 | 56.97 | 0.57 | 43 | **+0.4689** | 1.50 |
| 0.25 | 66 | 37.9 | **−0.7431** | −0.186 | 55.58 | 0.65 | 37 | **+0.2565** | 1.27 |
| **0.30** | **55** | **40.0** | **−0.9813** | **−0.245** | **47.86** | **0.56** | **33** | **−0.2569** | **0.78** |
| 0.35 | 29 | 27.6 | −1.6459 | −0.411 | 39.13 | 0.31 | 21 | −0.6889 | 0.54 |
| 0.40 | 22 | 31.8 | −1.3279 | −0.332 | 28.34 | 0.45 | 18 | −0.8027 | 0.49 |

### `vote_threshold` (deployed: 0.15)

| value | IS trades | IS win % | **IS expectancy %** | IS max DD % | IS PF | OOS trades | OOS expectancy % | OOS PF |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.10 | 55 | 40.0 | −0.9815 | 47.87 | 0.56 | 30 | **+0.0830** | 1.07 |
| **0.15** | **55** | **40.0** | **−0.9813** | **47.86** | **0.56** | **33** | **−0.2569** | **0.78** |
| 0.20 | 56 | 35.7 | −1.0180 | 49.54 | 0.55 | 34 | −0.4090 | 0.68 |
| 0.25 | 57 | 38.6 | **−0.8369** | 48.64 | 0.61 | 36 | −0.0640 | 0.94 |

### Reading these tables

1. **Every configuration is negative in-sample.** There is no value of either parameter that makes
   this pipeline profitable on the training slice. Tightening (0.35, 0.40) makes it markedly worse;
   loosening improves it slightly while staying negative.
2. **The in-sample and out-of-sample rankings disagree, for both parameters.** IS picks
   `min_signal_confidence = 0.25`; OOS would pick `0.20`. IS picks `vote_threshold = 0.25`; OOS would
   pick `0.10`. When the ranking is unstable across slices, the surface is noise.
3. **The out-of-sample positives are exactly what must not be chased.** `min_signal_confidence`
   0.20 and 0.25 return +0.47 % and +0.26 % per trade out of sample — on 43 and 37 trades in a
   42-day window, selected by looking at the held-out slice. Acting on that is the definition of
   selecting on out-of-sample data.
4. **The mission's own rule settles it.** *"Never loosen a filter without replay evidence that the
   additional signals it admits are net positive on expectancy."* In-sample, moving 0.30 → 0.25 adds
   11 trades and moves expectancy from −0.981 % to −0.743 %. Less negative is not net positive.

### Threshold change table

```
min_signal_confidence: 0.30 → 0.30  (NO CHANGE)
Evidence: in-sample expectancy negative at every tested value (−0.74 % to −1.65 %); the
          in-sample-selected value (0.25) and the out-of-sample-selected value (0.20) disagree.
Effect on replay: not applied.

vote_threshold: 0.15 → 0.15  (NO CHANGE)
Evidence: expectancy flat within noise across 0.10–0.25 (−0.84 % to −1.02 % in-sample, a spread
          smaller than the standard error on 55 trades); IS and OOS rankings invert.
Effect on replay: not applied.

adx_trending_threshold: 25.0 → 25.0  (NO CHANGE)
Evidence: the ADX median over 13,555 evaluations is 24.83. The deployed threshold sits on the
          median and splits routing 49.4 % / 50.6 %. The distribution endorses the current value.
Effect on replay: not applied.

gatekeeper_block_threshold: 0.95 → 0.95  (NO CHANGE)
Evidence: fires 615 times in 39,170 aggregations (1.6 %), 1.3 % of all rejections. Not the binding
          constraint; moving it would change almost nothing and cannot be justified on this data.
Effect on replay: not applied.
```

**Every one of these values was nevertheless moved out of the code body and into config**
(`adx_trending_threshold`, `gatekeeper_block_*`) or whitelisted so an `.env` value can reach the
container (`MIN_SIGNAL_CONFIDENCE`, `SHORT_MIN_CONFIDENCE`, `MIN_CONSENSUS_INDICATORS`). Before this
change, `MIN_SIGNAL_CONFIDENCE` was a `Settings` field with **no path into the container at all** —
trading-engine has no `env_file:` and the key was absent from the compose whitelist, so any operator
who "retuned" it in `.env` was editing a file the engine never read.

---

## 6. Out-of-sample result, stated plainly

The mission asks for this to be said without hedging, so:

**The deployed configuration loses money on both slices after costs.**

| Slice | Trades | Win % | Expectancy / trade | Avg R | Max drawdown | Profit factor |
|---|---:|---:|---:|---:|---:|---:|
| In-sample (Apr 25 – Jul 10) | 55 | 40.0 % | **−0.98 %** | −0.245 | 47.9 % | 0.56 |
| Out-of-sample (Jul 10 – Aug 21) | 33 | 48.5 % | **−0.26 %** | −0.064 | 20.2 % | 0.78 |
| Full window | 88 | 43.2 % | **−0.71 %** | −0.177 | 49.5 % | 0.61 |

The out-of-sample slice is less bad than the in-sample one, and if the parameter had been loosened
to 0.20 or 0.25 it would have been positive. **That is not evidence of edge.** Three reasons:

1. 33–43 trades over 42 days is nowhere near enough to distinguish a 0.5 % edge from noise.
2. The improvement is not monotonic in the parameter and reverses between slices.
3. No DSR or CPCV was applied. Per CLAUDE.md §2 no edge claim stands in this repo without them, and
   the `backtesting/edge_lab/` machinery exists for exactly this.

The honest statement is: **there is a hypothesis worth testing properly** — that the entry
confidence gate is set slightly too high for the confidence distribution this ensemble produces —
**and this replay is not the test.** The right next step is the edge-lab kill funnel with DSR/CPCV
over more data, not a config change.

---

## 7. What was changed as a result of this report

| Change | Reason |
|---|---|
| Nothing in the filter thresholds | §5 — no evidence supports moving any of them |
| `adx_trending_threshold` moved to config | It was a bare `25.0` in the router constructor while the dashboard advertised it as the live rule |
| `gatekeeper_block_threshold` / `_block_penalty` / `_counter_trend_penalty` moved to config | The gatekeeper docstring claimed 0.9 while the code applied 0.95; a reader could not tell which was live |
| Filter thresholds whitelisted in compose | They were `Settings` fields no `.env` value could reach |
| Advisory routing + the full funnel deployed | So the next person can answer "why zero?" from the dashboard instead of by grepping logs |

## 8. Reproducing this

```bash
# 1. export post-flip klines (floored at the 2026-04-25 mainnet flip)
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c \
  "\copy (SELECT timestamp,open,high,low,close,volume FROM klines
          WHERE symbol='ADAUSDT' AND interval='60' AND is_mainnet
            AND timestamp >= extract(epoch from timestamp '2026-04-25')*1000
          ORDER BY timestamp) TO STDOUT CSV HEADER" > klines/ADAUSDT_60.csv

# 2. stage 1 — indicator frames (TA context)
python3 backtesting/replay/build_indicator_frames.py \
  --klines-dir klines --out frames --symbols ADAUSDT --intervals 60,15,240 --primary 60

# 3. stage 2 — replay the live filter stack (engine context)
python3 backtesting/replay/replay_filter_stack.py \
  --frames frames --klines klines --out report.json --split-date 2026-07-10

# 4. sweep one threshold, selecting on the in-sample slice only
python3 backtesting/replay/sweep.py \
  --frames frames --klines klines --out-dir sweeps --split-date 2026-07-10 \
  --param min_signal_confidence --values 0.20,0.25,0.30,0.35,0.40
```

Stage 1 takes roughly 140 ms per bar per timeframe (≈ 15 min per symbol for the full window).
