---
phase: 02-integration-test-suite-runbook
plan: 03
subsystem: testing
tags: [pytest, integration-fixtures, conftest, bootstrap, asyncpg, httpx]

requires:
  - phase: 02-integration-test-suite-runbook
    provides: |
      02-01 POST /admin/tape/reset endpoint (used by tape_reset fixture)
      02-02 POST /api/v1/admin/force-signal endpoint (used by force_signal fixture)
provides:
  - Session-scoped bootstrap_stack fixture invoking ./bootstrap.sh in tmp clone
  - Session-scoped tmp_fresh_clone fixture (D-05) — git clone file://, delete on success only (D-08)
  - Function-scoped tape_reset fixture (D-04) — POSTs to bybit-connector
  - Function-scoped force_signal helper (CD-04) — async callable for trading-engine
  - Function-scoped db_truncate — TRUNCATE klines/tickers/positions/orders RESTART IDENTITY CASCADE
  - Function-scoped notification_received — mode-aware (record tail of tests/.notifications.log, live polls Telegram getUpdates)
  - Port-mapping bug fix (bybit_connector=8001, trading_engine=8005)
  - wait_for_services refactored from function- to session-scoped (D-03)
affects: [02-04, 02-05]

tech-stack:
  added: [asyncpg]
  patterns: [session-scoped-bootstrap, mode-aware-fixture, anti-mock-pathlib-IO]

key-files:
  created: []
  modified:
    - tests/integration/conftest.py

key-decisions:
  - "Empty .env at bootstrap entry per D-06 — validates Phase 1 D-17 tape-mode credential bypass"
  - "git clone file://<repo> per D-05 over rsync — preserves history, simpler"
  - "db_truncate uses RESTART IDENTITY CASCADE — schema preserved between tests"
  - "notification_received returns single async callable — test bodies are mode-agnostic"
  - "pathlib.Path for log I/O per project memory (mock.patch on builtins.open misses Path.write_text/read_text)"

patterns-established:
  - "Session-scoped stack bootstrap once, function-scoped per-test reset (D-03 + D-04)"
  - "Anti-mock fixture authoring — return real async callables, not MagicMock"
  - "Mode-aware test fixtures — branch on env var (record/live), unified return contract"

requirements-completed: [INFRA-01]

duration: ~25min (3 agent dispatches; final task committed inline by orchestrator)
completed: 2026-05-07
---

# Phase 02 Plan 03: conftest.py wiring Summary

**Phase 2 integration fixture suite — session-scoped bootstrap + 4 function-scoped fixtures (tape_reset, force_signal, db_truncate, notification_received) wired to 02-01/02-02 endpoints**

## Performance

- **Duration:** ~25 min wall clock (3 agent dispatches consumed; 2 stopped mid-flight on tool_uses cap, 1 inline finish)
- **Completed:** 2026-05-07T22:48:02Z
- **Tasks:** 3
- **Files modified:** 1

## Accomplishments
- Pre-existing port-mapping bug fixed (bybit_connector and trading_engine inversion in lines 27/30 — pattern-mapper Warning #1 from plan)
- wait_for_services refactored to session scope per D-03 (one stack boot, ~2-min cost shared across suite)
- bootstrap_stack + tmp_fresh_clone session fixtures shell out to ./bootstrap.sh in /tmp/cb-test-<sha>, capture last-50 log lines on failure, delete on success only per D-08
- tape_reset fixture HTTPs to 02-01's /admin/tape/reset between tests (D-04)
- force_signal helper fixture exposes async callable for 02-02's /api/v1/admin/force-signal (CD-04)
- db_truncate clears mutable rows in klines/tickers/positions/orders between tests
- notification_received is mode-aware: record mode tails tests/.notifications.log (default, local); live mode polls api.telegram.org getUpdates (CI). Single `async def _wait_for(text, timeout) -> bool` shape.

## Task Commits

1. **Task 1: Fix port mapping + refactor to session-scoped fixtures** — `3f21770` (fix)
2. **Task 2: Add bootstrap_stack + tmp_fresh_clone session fixtures** — `e9fe1e6` (feat)
3. **Task 3: Add tape_reset, force_signal, db_truncate, notification_received fixtures** — `cf24441` (feat)

**Plan metadata:** this commit (docs)

## Files Created/Modified
- `tests/integration/conftest.py` — +149 lines net across 3 commits. New session fixtures (bootstrap_stack, tmp_fresh_clone), 4 new function fixtures, port mapping fix.

## Decisions Made
- **db_truncate defaults corrected from plan:** plan specified user=postgres / db=crypto_trading / db=timescale, but docker-compose.unified.yml uses user=cryptobot / pg_db=cryptobot / ts_db=market_data / ts_host_port=5433. Defaults aligned to compose reality. Operator may override via POSTGRES_URL / TIMESCALE_URL env vars. Marked as Rule 1 fix.
- **notification_received returns async callable, not awaiting fixture value:** tests `await notification_received("substring")` — single shape across record/live modes.
- **pathlib.Path for log I/O** — bypasses mock.patch on builtins.open per project memory feedback_pathlib_mocking.md.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Default Mismatch] db_truncate Postgres/Timescale connection defaults**
- **Found during:** Task 3 (db_truncate fixture)
- **Issue:** Plan defaults referenced postgres:postgres@.../crypto_trading and .../timescale, but docker-compose.unified.yml uses cryptobot user, cryptobot pg db, market_data ts db, port 5433.
- **Fix:** Defaults aligned to compose. Env-var overrides preserved.
- **Files modified:** tests/integration/conftest.py
- **Verification:** `grep -n cryptobot tests/integration/conftest.py` matches compose user; `grep -n 5433 tests/integration/conftest.py` matches ts_host_port.
- **Committed in:** `cf24441` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 default mismatch).

## Issues Encountered

- **3 agent dispatches needed.** First two agents stopped mid-flight on tool_uses caps (`a74591091dfd6fd92` after Task 1 only; `a3c40e0a0b5e19033` after Task 2 with Task 3 written but uncommitted). Orchestrator committed Task 3 + this SUMMARY inline to close out.
- **No worktree isolation.** `.git` is a directory not a file in agent worktrees, so concurrent agents share index — same Wave-1 race. Single-plan Wave 2 sidesteps the cross-plan symptom; index race not observed here.

## Self-Check: PASSED

- [x] Port mapping fixed (bybit_connector=8001, trading_engine=8005)
- [x] bootstrap_stack + tmp_fresh_clone defined, session-scoped
- [x] tape_reset hits :8001/admin/tape/reset
- [x] force_signal hits :8005/api/v1/admin/force-signal
- [x] db_truncate runs RESTART IDENTITY CASCADE on klines/tickers/positions/orders
- [x] notification_received exposes single mode-agnostic async callable
- [x] All 3 task commits present
- [x] No modifications to STATE.md / ROADMAP.md by executor
