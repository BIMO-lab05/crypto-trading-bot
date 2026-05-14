---
phase: "03"
plan: "07"
subsystem: "tournament-harness/orchestrator"
tags: ["orchestrator", "docker-sdk", "failure-classifier", "leaderboard-ingest", "d15-enum"]
dependency_graph:
  requires: ["03-03", "03-04"]
  provides: ["orchestrator/__init__.py", "orchestrator/failure.py", "orchestrator/ingest.py", "orchestrator/launcher.py"]
  affects: ["03-08"]
tech_stack:
  added: ["docker SDK containers.run", "subprocess git rev-parse"]
  patterns: ["TDD red-green for failure + ingest", "sequential for-loop launcher (D-03)", "bounded-read stat-before-open (T-03-25)", "password scrub regex (T-03-26)", "SIGTERM+grace+SIGKILL timeout (T-03-27)"]
key_files:
  created:
    - services/tournament-harness/app/orchestrator/__init__.py
    - services/tournament-harness/app/orchestrator/failure.py
    - services/tournament-harness/app/orchestrator/ingest.py
    - services/tournament-harness/app/orchestrator/launcher.py
    - services/tournament-harness/tests/unit/test_orchestrator_failure.py
    - services/tournament-harness/tests/unit/test_orchestrator_ingest.py
  modified: []
decisions:
  - "Formatter (black/ruff) expanded `labels={...tournament_id}` dict to multi-line; content correct, `labels=.*tournament_id` single-line grep fails but behavior intact — documented as formatter artifact deviation"
  - "MAX_RESULT_BYTES re-exported as module attribute from ingest.py via top-level import from result_schema — test import resolves without explicit __all__ entry"
metrics:
  duration: "12m 9s"
  completed_date: "2026-05-09"
  tasks_completed: 3
  files_created: 6
  files_modified: 0
  tests_added: 25
---

# Phase 03 Plan 07: Orchestrator + Failure Classifier — Sequential Docker SDK Launcher with Leaderboard Ingest Summary

**One-liner:** Docker SDK sequential tournament orchestrator with D-15 failure enum classifier, bounded result.json ingest, and SIGTERM→SIGKILL timeout enforcement, backed by 25 unit tests.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | failure.py test | a0d2d7c | tests/unit/test_orchestrator_failure.py |
| 1 (GREEN) | failure.py impl | 68fc699 | app/orchestrator/__init__.py, app/orchestrator/failure.py |
| 2 (RED) | ingest.py test | 7518afc | tests/unit/test_orchestrator_ingest.py |
| 2 (GREEN) | ingest.py impl | dd5d21e | app/orchestrator/ingest.py |
| 3 | launcher.py impl | 5d7de5b | app/orchestrator/launcher.py |

## What Was Built

### failure.py — D-15 Enum Classifier

`classify(container_state, result_payload, validation_error)` maps Docker-observable state to the D-15 enum with strict precedence ordering:

1. `TimedOut=True` → `timeout` (orchestrator-side observable wins)
2. `OOMKilled=True OR ExitCode==137` → `oom_killed`
3. Valid result.json + `status=success` → `success`
4. Valid result.json + `status=failed` + valid reason → runner-emitted typed reason (nan_loss, db_unreachable, train_diverged)
5. Validation error present + exit!=0 → `exit_nonzero`
6. Validation error present + exit==0 → `unknown`
7. No result.json + exit!=0 → `exit_nonzero`
8. exit==0 + no result.json → `unknown` (defensive bucket)

**D-15 enum size: 7** (oom_killed, nan_loss, timeout, exit_nonzero, train_diverged, db_unreachable, unknown)

### ingest.py — Bounded Read + Schema Validate + DB Insert Pipeline

`read_and_validate_result(path)` enforces trust boundary in this order:
- `path.stat().st_size > 262_144` → abort without opening (T-03-25)
- `path.read_bytes()` → `json.loads()` → `result_schema.validate()`
- Returns `(payload, None)` on valid, `(payload, error_str)` on schema violation, `(None, None)` on missing

`ingest_run(db, spec, container_state, result_path, stderr_tail)` implements TOURN-04:
- Every experiment inserts exactly one leaderboard row (success OR failed)
- Failed rows built from spec dict when result.json is missing/invalid
- `PASSWORD_SCRUB_RE` scrubs `TIMESCALE_PASSWORD=*` and `TOURNAMENT_READER_PASSWORD=*` from stderr_tail before persist (T-03-26)

### launcher.py — Docker SDK Sequential Loop

`launch_one_experiment()` Docker SDK call shape:
- `read_only=True`, `cap_drop=["ALL"]`, `tmpfs={"/tmp": "size=512m"}` (T-03-24)
- `mem_limit` + `nano_cpus` from spec resource_caps (D-04)
- `network=crypto-bot-network`, labels: tournament_id, run_id, architecture, symbol (D-02)
- Timeout: `container.wait(timeout=N)` → SIGTERM → 10s grace → SIGKILL → `container.remove(force=True)` (T-03-27)
- Full stdout.log + stderr.log persisted per run dir (CD-03)

`run_tournament(yaml_path)` end-to-end loop:
- Refuses dirty git tree unless `allow_dirty=True` (D-13)
- Refuses `TIMESCALE_PASSWORD` that is empty or `"CHANGE_ME_VIA_ENV"`
- Captures `git_sha` + `tournament_start_ts` once, propagates to every experiment (D-13)
- Sequential for-loop (D-03); `concurrent.futures` deferred to CD-04

## Test Coverage

| Test file | Tests | Status |
|-----------|-------|--------|
| test_orchestrator_failure.py | 13 | PASS |
| test_orchestrator_ingest.py | 12 | PASS |
| **Total** | **25** | **25/25** |

**TOURN-07 gate:** 0 metric function definitions in orchestrator modules (grep confirmed).

## Deviations from Plan

### Formatter Artifact

**[Rule 1 - No-op] labels dict reformatted to multi-line by black/ruff**
- **Found during:** Task 3 acceptance criteria check
- **Issue:** Plan criterion `grep -q 'labels=.*tournament_id'` does single-line match; formatter expanded dict to multi-line (each label on own line). Content is semantically correct.
- **Fix:** Not fixed — formatter style is correct Python; the label IS present (`"tournament_id": spec.tournament_id` on dedicated line). Import test and behavior verified.
- **Impact:** Zero — plan verification command 3 (`python -c "from app.orchestrator.launcher import ..."`) passes; Docker lockdown flags count = 4 (>= 3 required).
- **Commit:** 5d7de5b

## Threat Mitigations Applied

| Threat ID | Applied | Evidence |
|-----------|---------|----------|
| T-03-24 | Yes | `read_only=True, cap_drop=["ALL"], tmpfs={"/tmp": ...}` in launcher.py |
| T-03-25 | Yes | `path.stat().st_size > MAX_RESULT_BYTES` abort before `json.loads` in ingest.py |
| T-03-26 | Yes | `PASSWORD_SCRUB_RE` scrubs TIMESCALE_PASSWORD + TOURNAMENT_READER_PASSWORD in ingest.py |
| T-03-27 | Yes | SIGTERM → 10s grace → SIGKILL → remove(force=True) in launcher.py |
| T-03-28 | Yes | result_schema sanity ranges enforced by result_schema.validate before insert |

## Known Stubs

None — all orchestrator functions are complete implementations. `run_tournament` requires live Docker socket and valid settings to execute end-to-end; unit test coverage is at the ingest/classify level (where no Docker is needed).

## Threat Flags

None — no new network endpoints or trust boundaries introduced beyond what the plan's threat model already covers.

## Self-Check: PASSED

All 6 created files confirmed on disk. All 5 task commits confirmed in git log.
