---
phase: 04-tournament-significance-auto-pr
plan: 10
subsystem: tournament-harness
tags: [gap-closure, significance, sharpe, persistence-baseline, win-gate]
status: complete
gap_closure: true
closes_gaps:
  - "04-08-SUMMARY.md Gap A — sharpe_lift = nan when baseline is the D-04 persistence (zero-variance) series; all 13 in-container e2e tests now PASS"
remaining_gaps:
  - "test_save_model_writes_scalers_pkl_with_expected_keys uses identity check on a serialized MinMaxScaler — pre-existing, unrelated to Phase 04; predates this phase"
requires:
  - "Plan 04-08 unmuted the in-container e2e suite by deleting the dual app/__init__.py collision"
provides:
  - "app.pr.open_pr._zero_safe_baseline_sharpe — module-private guard returning 0.0 for zero-variance baselines"
  - "test_significance_zero_variance_baseline.py — 5-test invariant suite pinning the contract"
  - "13/13 in-container e2e tests PASSING (was 11/13)"
affects:
  - "services/tournament-harness/app/pr/open_pr.py (call site at line ~203 now routes through the guard)"
  - "Win-gate semantics for the persistence baseline (PSR shortcut only — candidate side untouched)"
tech-stack:
  added: []
  patterns: ["zero-variance short-circuit for ratio metrics whose canonical implementation returns NaN on degenerate input"]
key-files:
  created:
    - "services/tournament-harness/tests/unit/test_significance_zero_variance_baseline.py"
  modified:
    - "services/tournament-harness/app/pr/open_pr.py"
  deleted: []
decisions:
  - "Option A (helper short-circuit) chosen over altering canonical sharpe_metrics.probabilistic_sharpe_ratio — keeps the canonical PSR/DSR chain byte-identical so other consumers (ml-retraining-service, CPCV evaluator) see unchanged semantics. T-04-10-01 mitigation pinned by test_zero_safe_baseline_sharpe_returns_psr_on_nonzero."
  - "var_eps = 1e-12 floor (not strict std == 0.0) catches floating-point drift in persistence-baseline construction. test_zero_safe_baseline_sharpe_handles_near_zero_variance pins this at 1e-15."
  - "Candidate-side PSR path unchanged — fix never masks a no-edge candidate. test_existing_failure_reason_semantics_preserved pins this invariant."
metrics:
  duration_minutes: 25
  completed: "2026-05-12"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 04 Plan 10: Zero-Safe Baseline Sharpe Guard — Summary

**One-liner:** Added a module-private helper `_zero_safe_baseline_sharpe` to short-circuit the persistence baseline's PSR computation to 0.0 when variance is below 1e-12; the lift `ens_sharpe - base_sharpe` is now finite, all 13 in-container e2e tests PASS (was 11/13), and the canonical PSR/DSR chain plus the bootstrap kernel remain byte-identical.

## Status: **COMPLETE** — Gap A from 04-08-SUMMARY closed; all acceptance criteria mechanical and met.

## Outcomes vs Plan Acceptance Criteria

| # | Acceptance Criterion | Status |
|---|----------------------|--------|
| 1 | `_zero_safe_baseline_sharpe` defined and used at `open_pr.py:~203` | PASS (commit `6bcb54b`) |
| 2 | `test_significance_zero_variance_baseline.py` created with 5 tests, all PASS | PASS — 5/5 on host AND in-container |
| 3 | All 13 in-container e2e tests PASS (zero FAIL, zero SKIP) | PASS — `13 passed in 74.43s` |
| 4 | `test_open_pr_smoke_round_trip_winner` reports `n_winning_symbols >= 1` for `drift=0.005` | PASS — `n_winning_symbols=5` |
| 5 | `test_open_pr_gh_argv_shape_under_real_path` captures exactly one `gh pr create --draft` invocation | PASS |
| 6 | `services/tournament-harness/app/significance/bootstrap.py` and `services/ml-retraining-service/app/sharpe_metrics.py` are byte-identical (`git diff` empty) | PASS — `git diff HEAD` for both paths returns empty |
| 7 | Existing harness unit suite shows zero new failures | PASS — 213 passed (was 208 + 5 new) |
| 8 | SUMMARY documents Plan 04-09 dependency reorder | See Hand-off section below |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `111d6db` | test | RED — 5 failing tests for `_zero_safe_baseline_sharpe` contract |
| `6bcb54b` | fix | GREEN — implement the helper, swap the call site at open_pr.py line ~203 |

## Verification Output

### In-container e2e suite (Task 2)

```
$ docker compose -f docker-compose.unified.yml --profile tournament run --rm \
    -v "$(pwd)/services/tournament-harness/tests:/app/tests:ro" \
    -e PYTHONPATH=/app:/opt/ml_retraining \
    tournament-harness \
    pytest tests/integration/test_open_pr_e2e.py \
           tests/integration/test_reproduce_idempotent.py \
           tests/integration/test_canonical_metrics_importable.py -v

tests/integration/test_open_pr_e2e.py::test_open_pr_smoke_round_trip_winner PASSED [  7%]
tests/integration/test_open_pr_e2e.py::test_open_pr_smoke_no_win_path PASSED [ 15%]
tests/integration/test_open_pr_e2e.py::test_open_pr_records_git_sha_consistently PASSED [ 23%]
tests/integration/test_open_pr_e2e.py::test_open_pr_gh_argv_shape_under_real_path PASSED [ 30%]
tests/integration/test_open_pr_e2e.py::test_open_pr_count_tournaments_reflects_state_at_call_time PASSED [ 38%]
tests/integration/test_open_pr_e2e.py::test_open_pr_imports_real_predict_fn_factory PASSED [ 46%]
tests/integration/test_open_pr_e2e.py::test_open_pr_writes_no_partial_artifacts PASSED [ 53%]
tests/integration/test_reproduce_idempotent.py::test_reproduce_round_trip_idempotent PASSED [ 61%]
tests/integration/test_reproduce_idempotent.py::test_reproduce_detects_drift PASSED [ 69%]
tests/integration/test_reproduce_idempotent.py::test_reproduce_round_trip_no_real_runner_imports PASSED [ 76%]
tests/integration/test_canonical_metrics_importable.py::test_canonical_metrics_available_in_container PASSED [ 84%]
tests/integration/test_canonical_metrics_importable.py::test_app_is_namespace_package_in_container PASSED [ 92%]
tests/integration/test_canonical_metrics_importable.py::test_app_path_includes_both_trees_in_container PASSED [100%]

======================== 13 passed in 74.43s (0:01:14) =========================
```

**Delta vs Plan 04-08 baseline:** was `2 failed, 11 passed` → now `13 passed, 0 failed, 0 skipped`. The two formerly-failing tests (`test_open_pr_smoke_round_trip_winner` + `test_open_pr_gh_argv_shape_under_real_path`) both PASS. Full log: `/tmp/04-10-e2e.log`.

### significance.json from the winner fixture (drift=0.005)

Captured in-container from the winner test's tmpdir:

```json
{
  "schema_version": 1,
  "tournament_id": "t-04-01-test",
  "baseline": "persistence",
  "aggregation": "mean_log_returns",
  "git_sha": "FIXED_SHA",
  "evaluated_at": "2026-05-12T22:40:57.494286+00:00",
  "tournaments_evaluated_count": 1,
  "n_winning_symbols": 5,
  "per_symbol": {
    "BTCUSDT": {
      "n_members": 3,
      "sharpe_pvalue": 9.999000099990002e-05,
      "sharpe_lift": 1.0,
      "dir_acc_pvalue": 9.999000099990002e-05,
      "dir_acc_lift": 1.62,
      "n_oos_bars": 200,
      "block_size": 14,
      "n_resamples": 10000,
      "bootstrap_seed": 357592374,
      "win_gate_passed": true,
      "gate_failure_reasons": []
    },
    ...
  }
}
```

**Before the fix:** `sharpe_lift: NaN`, `n_winning_symbols: 0`, `gate_failure_reasons: ["sharpe_lift_non_positive"]` for every symbol (see `/tmp/04-08-e2e.log` for the failing-state capture in Plan 04-08).

**After the fix:** `sharpe_lift: 1.0` (finite — PSR(candidate)=1.0 − base_sharpe=0.0 = 1.0), `n_winning_symbols: 5`, `win_gate_passed: true` for every symbol. The full per-symbol block is identical in shape to the pre-fix output — only the `sharpe_lift` field changes from nan to a finite value, and the boolean/list pass-through fields flip accordingly.

### New unit tests (in-container)

```
$ docker compose ... tournament-harness pytest tests/unit/test_significance_zero_variance_baseline.py -v
collected 5 items

tests/unit/test_significance_zero_variance_baseline.py::test_zero_safe_baseline_sharpe_returns_zero_on_zeros PASSED [ 20%]
tests/unit/test_significance_zero_variance_baseline.py::test_zero_safe_baseline_sharpe_returns_psr_on_nonzero PASSED [ 40%]
tests/unit/test_significance_zero_variance_baseline.py::test_zero_safe_baseline_sharpe_handles_near_zero_variance PASSED [ 60%]
tests/unit/test_significance_zero_variance_baseline.py::test_sharpe_lift_finite_with_persistence_baseline PASSED [ 80%]
tests/unit/test_significance_zero_variance_baseline.py::test_existing_failure_reason_semantics_preserved PASSED [100%]

============================== 5 passed in 1.45s ===============================
```

### Full host unit suite (regression scan)

```
$ pytest services/tournament-harness/tests/unit/ -v
============================= 213 passed in 13.08s =============================
```

213 passed (was 208 in 04-08 + 5 new = 213, zero new failures, zero pre-existing failures broken). Full log: `/tmp/04-10-unit.log`.

### Bootstrap kernel + canonical PSR untouched

```
$ git diff HEAD services/tournament-harness/app/significance/bootstrap.py services/ml-retraining-service/app/sharpe_metrics.py
(empty — zero diff)
```

Acceptance criterion 6 met. Plan 04-10's threat-register entry T-04-10-03 (bootstrap reproducibility) holds.

### Image rebuild (Task 2 step 1)

```
$ DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml --profile tournament build tournament-harness
...
Successfully built 8713df065064
Successfully tagged crypto-trading-bot-tournament-harness:latest
```

## Deviations from Plan

None. The plan was followed exactly — no Rule 1/2/3/4 deviations needed. The only minor judgement call was the test-file skip guard (`pytest.importorskip("app.sharpe_metrics")`) borrowed from `test_runner_metrics_bridge.py`'s pattern; it's a no-op on host because the harness conftest's path shim makes `app.sharpe_metrics` importable, so all 5 tests run on host AND in-container. Logged here as a design note, not a deviation.

## Threat Surface Update

Threat register entries from the plan (T-04-10-01, T-04-10-02, T-04-10-03) all mitigate as specified:

- **T-04-10-01** (Tampering — semantic shortcut bypassing canonical PSR): pinned by `test_zero_safe_baseline_sharpe_returns_psr_on_nonzero` — on any non-zero baseline, the helper MUST return exactly what `probabilistic_sharpe_ratio` returns. A future PR that lifted the variance gate or special-cased the candidate side would trip this test.
- **T-04-10-02** (Information disclosure — `gate_failure_reasons` schema): `sharpe_lift_non_positive` now covers both (a) lift ≤ 0 and (b) lift = nan (e.g. flat candidate). No new disclosure surface; PR body and leaderboard markdown surface area unchanged.
- **T-04-10-03** (Repudiation — bootstrap kernel reproducibility): `git diff HEAD` for `bootstrap.py` and `sharpe_metrics.py` is empty. Bootstrap seed derivation, geometric block resampling, and p-value smoothing are bit-for-bit identical to Plan 04-08.

No new threat surface introduced. The change is internal to one module's pure-Python metric-aggregation block.

## Hand-off Note for Plan 04-09 (CI wiring)

**Action required for the orchestrator:** Plan 04-09's CI-wiring work can now proceed against a fully-green in-container suite. Its `depends_on` field should be amended from `[08]` to `[08, 10]` before it executes. The recommended pytest invocation in 04-08-SUMMARY's hand-off (lines 158-164) is now backed by `13 passed, 0 failed, 0 skipped` so the GHA YAML can list those three test files without any `xfail` or `--deselect` workarounds for Gap A.

If the orchestrator runs wave assignment from `depends_on` edges, Plan 04-09 should move from Wave 3 (assigned earlier on the assumption Gap A would remain open) to a Wave that includes Plan 04-10. Concretely:

- **Old:** `04-09 depends_on: [08]`, Wave 3
- **New:** `04-09 depends_on: [08, 10]`, Wave 3 (or higher if other gap-closure plans land)

This is a coordination note — Plan 04-10 does NOT edit Plan 04-09's frontmatter (separation of concerns). The orchestrator or a follow-up `gsd-roadmapper` pass should make the edit.

## Self-Check: PASSED

Files verified to exist:

- `services/tournament-harness/tests/unit/test_significance_zero_variance_baseline.py` — FOUND
- `services/tournament-harness/app/pr/open_pr.py` — modified; `_zero_safe_baseline_sharpe` symbol resolves on host AND in-container

Commits verified in `git log`:

- `111d6db` (test RED) — FOUND
- `6bcb54b` (fix GREEN) — FOUND

Bootstrap + canonical PSR untouched: `git diff HEAD services/tournament-harness/app/significance/bootstrap.py services/ml-retraining-service/app/sharpe_metrics.py` returns empty — VERIFIED.

In-container e2e: `13 passed in 74.43s (0:01:16)` — VERIFIED via `/tmp/04-10-e2e.log`.
