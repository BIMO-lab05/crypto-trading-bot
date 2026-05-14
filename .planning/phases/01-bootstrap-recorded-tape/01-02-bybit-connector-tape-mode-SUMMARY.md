---
phase: 01-bootstrap-recorded-tape
plan: 02
subsystem: infra
tags: [bybit-connector, tape-mode, jsonl, fixtures, pydantic, fastapi, pytest]

requires:
  - phase: 01-bootstrap-recorded-tape
    plan: 01
    provides: "JSONL fixture schema (tape_version header, klines/ticker sub-dirs) consumed by TapeReplayClient"

provides:
  - "MARKET_DATA_SOURCE=tape|live selector in bybit-connector Settings (D-14)"
  - "TapeReplayClient: in-process JSONL replay mirroring BybitRestClient async surface (D-15)"
  - "Conditional credential validator: empty BYBIT_API_KEY/SECRET allowed in tape mode (D-17)"
  - "Lifespan branch: tape path skips live REST init and clock sync, emits grep-able startup log"
  - "7 unit tests covering /ready ticker shape (§3), unknown-symbol fallback (§4), missing-fixture refusal (§6)"

affects:
  - 01-bootstrap-recorded-tape (plan 03 bootstrap.sh consumes MARKET_DATA_SOURCE selector)
  - 01-bootstrap-recorded-tape (plan 04 CI workflow uses tape mode as default)

tech-stack:
  added: []
  patterns:
    - "model_validator(mode='after') for cross-field conditional validation (replaces field_validator)"
    - "Eager JSONL fixture loading at init with loud FileNotFoundError on missing fixtures (landmine §6 pattern)"
    - "DI seam via app.state.rest_client: TapeReplayClient / BybitRestClient both satisfy the same async interface"
    - "Distinct BYBIT_PRICE_SOURCE: mode=tape|live grep-able startup log line for audit/verify-stack"

key-files:
  created:
    - services/bybit-connector/app/tape_replay_client.py
    - services/bybit-connector/tests/test_tape_replay_client.py
  modified:
    - services/bybit-connector/app/config.py
    - services/bybit-connector/app/main.py
    - services/bybit-connector/tests/conftest.py

key-decisions:
  - "Field(default='') for bybit_api_key/secret instead of Field(...) — enables tape mode with truly empty .env (not just empty docker-compose default)"
  - "model_validator(mode='after') required over field_validator — field validators cannot read other field values"
  - "conftest.py MARKET_DATA_SOURCE=live preserves all existing tests on live branch (no test migration needed)"
  - "TapeReplayClient.get_ticker/get_kline return empty results (not raise) for unknown symbols — matches scheduler.py 7-symbol iteration vs v1 tape 5-symbol coverage"
  - "Tape lifespan uses try/finally + return to exit generator early, avoiding double-close in live path's finally"

requirements-completed:
  - INFRA-03

duration: 35min
completed: 2026-05-07
---

# Phase 01 Plan 02: Bybit Connector Tape Mode Summary

**TapeReplayClient JSONL replay loader with MARKET_DATA_SOURCE selector wired into bybit-connector lifespan, enabling offline bootstrap with empty Bybit credentials (D-14, D-15, D-17)**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-05-07T00:00:00Z
- **Completed:** 2026-05-07T00:35:00Z
- **Tasks:** 3 (+ conftest.py fix bundled in Task 1 commit)
- **Files modified:** 5

## Accomplishments

- `config.py`: Added `market_data_source` (Literal["tape","live"], default="tape"), `tape_fixtures_path` (Path), `is_tape_mode` property. Converted per-field `@field_validator` on API credentials to `@model_validator(mode="after")` so empty creds pass when mode is tape but raise `ValueError` in live mode.
- `tape_replay_client.py` (new): `TapeReplayClient` eagerly loads JSONL fixtures at init. Guards: tape_version mismatch raises ValueError (D-07); missing/empty dirs raise FileNotFoundError (landmine §6); unknown symbols return `[]`/`{"list":[]}` without raising (landmine §4); SOLUSDT ticker returns non-empty so `/ready` returns 200 (landmine §3). Out-of-scope feeds (orderbook, funding, recent-trades, instruments-info) stubbed empty per D-02.
- `main.py`: Lifespan branches on `settings.market_data_source`. Tape path skips live REST init and clock sync; emits `BYBIT_PRICE_SOURCE: mode=tape source_dir=... tape_version=1`. Live path emits `BYBIT_PRICE_SOURCE: mode=live testnet=...`. DI seam (`app.state.rest_client`) unchanged — downstream routes need zero edits (D-15).
- `test_tape_replay_client.py` (new): 7 tests, all passing. Cover landmines §3/§4/§6 plus D-07 tape_version validation and D-15 kline shape. All use `tmp_path` — no dependency on plan-01-01 fixture files.

## Task Commits

1. **Task 1: config.py MARKET_DATA_SOURCE + conftest fix** - `5d163f5` (feat)
2. **Task 2: TapeReplayClient** - `0679c47` (feat)
3. **Task 3: main.py lifespan branch** - `bfdcc54` (feat)
4. **Task 4: test_tape_replay_client.py** - `b354ec7` (test)

## Files Created/Modified

- `services/bybit-connector/app/config.py` — Added market_data_source, tape_fixtures_path, is_tape_mode; conditional credential validator via model_validator
- `services/bybit-connector/app/tape_replay_client.py` — NEW: TapeReplayClient mirroring BybitRestClient async surface
- `services/bybit-connector/app/main.py` — Lifespan branch on market_data_source, TapeReplayClient import, distinct startup log lines
- `services/bybit-connector/tests/test_tape_replay_client.py` — NEW: 7 unit tests (landmines §3/§4/§6, D-07, D-15)
- `services/bybit-connector/tests/conftest.py` — Added MARKET_DATA_SOURCE=live so existing tests stay on live branch

## TapeReplayClient Coverage vs BybitRestClient

| Method | TapeReplayClient | Status |
|--------|-----------------|--------|
| `get_ticker(category, symbol)` | Returns JSONL snapshot; unknown symbol -> `{"list":[]}` | Full (v1 tape) |
| `get_kline(category, symbol, interval, limit, start_time, end_time)` | Returns JSONL rows, descending order, optional window filter | Full (v1 tape) |
| `get_orderbook(...)` | Returns `{"a":[], "b":[], "ts":0, "u":0}` | Stub (Phase 5) |
| `get_recent_trades(...)` | Returns `{"list":[]}` | Stub (Phase 5) |
| `get_funding_rate_history(...)` | Returns `{"list":[]}` | Stub (Phase 5) |
| `get_instruments_info(...)` | Returns `{"list":[]}` | Stub (Phase 5) |
| `close()` | No-op (no HTTP client) | Full |

## Decisions Made

- Used `Field(default="")` instead of `Field(...)` for API key/secret — enables truly empty `.env` in tape mode, not just docker-compose's `${VAR:-}` default.
- Used `model_validator(mode="after")` — the only pydantic v2 validator that can read other fields (field_validators cannot).
- Bundled conftest.py env override in commit 1 so commits 2-4 never break the existing test suite.
- Tape lifespan uses `try/finally` + `return` to exit the async generator early without touching the live branch's finally block.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Field(default="") instead of Field(...) for API credentials**
- **Found during:** Task 1 — advisor review before writing
- **Issue:** Plan specified Field(...) (required) for bybit_api_key/secret. With model_validator making validation conditional, if the env var is completely absent (not just empty), pydantic's required-field gate runs before the model_validator and would reject it — defeating D-17 for truly empty .env files.
- **Fix:** Changed to `Field(default="", ...)` so field is always populated (empty string) when env var is absent; model_validator then decides whether to enforce.
- **Files modified:** services/bybit-connector/app/config.py
- **Verification:** `Settings(market_data_source='tape', bybit_api_key='', bybit_api_secret='')` succeeds
- **Committed in:** 5d163f5 (Task 1 commit)

**2. [Rule 2 - Missing Critical] conftest.py MARKET_DATA_SOURCE env override**
- **Found during:** Task 1 — advisor review identified that adding MARKET_DATA_SOURCE default="tape" would break existing tests because the tape lifespan path tries to load fixtures from `/app/tests/fixtures/tape` which doesn't exist on the host.
- **Fix:** Added `os.environ["MARKET_DATA_SOURCE"] = "live"` to conftest.py alongside existing env overrides, keeping the existing test fixture (patch on create_rest_client) valid.
- **Files modified:** services/bybit-connector/tests/conftest.py
- **Verification:** 348 existing tests pass (1 pre-existing failure in test_config.py::test_settings_default_values unrelated to this plan — assertion `bybit_testnet is True` contradicts Field(default=False) in base commit; confirmed pre-existing)
- **Committed in:** 5d163f5 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 bug/safety, 1 missing critical)
**Impact on plan:** Both fixes necessary for correctness. No scope creep. Plan's functional requirements met exactly.

## Issues Encountered

- Pre-existing test failure in `test_config.py::TestSettingsInitialization::test_settings_default_values`: asserts `bybit_testnet is True` but field default is `False` in base commit `5b98dc4`. Not introduced by this plan. Not fixed (out of scope per deviation rules).

## User Setup Required

None — no external service configuration required. Tape mode runs against fixtures in `tests/fixtures/tape/` (created by plan 01-01, bind-mounted in docker-compose per plan 01-03).

## Next Phase Readiness

- Ready for plan 01-03 (`docker-compose.unified.yml` + `bootstrap.sh`) — tape selector in bybit-connector is complete; compose needs `MARKET_DATA_SOURCE=${MARKET_DATA_SOURCE:-tape}` env var and `./tests/fixtures/tape:/app/tests/fixtures/tape:ro` bind-mount.
- Ready for plan 01-04 (live-smoke CI) — tape is now the default; live-smoke flips `MARKET_DATA_SOURCE=live`.
- Phase 5 work needed: populate orderbook + funding stubs in TapeReplayClient when PREFER_MAKER_ORDERS / ENABLE_FUNDING_GATE forward-tests run.

## Self-Check: PASSED

- `pytest tests/test_tape_replay_client.py -x -q` → 7 passed
- `pytest tests/ --no-cov` (excl. pre-existing broken test) → 348 passed, 25 skipped, 0 new failures
- `Settings(market_data_source='tape', bybit_api_key='', bybit_api_secret='')` → no error
- `Settings(market_data_source='live', bybit_api_key='', bybit_api_secret='')` → ValueError with "must be set"
- `ast.parse(open('main.py').read())` → syntax OK
- `grep -c "BYBIT_PRICE_SOURCE: mode=" main.py` → 3 (tape log + live log + comment)
- `grep -q "TapeReplayClient" main.py` → present
- git log shows 4 atomic commits in sequence

---
*Phase: 01-bootstrap-recorded-tape*
*Completed: 2026-05-07*
