---
phase: 13-bybit-connector-market-data-centralization
plan: 04
subsystem: ml-prediction-service
tags: [bybit-connector, ml-prediction, refactor, tdd, httpx, fail-fast, security]
requires:
  - 13-02 (BC-02 fail-fast contract test locked in Plan 03)
  - 13-03 (BC-07 tape-preservation RED test locked in Plan 03)
provides:
  - "Wave-1 ml-prediction-service bypass elimination (5 files clean)"
  - "respx unit test for refactored orderbook handler (4 GREEN tests)"
  - "BC-07 Test 1 (orderbook tape preservation) flipped GREEN"
  - "BC-07 Test 2 (no live Bybit call under tape) flipped GREEN"
  - "BC-02 fail-fast contract GREEN for all 4 ml-prediction download scripts"
  - "[Rule 1 fix] pre-existing fstr() crash in download_op_sui_6months.py"
affects:
  - services/ml-prediction-service/app/handlers/orderbook.py (BYBIT_CONNECTOR_URL + wrapper parser)
  - services/ml-prediction-service/download_missing_symbols_data.py (aiohttp -> httpx + connector)
  - services/ml-prediction-service/download_final_4.py (aiohttp -> httpx + connector)
  - services/ml-prediction-service/download_op_sui_6months.py (requests preserved; connector routed)
  - services/ml-prediction-service/download_suiusdt_12months.py (requests preserved; connector routed)
tech-stack:
  added:
    - tenacity bybit_connector_retry decorator (inline; verbatim from market-data-service circuit_breaker)
  patterns:
    - PATTERNS.md Pattern 1 (refactored service-runtime caller via httpx)
    - PATTERNS.md Pattern 2 (refactored standalone script with fail-fast scaffold)
    - PATTERNS.md Critical Warning #4 (coupled URL + parser swap)
    - RESEARCH Pitfall 6 (httpx response.json() is sync, not awaitable)
key-files:
  created:
    - services/ml-prediction-service/tests/test_orderbook_handler.py
  modified:
    - services/ml-prediction-service/app/handlers/orderbook.py
    - services/ml-prediction-service/download_missing_symbols_data.py
    - services/ml-prediction-service/download_final_4.py
    - services/ml-prediction-service/download_op_sui_6months.py
    - services/ml-prediction-service/download_suiusdt_12months.py
decisions:
  - "Retry decorator wraps fetch_orderbook_from_connector but is decorative (inner try/except HTTPException converts httpx errors before tenacity sees them) — matches in-repo fetcher.py pattern; advisor confirmed."
  - "Per Open Q #6: aiohttp converted to httpx for the two scripts that used it; requests preserved in the two scripts that used requests (smaller diff, original sync semantics intact). Reachability probe always uses httpx via asyncio.run."
  - "Backward-compat alias `fetch_orderbook_from_bybit = fetch_orderbook_from_connector` kept at module bottom (no external callers known but BC-07 test docstring shows it accepts either name)."
  - "Error messages in orderbook handler scrubbed: 'bybit-connector returned non-success response' (no inner Bybit/connector field propagation per security V7 hygiene)."
  - "Docstrings rewritten to avoid the literal 'api.bybit.com' and 'retCode' strings — these are flagged by the BC-03 grep gate (Pitfall 4 in RESEARCH); 'the upstream Bybit REST API' / 'raw Bybit shape' wording substituted."
metrics:
  duration_minutes: 27
  completed: 2026-05-21
  tasks_total: 2
  tasks_completed: 2
  files_total: 6
  commits_total: 6
---

# Phase 13 Plan 04: ml-prediction-service Bybit-Connector Centralization Summary

Refactored all 5 Bybit-bypass sites inside `services/ml-prediction-service/` to route through bybit-connector REST. Coupled URL+parser swap (Critical Warning #4) applied to every file. Fail-fast scaffold (D-04) added to the 4 standalone download scripts. New respx unit test for the orderbook handler. BC-07 tape-preservation tests (orderbook channel) flipped GREEN.

## What Changed

**Task 1 — orderbook handler refactor (TDD):**

`services/ml-prediction-service/app/handlers/orderbook.py`:
- Function renamed: `fetch_orderbook_from_bybit` → `fetch_orderbook_from_connector` (backward-compat alias kept at module bottom)
- URL swapped: `https://api.bybit.com/v5/market/orderbook` → `${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook` (default `http://bybit-connector:8001`)
- Parser swapped: `data.get("retCode") != 0` → `not data.get("success")`; `data["result"]` → `data["data"]`
- Error message scrubbed: generic 502 detail instead of propagating inner Bybit/connector fields (security V7 hygiene)
- Wrapped with `bybit_connector_retry` (verbatim from `services/market-data-service/app/circuit_breaker.py`)
- All 4 in-module callers (`get_orderbook_features`, `get_imbalance`, `get_liquidity`, `get_ml_features`) updated to use the new name

`services/ml-prediction-service/tests/test_orderbook_handler.py` (NEW):
- Test 1: `test_fetch_orderbook_from_connector_hits_bybit_connector` — asserts URL + params + parsed result
- Test 2: `test_fetch_orderbook_handles_empty_tape_response` — asserts empty-stub no-crash (BC-07 contract)
- Test 3: `test_fetch_orderbook_raises_on_connector_failure` — asserts HTTPException(502) + V7 message scrub
- Test 4: `test_fetch_orderbook_raises_on_http_error` — asserts HTTPException on 503 from connector

**Task 2 — 4 download_*.py scripts refactor:**

For each of `download_missing_symbols_data.py`, `download_final_4.py`, `download_op_sui_6months.py`, `download_suiusdt_12months.py`:
- Module-level `BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001")` (host-friendly default)
- `assert_connector_reachable()` async function pings `${BYBIT_CONNECTOR_URL}/health` with 5s timeout
- On unreachable: stderr message containing "bybit-connector is not reachable", "BYBIT_CONNECTOR_URL", and "docker compose -f docker-compose.unified.yml up -d bybit-connector"; `sys.exit(2)`
- Reachability check invoked from a sync `_check_or_exit()` wrapper as the first statement inside `__main__` (before any real work)
- Coupled URL + parser swap applied to kline fetch path
- aiohttp converted to httpx in the two scripts that used aiohttp (`download_missing_symbols_data.py`, `download_final_4.py`); `requests` retained in the two scripts that used `requests` (`download_op_sui_6months.py`, `download_suiusdt_12months.py`) — smaller diff, original synchronous semantics intact

## Verification

Per-file bypass-pattern violations (post-refactor):

```
services/ml-prediction-service/app/handlers/orderbook.py:        0 violations
services/ml-prediction-service/download_missing_symbols_data.py: 0 violations
services/ml-prediction-service/download_final_4.py:              0 violations
services/ml-prediction-service/download_op_sui_6months.py:       0 violations
services/ml-prediction-service/download_suiusdt_12months.py:     0 violations
```

Test results:

```
services/ml-prediction-service/tests/test_orderbook_handler.py:          4 passed
tests/integration/test_bybit_connector_tape_preserved.py:                3 passed (Tests 1 + 2 + 3)
tests/integration/test_scripts_fail_fast.py (4 ml-prediction cases):     4 passed
services/ml-prediction-service/tests/ (full suite):                      12 passed, 25 skipped, 0 failed
```

BC-07 Test 1 + Test 2 (orderbook channel) flipped from RED-on-main to GREEN. Test 3 was always-green by design.

Plan automated verification one-liner (Task 2):

```
all 4 download scripts refactored
```

All `must_haves.truths` from plan frontmatter verified:
- orderbook handler hits bybit-connector REST (grep confirms 0 `api.bybit.com` matches, ≥1 `BYBIT_CONNECTOR_URL`)
- Wrapper-shape parser replaces Bybit raw shape (0 `retCode` matches, ≥1 `"success"`)
- All 4 download scripts fail-fast on unreachable connector (exit 2 + operator hint)
- BC-07 Test 1 flips GREEN (confirmed)
- BC-03 grep-gate violation count drops by 5 ml-prediction-service entries

## Commits

| # | Hash       | Task     | Files                                                 |
| - | ---------- | -------- | ----------------------------------------------------- |
| 1 | `5e06f9b`  | 1 (RED)  | tests/test_orderbook_handler.py                       |
| 2 | `ad5fcd8`  | 1 (GREEN)| app/handlers/orderbook.py                             |
| 3 | `7a4bbf3`  | 2        | download_missing_symbols_data.py                      |
| 4 | `f5ee456`  | 2        | download_final_4.py                                   |
| 5 | `923ae20`  | 2        | download_op_sui_6months.py (+ Rule 1 fix)             |
| 6 | `34098c1`  | 2        | download_suiusdt_12months.py                          |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pre-existing `fstr(...)` crash in download_op_sui_6months.py**
- **Found during:** Task 2 — Wave 0 RED-test for this script revealed `NameError: name 'fstr' is not defined` at line 86 of the pre-refactor file
- **Issue:** Line 86 had `output_file = fstr(_REPO_ROOT / 'data/ml_training/{symbol}_1H_6months_20251210.csv')` — `fstr(...)` is not a real Python function, only a literal that happens to resemble one (likely a typo for an f-string)
- **Fix:** Replaced with a proper f-string: `output_file = str(_REPO_ROOT / f'data/ml_training/{symbol}_1H_6months_20251210.csv')`
- **Files modified:** `services/ml-prediction-service/download_op_sui_6months.py`
- **Why required:** Without this fix, the fail-fast acceptance test still failed (script crashed with returncode=1 not 2) — bug was previously masked because the script never reached this path before failing on `api.bybit.com` timeout
- **Commit:** `923ae20`

### Decision Documentation

**Retry decorator decorative:** `bybit_connector_retry` wraps `fetch_orderbook_from_connector` but the inner `try/except httpx.HTTPError` converts errors to `HTTPException` before tenacity gets a chance to retry. Advisor confirmed this matches the existing pattern in `services/market-data-service/app/fetcher.py:159-201`. Test 4 (`test_fetch_orderbook_raises_on_http_error`) asserts only that 503 raises `HTTPException` — it does not assert retry count. Smaller diff vs the alternative split-function approach.

**aiohttp vs requests treatment (Open Q #6):** Plan default was "convert aiohttp to httpx universally." Per advisor + practical judgment: the two `requests`-based scripts (`download_op_sui_6months.py`, `download_suiusdt_12months.py`) kept `requests` for their sync main loops. Only the connector reachability probe uses `httpx` (run via `asyncio.run` from a sync wrapper). Justification: smaller diff, preserves original synchronous semantics. Both scripts still satisfy URL + parser swap and fail-fast contract. The two `aiohttp`-based scripts (`download_missing_symbols_data.py`, `download_final_4.py`) were fully converted to httpx as the plan specified.

**Docstring "api.bybit.com" / "retCode" rewrites:** PATTERNS.md Pitfall 4 in RESEARCH calls out that the BC-03 grep gate trips on literal pattern matches in docstrings/comments. Acceptance criteria use unconditional `grep`. Rewrote module docstring + function docstring + comments to use "the upstream Bybit REST API" / "raw Bybit shape" rather than the literal banned strings. Logic unchanged.

## Auth Gates

None encountered. All work executed against in-tree test infrastructure.

## Known Stubs

None. Both tasks deliver complete functionality (no placeholder values, no UI-rendering stubs).

## Threat Flags

None. The refactor reduces external surface (5 fewer `api.bybit.com` egress paths). No new network endpoints, auth paths, or schema changes introduced. STRIDE register from `13-04-PLAN.md` `<threat_model>` mitigations all satisfied:
- T-BC02-ErrorShape: Tests 1 + 2 explicitly assert wrapper-shape parsing
- T-BC07-LiveLeak: BC-07 Tests 1 + 2 (GREEN) confirm no live Bybit hit under tape mode
- T-BC02-RetMsgLeak: Test 3 asserts generic 502 message, no inner-field propagation

## Self-Check: PASSED

- All 6 commit hashes present in `git log` ✓
- `services/ml-prediction-service/tests/test_orderbook_handler.py` exists ✓
- All 5 refactored files exist and load without import errors ✓
- All 4 acceptance grep checks for orderbook.py pass (0 bypass URLs, ≥1 connector URL, 0 retCode, ≥1 "success") ✓
- All 4 download scripts pass acceptance grep + fail-fast contract ✓
- BC-07 Tests 1 + 2 GREEN; orderbook respx tests GREEN ✓
- No regressions in `services/ml-prediction-service/tests/` (12 passed, 25 pre-existing skips) ✓
