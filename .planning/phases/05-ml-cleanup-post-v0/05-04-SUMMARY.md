---
phase: 05-ml-cleanup-post-v0
plan: "04"
subsystem: testing
tags: [backtest, signal-aggregation, adr, tdd, divergence, documentation]

# Dependency graph
requires:
  - phase: 05-ml-cleanup-post-v0
    provides: "MLCL-01 apparatus + gate, MLCL-02 horizon sweep, MLCL-03 monitoring disposition"
  - phase: 04-tournament-significance-auto-pr
    provides: "Tournament harness — the authoritative honest-evaluation path (context for why option B was chosen)"
provides:
  - "SC-4 satisfied: run_extended_backtest.py docstring + runtime warning permanently document signal divergence"
  - "ADR-012 codifies document_divergence_permanently as the binding architectural decision"
  - "5-test pytest invariant pinning PERMANENT DIVERGENCE marker + runtime warning + ADR reference"
  - "_emit_divergence_warning() module-level helper making the warning independently testable"
affects:
  - "Any operator running run_extended_backtest.py"
  - "Future plans that reference the tournament harness vs run_extended_backtest.py distinction"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PERMANENT DIVERGENCE docstring pattern: when a tool intentionally diverges from the live path, name the live component by module path and cite the ADR"
    - "Testable module-entry warning: extract logger.warning() into _emit_divergence_warning() so caplog can assert it without invoking the heavy main() loop"

key-files:
  created:
    - ".planning/phases/05-ml-cleanup-post-v0/05-04-DECISION.md"
    - "docs/decisions/ADR-012-extended-backtest-disposition.md"
    - "services/trading-engine/tests/test_run_extended_backtest_divergence_warning.py"
  modified:
    - "services/trading-engine/run_extended_backtest.py"

key-decisions:
  - "document_divergence_permanently chosen over rewrite_to_core_aggregator: tournament harness already provides the honest-evaluation path; script is strategy regime characterisation only"
  - "SC-4 punt phrases 'Fixing requires' / 'separate change' are architectural ambiguity violations — they imply a temporary TODO rather than a deliberate choice; replaced with PERMANENT DIVERGENCE framing"
  - "_emit_divergence_warning() added as a module-level helper (not inline in main) so the runtime warning is independently testable via caplog without triggering the HTTP-heavy backtest loop"

patterns-established:
  - "PERMANENT DIVERGENCE pattern: when offline tool diverges from live code path by design, document it in the module docstring with the exact live component name, its path, and an ADR reference"
  - "Testable entry warning: module-level _emit_divergence_warning() called first in main(), tested via caplog in a dedicated pytest"

requirements-completed:
  - MLCL-04

# Metrics
duration: ~30min
completed: 2026-05-13
---

# Phase 05 Plan 04: Extended Backtest Divergence Summary

**SC-4 closed: run_extended_backtest.py permanently documents its CoreAggregator divergence via PERMANENT DIVERGENCE docstring framing, _emit_divergence_warning() runtime log, and 5-test pytest invariant backed by ADR-012**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-13
- **Completed:** 2026-05-13
- **Tasks:** 2 (Task 1: DECISION.md; Task 2: TDD RED→GREEN)
- **Files modified:** 4 (1 created plan artifact, 1 modified script, 1 new ADR, 1 new test file)

## Accomplishments

- Wrote 05-04-DECISION.md (198 lines) analyzing both options (rewrite_to_core_aggregator vs
  document_divergence_permanently) with cost/risk/value scoring; decision pre-confirmed by
  operator as document_divergence_permanently
- Replaced the SC-4 ambiguity violation in run_extended_backtest.py: "KNOWN LIMITATION" block
  with "PERMANENT DIVERGENCE" framing naming CoreAggregator at app/aggregation/aggregator_core.py
- Added _emit_divergence_warning() module-level helper; called first in main(); emits
  "RUN_EXTENDED_BACKTEST: signal logic diverges from live CoreAggregator — do NOT treat
  output as live-PnL forecast. See ADR-012."
- Wrote ADR-012 (100 lines) with operator guidance table: script = regime characterisation;
  tournament harness = authoritative edge measurement
- TDD RED→GREEN: 5 tests written failing, then 5/5 passing after production edits

## Task Commits

Each task committed atomically:

1. **Task 1: Write DECISION.md** — `8e2132e` (feat)
2. **Task 2 RED: Failing tests** — `3c20dd3` (test)
3. **Task 2 GREEN: Production edits + ADR-012** — `5156ba8` (feat)

## Files Created/Modified

- `.planning/phases/05-ml-cleanup-post-v0/05-04-DECISION.md` (198 lines) — Two-option analysis with
  cost/risk/value scoring; decision: document_divergence_permanently; implementation notes binding Task 2
- `services/trading-engine/run_extended_backtest.py` — Docstring block replaced (KNOWN LIMITATION →
  PERMANENT DIVERGENCE); _emit_divergence_warning() helper added; main() updated to call helper first
- `docs/decisions/ADR-012-extended-backtest-disposition.md` (100 lines) — ADR codifying the disposition;
  operator guidance table; references to DECISION.md and tournament harness
- `services/trading-engine/tests/test_run_extended_backtest_divergence_warning.py` (122 lines) — 5 tests:
  SC-4 punt language absent, PERMANENT DIVERGENCE present, CoreAggregator named, ADR-012 referenced,
  runtime warning fires (caplog assertion)

## Decisions Made

- **document_divergence_permanently over rewrite_to_core_aggregator:** Tournament harness (Phase 3+4)
  already provides the authoritative honest-evaluation path. Option A would duplicate it at medium-to-high
  effort with ~60% risk of sub-divergences from CoreAggregator's stateful dependencies (vol estimator,
  funding cache, maker queue). Option B satisfies SC-4 at low cost with no new code paths.
- **_emit_divergence_warning() as a separate helper (not inline):** Enables caplog-based test assertion
  without invoking main()'s HTTP-heavy backtest loop. Pattern: extract entry warnings into named helpers.
- **ADR-012 operator guidance table:** Explicitly separates run_extended_backtest.py use case (strategy
  regime characterisation) from tournament harness use case (authoritative edge claims). Prevents future
  confusion about when to use which tool.

## Deviations from Plan

None — plan executed exactly as written. The pre-confirmed decision (document_divergence_permanently)
was applied without any checkpoint pause, matching the operator's pre-approval in the objective.

The formatter hook reformatted run_extended_backtest.py after edits (removed two unused imports:
ResearchOptimizedStrategy, MeanReversionStrategy). This is cosmetic and correct — those classes
were imported but never used in the script.

## Issues Encountered

- Pre-existing test failure in `tests/strategies/test_pairs_trading.py::TestPairsTradingCalibration::
  test_calibrate_cointegrated_pair`: pandas frequency deprecation (`H` → `h`). This failure predates
  this plan and is unrelated to any files modified here. Logged to deferred-items, not fixed (out of
  scope per deviation rule boundary).

## Operator Handoff

**When to use run_extended_backtest.py:**
- Understanding how HybridStrategyRouter behaves across trending vs ranging markets
- Comparing trend-following vs mean-reversion sub-strategies by regime
- Ad-hoc strategy regime inspection (NOT for edge claims)

**When to use the tournament harness (scripts/tournament/):**
- Authoritative edge measurement (DSR/CPCV, bootstrap p-values, PSR gate)
- Pre-deploy sanity check: does the strategy produce profitable signals?
- Any edge claim that will be cited as evidence — tournament harness ONLY

The runtime warning fires every time run_extended_backtest.py is executed, making the
distinction impossible to miss.

## Next Phase Readiness

Phase 05 is complete: all 4 plans (MLCL-01 through MLCL-04) done.
- MLCL-01: evaluation apparatus + DSR gate
- MLCL-02: horizon sweep (T0.1.x experiment)
- MLCL-03: monitoring tier-2 deleted (ADR-011)
- MLCL-04: run_extended_backtest.py divergence documented (ADR-012)

Phase 05 is ready for verification. The single outstanding external dependency:
TIMESCALE_PASSWORD still needed to re-run the T0.1.x horizon sweep tournament
(MLCL-02 produced INSUFFICIENT_DATA verdict due to missing env var — operator action required).

---
*Phase: 05-ml-cleanup-post-v0*
*Completed: 2026-05-13*
