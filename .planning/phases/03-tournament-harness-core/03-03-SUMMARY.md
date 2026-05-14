---
phase: "03"
plan: "03"
subsystem: "tournament-harness/leaderboard"
tags: ["sqlite", "migrations", "schema", "validation", "security", "tdd"]
dependency_graph:
  requires: ["03-01"]
  provides: ["leaderboard-schema", "migration-runner", "result-schema-validator"]
  affects: ["03-06", "03-07", "03-08"]
tech_stack:
  added: ["sqlite3 (stdlib)", "pathlib migrations runner"]
  patterns: ["WAL single-writer", "nullable-equality parameterised filter", "TDD red/green"]
key_files:
  created:
    - "services/tournament-harness/migrations/0001_initial.sql"
    - "services/tournament-harness/app/leaderboard/__init__.py"
    - "services/tournament-harness/app/leaderboard/result_schema.py"
    - "services/tournament-harness/app/leaderboard/db.py"
    - "services/tournament-harness/tests/__init__.py"
    - "services/tournament-harness/tests/unit/__init__.py"
    - "services/tournament-harness/tests/unit/test_result_schema.py"
    - "services/tournament-harness/tests/unit/test_leaderboard_db.py"
  modified: []
decisions:
  - "Used nullable-equality SQL pattern (? IS NULL OR col = ?) in list_runs to eliminate string concatenation and satisfy semgrep CWE-89 gate"
  - "Replaced f-string _INSERT_LEADERBOARD_SQL with raw string literal to eliminate string-join-based SQL construction"
  - "Precomputed INSERT SQL as module-level raw literal — all 20 column ? placeholders explicit in source"
metrics:
  duration: "~35 minutes"
  completed_date: "2026-05-09"
  tasks_completed: 3
  files_created: 8
  tests_passed: 20
---

# Phase 03 Plan 03: SQLite Leaderboard Schema + Migration Runner Summary

SQLite leaderboard DDL (TOURN-02 PK + 20 columns + 4 indexes), idempotent WAL migration runner, and result.json schema validator — the trust-boundary gatekeepers between experiment container output and leaderboard rows.

## What Was Built

**Schema (20 columns, 3 tables):**
- `leaderboard`: 20 columns with composite PK `(architecture, symbol, horizon, target_mode, hp_hash, run_id)`; 6 honest-metric columns nullable for failed rows; 4 CHECK constraints at DB level; 4 indexes
- `tournaments`: config YAML verbatim + run counts for reproducibility
- `schema_version`: numbered migration tracking (D-17)

**CHECK constraints applied (6 total):**
1. `architecture IN ('gru','lstm','transformer','tcn')`
2. `target_mode IN ('price','log_returns')`
3. `horizon >= 1 AND horizon <= 256`
4. `train_window_includes_contaminated IN (0, 1)`
5. `status IN ('success','failed')`
6. `failure_reason IS NULL OR failure_reason IN ('oom_killed','nan_loss','timeout','exit_nonzero','train_diverged','db_unreachable','unknown')`

**Migration runner idempotency verified:** 3 sequential runs against the same file produce identical state; `schema_version` table prevents double-apply.

**result_schema.py validator:**
- 256KB hard cap checked on `raw_bytes` BEFORE `json.load` (T-03-10)
- 10 required top-level fields validated
- Architecture/target_mode enum membership, horizon range [1,256]
- 7 metric sanity bounds checked on success rows
- D-15 failure_reason enum enforced on failed rows
- Pure function (no DB/FS) — fully unit-testable

**LeaderboardDB:**
- `run_migrations`: WAL mode, 0600 perms on first create (T-03-09)
- `insert_run`: raw literal SQL with 20 `?` placeholders — no value interpolation (T-03-08)
- `list_runs`: nullable-equality pattern (`? IS NULL OR col = ?`) — eliminates string concatenation, passes semgrep CWE-89 gate
- `upsert_tournament`, `update_tournament_counts`, `schema_version`, `get_tournament_config`

**Unit test counts:**
- `test_result_schema.py`: 12 tests (happy path + 11 reject paths)
- `test_leaderboard_db.py`: 8 tests (migration idempotency, 0600 mode, insert/list, failed run, SQL injection resistance, CHECK constraint enforcement, schema_version)
- **Total: 20 tests, all pass**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Contradictory f-string acceptance criteria in Task 3**
- **Found during:** Task 3 implementation (advisor pre-work call)
- **Issue:** Plan acceptance criteria simultaneously required `grep -c 'f"INSERT'` = 1 AND `grep -c "f\".*VALUES.*{"` = 0. The prescribed code `f"INSERT INTO leaderboard ({cols}) VALUES ({placeholders})"` matches the second grep and fails it.
- **Fix:** Replaced f-string construction with a raw string literal that spells out all 20 column names and 20 `?` placeholders inline. No f-string at all — both acceptance criteria effectively become 0/0.
- **Files modified:** `app/leaderboard/db.py`
- **Commit:** 3688c64

**2. [Rule 2 - Security] Semgrep CWE-89 flagged string concatenation in list_runs**
- **Found during:** Task 3 GREEN phase (semgrep PostToolUse hook)
- **Issue:** `sql = "SELECT * FROM leaderboard " + where + " ORDER BY..."` — semgrep flagged the WHERE string concatenation even though `clauses` contained only hardcoded column-name strings. Security gate requires 0 ERROR-severity findings.
- **Fix:** Rewrote `list_runs` to use nullable-equality pattern: `(? IS NULL OR col = ?)` for all 4 filter dimensions. Single fixed SQL string, no concatenation. All filter values still bound as `?` params.
- **Files modified:** `app/leaderboard/db.py`
- **Commit:** 3688c64

**3. [Rule 3 - Blocking] Worktree missing tests/smoke/ — pre-commit hook blocked all commits**
- **Found during:** Task 1 commit attempt
- **Issue:** The worktree was at commit `cdf46a6` (an ancestor of the required base `ebc399bd`). `tests/smoke/pytest.ini` only exists at `ebc399bd`+. The `PreToolUse:Bash` pre-commit smoke check hook ran pytest from the worktree cwd, found no `tests/smoke/`, and blocked all `git commit` commands.
- **Fix:** Reset worktree to `ebc399bd` per the `worktree_branch_check` protocol (`git reset --hard ebc399bd...`). After reset, `tests/smoke/` was present and 10 smoke tests passed. All subsequent commits succeeded.
- **Commits affected:** afa9aa7 and all subsequent

**4. [Rule 1 - Bug] Test count mismatch in plan**
- **Found during:** Task 3 GREEN phase
- **Issue:** Plan acceptance criteria said "7 tests pass" for `test_leaderboard_db.py`. The actual prescribed test file has 8 distinct test functions.
- **Fix:** All 8 tests implemented and pass. Count in SUMMARY reflects actual (8), not plan text (7). No tests were removed.

## TDD Gate Compliance

Both TDD tasks followed RED/GREEN protocol:

| Task | RED commit | GREEN commit |
|------|-----------|--------------|
| Task 2 (result_schema) | fc8b67c — 12 tests fail with ModuleNotFoundError | 667d52c — 12 tests pass |
| Task 3 (leaderboard_db) | 62a0533 — 8 tests fail with ModuleNotFoundError | 3688c64 — 8 tests pass |

## Known Stubs

None. All code paths are fully wired. No placeholder values, TODO comments, or mock data paths.

## Threat Flags

No new threat surface beyond what the plan's threat model covers. All four T-03-07 through T-03-10 mitigations are implemented:
- T-03-07: 256KB cap + field/type/range validation in result_schema.py
- T-03-08: Parameterised SQL only; CHECK constraint on failure_reason
- T-03-09: 0600 chmod on fresh DB create in run_migrations
- T-03-10: Size check on raw_bytes before json.load in validate()

## Self-Check: PASSED

All files present, all commits verified, 20 tests passing.
