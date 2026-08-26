---
phase: quick-260826-nzw
plan: 01
subsystem: portfolio-manager
tags: [health, readiness, asyncpg, observability, tdd]
requires: []
provides:
  - "portfolio-manager /health database_connection derived from live asyncpg pool probe"
  - "portfolio-manager GET /ready registered and probing the live pool"
affects:
  - monitoring/alerting that consumes portfolio-manager /health and /ready
tech-stack:
  added: []
  patterns:
    - "function-level import against app.main globals for test-patchable pool access"
    - "asyncio.wait_for hard-timeout probe that degrades instead of raising"
key-files:
  created:
    - services/portfolio-manager/tests/test_health_db_probe.py
  modified:
    - services/portfolio-manager/app/handlers/health.py
    - services/portfolio-manager/app/main.py
decisions:
  - "Registered GET /ready in main.py (Rule 2): readiness_check existed but was never wired to a route, so /ready returned 404 — plan must_haves and CLAUDE.md service contract both require the endpoint"
  - "Legacy shared.database.connection import kept verbatim as the pool-is-None fallback, per plan"
metrics:
  duration: "8m"
  completed: "2026-08-26"
  tasks: 2
  commits: 2
---

# Quick Task 260826-nzw: Fix portfolio-manager /health database_connection Summary

Live `SELECT 1` probe of `app.main.db_pool` (2s `asyncio.wait_for`) now drives `/health` `database_connection` and a newly registered `/ready`, demoting the dead in-container `shared.database.connection` import to a pool-is-None fallback.

## What was done

### Task 1: Probe the live asyncpg pool (TDD)

- **RED** (`b595a08`): 7 host-run tests in `tests/test_health_db_probe.py` via `TestClient(app)` (no lifespan), fake asyncpg pool built as MagicMock with `acquire()` returning an async-CM whose connection has `fetchval` as AsyncMock. RED state: 4 failed (probe behavior + `/ready` 404), 3 passed (current-behavior-preservation assertions — expected for regression-pinning tests).
- **GREEN** (`568d422`):
  - `health.py`: added `_probe_db_pool(pool)` — whole acquire+`SELECT 1` under `asyncio.wait_for(timeout=2.0)`; ANY exception (incl. `asyncio.TimeoutError`) → warning log + `False`, never an endpoint 500.
  - `health_check()`: `use_database` true → function-level `from app.main import db_pool`; pool present → probe; pool `None` → existing legacy `shared.database.connection` block unchanged. `use_database=False` path untouched (verified: pool never acquired).
  - `readiness_check()`: same shape; probe ok → `database: "ok"`, probe fail → 503 "Database unavailable"; pool `None` → legacy block preserved exactly (ImportError → "unavailable").

### Task 2: Full-suite regression

Baseline captured on untouched tree BEFORE edits: **132 passed, 321 skipped**. Post-change: **139 passed, 321 skipped** = baseline + 7 new, zero regressions. Skip-marked `test_health_handler.py` untouched (321 skip count unchanged).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Registered GET /ready in main.py**
- **Found during:** Task 1 (RED run — Tests 5-7 hit 404)
- **Issue:** `readiness_check` was exported from `app/handlers/__init__.py` but never wired to a route; portfolio-manager had NO `/ready` endpoint despite CLAUDE.md §3 ("Every service exposes GET /health and GET /ready") and the plan's must_have truths targeting `/ready` responses.
- **Fix:** Added `readiness_check` to main.py's handler import block and registered `@app.get("/ready")` next to `/health`. Route body is a one-line delegation, same pattern as `/health` and `/status`.
- **Files modified:** `services/portfolio-manager/app/main.py`
- **Commit:** `568d422`

**2. [Tooling note, not a code deviation] Format hook stripped the not-yet-used import, then line-joined unrelated main.py statements**
- The repo's PostToolUse format hook (autoflake) removed `readiness_check` from the import block when added before its usage (known trap, on record in project memory). Resolved by adding the route first, then re-adding the import. The same hook also line-joined 5 unrelated cosmetic sites in main.py (Gauge/labels/logger calls) — formatting only, no imports removed, no logic changed; included in the feat commit and flagged in its message.

## Verification results

- `pytest tests/test_health_db_probe.py --no-cov -q` → **7/7 pass**
- `pytest tests/ --no-cov -q` → **139 passed, 321 skipped** (baseline 132/321, zero new failures)
- `grep -n "from app.main import db_pool" app/handlers/health.py` → lines 73, 122; AST check confirms **0** module-level `app.main` imports (function bodies only)
- `grep -c "asyncio.wait_for" app/handlers/health.py` → 1
- In-container `curl /health` proof deliberately DEFERRED to orchestrator's deploy step (plan directive — no container restart/rebuild performed)

## Threat model compliance

- T-quick-01 (DoS, probe hang): mitigated — 2.0s `asyncio.wait_for` wraps acquire+query; all exceptions degrade to false/503.
- T-quick-02/03: accepted per plan, unchanged.
- T-quick-SC: zero new dependencies (asyncio stdlib; asyncpg already in main.py).
- The `/ready` registration realizes the plan's already-modeled `monitoring→/ready` boundary; no new unmodeled surface introduced.

## Known Stubs

None — probes are wired to the real pool; no placeholder values or dead data paths added.

## Worktree base discrepancy (noted per dispatch instructions)

Dispatch cited base `8212fdc` (main); this worktree branched from its parent `fad17e8` (8212fdc is a docs-only STATE commit on top of it). All plan target files were present and current; proceeded per instruction. The PLAN.md itself exists only in the main checkout's working tree (untracked there), not in the worktree — read from the main repo path, executed in the worktree.

## Commits

| Hash | Type | Description |
|---|---|---|
| `b595a08` | test | 7 failing tests for health/ready DB pool probe (RED) |
| `568d422` | feat | live pool probe + /ready registration (GREEN) |

## TDD Gate Compliance

RED gate: `test(...)` commit `b595a08` (4 behavior tests failing pre-implementation). GREEN gate: `feat(...)` commit `568d422` (7/7 pass). No refactor commit needed.

## Self-Check: PASSED

- `services/portfolio-manager/tests/test_health_db_probe.py` — FOUND
- `services/portfolio-manager/app/handlers/health.py` (contains `_probe_db_pool`) — FOUND
- Commit `b595a08` — FOUND
- Commit `568d422` — FOUND
- Working tree clean under `services/portfolio-manager` (no untracked/uncommitted code)
