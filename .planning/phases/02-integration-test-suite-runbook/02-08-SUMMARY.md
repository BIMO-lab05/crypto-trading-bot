---
phase: 02-integration-test-suite-runbook
plan: 8
subsystem: infra
tags: [ml-prediction, technical-analysis, signal-aggregator, model-reload, mtime, docker-compose, runbook]

# Dependency graph
requires:
  - phase: 02-integration-test-suite-runbook
    provides: Bootstrap/integration test harness, RUNBOOK.md structure, conftest fixtures

provides:
  - "_reload_if_stale() mtime-watching hook in GRUPricePredictor (Bug 1 FIXED)"
  - "confidence > 0 filter + AGGREGATOR_CONFIDENCE_FILTER log in handlers/analysis.py (Bug 2 FIXED)"
  - "INFRA-06 Bug Triage Outcomes table in RUNBOOK.md (Bug 3 DOCUMENTED)"
  - "Unit regression tests: test_model_reload.py (3 tests), test_signal_aggregator_confidence_zero.py (3 tests)"
  - "Integration regression: test_pre_existing_bug_regressions.py::test_stale_ml_model_reload"

affects:
  - ml-prediction-service
  - technical-analysis
  - trading-engine (consumes aggregated signals)
  - integration-test-suite

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "mtime-watching model reload: _reload_if_stale() checks stat().st_mtime before predict(); returns bool; MODEL_RELOAD: path= log on fire"
    - "confidence filter at aggregation chokepoint: filter before weighted-sum, AGGREGATOR_CONFIDENCE_FILTER: dropped N log on fire"
    - "compose-resolved integration test: _resolve_compose_value() reads docker-compose.unified.yml at runtime to avoid hardcoding container names (Blocker #4)"
    - "profile-gated service bootstrap in integration test: _ensure_ml_prediction_running() starts ml-prediction with --profile ml if not already healthy"

key-files:
  created:
    - services/ml-prediction-service/tests/test_model_reload.py
    - services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py
    - tests/integration/test_pre_existing_bug_regressions.py
  modified:
    - services/ml-prediction-service/app/ml_models/gru_predictor.py
    - services/ml-prediction-service/app/ml_models/gru_model.py
    - services/technical-analysis/app/handlers/analysis.py
    - RUNBOOK.md

key-decisions:
  - "Bug 1 retarget: plan called for new model_loader.py + ModelLoader class; retargeted to inline _reload_if_stale() in GRUPricePredictor (mirrors existing gru_model.py:140-166 pattern already present in codebase)"
  - "Bug 2 retarget: plan targeted signal_aggregator.py (does not exist); retargeted to handlers/analysis.py get_aggregated_signal where actual weighted-sum lives; tuple shape (label, confidence) not object.confidence"
  - "Bug 3: no code fix; DOCUMENTED in RUNBOOK with FIXED/DOCUMENTED/DOCUMENTED status rows; Makefile build-no-buildkit shortcut in Plan 02-10"
  - "Integration test design: ml-prediction is profile-gated (profiles: [ml]); test starts it with --profile ml if needed rather than depending on bootstrap_stack (which would fail waiting for port 8007)"

patterns-established:
  - "Compose-resolution at test time: _resolve_compose_value(service, pattern) extracts fields from compose yaml at runtime — no hardcoded container names in tests"
  - "Profile-gated service self-bootstrap: integration tests that need profile-gated services start them inline rather than requiring manual compose profile invocation"

requirements-completed: [INFRA-06]

# Metrics
duration: 30min
completed: 2026-05-08
---

# Phase 02 Plan 08: INFRA-06 Pre-Existing Bug Triage Summary

**mtime-watching ML model reload in GRUPricePredictor + confidence>0 filter at signal aggregation chokepoint + RUNBOOK triage outcomes table for all 3 INFRA-06 bugs**

## Performance

- **Duration:** ~30 min (Tasks 3-4; Task 2 was prior continuation)
- **Started:** 2026-05-08T14:20:20Z (Task 2 base)
- **Completed:** 2026-05-08T14:50:28Z
- **Tasks:** 4 total (Task 1: checkpoint/investigation; Task 2: Bug 1 fix; Task 3: Bug 2 fix; Task 4: integration regression + RUNBOOK)
- **Files modified:** 7

## Accomplishments

- Bug 1 FIXED: `_reload_if_stale()` added to `GRUPricePredictor` in `gru_predictor.py`; called at top of `predict()`; emits `MODEL_RELOAD: path=%s mtime=%s (was=%s)` log when mtime advances; log format aligned with `gru_model.py:154-166` so both predictors surface the same grep-able line.
- Bug 2 FIXED: explicit `confidence > 0.0` filter inserted before weighted-sum loop in `handlers/analysis.py:get_aggregated_signal`; dropped count emitted via `AGGREGATOR_CONFIDENCE_FILTER: dropped %d zero-confidence signals` at INFO level; 3 unit tests all passing.
- Bug 3 DOCUMENTED: WSL2 BuildKit hang confirmed as environmental (no code fix possible); RUNBOOK § BuildKit hang already present; INFRA-06 triage outcomes table appended to RUNBOOK with FIXED/FIXED/DOCUMENTED rows.

## Task Commits

| Task | Name | Commit | Type |
|------|------|--------|------|
| Task 2 | Bug 1 — mtime-watching reload in GRUPricePredictor | `8b89cec` | fix |
| Task 3 | Bug 2 — confidence>0 filter + AGGREGATOR_CONFIDENCE_FILTER log | `cfa8e39` | fix |
| Task 4 | Integration regression + RUNBOOK triage outcomes | `8a15755` | fix |
| Metadata | SUMMARY.md (this file) | TBD | docs |

## Files Created/Modified

- `services/ml-prediction-service/app/ml_models/gru_predictor.py` — added `_reload_if_stale()` method + `model_loaded_at: float = 0.0` attribute; called from `predict()`
- `services/ml-prediction-service/app/ml_models/gru_model.py` — log format aligned to `MODEL_RELOAD: path=%s mtime=%s (was=%s)` (was `MODEL_RELOAD: ...` with different arg order)
- `services/ml-prediction-service/tests/test_model_reload.py` (CREATED) — 3 unit tests: mtime change triggers reload, missing file returns False, unchanged mtime is idempotent
- `services/technical-analysis/app/handlers/analysis.py` — confidence filter + AGGREGATOR_CONFIDENCE_FILTER log before weighted-sum loop (lines 91-99)
- `services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py` (CREATED) — 3 unit tests: zero-confidence tuple filtered+log fires, all-positive unchanged, empty list returns confidence=0.5 neutral fallback
- `tests/integration/test_pre_existing_bug_regressions.py` (CREATED) — Bug 1 integration regression; compose-resolved container name + model path; ml-prediction self-bootstrapped with --profile ml if not running
- `RUNBOOK.md` — INFRA-06 Bug Triage Outcomes table appended with 3 rows (FIXED/FIXED/DOCUMENTED)

## Decisions Made

- **Bug 1 inlined vs. new class**: Plan specified a new `model_loader.py` with `ModelLoader` class. Retargeted to inline `_reload_if_stale()` directly in `GRUPricePredictor` because: (1) an identical reload pattern already existed in `gru_model.py:140-166`, (2) creating a separate class for one method adds indirection with no benefit, (3) operator approved Option A (minimal fix) at Task 1 checkpoint.
- **Bug 2 aggregation surface**: Plan targeted `signal_aggregator.py` which does not exist. Retargeted to `handlers/analysis.py` where the actual weighted-sum aggregation lives. Signal shape confirmed as `(label, confidence)` tuples (not objects), so filter uses `weight > 0.0` (where `weight` is the second element of the tuple — the confidence value).
- **Bug 3 no deferral item**: Bug 3 is already fully documented in RUNBOOK (Plan 02-07) + Makefile shortcut (Plan 02-10). No additional deferral note required; triage outcomes table row is sufficient.
- **Integration test fixture design**: `ml-prediction` has `profiles: [ml]` in compose; `bootstrap.sh` does not start it; `bootstrap_stack` fixture would timeout waiting for port 8007. Designed `_ensure_ml_prediction_running()` to start ml-prediction on-demand with `--profile ml`, making the test self-contained without needing to modify bootstrap.sh or conftest.py.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Bug 1 plan referenced model_loader.py (does not exist; retarget to gru_predictor.py)**
- **Found during:** Task 1 (investigation checkpoint; operator approved at Task 1)
- **Issue:** Plan frontmatter `files_modified` listed `services/ml-prediction-service/app/model_loader.py` (new file) and `services/technical-analysis/app/signal_aggregator.py` (non-existent). The actual model reload logic belongs in `gru_predictor.py` (which already mirrors the pattern from `gru_model.py`).
- **Fix:** Inlined `_reload_if_stale()` in `GRUPricePredictor` instead of creating `model_loader.py`.
- **Files modified:** `gru_predictor.py`, `gru_model.py` (log format alignment)
- **Operator-approved:** Yes — Option A approved at Task 1 checkpoint before Task 2 execution.
- **Committed in:** `8b89cec` (Task 2)

**2. [Rule 3 - Blocking] Bug 2 plan referenced signal_aggregator.py (does not exist; retarget to handlers/analysis.py)**
- **Found during:** Task 1 (investigation checkpoint; operator approved at Task 1)
- **Issue:** `services/technical-analysis/app/signal_aggregator.py` does not exist. The aggregation loop lives in `handlers/analysis.py:get_aggregated_signal` (lines 91-102). Signal type is `(label, confidence)` tuples, not objects with `.confidence`.
- **Fix:** Inserted filter before weighted-sum loop in `handlers/analysis.py`; adapted tests to use mock indicators returning tuple signals.
- **Files modified:** `handlers/analysis.py`, `test_signal_aggregator_confidence_zero.py`
- **Operator-approved:** Yes — Option A approved at Task 1 checkpoint.
- **Committed in:** `cfa8e39` (Task 3)

**3. [Rule 1 - Bug] datetime constructor in test used minutes beyond valid range**
- **Found during:** Task 3 test execution
- **Issue:** `datetime(2026, 1, 1, 0, i * 60)` where i=1..9 sets minute to 60-540 — `ValueError: minute must be in 0..59`.
- **Fix:** Changed to `datetime(2026, 1, 1, i)` (uses hour parameter, valid 0-9).
- **Files modified:** `test_signal_aggregator_confidence_zero.py`
- **Committed in:** `cfa8e39` (inline during Task 3 commit)

---

**Total deviations:** 3 (2 operator-approved retargets + 1 auto-fixed test bug)
**Impact on plan:** All deviations necessary — plan assumptions about file structure were wrong; retargets land the same fixes in the correct files.

## Plan Frontmatter Key_links That No Longer Match

The plan's `key_links` section specified patterns that reference the old (non-existent) code paths. These patterns will NOT match in the retargeted implementation:

| Plan pattern | Status | Retargeted pattern |
|---|---|---|
| `model_loader\.get_current_model` | NO MATCH — model_loader.py not created | `_reload_if_stale\b` in `gru_predictor.py` |
| `confidence.*==.*0` | NO MATCH — filter uses `> 0.0` not `== 0` | `weight > 0\.0` in `handlers/analysis.py` |
| `container_name.*ml-prediction` | MATCH — present in `_resolve_compose_value` regex | `_resolve_ml_container_name` in regression test |

## Threat Model Items Closed

| Threat ID | Status |
|---|---|
| T-02-08-01 (model file tampering via mtime watch) | Accepted — mtime watch does not introduce new vector; operator owns model files |
| T-02-08-02 (confidence=0 bypass filter) | Mitigated — filter at aggregation chokepoint in handlers/analysis.py |
| T-02-08-03 (info disclosure via MODEL_RELOAD path in log) | Accepted — path disclosed is non-secret (matches compose volume mount) |
| T-02-08-04 (DoS via mtime syscall on hot path) | Mitigated — one stat() per predict() call; lock only acquired on mtime change |

## Resolved Compose Values Used in Regression Test

Resolved at test runtime by `_resolve_compose_value()` reading `docker-compose.unified.yml`:

| Field | Resolved value |
|---|---|
| `container_name` | `crypto-bot-ml-prediction` |
| Model bind mount (host) | `./services/ml-prediction-service/models` |
| Model bind mount (container) | `/app/models` |
| First model file (at test execution) | `ADAUSDT_60m_gru.keras` → `/app/models/ADAUSDT_60m_gru.keras` |

## Test Counts

| Scope | File | Count |
|---|---|---|
| Unit | `services/ml-prediction-service/tests/test_model_reload.py` | 3 |
| Unit | `services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py` | 3 |
| Integration | `tests/integration/test_pre_existing_bug_regressions.py` | 1 (requires docker) |
| **Total** | | **7** |

## Issues Encountered

- `ml-prediction` is profile-gated (`profiles: [ml]`) in compose; `bootstrap.sh` and `bootstrap_stack` fixture do not start it. Integration test self-bootstraps the service with `--profile ml` to avoid depending on a modified bootstrap.

## Known Stubs

None — all fixes wire live logic (mtime stat, log emit, filter); no hardcoded empty values flowing to test output.

## Next Phase Readiness

- INFRA-06 closed: all 3 bugs accounted for (FIXED/FIXED/DOCUMENTED)
- CD-02 criterion satisfied: regression tests at unit + integration scope
- `gru_predictor.py` now reloads models on retrain without restart; operators no longer need `docker compose restart ml-prediction-service` after `scripts/train_ml.*`
- `handlers/analysis.py` now filters confidence=0 tuples before weighted-sum; stale/disabled indicators cannot pollute signal output

---
*Phase: 02-integration-test-suite-runbook*
*Plan: 08*
*Completed: 2026-05-08*
