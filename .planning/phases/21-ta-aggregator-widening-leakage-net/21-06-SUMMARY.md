---
phase: 21-ta-aggregator-widening-leakage-net
plan: 06
subsystem: trading-engine
tags: [ensemble, diversity-guard, taxonomy, telemetry, signal-funnel, wiring, threshold-lock]

# Dependency graph
requires:
  - phase: 21-ta-aggregator-widening-leakage-net
    provides: "21-CONTEXT P21-2 (agreement counting must not present single-source information as multi-leg agreement) and the locked no-threshold-change constraint"
  - plan: 21-03
    provides: "ATR threading — mean_reversion's SMA-deviation firing route, which makes {MOMENTUM, TREND} a real leg-category pair rather than a hypothetical"
  - plan: 21-05
    provides: "the behavioural threshold lock this plan must not break, and the mtf_demoted rejection path that becomes cause #1 of five"
provides:
  - "Leg source-diversity guard in MultiStrategyEnsemble.generate_signal, reusing voter.INDICATOR_CATEGORIES — one taxonomy, not two"
  - "MultiStrategyEnsemble.MIN_LEG_CATEGORIES = 2, mirroring CoreAggregator's own check_category_diversity(min_categories=2)"
  - "EnsembleRejection(cause, detail) on self.last_rejection — five mutually-exclusive, machine-readable rejection causes"
  - "auto_trader._check_and_trade_ensemble records the specific cause in the funnel instead of one fixed ensemble_returned_hold bucket"
  - "_mean_reversion_source() — sub-signal prefix to indicator mapping, with a source-file drift scan"
affects: [21-09 ablation '+gates' arm, 21-09 funnel attribution analysis]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Derive from the shared taxonomy, never restate it — _KNOWN_INDICATOR_NAMES is computed from voter.INDICATOR_CATEGORIES, and a test asserts object identity so a copy cannot be introduced silently"
    - "Diverge from an analog deliberately and say so in-code: voter counts OTHER as an agreeing category; at leg level that would switch the guard off, so unmapped names are dropped instead"
    - "Fail OPEN on an unresolvable input, with a WARNING and an argument for why it cannot defeat the guard's purpose"
    - "One agreement predicate evaluated once (agreeing_leg_ids), with the count derived from it — never a second predicate for the second consumer"
    - "Structured rejection cause reset at the top of the call, not just set on each exit, because the producer is a process singleton iterating symbols"
    - "Source-file scan as a drift guard: the test regexes the real leg for sub-signals the mapping has not seen"

key-files:
  created:
    - services/trading-engine/tests/strategies/test_ensemble_diversity_guard.py
  modified:
    - services/trading-engine/app/strategies/multi_strategy_ensemble.py
    - services/trading-engine/app/auto_trader.py

key-decisions:
  - "The guard is a CATEGORY rule, not a leg count. multi_indicator alone passes — it already cleared CoreAggregator's two-category gate — which is the single row where the two rules diverge and the acceptance criterion that proves it."
  - "multi_indicator's diversity is asserted BY CONSTRUCTION, never re-derived from aggregator_signal.indicators or consensus_count. Re-deriving invites the two gates to drift apart."
  - "HOLD outcomes short-circuit the guard, mirroring voter.check_category_diversity. This is what keeps a zero-score evaluation attributed to the agreement gate rather than to diversity — an ordering fix the plan's insertion point alone would have got wrong."
  - "Deliberate divergence from voter.calculate_category_consensus: an unmapped indicator name is DROPPED, not counted as OTHER. Counting OTHER at leg level hands a single-source leg a free second category."
  - "Unresolvable leg sources FAIL OPEN with a WARNING. Defensible because simple_rsi is hardcoded {RSI} and always resolvable, and mean_reversion cannot be single-source at all (MIN_INDICATORS_ALIGNED = 2) — the guard's target case can never take that path."
  - "Rejection telemetry took 21-RESEARCH.md Pitfall 5 option (a), a structured cause. The funnel's `reason` is a free-form dict key, not a constrained set, so no schema change was needed."

patterns-established:
  - "Taxonomy reuse pinned by identity: `assert ensemble_module.INDICATOR_CATEGORIES is voter.INDICATOR_CATEGORIES`"
  - "Rejection identifiers as module constants (REJECT_*) so a test can assert they are distinct snake_case tokens"

requirements-completed: [P21-2]

# Metrics
duration: ~95 min
completed: 2026-08-27
---

# Phase 21 Plan 06: Leg Source-Diversity Guard + Per-Cause Rejection Telemetry Summary

**Two ensemble legs echoing one RSI print no longer count as independent confirmation, the strongest leg is explicitly exempt from double jeopardy, and the funnel's one collapsed `ensemble_returned_hold` bucket became five separately-attributable causes — with every locked threshold holding its value.**

## Performance

- **Duration:** ~95 min
- **Tasks:** 2/2
- **Files modified:** 3 (2 production, 1 new test file) — exactly the plan's `files_modified`, nothing else
- **Tests added:** 22 (11 guard behaviour + taxonomy, 11 rejection telemetry + funnel wiring)

## Task Commits

| Task | Commit | What landed |
|---|---|---|
| 1 — Leg source-diversity guard | `9fddba9` | `multi_strategy_ensemble.py`, new `test_ensemble_diversity_guard.py` (+680/-4) |
| 2 — Structured rejection cause in the funnel | `e59a174` | `multi_strategy_ensemble.py`, `auto_trader.py`, `test_ensemble_diversity_guard.py` (+408/-5) |

## The defect, precisely

Agreement was counted without asking what each leg had **read**. `simple_rsi` consumes exactly one indicator key — `indicators.get("RSI")` at `simple_rsi_strategy.py:153` — so it is structurally a MOMENTUM-only leg, and `mean_reversion`'s cheapest firing route starts from the same RSI print. Two legs echoing one number were presented downstream as independent multi-leg confirmation.

**Why it bites now, with the measured context.** Until 2026-08-23 the weighted score was normalised over all three legs' weight, so a lone leg was capped at 1/3 of its conviction and could not clear the downstream 0.30 floor whatever it believed (live SOLUSDT 2026-08-23 01:00–01:23: conviction 0.36 reported as 0.119 and rejected 36 times). The fix that normalises over **directional** legs only made single-leg admission reachable — which is precisely what turns single-source agreement into a trade. The guard closes a hole that the previous fix opened.

## It is a category rule, not a leg count — and here is the proof

The two rules agree on two rows out of three. The third is the whole argument, and it is now an executable assertion:

| Agreeing legs | Categories | Diversity guard | `MIN_AGREEING_LEGS = 2` |
|---|---|---|---|
| `simple_rsi` alone | {MOMENTUM} | **block** | block |
| `simple_rsi` + `mean_reversion` (BB or SMA co-signal) | 2 | **pass** | pass |
| `multi_indicator` alone | ≥ 2 by construction | **PASS** | block |

`multi_indicator` carries the full nine-voter gate stack and has already cleared `CoreAggregator`'s own `check_category_diversity(min_categories=2)`. Its diversity is asserted **by construction** and never re-derived from `aggregator_signal.indicators` or `consensus_count` — re-deriving invites the two gates to drift apart, and any divergence would silently double-jeopardy the strongest leg. The table is written into the production comment block so the guard cannot be read as a smuggled threshold change (T-21-06-03).

Row 3 is pinned twice: by this plan's `test_multi_indicator_alone_at_the_conviction_floor_still_emits` and by Plan 21-05's `test_threshold_lock_lone_multi_indicator_leg_at_the_conviction_floor_emits`. Both are green.

## One taxonomy, and one deliberate divergence from it

`voter.INDICATOR_CATEGORIES` is imported and used, not restated. `_KNOWN_INDICATOR_NAMES` is **derived** from it (`frozenset().union(*INDICATOR_CATEGORIES.values())`), so a name added upstream is automatically known here, and `_indicator_category()` delegates to `voter.SignalVoter.get_indicator_category` through one lazily-built instance. `test_the_guard_reuses_the_voter_taxonomy_rather_than_restating_it` asserts **object identity** against the voter's map, so a copy cannot be introduced without going red. The precedent is measured: MACD's 2026-08-23 move from MOMENTUM to TREND exists because a mis-bucketed indicator let the aggregator report "trend + momentum confirmation" when it had trend + trend, on 712 of 1,924 diversity passes.

**The divergence, stated so a reviewer does not read it as a bug.** `voter.calculate_category_consensus` counts `"OTHER"` as an agreeing category. This guard **drops** an unmapped name instead. At the voter level OTHER is one of many indicators; at the **leg** level it would hand a single-source leg a free second category and switch the guard off with nothing going red. Dropping errs strict, which is the safe direction, and two tests keep the mapping honest:

- `test_no_firing_leg_source_falls_through_to_other` — every sub-signal the `mean_reversion` ladder can emit resolves to a known category.
- `test_every_sub_signal_in_the_source_file_is_mapped` — **scans `mean_reversion_strategy.py` itself** for `_signals.append("TOKEN")` and fails if the file emits a token the mapping has not seen, or if this file lists one the source no longer emits. A guard that could go quietly vacuous is not a guard, so the scan also asserts its own regex matched something.

## Two mean_reversion firing routes, not one

The guard reads `MeanReversionSignal.indicators_aligned` rather than assuming Bollinger is always present. That matters because Plan 21-03 threaded a real ATR into the leg, which un-deadened the SMA-deviation branch (`mean_reversion_strategy.py:169`, gated on `atr_value > 0`):

| Route | `indicators_aligned` | Categories | Verdict |
|---|---|---|---|
| RSI + Bollinger | `RSI_OVERSOLD`, `BB_LOWER` | {MOMENTUM, VOLATILITY} | pass |
| RSI + SMA deviation (post-21-03) | `RSI_OVERSOLD`, `PRICE_BELOW_SMA` | {MOMENTUM, TREND} | pass |
| RSI only (not reachable today) | `RSI_EXTREME` | {MOMENTUM} | **block** |

A guard written against "Bollinger is always there" would have wrongly blocked the second row. The third row is `must_have` truth #1 stated literally; it is currently unreachable in production because `MIN_INDICATORS_ALIGNED = 2` requires a Bollinger or SMA co-signal, and the test says so — it pins the **rule**, so that if that constant ever moves the guard is already correct.

## Two design decisions the plan did not specify

### 1. HOLD short-circuit — an ordering fix, not decoration

The plan's insertion point (between the `agreeing_legs` count and the `MIN_AGREEING_LEGS` check) creates a mis-attribution the plan did not anticipate. When two legs cancel exactly, `weighted_score == 0`, **no leg agrees**, and the category union is empty — so a naive guard would reject with `insufficient_category_diversity` a case that is really the agreement gate's.

Mirroring `voter.check_category_diversity`'s HOLD short-circuit fixes it: the proposed action is computed as `BUY / SELL / HOLD` from the score's sign, and a HOLD outcome abstains. That keeps the insertion point the plan mandated **and** the attribution the plan's own Task 2 requires. Pinned by `test_hold_outcome_short_circuits_the_guard` (asserts `"diversity"` does **not** appear in the log) and `test_insufficient_agreeing_legs_reports_its_own_cause`.

Note the arithmetic that makes this safe rather than a hole: `weighted_score > 0` requires at least one BUY leg, so `agreeing_legs >= 1` whenever the score is directional. The short-circuit can only fire where nothing agreed anyway.

### 2. Fail OPEN on unresolvable leg sources

If an agreeing leg's `indicators_aligned` is missing or not a sequence, the guard **skips** with a WARNING rather than blocking. The argument that makes this defensible rather than convenient, and which is written into the code:

- `simple_rsi` is hardcoded to `{"RSI"}` and is **always** resolvable — the guard's actual target can never take this path.
- `mean_reversion` cannot be single-source at all (`MIN_INDICATORS_ALIGNED = 2`).

So failing open cannot defeat the guard's stated purpose, while failing **closed** on a malformed leg object would turn one upstream shape change into a silent halt of the whole trading path — the same doctrine Plan 21-05 applied to `demoted_to_hold`. Pinned by `test_unresolvable_leg_sources_fail_open`, which also asserts the WARNING is emitted, because failing open silently is how a guard quietly stops guarding.

## Rejection telemetry — the choice, made explicitly

21-RESEARCH.md Pitfall 5 requires the choice between (a) a structured rejection reason wired into the funnel and (b) parsing log lines to be **stated**. **This plan took (a).** Log parsing would tie the funnel's schema to prose no test pins.

**Finding that answers the plan's `read_first` on the funnel contract:** `SignalFunnel.reject`'s `reason` is a **free-form dict key** — `st.reasons.setdefault(reason, _ReasonStat())` in `signal_funnel.py:270`. It is **not** a constrained set (only `STAGES` is validated, via `_require_stage`). So new values needed **no schema change** and no downstream consumer can drop one for being unknown, closing T-21-06-06 without touching `signal_funnel.py`.

`generate_signal` now sets `self.last_rejection = EnsembleRejection(cause, detail)` on every return-None path through one writer (`_reject`), so a new path cannot be added without a cause:

| Cause | Path |
|---|---|
| `mtf_demoted` | Plan 21-05's MTF demote-to-HOLD gate |
| `no_directional_legs` | no leg produced a signal at all |
| `insufficient_category_diversity` | **this plan's guard** |
| `insufficient_agreeing_legs` | `MIN_AGREEING_LEGS` gate |
| `score_below_threshold` | `AGGREGATION_THRESHOLD` gate |

`generate_signal`'s signature and `Optional[EnsembleSignal]` return type are unchanged (verified: `git diff | grep -E '^[-].*def generate_signal'` produces no output). The cause rides on the instance, and `ensemble_returned_hold` is retained in `auto_trader` as the fallback so an unhandled path degrades to today's behaviour instead of crashing.

### The load-bearing part of T-21-06-05 is NOT the reset — do not remove it by accident

`last_rejection` lives on a **process singleton** (`get_ensemble()`). The reset at the top of `generate_signal` handles *sequential* reuse, which is what the tests pin. It does **not** handle interleaving: if two evaluations overlapped, symbol B's `_reject` could land between symbol A's `generate_signal` returning and A's funnel read, and A would be recorded under B's cause.

Two properties make that unreachable today, and **both are held by construction rather than by any assertion**:

1. `_check_and_trade_ensemble` is `await`ed **sequentially** inside the per-symbol loop (`auto_trader.py:988`) — not `asyncio.gather`ed.
2. There is **no suspension point between the write and the read**. `ensemble.generate_signal(...)`, the three `getattr` lines and `funnel.gate(...)` are all synchronous, so the event loop cannot interleave inside that window (verified: `grep -n await` over `:4779-4795` returns nothing).

**Inserting an `await` between those two points, or scheduling symbols concurrently, reintroduces T-21-06-05.** If either becomes necessary, carry the cause out of `generate_signal` as a return value or a per-call object instead of widening the window.

## Read this before quoting funnel counts at 21-09

The funnel attributes each evaluation to the **first gate it fails**, so the five causes are mutually exclusive and **order-dependent**. The diversity guard now sits ahead of both the agreement gate and the score gate, so those two buckets shrink **by construction** — that shift is not a behaviour change and must not be read as one. This warning is written into the `auto_trader` comment block, not only here.

## Expected and authorized behavior change

**Trade admission DECREASES.** `simple_rsi` firing alone no longer clears the ensemble. 21-CONTEXT authorises this explicitly ("these fixes reduce trade admission; that is expected and accepted").

**This is the "+gates" arm of the Plan 21-09 ablation**, together with Plan 21-05's MTF gate. Do **not** conflate it with Plan 21-03's ATR-driven changes, which push in **both** directions.

**No profitability claim is made or implied.** No P&L figure appears in this summary, and none should be derived from it — CLAUDE.md §2: no edge claim without DSR/CPCV, and profitability is explicitly not a goal of this phase.

## No threshold value changed

Stated as required, with evidence.

```
$ python3 -c "import app.strategies.multi_strategy_ensemble as m; from app.config import get_settings; ..."
MIN_AGREEING_LEGS     = 1
AGGREGATION_THRESHOLD = 0.1
min_signal_confidence = 0.3
MIN_LEG_CATEGORIES    = 2
```

`MIN_LEG_CATEGORIES = 2` is **not** a new knob: it is the value `CoreAggregator` already applies one level up, via `voter.check_category_diversity(..., min_categories=2)`. Both production comment blocks carry an explicit "NO THRESHOLD VALUE CHANGED" sentence, and `test_locked_thresholds_are_untouched_by_the_guard` asserts all four values.

## Verification Results

### Suite comparison

| Check | Baseline (`3199fa9`) | After (`e59a174`) | Verdict |
|---|---|---|---|
| `pytest tests/ --no-cov -q` | **2069 passed, 795 skipped, 0 failed** | **2091 passed, 795 skipped, 0 failed** | PASS |
| `pytest tests/ -k threshold_lock` | 2 passed | **2 passed** | PASS — 21-05's lock still green |
| `pytest tests/ -k "diversity or threshold_lock"` | — | **24 passed** (plan's Task-1 command) | PASS |
| `pytest tests/strategies/` | — | **194 passed** | PASS |
| `pytest tests/strategies/test_ensemble_leg_wiring.py test_ensemble_atr_levels.py tests/test_mtf_confidence_consolidation.py` | — | **48 passed** | PASS — 21-03 and 21-05 pins survive |
| `requirements*` files touched | — | **0** | PASS (T-21-SC) |

**Arithmetic check on the counts:** baseline 2069 + 22 new tests = **2091**. Every test this plan added passes, and **nothing regressed** — unlike 21-02/21-03/21-05, the documented `tests/unit/test_signal_cache.py` wall-clock TTL flake did not fire on either the baseline or the post-change run.

### RED captures (both TDD tasks)

**Task 1** — the full new file against the unmodified production code:

```
FAILED tests/strategies/test_ensemble_diversity_guard.py::test_simple_rsi_alone_is_blocked_as_single_source
FAILED tests/strategies/test_ensemble_diversity_guard.py::test_rsi_only_agreement_between_two_legs_is_still_blocked
FAILED tests/strategies/test_ensemble_diversity_guard.py::test_hold_outcome_short_circuits_the_guard
FAILED tests/strategies/test_ensemble_diversity_guard.py::test_unresolvable_leg_sources_fail_open
FAILED tests/strategies/test_ensemble_diversity_guard.py::test_no_firing_leg_source_falls_through_to_other
FAILED tests/strategies/test_ensemble_diversity_guard.py::test_every_sub_signal_in_the_source_file_is_mapped
FAILED tests/strategies/test_ensemble_diversity_guard.py::test_the_guard_reuses_the_voter_taxonomy_rather_than_restating_it
FAILED tests/strategies/test_ensemble_diversity_guard.py::test_locked_thresholds_are_untouched_by_the_guard
[... 8 further Task-2 failures ...]
======================== 16 failed, 5 passed in 31.26s =========================
```

The **5 that passed before any change** are the right ones and the reason the RED is meaningful: `test_multi_indicator_alone_at_the_conviction_floor_still_emits`, the two `mean_reversion` co-firing routes, the funnel fallback, and the return-type assertion. Those assert that current behaviour must be **preserved**. A RED in which they had also failed would have meant the tests were pinning the wrong thing.

**Task 2** — after Task 1's guard landed, exactly the telemetry assertions failed:

```
FAILED ...::test_mtf_demotion_reports_its_own_cause
FAILED ...::test_no_directional_legs_reports_its_own_cause
FAILED ...::test_diversity_block_reports_its_own_cause
FAILED ...::test_insufficient_agreeing_legs_reports_its_own_cause
FAILED ...::test_score_below_threshold_reports_its_own_cause
FAILED ...::test_a_successful_signal_clears_the_cause
FAILED ...::test_the_cause_does_not_carry_over_between_calls
FAILED ...::test_all_four_causes_are_distinct_identifiers
FAILED ...::test_the_funnel_records_the_specific_cause
======================== 9 failed, 13 passed in 49.02s =========================
```

GREEN after: **22 passed**.

## Acceptance Criteria — per-task evidence

**Task 1**

| Criterion | Result |
|---|---|
| Import of the taxonomy from `app.aggregation.voter` | `:23 from app.aggregation.voter import INDICATOR_CATEGORIES, SignalVoter` — PASS |
| `grep -c 'MOMENTUM'` reveals no re-declared category map | 5 matches, **all in comments/docstrings** (`:43`, `:87`, `:561`, `:911`, `:929`); no dict literal — PASS |
| **Load-bearing:** lone `multi_indicator` at conviction ≥ 0.30 returns non-None | `test_multi_indicator_alone_at_the_conviction_floor_still_emits` — PASS |
| **Load-bearing:** `-k threshold_lock` exits 0 after the guard lands | 2 passed — PASS |
| `simple_rsi` alone is blocked | `test_simple_rsi_alone_is_blocked_as_single_source` — PASS |
| Both `mean_reversion` routes ({MOMENTUM, VOLATILITY} and {MOMENTUM, TREND}) pass | two dedicated tests — PASS |
| `MIN_AGREEING_LEGS` still 1, `AGGREGATION_THRESHOLD` still 0.10 | proven by value, see the block above — PASS **with a caveat on the regex, below** |
| Comment block states no threshold value changed | present in both edited regions — PASS |
| `grep -nE 'capital\s*=\s*[0-9]'` on the new test file returns nothing | no output — PASS |
| `pytest tests/strategies/ --no-cov -q` exits 0 | 194 passed — PASS |

**Task 2**

| Criterion | Result |
|---|---|
| `grep -c` for the four cause identifiers ≥ 4 | **4** — PASS |
| `ensemble_returned_hold` appears in `auto_trader.py` only as a fallback | 3 matches: `:4761` and `:4774` are comment prose, `:4784` is the `or` fallback. Zero hardcoded `reason=` — PASS |
| A test proves the cause does not carry over between calls | `test_the_cause_does_not_carry_over_between_calls` (mtf_demoted then score_below_threshold) — PASS |
| A test asserts a successful signal clears the cause | `test_a_successful_signal_clears_the_cause` — PASS |
| `generate_signal` signature and return type unchanged | `git diff \| grep -E '^[-].*def generate_signal'` → no output — PASS |
| Cross-wave: `-k threshold_lock` exits 0 | 2 passed — PASS |
| Cross-wave: leg wiring + ATR levels + MTF consolidation exit 0 | 48 passed — PASS |
| Full suite shows no new failures vs baseline | 2069 → 2091, **0 failed both sides** — PASS |

### One acceptance criterion is unsatisfiable as written — plan defect, not a code defect

```
$ grep -nE 'MIN_AGREEING_LEGS\s*[:=]\s*[0-9]' app/strategies/multi_strategy_ensemble.py
597:        # It also contradicted MIN_AGREEING_LEGS = 1. That knob says one leg
```

The only match is a **comment**. Black wrapped the declaration across two lines long before this phase —

```python
    MIN_AGREEING_LEGS = (
        1  # at least 1 leg must fire (ensemble still applies aggregation_threshold)
    )
```

— so the regex has never matched the assignment, on the pristine file at `3199fa9` or now. The same applies to `grep -nE 'AGGREGATION_THRESHOLD\s*[:=]'`, which matches `:239 AGGREGATION_THRESHOLD = (` without showing `0.10`.

**This was verified against the pristine file before any edit**, and the constants were deliberately **not** reformatted onto one line to satisfy it: rewrapping a locked constant is exactly the cosmetic diff a reviewer misreads as a threshold change. The values are proven instead by reading them off the imported class (output pasted above) and by `test_threshold_lock_constants_are_unchanged` plus this plan's `test_locked_thresholds_are_untouched_by_the_guard`. Recorded here so a future auditor does not re-derive it.

## Deviations from Plan

### 1. [Rule 2 — Missing critical] HOLD short-circuit added to the guard

- **Found during:** Task 1, reasoning about the plan's mandated insertion point.
- **Issue:** the plan places the guard between the `agreeing_legs` count and the `MIN_AGREEING_LEGS` check, and separately requires (Task 2) that each cause be separately attributable. Those two requirements collide when `weighted_score == 0`: no leg agrees, the category union is empty, and a naive guard rejects with `insufficient_category_diversity` a case that belongs to the agreement gate. Every mutually-cancelling evaluation would have been mis-attributed, and the 21-09 ablation would read a diversity delta that never happened.
- **Fix:** compute a proposed action from the score's sign and short-circuit on HOLD, exactly as `voter.check_category_diversity` does. The insertion point the plan mandated is unchanged.
- **Verification:** `test_hold_outcome_short_circuits_the_guard` (asserts `"diversity"` is absent from the log) and `test_insufficient_agreeing_legs_reports_its_own_cause`.
- **Committed in:** `9fddba9` / `e59a174`

### 2. [Rule 2 — Missing critical] `agreeing_legs` refactored to one predicate, not two

- **Found during:** Task 1.
- **Issue:** the existing count is a `sum(...)` over `leg_signals.values()`. The guard needs the leg **identities**, so a second copy of the same predicate would have been the obvious edit — and a divergence between the two would make the guard evaluate a different set of legs than the gate below it. That is the drift class this phase exists to remove.
- **Fix:** one list comprehension over `.items()` producing `agreeing_leg_ids`, with `agreeing_legs = len(...)` derived from it. This accounts for 3 of the commit's 4 deletions.
- **Verification:** all 21-05 and 21-03 ensemble tests still pass (48 + 194).
- **Committed in:** `9fddba9`

### 3. [Rule 1 — Correctness] Unmapped indicator names dropped rather than counted as `OTHER`

- **Found during:** Task 1, reading `voter.calculate_category_consensus`.
- **Issue:** the analog **counts** `"OTHER"` as an agreeing category. Copying that behaviour would hand a single-source leg a free second category the moment any new `mean_reversion` sub-signal appeared — silently switching the guard off, with nothing going red.
- **Fix:** `_mean_reversion_source` returns `None` for unrecognised tokens, and unknown names are excluded from the union with a WARNING. Backed by the source-file drift scan.
- **Verification:** `test_no_firing_leg_source_falls_through_to_other`, `test_every_sub_signal_in_the_source_file_is_mapped`.
- **Committed in:** `9fddba9`

### 4. [Tooling] Both production files edited via Bash + `pathlib`; the two commits split around a parked test half

- **Found during:** planning the first write, from 21-02/21-03/21-05, which each lost a cycle to the format hook (ruff at 88 columns against a 100-column codebase; reflows unrelated blocks and strips imports).
- **Issue A:** every production edit was applied through `python3` + `pathlib` with `assert count == 1` anchors. Zero reverts were needed. **Diff evidence:** Task 1 = 258 insertions / **4 deletions** (1 typing import line, 3 the refactored `sum(...)`); Task 2 = **5 deletions**, all the removed hardcoded `reason=`/`detail=` block. No reflow churn in either file.
- **Issue B:** the plan's `<output>` mandates two commits that each carry the production file **and** the single test file. Committing the whole test file at commit 1 would have landed 9 red Task-2 tests. The Task-2 half was parked in the scratchpad, commit 1 landed **green (11 passed)**, then it was restored for Task 2. `git stash` was never used — it is a shared ref across worktrees.
- **Verification:** commit 1 was observed green in isolation before committing; commit 2 green at 22 passed.

---

**Total deviations:** 4 (2 missing-critical, 1 correctness, 1 tooling). **Impact:** deviations 1–3 were required for the plan's own Task 2 acceptance criteria to be meaningful and for the guard not to be defeatable by a future edit. No file outside the plan's `files_modified` was touched.

## TDD Gate Compliance

Both tasks are marked `tdd="true"`, while the plan's `<output>` block mandates **two** commits with each production file and its test file committed **together**. RED/GREEN were therefore collapsed into one commit each rather than emitting separate `test(...)` RED commits.

The discipline was preserved in execution and **both RED runs are captured verbatim above**: Task 1's tests were written and observed failing 16/21 before any change to `multi_strategy_ensemble.py`, with the 5 passing being exactly the preservation assertions; Task 2's were observed failing 9/22 after the guard landed and before any telemetry code existed.

The absence of two `test(...)` commits is a deliberate consequence of the plan's `<output>` instruction, not a skipped gate.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data sources were introduced.

## Threat Flags

None. No new network endpoint, auth path, file access pattern, or schema change at a trust boundary.

Threat register dispositions:

| Threat ID | Disposition | Evidence |
|---|---|---|
| T-21-06-01 (single-source presented as independent agreement) | **mitigated** | Category-union guard reusing `voter.INDICATOR_CATEGORIES` (identity-pinned); `mean_reversion` categories derived from its own `indicators_aligned`, both routes tested |
| T-21-06-02 (double jeopardy on `multi_indicator`) | **mitigated** | Diverse by construction, never re-derived; pinned by this plan's test **and** by 21-05's `threshold_lock`, both green |
| T-21-06-03 (guard as a smuggled `MIN_AGREEING_LEGS = 2`) | **mitigated** | Three-row table in the code comment; constants re-asserted by value; the divergent row is an explicit test |
| T-21-06-04 (funnel detail misdescribing causes) | **mitigated** | Five per-cause identifiers replace the fixed string; option (a) chosen and its rationale recorded |
| T-21-06-05 (stale cause reported for another symbol) | **mitigated** | Reset at the top of `generate_signal`; `test_the_cause_does_not_carry_over_between_calls`. **See the concurrency note below — the reset alone is not the whole invariant.** |
| T-21-06-06 (unknown `reason` silently dropped) | **mitigated** | Contract checked: `reason` is a free-form dict key, not a constrained set — no schema change needed; `ensemble_returned_hold` retained as fallback, tested |
| T-21-SC (package installs) | **n/a** | `git status` → zero `requirements` files touched |

## Deployment status — NOT in the running stack

**These changes are committed and unit-verified only. The trading-engine has NOT been rebuilt or `--force-recreate`d, so the admission change is not live.** This executor runs in an isolated worktree; touching the shared stack would collide with sibling agents, and this plan's `<verification>` block is pytest-only by design.

21-CONTEXT `<specifics>` still owes a before/after signal comparison on BTC/ETH/SOL/BNB/ADA **through the running stack** plus a rebuild of the changed service, and CLAUDE.md §7 forbids any "working end-to-end" claim without it. That debt is unpaid and belongs at 21-09. This matters concretely: the auto-trader is ARMED (`AUTO_TRADING_ENABLED=true` in the operator `.env`), so nobody should assume leg-diversity suppression is already in force.

## Deferred Issues

- **The regime hard-block follow-up** (`signal_aggregator.py:1206-1258`), named by 21-05 and still open. Unchanged by this plan.
- **7 pre-existing `capital=100.0` literals** in `test_ensemble_confidence_units.py` (lines 103–197) — P21-8 hygiene residue owned by another plan. Every test this plan added passes `capital=None`.
- **`tests/unit/test_signal_cache.py` wall-clock TTL flakiness** — documented in 21-02/21-03/21-05. It did **not** fire on either run here; a proper fix (freeze the clock rather than `sleep`) remains worth a standalone task.
- **Funnel-singleton hygiene, for the post-merge orchestrator.** The two async tests in `test_ensemble_diversity_guard.py` call `get_signal_funnel().reset()` on the process-local singleton and do **not** restore prior state — the same pattern the module already exposes as a test hook. Green in this suite and in the full 2091-test run. If the merged wave goes red in `tests/test_signal_funnel.py` or any other funnel-reading test, look here first; the fix is an autouse fixture that resets around rather than inside those two tests.

## Next Phase Readiness

- **Ready for 21-09.** The "+gates" arm now has two clean, single-signed effects to ablate (MTF demotion from 21-05, leg source diversity from 21-06), and the funnel can attribute them separately. Keep both separate from 21-03's "+ATR" arm, which is double-signed. **Read the order-dependence note above before comparing bucket counts.**
- **No blockers for sibling plans.** Only the plan's three declared files were touched.

## Self-Check: PASSED

Files verified present on disk:
- `services/trading-engine/app/strategies/multi_strategy_ensemble.py` — FOUND
- `services/trading-engine/app/auto_trader.py` — FOUND
- `services/trading-engine/tests/strategies/test_ensemble_diversity_guard.py` — FOUND

Commits verified in `git log`:
- `9fddba9` `fix(trading-engine): require source diversity across agreeing ensemble legs (P21-2)` — FOUND
- `e59a174` `fix(trading-engine): report the specific ensemble rejection cause in the trade funnel` — FOUND

All task `<acceptance_criteria>` re-run against the committed state (24 passed for `-k "diversity or threshold_lock"`); plan-level `<verification>` commands re-run with both suite counts and the threshold-lock capture pasted above.

**STATE.md and ROADMAP.md deliberately NOT modified** — parallel worktree mode; the orchestrator owns those writes after the wave merges.

---
*Phase: 21-ta-aggregator-widening-leakage-net*
*Completed: 2026-08-27*
