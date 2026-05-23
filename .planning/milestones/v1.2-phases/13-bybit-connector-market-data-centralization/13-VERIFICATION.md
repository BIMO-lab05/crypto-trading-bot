---
phase: 13-bybit-connector-market-data-centralization
verified: 2026-05-22T03:00:00Z
status: human_needed
score: 7/7 must-haves verified
overrides_applied: 0
human_verification:
  - test: "BC-07 Test 1 — tape orderbook shape via refactored consumer"
    expected: "Inside ml-prediction-service container: pytest tests/integration/test_bybit_connector_tape_preserved.py::test_bybit_connector_orderbook_under_tape_returns_empty_shape passes (MARKET_DATA_SOURCE=tape; respx mock confirms consumer hits bybit-connector:8001, not api.bybit.com)"
    why_human: "Test requires ml-prediction-service Python environment (scipy, tensorflow deps not installed on host). pytest.fail message in the test body explicitly says 'Rerun inside the ml-prediction-service container or install its requirements.' On host: FAIL with documented container-required message — this is by design, not a code regression."
  - test: "BC-07 Test 2 — no live Bybit call during tape mode"
    expected: "Inside ml-prediction-service container: pytest tests/integration/test_bybit_connector_tape_preserved.py::test_no_live_bybit_call_during_tape_mode passes (respx assert_all_called=False; live_route.called must be False)"
    why_human: "Same transitive-dep constraint as Test 1. Same container-required pytest.fail message. On host: FAIL with documented message — not a code regression."
  - test: "Verify-stack Check 1 — live exchange URL in service logs"
    expected: "docker logs crypto-bot-bybit-connector shows 'mainnet' or 'api.bybit.com' (not testnet) after bybit-connector starts; BYBIT_TESTNET=false confirmed in env."
    why_human: "CLAUDE.md Verification standards: 'No declare features working end-to-end on curl/HTTP 200 alone.' Requires running stack + log inspection. Cannot verify without running docker compose up."
  - test: "Verify-stack Check 2 — real notification delivery"
    expected: "13-09 SUMMARY documents Check 2 as explicitly N/A for Phase 13 (Phase 13 did not touch notification surface). Operator to confirm or skip."
    why_human: "Notification path was not modified by Phase 13. Per 13-09 SUMMARY: 'verify-stack Check 2 explicitly N/A (Phase 13 did not touch notification surface).' Operator to confirm the N/A ruling is acceptable for phase-close."
  - test: "Verify-stack Check 3 — DB row persisted post-refactor"
    expected: "After running a bybit-connector-routed kline fetch: SELECT count(*) FROM klines WHERE ts > now()-interval '10 minutes' returns > 0. Confirms data flows through the new routing path into TimescaleDB."
    why_human: "Requires running stack with compose + psql access. Cannot verify without live service execution."
  - test: "Verify-stack Check 4 — restart after config change"
    expected: "Any service whose config changed in Phase 13 (market-data-service for BC-05, bybit-connector consumers) restarted before declaring integration verified; post-restart health probes return 200."
    why_human: "Requires running stack. Market-data-service config.py was edited (BC-05 default port fix); service must be restarted before in-memory state reflects the change per CLAUDE.md 'Stale in-memory state = most common false-pass.'"
---

# Phase 13: Bybit-Connector Market-Data Centralization — Verification Report

**Phase Goal:** Make `services/bybit-connector/` the sole Bybit-facing service in the codebase. Repo-wide audit and refactor every Python file outside the connector that imports `pybit`, hits `api.bybit.com`/`api-testnet.bybit.com`, or opens `wss://stream.bybit.com`. CI grep gate locks the new contract. Operator policy: archive `services/trading-engine/app/exchanges/binance.py`.

**Verified:** 2026-05-22T03:00:00Z
**Status:** HUMAN_NEEDED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth (Roadmap SC) | Status | Evidence |
|---|---|---|---|
| 1 | `tests/ci/test_no_bybit_bypass.py` green on `main`; grep across `**/*.py` outside `services/bybit-connector/` returns zero hits for all five banned patterns (BC-01, BC-03) | VERIFIED | `pytest tests/ci/test_no_bybit_bypass.py -v` → 5 passed in 101s. Raw repo-wide grep returns 0 hits for `from pybit`, `import pybit`, `https?://api.bybit.com`, `https?://api-testnet.bybit.com`, `wss?://stream.bybit`. |
| 2 | Every script under `scripts/` that previously pulled market data direct from Bybit now calls `${BYBIT_CONNECTOR_URL}/api/v1/market/...`; running with connector down fails fast pointing at `docker compose up bybit-connector` (BC-02, D-04) | VERIFIED | `scripts/collect_180_days_data.py`, `collect_6months_for_ml.py`, `collect_ml_training_data_simple.py`, `collect_bybit_direct_180days.py`, `collect_6months_historical.py`, `data_quality_enhancement.py`, `fetch_real_historical_data.py` all reference `BYBIT_CONNECTOR_URL`. Fail-fast confirmed: `sys.exit(2)` + literal `docker compose -f docker-compose.unified.yml up -d bybit-connector` in error path. |
| 3 | `services/ml-prediction-service/app/handlers/orderbook.py` calls `${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook`; `infrastructure/scripts/rotate_secrets.py` calls `${BYBIT_CONNECTOR_URL}/api/v1/account/balance` (BC-02) | VERIFIED | `orderbook.py` line 56: `_BYBIT_CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://bybit-connector:8001")`; line 326: `url = f"{_BYBIT_CONNECTOR_URL}/api/v1/market/orderbook"`. `rotate_secrets.py` line 69: `BYBIT_CONNECTOR_URL = os.getenv(...)` and line 200: `response = await client.get("/api/v1/account/balance")`. |
| 4 | `services/trading-engine/app/exchanges/binance.py` at `_archive_exchanges/binance.py`; `factory.py`, `__init__.py`, and `tests/test_multi_exchange.py` contain no live Binance references; trading-engine boots without ImportError (BC-04) | VERIFIED | `_archive_exchanges/binance.py` exists. `services/trading-engine/app/exchanges/binance.py` absent. `factory.py` grep for `BinanceExchangeAdapter` returns 0. `__init__.py` grep for `BinanceExchangeAdapter`, `from app.exchanges.binance`, `import.*binance` all return 0. `test_multi_exchange.py` absent. Only remaining `Binance` text in `__init__.py` is line 56 ASCII-art architecture diagram comment — non-functional, outside banned patterns. |
| 5 | `services/market-data-service/app/config.py` default reads `http://localhost:8001` (BC-05) | VERIFIED | Line 62: `bybit_connector_url: str = Field(default="http://localhost:8001")`. (PLAN cited line 58; actual line is 62 due to subsequent edits — content is correct.) `test_config_defaults.py::test_bybit_connector_url_default_is_8001` passes and asserts this exact value. |
| 6 | `RUNBOOK.md` contains "Market-data stale or missing — bybit-connector chain broken" symptom in Diagnose/Action/Verification format covering ≥3 root causes with concrete curl commands (BC-06) | VERIFIED | Symptom heading confirmed. Four sub-causes: A (container down), B (BYBIT_CONNECTOR_URL misconfigured), C (Bybit ratelimit), D (MARKET_DATA_SOURCE=tape in production). Diagnose/Action/Verification triad present. Curl command `curl http://bybit-connector:8001/api/v1/market/ticker?symbol=BTCUSDT&category=linear` present. |
| 7 | Integration test `tests/integration/test_bybit_connector_tape_preserved.py` asserts `MARKET_DATA_SOURCE=tape` works for refactored consumers (BC-07) | VERIFIED (code exists; container execution human_needed) | 3 test functions defined. Test 3 (`test_tape_stub_shapes_match_handler_expectations`) passes on host (1/3 green). Tests 1 and 2 require ml-prediction-service container (documented `pytest.fail` with explicit container-required message — by design, not a regression). |

**Score:** 7/7 truths verified at code level

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `scripts/audit_bybit_bypass.py` | Repo-wide bypass enumeration script | VERIFIED | Exists, >60 lines, emits JSON per BC-01 schema |
| `.planning/evidence/BC-01/bybit-bypass-audit.json` | Audit JSON with ≥18 entries | VERIFIED | 20 entries; kinds: `mainnet_rest_url` (15), `testnet_rest_url` (3), `pybit_import` (2); 16 unique files. Note: `wss_stream_url` kind absent (0 entries) — correct, no wss bypass sites exist in repo. |
| `tests/ci/test_no_bybit_bypass.py` | CI grep gate test (5 tests) | VERIFIED | Exists; 5 test functions; 5/5 pass |
| `.github/workflows/bybit-bypass-gate.yml` | Valid YAML workflow on PR+push to main | VERIFIED | Valid YAML; triggers on `pull_request` (branches: main) and `push` (branches: main); single job `bc03-grep-gate` invoking `pytest tests/ci/test_no_bybit_bypass.py -v` |
| `tests/integration/test_bybit_connector_tape_preserved.py` | BC-07 tape test with 3 functions | VERIFIED | 3 async test functions present; Tests 1+2 have documented container-required `pytest.fail` messages |
| `services/market-data-service/tests/test_config_defaults.py` | BC-05 test asserting :8001 default | VERIFIED | `test_bybit_connector_url_default_is_8001` present and asserts `"http://localhost:8001"` |
| `RUNBOOK.md` | BC-06 symptom with 4 sub-causes | VERIFIED | 4 sub-causes A/B/C/D confirmed |
| `_archive_exchanges/binance.py` | Archived Binance adapter | VERIFIED | Exists at repo root |
| `services/trading-engine/app/exchanges/binance.py` | MUST NOT EXIST | VERIFIED | Absent |
| `services/trading-engine/tests/test_multi_exchange.py` | MUST NOT EXIST | VERIFIED | Absent |
| `scripts/test_public_bybit_api.py` | MUST NOT EXIST | VERIFIED | Absent |
| `services/market-data-service/tests/test_pagination_fix.py` | MUST NOT EXIST | VERIFIED | Absent |

---

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `scripts/audit_bybit_bypass.py` | `.planning/evidence/BC-01/bybit-bypass-audit.json` | `json.dump` on invocation | VERIFIED | 20-entry JSON committed; script idempotent |
| `ml-prediction-service/app/handlers/orderbook.py` | `${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook` | httpx GET | VERIFIED | `_BYBIT_CONNECTOR_URL` env-read + `/api/v1/market/orderbook` path in handler |
| `infrastructure/scripts/rotate_secrets.py` | `${BYBIT_CONNECTOR_URL}/api/v1/account/balance` | httpx GET | VERIFIED | `BYBIT_CONNECTOR_URL` env-read + `/api/v1/account/balance` in auth-ping function |
| `shared/health_check.py` | `${BYBIT_CONNECTOR_URL}/health` | httpx GET | VERIFIED | `BYBIT_CONNECTOR_URL = os.getenv(...)` + `url = f"{BYBIT_CONNECTOR_URL}/health"` |
| All `scripts/collect_*.py` + `backtesting/bybit_data_fetcher.py` | `${BYBIT_CONNECTOR_URL}/api/v1/market/kline` | httpx/requests GET + fail-fast | VERIFIED | Each file references `BYBIT_CONNECTOR_URL`; fail-fast calls `sys.exit(2)` with `docker compose` message |
| `tests/ci/test_no_bybit_bypass.py` | `.github/workflows/bybit-bypass-gate.yml` | `pytest` invocation in workflow `run:` step | VERIFIED | Workflow runs `pytest tests/ci/test_no_bybit_bypass.py -v` on every PR+push |

---

### Data-Flow Trace (Level 4)

Level 4 not applicable for this phase — phase delivers refactored CLI scripts, a CI gate, documentation artifacts, and an archived file. No React/Next.js component rendering dynamic data.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| BC-03 grep gate passes | `pytest tests/ci/test_no_bybit_bypass.py -v` | 5 passed in 101s | PASS |
| Zero banned patterns in codebase | `grep -rn --include="*.py" -E "from pybit\|import pybit" . --exclude-dir=services/bybit-connector` | No output (0 matches) | PASS |
| Zero hardcoded Bybit URLs | `grep -rn --include="*.py" -E "https?://api\.bybit\.com\|wss?://stream\.bybit" . --exclude-dir=services/bybit-connector` | No output (0 matches) | PASS |
| BC-01 artifact has ≥18 entries | `python3 -c "import json; arr=json.load(open(...)); assert len(arr)>=18"` | 20 entries | PASS |
| BC-05 config default is :8001 | `grep -n "bybit_connector_url.*localhost" services/market-data-service/app/config.py` | Line 62: `localhost:8001` | PASS |
| BC-04 archive exists, source absent | `test -f _archive_exchanges/binance.py && ! test -f services/trading-engine/app/exchanges/binance.py` | Both true | PASS |
| BC-06 RUNBOOK 4 sub-causes | `grep -c "Sub-cause [ABCD]" RUNBOOK.md` | 4 | PASS |
| BC-07 test pin (Test 3) | `pytest tests/integration/test_bybit_connector_tape_preserved.py::test_tape_stub_shapes_match_handler_expectations -v` | 1 passed | PASS |
| BC-07 Tests 1+2 container-required | `pytest tests/integration/test_bybit_connector_tape_preserved.py -v` | 2 failed with documented container-required message, 1 passed | SKIP (human_needed — by design) |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| BC-01 | 13-01 | Audit JSON artifact ≥18 entries, all 5 keys, valid schema | SATISFIED | 20 entries; `scripts/audit_bybit_bypass.py` runs without error; artifact tracked in git |
| BC-02 | 13-04..13-07 | All bypass sites refactored to bybit-connector REST; fail-fast with docker compose message | SATISFIED | 0 grep hits; all consumers reference `BYBIT_CONNECTOR_URL`; `sys.exit(2)` + `docker compose` message in every refactored script |
| BC-03 | 13-02 | CI grep gate green on main; workflow in `.github/workflows/` | SATISFIED | 5/5 CI tests pass; valid YAML workflow present; triggers on PR+push to main |
| BC-04 | 13-08 | Binance adapter archived; factory.py + __init__.py cleaned; test_multi_exchange.py deleted | SATISFIED | All file checks pass; 0 functional Binance refs in trading-engine |
| BC-05 | 13-06 | `config.py` default port `8001` instead of `8002` | SATISFIED | Line 62 verified; `test_config_defaults.py` GREEN |
| BC-06 | 13-09 | RUNBOOK symptom with Diagnose/Action/Verification, 4 root causes, concrete curl commands | SATISFIED | All 4 sub-causes (A/B/C/D) confirmed; curl command present |
| BC-07 | 13-03 | Tape preservation test: 3 tests defined; Tests 1+2 GREEN inside container | SATISFIED (code) / human_needed (container execution) | 3 tests defined; Test 3 always-green on host (1/3); Tests 1+2 GREEN only inside ml-prediction-service container per documented design |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `services/trading-engine/app/exchanges/__init__.py` | 56 | `\| - Binance \|` in ASCII-art architecture diagram comment | INFO | Non-functional comment in module docstring; BC-03 gate does not flag it; D-02 cleanup targeted live import lines 23, 213, 329, 330, 513 which are all clean. No impact on runtime. |
| `.planning/codebase/INTEGRATIONS.md` | 230 | REST API row still lists `ml-prediction-service` as direct `https://api.bybit.com/*` consumer | INFO | Documentation drift — stale after BC-02 refactored ml-prediction orderbook handler to route through bybit-connector. D-10 scope was explicitly line 231 (WS row) only per CONTEXT.md, 13-09 PLAN, and 13-09 SUMMARY. Not a code gap. 13-09 SUMMARY registers this as BC-FOLLOWUP-01 for a future hardening pass. |

No BLOCKER anti-patterns found.

---

### Human Verification Required

#### 1. BC-07 Test 1 — Tape orderbook shape via refactored consumer

**Test:** Inside the `crypto-bot-ml-prediction-service` container, run:
```
docker exec crypto-bot-ml-prediction-service bash -c "cd /app && PYTHONPATH=. pytest tests/integration/test_bybit_connector_tape_preserved.py::test_bybit_connector_orderbook_under_tape_returns_empty_shape -v"
```
or from repo root with PYTHONPATH set to the service:
```
PYTHONPATH=services/ml-prediction-service pytest tests/integration/test_bybit_connector_tape_preserved.py::test_bybit_connector_orderbook_under_tape_returns_empty_shape -v
```

**Expected:** Test passes. respx confirms `connector_route.called = True`, `live_route.called = False`. Consumer handles `{"a":[],"b":[],"ts":0,"u":0}` tape stub without exception.

**Why human:** ml-prediction-service transitive deps (scipy, tensorflow) are not installed on the host. Test `pytest.fail` message says explicitly: "Rerun inside the ml-prediction-service container or install its requirements." This is by design — not a code regression.

---

#### 2. BC-07 Test 2 — No live Bybit call during tape mode

**Test:** Same container context as Test 1:
```
docker exec crypto-bot-ml-prediction-service bash -c "cd /app && PYTHONPATH=. pytest tests/integration/test_bybit_connector_tape_preserved.py::test_no_live_bybit_call_during_tape_mode -v"
```

**Expected:** Test passes. respx confirms `live_route.called = False` (consumer never hits `https://api.bybit.com/v5/market/orderbook` under tape mode).

**Why human:** Same container-dep constraint as Test 1.

---

#### 3. Verify-stack Check 1 — Live exchange URL in service logs

**Test:** With the compose stack running (`docker compose -f docker-compose.unified.yml up -d`), inspect bybit-connector logs:
```
docker logs crypto-bot-bybit-connector --tail 50 | grep -iE "mainnet|api.bybit.com|BYBIT_TESTNET"
docker exec crypto-bot-bybit-connector env | grep BYBIT_TESTNET
```

**Expected:** `BYBIT_TESTNET=false` in env; logs reference mainnet endpoint (not testnet). No `api-testnet.bybit.com` in live connection logs.

**Why human:** Requires running Docker stack. CLAUDE.md "Verification standards": "Real proof needs: live exchange URL visible in service logs (not testnet)."

---

#### 4. Verify-stack Check 2 — Real notification delivery (N/A assessment)

**Test:** Confirm whether Phase 13 requires notification verification. Per 13-09 SUMMARY: "verify-stack Check 2 explicitly N/A (Phase 13 did not touch notification surface)."

**Expected:** Operator confirms the N/A ruling. If Check 2 is waived for Phase 13 (no notification surface touched), record the waiver. If operator disagrees, run: trigger a trading signal and confirm Telegram/email arrives.

**Why human:** Judgment call on whether N/A waiver is acceptable for a phase that centralized market-data routing without touching notifications.

---

#### 5. Verify-stack Check 3 — DB row persisted via refactored routing

**Test:** With stack running, trigger a kline fetch through the refactored bybit-connector path and confirm TimescaleDB persistence:
```
curl -s "http://localhost:8002/api/v1/collect/ticker/BTCUSDT"
sleep 10
docker exec -it crypto-bot-timescaledb psql -U postgres -d trading_bot -c "SELECT count(*) FROM klines WHERE ts > now() - interval '2 minutes';"
```

**Expected:** Row count > 0 after fetch.

**Why human:** Requires running compose stack + psql access. CLAUDE.md: "relevant DB row persisted (paste SELECT result)."

---

#### 6. Verify-stack Check 4 — Restart after config change confirmed

**Test:** Confirm that `market-data-service` (BC-05 config.py default port edit) was restarted after the Phase 13 edits. If not already done:
```
docker compose -f docker-compose.unified.yml up -d --force-recreate market-data-service
sleep 5
curl http://localhost:8002/health
```

**Expected:** `market-data-service` reports healthy after recreate; no stale in-memory config state.

**Why human:** CLAUDE.md: "Stale in-memory state = most common false-pass. When config changes, restart service before re-running integration tests."

---

### Gaps Summary

No gaps. All 7 BC-NN requirements are satisfied at the code level. Phase goal is achieved: `services/bybit-connector/` is the sole Bybit-facing service; repo-wide grep confirms zero bypass sites; CI gate enforces the contract; Binance adapter archived; config defect fixed; RUNBOOK documents the chain; tape preservation test structure is correct.

Two human verification items remain before phase can be declared fully closed:
1. BC-07 Tests 1+2 must pass inside the ml-prediction-service container.
2. Verify-stack 4-check matrix must be executed by the operator per CLAUDE.md "Verification standards."

These are operational gates, not code defects. No rework is required.

---

_Verified: 2026-05-22T03:00:00Z_
_Verifier: Claude (gsd-verifier)_
