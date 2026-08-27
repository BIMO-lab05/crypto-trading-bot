---
phase: 21-ta-aggregator-widening-leakage-net
plan: 07
subsystem: trading-engine (config single-sourcing / signal-path correctness)
tags: [config-drift, mirror-literal, single-source-of-truth, adx, sqzmom, regime, sentinel]

# Dependency graph
requires:
  - plan: 21-02
    provides: "the param-omission precedent (fetch_macd / fetch_sma) and the outbound-request capture idiom"
  - plan: 21-05
    provides: "the current signal_aggregator.py state (demoted_to_hold metadata, SignalAction import fix)"
provides:
  - "settings.adx_weak_trend_threshold — the engine-side mirror of technical-analysis default_adx_weak_trend_threshold, applied by the ADX vote gate and the SQZMOM trend gate"
  - "settings.sqzmom_volume_ratio_min — engine-owned volume floor for the SQZMOM gate, no TA counterpart"
  - "handlers/signals.TA_REGIME_TO_ENGINE_REGIME — the explicit TA→engine regime vocabulary map, with UNKNOWN + WARNING for unmapped labels"
  - "tests/aggregation/test_mirror_literals.py — 31-case declaration + behavioural guard over all five P21-7 sites"
affects: [21-08 hygiene batch, 21-09 ablation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Behavioural setting-wiring test paired with a default-value positive control, so a de-literalled-but-unwired gate still fails"
    - "Log messages interpolate the RESOLVED threshold; a literal inside a message string is banned by the same source guard as the comparison"
    - "Explicit cross-service vocabulary map with a fail-loud UNKNOWN default, instead of passing a foreign enum straight into a branch table"
    - "Deleted classifier retained inside the test file only, as an executable equivalence oracle"

key-files:
  created:
    - services/trading-engine/tests/aggregation/test_mirror_literals.py
  modified:
    - services/trading-engine/app/config.py
    - services/trading-engine/app/signal_aggregator.py
    - services/trading-engine/app/strategies/sqzmom_strategy_integration.py
    - services/trading-engine/app/handlers/signals.py
    - services/trading-engine/app/aggregation/market_regime.py

key-decisions:
  - "STRONG_TREND is mapped onto TRENDING rather than passed through. TA's regime vocabulary has four labels; the engine's deleted re-derivation had three, and STRONG_TREND has no consumer — passing it raw would have silently dropped every ADX >= 30 bar onto the neutral multiplier. That is a behaviour regression 21-CONTEXT does not authorise."
  - "A missing ADX now resolves to None on BOTH the success and the failure path. The plan's acceptance grep only covers the success path's `.get(\"adx\", 25)`; the except branch fabricated the identical 25 and is the same defect (Rule 2)."
  - "`adx_period` removed from MarketRegimeDetector.__init__ outright, not retained. Zero callers passed it; keeping it would have been an argument that silently does nothing."
  - "The three research literals (ADX 20, volume 1.2) stay recorded in the provenance comment as *research values*, while the *applied* values read from Settings — provenance and application are now separable."
  - "Regime `confidence` left at the hardcoded 0.7 rather than switched to TA's own regime confidence. TA returns one, but adopting it is a numeric behaviour change outside this plan's mandate."

patterns-established:
  - "Cross-service vocabulary map: when the engine consumes a label another service owns, map it explicitly, default to the unknown sentinel, and log the unmapped case by name"
  - "Equivalence oracle: keep the deleted derivation in the test file and assert the new read reproduces it for every input the upstream service can produce"

requirements-completed: [P21-7]

# Metrics
duration: ~90 min
completed: 2026-08-27
---

# Phase 21 Plan 07: Mirror-Literal Cluster Summary

**All five P21-7 sites now resolve from a declared engine `Settings` field or from the technical-analysis response itself — and a failed ADX read, which used to be reported as a confident TRENDING regime, is now reported as absent.**

## Performance

- **Duration:** ~90 min
- **Tasks:** 3/3
- **Files:** 1 created, 5 modified — exactly the plan's `files_modified`, nothing else
- **Tests added:** 31

## Task Commits

| Task | Commit | What landed |
|---|---|---|
| 1 — Mirror `Settings` fields + declaration guard | `dff465b` | `config.py` (+54), `test_mirror_literals.py` (new) |
| 2 — Three Settings-backed sites | `a30540f` | `signal_aggregator.py`, `sqzmom_strategy_integration.py`, tests |
| 3 — Read TA's regime; omit TA-owned ADX period | `0046bd2` | `handlers/signals.py`, `market_regime.py`, tests |

## The five sites, and what each resolves from now

| Site | Was | Now |
|---|---|---|
| `signal_aggregator.py:483-486` (`fetch_adx` vote gate) | `adx_val >= 20.0` twice | `self.settings.adx_weak_trend_threshold`, read once into a local |
| `sqzmom_strategy_integration.py:253-254` (ADX demotion) | `adx_val < 20.0` | same field |
| `sqzmom_strategy_integration.py:300-301` (volume demotion) | `ratio < 1.2` | `self.settings.sqzmom_volume_ratio_min` |
| `handlers/signals.py:191-205` (regime) | three-branch re-derivation from 25 / 20 | TA's own `regime`, via `TA_REGIME_TO_ENGINE_REGIME` |
| `market_regime.py:249` (ADX request) | `"period": self.adx_period` | omitted; the constructor parameter is gone too |

## The one place output can differ — and why it does not

The plan's `<verification>` singles out the `handlers/signals.py` regime read as the only site where behaviour can move. It can move for two reasons: TA's label disagreeing with the deleted derivation, and the missing-data default. Both were checked.

**TA's vocabulary is wider than the engine's derivation was.** `services/technical-analysis/app/indicators/adx.py::MarketRegime` has **four** labels; the engine's `if/elif/else` produced **three**. `STRONG_TREND` (ADX ≥ 30) has no consumer in this module — `_calculate_enhanced_signal`'s `regime_multiplier` branches on `RANGING` / `TRENDING` only (`:247-254`), so an unrecognised label keeps the neutral `1.0`. Passing TA's label through raw would therefore have dropped every ADX ≥ 30 bar from multiplier **1.1** to **1.0**, silently. That is T-21-07-06 exactly. `STRONG_TREND` is mapped onto `TRENDING`.

The blast radius is **one** multiplier, not two: `_get_risk_adjusted_signal` (`:375-382`) also branches on `RANGING` / `TRENDING`, but **every one of its three branches returns `"HOLD"`** — it is a no-op switch, so the regime label cannot move its output. Worth stating precisely, because "two consumers would break" would have overstated the case for the mapping; the mapping is justified by the multiplier alone.

With that mapping the two classifiers agree on **every** input:

| ADX | Old re-derivation | TA `regime` | After mapping | Same? |
|---|---|---|---|---|
| ≥ 30 | TRENDING | STRONG_TREND | TRENDING | ✅ |
| 25 – 30 | TRENDING | TRENDING | TRENDING | ✅ |
| 20 – 25 | WEAK_TREND | WEAK_TREND | WEAK_TREND | ✅ |
| < 20 | RANGING | RANGING | RANGING | ✅ |
| **missing** | **TRENDING** (`.get("adx", 25)`) | absent | **UNKNOWN** | ❌ **intended** |

The boundaries coincide because TA's `_classify_regime` (`adx.py:259-276`) uses the same 25 / 20 the engine had copied — which is the whole point of the defect class: they agreed only because nobody had overridden either side yet.

This table is not prose. `test_handler_returns_the_regime_ta_computed` keeps the deleted three-branch classifier as `_legacy_rederivation` inside the test file and asserts the new read reproduces it for all four labels. Those four cases **passed in the RED run too** — correctly, because they pin preservation, not change.

**The one deliberate difference** is the last row, and it is T-21-07-02: `data.get("data", {}).get("adx", 25)` back-filled a missing ADX with a number that satisfied `>= 25`, so an empty or malformed TA reply was reported as `TRENDING` at `confidence: 0.7`, indistinguishable downstream from a real measurement. It now reports `UNKNOWN` with `adx: None`.

**Unmapped labels fail loud.** Any future TA label not in the table resolves to `UNKNOWN` **and logs a WARNING naming the label**, rather than falling through to the neutral branch unnoticed.

## No threshold value changed

- `adx_weak_trend_threshold` defaults to **20.0** — the literal it replaced, and equal to TA's `default_adx_weak_trend_threshold`.
- `sqzmom_volume_ratio_min` defaults to **1.2** — the literal it replaced.
- The omitted ADX period equals TA's `default_adx_period` (**14**), and TA's route resolves its query default from that field (`technical-analysis/app/main.py:467`), so the omission is genuine single-sourcing, not numeric coincidence.
- The regime boundaries are TA's, and are the same 25 / 20.
- Every production comment touched carries an explicit "NO THRESHOLD VALUE CHANGED" / "NO VALUE CHANGED" sentence.

**Env-shadow pre-check — the claim is live-effective, not merely inert.** "Byte-identical at default settings" only means something if no operator override shadows the two new keys. Checked against the **main repo** paths, because `.env` is gitignored and therefore absent from this worktree — grepping the worktree path would have been a false pass rather than a zero match:

```
$ grep -inE 'ADX_WEAK_TREND_THRESHOLD|SQZMOM_VOLUME_RATIO_MIN' \
    docker-compose.unified.yml .env
(no matches)

$ wc -c docker-compose.unified.yml .env
48109 docker-compose.unified.yml
11616 .env
```

Both files present and non-empty, so this is a genuine zero-match. **No operator env var shadows either new field** — the declared defaults are what the code will apply. `.env` was read-only throughout and never staged.

## Log messages report the resolved value

T-21-07-03. Both `[SQZMOM_GATE]` messages baked the number into the string. A log claiming `< 20` while the setting says 30 is the same defect in a different costume — it is how an operator debugs against a value the code no longer applies.

| | Before | After |
|---|---|---|
| ADX | `ADX {adx_val:.1f} < 20 (weak trend)` | `ADX {adx_val:.1f} below the declared weak-trend floor {adx_floor:.1f} (weak trend)` |
| Volume | `volume_ratio={ratio:.2f} (<1.2 or unconfirmed)` | `volume_ratio={ratio:.2f} (below the declared floor {volume_floor:.2f}, or unconfirmed)` |

Both are asserted by `caplog` in the raised-threshold cases, not merely grepped.

## RED captures

**Task 1** — the two fields do not exist:

```
FAILED tests/aggregation/test_mirror_literals.py::test_adx_weak_trend_threshold_defaults_to_the_literal_it_replaced
FAILED tests/aggregation/test_mirror_literals.py::test_sqzmom_volume_ratio_min_defaults_to_the_literal_it_replaced
FAILED tests/aggregation/test_mirror_literals.py::test_mirror_field_is_a_bounded_float[adx_weak_trend_threshold-0.0-100.0]
FAILED tests/aggregation/test_mirror_literals.py::test_mirror_field_is_a_bounded_float[sqzmom_volume_ratio_min-0.0-10.0]
FAILED tests/aggregation/test_mirror_literals.py::test_mirror_field_description_names_its_ta_counterpart_or_says_there_is_none[adx_weak_trend_threshold-default_adx_weak_trend_threshold]
FAILED tests/aggregation/test_mirror_literals.py::test_mirror_field_description_names_its_ta_counterpart_or_says_there_is_none[sqzmom_volume_ratio_min-no counterpart]
============================== 6 failed in 0.63s ===============================
```

**Task 2** — the ideal shape: exactly the three *raised-threshold* cases fail, while the three default-value positive controls pass. A RED in which the controls also failed would have meant the harness, not the gate, was broken.

```
FAILED ...::test_adx_vote_gate_resolves_from_settings[raised_threshold_silences_the_vote]
FAILED ...::test_sqzmom_adx_gate_resolves_from_settings[raised_threshold_demotes]
FAILED ...::test_sqzmom_volume_gate_resolves_from_settings[raised_floor_demotes]
FAILED ...::test_no_p21_7_site_regained_an_inline_literal[signal_aggregator.py::adx_val\s*(>=|<)\s*20(\.0)?\b]
FAILED ...::test_no_p21_7_site_regained_an_inline_literal[strategies/sqzmom_strategy_integration.py::adx_val\s*(>=|<)\s*20(\.0)?\b]
FAILED ...::test_no_p21_7_site_regained_an_inline_literal[strategies/sqzmom_strategy_integration.py::ratio\s*<\s*1\.2]
FAILED ...::test_no_p21_7_site_regained_an_inline_literal[strategies/sqzmom_strategy_integration.py::<\s*20 |<1\.2]
========================= 7 failed, 9 passed in 4.58s ==========================
```

**Task 3** — 11 failed, 20 passed. The four equivalence cases passed (they pin preservation); the outbound-param test failed for the right reason, with the leaking key named:

```
E  AssertionError: market_regime sent 'period', which technical-analysis declares in its
   Settings. Full captured params: {'interval': '60', 'period': 14, 'limit': 100}
```

## Verification results

| Check | Baseline (`3199fa9`) | After (`0046bd2`) | Verdict |
|---|---|---|---|
| `pytest tests/ --no-cov -q` (run 1) | 1 failed, 2068 passed, 795 skipped | 2 failed, 2098 passed, 795 skipped | see flake note |
| `pytest tests/ --no-cov -q` (run 2, no code change) | — | **2100 passed, 795 skipped, 0 failed** | **PASS — clean** |
| `pytest tests/aggregation/ --no-cov -q` | 5 passed | **36 passed** | PASS |
| `pytest tests/aggregation/test_mirror_literals.py` | n/a | **31 passed** | RED→GREEN |
| `pytest tests/ -k "adx or sqzmom or mirror"` | n/a | 35 passed, 20 skipped | PASS |
| `pytest tests/aggregation tests/strategies` | n/a | 193 passed | PASS |
| `requirements.txt` touched | — | **0 files** | PASS (T-21-SC: zero package installs) |

**Arithmetic check.** Baseline non-skipped total = 2068 + 1 = 2069. Run 1 after = 2098 + 2 = 2100. Run 2 after = 2100 + 0 = 2100. 2069 + 31 new tests = **2100** ✅ — every test this plan added is accounted for, on both post-change runs.

**On the failures — a second full-suite run with no code change came back completely clean (2100 passed, 0 failed), so both were wall-clock flakes.** Individually:

- `tests/unit/test_signal_cache.py::TestCacheIntegration::test_partial_expiration` — failed on the **baseline** too, identically, and passed on the clean rerun. Not a regression under any reading. It is the TTL flake documented in the 21-02, 21-03 and 21-05 summaries.
- `tests/strategies/test_pairs_trading.py::TestRecalibration::test_needs_recalibration_after_period` — the same family. Isolated rerun: **20 passed**; full-suite rerun: passed. The file contains **zero** references to `adx`, `sqzmom`, `market_regime`, `signal_aggregator` or `handlers.signals` (`grep -c` → 0). The test is a `time.sleep(4)` against a `recalibration_period=0.001` hours (≈3.6 s) window — a 0.4-second margin on a WSL2 host under a six-minute suite.

Left alone per the scope boundary. Both would be fixed by one standalone task that freezes the clock instead of sleeping.

Settings resolve check (acceptance criterion): `20.0 1.2` ✅

## Acceptance criteria — per-task evidence

**Task 1**

| Criterion | Result |
|---|---|
| `python3 -c "... print(s.adx_weak_trend_threshold, s.sqzmom_volume_ratio_min)"` prints `20.0 1.2` | `20.0 1.2` — PASS |
| `grep -c 'Do NOT diverge' config.py` ≥ 2 | **2** — PASS |
| `grep -n 'sqzmom_volume_ratio_min' config.py` shows a no-TA-counterpart comment | line 367: "`sqzmom_volume_ratio_min` has NO technical-analysis counterpart." — PASS |
| Test file exists and asserts both defaults + both bound sets | 6 cases — PASS |
| `pytest tests/aggregation/ --no-cov -q` exits 0 | 11 passed at the time of Task 1 — PASS |

**Task 2**

| Criterion | Result |
|---|---|
| `grep -nE 'adx_val\s*(>=\|<)\s*20(\.0)?'` on both files → no matches | exit 1, no output — PASS |
| `grep -nE 'ratio\s*<\s*1\.2'` → no matches | exit 1 — PASS |
| `grep -nE '<\s*20 \|<1\.2'` → no matches (literals gone from the messages too) | exit 1 — PASS |
| `grep -c 'adx_weak_trend_threshold'` non-zero in both files | **2** and **2** — PASS |
| ≥ 3 behavioural tests monkeypatch a setting and assert the gate moves | **3** (each with a default-value positive control) — PASS |
| Full suite: no new failures vs baseline | see flake note — PASS |

**Task 3**

| Criterion | Result |
|---|---|
| `grep -nE 'adx_value\s*>=\s*25\|adx_value\s*<\s*20'` → no matches | exit 1 — PASS |
| `grep -n 'WEAK_TREND'` shows it only in a mapping/comment | one hit, line 50, inside `TA_REGIME_TO_ENGINE_REGIME` — PASS |
| `grep -nE '\.get\("adx",\s*25\)'` → no matches | exit 1 — PASS |
| `grep -n '"period"'` in `market_regime.py` → no match | exit 1 — PASS |
| `grep -rn 'adx_period'` → none remaining, or a documented retained parameter | none in the two plan files; **two out-of-scope survivors**, see below — PASS with note |
| Three new tests: regime passthrough, missing-regime unknown, `period` omitted | present (plus 12 more) — PASS |
| Full suite: no new failures vs baseline | see flake note — PASS |

### Out-of-scope `adx_period` survivors (deliberately not touched)

`grep -rn 'adx_period' services/trading-engine/app` still matches:

- `app/strategies/trend_following.py:70,111,239`
- `app/strategies/trend_following_strategy.py:366,377,385,402,1551` (`:1551` does send `"period": self.adx_period` on its own ADX request)

Neither file is in this plan's `files_modified`, and neither is in 21-CONTEXT's P21-7 site list. They are the same defect class and are recorded here rather than fixed — T-21-07-05 (silent scope expansion) explicitly forbids widening. **Recommend adding them to a future plan's inventory.**

**Scope qualification on must-have truth #3.** "The engine no longer sends an ADX period that TA Settings already own" holds for **P21-7's site list**, not globally: `trend_following_strategy.py:1551` still sends `"period": self.adx_period` on its own ADX request. Stating the truth without this qualifier would be false, and a verifier grepping the repo would find the counterexample. The claim this plan actually establishes is: *every P21-7-scoped ADX request omits the period.*

### `market_regime.py`'s own regime classification — checked, already correct

The other file this plan edited carries a `MarketRegime` enum and a classification block (`:294-307`), so it is a natural place to look for a violation of must-have truths #1 and #4. It was read in full. **Neither truth has a counterexample there:**

- `:290` reads `adx_data.get("regime", "UNKNOWN")` and `:296-305` **maps that string onto the enum**. It applies **no numeric threshold of its own** — there is no `adx >= 25` anywhere in the file. It does not re-derive; truth #1 holds.
- `_get_default_analysis()` (`:439-464`) returns `MarketRegime.UNKNOWN` with `confidence=0.0` and a docstring naming the regime field as *the* failure sentinel (audit-flagged 2026-04-28, because `confidence=0.0` alone was indistinguishable from a genuine low-confidence read). A failed ADX read cannot be classified as TRENDING here; truth #4 holds.

This is worth more than a clean bill of health: it is the **in-repo precedent for the exact map-don't-re-derive pattern** adopted for `handlers/signals.py` in Deviation 2, arrived at independently. Two files in the same service now handle TA's regime vocabulary the same way, and `handlers/signals.py` was the odd one out.

One dead branch noted, not fixed: `market_regime.py` consumers reference `MarketRegime.VOLATILE` (`:359`, `:399`, `:548`) but the string mapper can never produce it — TA does not emit that label. Out of scope, recorded for a future inventory.

## Deviations from Plan

### 1. [Rule 2 — Missing critical] The failure path fabricated the same ADX 25

- **Found during:** Task 3
- **Issue:** the plan and its acceptance grep target `data.get("data", {}).get("adx", 25)` on the success path. The `except` branch (`handlers/signals.py:174-178`) returned `"adx": 25` as well. Its `regime` was already `UNKNOWN`, so it is less dangerous than the success-path default — but it is the identical fabrication, it is surfaced verbatim in the API response metadata (`:133`), and leaving it would have meant the very next reader "fixed" one instance and blessed the other.
- **Fix:** `"adx": None` on the failure path too, with a comment stating why.
- **Blast-radius check before changing it:** `market_regime["adx"]` is read **nowhere** in the engine — `_calculate_enhanced_signal` consumes only `regime` (`:244`) and `confidence` (`:274`). The key is JSON-serialised into the response and nothing else, so `None` is safe.
- **Verification:** `test_regime_fetch_failure_does_not_fabricate_an_adx`.
- **Committed in:** `0046bd2`

### 2. [Rule 2 — Missing critical] `STRONG_TREND` mapped rather than passed through

- **Found during:** Task 3, while performing the plan's own instruction to "grep for consumers of this handler's `regime` value before changing the string set".
- **Issue:** reading TA's `regime` raw is a silent behaviour regression for every ADX ≥ 30 bar — the label has no consumer and would take the neutral branch.
- **Fix:** an explicit module-level map with a fail-loud `UNKNOWN` default and a WARNING naming the unmapped label. This is precisely T-21-07-06's stated mitigation ("map it explicitly with a comment rather than leaving an unmapped string to fall through"), so it is an in-mandate application rather than an expansion — recorded as a deviation because the plan's site table implied a bare `regime` read.
- **Verification:** the four-label equivalence table against `_legacy_rederivation`, plus `test_unmapped_ta_regime_label_fails_loud_not_silent` and `test_engine_maps_every_regime_label_ta_can_emit`.
- **Committed in:** `0046bd2`

### 3. [Scope discipline] Research-provenance comment updated alongside the gates

- **Found during:** Task 2. `sqzmom_strategy_integration.py`'s research comment listed "(a) ADX >= 20 trend-strength gate" and "(c) Volume on release > 1.2× SMA(20)". Neither is caught by the acceptance greps, but both would have gone stale the moment the settings moved — the same failure the plan required fixing in the log messages.
- **Fix:** the comment now records 20 and 1.2 as the **research** values while naming the settings that are **applied**, so provenance and application are separable rather than conflated.
- **Committed in:** `a30540f`

### 4. [Tooling] Every source edit applied via Bash + `pathlib`, never the Edit tool

- **Found during:** planning the first write, from the 21-02, 21-03 and 21-05 summaries, which each lost a cycle to this.
- **Issue:** the repo's PostToolUse format hook runs ruff/autoflake at 88 columns against a 100-column codebase; it reflows unrelated blocks and strips not-yet-referenced imports. Here it would have been particularly costly: the `annotated_types` import in the new test file is referenced only inside a helper, and a reflow of `config.py` would have swamped the 54-line addition.
- **Fix:** every edit applied through `python3` + `pathlib` with `assert count == 1` anchors. Zero reverts were needed.
- **Verification:** `git diff --stat` across the plan shows **750 insertions, 26 deletions** over six files, with the production diffs at 54 / 16 / 30 / 63 / 20 lines — no reflow churn anywhere.

### 5. [Rule 1 — Self-correction] The mapping comment overstated its own blast radius

- **Found during:** post-task verification, while checking the line references cited in this summary.
- **Issue:** the comment introduced in `0046bd2` said `_calculate_enhanced_signal`'s multiplier **and** `_get_risk_adjusted_signal` "both branch on TRENDING / RANGING only, so an unmapped label silently lands on the neutral branch". The first half is right. The second is misleading: `_get_risk_adjusted_signal` (`:375-382`) returns `"HOLD"` from **all three** of its branches, so the regime label cannot move its output at all. Left as written, the comment would have justified the mapping with a consumer that does not exist — the same "documentation asserting something the code does not do" failure this plan exists to remove.
- **Fix:** the comment now names the multiplier as the sole protected consumer and carries an explicit scope note about the no-op switch.
- **Verification:** `pytest tests/aggregation/ --no-cov -q` → 36 passed.
- **Committed in:** the plan-metadata commit (comment-only; no behaviour touched).

---

**Total deviations:** 5 (2 missing-critical, 1 scope-discipline, 1 tooling, 1 self-correction). **Impact:** both missing-critical fixes prevent the plan's own change from introducing a regression it was meant to remove. No file outside the plan's `files_modified` was touched.

## TDD Gate Compliance

All three tasks are marked `tdd="true"`, while the plan's `<output>` block mandates **three** commits, each pairing production files with the test file. RED and GREEN were therefore collapsed into one commit per task rather than emitting separate `test(...)` RED commits — the same deliberate consequence recorded in 21-05's summary.

The discipline was preserved in execution and all three RED runs are captured verbatim above: each task's tests were written and observed failing before any production change, and in Tasks 2 and 3 the RED shape was itself diagnostic (only the behaviour-changing assertions failed; the preservation assertions passed).

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data sources were introduced. `TA_REGIME_TO_ENGINE_REGIME` is fully populated against TA's live enum and is covered by a completeness test.

## Threat Flags

None. No new network endpoint, auth path, file access pattern, or schema change at a trust boundary. Zero package installs; `git diff --name-only` shows no `requirements` file (T-21-SC: n/a).

Threat register dispositions:

| Threat ID | Disposition | Evidence |
|---|---|---|
| T-21-07-01 (config drift between mesh services) | **mitigated** | Two typed `Field`s with bounds, descriptions naming the TA counterpart (or its absence), the "Do NOT diverge" sentence; three behavioural tests monkeypatch each setting and assert the gate moves |
| T-21-07-02 (failed ADX read reported as confident TRENDING) | **mitigated** | `.get("adx", 25)` removed on **both** paths; missing `regime` → `UNKNOWN`; `test_a_failed_adx_read_can_no_longer_masquerade_as_trending` |
| T-21-07-03 (logs hardcoding a threshold no longer applied) | **mitigated** | Both `[SQZMOM_GATE]` messages interpolate the resolved value; asserted by caplog and banned by a source-guard row |
| T-21-07-04 (env override widening config surface) | **mitigated** | Both fields are `Field(default=…, ge=…, le=…)`; no secret, no required field; bounds pinned by `test_mirror_field_is_a_bounded_float` |
| T-21-07-05 (scope creep into the three non-CONTEXT mirror sites) | **mitigated** | `signal_aggregator.py`'s `std_dev: 2.5`, RSI `period: 9` and trend-filter `limit: 300` untouched; the two out-of-scope `adx_period` files named above, not edited |
| T-21-07-06 (unmapped TA regime falling through) | **mitigated** | Explicit map, fail-loud `UNKNOWN` + WARNING, completeness test over TA's four labels |
| T-21-SC (package installs) | **n/a** | Zero installs, no `requirements.txt` in the diff |

## Deployment status — NOT in the running stack

**These changes are committed and unit-verified only. The trading-engine has NOT been rebuilt or `--force-recreate`d.** This executor runs in an isolated worktree; touching the shared stack would collide with sibling agents, and this plan's `<verification>` block is pytest-only by design.

21-CONTEXT `<specifics>` still owes a before/after signal comparison on BTC/ETH/SOL/BNB/ADA **through the running stack** plus a rebuild of the changed service, and CLAUDE.md §7 forbids any "working end-to-end" claim without it. That debt belongs at 21-09.

This matters concretely here: `MarketRegimeDetector` logs a changed init line and `_fetch_market_regime` returns a changed `adx` type (`int` → `None` on failure). Neither is live until the service is rebuilt.

## Deferred Issues

- **`test_signal_cache.py` and `test_pairs_trading.py` wall-clock flakes** — both are `time.sleep`-based; both passed on a clean full-suite rerun and in isolation; neither references any file this plan touched. Out of scope. A single standalone task freezing the clock would fix both families. Worth doing: they have now cost four consecutive plans a diagnostic detour.
- **Two out-of-scope `adx_period` declarations** in `trend_following.py` / `trend_following_strategy.py`, one of which still sends `"period"` on an ADX request (`:1551`). Same defect class, outside CONTEXT's P21-7 list.
- **Regime `confidence` is still the hardcoded 0.7** in `_fetch_market_regime`. TA computes and returns a real regime-classification confidence on the same response (`adx.py::ADXCalculator._calculate_confidence`, surfaced as the `confidence` key `fetch_adx` already reads). Adopting it is a numeric behaviour change — it feeds `_calculate_enhanced_signal`'s risk weight — and was deliberately not made here.

## Next Phase Readiness

- **Ready for 21-08.** No overlap: 21-08's hygiene batch touches `multi_strategy_ensemble.py`, `simple_rsi_strategy.py`, `advanced_position_sizing.py`, `hybrid_strategy_router.py`, `squeeze_momentum_strategy.py` and the `signal_aggregator.py:143` docstring — none of which this plan modified, and the docstring is far from the `fetch_adx` region touched here.
- **Ready for 21-09.** This plan is behaviour-neutral at default settings except for the missing-data path, so it should contribute **no** admission delta to the ablation. If 21-09 measures one, the likely cause is TA-response failures previously being scored as TRENDING — which is the defect, not the fix.
- **No blockers for sibling plans.** Only the plan's six declared files were touched. `STATE.md` and `ROADMAP.md` deliberately NOT modified — parallel worktree mode; the orchestrator owns those writes after the wave merges.

## Self-Check: PASSED

Files verified present on disk:
- `services/trading-engine/tests/aggregation/test_mirror_literals.py` — FOUND (created)
- `services/trading-engine/app/config.py` — FOUND
- `services/trading-engine/app/signal_aggregator.py` — FOUND
- `services/trading-engine/app/strategies/sqzmom_strategy_integration.py` — FOUND
- `services/trading-engine/app/handlers/signals.py` — FOUND
- `services/trading-engine/app/aggregation/market_regime.py` — FOUND
- `.planning/phases/21-ta-aggregator-widening-leakage-net/21-07-SUMMARY.md` — FOUND

Commits verified in `git log`:
- `dff465b` `feat(trading-engine)` — FOUND
- `a30540f` `fix(trading-engine)` — FOUND
- `0046bd2` `fix(trading-engine)` — FOUND

All task `<acceptance_criteria>` re-run and passing; plan-level `<verification>` re-run with both full-suite captures recorded above. Every `file:line` cited in this summary was re-read from source, not carried over from the plan — two references were corrected in the process (Deviation 5).

**STATE.md and ROADMAP.md deliberately NOT modified** — parallel worktree mode; the orchestrator owns those writes after the wave merges.

---
*Phase: 21-ta-aggregator-widening-leakage-net*
*Completed: 2026-08-27*
