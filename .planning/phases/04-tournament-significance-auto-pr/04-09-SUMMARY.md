---
phase: 04-tournament-significance-auto-pr
plan: 09
subsystem: ci
tags: [ci, gha, integration-tests, gap-closure, phase-4]
status: complete
gap_closure: true
closes_gaps:
  - "04-UAT.md Test 7 FAIL — Phase 4 integration tests not exercised on PRs"
remaining_gaps: []
requires:
  - "Plan 04-08 PEP 420 namespace fix (image now resolves canonical metric chain)"
  - "Plan 04-10 zero-safe baseline sharpe guard (in-container e2e suite at 13/13 PASS)"
provides:
  - "CI enforcement on every PR for: D-13 (no >5% R² win criterion), CD-10 (no gh pr merge), B1 (klines is_mainnet), TOURN-07 (no parallel metric reimpl)"
  - "container-integration GHA job — builds tournament-harness image fresh, runs 3 container-only tests with 0-SKIP guard"
  - "Future-proof glob+ignore pattern: new grep gates auto-attach without YAML edits"
affects:
  - ".github/workflows/tournament-harness.yml (5 jobs total)"
tech-stack:
  added: []
  patterns: ["pytest dir-glob + --ignore (cwd-relative) for CI test routing"]
key-files:
  created:
    - ".planning/phases/04-tournament-significance-auto-pr/04-09-PLAN.md (newly tracked)"
    - ".planning/phases/04-tournament-significance-auto-pr/04-09-SUMMARY.md (this file)"
  modified:
    - ".github/workflows/tournament-harness.yml (+59 / -2)"
  deleted: []
decisions:
  - "Used pytest --ignore (cwd-relative) over --deselect (which requires rootdir-relative node IDs) for the integration-fake-docker job — cleaner read, matches the plan author's intended cwd-relative path form, and avoids the silent-mismatch footgun documented in the YAML comment"
  - "Single per-job image build (no cross-job layer caching) for container-integration — solo operator, low PR frequency, ~2-5min rebuild acceptable; future optimization via docker/build-push-action@v5 is out of scope"
  - "0-SKIP grep guard (grep -E '^[0-9]+ skipped' + exit 1) is the load-bearing CI assertion for Gap 1 regression detection — pairs with Plan 04-08's test_canonical_metrics_importable.py for defence in depth"
metrics:
  duration_minutes: 35
  completed: "2026-05-12"
  tasks_completed: 3
  tasks_total: 3
---

# Phase 04 Plan 09: CI Wiring for Phase 4 Integration Tests — Summary

**One-liner:** Extended `.github/workflows/tournament-harness.yml` so every PR runs all 4 Phase 4 host-runnable grep gates (18 tests) via the dir-glob `integration-fake-docker` job AND the 3 container-only tests (13 tests) via a NEW `container-integration` job; 04-UAT.md Test 7 FAIL closed.

## Status: **COMPLETE** — all acceptance criteria met; both new/changed jobs verified locally.

## Outcomes vs Plan Acceptance Criteria

| # | Acceptance Criterion | Status |
|---|----------------------|--------|
| 1 | `integration-fake-docker` runs all 4 Phase 4 grep gates via dir-glob | PASS — `tests/integration/ -v --ignore=...` |
| 2 | `container-integration` job runs the 3 container-only tests | PASS — needs `unit-tests`, no schedule guard |
| 3 | `integration-real-stack`'s `test_end_to_end_tournament.py` invocation preserved | PASS — line 161 unchanged |
| 4 | Dir-glob + `--ignore` pattern; new grep gates auto-attach | PASS — verified via collect-only |
| 5 | YAML comment documents the invariant | PASS — 5-line comment block above the step |
| 6 | YAML parses cleanly (`yaml.safe_load` exits 0) | PASS |
| 7 | Host smoke: 0 fails, 0 skips on integration-fake-docker surface | PASS — **26 passed in 5.52s** |
| 8 | Container smoke: 13/13 PASS in container-integration surface | PASS — **13 passed in 73.80s** |

## Final Workflow Job Chain

| Job | needs | Triggered by | Phase 4 invariants enforced |
|-----|-------|--------------|-----------------------------|
| `tourn07-grep-gate` | — | every PR + push to main | TOURN-07 (head-of-DAG fast fail) |
| `unit-tests` | `tourn07-grep-gate` | every PR + push to main | Unit suite (incl. test_pr_gh::test_no_gh_pr_merge_in_module) |
| `integration-fake-docker` | `unit-tests` | every PR + push to main | D-13 (no >5% R²), CD-10 (no gh pr merge), B1 (klines is_mainnet), TOURN-07 (no parallel metric reimpl) |
| `container-integration` (NEW) | `unit-tests` | every PR + push to main | SC-1 (PSR/DSR persistence baseline e2e), SC-3 (draft PR e2e), Plan 04-08 namespace-merge regression |
| `integration-real-stack` | `unit-tests` | schedule + workflow_dispatch only | SC-1 e2e against real postgres/timescaledb (Phase 3 nightly) |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `37a2d6a` | ci | Task 1 + Task 2 + 04-09-PLAN.md frontmatter bump in one commit |

Single-commit form is consistent with the plan's Task 3 commit message template, and 04-10-SUMMARY explicitly left the 04-09 frontmatter bump for the executor.

## Verification Output

### Host smoke (integration-fake-docker surface)

```
$ cd services/tournament-harness && PYTHONPATH=... pytest tests/integration/ -v \
    --ignore=tests/integration/test_open_pr_e2e.py \
    --ignore=tests/integration/test_reproduce_idempotent.py \
    --ignore=tests/integration/test_canonical_metrics_importable.py \
    --ignore=tests/integration/test_end_to_end_tournament.py

tests/integration/test_klines_filter_required.py .....                   [ 19%]
tests/integration/test_no_auto_merge.py ....                             [ 34%]
tests/integration/test_no_legacy_r2_criterion.py .....                   [ 53%]
tests/integration/test_no_parallel_metric_reimplementations.py ....      [ 69%]
tests/integration/test_orchestrator_with_fake_docker.py .....            [ 88%]
tests/integration/test_tourn07_grep_gate.py ...                          [100%]

============================== 26 passed in 5.52s ==============================
```

Composition: 18 Phase 4 grep-gate tests (5+4+5+4) + 8 Phase 3 host-integration tests (5+3) = 26. Zero skips, zero deselected, zero fails.

### Container smoke (container-integration surface)

```
$ docker compose -f docker-compose.unified.yml --profile tournament run --rm \
    -v "$(pwd)/services/tournament-harness/tests:/app/tests:ro" \
    -e PYTHONPATH=/app:/opt/ml_retraining \
    tournament-harness \
    pytest tests/integration/test_open_pr_e2e.py \
           tests/integration/test_reproduce_idempotent.py \
           tests/integration/test_canonical_metrics_importable.py -v

======================== 13 passed in 73.80s (0:01:13) =========================
```

Composition: 7 e2e + 3 reproduce + 3 namespace-regression = 13. Matches 04-10-SUMMARY baseline exactly (image `8713df065064`). Zero skips — confirms Plan 04-08 namespace-merge invariant intact + Plan 04-10 zero-safe sharpe guard intact.

### YAML structural verification

```
$ python3 -c "import yaml; data = yaml.safe_load(open('.github/workflows/tournament-harness.yml')); print(sorted(data['jobs'].keys()))"
['container-integration', 'integration-fake-docker', 'integration-real-stack', 'tourn07-grep-gate', 'unit-tests']
```

`integration-real-stack`'s schedule guard preserved (`if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'`); `test_end_to_end_tournament.py` invocation intact (line 161). Verified via `grep -n test_end_to_end_tournament` → 2 hits: line 90 (in the `--ignore` list of `integration-fake-docker`) and line 161 (in the run step of `integration-real-stack`).

## Deviations from Plan

### [Rule 1 — Bug in plan's literal YAML] `--deselect` form silently matches nothing

- **Found during:** Task 1 host smoke verification.
- **Issue:** Plan specified `--deselect tests/integration/X.py` (cwd-relative path). pytest's rootdir is the repo root via the repo-level `pytest.ini`, so collected node IDs are `services/tournament-harness/tests/integration/...`. The cwd-relative `--deselect` argument silently matched zero tests: `pytest --collect-only` reported 40 tests collected (the same as without the deselect args), and `test_open_pr_e2e.py::test_open_pr_smoke_no_win_path` reproduced a host FAIL because Plan 04-10's zero-safe baseline now makes drift=0.0 produce winners on host (exactly the behaviour that made the test container-only in the first place).
- **Fix:** Switched the 4 `--deselect` flags to `--ignore=...` (collection-time skip, cwd-relative paths — preserves the plan author's intended path form). Updated the YAML invariant comment to reference `--ignore` and added a 4-line note explaining the pytest rootdir gotcha for future maintainers.
- **Files modified:** `.github/workflows/tournament-harness.yml` (only the `integration-fake-docker` step; Task 2's `container-integration` job is unaffected because it runs the container-only tests by explicit positional path inside the container — no deselect involved).
- **Commit:** `37a2d6a`.
- **Evidence:**
  - Pre-fix (plan literal): `40 tests collected` (zero deselected — verified via `pytest --collect-only`)
  - Post-fix (`--ignore`): `26 tests collected` (14 ignored)
  - Pre-fix host smoke: `1 failed (test_open_pr_smoke_no_win_path), 35 passed, 4 skipped`
  - Post-fix host smoke: `26 passed in 5.52s` (no fails, no skips)

### No other deviations.

## Hand-off Note for Future Phases

When adding a new integration test under `services/tournament-harness/tests/integration/`, the **default policy is that `integration-fake-docker` picks it up automatically** via the directory glob (`pytest tests/integration/ -v`). Only extend the `--ignore` list at lines 87-90 of `.github/workflows/tournament-harness.yml` if the new test is:

- **container-only** (requires the canonical metric chain inside the tournament-harness image — see Plan 04-08 namespace-merge), in which case add the same path to the `container-integration` job's positional pytest args at lines 122-124; OR
- **real-stack-only** (requires live postgres/timescaledb/redis/rabbitmq — see `test_end_to_end_tournament.py`), in which case add to the schedule-only `integration-real-stack` job at line 161.

See 04-UAT.md Test 7 for the invariant rationale. The YAML comment block above the `integration-fake-docker` run step states this verbatim and warns about the pytest rootdir footgun that bit this plan's literal YAML.

## CI Run

**Not yet triggered.** Per the project rule "never push to remote unless user explicitly asks", the commit is local-only. The workflow will fire on the next push of this branch or via `gh workflow run tournament-harness.yml --ref <branch>` (workflow_dispatch is wired). The local host + container smoke runs above prove both new/changed jobs will go green when CI does run.

## Threat Surface Update

No new threat surface introduced. The 5 threat register entries from the plan (T-04-09-01 through T-04-09-05) all mitigate as specified:

- **T-04-09-01** (Repudiation — silent SKIP-pass): mitigated by the `grep -E '^[0-9]+ skipped' /tmp/container-integration.log` guard at lines 134-138 of the workflow; verified locally — `13 passed, 0 skipped` (no skipped count line) means the guard does not fire on healthy state.
- **T-04-09-02** (Tampering — future contributor adds host-skipping test without `--ignore`): mitigated by the YAML comment invariant block. Additionally hardened by the deviation note above — anyone copy-pasting the plan's literal `--deselect` form will now see the cautionary comment.
- **T-04-09-03** (DoS — `--no-cache` build per PR): accepted (solo operator, low PR cadence).
- **T-04-09-04** (Tampering — accidental deletion of `integration-real-stack`): mitigated by the Task 3 verification script asserting `'integration-real-stack' in jobs` — re-run before commit confirmed.
- **T-04-09-05** (Information disclosure — runner secrets in container): accepted (no `env:` block exposes secrets; `docker compose run --rm` does not inherit runner secrets).

## Self-Check: PASSED

Files verified to exist:
- `.github/workflows/tournament-harness.yml` — FOUND (modified, +59/-2)
- `.planning/phases/04-tournament-significance-auto-pr/04-09-PLAN.md` — FOUND (newly tracked, frontmatter `wave: 3`, `depends_on: [08, 10]`)
- `.planning/phases/04-tournament-significance-auto-pr/04-09-SUMMARY.md` — FOUND (this file)

Commits verified in `git log`:
- `37a2d6a` (Task 1 + Task 2 + frontmatter bump) — FOUND

Workflow verification:
- 5 jobs in YAML: `tourn07-grep-gate`, `unit-tests`, `integration-fake-docker`, `container-integration`, `integration-real-stack` — VERIFIED
- `integration-real-stack` schedule guard preserved — VERIFIED
- `test_end_to_end_tournament.py` invocation in `integration-real-stack` step intact at line 161 — VERIFIED
