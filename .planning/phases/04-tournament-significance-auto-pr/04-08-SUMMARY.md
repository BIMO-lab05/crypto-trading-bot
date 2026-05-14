---
phase: 04-tournament-significance-auto-pr
plan: 08
subsystem: tournament-harness
tags: [pep420, namespace-package, docker, ml-retraining, gap-closure]
status: partial
gap_closure: true
closes_gaps:
  - "04-UAT.md Test 6 root cause (dual app/__init__.py collision) — RESOLVED"
remaining_gaps:
  - "sharpe_lift = nan when baseline is persistence (all-zero log-returns) — PSR(zeros)/std=0 returns nan; pre-existing bug exposed by skip removal. Needs new gap plan 04-10."
  - "test_save_model_writes_scalers_pkl_with_expected_keys uses identity check on a serialized MinMaxScaler — pre-existing, unrelated to this plan."
requires:
  - "Plan 04-06 left container-only e2e tests stubbed/skipped"
  - "Plan 03-06 introduced PYTHONPATH=/app:/opt/ml_retraining design"
provides:
  - "PEP 420 namespace package: app.* resolves across /app/app and /opt/ml_retraining/app inside tournament-harness container"
  - "test_canonical_metrics_importable.py — non-bypassable regression test for the namespace-merge invariant"
  - "app/_version.py — package metadata module replacing the deleted app/__init__.py body"
affects:
  - "services/tournament-harness/app/runner/metrics_bridge.py (canonical imports now resolve in-container)"
  - "services/ml-retraining-service/app/main.py (4 call sites switched from __import__('app').__version__ to app._version)"
tech-stack:
  added: []
  patterns: ["PEP 420 implicit namespace packages for cross-service code sharing"]
key-files:
  created:
    - "services/tournament-harness/tests/integration/test_canonical_metrics_importable.py"
    - "services/ml-retraining-service/app/_version.py"
  modified:
    - "services/ml-retraining-service/app/main.py"
  deleted:
    - "services/tournament-harness/app/__init__.py"
    - "services/ml-retraining-service/app/__init__.py"
decisions:
  - "Used PEP 420 namespace packages (04-UAT.md Option A) — lowest-risk match for documented PYTHONPATH design"
  - "Moved ml-retraining package metadata to dedicated app/_version.py rather than restoring __init__.py — keeps app/ a namespace package"
metrics:
  duration_minutes: 95
  completed: "2026-05-12"
  tasks_completed: 3
  tasks_total: 3
---

# Phase 04 Plan 08: PEP 420 Namespace Package Fix — Summary

**One-liner:** Deleted both top-level `app/__init__.py` files so `services/tournament-harness/` and `services/ml-retraining-service/` merge under a single PEP 420 namespace package; canonical metric chain now resolves inside the tournament-harness container, 8 of 10 previously-skipped tests pass, 3 new regression tests guard against silent re-introduction.

## Status: **PARTIAL** — namespace-merge invariant fully achieved; 2 downstream tests fail on a pre-existing `sharpe_lift = nan` bug surfaced by the skip removal.

## Outcomes vs Plan Acceptance Criteria

| # | Acceptance Criterion | Status |
|---|----------------------|--------|
| 1 | `services/tournament-harness/app/__init__.py` deleted | PASS (commit `e022204`) |
| 2 | `services/ml-retraining-service/app/__init__.py` deleted | PASS (commit `e022204`) |
| 3 | Sub-package `__init__.py` files retained (`app/runner`, `app/core`, etc.) | PASS |
| 4 | Rebuilt image: `_CANONICAL_METRICS_AVAILABLE = True` | PASS (image `0b2940892f02`) |
| 5 | 10 previously-skipped tests now PASS in container | **PARTIAL** — 8/10 PASS, 2 FAIL (`sharpe_lift = nan`, downstream bug) |
| 6 | New regression test catches silent re-introduction | PASS (3/3 PASS in-container; SKIP on host as designed) |
| 7 | `_CANONICAL_METRICS_AVAILABLE` invariant test exists | PASS |
| 8 | ml-retraining-service unit tests remain green | PASS (167 passed / 1 failed, where the 1 failure is pre-existing and unrelated) |

**Plan core invariant met:** the dual regular-package collision is gone. `app.__path__` now lists both `/app/app` and `/opt/ml_retraining/app` inside the rebuilt image (proven by `test_app_path_includes_both_trees_in_container`).

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `e022204` | fix | Delete top-level `app/__init__.py` in both service trees (Task 1) |
| `a7437ef` | fix | Restore ml-retraining `__version__` via `app/_version.py` (Rule 1 deviation — see below) |
| `e2337e3` | test | Container-aware regression test for PEP 420 namespace merge (Task 3) |

## Verification Output

### In-container e2e suite (Task 3 verify step)

```
docker compose -f docker-compose.unified.yml --profile tournament run --rm \
  -v "$(pwd)/services/tournament-harness/tests:/app/tests:ro" \
  -e PYTHONPATH=/app:/opt/ml_retraining \
  tournament-harness \
  pytest tests/integration/test_open_pr_e2e.py \
         tests/integration/test_reproduce_idempotent.py \
         tests/integration/test_canonical_metrics_importable.py -v

================== 2 failed, 11 passed in 76.96s (0:01:16) ===================
```

**Breakdown:**

- `test_open_pr_e2e.py`: **5 PASS, 2 FAIL**
  - PASS: `test_open_pr_smoke_no_win_path`, `test_open_pr_records_git_sha_consistently`, `test_open_pr_count_tournaments_reflects_state_at_call_time`, `test_open_pr_imports_real_predict_fn_factory`, `test_open_pr_writes_no_partial_artifacts`
  - FAIL: `test_open_pr_smoke_round_trip_winner`, `test_open_pr_gh_argv_shape_under_real_path`
- `test_reproduce_idempotent.py`: **3/3 PASS** (`test_reproduce_round_trip_idempotent`, `test_reproduce_detects_drift`, `test_reproduce_round_trip_no_real_runner_imports`)
- `test_canonical_metrics_importable.py` (NEW): **3/3 PASS**

**Zero SKIPS** — the namespace-merge fix worked. Tests that previously couldn't even execute now run and surface a separate downstream bug.

### Canonical-chain availability (Task 2 verify step)

```
$ docker compose ... run ... tournament-harness python -c \
    "from app.runner.metrics_bridge import _CANONICAL_METRICS_AVAILABLE; print(_CANONICAL_METRICS_AVAILABLE)"
CANONICAL_METRICS_AVAILABLE = True
```

### Image rebuild (Task 2)

```
$ DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml --profile tournament \
    build --no-cache tournament-harness
...
Successfully built 0b2940892f02
Successfully tagged crypto-trading-bot-tournament-harness:latest
```

### ml-retraining unit suite (Task 3 acceptance criterion 8)

```
$ pytest services/ml-retraining-service/tests/ -v
======================== 1 failed, 167 passed in 12.05s ========================
```

The 1 failure is `test_save_model_writes_scalers_pkl_with_expected_keys` which uses an `is` identity assertion on a serialize/deserialize round-trip of a MinMaxScaler. Identity (`is`) never holds across a serialization round-trip (a new instance is returned on load) — pre-existing bug, unrelated to this plan. Logged to deferred-items below.

## Deviations from Plan

### [Rule 1 — Bug introduced by Task 1] Restore ml-retraining `__version__` via `app/_version.py`

- **Found during:** Task 3 verification step (running `pytest services/ml-retraining-service/tests/` per acceptance criterion 8).
- **Issue:** Plan 04-08's pre-flight grep used patterns `from app import` / `^import app$` / `app.__version__` / `app.__service_name__` and reported zero callers. It MISSED the four dynamic-lookup call sites at lines 44, 123, 153, 497 of `services/ml-retraining-service/app/main.py` that use the literal `__import__("app").__version__`. After Task 1's `__init__.py` deletion, these raised `AttributeError: module 'app' has no attribute '__version__'` and broke `test_health`, `test_detailed_health`, `test_service_status`.
- **Fix:** Created `services/ml-retraining-service/app/_version.py` holding `__version__ = "1.0.0"` and `__service_name__ = "ml-retraining-service"`. Updated the four call sites in `app/main.py` to `from app._version import __version__ as _service_version` (function-local imports — keeps the import surface minimal and matches the original lazy-lookup pattern). Cannot re-introduce `app/__init__.py` because that would defeat Task 1's namespace merge.
- **Files modified:** `services/ml-retraining-service/app/_version.py` (new), `services/ml-retraining-service/app/main.py` (4 call sites)
- **Commit:** `a7437ef`
- **Verified:** ml-retraining-service test suite restored from 4-failed to 1-failed (where the remaining 1 is the pre-existing serialize-identity bug).

### No other deviations from the written tasks.

## Remaining Gaps — Recommend New Plans

### Gap A: `sharpe_lift = nan` in win-gate when baseline is persistence (zeros)

- **Where:** `services/tournament-harness/app/pr/open_pr.py:205` computes `sharpe_lift = ens_sharpe - base_sharpe` where `base_sharpe = float(probabilistic_sharpe_ratio(baseline_log_ret, benchmark_sr=0.0))` and `baseline_log_ret = np.zeros_like(actual_log_ret)`. PSR on an all-zero series divides by `std(SR) = 0` and returns `nan`.
- **Impact:** `win_gate` then fails for every symbol with `gate_failure_reasons: ['sharpe_lift_non_positive']`, so no symbol ever wins, even with `drift=0.005`. The 2 in-container test FAILs (`test_open_pr_smoke_round_trip_winner`, `test_open_pr_gh_argv_shape_under_real_path` — depends on winner state via `winner_run_dir` fixture) both bottom out on this.
- **Why not fixed here:** Rule 4 (architectural — touches metric-aggregation semantics central to ROADMAP SC-1 / SC-3). Fixing inline would scope-creep 04-08 into 04-10's territory. The 04-UAT explicitly flagged this risk: the 04-06 SUMMARY's claim of "all 10 PASS in container" was based on a build that never actually ran the tests (they were SKIPPED throughout). 04-08 closes the SKIP gap; the underlying logic gap is fresh ground.
- **Recommendation:** File new gap plan **04-10** to define how the persistence baseline's Sharpe is computed (proposed: when `baseline_log_ret.std() == 0`, return `base_sharpe = 0.0` rather than `nan`, with explicit handling in the win-gate). Or alternative: use `ens_sharpe` magnitude directly as the lift gate when baseline is the trivial persistence path.

### Gap B (deferred — pre-existing, low priority)

- `test_save_model_writes_scalers_pkl_with_expected_keys` asserts `payload["price_scaler"] is scaler_y` against a serialize-and-reload of the scaler. Identity (`is`) never holds across that round-trip. Change assertion to `np.allclose` over the scaler params, or use `type(payload["price_scaler"]) is type(scaler_y)`. Predates Phase 04.

## Hand-off Note for Plan 04-09 (CI wiring)

`services/tournament-harness/tests/integration/test_canonical_metrics_importable.py` MUST be wired into the **container-integration** CI job, NOT the host-integration job. The test self-skips on host (the `_in_tournament_harness_container()` heuristic checks for both `/app/app` and `/opt/ml_retraining/app` as absolute paths). Wiring it into host pytest would cause silent SKIP and defeat the regression guard.

Recommended pytest invocation pattern for 04-09 container job:

```yaml
pytest tests/integration/test_open_pr_e2e.py \
       tests/integration/test_reproduce_idempotent.py \
       tests/integration/test_canonical_metrics_importable.py \
       -v
```

(Note: until Gap A is resolved by Plan 04-10, the 2 `test_open_pr_e2e.py` FAILs will continue to surface in this job. That's the intended honest signal — keeping these as FAILs rather than re-skipping them is what makes the next gap visible.)

## Threat Surface Update

No new threat surface introduced by this plan. The PEP 420 namespace-merge is bounded to the two trusted service trees both built into the same Docker image. The `T-04-08-01` and `T-04-08-02` mitigations from the plan threat register are implemented by the new regression test.

## Self-Check: PASSED

Files verified to exist:

- `services/tournament-harness/tests/integration/test_canonical_metrics_importable.py` — FOUND
- `services/ml-retraining-service/app/_version.py` — FOUND
- `services/tournament-harness/app/__init__.py` — confirmed MISSING (expected)
- `services/ml-retraining-service/app/__init__.py` — confirmed MISSING (expected)

Commits verified in `git log`:

- `e022204` (Task 1: delete __init__.py) — FOUND
- `a7437ef` (Rule 1 fix: _version.py) — FOUND
- `e2337e3` (Task 3: regression test) — FOUND
