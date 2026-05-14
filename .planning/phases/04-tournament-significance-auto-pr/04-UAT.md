---
phase: 04-tournament-significance-auto-pr
phase_number: 04
status: gaps_closed
created: 2026-05-12
completed: 2026-05-12
gaps_closed_on: 2026-05-13
mode: standard
current_test: 7
total_tests: 7
passed: 7
failed: 0
gap_closure_plans:
  - "04-08 (PEP 420 namespace fix) — closed Test 6 root cause"
  - "04-10 (zero-safe baseline sharpe) — closed emergent nan bug surfaced by Test 6"
  - "04-09 (CI wiring) — closed Test 7"
final_evidence:
  container_e2e: "13/13 PASS, 0 SKIP"
  host_grep_gates: "18/18 PASS"
  ci_wiring: "tournament-harness.yml integration-fake-docker + container-integration jobs wired (run blocked by GH Actions billing, operator action)"
---

# Phase 04 — UAT

Validates Phase 04 (`tournament-significance-auto-pr`) deliverables against the 4 ROADMAP success criteria plus the 2 human-needed gates from `04-VERIFICATION.md`.

## Test Plan

| # | Test | Maps To | Status |
|---|------|---------|--------|
| 1 | `tournament open-pr --help` shows the subcommand + key flags | TOURN-06, SC-3 | PASS |
| 2 | `tournament reproduce --help` shows the subcommand + key flags | TOURN-06, D-12 | PASS |
| 3 | Host grep gates: 4 integration files all PASS (18 tests) | SC-2, SC-4 | PASS |
| 4 | Static evidence: zero `5% R²` hits in `app/` | SC-2 (D-13) | PASS |
| 5 | Static evidence: zero `gh pr merge` hits in harness + workflows | SC-4 (CD-10) | PASS |
| 6 | Container e2e suite: 10 tests PASS in `tournament-harness` image | SC-1, SC-3 | **FAIL** |
| 7 | CI wiring: `.github/workflows/tournament-harness.yml` exercises Phase 4 integration tests | CI gate | **FAIL** |

## Findings

### Test 6 FAIL — Container e2e tests skipped, not passing

**Symptom:** `docker compose --profile tournament run --rm -v ./tests:/app/tests:ro -e PYTHONPATH=/app:/opt/ml_retraining tournament-harness pytest tests/integration/test_open_pr_e2e.py tests/integration/test_reproduce_idempotent.py -v` → **10 SKIPPED, 0 PASSED**. Same `_CANONICAL_METRICS_AVAILABLE = False` skip path that runs on host.

**Diagnosis:** Dual `app/__init__.py` collision.

- `/app/app/__init__.py` (tournament-harness, empty, 0 bytes)
- `/opt/ml_retraining/app/__init__.py` (ml-retraining, 212 bytes)

Both are **regular packages**. Python resolves `from app.X` against the first `app` package on `sys.path`. With `PYTHONPATH=/app:/opt/ml_retraining`, `/app/app/` wins; `/opt/ml_retraining/app/` is unreachable via the `app` namespace. Verified inside the running container:

```
sys.path: ['', '/app', '/opt/ml_retraining', ...]
returns_metrics FAIL: ModuleNotFoundError No module named 'app.core'
cpcv_evaluation FAIL: ModuleNotFoundError No module named 'app.core'
sharpe_metrics FAIL: ModuleNotFoundError No module named 'app.sharpe_metrics'
cpcv FAIL: ModuleNotFoundError No module named 'app.cpcv'
ml_retraining contents: ['app']
app contents: ['sharpe_metrics.py', 'core', 'config', 'main.py', 'cpcv.py', '__pycache__', '__init__.py', 'utils', 'database']
```

The 04-06 SUMMARY's claim that "test_open_pr_e2e.py (7 tests) and test_reproduce_idempotent.py (3 tests) all PASS in container" is **not reproducible against the current Dockerfile + image**. ROADMAP SC-1 ("Tournament wraps with a top-3-by-DSR ensemble and a bootstrap p-value vs the persistence baseline at p<0.05 on OOS Sharpe and `dir_acc_corrected`") and SC-3 (draft PR e2e) lack live behavioural proof — only static + unit-level proof exists.

**Severity:** High. The unit suites (79 + 36 tests) cover the components, but the end-to-end orchestration that ROADMAP SC-1 / SC-3 demand is not verified end-to-end.

**Fix options (one of, not all):**

- **A. PEP 420 namespace packages.** Delete both `services/tournament-harness/app/__init__.py` and `services/ml-retraining-service/app/__init__.py`. `app.core`, `app.sharpe_metrics`, `app.cpcv`, and tournament-harness's `app.pr`, `app.significance`, `app.runner` merge automatically as a namespace package. Cleanest; matches the documented `PYTHONPATH=/app:/opt/ml_retraining` design.
- **B. Rename ml-retraining root.** Change `/opt/ml_retraining/app/` → `/opt/ml_retraining/ml_app/`, update the 4 imports in `app/runner/metrics_bridge.py` from `app.core` → `ml_app.core` etc. Explicit, no namespace tricks. Larger diff.
- **C. Drop the cross-service vendoring entirely.** Copy `returns_metrics.py`, `sharpe_metrics.py`, `cpcv.py`, `cpcv_evaluation.py` into a shared package consumed by both services. Highest cost, only worth it if Phase 5 expands cross-service sharing.

Option **A** is the lowest-risk and matches the original design intent.

### Test 7 FAIL — CI does not exercise Phase 4 integration tests

**Symptom:** `.github/workflows/tournament-harness.yml` integration-fake-docker step (lines 81-82) invokes only:

```
pytest tests/integration/test_tourn07_grep_gate.py -v
pytest tests/integration/test_orchestrator_with_fake_docker.py -v
```

Six Phase 4 integration files are not listed:

- `test_no_legacy_r2_criterion.py`
- `test_no_auto_merge.py`
- `test_klines_filter_required.py`
- `test_no_parallel_metric_reimplementations.py`
- `test_open_pr_e2e.py`
- `test_reproduce_idempotent.py`

ROADMAP SC-2 (no `>5% R²` win criterion) and SC-4 (no `gh pr merge`) invariants run on developer hosts but are not enforced on PRs.

**Severity:** Medium. Unit-test job does exercise `test_pr_gh.py::test_no_gh_pr_merge_in_module`, so CD-10 has partial CI coverage. D-13 (no `>5% R²`) and B1 (klines `is_mainnet`) have **zero** CI enforcement.

**Fix:** Extend `.github/workflows/tournament-harness.yml` integration-fake-docker step to:

```
pytest tests/integration/test_tourn07_grep_gate.py tests/integration/test_orchestrator_with_fake_docker.py tests/integration/test_no_legacy_r2_criterion.py tests/integration/test_no_auto_merge.py tests/integration/test_klines_filter_required.py tests/integration/test_no_parallel_metric_reimplementations.py -v
```

Or use a directory glob with deselect for the container-only ones:

```
pytest tests/integration/ -v --deselect tests/integration/test_open_pr_e2e.py --deselect tests/integration/test_reproduce_idempotent.py --deselect tests/integration/test_end_to_end_tournament.py
```

The `--deselect` form auto-picks up future grep-gate tests without further YAML edits.

## Gap Summary

Two fix plans needed for `/gsd-plan-phase --gaps`:

| Plan | Scope | Files | Priority |
|------|-------|-------|----------|
| 04-08 | PEP 420 namespace pkg fix: delete both `app/__init__.py`; verify e2e + reproduce tests PASS in container | `services/tournament-harness/app/__init__.py` (delete), `services/ml-retraining-service/app/__init__.py` (delete) | High |
| 04-09 | CI wiring: extend `tournament-harness.yml` integration-fake-docker step to invoke all 6 Phase 4 integration test files | `.github/workflows/tournament-harness.yml` | Medium |

After both fixes ship, re-run tests 6 + 7 to confirm Phase 04 fully verified.
