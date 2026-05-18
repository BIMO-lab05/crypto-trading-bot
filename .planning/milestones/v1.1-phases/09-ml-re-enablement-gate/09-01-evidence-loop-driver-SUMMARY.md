---
phase: 09-ml-re-enablement-gate
plan: 01
subsystem: scripts/forward_paper_test + services/tournament-harness
tags:
  - mlgate
  - evidence-loop
  - tournament-harness
  - psr-ci
  - phase-9
requires: []
provides:
  - "Migration 0002: leaderboard.run_date + leaderboard.psr_ci_published + idx_leaderboard_psr_published"
  - "run_evidence_loop driver — idempotent ≥7-day accrual + PSR-CI publish orchestrator (MLGATE-01)"
  - "8-case unit test suite covering idempotency, accrual window, resume, dry-run, paper-only refusal"
affects:
  - phase 09-02 (MLGATE-02 auto-flip reads psr_ci_published=1 AND run_date within 14d)
  - phase 11 LIVECLOSE-03 (operator runs this driver to accrue evidence)
  - phase 09-03 (digest reads `MLGATE_EVIDENCE_LOOP action=...` log literals)
tech-stack:
  added: []
  patterns:
    - "Canonical migration runner (services/tournament-harness/app/leaderboard/db.py::run_migrations) is the project's idempotency layer for raw-SQL migrations — SQLite has no native ADD COLUMN IF NOT EXISTS."
    - "Parameterised UPDATE with full composite PK as WHERE clause — single-row, single-transaction, no value interpolation (T-03-08 + T-09-01-01 disposition)."
    - "Log line as contract surface: `MLGATE_EVIDENCE_LOOP action=<value> reason=<reason>` literal is read by Plan 09-03 digest; inlined (not f-string-interpolated) so static grep gates can verify presence."
    - "Error log emits type(e).__name__ only — never raw exception string (T-09-01-03 information-disclosure mitigation; mirrors trading-engine preflight/checks.py:246-251)."
key-files:
  created:
    - services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql
    - scripts/forward_paper_test/run_evidence_loop.py
    - scripts/forward_paper_test/tests/test_run_evidence_loop.py
  modified: []
decisions:
  - "D-09-01-01 honored — leaderboard table name used directly (NOT tournament_results); REQUIREMENTS.md wording correction deferred to a follow-up docs commit."
  - "D-09-01-02 honored — ALTER TABLE on existing leaderboard with nullable run_date + default-0 psr_ci_published; no view/alias table that would split the read surface."
  - "D-09-01-03 honored — driver imports compute_psr_with_bootstrap_ci from psr_ci.py; zero inlined bootstrap math (np.percentile count = 0)."
  - "D-09-01-04 honored — wall-clock 7-day rule on per-natural-key group min(run_date); below window logs accrual_window_open skip and does NOT flip."
metrics:
  duration: ~35min
  completed: "2026-05-17"
  tasks: 3
  files_created: 3
  files_modified: 0
  tests_added: 8
  tests_passing: 8
---

# Phase 09 Plan 01: Evidence-Loop Driver Summary

Idempotent ≥7-day forward-paper-test evidence accrual + PSR-CI publish orchestrator (MLGATE-01) — landed as migration 0002 (run_date, psr_ci_published columns + supporting index), a host-runnable driver script, and an 8-case unit-test suite asserting the two-run-same-count and resume-from-partial-state invariants.

## Tasks Completed

| Task | Name                                                                         | Commit  | Files                                                            |
| ---- | ---------------------------------------------------------------------------- | ------- | ---------------------------------------------------------------- |
| 1    | Migration 0002 — run_date + psr_ci_published columns on leaderboard          | b33ecad | services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql |
| 2    | run_evidence_loop driver — idempotent ≥7-day accrual + PSR-CI publish        | 7fffffd | scripts/forward_paper_test/run_evidence_loop.py                  |
| 3    | 8 unit tests — idempotency, accrual window, resume, dry-run, paper-only      | 419a591 | scripts/forward_paper_test/tests/test_run_evidence_loop.py       |

## Verification

| Check                                                                              | Result |
| ---------------------------------------------------------------------------------- | ------ |
| `pytest scripts/forward_paper_test/tests/test_run_evidence_loop.py` — 8/8 passing  | PASS   |
| Migration 0002 applies cleanly via `run_migrations` against fresh DB from 0001     | PASS   |
| Re-applying migration 0002 is no-op (runner detects schema_version=2 and skips)    | PASS   |
| Pre-existing 0001-only row survives 0002 (run_date=NULL, psr_ci_published=0)       | PASS   |
| `python3 -m scripts.forward_paper_test.run_evidence_loop --help` exits 0           | PASS   |
| `TRADING_MODE=LIVE python3 -m scripts.forward_paper_test.run_evidence_loop ...`    | EXIT 1 |
| Two-run-same-count invariant: `SELECT COUNT(*)` unchanged across runs              | PASS   |
| Resume invariant: pre-published rows never re-flipped                              | PASS   |
| Canonical-kernel reuse: `np.percentile` count in driver = 0 (TOURN-07 spirit)      | PASS   |
| `MLGATE_EVIDENCE_LOOP` literal count in driver = 10 (≥4 required)                  | PASS   |

## Decisions Made

- **D-09-01-01 — leaderboard table name (carried in)**: Phase 9 reads and writes `leaderboard` directly. REQUIREMENTS.md still references the non-existent `tournament_results` table; correction deferred to a follow-up docs commit (same disposition as Phase 8, see 08-01-SUMMARY.md lines 153-177).
- **D-09-01-02 — schema extension via ALTER TABLE**: Non-destructive `ADD COLUMN run_date TEXT` (nullable) and `ADD COLUMN psr_ci_published INTEGER NOT NULL DEFAULT 0 CHECK (0,1)` on the existing `leaderboard` table, plus a supporting `idx_leaderboard_psr_published(psr_ci_published, run_date DESC)` index for the MLGATE-02 lookup. A view/alias `tournament_results` was explicitly rejected because it would split the read surface and break the TOURN-07 grep-gate scope.
- **D-09-01-03 — driver is an orchestrator, not a re-implementation**: `compute_psr_with_bootstrap_ci` is imported from `scripts/forward_paper_test/psr_ci.py`; the driver contains zero inlined bootstrap math (`grep -c np.percentile` returns 0). Natural-key idempotency uses the existing leaderboard composite PK `(architecture, symbol, horizon, target_mode, hp_hash, run_id)`.
- **D-09-01-04 — 7-day accrual is a wall-clock check on `run_date`**: Below window → `MLGATE_EVIDENCE_LOOP action=skip reason=accrual_window_open days_observed=N`; at/above window → compute PSR-CI then single-transaction `UPDATE psr_ci_published=1` on the composite-PK row.

## Deviations from Plan

### Rule 3 — Migration idempotency via runner, not inline SQL guard

- **Found during**: Task 1 verify script design.
- **Issue**: The plan's Task 1 verify block calls `conn.executescript(mig2)` twice. SQLite has no `ALTER TABLE ADD COLUMN IF NOT EXISTS` and `executescript` cannot do conditional DDL, so the second call would raise `OperationalError: duplicate column name`. The plan's action step 1 prose ("first SELECT COUNT(*) FROM schema_version WHERE version = 2 — if zero, run the ALTERs") describes runner-level idempotency, not SQL-level.
- **Fix**: Migration 0002 is a clean two-ALTER + one-INDEX + one-INSERT script with NO inline guard. Idempotency is delegated to the canonical project runner at `services/tournament-harness/app/leaderboard/db.py::run_migrations` (lines 56-119), which reads `schema_version` and skips already-applied versions. The runner is the same one used by `services/tournament-harness/tests/unit/test_leaderboard_db.py::test_run_migrations_is_idempotent`, so the test surface matches production boot semantics.
- **Verification**: Standalone Python script using `run_migrations` applies 0001 + 0002 successfully, re-applies 0002 cleanly (no error), preserves pre-existing rows from 0001 with `run_date=NULL` and `psr_ci_published=0`. Test 3 fixture uses `run_migrations` directly, so the 8-test suite exercises this contract.
- **Files affected**: `services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` documents the rationale in its header comment block (`IDEMPOTENCY NOTE`).
- **Commit**: b33ecad

### Rule 2 — Inline `MLGATE_EVIDENCE_LOOP` literal in log format strings

- **Found during**: Task 2 acceptance grep gate.
- **Issue**: The plan's Task 2 action step 8 prescribed `f"{LOG_PREFIX} action=publish ..."` (variable interpolation). The acceptance criterion requires `grep -c "MLGATE_EVIDENCE_LOOP"` to return ≥4 — a static-text count that cannot see runtime variable substitution.
- **Fix**: Each log call inlines the literal string `"MLGATE_EVIDENCE_LOOP action=..."`. The `LOG_PREFIX` module constant is retained as a documented contract-surface marker for Plan 09-03 (so downstream consumers have a single named reference even though the call sites use the literal).
- **Verification**: `grep -c "MLGATE_EVIDENCE_LOOP" scripts/forward_paper_test/run_evidence_loop.py` returns 10 (gate required ≥4). Runtime log lines are identical to the plan's prescribed format.

### Rule 3 — Test fixture `_returns_json` auto-creates parent directory

- **Found during**: Task 3 initial test run (5/8 tests failed with `FileNotFoundError`).
- **Issue**: Several tests pass a sub-path (e.g. `tmp_path / "ret1"`) to `_returns_json` to keep multiple fixture trees isolated within one test's `tmp_path`. The original helper called `.write_text` on a non-existent directory.
- **Fix**: `_returns_json` now does `tmp_path.mkdir(parents=True, exist_ok=True)` before writing `run.json`. Behaviour for top-level `tmp_path` is unchanged.
- **Verification**: All 8 tests pass after the fix.

## Authentication Gates

None — driver runs host-side with no external auth.

## Threat Model — Implementation Notes

| Threat ID | Disposition | Implementation                                                                                       |
| --------- | ----------- | ---------------------------------------------------------------------------------------------------- |
| T-09-01-01 | accept     | Driver only UPDATEs `psr_ci_published`; never INSERTs/DELETEs. Verified by test_evidence_loop_two_runs_same_row_count. |
| T-09-01-02 | mitigate   | `run_date` is READ from leaderboard (written by tournament-harness orchestrator); driver applies 7-day rule against an injectable clock. |
| T-09-01-03 | mitigate   | All sqlite3.Error and ValueError paths emit `type(e).__name__` only (never raw exception string). Same disposition as trading-engine preflight checks.py:246-251. |
| T-09-01-04 | accept     | Operator-synchronous, no daemon mode; `--dry-run` available for fast inspection. |
| T-09-01-05 | mitigate   | `_check_paper_mode_precondition` refuses TRADING_MODE=LIVE with exit 1. Verified by test_evidence_loop_refuses_live_mode (subprocess invocation). |
| T-09-01-06 | accept     | `--returns-source` documented in CLI help as test convenience; production resolution walks `.planning/evidence/forward_paper_test/<flag>/<run_id>/run.json`. |

## Files Created

- `services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` (57 lines) — non-destructive ALTER TABLE + supporting index + schema_version row.
- `scripts/forward_paper_test/run_evidence_loop.py` (~370 lines) — orchestrator with `main`, `run_evidence_loop`, `DEFAULT_TOURNAMENT_DB_PATH`, `ACCRUAL_WINDOW_DAYS`, `LOG_PREFIX` exports.
- `scripts/forward_paper_test/tests/test_run_evidence_loop.py` (~440 lines) — 8 unit tests, all passing host-side.

## Self-Check: PASSED

- Migration file exists: FOUND: services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql
- Driver file exists: FOUND: scripts/forward_paper_test/run_evidence_loop.py
- Test file exists: FOUND: scripts/forward_paper_test/tests/test_run_evidence_loop.py
- Commit b33ecad: FOUND
- Commit 7fffffd: FOUND
- Commit 419a591: FOUND
- All 8 tests pass: PASS (8 passed in ~13s)
