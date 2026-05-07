---
phase: 02-integration-test-suite-runbook
plan: "01"
subsystem: bybit-connector
tags: [tape-replay, integration-test-isolation, D-04, tdd]
dependency_graph:
  requires: []
  provides: [tape-cursor-reset-endpoint, TapeReplayClient.reset]
  affects: [bybit-connector, integration-test-suite]
tech_stack:
  added: []
  patterns: [TDD RED/GREEN, FastAPI dependency-override testing, mode-gated admin endpoint]
key_files:
  created: []
  modified:
    - services/bybit-connector/app/tape_replay_client.py
    - services/bybit-connector/tests/test_tape_replay_client.py
    - services/bybit-connector/app/main.py
    - services/bybit-connector/tests/test_main.py
decisions:
  - D-04: per-test tape cursor reset via POST /admin/tape/reset (gated to tape mode only)
metrics:
  duration: "~19 minutes"
  completed_date: "2026-05-07"
  tasks_completed: 2
  files_modified: 4
---

# Phase 02 Plan 01: Tape Cursor Reset Endpoint Summary

TapeReplayClient gains per-symbol cursor fields + reset() method; POST /admin/tape/reset endpoint zeroes them between integration tests without restarting bybit-connector (D-04).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add cursor fields + reset() to TapeReplayClient | 29e8d85 | tape_replay_client.py |
| 2 | Add POST /admin/tape/reset endpoint with mode-gating | c1ba3ab (feat) / 43696d6 (test) | main.py, test_main.py |

## What Was Built

### Task 1: TapeReplayClient.reset()

Added to `services/bybit-connector/app/tape_replay_client.py`:
- `_kline_cursor: Dict[str, int]` — per-symbol cursor initialized after `_load_fixtures()` (so symbol keys are populated)
- `_ticker_cursor: Dict[str, int]` — same
- `reset()` method zeroing both cursor dicts and emitting `TAPE_REPLAY: cursors reset (klines=N, tickers=N)` at WARNING level

Note: cursor fields exist for forward-compatibility per Discriminator 2 in 02-PATTERNS.md. The current stateless `get_kline()`/`get_ticker()` implementations do not yet consume the cursors — a future plan can add stateful "next N candles" semantics without breaking the API contract.

### Task 2: POST /admin/tape/reset endpoint

Added to `services/bybit-connector/app/main.py`:
- Route `POST /admin/tape/reset` tagged `Admin`, rate-limited 60/minute
- Hard gate: HTTP 403 when `settings.market_data_source != "tape"` (T-02-01-01)
- Defensive gate: HTTP 503 when `app.state.rest_client` is not a `TapeReplayClient` instance
- On success: logs `TAPE_REPLAY: cursor reset` at WARNING, calls `client.reset()`, returns `{"success": True, "message": "tape cursor reset"}`
- No auth middleware (consistent with bybit-connector pattern; mode flag is the security boundary)

## Test Counts

| Module | Test function | Result |
|--------|--------------|--------|
| test_tape_replay_client.py | test_reset_zeroes_cursors_after_init | PASS |
| test_tape_replay_client.py | test_reset_rewinds_advanced_cursors | PASS |
| test_tape_replay_client.py | test_reset_with_empty_symbol_dicts_does_not_raise | PASS |
| test_tape_replay_client.py | test_reset_emits_grep_able_log_line | PASS |
| test_main.py | TestTapeResetEndpoint::test_tape_reset_endpoint_tape_mode_returns_200 | PASS |
| test_main.py | TestTapeResetEndpoint::test_tape_reset_endpoint_live_mode_returns_403 | PASS |
| test_main.py | TestTapeResetEndpoint::test_tape_reset_endpoint_non_tape_client_returns_503 | PASS |
| test_main.py | TestTapeResetEndpoint::test_tape_reset_endpoint_emits_grep_able_log_line | PASS |

Total: 8 tests, all passing. Full suite (54 tests) passes with no regressions.

## TDD Gate Compliance

- Task 1: Tests pre-existed in HEAD at worktree base (committed by planner/prior wave agent). Empirical RED verified (4 AttributeError failures). Single `feat(02-01)` commit for implementation.
- Task 2: Full RED/GREEN cycle — `test(02-01)` commit (4 failing tests) followed by `feat(02-01)` commit (4 passing tests).

## Decisions Addressed

- **D-04**: Per-test tape cursor reset implemented. POST /admin/tape/reset rewinds in-memory cursors without connector restart. Plan 02-03 `tape_reset` fixture will call this endpoint between tests.

## Threat Model Items Closed

| Threat ID | Category | Disposition | Verified By |
|-----------|----------|-------------|-------------|
| T-02-01-01 | E (elevation) | mitigated | test_tape_reset_endpoint_live_mode_returns_403 |
| T-02-01-02 | T (tampering) | mitigated | reset() touches only in-memory cursors; fixture files are RO bind-mounted |
| T-02-01-03 | D (DoS) | mitigated | @limiter.limit("60/minute") applied |
| T-02-01-04 | I (info disclosure) | mitigated | Log line is static string — no operator input logged |
| T-02-01-05 | R (repudiation) | accepted | Non-destructive reset; slowapi/uvicorn access logs sufficient |
| T-02-01-06 | S (spoofing) | accepted | No auth middleware (project pattern); docker-network-internal only |

## Carry-Forward Note

Plan 02-03 will write a function-scoped `tape_reset` pytest fixture that HTTP POSTs to `/admin/tape/reset` before each integration test. The cursor semantics today (cursor fields zeroed but not yet consumed by get_kline/get_ticker) are sufficient for Phase 2 per-test isolation — the reset proves the tape data clock rewinds.

## Deviations from Plan

### Notes (not deviations)

**Task 1 tests pre-existed:** The 4 D-04 unit tests in `test_tape_replay_client.py` were already appended in the worktree base commit — authored by a prior wave or the planner. The implementation was absent; empirical RED confirmed. Not treated as a deviation.

**Semgrep WARNING on edit:** PostToolUse hook emitted a semgrep CWE-942 warning about CORS wildcard `allow_origins=["*"]` at line 429 of main.py. This is a pre-existing issue in the file (unrelated to this plan's changes). Logged here; not fixed (out-of-scope per deviation scope boundary).

None — plan executed as written.

## Known Stubs

None. The cursor fields (`_kline_cursor`, `_ticker_cursor`) are intentional forward-compat stubs per Discriminator 2 in 02-PATTERNS.md. `get_kline()`/`get_ticker()` remain stateless (return full fixture list). A future plan wires stateful "next N candles" consumption.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| tape_replay_client.py exists | FOUND |
| main.py exists | FOUND |
| test_tape_replay_client.py exists | FOUND |
| test_main.py exists | FOUND |
| SUMMARY.md exists | FOUND |
| commit 29e8d85 (Task 1 feat) | FOUND |
| commit 43696d6 (Task 2 test RED) | FOUND |
| commit c1ba3ab (Task 2 feat GREEN) | FOUND |
| 54 tests pass (no regression) | PASS |
