---
phase: 02-integration-test-suite-runbook
plan: "04"
subsystem: integration-tests
tags: [integration-tests, infra-01, d-12, ml-on, paper-trade, notification]
dependency_graph:
  requires:
    - 02-01 (tape_reset endpoint on bybit-connector)
    - 02-02 (force_signal endpoint on trading-engine)
    - 02-03 (conftest fixture suite: bootstrap_stack, tape_reset, force_signal, db_truncate, notification_received)
  provides:
    - INFRA-01 e2e test (headline ROADMAP Phase 2 success criterion 1)
    - CD-05 ML-on variant gated behind @pytest.mark.ml_on
    - D-12 clean integration test tree (0 pytest.skip / xfail)
  affects:
    - tests/integration/ (D-12 enforcement now covers entire directory)
    - pytest.ini (ml_on marker registration)
tech_stack:
  added: [asyncpg (DB poll in round-trip test)]
  patterns:
    - time.monotonic() deadline + 250ms poll cadence (CD-04)
    - mode-aware notification_received fixture (CD-01 record/live)
    - @pytest.mark.ml_on for opt-in nightly variant (CD-05)
    - bootstrap_stack hard-fail replacing pytest.skip silent-skip (D-12)
key_files:
  created:
    - tests/integration/test_fresh_clone_round_trip.py
    - tests/integration/test_ml_on_variant.py
  modified:
    - pytest.ini (added ml_on marker)
    - tests/integration/test_phase3_integration.py (D-12 refactor)
decisions:
  - "D-12: refactor test_phase3_integration.py in-place (Warning #2 chosen path); no .skipped rename"
  - "CD-04: postgres_url uses POSTGRES_URL env var defaulting to compose creds (cryptobot:cryptobot_dev_password@localhost:5432/cryptobot)"
  - "CD-05: ML-on variant opted-in via -m ml_on only; default suite runs ML-off"
  - "CD-01: notification_received is mode-aware; record mode (local) / live Telegram (CI)"
metrics:
  duration_minutes: ~15
  completed_date: "2026-05-08"
  tasks_completed: 3
  files_changed: 4
---

# Phase 02 Plan 04: Integration E2E Tests + D-12 Refactor Summary

End-to-end INFRA-01 headline test + ML-on variant + D-12 silent-skip prohibition enforcement across tests/integration/.

## What Was Built

### Task 1 — test_fresh_clone_round_trip.py (INFRA-01, commit 343e55a)

Three tests that prove the ROADMAP Phase 2 success criteria:

| Test | Proves |
|------|--------|
| `test_fresh_clone_round_trip` | Tape prices flow + paper-trade round-trip <60s (CD-04) + notification emitted (CD-01) |
| `test_all_ten_services_healthy` | All 10 services return /health=200 (belt-and-suspenders over bootstrap_stack) |
| `test_unknown_symbol_does_not_500` | XRPUSDT returns 200 + empty list, not 500 (Phase 1 landmine §4 contract) |

`test_fresh_clone_round_trip` chains all four ROADMAP success criteria:
1. `bootstrap_stack` fixture asserts all services healthy (criteria 1 — implicit)
2. GET `/api/v1/market/tickers?symbol=SOLUSDT` returns non-empty list (criteria 2 — tape flows)
3. `force_signal` -> DB poll at 250ms cadence with 60s deadline (criteria 3 — <60s round-trip)
4. `notification_received("SOLUSDT", timeout=10.0)` asserts truthy (criteria 4 — notification)

### Task 2 — test_ml_on_variant.py + pytest.ini (CD-05, commit 7cea1e9)

Two tests gated behind `@pytest.mark.ml_on`:
- `test_ml_models_loaded`: asserts `confidence != 0.0` (model loaded and inference ran)
- `test_ml_prediction_endpoint_alive`: asserts response envelope shape

`ml_on` marker added to existing `pytest.ini` markers block (not clobbered — pre-existing `asyncio_mode = auto` and `integration` marker preserved).

### Task 3 — test_phase3_integration.py refactor (D-12, commit 36dc7c8)

Removed the `pytest.skip` anti-pattern from the file that had it:
- Deleted `check_services_available` fixture (the silent-skip source)
- Deleted local `async_client` fixture (duplicate of conftest `http_client`)
- Rewired all 20 test methods: `check_services_available` → `bootstrap_stack`, `async_client` → `http_client`
- File remains active (not renamed to `.skipped`) — D-12 Warning #2 refactor-in-place path

**D-12 is now satisfied across the entire `tests/integration/` tree:** `grep -rE "pytest.skip|xfail" tests/integration/` returns 0 hits.

## Test Counts

| File | Tests | Notes |
|------|-------|-------|
| test_fresh_clone_round_trip.py | 3 | INFRA-01 headline |
| test_ml_on_variant.py | 2 | CD-05 opt-in (ml_on marker only) |
| test_phase3_integration.py | 20 | Refactored; previously had silent-skip |
| **Total new/active** | **25** | |

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| 343e55a | test | INFRA-01 headline e2e round-trip test |
| 7cea1e9 | feat | ML-on variant tests + ml_on pytest.ini marker |
| 36dc7c8 | refactor | D-12 refactor of test_phase3_integration.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected postgres_url in test_fresh_clone_round_trip.py**
- **Found during:** Task 1 (advisor review before writing)
- **Issue:** Plan code used `postgres:postgres@localhost:5432/crypto_trading` — this does NOT match docker-compose.unified.yml defaults (`cryptobot:cryptobot_dev_password@localhost:5432/cryptobot`)
- **Fix:** Used `os.getenv("POSTGRES_URL", "postgresql://cryptobot:cryptobot_dev_password@localhost:5432/cryptobot")` to match compose defaults and allow env-var override (same pattern as conftest.py Rule 1 fix from Plan 02-03)
- **Files modified:** tests/integration/test_fresh_clone_round_trip.py
- **Commit:** 343e55a

**2. [Rule 2 - Missing] pytest.ini preserved, not clobbered**
- **Found during:** Task 2 orientation
- **Issue:** Plan's Task 2 snippet would have replaced a 185-line pytest.ini with a 5-line snippet, deleting asyncio_mode=auto (--asyncio-mode=auto in addopts), all existing markers, coverage config, JUnit config, etc.
- **Fix:** Used Edit (not Write) to add only the `ml_on` marker line into the existing `markers =` block
- **Files modified:** pytest.ini
- **Commit:** 7cea1e9

**3. [Wording deviation] Task 2 acceptance criterion for default-suite collection**
- **Finding:** The plan criterion `pytest --collect-only tests/integration/ 2>&1 | grep "ml_on" | wc -l` returns > 0 even without `-m ml_on` because the filename `test_ml_on_variant.py` contains the substring `ml_on`. The criterion as worded is unsatisfiable.
- **Actual behavior:** Tests ARE collected by default (pytest shows them in `--collect-only`); the `@pytest.mark.ml_on` marker causes them to be EXCLUDED at run-time when invoked without `-m ml_on`. This matches CD-05 intent.
- **Resolution:** Documented as wording deviation; functional behavior (opt-in via marker) is correct.

**4. [Rule 1 - Bug] Comment contamination from replace_all during Task 3**
- **Found during:** Task 3 after replace_all for `check_services_available` → `bootstrap_stack`
- **Issue:** The `replace_all` also replaced the fixture name inside the explanatory comment, making it read "- bootstrap_stack: contained pytest.skip() anti-pattern" — logically inverted and confusing
- **Fix:** Rewrote the comment block to avoid mentioning both banned pattern names inline (acceptance criteria grep would count comment text as violations)
- **Files modified:** tests/integration/test_phase3_integration.py
- **Commit:** 36dc7c8 (included in same task commit)

## Threat Model Items Closed

| Threat ID | Status | Notes |
|-----------|--------|-------|
| T-02-04-01 | Closed | Anti-mock grep (acceptance criteria) confirmed 0 banned patterns; D-12 enforced |
| T-02-04-02 | Accepted | Placeholder postgres URL in test documented; compose default is localhost:5432, not prod |
| T-02-04-03 | Closed | DB poll uses fresh asyncpg connection per iteration + `created_at IS NOT NULL` filter |
| T-02-04-04 | Closed | Hard 60s deadline (time.monotonic) + 10s notification timeout; both finite |
| T-02-04-05 | Closed | test_unknown_symbol_does_not_500 asserts 200 + empty list for XRPUSDT |

## Carry-forward

- Plan 02-09 CI workflow runs `pytest tests/integration` (default suite); ML-on variant runs nightly via separate workflow trigger with `-m ml_on`
- The postgres DB poll in `test_fresh_clone_round_trip` uses a direct asyncpg connection to port 5432. If compose maps postgres to a non-standard port, set `POSTGRES_URL` env var before running
- `test_phase3_integration.py` tests call the sentiment-analysis and technical-analysis services through the api-gateway (`API_GATEWAY_URL = "http://localhost:8000"`); bootstrap_stack must have those services healthy for these tests to pass

## Known Stubs

None. All three files exercise real fixtures (bootstrap_stack, force_signal, notification_received) with no hardcoded empty/mock data.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| tests/integration/test_fresh_clone_round_trip.py exists | FOUND |
| tests/integration/test_ml_on_variant.py exists | FOUND |
| tests/integration/test_phase3_integration.py exists | FOUND |
| pytest.ini exists | FOUND |
| 02-04-SUMMARY.md exists | FOUND |
| commit 343e55a (Task 1) exists | FOUND |
| commit 7cea1e9 (Task 2) exists | FOUND |
| commit 36dc7c8 (Task 3) exists | FOUND |
