---
phase: 08-pre-live-preflight
plan: 01
subsystem: trading-engine
tags:
  - preflight
  - foundation
  - PREFLIGHT-01

requires: []
provides:
  - app.preflight.run_all
  - app.preflight.CheckResult
  - app.preflight.PreflightReport
  - app.preflight.check_cap
  - app.preflight.check_paper_mode
  - app.preflight.check_trading_mode
  - app.preflight.check_ack
  - app.preflight.check_emergency_stop
  - app.preflight.check_dsr_evidence
affects:
  - services/trading-engine

tech_stack_added: []
patterns:
  - stdlib-only @dataclass(frozen=True) for JSON-safe value types
  - module-level path constants overridable via monkeypatch.setattr (avoids
    mass-patching pathlib.Path.is_file across checks)
  - Pydantic v2 keyword-arg constructor for unit-test Settings overrides
  - production-faithful sqlite fixture schema + meta-test guarding
    fixture-vs-production type-semantic drift

key_files_created:
  - services/trading-engine/app/preflight/__init__.py
  - services/trading-engine/app/preflight/types.py
  - services/trading-engine/app/preflight/checks.py
  - services/trading-engine/tests/test_preflight_checks.py
key_files_modified: []

decisions:
  - REQUIREMENTS.md says tournament_results table; actual schema defines
    leaderboard with the dsr column. Phase 8 reads from leaderboard per
    08-CONTEXT.md lines 95-101. REQUIREMENTS.md wording needs a docs-only
    cleanup commit (not a separate phase).
  - paper_trading_mode is NOT a Pydantic Settings field — config.py exposes
    only trading_mode and emergency_stop_file. check_paper_mode reads
    PAPER_TRADING_MODE from os.environ directly, mirroring check_ack's
    direct-env pattern (same trust source as main.py:251). Documented as a
    deviation below.
  - DSR fixture schema declares tournament_start_ts TEXT NOT NULL (matches
    production schema 0001_initial.sql:28), not INTEGER. Meta-test
    test_dsr_fixture_schema_matches_production guards against regression.
  - The boot-reject log literal does NOT appear in checks.py — the
    PREFLIGHT-02 boot-path log emission lives in main.py per Phase 8 plan
    03 (the grep-gate scope deliberately catches its removal, not its
    relocation; keeping it scoped to one file keeps the gate sharp).
  - DSR check's default db_path is /data/tournament.db; overridable via
    keyword argument for tests + non-default deploys.

metrics:
  duration_minutes: 25
  completed: 2026-05-16
  files_created: 4
  files_modified: 0
  tests_added: 23
  tests_passed: 23
  commits: 3
---

# Phase 8 Plan 1: Preflight Core Module Summary

Shared preflight check module — 6 pure functions + run_all aggregator + frozen
dataclass result types — committed as the foundation layer that Phase 8 plans
02/03/04 will all import from.

## Tasks Completed

| Task | Name                                                  | Commit  | Files                                                                                  |
| ---- | ----------------------------------------------------- | ------- | -------------------------------------------------------------------------------------- |
| 1    | Create preflight package skeleton + dataclass types   | 321d901 | `app/preflight/__init__.py`, `app/preflight/types.py`                                  |
| 2    | Implement 6 check functions + run_all aggregator      | 9b41e17 | `app/preflight/checks.py` + uncomment `__init__.py` re-exports                         |
| 3    | Unit tests for every check + run_all                  | aa2553f | `tests/test_preflight_checks.py`                                                       |

## Source Files

| File                                                              | Lines | Purpose                                                                                                              |
| ----------------------------------------------------------------- | ----- | -------------------------------------------------------------------------------------------------------------------- |
| `services/trading-engine/app/preflight/__init__.py`               | 37    | Re-exports public surface (`run_all`, 6 check fns, `CheckResult`, `PreflightReport`); mirrors `app/lifespan/__init__.py` |
| `services/trading-engine/app/preflight/types.py`                  | 80    | `CheckResult` + `PreflightReport` frozen dataclasses; `schema_version=1`; `to_dict()`/`to_json()` helpers             |
| `services/trading-engine/app/preflight/checks.py`                 | 310   | 6 pure check functions + `run_all` aggregator; stdlib + `app.config` + `sqlite3` only (no FastAPI)                   |
| `services/trading-engine/tests/test_preflight_checks.py`          | 412   | 23 unit tests covering PASS/FAIL/UNKNOWN paths for each check + run_all precedence + meta-test schema guard            |
| **Total**                                                         | **839** |                                                                                                                      |

## Tests

```
============================= test session starts ==============================
collected 23 items

tests/test_preflight_checks.py::test_check_cap_paper_allows_10pct PASSED
tests/test_preflight_checks.py::test_check_cap_live_rejects_3pct PASSED
tests/test_preflight_checks.py::test_check_cap_live_accepts_2pct PASSED
tests/test_preflight_checks.py::test_check_paper_mode_non_live_skips PASSED
tests/test_preflight_checks.py::test_check_paper_mode_live_with_true_fails PASSED
tests/test_preflight_checks.py::test_check_paper_mode_live_with_false_passes PASSED
tests/test_preflight_checks.py::test_check_trading_mode_live_passes PASSED
tests/test_preflight_checks.py::test_check_trading_mode_paper_fails PASSED
tests/test_preflight_checks.py::test_check_ack_present PASSED
tests/test_preflight_checks.py::test_check_ack_missing_in_live PASSED
tests/test_preflight_checks.py::test_check_ack_skipped_in_paper PASSED
tests/test_preflight_checks.py::test_check_emergency_stop_file_present PASSED
tests/test_preflight_checks.py::test_check_emergency_stop_directory_at_path_is_not_file PASSED
tests/test_preflight_checks.py::test_check_emergency_stop_absent PASSED
tests/test_preflight_checks.py::test_check_dsr_evidence_ml_disabled_passes PASSED
tests/test_preflight_checks.py::test_check_dsr_evidence_ml_enabled_no_marker_is_unknown PASSED
tests/test_preflight_checks.py::test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes PASSED
tests/test_preflight_checks.py::test_check_dsr_evidence_ml_enabled_with_row_at_or_below_gate_fails PASSED
tests/test_preflight_checks.py::test_run_all_returns_six_checks_in_order PASSED
tests/test_preflight_checks.py::test_run_all_overall_fail_when_any_check_fails PASSED
tests/test_preflight_checks.py::test_run_all_overall_unknown_when_no_fail_but_unknown PASSED
tests/test_preflight_checks.py::test_run_all_overall_pass_when_all_pass PASSED
tests/test_preflight_checks.py::test_dsr_fixture_schema_matches_production PASSED

============================== 23 passed in 0.71s ==============================
```

23/23 passing — exceeds the plan's `>=13` floor.

## Sample `run_all()` Output

In the default trading-engine env (PAPER mode, ML off), `run_all()` returns:

```python
schema_version: 1
overall: FAIL
checks: [
    ('cap', 'PASS'),               # PAPER skips cap check (ADR-010)
    ('paper_mode', 'PASS'),         # non-LIVE skipped
    ('trading_mode', 'FAIL'),       # TRADING_MODE=PAPER (not LIVE)
    ('ack', 'PASS'),                # non-LIVE skipped
    ('emergency_stop', 'PASS'),     # no file at /app/EMERGENCY_STOP
    ('dsr_evidence', 'PASS'),       # ENABLE_ML_PREDICTIONS=false skip
]
```

`overall=FAIL` is correct: from the LIVE-readiness perspective, a system that
is in PAPER mode is not LIVE-ready. The aggregate flips to `PASS` only when all
six checks individually return PASS (LIVE + ack + paper_mode=false + cap<=0.02
+ no emergency-stop file + ML off or DSR row above 0.95).

## Decisions Made

### Table name: `leaderboard` not `tournament_results`

REQUIREMENTS.md PREFLIGHT-01 wording references a `tournament_results` table
that does NOT exist. The actual schema (`services/tournament-harness/migrations/0001_initial.sql:9`)
defines a `leaderboard` table with a `dsr REAL` column and an index on
`(tournament_id, dsr DESC)`. This plan reads from `leaderboard` per
08-CONTEXT.md lines 95-101.

**Follow-up:** REQUIREMENTS.md PREFLIGHT-01 should be updated to reference
the actual table name. This is a docs-only cleanup, not a separate plan;
should land in Phase 8 plan 04 or a standalone docs commit.

### `tournament_start_ts` column type

Production schema declares this column as `TEXT NOT NULL` (ISO-8601 string,
line 28 of the migration). The DSR check's `ORDER BY tournament_start_ts DESC`
relies on lexicographic ordering of fixed-width ISO-8601 strings — which is
also chronological. The test fixture matches production type semantics
(`TEXT NOT NULL`, ISO-8601 string `'2026-05-16T14:32:01Z'`), and the
meta-test `test_dsr_fixture_schema_matches_production` enforces this by
source-inspecting the test file.

The meta-test's forbidden literal is constructed at runtime via string
concatenation so it does not appear in this file's source and self-trigger.

### `_MLGATE_MARKER_PATH` as module-level constant

The Phase 9 (MLGATE-02) auto-flip marker path is exposed as a module-level
constant `_MLGATE_MARKER_PATH` so tests can override it via
`monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", ...)`.

The alternative — mass-patching `pathlib.Path.is_file` — would also affect
`check_emergency_stop` and create cross-check leakage. The constant approach
keeps each check independently testable.

### DSR sqlite error handling

`sqlite3.Error` exceptions return `UNKNOWN` with the exception class name
only (`type(e).__name__`), not the full message. Full sqlite error strings
can include filesystem paths; keeping the leak surface to the class name
matches the disclosure level of `/api/config/safety-state` (D-09).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan referenced non-existent `paper_trading_mode` Settings field**

- **Found during:** Task 2 read-first review of `services/trading-engine/app/config.py`.
- **Issue:** Plan's `<behavior>` for `check_paper_mode` says read `s.paper_trading_mode`. Grep over `services/trading-engine/app/` and `config.py` confirms there is no such field on the `Settings` model; `PAPER_TRADING_MODE` is consumed elsewhere in compose/bybit-connector wiring.
- **Fix:** `check_paper_mode` reads `os.environ.get("PAPER_TRADING_MODE", "false")` directly. This mirrors `check_ack`'s direct-env pattern (which uses the same source-of-truth as the existing `LIVE_TRADING_ACK` lifespan check at `main.py:251`). The function signature still accepts `settings: Settings | None = None` for symmetry with the other checks; `settings.trading_mode` is still used to short-circuit non-LIVE modes.
- **Files modified:** `services/trading-engine/app/preflight/checks.py` (only — no plan amendment needed since this is a Rule 3 implementation-detail fix).
- **Commit:** 9b41e17.

**2. [Rule 1 - Bug] Meta-test self-tripped on docstring containing forbidden literal**

- **Found during:** Task 3 first test run — 22/23 passed, meta-test failed because its own assertion message string contained the literal `"tournament_start_ts INTEGER"`.
- **Issue:** The meta-test reads its own source file and asserts the forbidden form is NOT present. The forbidden literal cannot appear anywhere in the file, including inside the assertion or its message.
- **Fix:** The forbidden literal is constructed at runtime via string concatenation (`column + " " + "INT" + "EGER"`) so it does not exist as a contiguous substring in the source.
- **Files modified:** `services/trading-engine/tests/test_preflight_checks.py` (single-test fix).
- **Commit:** aa2553f (included in the Task 3 commit before push).

**3. [Rule 1 - Bug] Forbidden grep-gate literal appeared in checks.py docstring**

- **Found during:** Task 2 acceptance grep — `LIVE_PREFLIGHT_REJECTED` count was 1 (in a docstring) when the plan requires 0.
- **Issue:** The plan's acceptance criteria require that the boot-reject log literal does NOT appear in `checks.py`. The first draft's module docstring mentioned the literal verbatim while explaining why the literal lives only in `main.py`.
- **Fix:** Rephrased the docstring to convey the same point without using the literal token. The semantic guidance is preserved; the grep-gate scope is now sharp.
- **Files modified:** `services/trading-engine/app/preflight/checks.py` docstring.
- **Commit:** 9b41e17.

### Worktree placement

First file writes accidentally landed in `/mnt/d/Bimo_max/crypto-trading-bot/services/...` (parent repo) instead of the worktree at `/mnt/d/Bimo_max/crypto-trading-bot/.claude/worktrees/agent-a0382da404036fa34/services/...`. Detected before commit; files were moved into the worktree and the parent-repo copies removed. No commit landed on the wrong branch. All subsequent operations use absolute paths anchored at the worktree root and `git -C <worktree>` for git ops.

## TDD Gate Compliance

This plan's commit sequence is `feat → feat → test` (Tasks 1, 2, 3), not the
standard TDD `test → feat → refactor` cycle. This is intentional per the plan
structure — Tasks 1 and 2 build foundation scaffolding (dataclasses + check
fns) that the Task 3 tests then exercise. The plan's per-task acceptance
criteria are all satisfied; the workflow-level TDD-gate check that looks for
`test(...)` before `feat(...)` will flag this as a warning. The warning is
expected and documented here per the plan's explicit foundation-first
ordering.

## Threat Surface Scan

No new attack surface introduced. The threat register entries in the plan
(T-08-01-01 through T-08-01-06) are all addressed:

| Threat ID    | Disposition | Status                                                                                  |
| ------------ | ----------- | --------------------------------------------------------------------------------------- |
| T-08-01-01   | mitigate    | DSR query uses parameter-free literal SQL; column is whitelisted in code, no user input |
| T-08-01-02   | mitigate    | `check_emergency_stop` uses `.is_file()` not `.exists()` for WSL bind-mount safety       |
| T-08-01-03   | accept      | MLGATE marker file in same trust domain as host; main.py boot path is the hard gate    |
| T-08-01-04   | accept      | `check_ack` reads `os.environ` directly to mirror main.py:251 (no Settings cache race) |
| T-08-01-05   | accept      | `CheckResult.detail` strings contain config values, not secrets (D-09 disclosure)      |
| T-08-01-06   | mitigate    | `test_dsr_fixture_schema_matches_production` meta-test asserts type semantics          |

No `threat_flag` items — no new endpoints, no auth surface added, no schema
changes at trust boundaries.

## Self-Check: PASSED

- `services/trading-engine/app/preflight/__init__.py` — FOUND
- `services/trading-engine/app/preflight/types.py` — FOUND
- `services/trading-engine/app/preflight/checks.py` — FOUND
- `services/trading-engine/tests/test_preflight_checks.py` — FOUND
- commit 321d901 — FOUND
- commit 9b41e17 — FOUND
- commit aa2553f — FOUND
- behavior: `from app.preflight import run_all; r = run_all()` returns 6 checks with schema_version=1 — VERIFIED
- behavior: `pytest tests/test_preflight_checks.py` exits 0 with 23 passed — VERIFIED
- grep gate: `schema_version` in types.py — 5 occurrences (>=1)
- grep gate: `frozen=True` in types.py — 2 occurrences (>=2)
- grep gate: `is_file()` in checks.py — 3 occurrences (>=1)
- grep gate: `FROM leaderboard` in checks.py — 1 occurrence (>=1)
- grep gate: `LIVE_PREFLIGHT_REJECTED` in checks.py — 0 occurrences (==0)
- grep gate: 7 named function defs in checks.py — confirmed
- grep gate: test count in test file — 23 (>=13)
- grep gate: `tournament_start_ts TEXT NOT NULL` — 2 occurrences (>=1)
- grep gate: `tournament_start_ts INTEGER` — 0 occurrences (==0)
- grep gate: meta-test name — 2 occurrences (=1 in plan; the docstring + def line both match; both required)
- grep gate: ISO-8601 timestamp literal `'2026-05-16T14:32:01Z'` — 1 occurrence (>=1)
- no fastapi import in `app/preflight/*.py` — VERIFIED
