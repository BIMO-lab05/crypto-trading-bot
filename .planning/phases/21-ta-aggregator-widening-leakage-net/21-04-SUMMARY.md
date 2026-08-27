---
phase: 21-ta-aggregator-widening-leakage-net
plan: 04
subsystem: technical-analysis (dashboard aggregate endpoint — gating tests + parameter single-sourcing)
tags: [ta-agg-01, p21-6, config-drift, single-source-of-truth, gating, mutation-testing, wiki]
requires:
  - 21-02 default_aggregate_limit field + derived warm-up floor validator
  - 21-01 tests/test_leakage_regression.py aggregate-path assertions
  - tests/test_aggregator_new_legs.py _patched() handler-namespace fixture
provides:
  - regression tests for the three ADX/SQZMOM/volume gates in get_aggregated_signal
  - TA Settings as sole declaration for every aggregate-path voter parameter
  - default_aggregate_limit wired into both kline fetches (closes 21-02's half-satisfied must-have)
  - wiki page describing the endpoint's real vote composition and dashboard-only status
affects:
  - dashboard consumers of GET /api/v1/indicators/signal/{symbol} (dashboard-only; no numeric change — see zero-delta table)
  - GET /api/v1/analysis/multi-timeframe/{symbol} — ENGINE-CONSUMED via enhanced_aggregator.py:242, not dashboard-only (no numeric change)
tech-stack:
  added: []
  patterns:
    - capture-dict out-param on a patch.multiple fixture to reach class-mock call_args
    - moved-settings routing proof (monkeypatch the field, require the call site to follow)
    - mutation-checked gates (delete the gate, require exactly its own test to go red)
key-files:
  created: []
  modified:
    - services/technical-analysis/app/handlers/analysis.py
    - services/technical-analysis/tests/test_aggregator_new_legs.py
    - wiki/modules/technical-analysis.md
key-decisions:
  - "The ADX zero-confidence test asserts on the AGGREGATOR_CONFIDENCE_FILTER log, not the payload. Both the :142 gate and the generic :158 weight filter produce an identical HOLD/0.5 response, so a payload-only test is tautological — proven by deleting the gate."
  - "Added a moved-settings routing proof beyond the equality assertions the plan specified. Every settings default equals the constructor default it replaced, so `kwargs[x] == settings.field` stays green against a hardcoded-but-equal literal. Measured: regressing the volume signal type left the per-field test green; only the routing test caught it."
  - "The stale `sqzmom_enhanced.py:687-688` line ref inside analysis.py's gating comment was NOT corrected — the plan requires that comment block preserved verbatim. The wiki cites the verified `:692` and flags the discrepancy."
requirements-completed: [TA-AGG-01, P21-6]
duration: ~70 min
completed: 2026-08-27
---

# Phase 21 Plan 04: TA-AGG-01 Residue + P21-6 Summary

The three gates that keep a dead ADX, a confident SQZMOM HOLD and an absent volume reading out of the dashboard aggregate vote are now regression-tested and mutation-proven; every voter parameter in both handlers resolves from TA `Settings`; and the wiki describes the vote the code actually casts rather than the one the 2026-05-23 requirement text imagined.

**Tasks:** 3/3 · **Files:** 0 created, 3 modified · **Commits:** 3 task + 2 doc · **TA suite:** 698 → **709 passed**

| Task | Commit | What landed |
|---|---|---|
| 1 — TA-AGG-01 gating tests | `c2c209b` | 3 gating tests + `volume_ratio` parametrized in `_patched()` |
| 2 — P21-6 settings sourcing | `1d2e9a2` | `analysis.py` rewire + 8 constructor/routing tests |
| 3 — wiki correction | `8eed75f` | `wiki/modules/technical-analysis.md` |
| — SUMMARY | `1bd0db3` | this file |
| — post-review scope fix | see log | wiki MTF scoping + this section (Deviation 5) |

## What this plan did NOT do (read before citing it)

**TA-AGG-01 was not a vote-widening job and no vote was widened.** ADX and SQZMOM already voted; volume was already a post-vote penalty. Per `21-CONTEXT.md`, the audit is authoritative over the roadmap's stale "RSI + MACD + TrendFilter only" premise. What was owed — and what shipped — is tests and documentation. The `aggregator_mode = minimal|full` env from the old requirement text was **not** added (CONTEXT drops it as YAGNI).

**Volume is still not a voter, in every code path.** Asserted explicitly per the plan's `<verification>`: `handlers/analysis.py` constructs `VolumeConfirmation` and applies its result only as a post-vote multiplier on an already-decided directional label (`analysis.py:204–221`); it never appends to `signals`. Two tests now pin label-equality across confirmed/unconfirmed and absent/disconfirming runs. The standing "Volume is NOT a voter" comment survived the rewire (`grep -c 'NOT a voter'` = 1).

## RED capture (Task 2, `tdd="true"`)

```
FAILED tests/test_aggregator_new_legs.py::test_trend_filter_is_constructed_from_settings
FAILED tests/test_aggregator_new_legs.py::test_adx_calculator_is_constructed_from_settings
FAILED tests/test_aggregator_new_legs.py::test_enhanced_sqzmom_is_constructed_from_settings
FAILED tests/test_aggregator_new_legs.py::test_volume_confirmation_period_and_signal_type_come_from_settings
FAILED tests/test_aggregator_new_legs.py::test_multi_timeframe_handler_is_settings_sourced_too
========================= 5 failed, 9 passed in 3.40s ==========================
```

Each failure read `EnhancedSqueezeMomentum was constructed without bb_length=, ... Captured call: call()` — the bare constructor, exactly. After the rewire: **15 passed**.

**The RED capture is recorded here rather than as a separate `test(...)` commit.** The plan's `<output>` specifies three commits with explicit pathspecs and folds Task 2's test changes into the implementation commit; that instruction is more specific than the generic TDD commit flow, and the plan frontmatter is `type: execute`, not `type: tdd`, so the plan-level gate sequence does not apply.

**One RED test passed that should not have.** `test_aggregate_kline_window_comes_from_settings` was green before the wiring existed, because the literal it replaced was itself `200`. That is the inversion trap `CLAUDE.md` names for the account size — numeric agreement is not routing — and it drove the strengthening below.

## Mutation checks — the tests are load-bearing, not merely green

A green test proves nothing about a gate it cannot see fail. Every gate and every wire was regressed in `analysis.py` and the suite re-run; the file was restored byte-for-byte each time (`restored: True`).

| Regression introduced | Result |
|---|---|
| ADX `and float(adx_conf) > 0.0` clause deleted | **CAUGHT** (1 failed) |
| SQZMOM directional-label gate deleted | **CAUGHT** (1 failed) |
| volume absence/disconfirmation distinction deleted | **CAUGHT** (1 failed) |
| aggregate `limit` back to a literal `200` | **CAUGHT** (1 failed) |
| multi-timeframe `limit` back to a literal `200` | **CAUGHT** (1 failed) |
| `TrendFilter` back to a bare constructor | **CAUGHT** (2 failed) |
| volume signal type back to a literal | **CAUGHT** (1 failed) — *see below* |
| `ADXCalculator(period=14)` hardcoded but numerically equal | **CAUGHT** (1 failed) |

**Two of these were NOT caught by the assertions the plan specified**, and that is the substantive finding of this plan:

1. **Volume signal type.** With only the per-field equality assertion, regressing `settings.default_volume_signal_type` to its literal left the test **green** — the setting and the literal are the same string.
2. **A hardcoded-but-equal `ADXCalculator(period=14)`.** Same shape: `period in call.kwargs` is satisfied and `14 == settings.default_adx_period` is satisfied.

Both are now caught by `test_every_voter_parameter_follows_a_moved_setting`, which monkeypatches all 17 settings fields to off-canon values and requires each constructor's `call_args.kwargs` to match exactly. The two kline-window tests carry the same routing proof.

## Verification results

| Check | Baseline | After | Verdict |
|---|---|---|---|
| TA suite (`services/technical-analysis`, `--no-cov`) | 698 passed | **709 passed**, 0 failed | +11 tests, no regressions |
| `test_aggregator_new_legs.py` | 4 passed | **15 passed** | 4 pre-existing unchanged |
| `test_leakage_regression.py -k aggregate` (cross-wave, T-21-04-05) | 8 passed | **8 passed** | Plan 21-01's assertion survived the rewire |
| `test_endpoint_defaults_from_settings.py` | 78 passed | 78 passed | untouched |

Task 3's verify command prints `WIKI_OK`.

Every task acceptance grep re-run:

```
bare constructors      -> (none)
limit=200              -> (none)
"breakout" literal     -> (none)
settings.default_aggregate_limit = 3   (need >= 2)
'NOT a voter'          = 1   (need >= 1)
'failure default'      = 1   (need >= 1)
'call_args' in tests   = 16  (need >= 4)
patch("app.indicators  = 0   (need 0)
Corrections 2026-08-26 = 1 · updated: 2026-08-26 = 1 · Corrections 2026-07-29 still present
```

## Expected behavior change: none, verified rather than assumed

The plan asks for any observed difference with the field that caused it. **There is none.** Every settings value already equalled the constructor default it replaced — resolved from the live `Settings` singleton, not read off `config.py`:

| Setting | Resolves to | Constructor default replaced | Δ |
|---|---|---|---|
| `default_trend_fast_period` | 50 | `TrendFilter.fast_period` 50 | — |
| `default_trend_slow_period` | 200 | `TrendFilter.slow_period` 200 | — |
| `default_adx_period` | 14 | `ADXCalculator.period` 14 | — |
| `default_adx_trending_threshold` | 25.0 | 25.0 | — |
| `default_adx_weak_trend_threshold` | 20.0 | 20.0 | — |
| `default_adx_strong_trend_threshold` | 30.0 | 30.0 | — |
| `default_sqzmom_bb_period` | 20 | `bb_length` 20 | — |
| `default_sqzmom_bb_mult` | 2.0 | 2.0 | — |
| `default_sqzmom_kc_period` | 20 | `kc_length` 20 | — |
| `default_sqzmom_kc_mult` | 1.5 | 1.5 | — |
| `default_sqzmom_mom_period` | 12 | `momentum_length` 12 | — |
| `default_volume_period` | 20 | `VolumeConfirmation.period` 20 | — |
| `default_volume_signal_type` | `'breakout'` | the literal | — |
| `default_aggregate_limit` | 200 | `limit=200` × 2 | — |

That zero delta is exactly why the defect was invisible and why the equality-only tests were insufficient. It also explains why `test_leakage_regression.py:827-833` — which already built `EnhancedSqueezeMomentum` from `SETTINGS.default_sqzmom_*` and compared against handler output — passed *before* this plan: it was numerically right and structurally lucky. It is now structurally right too.

**Note the constructor keywords do not match the settings field names**: `bb_length ← bb_period`, `kc_length ← kc_period`, `momentum_length ← mom_period`. A plausible-looking `bb_period=` would raise `TypeError`. The mapping is pinned by test.

## Constructor parameters deliberately left un-routed

The plan asks that a settings field with no matching constructor parameter be left alone and noted. The inverse case occurred — constructor parameters with **no** settings field — and got the same treatment:

| Class | Parameter left at its constructor default | Value |
|---|---|---|
| `TrendFilter` | `neutral_threshold` | 0.005 |
| `EnhancedSqueezeMomentum` | `use_true_range` | `True` |
| `VolumeConfirmation` | `breakout_threshold` | 1.2 |
| `VolumeConfirmation` | `strong_threshold` | 1.5 |

No settings field was invented for these. `VolumeConfirmation.breakout_threshold` is worth flagging: `21-CONTEXT.md` §P21-7 lists an engine-side mirror of the same `1.2` at `sqzmom_strategy_integration.py:284` and notes "**no TA settings field exists for this**". If P21-7 adds one, this call site should adopt it in the same change. No settings field exists in the reverse direction either — every `default_*` field the four classes could accept is now passed.

## Deviations from Plan

### 1. [Rule 2 — Missing critical] The plan's ADX assertion would have been tautological; asserted on the log instead

- **Found during:** Task 1.
- **Plan said:** "Assert against the aggregate outcome (label and/or confidence) versus an otherwise identical run with a positive ADX confidence."
- **Why that fails:** the handler has two zero-confidence filters. The gate under test is `analysis.py:142`; the generic INFRA-06 filter at `:158` drops any `(label, 0.0)` tuple regardless. With all other legs dead, both paths produce an identical `HOLD` / `0.5` payload, and `result["adx"]` merely echoes the mock's inputs. A comparison run does not help — that delta is produced by `:158` too.
- **Fix:** asserted on `AGGREGATOR_CONFIDENCE_FILTER` (`analysis.py:161`), which fires only when a zero-confidence tuple actually entered the aggregation list. Silence proves `:142` ran first. Added a **positive control** in the same test — a zero-confidence directional vote pushed through `TrendFilter`, which has no such gate — so the silence is known to be meaningful rather than a log that never fires.
- **Verified:** deleting `and float(adx_conf) > 0.0` turns this test red. The plan's specified assertion stays green under the same mutation.
- **Commit:** `c2c209b`

### 2. [Rule 2 — Missing critical] Added a moved-settings routing proof beyond the specified equality assertions

- **Found during:** Task 2, when `test_aggregate_kline_window_comes_from_settings` passed during the RED phase.
- **Issue:** the plan specifies comparing `call_args` "against `getattr(settings, field)` rather than against a literal, so a future canonical-value change stays auto-covered". That is correct and necessary but not sufficient: since every settings value currently equals the constructor default, the comparison cannot distinguish a routed parameter from a hardcoded-but-equal one. Confirmed empirically for two sites (volume signal type, ADX period) — the specified assertions stayed green under both regressions.
- **Fix:** `test_every_voter_parameter_follows_a_moved_setting` monkeypatches all 17 fields off-canon and asserts exact `call_args.kwargs` equality per class; the two kline-window tests each move `default_aggregate_limit` to 250 and require the fetch to follow. Exact-dict equality is deliberate — it also catches a stray argument Settings does not own.
- **Files:** `services/technical-analysis/tests/test_aggregator_new_legs.py` · **Commit:** `1d2e9a2`

### 3. [Rule 1 — Bug] Wiki line anchor corrected against source, not copied from the in-code comment

- **Found during:** Task 3, verifying the anchors before publishing them.
- **Issue:** `analysis.py:145`'s gating comment cites `sqzmom_enhanced.py:687-688` for the flat SQZMOM HOLD confidence. The actual `return 0.25` is at **`:692`** (`:690` is the explanatory comment). `:687-688` is prose inside a docstring. Copying it into the wiki would have published a ref that fails the "verify rather than trust" purpose of naming file:line at all.
- **Fix:** the wiki cites `sqzmom_enhanced.py:690–692` and explicitly flags that the in-code comment still carries the pre-move ref. `volume_confirmation.py:129–140` likewise corrected to `:129–142` (the dict closes at `:142`).
- **Not fixed in code:** the plan requires the gating comment block "preserved verbatim, editing around them". Editing the ref inside it would violate that. Recorded under *Deferred Issues*.
- **Commit:** `8eed75f`

### 4. [Rule 3 — Blocking] Format-hook avoidance; one self-inflicted escape-sequence bug

- All three files were edited through Bash + `pathlib` scripts rather than the `Edit` tool, per the wave-1 carry-forward warning about the 396-line reflow incident. Result: `analysis.py` diff is **45 insertions / 8 deletions**, surgical, and `git diff | grep -E '^[+-](import|from)'` returns **no output** — zero import churn.
- One script wrote `rstrip("\\n")` where a real newline was intended, injecting a literal `\n` token into the test file and breaking collection with `SyntaxError: unexpected character after line continuation character`. Caught immediately by the test run, repaired in place, suite re-run green. Recorded because it is the failure mode of the workaround itself.

### 5. [Rule 1 — Bug] "Dashboard-only" was scoped too broadly in the wiki

- **Found during:** post-completion review, grepping the engine for the
  *sibling* endpoint rather than only the one under test.
- **Issue:** the plan, CONTEXT and this SUMMARY all frame the aggregate path
  as dashboard-only, which is correct for `GET /api/v1/indicators/signal/
  {symbol}` (zero hits in `services/trading-engine/app/`). But
  `GET /api/v1/analysis/multi-timeframe/{symbol}` — served by
  `analyze_timeframe`, which **this plan modified** — *is* consumed by the
  engine: `trading-engine/app/aggregation/enhanced_aggregator.py:242`,
  reached from `signal_aggregator.py:986`. The wiki's dashboard-only
  blockquote opened the same section that then describes `analyze_timeframe`,
  so a reader could reasonably generalise the claim across both endpoints.
- **Why it matters:** it would understate the blast radius of any *future*
  edit to `analyze_timeframe`. It does not change this plan's outcome — the
  delta on that path is zero (TrendFilter 50/200 → 50/200, `limit` 200 → 200)
  — but "no behavior changed" and "no live path touched" are different claims
  and only the first is true.
- **Fix:** the wiki blockquote now names the exception explicitly and the
  `analyze_timeframe` sentence says it sits on a live engine path. The
  corrections section records the scoping.
- **Verified:** `grep -rn "indicators/signal" services/trading-engine/app/`
  → 0 hits. `grep -rn "analysis/multi-timeframe" services/trading-engine/app/`
  → 1 hit (`enhanced_aggregator.py:242`).

**Total deviations:** 5 (2 missing-critical test strengthenings, 2 doc corrections, 1 tooling workaround). **Impact:** the tests catch regressions the plan's specified assertions provably would not; no traded parameter moved; no numeric behavior changed.

## Deferred Issues

- **`analysis.py:145` cites `sqzmom_enhanced.py:687-688`; the constant is at `:692`.** Not corrected here — the plan mandates that comment block be preserved verbatim, and the surrounding reasoning is what makes the gate legible. The wiki carries the verified ref and names the discrepancy. A future touch of that comment block should fix it.
- **`21-02`'s `test_ichimoku_displacement.py:30-33` stale comments** remain stale (noted in that plan's SUMMARY, outside this plan's `files_modified`). Untouched.
- **The wiki's `updated:` field is pinned to `2026-08-26`, not the execution date `2026-08-27`.** This is deliberate: three of Task 3's acceptance criteria grep for the literal `2026-08-26` (`updated: 2026-08-26`, `Corrections 2026-08-26`). Do **not** "correct" it forward — that breaks the criteria. The phase's context, audit and plan all carry the 2026-08-26 date.

## Threat Flags

None. No new network endpoint, auth path, file access pattern, or schema change at a trust boundary.

Register dispositions:

| Threat | Disposition | Evidence |
|---|---|---|
| T-21-04-01 dead indicator casting a real vote | **mitigated** | both gates regression-tested; each mutation-checked to turn exactly its own test red |
| T-21-04-02 volume promoted to voter | **mitigated** | label asserted identical across confirmed/unconfirmed and absent/disconfirming; "NOT a voter" comment preserved (`grep -c` = 1) |
| T-21-04-03 constructor-default drift | **mitigated** | zero bare constructors; `call_args` pinned against `getattr(settings, …)` **and** against moved settings |
| T-21-04-04 docs asserting a vote the code lacks | **mitigated** | wiki rewritten against post-Task-2 source; anchors re-derived, one found stale and corrected |
| T-21-04-05 rewire breaking 21-01's leakage assertion | **mitigated** | `test_leakage_regression.py -k aggregate` 8 passed, before and after |
| T-21-04-06 wiki publishing file:line anchors | accepted | repo-local Obsidian vault, per plan |
| T-21-SC package installs | **n/a** | `git diff --stat 5153dd7..HEAD` = 3 files, no `requirements.txt`, zero installs |

## Next

TA-AGG-01 and P21-6 are closed. `21-02`'s half-satisfied must-have — "the aggregate endpoint's kline limit is a declared, floor-validated setting rather than a literal" — is now **fully** satisfied: declared and floor-validated by 21-02, wired by this plan.

Open in CONTEXT and untouched here: P21-7 (mirror-literal cluster, including the `VolumeConfirmation.breakout_threshold` 1.2 mirror noted above) and P21-8 (hygiene batch).

## Self-Check: PASSED

Modified files verified on disk:
- `services/technical-analysis/app/handlers/analysis.py` — FOUND
- `services/technical-analysis/tests/test_aggregator_new_legs.py` — FOUND
- `wiki/modules/technical-analysis.md` — FOUND

Commits verified in `git log`:
- `c2c209b` test(technical-analysis) — FOUND
- `1d2e9a2` fix(technical-analysis) — FOUND
- `8eed75f` docs(technical-analysis) — FOUND
- `1bd0db3` docs(21-04) SUMMARY — FOUND

Plan-level `<verification>` re-run at the final tree: TA suite **709 passed / 0 failed**, `test_leakage_regression.py -k aggregate` **8 passed**. `STATE.md` and `ROADMAP.md` deliberately untouched (orchestrator owns those writes).
