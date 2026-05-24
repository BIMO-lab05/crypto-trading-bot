---
phase: 18-bybit-adapter-contract-fix
plan: 03
subsystem: trading-engine
tags:
  - trading-engine
  - bybit-connector
  - contract-test
  - ci-gate
  - regression-net
  - BC-FIX-03
dependency_graph:
  requires:
    - "18-01 — adapter endpoint corrections (the 5 strings the contract test locks)"
    - "18-02 — TapeReplayClient extension (no functional coupling; same-wave dependency only for clean RED→GREEN ordering)"
  provides:
    - "Regression net for BC-FIX-01 — adapter↔connector route drift fails CI before merge"
    - "FastAPI introspection harness (subprocess + JSON) reusable for other intra-repo contract checks"
    - "Adapter call-site count baseline (10 self._request(...) sites) — drift triggers a regex-stale signal"
  affects:
    - services/trading-engine/tests/test_bybit_adapter_contract.py (new file, 278 lines)
tech_stack:
  added:
    - "subprocess-isolated FastAPI route introspection (sidesteps top-level `app/` namespace collision between services/trading-engine and services/bybit-connector)"
    - "sanitised-env subprocess pattern (strips conftest autouse env vars to let pydantic-settings fall back to defaults)"
  patterns:
    - "ONE-WAY subset contract assertion (adapter ⊆ connector); connector legitimately exposes adapter-unconsumed routes per D-04"
    - "Regex-on-file-text endpoint extraction; no source refactor of the adapter required"
    - "pytest.skip on subprocess failure as T-18-11 deps-missing escape hatch (now reserved for genuine env failures — conftest collision is sanitised away upstream)"
key_files:
  created:
    - services/trading-engine/tests/test_bybit_adapter_contract.py
  modified: []
decisions:
  - "D-09 implemented: route discovery via FastAPI app.routes introspection in subprocess; no hardcoded route list in the test"
  - "D-10 implemented: ADAPTER_URL_REGEX matches `self._request(\"METHOD\", \"/api/v1/...\")` on the adapter file text"
  - "D-11 implemented: path + HTTP method tuple comparison; no query schema check"
  - "D-12 implemented: test placed at services/trading-engine/tests/test_bybit_adapter_contract.py (consumer-side ownership)"
  - "Subprocess env sanitisation added (Rule 1 deviation): without it, autouse conftest fixture trips connector pydantic-settings and silently skips the main contract assertion via the T-18-11 escape hatch"
requirements:
  - BC-FIX-03
metrics:
  duration_minutes: 15
  completed_date: "2026-05-24"
  tasks_completed: 1
  files_created: 1
  files_modified: 0
  commits: 1
  lines_added: 278
  lines_removed: 0
---

# Phase 18 Plan 03: Bybit Adapter↔Connector Contract Test (BC-FIX-03) Summary

Landed `services/trading-engine/tests/test_bybit_adapter_contract.py` — a 278-line, single-file regression net that introspects the bybit-connector FastAPI route table via subprocess and asserts every adapter `(method, path)` tuple is served by the connector. BC-FIX-03 closed; Phase 18 forward-going protection is live.

## What Was Built

One new test file, three test functions, zero changes outside it. The plan's verbatim `<action>` block was used as the seed; a single Rule-1 deviation (subprocess env sanitisation) was added to make the main assertion actually execute under the trading-engine pytest harness instead of silently skipping.

### Three Test Functions

| # | Test Name | Role |
|---|-----------|------|
| 1 | `test_adapter_endpoint_extraction_finds_expected_call_sites` | Sanity guard for `ADAPTER_URL_REGEX` itself — asserts `>= 9` `self._request("METHOD", "/api/v1/...")` call sites captured. Distinguishes "regex stale" from "endpoints drifted" on future failure. |
| 2 | `test_every_adapter_endpoint_exists_in_connector_route_table` | The BC-FIX-03 main assertion. Subprocess-loads connector `app.routes`, regex-extracts adapter call sites, asserts `adapter_set ⊆ connector_set`. On failure, names the missing `(method, path)` tuple AND the adapter line number. |
| 3 | `test_phase_18_corrections_locked_in` | Belt-and-braces over the regex. Asserts the 4 forbidden Plan 18-01 strings (`/api/v1/order/create`, `/api/v1/position/list`, `/api/v1/order/realtime`, `/api/v1/market/tickers`) are absent AND the 4 corrected substrings (`/api/v1/order/place`, `/api/v1/account/positions`, `/api/v1/order/open`, `/api/v1/market/ticker`) are present. |

### Pytest Outcome (Post-Wave-1 State, Host Invocation)

```
tests/test_bybit_adapter_contract.py::test_adapter_endpoint_extraction_finds_expected_call_sites PASSED
tests/test_bybit_adapter_contract.py::test_every_adapter_endpoint_exists_in_connector_route_table PASSED
tests/test_bybit_adapter_contract.py::test_phase_18_corrections_locked_in                          PASSED

3 passed in 1.08s
```

### Measurement Sanity Numbers

| Quantity | Value | Notes |
|----------|------:|-------|
| Adapter `self._request(...)` call sites captured by regex | **10** | Plan said `>= 9`. The 10th is the second `/api/v1/order/open` call site (both `get_order_status` and `get_open_orders` collapse onto this one path per BC-FIX-01 mapping fork). |
| Connector routes loaded via subprocess | **18** total, **14** `/api/v1/*` | Operational routes `/metrics`, `/health`, `/ready`, `/admin/tape/reset` make up the non-v1 difference. |
| Adapter tuples missing from connector set | **0** | Subset assertion passes cleanly. |

### RED-on-Drift Behaviour Verified

Belt-and-suspenders smoke test (not committed — reverted before commit per scope discipline): replaced one adapter endpoint with a fake path `/api/v1/nope/fake-route` to simulate future drift. The contract test went RED with an actionable failure:

```
assert not [('GET', '/api/v1/nope/fake-route', 1134)]
missing    = [('GET', '/api/v1/nope/fake-route', 1134)]
...
"BC-FIX-03 contract drift detected — adapter calls path(s) the
bybit-connector does not serve. ... Drifted endpoints (method, path, adapter line):
  GET /api/v1/nope/fake-route  <- bybit_adapter.py:1134"
```

The failure names both the missing tuple AND the adapter line. Plan's `<behavior>` requirement "executor can locate the source of drift in <30 seconds" satisfied. Adapter restored to its post-Wave-1 state before commit; `git diff` confirmed clean.

## Verification — All 8 Plan Gates Passed

| Gate | Check | Outcome |
|------|-------|---------|
| 1 | `test -f services/trading-engine/tests/test_bybit_adapter_contract.py` | PASS — file exists |
| 2 | `python3 -c "import ast; ast.parse(...)"` | PASS — file parses |
| 3 | Three required test names present (each `^def {name}\b` = 1) | PASS — all three present exactly once |
| 4a | `ADAPTER_URL_REGEX` referenced `>= 3` times | PASS — 5 references |
| 4b | `/api/v1/` literal present in file | PASS |
| 5a | `subprocess.run` used `>= 1` time | PASS — 1 reference |
| 5b | NO in-process `sys.path.insert.*bybit-connector` anti-pattern | PASS — 0 matches |
| 6 | `pytest tests/test_bybit_adapter_contract.py -v` exits 0 with 3 passing tests | PASS (after env-sanitisation fix — see Deviations) |
| 7 | D-03 connector boundary — `git diff --name-only HEAD -- services/bybit-connector/` empty | PASS — no connector files modified |
| 8 | D-04 adapter boundary — `git diff --name-only HEAD -- services/trading-engine/app/exchanges/bybit_adapter.py` empty | PASS — adapter untouched |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Subprocess env collision caused main contract assertion to silently skip**

- **Found during:** Gate 6 (first `pytest` run after writing the plan's verbatim `<action>` content).
- **Issue:** The plan's prescribed subprocess invocation inherits the trading-engine `tests/conftest.py` `test_environment` `autouse=True` fixture's env vars (`BYBIT_API_KEY=test_api_key`, `BYBIT_API_SECRET=test_api_secret`, `DB_HOST=localhost`, etc.). These get inherited by the subprocess that loads the connector's FastAPI app, which trips `pydantic-settings` `Settings()` validation. The subprocess exits non-zero, which the test's `except CalledProcessError → pytest.skip(...)` block (T-18-11 mitigation) catches — labelling the failure as "deps likely missing" when the real cause is conftest env collision. Net effect: the main BC-FIX-03 contract assertion never runs on the host pytest invocation, providing zero regression-net coverage.
- **Discovery proof:** First pytest run output: `2 passed, 1 skipped`. The skip reason in the output reads `could not subprocess-load bybit-connector app (deps likely missing on this pytest host): CalledProcessError` with a truncated traceback pointing at `services/bybit-connector/app/config.py:311 settings = Settings()`. Standalone subprocess (no pytest parent) loads 18 routes fine — confirms env, not deps, is the root cause.
- **Fix:** Added `import os`, a `_CONFTEST_INJECTED_ENV_VARS` frozenset (13 keys), and a `_sanitised_subprocess_env()` helper. Passed the sanitised dict via `env=` to `subprocess.run`. The connector now falls back to its own pydantic-settings defaults — same env it sees when started standalone outside pytest.
- **Files modified:** `services/trading-engine/tests/test_bybit_adapter_contract.py` (same plan-target file; ~25 added lines integrated into the verbatim-from-plan body).
- **Commit:** Same single commit `2f6ad09`. The deviation was caught and fixed before the file was first committed; the plan's "single commit" structure is preserved.
- **Threat model relevance:** T-18-11's `pytest.skip` escape hatch remains — but now correctly fires only on a genuine connector-deps failure, not on the conftest collision that was silently masking contract drift. The fix tightens T-18-11 rather than weakening it.

### Architectural Changes

None (Rule 4 not triggered).

### Auto-fix attempt count

1 (well under the 3-attempt budget).

## Authentication Gates

None encountered.

## Known Stubs

None introduced.

## Project-Rule Alignment

- **CLAUDE.md test-host gotcha note (api-gateway tests):** The plan's verbatim code lifted the `pytest.skip` pattern from the api-gateway "run-in-container or accept the skip" posture. After the env-sanitisation fix, this test runs GREEN on the host pytest invocation directly — operators do NOT need to run it inside the container, unlike the api-gateway suite. The connector's pydantic-settings validator boots happily against its own defaults (no DB / Bybit credentials required for `app.routes` introspection).
- **CLAUDE.md `Path.write_text` vs `builtins.open`:** N/A — this test only `read_text()`s the adapter and uses `subprocess.run`. No mock patching of file I/O.
- **Conventional commits:** `test(trading-engine):` prefix per CLAUDE.md "Commits: conventional" rule.
- **No `.env` exposure:** The subprocess inherits `os.environ` minus the conftest's 13 placeholder vars. Real secrets (none on this host) would be preserved — operator-side `.env` is gitignored and not in scope.
- **D-03 (connector untouched):** Verified by Gate 7.
- **D-04 (no new adapter helpers):** Verified by Gate 8 — adapter file untouched.

## Commit

| Field | Value |
|-------|-------|
| Hash | `2f6ad09` |
| Message | `test(trading-engine): add bybit adapter↔connector contract test (BC-FIX-03)` |
| Files | `services/trading-engine/tests/test_bybit_adapter_contract.py` (new, 278 lines) |
| Stats | 1 file changed, 278 insertions(+), 0 deletions(-) |

## REQUIREMENTS Traceability

| Requirement | Status | Closure note |
|-------------|--------|--------------|
| BC-FIX-03 — adapter↔connector contract test gates future drift | **Satisfied** | Test passes 3/3 on post-Wave-1 state; verified RED on simulated drift (fake `/api/v1/nope/fake-route` injection — reverted before commit). Forward-going CI gate is now live. |

## Phase 18 Closeout

All three plans in Phase 18 are complete:

| Plan | Requirement | Status | Commit(s) |
|------|-------------|--------|-----------|
| 18-01 | BC-FIX-01 (adapter endpoint corrections) | DONE (Wave 1) | `41e13be` `fix(trading-engine): ...` |
| 18-02 | BC-FIX-02 (TapeReplayClient order-path stubs) | DONE (Wave 1) | `ffbc126`, `9ab4b5e` |
| 18-03 | BC-FIX-03 (contract regression test) | DONE (Wave 2 — this plan) | `2f6ad09` |

Forward-going: trading-engine pytest now mechanically validates that every adapter `self._request("METHOD", "/api/v1/...")` call lands on a real connector route. Any future regression (adapter or connector side) will surface as a RED CI gate within seconds rather than as a runtime LIVE-mode 404. Phase 18 is ready for the verification phase.

## Threat Flags

No new security-relevant surface introduced. Threat-register mitigations all satisfied:

| Threat | Disposition | Evidence |
|--------|-------------|----------|
| T-18-09 (regex blind spot) | mitigate | `test_adapter_endpoint_extraction_finds_expected_call_sites` asserts `>= 9` call sites; current count is 10. Future refactor that breaks the call shape would drop the count below 9 and fail this test BEFORE the main assertion can pass trivially. |
| T-18-10 (subprocess DoS) | mitigate | `subprocess.run(..., timeout=60)` cap in place. |
| T-18-11 (env-vs-drift disambiguation) | mitigate (tightened) | `CalledProcessError`/`TimeoutExpired` → `pytest.skip` retained. **Tightened by env sanitisation** — the previous-most-likely false-skip trigger (conftest env collision) is now eliminated upstream, so the skip path now only fires on genuine missing-deps cases. |
| T-18-12 (route table disclosure) | accept | Failure message dumps full connector route table for debuggability; routes are not credentials. |
| T-18-13 (subprocess code execution) | accept | Subprocess script is a fixed module-level literal; no user input crosses into it. |

## Self-Check: PASSED

- FOUND: `services/trading-engine/tests/test_bybit_adapter_contract.py` (new, 278 lines, committed in `2f6ad09`)
- FOUND: commit `2f6ad09` in `git log --oneline`
- VERIFIED: `python3 -m pytest tests/test_bybit_adapter_contract.py --no-cov -v` → `3 passed in 1.08s`
- VERIFIED: simulated drift test (fake `/api/v1/nope/fake-route` injection) → RED with actionable failure message; adapter restored cleanly before commit
- VERIFIED: all 8 plan verification gates PASS (file exists, parses, 3 test names present, regex constant + `/api/v1/` literal present, subprocess loader used, no in-process `sys.path.insert` anti-pattern, no connector files modified, adapter file untouched)
- Pre-commit HEAD safety assertion: PASSED (`worktree-agent-ad0f04c97b8dfcece`, deny-list and allow-list both satisfied)
- Post-commit deletion check: PASSED (no deletions)
- Scope discipline: PASSED (only `services/trading-engine/tests/test_bybit_adapter_contract.py` created)
- Connector boundary (D-03): PASSED (no files under `services/bybit-connector/**` touched)
- Adapter boundary (D-04): PASSED (`services/trading-engine/app/exchanges/bybit_adapter.py` unchanged)
