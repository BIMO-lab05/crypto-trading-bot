---
status: partial
phase: 13-bybit-connector-market-data-centralization
source: [13-VERIFICATION.md]
started: 2026-05-22T03:00:00Z
updated: 2026-05-22T03:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. BC-07 Test 1 — tape orderbook shape via refactored consumer
expected: Inside `crypto-bot-ml-prediction-service` container, run `pytest tests/integration/test_bybit_connector_tape_preserved.py::test_bybit_connector_orderbook_under_tape_returns_empty_shape` with `MARKET_DATA_SOURCE=tape` and confirm test passes. respx mock confirms refactored consumer hits `bybit-connector:8001`, not `api.bybit.com`.
result: [pending]
why_human: Test requires `services/ml-prediction-service/` Python env (scipy + tensorflow + sklearn). On host pytest fails with documented `pytest.fail("Could not load services/ml-prediction-service/app/handlers/orderbook.py (missing transitive deps in this host env)…")` message — by design, not a code regression.

### 2. BC-07 Test 2 — no live Bybit call during tape mode
expected: Inside `crypto-bot-ml-prediction-service` container, run `pytest tests/integration/test_bybit_connector_tape_preserved.py::test_no_live_bybit_call_during_tape_mode` with `MARKET_DATA_SOURCE=tape` and confirm test passes. respx assertion: `live_route.called == False`.
result: [pending]
why_human: Same transitive-dep constraint as Test 1. Container-only.

### 3. Verify-stack Check 1 — live exchange URL visible in service logs (mainnet, not testnet)
expected: After `docker compose up -d bybit-connector`, `docker logs crypto-bot-bybit-connector --tail 100` shows `api.bybit.com` mainnet references (NOT `api-testnet.bybit.com`). `BYBIT_TESTNET=false` confirmed in container env. `curl -s "http://localhost:8001/api/v1/market/ticker?symbol=BTCUSDT&category=linear"` returns JSON with non-zero `lastPrice`.
result: [pending]
why_human: CLAUDE.md Verification standards forbid declaring features working end-to-end on curl/HTTP 200 alone. Requires running stack + log inspection.

### 4. Verify-stack Check 2 — real notification delivery (N/A ruling)
expected: Phase 13 did NOT touch the notification surface. Plan 13-09 SUMMARY documents Check 2 as explicitly N/A. Operator confirms the N/A waiver is acceptable for phase-close OR runs a notification-service smoke (e.g., trigger a Telegram digest) to confirm no regression from Phase 13 commits.
result: [pending]
why_human: Operator confirms scope waiver; no autonomous reproduction.

### 5. Verify-stack Check 3 — DB row persisted post-refactor
expected: After running a refactored consumer (any `scripts/collect_*.py` or `services/ml-prediction-service/download_*.py`) against the running stack, `psql -d market_data -c "SELECT count(*) FROM klines WHERE ts > now() - interval '10 minutes';"` returns > 0. Confirms market-data flow lands rows via the new bybit-connector routing.
result: [pending]
why_human: Requires running stack + psql + live consumer execution.

### 6. Verify-stack Check 4 — restart after config change (BC-05 default port)
expected: After Phase 13 changes land on `main`, run `docker compose -f docker-compose.unified.yml up -d --force-recreate market-data-service` (and `ml-prediction-service`, `trading-engine` whose code touched the env-read paths). Health probes return 200. Stale in-memory state cleared per CLAUDE.md "Stale in-memory state = most common false-pass" rule.
result: [pending]
why_human: Requires running stack. Verifies refactored consumers re-read env on recreate.

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps

[No code gaps. All 6 items are operational gates — running stack + container execution.]
