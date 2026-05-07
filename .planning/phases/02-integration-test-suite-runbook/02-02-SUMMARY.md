---
phase: 02-integration-test-suite-runbook
plan: 02
subsystem: trading-engine
tags: [infra, admin-endpoint, integration-test-fixture, security-gate, cd-04]
requires:
  - StrategyOrchestrator (services/trading-engine/app/orchestration/orchestrator.py)
  - SignalSubmissionRequest (existing pydantic model)
  - settings.trading_mode (services/trading-engine/app/config.py:193)
provides:
  - POST /api/v1/admin/force-signal endpoint (trading-engine, port 8005)
  - admin_force_signal_router (importable from app.handlers.orchestration)
  - Audit log line "FORCE_SIGNAL: strategy_id=... symbol=... action=... direction=..."
affects:
  - Plan 02-04 will use this endpoint via the force_signal fixture in tests/integration/conftest.py
tech-stack:
  added: []
  patterns:
    - "admin-router prefix convention (/api/v1/admin/*)"
    - "TRADING_MODE != LIVE mode-gate as security boundary (no auth middleware)"
    - "logger.warning() for state-transition audit lines (grep-able from compose logs)"
key-files:
  created:
    - services/trading-engine/tests/test_force_signal.py
  modified:
    - services/trading-engine/app/handlers/orchestration.py
    - services/trading-engine/app/main.py
decisions:
  - "CD-04 (force-signal endpoint host): Option A — trading-engine itself, no auth middleware. Consistent with project pattern: trading-engine has no auth; gate at api-gateway upstream. TRADING_MODE != LIVE is the security boundary."
  - "Endpoint reuses the EXACT signal-construction sequence from submit_signal (line 646). Intentional duplication, not refactor — Phase 2 keeps this contained."
  - "Sanitization (T-02-02-03): logger.warning() takes ONLY controlled scalars (strategy_id, symbol, action, direction). request.reasoning is NEVER logged — log injection vector."
metrics:
  duration: ~25 min
  completed: 2026-05-07T21:54:00Z
  task_count: 2
  test_count: 4
  files_changed: 3
---

# Phase 02 Plan 02: Force-Signal Admin Endpoint Summary

**One-liner:** Add `POST /api/v1/admin/force-signal` on trading-engine with `TRADING_MODE != LIVE` mode-gate, sanitized audit log, and 4-test pytest module — provides the deterministic synthetic-signal entry point that Plan 02-04's `<60s` round-trip integration test depends on.

## What Shipped

### Task 1 — `admin_force_signal_router` with POST endpoint (orchestration.py + test_force_signal.py)

**Endpoint:** `POST /api/v1/admin/force-signal` accepts a `SignalSubmissionRequest` body, builds a `StrategySignal` with a deterministic `signal_id` matching `^sig_\d{8}_\d{6}_[a-f0-9]{8}$`, calls `orchestrator.submit_signal(signal)`, and returns the signal_id + orchestrator result for downstream test correlation.

**Security gate:** Refuses with **HTTP 403** when `settings.trading_mode == "LIVE"`. The gate runs **before** the orchestrator call — `submit_signal` is never invoked in LIVE mode (verified by `mock.assert_not_called()`).

**Audit log line:** `logger.warning("FORCE_SIGNAL: strategy_id=%s symbol=%s action=%s direction=%s", ...)` written on every successful invocation. Grep-able from `docker compose logs trading-engine | grep FORCE_SIGNAL`. Sanitization: free-form `request.reasoning` is **never** passed to the logger — only controlled scalars from the request body. Mitigates log-injection (T-02-02-03).

**Tests** (`services/trading-engine/tests/test_force_signal.py`, 4 tests, all PASS):
1. `test_force_signal_paper_mode_returns_200` — happy path: 200 + `signal_id` matches regex + `orchestrator.submit_signal` called once.
2. `test_force_signal_live_mode_returns_403` — LIVE-mode refusal: 403 + detail mentions "LIVE" + `submit_signal` NOT called.
3. `test_force_signal_missing_strategy_id_returns_422` — pydantic validation: 422 + orchestrator NOT reached.
4. `test_force_signal_emits_audit_log_line` — caplog assertion: `"FORCE_SIGNAL: strategy_id="` appears in WARNING-level logs **and** `request.reasoning` does NOT (sanitization check).

### Task 2 — Router mount in main.py

**`services/trading-engine/app/main.py`:**
- Added `admin_force_signal_router` to the multi-line import block at line 134 (alongside `admin_indicator_router`)
- Added `app.include_router(admin_force_signal_router)` at line 418, directly after the indicator-gate mount

**Verification:** `python3 -c "from app.main import app; assert any(r.path == '/api/v1/admin/force-signal' for r in app.routes)"` exits 0. Total registered routes: 141.

## Files Modified + Commit SHAs

| File | Lines Changed | Commit |
|------|---------------|--------|
| `services/trading-engine/app/handlers/orchestration.py` | +97 (force-signal block) + autoflake/black reformat of unrelated regions | `c1ba3ab` (absorbed into a concurrent-agent commit during a parallel-execution shared-tree race — see Deviations) |
| `services/trading-engine/tests/test_force_signal.py` | +231 (new file) | `2589dcd` (absorbed into a concurrent-agent's 02-07 finalization commit during the same race) |
| `services/trading-engine/app/main.py` | +6 (import + include_router) | `9c844fc` (this plan's primary commit) |
| `.planning/phases/02-integration-test-suite-runbook/02-02-SUMMARY.md` | +this file | (next commit) |

## Test Count

**4 tests** in `services/trading-engine/tests/test_force_signal.py`. All PASS (`pytest tests/test_force_signal.py -v` → `4 passed in 149.97s`). Coverage report shows 25% project total (file-local coverage on the new endpoint at >90%).

## Decisions Addressed

| Decision | How |
|----------|-----|
| **CD-04** — force-signal endpoint host (Option A: trading-engine, no auth) | Endpoint mounted at `/api/v1/admin/force-signal` on port 8005. No auth middleware (consistent with project pattern). `TRADING_MODE != LIVE` is the only security boundary. |

## Threat Items Closed

| Threat | Disposition | Mitigation |
|--------|-------------|------------|
| **T-02-02-01** (E — elevation: force-signal in LIVE mode) | mitigate | `if settings.trading_mode == "LIVE": raise HTTPException(403)` runs BEFORE any orchestrator call. Verified by `test_force_signal_live_mode_returns_403`. |
| **T-02-02-02** (T — tampering: synthetic signal in real-money pipeline) | mitigate | Same 403 gate. Plus the project's existing three-flag LIVE checklist (`PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`) — even with all three set, this endpoint refuses. |
| **T-02-02-03** (I — log injection via free-form `reasoning`) | mitigate | `logger.warning(...)` excludes `request.reasoning`. Only controlled scalars: `strategy_id`, `symbol`, `action`, `direction`. Verified by acceptance criterion `! grep "request.reasoning" .. \| grep logger` AND the caplog assertion in `test_force_signal_emits_audit_log_line`. |
| **T-02-02-04** (D — DoS: rate-limit on admin endpoint) | accept | trading-engine has no slowapi installed. Per-test cadence (≤10 calls/run) does not warrant the dep. The LIVE gate refuses BEFORE orchestrator call, so no DoS vector through `submit_signal`. |
| **T-02-02-05** (R — repudiation: unaudited admin call) | mitigate | Single WARNING-level log line per call. CI log audit (Plan 02-09) and RUNBOOK triage (Plan 02-07) rely on this — `docker compose logs trading-engine \| grep FORCE_SIGNAL` is the audit interface. |
| **T-02-02-06** (S — spoofing: no-auth network exposure) | accept | Consistent with project pattern. `TRADING_MODE` gate is the security boundary. Operator/deploy errors that expose `:8005` outside docker network are tracked elsewhere. |

## Deviations from Plan

### [Concurrent-agent shared-tree index race]

**Found during:** Tasks 1 & 2 commit phase

**Issue:** I ran inside the main repo (not a worktree — `.git` is a directory). Concurrent worktree-agents executing other Phase 2 plans (02-01, 02-07) absorbed my Task 1 file edits into their commits via the shared working tree. By the time I tried to `git commit` the orchestration.py + test file changes for Task 1, the repo reported `nothing to commit, working tree clean` — my changes had already been bundled into:

- **`c1ba3ab feat(02-01): add POST /admin/tape/reset endpoint with mode-gating`** — this commit's stat shows `services/trading-engine/app/handlers/orchestration.py | 211 +++++++++++++----` which is precisely my Task 1 force-signal block. Mislabeled under 02-01 due to the race.
- **`2589dcd docs(02-07): complete failure-triage RUNBOOK plan`** — included `services/trading-engine/tests/test_force_signal.py | 231 +++++++++++++++++++++` (the new file I wrote).

**Resolution:** I did NOT attempt to revert, amend, or rebase those commits — that would clobber the concurrent agents' work. Instead I:
1. Verified the orchestration.py and test_force_signal.py at HEAD match my intended content (confirmed via `git show HEAD:... | grep ...`).
2. Re-confirmed all 6 acceptance criteria for Task 1 still pass (greps + 4-test pytest run).
3. Did Task 2 fresh — staged main.py immediately to mitigate re-occurrence of the race, committed as `9c844fc feat(02-02): mount admin_force_signal_router in trading-engine main.py`.

**Precedent:** `25caa6e docs(02-07): note concurrent-agent index race in plan summary` — same race noted by the 02-07 plan summary author.

### [Hook formatter side-effects on orchestration.py]

**Found during:** Task 1 implementation phase

**Issue:** A PostToolUse hook (autoflake + black, per project memory) reformatted `services/trading-engine/app/handlers/orchestration.py` after my Edit, stripping unused imports (`StrategyOrchestrator`, `AllocationMethod`, `RegisterStrategyRequest`, `UpdateAllocationRequest`, `MetricsTrade`) and reformatting unrelated whitespace.

**Resolution:** Verified via `grep -rn` that the stripped imports were truly unused both inside the file and across all callers (no test mocks reference them). Module imports cleanly: `python3 -c "from app.handlers.orchestration import admin_force_signal_router, router, admin_indicator_router"` succeeds. All 4 tests pass on the formatted file. No regression. The reformatting is cosmetic and does not affect plan deliverables.

## Carry-Forward Notes

**For Plan 02-04 (`<60s round-trip` integration test):**

The `force_signal` fixture in `tests/integration/conftest.py` should call:
```python
import httpx

async def force_signal(strategy_id: str, symbol: str, action: str, direction: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8005/api/v1/admin/force-signal",
            json={
                "strategy_id": strategy_id,
                "symbol": symbol,
                "direction": direction,
                "action": action,
                "strength": 0.5,
                "confidence": 0.5,
            },
        )
    resp.raise_for_status()
    return resp.json()["signal_id"]
```

The returned `signal_id` (matching `^sig_\d{8}_\d{6}_[a-f0-9]{8}$`) is the correlator for downstream DB row queries (`SELECT * FROM signals WHERE signal_id = $1`).

**For Plan 02-09 (CI log audit / anti-mock guard):**

The audit grep target is the literal string `FORCE_SIGNAL: strategy_id=` at WARNING level. CI may add this to its allow-list of expected log lines and assert at least one occurrence per integration-test run.

**For Plan 02-07 (RUNBOOK):**

If the integration suite reports `<60s round-trip` failures with no `FORCE_SIGNAL:` log line, the RUNBOOK should suggest:
1. Verify `TRADING_MODE=PAPER` in the trading-engine env (not LIVE).
2. Verify the route registers — `curl http://localhost:8005/openapi.json | jq '.paths | keys[]' | grep force-signal`.
3. Verify trading-engine was rebuilt after merging this plan (in-memory module cache).

## Self-Check: PASSED

- File `services/trading-engine/app/handlers/orchestration.py` exists, contains `admin_force_signal_router` (line 839), `force_signal` POST handler (line 845), `trading_mode == "LIVE"` 403 gate (line 859), `FORCE_SIGNAL: strategy_id=` log line (line 896). FOUND.
- File `services/trading-engine/app/main.py` exists, contains `admin_force_signal_router` import (line 134) and `app.include_router(admin_force_signal_router)` mount (line 418). FOUND.
- File `services/trading-engine/tests/test_force_signal.py` exists, contains 4 `def test_force_signal_*` test functions, 231 lines. FOUND.
- Commits exist: `c1ba3ab` (orchestration.py changes — absorbed), `2589dcd` (test file — absorbed), `9c844fc` (main.py mount — owned by this plan). All three FOUND in `git log`.
- 4 tests PASS via `pytest tests/test_force_signal.py -v` (149.97s, includes coverage). FOUND.
- Route mount verified at app level: `python3 -c "from app.main import app; assert '/api/v1/admin/force-signal' in [r.path for r in app.routes]"` exits 0 with `Total routes: 141`. FOUND.
