# Why every signal is HOLD and the system placed zero orders

**Date:** 2026-08-22 (revised 2026-08-23 after adversarial verification)
**Window:** container lifetime `2026-08-22 17:39:09 → 20:14:33 UTC` = **2h35m** (154.8 min), 3,720 aggregation blocks
**Branch:** `feature/edge-search-v2` @ `931eb81` · **Mode:** PAPER, `STRATEGY_MODE=ensemble`, auto-trading ON, no kill-switch file

> **Evidence status.** Numbers below were measured directly (commands in transcript), then re-measured
> by independent adversarial verifiers against a frozen copy of the log
> (`FROZEN.log`, md5 `bd0f417d55c004b98eb069fb4b9c80a1`, 207,548 lines). Where the two disagreed,
> **the verifier's number is used** and the original is noted. 59 verdicts landed: 49 upheld,
> 10 partially refuted. **116 of 181 verification agents died on an API session limit** — findings
> marked *[unverified]* had no surviving verifier and are **not** thereby refuted, only untested.

## Verdict

The system is **not broken and not halted**. The loop runs, 12/12 indicators fetch cleanly, and the
aggregator does emit directional signals.

Zero orders is produced by **two gates in series, each individually sufficient to block everything**,
plus a third downstream ceiling. The first two are **perfectly anti-correlated** — which is why the
naive reading ("only the confidence floor binds") is wrong, and why fixing either one alone changes
almost nothing.

## 1. The measured funnel

| Stage | Count | Note |
|---|---|---|
| Aggregation blocks (symbol × timeframe) | 3,720 | polling, not independent events — see §7 |
| Killed by the **voter score floor 0.15** before any confidence test | 1,900 (51.08%) | `voter.py:84, :262, :270` |
| Directional preliminaries surviving | 1,820 | = 1,820 `Preliminary (agreement)` lines |
| **Passed the aggregator gate** | **19 (1.04%)** | all ADAUSDT 15m, all conf 0.31 |
| Rejected at the gate | 1,801 | |
| Ensemble decisions | 1,235 | 1,140 "no legs fired" + 95 threshold rejects |
| **Orders placed** | **0** | all 7 downstream gates have `evaluated = 0` |

Per timeframe (directional / rejected / passed):
**15m** 282 / 263 / 19 · **60m** 550 / 550 / 0 · **240m** 988 / 988 / 0.

## 2. Gate A — the volume multiplier, which *is* the confidence floor

The confidence leg appears in **1,801 / 1,801 rejections (100%)**. But it is not an independent
selector. Across all 1,820 directional survivors the volume multiplier separates the outcome
**perfectly**:

| Volume multiplier | n | rejected | passed |
|---|---|---|---|
| ×0.5 (INSUFFICIENT) | 1,765 | 1,765 | **0** |
| ×0.75 (WEAK) | 36 | 36 | **0** |
| ×1.0 (STRONG) | 19 | 0 | **19** |

Zero penalised signal ever reached 0.30. Max under ×0.5 = **0.290** (a single degenerate record,
see below); 1,764 of 1,765 are ≤ 0.25. Max under ×0.75 = 0.190.

Arithmetic bound: observed agreement ceiling **0.49** × 0.5 × 1.20 (the STRONG_TREND cap,
`market_regime.py:326-353`) = **0.294 < 0.30**. **With the volume penalty applied, the confidence
gate is unreachable.**

**The decisive evidence that the floor is not selecting on agreement quality:** the 19 signals that
passed had pre-validator agreement confidence **0.31**; 988 rejected signals had **0.40**. The gate
rejects *higher*-agreement signals that lack volume confirmation and admits *lower*-agreement
signals that have it. The 0.30 floor is where the validator's verdict gets recorded, not a quality
test.

*(Corrections applied: max is 0.290 not 0.25 — my first parse dropped 8 records including that one.
That record is `consensus=1 (min=3), confidence=0.29, category_diversity=1` — one voter carrying the
whole ballot during a TA outage, failing three legs. It cleared nothing. The multiplier buckets are
{0.5, 0.75, 1.0}; there is no 0.8× — `validator.py:194` formats with `:.1f` so 0.75 prints as "×0.8".)*

### The volume indicator is correct; its use is the problem

`volume_confirmation.py:70-90`: `volume_ratio = bar_volume / mean(last 20 bars including itself)`;
`< 1.0` → INSUFFICIENT. Because bar volume is right-skewed, the 1.0× line sits near the **65th
percentile** — the *median* bar is labelled "insufficient". A median baseline would give ~50% by
identity. **This is a label-vs-baseline specification mismatch, not a threshold-tuning question.**

Three rates that must never be blended:

| basis | rate | n |
|---|---|---|
| per **bar**, 30-day history | **61–66%** | 18,885 |
| per **bar**, this window | ~79% | 145 |
| per **evaluation**, this window | **95.5%** | 3,720 |

The 30-day figure reproduces `validator.py`'s docstring claim (64.7% of 17,478 bars) to within a
point — **the docstring is accurate**. The jump to 95% is two effects, roughly 16 points each: a
genuinely low-volume window, and evaluation weighting (every symbol/interval re-polled ~247 times
regardless of how many bars closed, giving slow timeframes — 100% INSUFFICIENT this window — the
same weight as fast ones).

**Partial-bar contamination: tested and REFUTED.** All stored bars are closed
(BTC at 20:09 UTC: 15m→19:45, 60m→19:00, 240m→16:00). The collector lags one bar; it never
publishes a forming bar.

**Additional defect** *[unverified]*: the engine only ever requests `signal_type="breakout"`, so
`confirmed=True` requires ratio ≥ 1.2 and the WEAK band (1.0–1.2×) is **permanently unconfirmable**;
the `threshold` local computed from `signal_type` is never read. Long-run confirmed-rate ceiling
≈ 26–28%; measured live **3.2%** (120 of 3,709).

## 3. Gate B — category diversity is MASKED, not redundant

My first pass concluded "diversity never binds alone, so fixing it changes nothing." **That reading
is wrong, and the verifiers overturned it.**

Observationally true: 989 diversity failures, **0 of 1,801 rejections cite diversity without
confidence also failing**. (Structurally guaranteed — `_build_rejection_reasons`
(`aggregator_core.py:620-641`) appends every failing leg with no early return.)

But the co-failure is **manufactured by the volume validator**. All 989 diversity failures logged
`Volume INSUFFICIENT - Penalty: 0.5x`, and their **pre-penalty agreement confidence was 0.37–0.49 —
every one already above the 0.30 floor**. Remove the penalty and confidence lands at 0.444–0.588,
passing on **989/989**; consensus passes on 988/989. **Category diversity would then be the sole
blocking leg on 988 records.**

The two gates are **perfectly anti-correlated across all 1,820 survivors — zero off-diagonal**:

| | diversity FAIL | diversity OK |
|---|---|---|
| **pre-penalty conf ≥ 0.35** | **989** | 0 |
| **pre-penalty conf < 0.35** | 0 | **831** |

Mechanism: high agreement confidence arises *precisely* when voting power concentrates in one
category — and **TREND supplies 4 of the 9 live voters and 4.1 of 9.5 total weight (43.2%)**.
Concentration is simultaneously what raises confidence and what fails diversity.

Since volume is INSUFFICIENT on ~65% of bars structurally, **the masking is a 2-in-3 coin flip, not
a guarantee**: on the other ~35% of bars diversity decides the outcome by itself. The leg is
**maximally load-bearing**, not inert.

**Counterfactual — removing only the volume penalty: 1,011 clear the floor, 989 then fail diversity,
and only 22 pass.** Not 938. My §4 figure in the previous revision double-counted.

### Where diversity fires, and the corrected absolutes

| timeframe | directional | diversity failures |
|---|---|---|
| 15m | 282 | 0 |
| 60m | 550 | **1** |
| 240m | 988 | **988 (100%)** |

All 989 failures are exactly `1/2 categories (need 2)`. Passes: 831 = 576 at 2 categories + 255 at 3.

The single non-240m firing (`FROZEN.log:172735`, LINKUSDT 60m, 19:47:23) is **degenerate** — 10 of
12 TA fetches failed, leaving `Filtered voting indicators: 1/2`, one voter (ADX SELL) which cannot
span 2 categories. It occurred during a TA-outage episode (~19:45–19:47) in which the engine
evaluated the **wider research universe** (AVAX, MATIC, LINK, ARB, DOT), not only the 5 validated
symbols. On normally-populated rosters the leg fires 0 times outside 240m — but **"never" and
"exclusively" are false as stated.**

The 988 failures are real 1-category signals: prelim BUY with **only TREND agreeing**
(SMA + EMA + ICHIMOKU + ADX bullish) against RSI / MACD / STOCHASTIC / BOLLINGER.

### Category-map findings *[unverified except where noted]*

- **The map is complete** — all nine live voter names are in `INDICATOR_CATEGORIES`, the `OTHER`
  bucket was empty in every block, roster byte-identical across 4,015 of 4,016 evaluations.
  `diversity=1` is real vote disagreement, **not** name drift.
- **TREND appeared in the agreeing set 1,973 / 1,973 times (100%).** The gate never tests whether
  TREND agrees — the 2-of-3 requirement is in practice a **1-of-2 requirement on MOMENTUM|VOLATILITY**.
- **MACD is bucketed `MOMENTUM` but is a moving-average crossover — a slow trend-follower.**
  316 of 904 passes (35.0%) were carried by MACD alone as the sole non-TREND agreeing voter: the
  gate believes it got trend + momentum confirmation when it got trend + trend. On 240m, MACD alone
  carries the entire MOMENTUM opposition (1,068/1,068); genuine mean-reverters oppose far less
  often (RSI 57.9%, STOCH 25.0%). **This inverts the "trend-followers vs mean-reverters" story in
  the previous revision** — the 240m failure is *fast-trend vs slow-trend* disagreement.
- **SQZMOM_ENHANCED is the swing vote in 1,069/1,069 failures** (always HOLD there). Its silence is
  conditional-fire, not a dead leg: 66.3% directional on 15m, 0.0% on 240m — **must not be pooled**.
  Consistent with the corrected memory note (52.5% directional over 12,740 bars).

## 4. Gate C — the ensemble, and where its confidence comes from

`multi_strategy_ensemble.py:208-221`, confirmed against the live boot line:

```
legs=[simple_rsi, multi_indicator, mean_reversion]  threshold=0.1  min_agreeing=1
weights={'simple_rsi': 0.3333, 'multi_indicator': 0.3333, 'mean_reversion': 0.3333}
```

`:364` — `contribution = sign * conf * weights.get(leg_id, 0.0)`, normalised over **all three legs**
including those that did not fire.

- `simple_rsi` fired **0** times — `simple_rsi_strategy.py:100` returns `None` unless RSI ≤ 30 or ≥ 70.
- `mean_reversion` fired **0** times.
- `multi_indicator` fired 95 times; **every leg-fire event was `Actions={'multi_indicator': 'BUY'}`**.
- Scores: `+0.033` ×73, `+0.042` ×22. Threshold `0.10`. All rejected.

### The action and the confidence come from different sources

`signal_aggregator.py:1028, :1057-1058`:

```python
adjusted_confidence = original_confidence * mtf_analysis.confidence_modifier  # PRIMARY (60m) only
primary_signal.confidence = adjusted_confidence
primary_signal.action     = mtf_analysis.consensus_action   # blend of ALL THREE timeframes' SCORES
```

And `aggregator_core.py:431-446`: on gate failure `action` is forced to `HOLD` but **`confidence` is
left at the directional value that just failed** — so it is `< 0.30` by construction.

`_calculate_weighted_consensus` (`multi_timeframe.py:189-211`) thresholds a weighted sum of raw
**pre-gate scores** at ±0.2 and never reads the gated action. **Verified at larger N: 195/195
threshold-reject events had primary 60m = HOLD; in the majority all three timeframes were HOLD at
0.0% agreement.** This is the only path by which aggregator-rejected signals reach the ensemble at all.

**Consequence:** all 19 aggregator passes were on **15m**, which feeds the consensus *action* but
never the confidence. Their 0.31 is discarded; the 60m's `0.11 → 0.10` is forwarded. Per the funnel,
2,745 of 4,110 per-timeframe aggregations (66.8%) contribute a vote and nothing else.

**60m — the primary — produced 0 directional signals in 550 evaluations**, and its maximum
*counterfactual* confidence at penalty 1.0× was **0.28**, still below 0.30. (The code comment at
`signal_aggregator.py:1041-1043` records the same 100%-HOLD result over an earlier 2,820-evaluation
sample. Still true.)

### Why the ensemble cannot fire

`score = C₆₀ × m × 0.3333` vs `0.10` (`:382`, `abs(score) < threshold` → reject).

- **60m fails its gate** (550/550): `C₆₀ < 0.30` by definition → `score < 0.090`. **Guaranteed reject.**
- **60m passes**: needs `C₆₀ ≥ 0.333` at the 0.90× WEAK modifier — strictly above the advertised 0.30.
  Signals in `[0.30, 0.333)` clear the documented gate and die at an undocumented one.

Chain verified: `0.11 × 0.90 = 0.099`; `0.099 × 0.3333 = 0.0330` → logged `+0.033`. ✓

**Correcting prior lore:** renormalising weights over firing legs (the declined 3× relaxation)
**does not unblock the 73 main events**. One firing leg → weight 1.0 → `score = conf = 0.099 < 0.10`,
still rejected. Only the 22 at `+0.042` (conf ≈ 0.126) would clear.

## 5. Instrumentation defects *[funnel findings, unverified unless noted]*

`app/monitoring/signal_funnel.py` — 22 stages, 5 distribution series, process-local, resets on
restart, no Prometheus/DB/file. Exposed at `GET /api/v1/trading/signal-funnel` and embedded in
`GET /api/v1/trading/status`.

- **The one stage that kills 100% of candidates is internally uninstrumented.**
  `ensemble_signal_emitted`: `evaluated=1625, passed=0, rejected=1625` *(verified at larger N)*.
  Its reject carries a hardcoded non-numeric reason with `observed=None, threshold=None`, so the
  92.7% / 7.3% split ("no legs fired" vs own threshold) is recoverable **only by grepping logs**.
- **`symbol` is hardcoded `"UNKNOWN"`** for every aggregation-stage rejection —
  `CoreAggregator.aggregate_signals()` takes no symbol parameter. Per-symbol attribution dead for
  7 of 22 stages.
- **`terminal_stage` is not terminal attribution.** `reject()` increments it at *every* stage, so
  `terminal_stage[X] == stages[X].rejected` identically and the total is ~4.8× the population.
- **`cycles` is permanently 0** — `start_cycle()` has zero call sites.
- **3 of 5 distribution series are contaminated** — `aggregator_confidence` and `adx` pool two
  writers with different denominators (4,110 per-timeframe + 1,365 per-evaluation);
  `aggregated_vote_score` is sampled signed while its gate records the absolute value. The module
  declares these as the basis for threshold calibration.
- **Aggregation-stage counts are not a survivor cascade** — stages do not short-circuit, so reject
  counts sum above the population. Reading them sequentially invites naming
  `passed_indicator_agreement` as the top killer; only `ensemble_signal_emitted` terminates candidates.

## 6. Other defects found *[unverified]*

- **Post-MTF confidence is unclamped.** `TradingSignal` declares `confidence` with `le=1.0`, but the
  MTF assignment bypasses validation because the model does not set `validate_assignment`. Raises the
  single-leg ensemble ceiling from 0.3333 to 0.3948. Whether any live signal exceeded 1.0 was
  **NOT MEASURED** (observed max 0.45).
- **`AGGREGATION_THRESHOLD = 0.10` is dominated by `min_signal_confidence = 0.30` downstream** —
  anything clearing 0.30 has already cleared 0.10, so 0.10 can never be the deciding filter. It
  currently absorbs the rejections and mislabels the funnel's terminal cause, hiding a 3×-larger
  real gate. Note that gate has `evaluated = 0` — **neither `min_signal_confidence` nor
  `short_min_confidence` has ever run on the live path.**
- **MTF mixes units.** Consensus from pre-gate scores (`:189-211`), "Agreement %" from post-gate
  actions (`:298-306`). The 0.90× weak-alignment penalty measures a different quantity than the
  consensus it penalises.
- **Dead code:** `multi_strategy_ensemble.py:305` adds `simple_rsi` without the `!= HOLD` guard that
  `mean_reversion` carries at `:337`. Verified unreachable — every returning path in
  `simple_rsi_strategy.py` sets BUY or SELL, mid-range returns `None` at `:100`, and every branch
  confidence (≥ 0.45) exceeds `MIN_CONFIDENCE = 0.20`.
- **`voter.py` logs a misleading consensus count** — `Voting Results: ... consensus=5/9` reports the
  max bucket, not agreement with the chosen action. The gate is unaffected (`aggregator_core.py:386-389`
  reassigns before both the check and the `Final Signal` line).
- **`ensemble_weights.json` does not exist.** `STATE_PATH = "/app/data/ensemble_weights.json"` (`:84`);
  `docker exec … cat` → `No such file or directory`. ADR-015 weight learning has never persisted.
- **`config.py` comment overstates the `mean_reversion` leg ceiling** — cites 1.00, code caps at 0.95.
  Load-bearing documentation for a live threshold, and wrong.

## 7. Sampling — the counts are polling-weighted

15 symbol×timeframe combos re-evaluated every ~36 s. **Collapsing consecutive identical states
reduces 3,701 records to 80 distinct states**, and the 19 BUYs collapse to **one** recurring ADAUSDT
15m state. *Verified independently by arithmetic that does not depend on the dedup key:* over 154.8
min, `5 × (154.8/15 + 154.8/60 + 154.8/240) = 67.7` bar transitions + 15 initial states ≈ **82.7
expected** vs **80 measured** — within 3%.

Deduplicated leg frequency over 26 distinct directional rejections: confidence 26 (100%),
**diversity 8 (30.8%)** — not the polling-weighted 54.9%.

**The 240m result is n-limited.** Its 988 failures collapse to ~7 distinct states across 4 symbols
spanning ~2 bar closes. The 100%/0% timeframe split is **not** established as structural. The
*passability* verdict is not n-limited: 15m/60m carry 62 distinct states.

**Diversity is passable** — 904 of 1,973 directional prelims cleared it (45.8% raw, 69% deduplicated).
It is not a structurally unreachable condition.

## 8. Direction asymmetry

1,745 BUY vs 75 SELL preliminaries. **No SELL passed any stage; no SELL final signal was ever
emitted; MTF consensus was never SELL across 1,235 blocks.** *Verified exact.* A 2h35m sample cannot
separate a directional market regime from a structural short-side defect — reported as observation,
not diagnosis. Context: the short gate was repaired 0.70 → 0.35 in `fix/gates-ta-dsr`, so this is
**not** the previously known unreachable-short-gate defect.

## 9. Structural vs defect

**Defects (correctness fixes, not threshold changes):**
- §4 — consolidated `action` from a 3-timeframe score consensus, `confidence` from the 60m primary
  alone; a gate-rejected signal keeps the confidence that failed; the ensemble gates on that number.
- §2 — `signal_type` hardcoded `"breakout"` makes the WEAK band unconfirmable; `threshold` is dead.
- §6 — unclamped post-MTF confidence; MTF unit mixing; funnel instrumentation (§5).
- §3 — MACD bucketed as MOMENTUM while behaving as a trend-follower, so the diversity gate's
  "2 categories" is not measuring what it claims on 35% of passes.

**Design consequences — gates doing what they were built to do:**
- §2 — the volume trailing-mean label puts the median bar below the line by construction (~65%).
- §3 — TREND holds 43.2% of voting weight, so concentration simultaneously raises confidence and
  fails diversity. The gate is working; the voter basket is unbalanced.
- 2 of 3 ensemble legs are RSI-extreme mean-reverters; with RSI in 30–70 all window, silence is correct.

## 10. Options — NOT recommendations

**[CORRECTNESS]**
1. Reconcile the action/confidence sourcing across MTF and the ensemble (§4). Effect on trade count
   on its own: none measured. Stops the funnel from lying.
2. Fix `signal_type` / WEAK-band confirmability (§2). Would move some ×0.5 to ×0.75 or confirmed.
3. Re-bucket MACD out of MOMENTUM, or split TREND, so diversity measures what it claims (§3).
   Note this makes diversity **harder**, not easier — 35% of current passes lose their sole non-TREND voter.
4. Funnel instrumentation: symbol attribution, terminal-stage semantics, `cycles`, series separation (§5).
5. Clamp post-MTF confidence; fix the `config.py` ceiling comment (§6).
6. Decide whether `/app/data` should be a persisted volume for ADR-015 (§6).

**[THRESHOLD RELAXATION — this class was declined once already]**
7. Remove or rescale the volume penalty. **Measured effect: 22 additional passes, not 1,011** —
   989 of the 1,011 that clear the floor then fail diversity (§3). And **0 additional ensemble
   emissions**: the two non-zero scores would go 0.033 → ~0.066 and 0.042 → ~0.084, both still
   under 0.10.
8. Renormalise ensemble weights over firing legs. **Does not unblock the 73 main events** (§4).
9. Lower `min_confidence` / `min_category_consensus` / `AGGREGATION_THRESHOLD`. Note the 95 ensemble
   near-misses are **manufactured artifacts** — signals the aggregator explicitly rejected, laundered
   by the score-based MTF consensus, mostly at 0.0% timeframe agreement. The threshold is catching
   junk, not suppressing opportunity. This argues **against** relaxing it.

All relaxations manufacture trades into a pipeline with **no demonstrated edge**
(CLAUDE.md §2: Sharpe −0.22 … −0.50) at ~0.11% round-trip on $100.

## 11. Not measured

- Whether any of these signals would have been **profitable**. Zero trades → zero P&L evidence.
  Nothing here is an edge claim.
- Whether the 240m diversity result is structural (n_effective ≈ 7 states over ~2 bar closes).
- Whether the short-side zero is regime or defect (§8).
- Risk-manager, min-notional ($5 Bybit vs $10 paper cap), exposure, cooldown and idempotency gates —
  never exercised, `evaluated = 0`.
- Whether post-MTF confidence has ever actually exceeded 1.0.
- Why `mean_reversion` fired 0 times was not traced to a specific branch.
- TA-side caching: the 20:00:17 sample lies in a new bar yet carries values identical to the previous
  bar's — consistent with caching, **not confirmed**.
- **116 of 181 verification agents died on an API session limit.** Findings marked *[unverified]*
  were never adversarially tested.
