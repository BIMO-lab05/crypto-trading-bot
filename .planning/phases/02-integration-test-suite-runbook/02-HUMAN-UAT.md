---
status: partial
phase: 02-integration-test-suite-runbook
source: [02-VERIFICATION.md]
started: 2026-05-08T18:30:00Z
updated: 2026-05-08T18:30:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. INFRA-01 round-trip — pytest tests/integration/test_fresh_clone_round_trip.py against booted stack

expected: `test_fresh_clone_round_trip` passes — bootstrap_stack reports all 10 services healthy, SOLUSDT ticker returns non-empty, force_signal → position row in DB within 60s, notification matches symbol marker. `test_all_ten_services_healthy` and `test_unknown_symbol_does_not_500` also pass.

run: `bash bootstrap.sh && pytest tests/integration/test_fresh_clone_round_trip.py -v`

result: [pending]

### 2. CD-05 ML-on variant — pytest -m ml_on with ENABLE_ML_PREDICTIONS=true

expected: `test_ml_models_loaded` passes (confidence != 0.0 — proves GRU model loaded into ml-prediction-service when CD-05 nightly variant runs). `test_ml_prediction_endpoint_alive` also passes.

run: `ENABLE_ML_PREDICTIONS=true bash bootstrap.sh && pytest tests/integration -m ml_on -v`

result: [pending]

### 3. INFRA-06 Bug 1 integration regression — test_stale_ml_model_reload

expected: docker exec touch on the in-container model file triggers `_reload_if_stale()` during the next prediction call; container logs contain `MODEL_RELOAD: path=` line.

run: `pytest tests/integration/test_pre_existing_bug_regressions.py::test_stale_ml_model_reload -v` against the booted stack with ml-prediction healthy.

result: [pending]

### 4. CD-01 notification delivery — test_notification_delivery.py

expected: `test_notification_delivery_via_trade_endpoint` passes — POST /api/v1/notify/trade returns 200, and the unique marker `PHASE2-<ts>` appears in tests/.notifications.log within 15s in record-mode (or in Telegram getUpdates in live-mode).

run: `pytest tests/integration/test_notification_delivery.py -v` against the running stack.

result: [pending]

### 5. WR-09 EMERGENCY_STOP coupling — operator confirms doc-only resolution

expected: WR-09 chose Option B (document EMERGENCY_STOP coupling in fixture docstring) over Option A (clear file in fixture). The conftest.py docstring at lines 99-124 is substantive and explicit. Operator should confirm doc-only resolution is acceptable rather than the active-clear approach.

run: `sed -n '95,130p' tests/integration/conftest.py` — read the docstring; then operator decides Option B (current) vs Option A (active-clear, would be a follow-up commit).

result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
