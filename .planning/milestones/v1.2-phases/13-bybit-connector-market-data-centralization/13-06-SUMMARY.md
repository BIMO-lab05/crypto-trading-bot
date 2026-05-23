---
phase: 13-bybit-connector-market-data-centralization
plan: 06
subsystem: infra
tags: [bybit-connector, scripts, backtesting, config-fix, refactor]

# Dependency graph
requires:
  - phase: 13-bybit-connector-market-data-centralization
    provides:
      - 13-02 (BC-01 audit + repo map of all bypass sites)
      - 13-03 (Wave 0 RED tests: test_scripts_fail_fast.py parametrize list, test_config_defaults.py BC-05 assertion)
provides:
  - "scripts/fetch_real_historical_data routes through bybit-connector with sync fail-fast in __main__"
  - "scripts/collect_6months_historical routes through bybit-connector with sync fail-fast in __main__"
  - "backtesting/bybit_data_fetcher routes through bybit-connector with fail-fast on BOTH __main__ AND class-level fetch_klines (gated by _reachability_checked)"
  - "scripts/test_public_bybit_api.py deleted (unused diagnostic probe)"
  - "services/market-data-service/app/config.py: bybit_connector_url default port :8002 → :8001 (BC-05)"
  - "services/market-data-service/tests/test_pagination_fix.py deleted (Open Q #4 default)"
  - "Plan 03 RED tests transitioned GREEN: 3 fail-fast cases + 1 BC-05 default-port assertion"
affects: [13-04, 13-05, 13-07, 13-08, 13-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sync + async pair for connector reachability probes (assert_connector_reachable_sync / assert_connector_reachable)"
    - "Class-level first-call reachability gate via instance _reachability_checked flag (mirrors services/market-data-service/app/fetcher.py)"

key-files:
  created: []
  modified:
    - scripts/fetch_real_historical_data.py
    - scripts/collect_6months_historical.py
    - backtesting/bybit_data_fetcher.py
    - services/market-data-service/app/config.py
  deleted:
    - scripts/test_public_bybit_api.py
    - services/market-data-service/tests/test_pagination_fix.py

key-decisions:
  - "Backtesting fetcher fail-fast lives on BOTH the __main__ entry AND the class-level fetch_klines first call (revision-2 plan amendment). Library callers that import BybitDataFetcher get the same operator hint as CLI users."
  - "BybitDataFetcher.get_klines() kept as a thin backwards-compatible alias delegating to fetch_klines, so existing download_*.py call sites continue to work and still trigger the first-call reachability probe."
  - "Constructor signature change is breaking: `BybitDataFetcher(testnet=...)` → `BybitDataFetcher(base_url=...)`. Documented in commit body."
  - "CLI flag `--testnet` replaced with `--connector-url` on backtesting/bybit_data_fetcher.py (matching the constructor; bybit-connector chooses testnet vs mainnet via its own env)."
  - "scripts/test_public_bybit_api.py deleted (Open Q #7 default — confirmed no in-repo automation references)."
  - "services/market-data-service/tests/test_pagination_fix.py deleted (Open Q #4 default — diagnostic, not unit test; analog test_fetcher.py is wholesale-skipped). Surfaced BC-FOLLOWUP-03 carry-in for an explicit respx unit test."

patterns-established:
  - "Sync + async assert_connector_reachable pair: sync variant uses httpx.Client and runs at __main__ entry before asyncio.run(); async variant uses httpx.AsyncClient and runs inside async library code"
  - "Class-level reachability probing gated by `_reachability_checked` instance flag (probe once per fetcher instance, not per call)"
  - "Backwards-compatible alias method (get_klines → fetch_klines) preserves existing call sites while routing through the new fail-fast gate"

requirements-completed:
  - BC-02
  - BC-05

# Metrics
duration: 32min
completed: 2026-05-21
---

# Phase 13 Plan 06: Wave-1 Cleanup — bybit-connector routing for fetch / backtesting scripts + BC-05 default-port fix Summary

**BC-02 closure for scripts/fetch_real_historical_data, scripts/collect_6months_historical, and backtesting/bybit_data_fetcher (with dual-path fail-fast on both __main__ and class-level fetch_klines); BC-05 one-line default-port fix (`bybit_connector_url` default `:8002` → `:8001`); two unused diagnostic-test files deleted.**

## Performance

- **Duration:** ~32 min
- **Started:** 2026-05-21T18:59:00Z
- **Completed:** 2026-05-21T19:31:42Z
- **Tasks:** 3 (6 commits total — Task 1 split per-script, Task 2 split per refactor/delete, Task 3 split per fix/delete)
- **Files modified:** 4
- **Files deleted:** 2

## Accomplishments

- **scripts/fetch_real_historical_data.py** now constructs the inner `BybitDataFetcher` against `${BYBIT_CONNECTOR_URL}/api/v1/market/kline` (default `http://localhost:8001`) and swaps the V5 `retCode/result` parser for the connector wrapper `success/data` shape. A synchronous `assert_connector_reachable()` probe runs at `__main__` entry, exiting 2 with operator-readable `docker compose ... bybit-connector` hint on D-04 fail-fast.
- **scripts/collect_6months_historical.py** is re-routed away from the legacy market-data-service `/api/v1/klines/{symbol}` proxy onto the bybit-connector endpoint directly. The script's internal V5-row normalizer feeds the same DataFrame pipeline downstream (`timestamp` / OHLC / volume keys preserved). Synchronous fail-fast at `__main__` entry.
- **backtesting/bybit_data_fetcher.py** dropped the `testnet: bool` constructor parameter entirely; the constructor now accepts an optional `base_url` override that falls back to `$BYBIT_CONNECTOR_URL`. The `--testnet` CLI flag was replaced with `--connector-url`. Fail-fast is on BOTH paths per the revision-2 plan amendment: a sync `assert_connector_reachable_sync()` in `__main__`, AND an async `await assert_connector_reachable()` at the top of `fetch_klines` gated by `self._reachability_checked` so batched fetches don't re-probe.
- **services/market-data-service/app/config.py** had its `bybit_connector_url` default flipped from `http://localhost:8002` to `http://localhost:8001`. The defect was a copy-paste of the service's own port; under the compose stack the env override hid it, but any host-side `Settings()` construction misrouted to market-data-service itself.
- **scripts/test_public_bybit_api.py** deleted (Open Q #7 default — no in-repo references; diagnostic probe with no automation hookup).
- **services/market-data-service/tests/test_pagination_fix.py** deleted (Open Q #4 default — diagnostic with real HTTP calls + print-based assertions; analog `test_fetcher.py` is wholesale `pytest.mark.skip`-d, so coverage parity wasn't a meaningful gate).

## Task Commits

Each task was committed atomically (one logical change per commit, intentional deletions verified):

1. **Task 1 (a): refactor scripts/fetch_real_historical_data.py** — `fedc4d9` (refactor)
2. **Task 1 (b): refactor scripts/collect_6months_historical.py** — `27632bf` (refactor)
3. **Task 2 (a): refactor backtesting/bybit_data_fetcher.py (fail-fast on BOTH __main__ AND class-level fetch_klines)** — `57b0d72` (refactor)
4. **Task 2 (b): delete scripts/test_public_bybit_api.py** — `9378a0f` (chore)
5. **Task 3 (a): fix BC-05 default port 8002 → 8001** — `293b17e` (fix)
6. **Task 3 (b): delete services/market-data-service/tests/test_pagination_fix.py** — `19927f7` (chore)

_Plan metadata commit follows this file._

## Files Created/Modified

- `scripts/fetch_real_historical_data.py` — routed through bybit-connector, sync fail-fast in `__main__`, V5 wrapper parser
- `scripts/collect_6months_historical.py` — routed through bybit-connector (was market-data-service proxy), sync fail-fast in `__main__`, V5 row normalizer feeding DataFrame pipeline
- `backtesting/bybit_data_fetcher.py` — routed through bybit-connector, `testnet: bool` constructor param dropped, `--testnet` CLI flag dropped (replaced with `--connector-url`), fail-fast on both `__main__` (sync) AND class-level `fetch_klines` (async, gated by `_reachability_checked`); `get_klines` kept as backwards-compatible alias
- `services/market-data-service/app/config.py` — `bybit_connector_url` default port flipped `:8002` → `:8001`
- `scripts/test_public_bybit_api.py` — **deleted** (intentional, Open Q #7)
- `services/market-data-service/tests/test_pagination_fix.py` — **deleted** (intentional, Open Q #4)

## Decisions Made

- **Fail-fast on BOTH paths for `backtesting/bybit_data_fetcher.py`** (revision-2 plan amendment): the file is both a CLI (`if __name__ == "__main__":`) and an importable library. The CLI path uses a synchronous probe (`assert_connector_reachable_sync()`) to exit cleanly before any `asyncio.run()`. The library path uses an async probe (`await assert_connector_reachable()`) on the first call to `fetch_klines`, gated by `self._reachability_checked` so batched downloads don't re-probe per batch. This mirrors `services/market-data-service/app/fetcher.py` where the class itself enforces the connector contract.
- **Kept `BybitDataFetcher.get_klines()` as a backwards-compatible alias** delegating to `fetch_klines()`. The signature changes (constructor now takes `base_url`, not `testnet`) are still breaking — but call-sites in `download_historical_data` and any external scripts that call `get_klines(...)` directly continue to work and still hit the first-call reachability probe.
- **Replaced `--testnet` CLI flag with `--connector-url`** on the `backtesting/bybit_data_fetcher.py` `argparse`. Testnet selection is no longer this script's responsibility — bybit-connector chooses via its own `BYBIT_TESTNET` env. The `--connector-url` override makes it easy to point at a non-default host.
- **`scripts/collect_6months_historical.py` was re-routed from market-data-service to bybit-connector directly**, even though the legacy code already used a wrapper service. Reason: the parametrize list in `tests/integration/test_scripts_fail_fast.py` requires the script to fail-fast on `BYBIT_CONNECTOR_URL`, not on `MARKET_DATA_API`. The contract is "all kline-fetching scripts route through bybit-connector"; routing via market-data-service would have left the fail-fast assertion RED on this case.
- **Deleted `scripts/test_public_bybit_api.py`** per Open Q #7 default. Final ref check (Makefile, .github/workflows/, RUNBOOK.md, docs/, .py, .yml, .sh, .json) confirmed zero in-repo automation references.
- **Deleted `services/market-data-service/tests/test_pagination_fix.py`** per Open Q #4 default. The file's structure (real HTTP calls, print-based "assertions", custom `main()` runner) is diagnostic, not a real pytest unit test. The natural analog (`test_fetcher.py`) is wholesale `pytest.mark.skip`-d, so "coverage parity" wasn't a meaningful pre-deletion check.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Stale `MARKET_DATA_API` reference in `verify_data_availability()` after constant removal**

- **Found during:** Task 1 (b) — refactor of `scripts/collect_6months_historical.py`.
- **Issue:** My initial edit dropped the `MARKET_DATA_API = "http://localhost:8002"` constant but left the legacy `verify_data_availability()` function still referencing it. If left in, the script would `NameError` at import time on any host that didn't already have `MARKET_DATA_API` in scope.
- **Fix:** Rewrote `verify_data_availability()` to delegate to `assert_connector_reachable()` (which itself exits 2 on D-04 fail-fast). The function now reports availability for the bybit-connector, matching the new routing.
- **Files modified:** `scripts/collect_6months_historical.py`
- **Verification:** Python `ast.parse()` + `python3 -m pytest tests/integration/test_scripts_fail_fast.py -v -k "collect_6months_historical"` → PASSED.
- **Committed in:** `27632bf` (Task 1 (b) commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug from intermediate refactor state).
**Impact on plan:** No scope creep. The fix was a direct consequence of removing the now-unused `MARKET_DATA_API` constant; bundled into the same commit as the broader refactor.

## Issues Encountered

- **PostToolUse formatter hook fired on `scripts/collect_6months_historical.py` and `backtesting/bybit_data_fetcher.py` after my first Edits**, normalizing whitespace and quote styles. After each event I re-read the target region before the next Edit so `old_string` matched the formatted content. One Edit failed on `backtesting/bybit_data_fetcher.py` initially (whitespace mismatch in the imports block) — re-Read + Edit succeeded on the second attempt. No work lost.
- **`pytest` host coverage threshold warning** at the end of `python3 -m pytest services/market-data-service/tests/test_config_defaults.py` (`FAIL Required test coverage of 80.0% not reached. Total coverage: 25.38%`). This is the global pytest-cov gate from `pyproject.toml`, not a Plan-06 contract failure. Both BC-05 assertions still PASSED. No action needed at this plan level.

## Carry-ins surfaced

- **BC-FOLLOWUP-03 — explicit pagination unit test** (Open Q #4): `services/market-data-service/tests/test_pagination_fix.py` was diagnostic, not a real unit test. The deletion accepts that pagination behavior is implicitly covered by `services/market-data-service/app/fetcher.py` (lines 248-391) when the service runs under integration testing. A follow-up requirement is to write a proper `respx`-based unit test that drives the pagination loop without hitting the exchange. Surfaced for a future plan-phase.

## RED → GREEN test transitions

| Test | Before this plan | After this plan |
|------|------------------|-----------------|
| `tests/integration/test_scripts_fail_fast.py::test_script_fails_fast_when_connector_unreachable[scripts/fetch_real_historical_data.py]` | RED | GREEN |
| `tests/integration/test_scripts_fail_fast.py::test_script_fails_fast_when_connector_unreachable[scripts/collect_6months_historical.py]` | RED | GREEN |
| `tests/integration/test_scripts_fail_fast.py::test_backtesting_fetcher_fails_fast_when_connector_unreachable` | RED | GREEN |
| `services/market-data-service/tests/test_config_defaults.py::test_bybit_connector_url_default_is_8001` | RED | GREEN |
| `services/market-data-service/tests/test_config_defaults.py::test_service_port_default_is_8002` | GREEN (guard) | GREEN (still guard) |

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 06 closes out the remaining Wave 1 BC-02 refactor surface for **scripts/fetch_real_historical_data** + **scripts/collect_6months_historical** + **backtesting/bybit_data_fetcher**, and lands the **BC-05 one-line default-port fix**. After Plans 04 + 05 + 07 land (Wave 1 in-flight), every BC-01 audit entry except the Binance archival (BC-04, Wave 2) has a corresponding refactor.
- BC-03 grep gate should be GREEN on the scripts touched by this plan; the remaining BC-03 violations belong to Plan 04 + 05 + 07 + the Wave-2 Binance archival.
- `BC-FOLLOWUP-03` (explicit pagination unit test via respx) is the only carry-in surfaced by this plan.

## Self-Check: PASSED

**Files modified — verified to exist on disk:**
- `scripts/fetch_real_historical_data.py` — FOUND
- `scripts/collect_6months_historical.py` — FOUND
- `backtesting/bybit_data_fetcher.py` — FOUND
- `services/market-data-service/app/config.py` — FOUND

**Files deleted — verified absent from disk:**
- `scripts/test_public_bybit_api.py` — ABSENT (deletion committed in `9378a0f`)
- `services/market-data-service/tests/test_pagination_fix.py` — ABSENT (deletion committed in `19927f7`)

**Commits — verified to exist in git log:**
- `fedc4d9` — refactor(scripts): centralize fetch_real_historical_data via bybit-connector + fail-fast (BC-02)
- `27632bf` — refactor(scripts): centralize collect_6months_historical via bybit-connector + fail-fast (BC-02)
- `57b0d72` — refactor(backtesting): centralize bybit_data_fetcher via bybit-connector; fail-fast in __main__ and class (BC-02)
- `9378a0f` — chore(scripts): delete unused scripts/test_public_bybit_api.py diagnostic probe (BC-02)
- `293b17e` — fix(market-data-service): correct bybit_connector_url default port 8002 → 8001 (BC-05)
- `19927f7` — chore(market-data-service): delete services/market-data-service/tests/test_pagination_fix.py (Open Q #4)

**Test results:**
- `tests/integration/test_scripts_fail_fast.py -k "fetch_real_historical or collect_6months_historical or backtesting"` → 3 passed, 10 deselected
- `services/market-data-service/tests/test_config_defaults.py::test_bybit_connector_url_default_is_8001` → PASSED

**Grep gates (zero matches on banned patterns in modified files):**
- `scripts/fetch_real_historical_data.py`: 0 bypass-pattern matches, 6 BYBIT_CONNECTOR_URL refs, `sys.exit(2)` present, "docker compose" hint present.
- `scripts/collect_6months_historical.py`: 0 bypass-pattern matches, 7 BYBIT_CONNECTOR_URL refs, `sys.exit(2)` present, "docker compose" hint present, 0 stale `MARKET_DATA_API` refs.
- `backtesting/bybit_data_fetcher.py`: 0 bypass-pattern matches, 9 BYBIT_CONNECTOR_URL refs, 0 `testnet: bool` matches, `sys.exit(2)` present (×4), "docker compose" hint present, `_reachability_checked` flag present (×3), `assert_connector_reachable_sync` used in `__main__`.

**Data-integrity guard:** `is_mainnet` filter in `backtesting/run_walk_forward_ensemble.py` (lines 563-566) unchanged — 3 lines, same as before this plan.

---

*Phase: 13-bybit-connector-market-data-centralization*
*Completed: 2026-05-21*
