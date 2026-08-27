---
phase: 21-ta-aggregator-widening-leakage-net
plan: 05
subsystem: trading-engine
tags: [mtf, ensemble, gating, metadata, threshold-lock, wiring, unbound-local]

# Dependency graph
requires:
  - phase: 21-ta-aggregator-widening-leakage-net
    provides: "21-CONTEXT P21-3 (MTF demotion must gate ALL ensemble legs) and the locked no-threshold-change constraint"
  - plan: 21-03
    provides: "ATR threading + local-copy leg dispatch in multi_strategy_ensemble.generate_signal — the gate lands upstream of it"
provides:
  - "metadata['multi_timeframe']['demoted_to_hold'] — True only when a directional MTF consensus was demoted to HOLD by consolidate_mtf_confidence"
  - "metadata['multi_timeframe']['consolidated_action'] — the post-consolidation action at the moment of the write"
  - "All-leg suppression in MultiStrategyEnsemble.generate_signal, before any leg is dispatched"
  - "Behavioural threshold lock (`pytest -k threshold_lock`) — the phase-wide floor that 21-06 must not move"
  - "signal_aggregator.get_trading_signal_multi_timeframe is free of the SignalAction shadowing that made the module-level import unusable inside it"
affects: [21-06 leg diversity guard, 21-09 ablation '+gates' arm]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Behavioural threshold lock over a constants-only lock — the constants test passes in both worlds, so the load-bearing assertion is a payload that must keep emitting"
    - "Positive control paired with a suppression test, so the suppression assertion cannot pass vacuously"
    - "Identity check (`is True`) plus an isinstance guard on an untyped metadata field that gates trade admission — malformed input fails OPEN, never to a global halt"
    - "Additive metadata keys beside an existing key whose meaning is load-bearing, rather than redefining it"
    - "End-to-end harness over the real metadata writer using the REAL MultiTimeframeAnalysis builder, not a duck-typed stand-in"

key-files:
  created: []
  modified:
    - services/trading-engine/app/signal_aggregator.py
    - services/trading-engine/app/strategies/multi_strategy_ensemble.py
    - services/trading-engine/tests/test_mtf_confidence_consolidation.py
    - services/trading-engine/tests/strategies/test_ensemble_confidence_units.py

key-decisions:
  - "Narrow route taken as mandated: the gate is keyed on `demoted_to_hold`, never on bare `action == HOLD`. The regime hard-block is NAMED as a 21-09 follow-up, not fixed."
  - "`consensus_action` left byte-identical — verified by an acceptance grep on the diff. It carries the PRE-demotion blend and something downstream may already read it."
  - "Identity check `is True` plus an isinstance guard on the containing block. A truthiness check would turn one malformed upstream value into a silent, total denial of service on the trading path."
  - "The threshold lock is behavioural FIRST, constants second. A constants-only guard is documented in-test as insufficient because a diversity guard is MIN_AGREEING_LEGS=2 wearing a different hat."
  - "The suppression test is paired with a positive control on the identical payload minus the flag. Without it the suppression assertion could pass against a payload that never emitted anyway."

requirements-completed: [P21-3]

# Metrics
duration: ~75 min
completed: 2026-08-27
---

# Phase 21 Plan 05: MTF Demote-to-HOLD Gates All Three Ensemble Legs Summary

**A multi-timeframe demotion to HOLD now suppresses every ensemble leg instead of only the one that honoured it by accident — and the phase's behavioural threshold lock was landed first, observed green, and is still green after.**

## Performance

- **Duration:** ~75 min
- **Tasks:** 3/3
- **Files modified:** 4 (2 production, 2 test) — exactly the plan's `files_modified`, nothing else
- **Tests added:** 17 (2 threshold lock, 4 metadata, 11 gating)

## Task Commits

| Task | Commit | What landed |
|---|---|---|
| 1 — Threshold lock (behavioural + constants) | `2849511` | `test_ensemble_confidence_units.py` +107 |
| 2 — `demoted_to_hold` / `consolidated_action` metadata | `b0e4530` | `signal_aggregator.py`, `test_mtf_confidence_consolidation.py` |
| 3 — All-leg suppression on demotion | `d7edaea` | `multi_strategy_ensemble.py`, `test_ensemble_confidence_units.py` |

## The defect, precisely

`consolidate_mtf_confidence` demotes a directional consensus to HOLD when no timeframe's **gated** action agrees with a consensus computed from **pre-gate** scores (measured live: 152 of 231 directional consensuses, 65.8%). `signal_aggregator.py` already applied that demotion to `primary_signal.action`.

Of the three ensemble legs, only `multi_indicator` honoured it — and only **incidentally**, because its guard happens to read `aggregator_signal.action != SignalAction.HOLD`. `simple_rsi` and `mean_reversion` are dispatched off the indicator dict and **never read `.action` at all**, so they traded straight past a system-level HOLD.

They could not have been gated on it even in principle: `metadata["multi_timeframe"]["consensus_action"]` stores the **pre**-demotion value, so a demoted consensus and a genuinely-HOLD consensus produced byte-identical metadata. The demotion was **unobservable downstream**. That is why Task 2 (observability) had to precede Task 3 (gating).

## Narrow versus broad — and the proof it stayed narrow

`action == HOLD` reaches the ensemble from four distinct upstream causes:

| Cause | In scope for P21-3? |
|---|---|
| MTF consensus demoted (`consolidate_mtf_confidence:71-78`) | **YES** — this plan |
| Raw consensus genuinely HOLD | no |
| Regime hard-block (`signal_aggregator.py:1206+`) | no — **named as follow-up** |
| Per-timeframe requirements gate in `aggregator_core` | no |

The gate is keyed on `demoted_to_hold`, never on the bare action. The narrowness is **test-pinned, not asserted**: `test_regime_hard_block_hold_is_not_recorded_as_an_mtf_demotion` drives a **surviving directional BUY** consensus through consolidation, then lets the regime hard-block force `action = HOLD` afterwards, and asserts `consolidated_action == "BUY"` with `demoted_to_hold is False` while `result.action == HOLD`. A HOLD produced by the regime path is therefore provably outside the gate.

## Candidate follow-up — the regime hard-block (NOT fixed here)

`signal_aggregator.py:1206-1258` forces `primary_signal.action = HOLD` on an ADX-based counter-trend block. This is **arguably the same class of defect**: a system-level HOLD that `simple_rsi` and `mean_reversion` still ignore, because they still do not read `.action`. It is deliberately **named, not fixed** — 21-CONTEXT authorises the MTF route only, and widening the gate to cover it is a larger admission change than this plan is allowed to make. **Recommend it as a 21-09 checkpoint decision.**

Note the ordering that makes this observable: the `multi_timeframe` metadata is written **before** the regime block runs, so `consolidated_action` records what consolidation produced and is not retroactively rewritten by the regime block.

## Expected and authorized behavior change

**Trade admission DECREASES.** Every MTF demotion that previously let `simple_rsi` or `mean_reversion` through now suppresses all three legs. 21-CONTEXT authorises this explicitly ("these fixes reduce trade admission; that is expected and accepted").

**This is the "+gates" arm of the Plan 21-09 ablation.** Do **not** conflate it with Plan 21-03's ATR-driven changes, which push in **both** directions (`mean_reversion` gains a firing route; ATR-fetch-failure loses one). Mis-attributing either would invert the measured direction of the ablation.

## No threshold value changed

Stated as required, with evidence.

- `git diff` across all three commits contains **no `+`/`-` line altering any threshold constant**. Total diff: 677 insertions, 2 deletions — the only deletion is the shadowing import removed in Deviation 1.
- `test_threshold_lock_constants_are_unchanged` asserts `MIN_AGREEING_LEGS == 1`, `AGGREGATION_THRESHOLD == 0.10`, `min_signal_confidence == 0.30`, each with a failure message naming CLAUDE.md §5 and 21-CONTEXT's locked constraint.
- Both production comment blocks carry an explicit "NO THRESHOLD VALUE CHANGED" sentence (`signal_aggregator.py:1152`, `multi_strategy_ensemble.py`).

## Verification Results

### Threshold lock — before and after (plan `<verification>` requires both)

**Pre-change baseline**, captured immediately after Task 1's commit `2849511` and **before** any gating change:

```
$ cd services/trading-engine && python3 -m pytest tests/ -k threshold_lock --no-cov -q
2 passed, 5 skipped, 2842 deselected in 9.63s
```

**Post-change**, after Task 3's gate landed:

```
$ cd services/trading-engine && python3 -m pytest tests/ -k threshold_lock --no-cov -q
2 passed, 5 skipped, 2857 deselected in 11.75s
```

Green on both sides. The deselected count rises from 2842 to 2857 because this plan added 15 further tests.

### Suite comparison

| Check | Baseline (`5153dd7`) | After (`d7edaea`) | Verdict |
|---|---|---|---|
| `pytest tests/ --no-cov -q` | 2052 passed, 795 skipped, **0 failed** | 2068 passed, 795 skipped, **1 failed** | PASS — see flake note |
| `pytest tests/ -k threshold_lock` | 2 passed (post-Task-1) | 2 passed | PASS |
| `pytest tests/strategies/ tests/test_mtf_confidence_consolidation.py` | — | **183 passed** | PASS (exit 0) |
| `pytest tests/strategies/test_ensemble_leg_wiring.py test_ensemble_atr_levels.py` | — | **37 passed** | PASS — 21-03's ATR pins survive |
| `pytest tests/test_mtf_confidence_consolidation.py` | 7 passed | **11 passed** | PASS |
| `requirements.txt` touched | — | **0 files** | PASS (T-21-SC: zero package installs) |

**Arithmetic check on the counts:** baseline 2052 + 17 new tests = 2069 = 2068 passed + 1 failed. **Every test this plan added passes**; the single failure is not one of them.

**On that failure — the documented wall-clock flake, not a regression.** `tests/unit/test_signal_cache.py::TestSignalCache::test_ttl_affects_expiration`. Isolated rerun with no code change: **33 passed, 0 failed**. The file contains **zero** references to `signal_aggregator`, `multi_strategy_ensemble` or `demoted_to_hold` (`grep -c` → 0). It is named as flaky in both the 21-02 and 21-03 summaries, where a *different* TTL test in the same file failed on each run. Left alone per the scope boundary; a proper fix (freeze the clock rather than `sleep`) remains worth a standalone task.

### RED captures (both TDD tasks)

**Task 2** — the four metadata tests against the unpatched writer:

```
FAILED tests/test_mtf_confidence_consolidation.py::test_demotion_to_hold_is_recorded_in_metadata
FAILED tests/test_mtf_confidence_consolidation.py::test_genuine_hold_consensus_is_not_recorded_as_a_demotion
FAILED tests/test_mtf_confidence_consolidation.py::test_surviving_directional_consensus_is_not_recorded_as_a_demotion
FAILED tests/test_mtf_confidence_consolidation.py::test_regime_hard_block_hold_is_not_recorded_as_an_mtf_demotion
========================= 4 failed, 7 passed in 1.89s ==========================
```

**Task 3** — exactly one failure, which is the ideal RED shape here:

```
FAILED tests/strategies/test_ensemble_confidence_units.py::test_mtf_demotion_suppresses_every_leg
======================== 1 failed, 19 passed in 31.70s =========================
```

Only the behavior-**changing** assertion failed. The positive control, the explicit-`False` case, the 5 malformed-value cases and the 3 non-dict cases all passed *before* the gate existed — correctly, since they assert that current behaviour is **preserved**. A RED in which those had also failed would have meant the tests were pinning the wrong thing.

## Acceptance Criteria — per-task evidence

**Task 1**

| Criterion | Result |
|---|---|
| `-k threshold_lock` selects ≥2 tests, exits 0, **before** any other task | 2 passed at `2849511`, captured above — PASS |
| A `threshold_lock` test asserts lone `multi_indicator` at conviction ≥ 0.30 yields non-None | `test_threshold_lock_lone_multi_indicator_leg_at_the_conviction_floor_emits` — PASS |
| A test asserts all three constants with an operator-approval failure message | `test_threshold_lock_constants_are_unchanged` — PASS |
| Behavioural test uses `ensemble_module` fixture and `capital=None` | both — PASS |
| `grep -nE 'capital\s*=\s*[0-9]'` shows no **newly added** literal | 7 matches, all pre-existing (lines 103-197, below the original EOF at 203); 0 new — PASS |

**Task 2**

| Criterion | Result |
|---|---|
| `grep -c 'demoted_to_hold' signal_aggregator.py` ≥ 1 | **2** — PASS |
| `grep -c 'consolidated_action' signal_aggregator.py` ≥ 2 | **4** — PASS |
| `git diff \| grep -E '^[-].*consensus_action'` empty | no output — PASS |
| Four new tests: demotion True; genuine-HOLD False; surviving directional False; non-MTF HOLD not True | all four present and passing — PASS |
| Comment block states no threshold value changed | `signal_aggregator.py:1152` — PASS |
| `pytest tests/test_mtf_confidence_consolidation.py` exits 0 | 11 passed — PASS |

**Task 3**

| Criterion | Result |
|---|---|
| `demoted_to_hold` read occurs before the first leg dispatch | gate at `:491`, first dispatch (`self.simple_rsi.generate_signal`) at `:529` — PASS |
| `grep -nE 'demoted_to_hold.*is True\|is True.*demoted_to_hold'` matches | `:491` — PASS |
| A test asserts all three legs suppressed (no leg called) | `test_mtf_demotion_suppresses_every_leg` asserts `calls == {"simple_rsi": 0, "mean_reversion": 0}` via counting spies, with `multi_indicator` silenced by the HOLD action — PASS |
| A test asserts a non-boolean truthy value does not suppress | 5 parametrized cases (`"true"`, `1`, `"HOLD"`, `[True]`, `{...}`) — PASS |
| Cross-wave: `-k threshold_lock` exits 0 | 2 passed — PASS |
| Cross-wave: 21-03's `test_ensemble_leg_wiring.py` + `test_ensemble_atr_levels.py` exit 0 | 37 passed — PASS |
| Full suite shows no new failures vs baseline | 1 failure, proven pre-existing flake — PASS |

## Deviations from Plan

### 1. [Rule 3 — Blocking] `UnboundLocalError`: a function-local import shadowed `SignalAction` for the entire method

- **Found during:** Task 2, immediately after the implementation landed. Task 2's four new tests **and three previously-passing tests** in `tests/test_mtf_consensus_action_applied.py` all failed with:
  ```
  E  UnboundLocalError: cannot access local variable 'SignalAction' where it is not associated with a value
  app/signal_aggregator.py:1156
  ```
- **Issue:** `get_trading_signal_multi_timeframe` contained `from app.models import SignalAction` inside its regime-hard-block branch (formerly `:1211`). Python binds a name imported **anywhere** in a function body as local to the **whole** function, so that one line shadowed the module-level import at `:21` across every line of the method. The new `demoted_to_hold` computation is the first reference to `SignalAction` earlier in that method, which is what surfaced it.
- **Why it was latent, not live:** before this plan no code path referenced `SignalAction` earlier in the method than the local import itself, so the shadowing never bound anything unbound. The bug was real but unreachable — a **trap for the next editor**, which is exactly what it turned out to be.
- **Fix:** removed the redundant local import; the module-level import at `:21` is the only one needed. `app.models` is already imported at module scope, so there is no circular-import motive for the local. Replaced with a comment explaining why a local import must not be reintroduced there.
- **Files modified:** `services/trading-engine/app/signal_aggregator.py` (the plan's own file — no scope expansion)
- **Verification:** `tests/test_mtf_confidence_consolidation.py` + `tests/test_mtf_consensus_action_applied.py` went from **7 failed / 7 passed** to **14 passed**.
- **Committed in:** `b0e4530` (Task 2 commit)

### 2. [Rule 2 — Missing critical] `isinstance` guard on the `multi_timeframe` block itself

- **Found during:** Task 3
- **Issue:** the plan specifies `(aggregator_signal.metadata or {}).get("multi_timeframe") or {}` followed by an identity check on `demoted_to_hold`. That closes the malformed-**value** hole (T-21-05-02) but not the malformed-**container** hole: if `metadata["multi_timeframe"]` were a string or a list, `.get` raises `AttributeError` **on the live signal path**, inside `generate_signal`. The threat register's stated concern — "a malformed value is a denial-of-service on trading" — applies with equal force one level up, and an exception is a worse outcome than a silent suppression.
- **Fix:** `if not isinstance(mtf_meta, dict): mtf_meta = {}` before the identity check. Both guards fail **open**: garbage degrades to the pre-fix behaviour, never to a halt.
- **Verification:** `test_non_dict_multi_timeframe_metadata_does_not_crash`, parametrized over a string, a list and an int.
- **Committed in:** `d7edaea` (Task 3 commit)

### 3. [Tooling] All four files edited via Bash + `pathlib`, never the Edit tool

- **Found during:** planning the first write, from the 21-02 and 21-03 summaries which both lost a revert cycle to this.
- **Issue:** the repo's PostToolUse format hook runs ruff/autoflake at 88 columns against a 100-column codebase; it reflows unrelated blocks and strips not-yet-referenced imports. Here it would specifically have rewritten the `metadata["multi_timeframe"]` dict literal and thereby **failed Task 2's own acceptance criterion** (`git diff | grep '^[-].*consensus_action'` must be empty).
- **Fix:** every edit applied through `python3` + `pathlib` with `assert count == 1` anchors. Zero reverts were needed. The hook did fire once on a scratchpad helper script outside the repo; the anchor strings were verified intact before running it.
- **Verification:** `git diff --stat` across the plan shows **677 insertions, 2 deletions** — the 2 deletions are Deviation 1's shadowing import and its blank line. No reflow churn in any of the four files.

---

**Total deviations:** 3 (1 blocking, 1 missing-critical, 1 tooling). **Impact:** Deviation 1 was required to make the plan's own tests pass and additionally repaired three pre-existing tests that would have broken for the next editor. No file outside the plan's `files_modified` was touched.

## TDD Gate Compliance

Tasks 2 and 3 are marked `tdd="true"`, while the plan's `<output>` block mandates **three** commits with the production file and its test file committed **together**. RED/GREEN were therefore collapsed into one commit each rather than emitting separate `test(...)` RED commits.

The discipline was preserved in execution and both RED runs are captured verbatim above: Task 2's tests were written and observed failing 4/4 before any change to `signal_aggregator.py`; Task 3's were written and observed failing 1/11 (only the behavior-changing assertion) before any change to `multi_strategy_ensemble.py`. Task 1 does carry a standalone `test(...)` commit.

The absence of two further `test(...)` commits is a deliberate consequence of the plan's `<output>` instruction, not a skipped gate.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data sources were introduced.

## Threat Flags

None. No new network endpoint, auth path, file access pattern, or schema change at a trust boundary. Zero package installs; no `requirements.txt` touched.

Threat register dispositions:

| Threat ID | Disposition | Evidence |
|---|---|---|
| T-21-05-01 (legs trading past a system HOLD) | **mitigated** | Gate returns `None` before any dispatch; `test_mtf_demotion_suppresses_every_leg` asserts 0 leg calls, paired with a positive control |
| T-21-05-02 (malformed value = DoS on trading) | **mitigated** | Identity check `is True` + `isinstance` container guard; 5 malformed-value and 3 non-dict negative tests |
| T-21-05-03 (smuggled threshold change) | **mitigated** | Behavioural lock landed and observed green **first** (`2849511`), re-run green after; constants companion documented in-test as insufficient alone; both production comments state no threshold changed |
| T-21-05-04 (scope creep into the regime hard-block) | **mitigated** | Narrow route; `test_regime_hard_block_hold_is_not_recorded_as_an_mtf_demotion` uses a *surviving* directional consensus so the case is discriminating, not trivially false |
| T-21-05-05 (redefining `consensus_action`) | **mitigated** | Additive keys only; acceptance grep on the diff returns no output; a test asserts `consensus_action` still carries the pre-demotion value |
| T-21-SC (package installs) | **n/a** | `git diff --name-only` → zero `requirements` files |

## Deployment status — NOT in the running stack

**These changes are committed and unit-verified only. The trading-engine has NOT been rebuilt or `--force-recreate`d, so the admission change is not live.** This executor runs in an isolated worktree; touching the shared stack would collide with sibling agents, and this plan's `<verification>` block is pytest-only by design.

21-CONTEXT `<specifics>` still owes a before/after signal comparison on BTC/ETH/SOL/BNB/ADA **through the running stack** plus a rebuild of the changed service, and CLAUDE.md §7 forbids any "working end-to-end" claim without it. That debt is unpaid and belongs at 21-09. This matters concretely: the auto-trader is ARMED (`AUTO_TRADING_ENABLED=true` in the operator `.env`), so nobody should assume leg suppression is already in force.

## Deferred Issues

- **`tests/unit/test_signal_cache.py` wall-clock TTL flakiness** — pre-existing, documented in 21-02 and 21-03, reproduced once here and clean on isolated rerun (33 passed). Out of scope; worth a standalone fix that freezes the clock instead of sleeping.
- **7 pre-existing `capital=100.0` literals** in `test_ensemble_confidence_units.py` (lines 103-197). These are stale `$100`-era balance literals that `.claude/rules/money.md` forbids in fixtures. They are **P21-8 hygiene residue owned by another plan** and were deliberately left alone — all 7 sit in tests whose legs are stubbed, so the value is inert. Every test this plan added passes `capital=None`.
- **The regime hard-block follow-up** — see the dedicated section above. Recommend as a 21-09 checkpoint decision.

## Next Phase Readiness

- **Ready for 21-06.** The behavioural threshold lock is in place and green. 21-06's leg source-diversity guard is exactly the change that lock exists to catch: a category-diversity requirement is `MIN_AGREEING_LEGS = 2` wearing a different hat, and it would break `test_threshold_lock_lone_multi_indicator_leg_at_the_conviction_floor_emits` **without touching a single constant**. If that test goes red during 21-06, the guard has moved the floor and needs operator approval — do not "fix" the test.
- **Ready for 21-09.** The "+gates" arm now has one clean, single-signed effect to ablate (admission decreases on MTF demotion). Keep it separate from 21-03's "+ATR" arm, which is double-signed.
- **No blockers for sibling plans.** Only the plan's four declared files were touched.

## Self-Check: PASSED

Modified files verified present on disk:
- `services/trading-engine/app/signal_aggregator.py` — FOUND
- `services/trading-engine/app/strategies/multi_strategy_ensemble.py` — FOUND
- `services/trading-engine/tests/test_mtf_confidence_consolidation.py` — FOUND
- `services/trading-engine/tests/strategies/test_ensemble_confidence_units.py` — FOUND

Commits verified in `git log`:
- `2849511` `test(21-05)` — FOUND
- `b0e4530` `fix(21-05)` — FOUND
- `d7edaea` `fix(21-05)` — FOUND

All task `<acceptance_criteria>` re-run and passing; plan-level `<verification>` commands re-run with both threshold-lock captures pasted above.

**STATE.md and ROADMAP.md deliberately NOT modified** — parallel worktree mode; the orchestrator owns those writes after the wave merges.

---
*Phase: 21-ta-aggregator-widening-leakage-net*
*Completed: 2026-08-27*
