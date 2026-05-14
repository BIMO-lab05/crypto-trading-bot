---
phase: "03"
plan: "03-08"
subsystem: "tournament-harness"
tags: ["cli", "leaderboard", "dsl", "snapshot", "security", "tdd"]
dependency_graph:
  requires: ["03-03", "03-07"]
  provides: ["CLI surface (run/leaderboard/export-snapshot)", "safe WHERE DSL", "JSON snapshot exporter (D-18)", "FastAPI list endpoints wired"]
  affects: ["downstream Phase 4 (TOURN-05/06 significance test)", "downstream Phase 7 (DASH-04 dashboard)"]
tech_stack:
  added: ["argparse (stdlib CLI)", "tempfile+os.replace (atomic writes)"]
  patterns: ["tokeniser+whitelist+parameterised SQL (T-03-29)", "atomic file write pattern (T-03-32)", "TDD RED/GREEN per task"]
key_files:
  created:
    - "services/tournament-harness/app/cli.py"
    - "services/tournament-harness/app/leaderboard/queries.py"
    - "services/tournament-harness/app/leaderboard/snapshot.py"
    - "services/tournament-harness/tests/unit/test_leaderboard_queries.py"
    - "services/tournament-harness/tests/unit/test_leaderboard_snapshot.py"
  modified:
    - "services/tournament-harness/app/main.py"
decisions:
  - "Removed old GET /api/v1/tournaments/{tournament_id} stub when adding /runs sub-path to avoid dual-stub false-pass (Rule 3 deviation)"
  - "Pre-existing CORS allow_origins=['*'] pattern left as-is — present in 8 other services, out-of-scope for this task"
  - "Created tests/smoke symlink in worktree to satisfy pre-commit smoke-check hook (Rule 3 deviation)"
metrics:
  duration: "~47 minutes"
  completed: "2026-05-09T15:01:16Z"
  tasks_completed: 3
  tests_added: 19
  files_created: 5
  files_modified: 1
---

# Phase 03 Plan 08: CLI surface + leaderboard query DSL + JSON snapshot exporter Summary

stdlib argparse CLI (run/leaderboard list/export-snapshot) + safe tokeniser-whitelist-parameterised WHERE DSL + atomic JSON snapshot exporter (D-18) + FastAPI list endpoints wired to LeaderboardDB.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for queries DSL | 498d7e5 | tests/unit/test_leaderboard_queries.py |
| 1 (GREEN) | Implement leaderboard/queries.py | 3dc048c | app/leaderboard/queries.py |
| 2 (RED) | Failing tests for snapshot exporter | cd1bf4a | tests/unit/test_leaderboard_snapshot.py |
| 2 (GREEN) | Implement leaderboard/snapshot.py | 91fb993 | app/leaderboard/snapshot.py |
| 3 | CLI + main.py wiring | 3cdc12b | app/cli.py, app/main.py |

## CLI Subcommands

| Subcommand | Description |
|------------|-------------|
| `run <yaml_path> [--allow-dirty]` | Launch tournament via orchestrator.run_tournament |
| `leaderboard list [--tournament-id ID] [--top N] [--by COL] [--where DSL]` | Query leaderboard via safe DSL |
| `export-snapshot <tournament_id> [--output PATH]` | Write committable JSON snapshot (D-18) |

## DSL Allowlist

- **ALLOWED_FILTER_COLS** (10): tournament_id, run_id, architecture, symbol, horizon, target_mode, hp_hash, status, failure_reason, train_window_includes_contaminated
- **ALLOWED_ORDER_BY** (9): r2_returns, dir_acc_corrected, oos_sharpe, psr, dsr, cpcv_dsr, train_seconds, created_at, horizon
- **ALLOWED_OPS** (8): =, !=, <, <=, >, >=, LIKE, IN
- **Joiners**: AND, OR
- **Pre-filter** rejects: ; -- /* */ UNION SELECT INSERT UPDATE DELETE DROP ALTER ATTACH DETACH

## Atomic Snapshot Verified

`tempfile.mkstemp` + `os.replace` pattern (T-03-32) — no leftover `.tmp` files on success or failure. File mode set to 0644.

## Test Results

- **queries DSL**: 14 tests pass (happy paths + injection rejection + clamp-to-max + parameterised execution)
- **snapshot exporter**: 5 tests pass (round-trip + unknown-tournament + atomicity + failed rows + empty tournament)
- **Total**: 19 tests added, all green

## TOURN-07 Compliance

`grep -r "def directional_accuracy|def sharpe|def deflated" services/tournament-harness/ --include='*.py' | grep -v '/tests/' | wc -l` = **0**

No metric function definitions in any of the new files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed old get_tournament stub when wiring list_runs**
- **Found during:** Task 3
- **Issue:** main.py had `GET /api/v1/tournaments/{tournament_id}` stub returning empty runs list. Plan calls for `GET /api/v1/tournaments/{tournament_id}/runs`. Leaving both would mean the empty stub persisted at the shorter path.
- **Fix:** Replaced the old `get_tournament` handler with the new `list_runs` handler at the `/runs` sub-path only. Old stub removed entirely.
- **Files modified:** services/tournament-harness/app/main.py
- **Commit:** 3cdc12b

**2. [Rule 3 - Blocking] Created tests/smoke symlink in worktree for pre-commit hook**
- **Found during:** Task 1 RED commit
- **Issue:** Pre-commit smoke-check hook runs `pytest -c tests/smoke/pytest.ini tests/smoke` from cwd (the worktree directory), but the worktree had no `tests/smoke/` directory. Hook blocked every commit.
- **Fix:** `ln -sfn /mnt/d/Bimo_max/crypto-trading-bot/tests/smoke /mnt/d/Bimo_max/crypto-trading-bot/.claude/worktrees/agent-a15bf71321996e66f/tests/smoke`
- **Commit:** N/A (filesystem symlink, not committed)

### Out-of-scope Items

**Pre-existing CORS allow_origins=["*"]** in main.py — semgrep WARNING fired on write. Pattern exists in 8 other services; not introduced by this plan. Logged to deferred-items, not fixed.

## Known Stubs

None — all FastAPI endpoints now query LeaderboardDB. The old empty stubs from 03-01 have been replaced.

## Threat Surface Scan

No new threat surface beyond what the plan's threat model already covers:
- `--where` DSL: mitigated by T-03-29 (tokeniser+whitelist+parameterised)
- Snapshot atomic write: mitigated by T-03-32 (tempfile+os.replace)
- `--top` clamp: mitigated by T-03-31 (min(N, 10_000))
- CORS wildcard: pre-existing, not introduced here

## Self-Check

Files exist:
- `test -f services/tournament-harness/app/leaderboard/queries.py` — FOUND
- `test -f services/tournament-harness/app/leaderboard/snapshot.py` — FOUND
- `test -f services/tournament-harness/app/cli.py` — FOUND
- `test -f services/tournament-harness/tests/unit/test_leaderboard_queries.py` — FOUND
- `test -f services/tournament-harness/tests/unit/test_leaderboard_snapshot.py` — FOUND

Commits exist (git log --all):
- 498d7e5 test(03-08): add failing tests for leaderboard queries DSL — FOUND
- 3dc048c feat(03-08): implement leaderboard/queries.py — FOUND
- cd1bf4a test(03-08): add failing tests for leaderboard snapshot exporter — FOUND
- 91fb993 feat(03-08): implement leaderboard/snapshot.py — FOUND
- 3cdc12b feat(03-08): implement cli.py + wire main.py FastAPI list endpoints — FOUND
