# Phase 21 — measured behaviour change, attributed per fix

**Phase:** 21-ta-aggregator-widening-leakage-net
**Plan:** 21-09 Task 1
**Run date:** 2026-08-27 (the filename carries the phase date, 2026-08-26; the measurement was executed on the 27th)
**Branch / HEAD at measurement:** `fix/ta-signal-path-phase-21` @ `5d108ad`

---

## What this is, and what it is not

This is an **admission and signal-count measurement**. It reports how many
constructed payloads produce a signal, how many survive the pre-fill stop check,
and which gate rejected the rest.

**No profitability result is computed or claimed here.** No P&L figure appears in
this document, no DSR and no CPCV were computed, and nothing below should be read
as evidence that any strategy has an edge. CLAUDE.md §2 forbids an edge claim
without DSR/CPCV, and profitability is explicitly not a goal of Phase 21
(21-CONTEXT `<domain>`). "Fewer admissions" is not "better" and "more admissions"
is not "worse" — these are correctness fixes, and the numbers below describe
*what changed*, not *what it is worth*.

## Reproduction

```
cd services/trading-engine
python3 scripts/ablation_ensemble_admission.py --arms all --check-determinism
```

Machine-readable output: add `--json <path>`.

**Payload-corpus source: constructed payloads.** The plan asked that
`scripts/backtest_ensemble.py` be tried first for a larger corpus. It does not
run on this host:

```
$ cd services/trading-engine && python3 scripts/backtest_ensemble.py
Traceback (most recent call last):
  File ".../scripts/backtest_ensemble.py", line 24, in <module>
    import psycopg2
ModuleNotFoundError: No module named 'psycopg2'
```

Installing a package is excluded from the executor's auto-fix rules, so the
harness fell back to constructed payloads as the plan provides for. Two further
reasons make that the better source anyway: `backtest_ensemble.py` is a P&L
replay (it would produce exactly the profitability numbers this document must not
contain), and its `build_trading_signal` never emits an MTF-demoted payload or
the ATR failure payload, so two of the four arms would have had nothing to
separate.

**Determinism.** The harness uses no randomness (`--seed` is accepted and printed
for the record only). Two consecutive full runs are byte-identical:

```
$ sha256sum run1.txt run2.txt
cc697a79ebc6d404f19395b2eac956f5f0f6ba1eb6e53afe9242709ca17db756  run1.txt
cc697a79ebc6d404f19395b2eac956f5f0f6ba1eb6e53afe9242709ca17db756  run2.txt
```

`--check-determinism` is stronger than re-running: it replays every arm in
**reverse order** and asserts the results are identical. Same-order re-runs
reproduce any corpus contamination and would pass regardless; reverse order does
not. Reported `determinism (reverse-order replay identical): True`.

## How the four arms are produced

There is no pre-phase checkout to run against by this wave, so the arms are
reconstructed from one tree by disabling each new behaviour individually via
targeted monkeypatching. The module is `importlib.reload`ed per arm so each
starts from a clean binding.

| Arm | `_atr_indicator` | `_atr_is_usable` | MTF demote gate | Diversity guard |
|---|---|---|---|---|
| `baseline` | forced `None` | permissive (`isinstance(d, dict)`) | neutralised | forced pass |
| `+ATR` | live | strict | neutralised | forced pass |
| `+gates` | forced `None` | permissive | live | live |
| `both` | live | strict | live | live |

**`_atr_is_usable` must be relaxed, not only `_atr_indicator` stubbed.** Plan
21-03 applied the shared predicate to `_atr_levels` as well
(`multi_strategy_ensemble.py:416`). Disabling only `_atr_indicator` would leave
the fetch-failure rejection active in all four arms and the +ATR admission
*decrease* would have measured exactly zero — the wrong answer, reported
confidently. The permissive predicate restores `_atr_levels`' pre-21-03 test
(`isinstance` only), which is what let the failure payload's populated 3% stops
be traded.

The MTF gate is inline with no patchable helper, so the gates-off arms strip
`demoted_to_hold` from a **deep copy** of the payload before calling — pre-phase
code never read the key, so an absent key is the faithful reconstruction. The
corpus is rebuilt by a factory on every arm, so no mutation carries forward.

**Every patch is asserted to have taken** before the arm runs
(`_assert_patches_took`), both by identity and behaviourally — e.g. the
permissive arm must actually read the failure payload's 3% stops back out. A
silently-unpatched arm reads as "no delta", which is the exact failure mode this
measurement exists to avoid (21-RESEARCH Pitfall 7 in a new costume).

## Measurement boundary — why admission is not the same as "signal produced"

`generate_signal` does **not** reject an `UNUSABLE_LEVEL` stop. It emits a signal
carrying `stop_loss = 0.0`, and `AutoTrader._ensemble_stops_are_consistent`
refuses it pre-fill. The harness therefore imports that real production predicate
(it does not re-implement it) and reports:

- **signals** — `generate_signal` returned an `EnsembleSignal`
- **admitted** — that signal also passed the pre-fill stop check

A measurement stopping at `generate_signal` would miss the **entire** +ATR
decrease. The corresponding bucket is named `rejected_prefill_unusable_stops` so
it does not read as one of Plan 21-06's five in-ensemble causes.

## The four-arm table

Corpus: 11 constructed payloads, identical across arms.

| arm | payloads | signals | admitted | insufficient_category_diversity | mtf_demoted | no_directional_legs | rejected_prefill_unusable_stops | score_below_threshold |
|---|---|---|---|---|---|---|---|---|
| `baseline` | 11 | 9 | **9** | 0 | 0 | 1 | 0 | 1 |
| `+ATR` | 11 | 9 | **8** | 0 | 0 | 1 | 1 | 1 |
| `+gates` | 11 | 4 | **4** | 5 | 1 | 1 | 0 | 0 |
| `both` | 11 | 6 | **5** | 3 | 1 | 1 | 1 | 0 |

**Counts reconcile.** For every arm, `admitted + sum(rejections) = 11`:
baseline 9+2, +ATR 8+3, +gates 4+7, both 5+6.

### Read the per-cause columns with care

The funnel and this harness both attribute an evaluation to the **first gate it
fails**, so the causes are mutually exclusive and **order-dependent**. The
diversity guard sits ahead of the agreement and score gates, so those buckets
shrink by construction. Only **`signals` and `admitted` are cross-arm deltas**;
a per-cause count moving between arms may be a re-attribution rather than a
behaviour change. `opposed_legs_below_threshold` below is the worked example.

## Per-scenario detail — the whole argument is in this table

| scenario | `baseline` | `+ATR` | `+gates` | `both` |
|---|---|---|---|---|
| `atr_unlocks_sma_route_buy` | ADMIT c=0.510 `simple_rsi` | ADMIT c=0.430 `mean_reversion`+`simple_rsi` | REJ diversity | ADMIT c=0.430 `mean_reversion`+`simple_rsi` |
| `atr_unlocks_sma_route_sell` | ADMIT c=0.800 `simple_rsi` | ADMIT c=0.625 `mean_reversion`+`simple_rsi` | REJ diversity | ADMIT c=0.625 `mean_reversion`+`simple_rsi` |
| `rsi_only_single_source` | ADMIT c=0.510 `simple_rsi` | ADMIT c=0.510 `simple_rsi` | REJ diversity | REJ diversity |
| `rsi_only_no_atr_payload` | ADMIT c=0.510 `simple_rsi` | ADMIT c=0.510 `simple_rsi` | REJ diversity | REJ diversity |
| `atr_fetch_failure_multi_leg` | ADMIT c=0.550 `multi_indicator` | **PREFILL-REJ** | ADMIT c=0.550 `multi_indicator` | **PREFILL-REJ** |
| `mtf_demoted_to_hold` | ADMIT c=0.530 | ADMIT c=0.470 | **REJ mtf_demoted** | **REJ mtf_demoted** |
| `mtf_not_demoted_control` | ADMIT c=0.530 | ADMIT c=0.470 | ADMIT c=0.530 | ADMIT c=0.470 |
| `multi_indicator_alone` | ADMIT c=0.550 | ADMIT c=0.550 | ADMIT c=0.550 | ADMIT c=0.550 |
| `rsi_plus_bollinger_route` | ADMIT c=0.480 | ADMIT c=0.480 | ADMIT c=0.480 | ADMIT c=0.480 |
| `no_legs_fire` | REJ no_directional_legs | REJ no_directional_legs | REJ no_directional_legs | REJ no_directional_legs |
| `opposed_legs_below_threshold` | REJ score_below_threshold | REJ score_below_threshold | REJ **diversity** | REJ **diversity** |

## Per-fix attribution

### The +ATR arm owns BOTH ATR effects — including the decrease

**Effect 1 — the `mean_reversion` SMA-deviation unlock (P21-1, Plan 21-03).**
Visible in the *leg set*, not in the top-line count. In `baseline`,
`atr_unlocks_sma_route_buy` fires on `simple_rsi` alone; in `+ATR` the same
payload fires on `mean_reversion`+`simple_rsi`. The `mean_reversion` leg is
present only when ATR is, because its `PRICE_BELOW_SMA` / `PRICE_ABOVE_SMA`
sub-signals are gated on `atr_value > 0` and `indicators["ATR"]` was written by
nothing before Plan 21-03. Directly probed: with a usable ATR the leg returns
`BUY 0.35 ['RSI_OVERSOLD', 'PRICE_BELOW_SMA']`; with the ATR key removed and
nothing else changed it returns `None`.

**Effect 2 — the `UNUSABLE_LEVEL`-on-fetch-failure rejection (also P21-1, Plan
21-03).** `atr_fetch_failure_multi_leg` is ADMITTED in `baseline` and `+gates`,
and **PREFILL-REJ** in `+ATR` and `both`. It moves with the ATR arm and is
completely unaffected by the gates arm. Pre-phase, `atr.py::_default_response()`
— whose `atr`/`atr_pct` are 0.0 while `stop_loss_long/short` are populated at a
hardcoded 3% nobody chose — was read by `_atr_levels` and **traded** as if it
were a real risk model. It is now refused.

**This second effect is an admission DECREASE that originates in the ATR work,
not in the gating work.** Filing it under +gates would invert the measured
direction of both arms: +ATR would show a pure increase it does not have, and
+gates would absorb a decrease it did not cause. 21-03's SUMMARY names this
explicitly and it is reproduced here as an executable measurement.

### The +gates arm owns the MTF suppression and the source-diversity block

**Effect 3 — MTF demote-to-HOLD gates all three legs (P21-3, Plan 21-05).**
`mtf_demoted_to_hold` is ADMITTED in both gates-off arms and rejected with cause
`mtf_demoted` in both gates-on arms. `mtf_not_demoted_control` is the positive
control on the identical payload shape minus the flag: it is admitted in all four
arms, so the suppression is attributable to the flag and not to the shape.

**Effect 4 — leg source-diversity block (P21-2, Plan 21-06).** `simple_rsi`
reads exactly one indicator key, so it is structurally a MOMENTUM-only leg.
`rsi_only_single_source` and `rsi_only_no_atr_payload` are admitted in both
gates-off arms and rejected with cause `insufficient_category_diversity` in both
gates-on arms.

Both are single-signed decreases.

### The interaction is the most important number here

`both` admits **5**, while `+gates` admits **4**. The +ATR unlock *rescues* two
payloads that the diversity guard alone rejects: once `mean_reversion` can see an
ATR, `atr_unlocks_sma_route_buy`/`_sell` span {MOMENTUM, TREND} instead of
{MOMENTUM} and clear the guard.

**A caveat the operator should read before checking direction.** The plan's
checkpoint criterion says "+ATR should show *more* admission from the
`mean_reversion` SMA-deviation unlock". At the top line it does **not**: `+ATR`
produces 9 signals, exactly as `baseline` does, and admits one **fewer**. That is
not a contradiction of 21-03 — it is what happens when the guard is off. With the
diversity guard disabled, `simple_rsi` alone already carried those payloads
through, so adding `mean_reversion` changes *which legs agree* and the resulting
confidence, not whether a signal is produced. The unlock's admission value is
only realised **in the presence of the gates**, which is exactly what the
`+gates` (4) → `both` (5) step measures. Reported as measured rather than as
predicted.

**Confidence moves down, not up, when the unlock fires** (0.510 → 0.430 and
0.800 → 0.625). The weighted score is an average over directional legs, and
`mean_reversion`'s conviction on the SMA route (0.35) sits below `simple_rsi`'s
(0.51 / 0.80). More corroboration, lower reported conviction. Noted because the
opposite is easy to assume.

### Order-dependence, worked

`opposed_legs_below_threshold` is rejected in every arm. In the gates-off arms
the cause is `score_below_threshold`; in the gates-on arms it is
`insufficient_category_diversity`. **The evaluation did not change — the
attribution did**, because the diversity guard now sits ahead of the score gate.
This single row is why the per-cause columns must not be differenced across arms.

### One further attribution caveat, carried forward from 21-05

The MTF gate **fails open** on both single-timeframe fallback paths: when the
primary timeframe fails to fetch, and when fewer than two timeframes are
available, `get_trading_signal_multi_timeframe` returns without writing a
`multi_timeframe` block at all, so no suppression occurs. A live window with
heavy MTF fetch failure will therefore **understate** the +gates decrease. The
constructed corpus does not model that; it is a property of the live path.

## Persisted leg weights

`StrategyPerformanceWeights` persists per-leg win rates to
`/app/data/ensemble_weights.json` and feeds `normalized_weights()` into every leg
contribution, so a drifting weight file is indistinguishable from a code-caused
delta (21-RESEARCH Pitfall 6).

Two independent controls:

1. **Pinned in the harness.** `STATE_PATH` is repointed to a throwaway path
   *before* any `StrategyPerformanceWeights` is constructed, and `_win_rates` is
   then set explicitly to `DEFAULT_WIN_RATE` for all three legs. Reported
   `leg_weights` are `{mean_reversion: 0.333333, multi_indicator: 0.333333,
   simple_rsi: 0.333333}` in every arm. The scratch file is never created
   (`exists=False` after the run) because nothing calls `record_outcome`.
2. **Digested before and after** the run regardless:

```
/app/data/ensemble_weights.json before: absent (no such file)
/app/data/ensemble_weights.json after : absent (no such file)
```

The path is a **container** path; the harness runs on the host, where it does not
exist. Recorded as measured — "absent before, absent after" — rather than
fabricating a hash. The harness exits non-zero if the two digests ever differ.

## No threshold value changed

Read off the imported class and settings at measurement time:

```
MIN_AGREEING_LEGS     = 1
AGGREGATION_THRESHOLD = 0.1
MIN_LEG_CATEGORIES    = 2
min_signal_confidence = 0.3
```

`MIN_LEG_CATEGORIES = 2` is not a new knob — it is the value `CoreAggregator`
already applies one level up via `voter.check_category_diversity(...,
min_categories=2)`.

Behavioural evidence, the phase-wide lock landed by Plan 21-05:

```
$ cd services/trading-engine && python3 -m pytest tests/ -k threshold_lock --no-cov -q
2 passed, 5 skipped, 2910 deselected in 9.00s
```

The lock is behavioural first: it asserts that a lone `multi_indicator` leg at
the conviction floor still emits. A constants-only guard passes in both worlds,
because a diversity requirement is `MIN_AGREEING_LEGS = 2` wearing a different
hat. That test is green, so the guard did not move the floor.

## Vocabulary audit

`grep -icE '\b(profit|p&l|pnl|improved|better|edge)\b'` on this file returns a
non-zero count. Every match sits inside an explicit non-claim or a scoping
sentence, enumerated here so the acceptance criterion can be checked by reading
rather than by trusting the grep:

- "What this is, and what it is not" — "No **profitability** result is computed
  or claimed here… nothing below should be read as evidence that any strategy has
  an **edge**… CLAUDE.md §2 forbids an **edge** claim without DSR/CPCV… 'Fewer
  admissions' is not '**better**'…" — the non-claim itself.
- Reproduction — "`backtest_ensemble.py` is a **P&L** replay (it would produce
  exactly the **profitability** numbers this document must not contain)" — the
  reason a corpus source was rejected.
- "How the four arms are produced" — "the wrong answer, reported confidently…
  **better** source anyway" — methodology, not a result.

No P&L figure, no return, no Sharpe, no win rate and no trade-level outcome
appears anywhere in this document.

---

*Produced by `services/trading-engine/scripts/ablation_ensemble_admission.py`.
Phase gate and live smoke: `.planning/evidence/21-phase-gate-2026-08-26.md`.*
